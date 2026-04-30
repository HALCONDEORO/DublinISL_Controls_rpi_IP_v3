#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# ptz/visca/protocol.py — Lógica VISCA pura, sin dependencias de Qt
#
# ViscaProtocol contiene toda la lógica de comandos VISCA (movimiento, zoom,
# focus, exposición, presets) desacoplada de cualquier framework de UI.
#
# MOTIVO DE SEPARACIÓN: visca_mixin.py mezclaba lógica VISCA con llamadas Qt
# (QTimer, QMetaObject, QMessageBox), lo que impedía instanciar el controlador
# en tests sin levantar QApplication.
#
# PATRÓN: ViscaProtocol recibe toda interacción con la UI como callbacks
# (ViscaUICallbacks). En producción, ViscaController los inyecta con
# implementaciones Qt. En tests basta con lambdas simples o mocks.

from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from config import (
    CAM1, CAM2,
    PRESET_MAP, SOCKET_TIMEOUT, VISCA_PORT,
    PAN_SPEED_MAX,
    PRESET_ZOOM_SETTLE_BASE, PRESET_ZOOM_SETTLE_MARGIN, PRESET_ZOOM_SETTLE_MAX,
    PRESET_ZOOM_POLL_INTERVAL,
)
from .worker import ViscaCommand
from .manager import CameraManager
from . import commands as vcmd, parser as vparse
from .types import PanDir, TiltDir, ZOOM_MAX

logger = logging.getLogger(__name__)


@dataclass
class ViscaUICallbacks:
    """
    Todos los puntos de contacto entre ViscaProtocol y la UI.

    En producción, ViscaController (Qt) los inyecta con implementaciones Qt.
    En tests, se pasan lambdas simples sin necesidad de QApplication:

        ui = ViscaUICallbacks(
            get_active_cam=lambda: (CAM1.ip, CAM1.cam_id),
            get_speed=lambda: 9,
            get_pan_cap=lambda: 24,
            get_tilt_cap=lambda: 20,
            get_zoom_value=lambda: 50,
            is_call_mode=lambda: True,
            is_set_mode=lambda: False,
            schedule_ui=lambda fn: fn(),
            update_zoom_slider=lambda pct: None,
            show_error=lambda: None,
            confirm_preset=lambda num, name: True,
            on_focus_changed=lambda: None,
            on_exposure_changed=lambda: None,
            on_backlight_changed=lambda: None,
            on_af_result=lambda ok: None,
            on_brightness_up_result=lambda ok: None,
            on_brightness_down_result=lambda ok: None,
        )
    """

    # ── Lectura de estado UI ─────────────────────────────────────────────────

    get_active_cam: Callable[[], tuple[str, str]]
    """Devuelve (ip, cam_id) de la cámara seleccionada en la UI."""

    get_speed: Callable[[], int]
    """Velocidad para pan/tilt por botón (devuelve el cap de pan como máximo)."""

    get_pan_cap: Callable[[], int]
    """Cap dinámico de velocidad pan (watchdog lo reduce si VISCA responde error)."""

    get_tilt_cap: Callable[[], int]
    """Cap dinámico de velocidad tilt (watchdog lo reduce si VISCA responde error)."""

    get_zoom_value: Callable[[], int]
    """Valor actual del ZoomSlider (0–100 %)."""

    is_call_mode: Callable[[], bool]
    """True si BtnCall está activo."""

    is_set_mode: Callable[[], bool]
    """True si BtnSet está activo."""

    # ── Threading / actualización de UI ─────────────────────────────────────

    schedule_ui: Callable[[Callable], None]
    """
    Programa fn para ejecutarse en el hilo principal de UI.
    En Qt: QTimer.singleShot(0, fn).
    Seguro llamarlo desde cualquier thread (p.ej. callbacks de ViscaCommand).
    """

    update_zoom_slider: Callable[[int], None]
    """
    Actualiza el ZoomSlider con el porcentaje dado.
    Debe ser thread-safe: se llama tanto desde el hilo principal (cache hit)
    como desde el thread del worker (query de red).
    En Qt: QMetaObject.invokeMethod con Qt.QueuedConnection.
    """

    # ── Diálogos ─────────────────────────────────────────────────────────────

    show_error: Callable[[], None]
    """Muestra diálogo de error de red."""

    confirm_preset: Callable[[int, str], bool]
    """
    Pide confirmación antes de sobreescribir un preset.
    Recibe (preset_number, cam_name). Devuelve True si el usuario confirma.
    En Qt: QMessageBox.question.
    """

    # ── Notificaciones de cambio de estado ───────────────────────────────────

    on_focus_changed: Callable[[], None]
    """Refresca los controles de focus en la UI."""

    on_exposure_changed: Callable[[], None]
    """Refresca el indicador de nivel de exposición en la UI."""

    on_backlight_changed: Callable[[], None]
    """Refresca el botón de backlight en la UI."""

    on_af_result: Callable[[bool], None]
    """Flash del botón One-Push AF: True = éxito, False = fallo."""

    on_brightness_up_result: Callable[[bool], None]
    """Flash del botón Brightness Up: True = éxito, False = fallo."""

    on_brightness_down_result: Callable[[bool], None]
    """Flash del botón Brightness Down: True = éxito, False = fallo."""


class ViscaProtocol:
    """
    Lógica VISCA pura, sin dependencias de Qt.

    Toda interacción con la UI se delega en los callbacks de ViscaUICallbacks.
    El estado de las cámaras (zoom cache, focus, exposición, backlight) vive
    en CameraManager, que tampoco tiene dependencias Qt.

    Para testear sin QApplication:
        cameras = CameraManager(CAM1, CAM2)
        proto   = ViscaProtocol(cameras, <ViscaUICallbacks con mocks>)
        proto.Up()  # no se necesita QApplication
    """

    def __init__(self, cameras: CameraManager, ui: ViscaUICallbacks):
        self._cameras = cameras
        self._ui_cb   = ui
        self._preset_stop_events: dict[str, threading.Event] = {}  # ip → stop event del poll activo
        self._stop_lock = threading.Lock()  # protege accesos concurrentes a _preset_stop_events

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers internos
    # ─────────────────────────────────────────────────────────────────────────

    def _ui(self, fn: Callable[[], None]):
        """Programa fn en el hilo de UI vía el callback inyectado."""
        self._ui_cb.schedule_ui(fn)

    def _send_cmd(self, ip: str, payload: bytes) -> bool:
        """
        Abre una conexión TCP, envía el payload VISCA y lee el ACK.
        Devuelve True si tuvo éxito, False si falló.

        NOTA: abre y cierra el socket en cada llamada (stateless).
        Para comandos frecuentes (movimiento continuo) usa _dispatch con ViscaCommand,
        que delega en CameraWorker con socket persistente y callbacks.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(payload)
                s.recv(64)
            return True
        except (socket.timeout, socket.error, OSError) as exc:
            logger.error("_send_cmd %s: %s", ip, exc)
            return False

    def _dispatch(self, cmd: ViscaCommand):
        """
        Enruta ViscaCommand al worker de la cámara indicada en cmd.camera.
        Si cmd.priority=True vacía la cola antes de encolar (para STOP).
        """
        if cmd.camera == 1:
            ip = CAM1.ip
        elif cmd.camera == 2:
            ip = CAM2.ip
        else:
            logger.error("_dispatch: camera key inválido %r — comando descartado", cmd.camera)
            return
        worker = self._cameras.worker(ip)
        if cmd.priority:
            worker.send_priority(cmd)
        else:
            worker.send(cmd)

    def _active_cam(self) -> tuple[str, str]:
        """
        Devuelve (ip, cam_id) de la cámara actualmente seleccionada en la UI.
        Centraliza la lectura del toggle Cam1/Cam2 para no repetirlo en cada método.
        """
        return self._ui_cb.get_active_cam()


    # ─────────────────────────────────────────────────────────────────────────
    #  Movimiento Pan/Tilt
    # ─────────────────────────────────────────────────────────────────────────
    # Formato VISCA: 8x 01 06 01 <pan_spd> <tilt_spd> <pan_dir> <tilt_dir> FF
    #   pan_dir:  01=Izq, 02=Der, 03=Parado
    #   tilt_dir: 01=Arriba, 02=Abajo, 03=Parado
    # La velocidad de los ejes parados se envía como 0x00 para no mover nada.

    def _move(self, pan_dir: PanDir, tilt_dir: TiltDir,
              pan_spd: Optional[int] = None, tilt_spd: Optional[int] = None):
        """
        Envía comando de movimiento pan/tilt a la cámara activa.
        Si pan_spd/tilt_spd son None, lee la velocidad del SpeedSlider (retrocompatible).
        Los ejes con dirección STOP reciben velocidad 0 para no producir deriva accidental.
        """
        ip, cam_id = self._active_cam()
        if pan_spd is None:
            pan_spd = tilt_spd = self._ui_cb.get_speed()
        pan_spd  = 0 if pan_dir  == PanDir.STOP  else max(1, min(self._ui_cb.get_pan_cap(),  pan_spd))
        tilt_spd = 0 if tilt_dir == TiltDir.STOP else max(1, min(self._ui_cb.get_tilt_cap(), tilt_spd))
        self._dispatch(ViscaCommand(
            camera=self._cameras.cam_key(ip),
            payload=vcmd.pan_tilt(cam_id, pan_spd, tilt_spd, pan_dir, tilt_dir),
        ))

    # 8 direcciones: combinación de PanDir y TiltDir
    def UpLeft(self, pan_spd=None, tilt_spd=None):    self._move(PanDir.LEFT,  TiltDir.UP,   pan_spd, tilt_spd)
    def Up(self, pan_spd=None, tilt_spd=None):        self._move(PanDir.STOP,  TiltDir.UP,   pan_spd, tilt_spd)
    def UpRight(self, pan_spd=None, tilt_spd=None):   self._move(PanDir.RIGHT, TiltDir.UP,   pan_spd, tilt_spd)
    def Left(self, pan_spd=None, tilt_spd=None):      self._move(PanDir.LEFT,  TiltDir.STOP, pan_spd, tilt_spd)
    def Right(self, pan_spd=None, tilt_spd=None):     self._move(PanDir.RIGHT, TiltDir.STOP, pan_spd, tilt_spd)
    def DownLeft(self, pan_spd=None, tilt_spd=None):  self._move(PanDir.LEFT,  TiltDir.DOWN, pan_spd, tilt_spd)
    def Down(self, pan_spd=None, tilt_spd=None):      self._move(PanDir.STOP,  TiltDir.DOWN, pan_spd, tilt_spd)
    def DownRight(self, pan_spd=None, tilt_spd=None): self._move(PanDir.RIGHT, TiltDir.DOWN, pan_spd, tilt_spd)

    def Stop(self):
        """
        Para el movimiento pan/tilt.
        Vacía la cola de comandos pendientes y coloca STOP en primer lugar,
        garantizando que ningún comando de movimiento acumulado retrase la parada.
        """
        ip, cam_id = self._active_cam()
        self._dispatch(ViscaCommand(
            camera=self._cameras.cam_key(ip),
            payload=vcmd.pan_tilt_stop(cam_id),
            priority=True,
        ))

    def HomeButton(self):
        """Mueve la cámara activa a su posición Home."""
        ip, cam_id = self._active_cam()
        self._dispatch(ViscaCommand(
            camera=self._cameras.cam_key(ip),
            payload=vcmd.home(cam_id),
        ))

    def _send_comments_cam_home(self):
        """Manda la cámara Comments (Cam2) a Home. Llamado por el ATEMMonitor."""
        self._dispatch(ViscaCommand(
            camera=2,
            payload=vcmd.home(CAM2.cam_id),
        ))

    # ─────────────────────────────────────────────────────────────────────────
    #  Zoom
    # ─────────────────────────────────────────────────────────────────────────
    # Formato VISCA zoom absoluto: 8x 01 04 47 0p 0q 0r 0s FF
    #   pqrs = 4 nibbles del valor (0x0000 wide–0x4000 tele)
    # Formato inquiry zoom:        8x 09 04 47 FF
    #   Respuesta:                 y0 50 0p 0q 0r 0s FF

    def ZoomAbsolute(self):
        """Envía la posición de zoom absoluta según el valor del ZoomSlider (0–100 %)."""
        ip, cam_id = self._active_cam()
        pct = self._ui_cb.get_zoom_value()
        self._cameras.set_zoom(ip, pct)          # actualizar cache con valor enviado
        self._dispatch(ViscaCommand(
            camera=self._cameras.cam_key(ip),
            payload=vcmd.zoom_absolute(cam_id, pct),
        ))

    def _query_ae_and_exp_comp(self, ip: str, cam_id: str) -> tuple[str, Optional[int]]:
        """
        Consulta modo AE y nivel ExpComp en una sola sesión TCP.

        Envía dos inquiries en secuencia sobre la misma conexión, igual que
        _query_position_and_zoom. Usar una sola conexión evita fallos en cámaras
        que limitan conexiones simultáneas (algunos modelos admiten solo 1-2).

        Devuelve (ae_mode, exp_comp_level):
          ae_mode:         'auto' | 'manual' | 'bright'  — 'auto' como fallback seguro
          exp_comp_level:  -7..+7 mapeado desde 0-14, o None si la query falla
                           (cámara no soporta ExpComp inquiry, o modo no es auto)
        """
        ae_mode = 'auto'
        exp_level: Optional[int] = None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))

                s.send(vcmd.ae_mode_inquiry(cam_id))
                ae_data = s.recv(64)
                frame = vparse.inquiry_frame(ae_data, payload_len=1)
                if frame is not None:
                    ae_mode = vparse.ae_mode(frame)

                if ae_mode not in ('manual', 'bright'):
                    s.send(vcmd.exp_comp_inquiry(cam_id))
                    ec_data = s.recv(64)
                    frame = vparse.inquiry_frame(ec_data, payload_len=4)
                    if frame is not None:
                        exp_level = vparse.exp_comp_level(frame)

        except (socket.timeout, socket.error, OSError) as exc:
            logger.warning("_query_ae_and_exp_comp %s: %s", ip, exc)

        return ae_mode, exp_level

    def refresh_ae_mode_async(self, ip: str, cam_id: str,
                              active_ip: Optional[str] = None) -> None:
        """
        Consulta en background el modo AE y el nivel ExpComp real de la cámara
        en una sola sesión TCP, actualiza el cache y refresca la UI si es la activa.
        Descarta si ya hay un query en vuelo (guard atómico, evita TOCTOU).

        active_ip: si se llama desde un thread de background (p.ej. _preset_poll_loop),
                   pasar el snapshot capturado en el hilo Qt para evitar la lectura de
                   widgets fuera del hilo principal. Si None, se captura aquí (llamada
                   directa desde el hilo Qt).
        """
        if not self._cameras.ae_query_try_acquire(ip):
            return
        cam_key   = self._cameras.cam_key(ip)
        if active_ip is None:
            active_ip = self._active_cam()[0]  # seguro: llamada desde hilo Qt
        def _fetch():
            try:
                mode, level = self._query_ae_and_exp_comp(ip, cam_id)
                self._cameras.ae_mode[cam_key] = mode
                logger.info("AE mode cam%d (%s): %s", cam_key, ip, mode)
                if level is not None:
                    self._cameras.exposure_level[cam_key] = level
                    logger.info("ExpComp level cam%d (%s): %d", cam_key, ip, level)
                    if active_ip == ip:
                        self._ui(self._ui_cb.on_exposure_changed)
            finally:
                self._cameras.ae_query_release(ip)
        threading.Thread(target=_fetch, daemon=True).start()

    def _query_zoom(self, ip: str, cam_id: str) -> Optional[int]:
        """Consulta el zoom actual vía VISCA inquiry. Devuelve valor 0–0x4000 o None."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(vcmd.zoom_inquiry(cam_id))
                data = s.recv(64)
            return vparse.zoom(data)
        except (socket.timeout, socket.error, OSError) as exc:
            logger.error("_query_zoom %s: %s", ip, exc)
        return None

    def _query_position_and_zoom(self, ip: str, cam_id: str
                                 ) -> tuple[Optional[tuple[int, int]], Optional[int]]:
        """
        Una sola sesión TCP: envía PTZ Position Inquiry y Zoom Inquiry en secuencia.
        Devuelve ((pan, tilt), zoom_raw) — cualquiera puede ser None si falla.

        MOTIVO: dos consultas en una conexión reduce el overhead de setup TCP
        que se acumula en el polling de 300 ms durante un preset.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(vcmd.ptz_position_inquiry(cam_id))
                ptz_data  = s.recv(64)
                s.send(vcmd.zoom_inquiry(cam_id))
                zoom_data = s.recv(64)
            return vparse.ptz_position(ptz_data), vparse.zoom(zoom_data)
        except (socket.timeout, socket.error, OSError) as exc:
            logger.debug("_query_position_and_zoom %s: %s", ip, exc)
            return None, None

    def _refresh_zoom_slider(self):
        """
        Actualiza el slider con el zoom de la cámara activa.
        Usa el cache si ya existe un valor enviado; hace query de red solo si es None.
        """
        ip, cam_id = self._active_cam()
        cached = self._cameras.get_zoom(ip)
        if cached is not None:
            self._ui_cb.update_zoom_slider(cached)
            return

        if not self._cameras.zoom_query_try_acquire(ip):
            return  # ya hay un thread consultando esta cámara, ignorar

        def _fetch():
            try:
                val = self._query_zoom(ip, cam_id)
                if val is not None:
                    pct = vparse.zoom_to_pct(val)
                    self._cameras.set_zoom(ip, pct)  # poblar cache desde red
                    self._ui_cb.update_zoom_slider(pct)  # el callback es thread-safe
            finally:
                self._cameras.zoom_query_release(ip)

        threading.Thread(target=_fetch, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    #  Preset zoom polling
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_preset_ceiling(self) -> float:
        """
        Techo dinámico para el polling post-preset, en segundos.

        Escala inversamente con pan_cap: si el watchdog redujo la velocidad a
        la mitad, el movimiento tarda el doble → techo doble.
        Está acotado por PRESET_ZOOM_SETTLE_MAX para no esperar eternamente.
        """
        pan_cap = self._ui_cb.get_pan_cap()
        base = PRESET_ZOOM_SETTLE_BASE * (PAN_SPEED_MAX / max(pan_cap, 1))
        return min(base * PRESET_ZOOM_SETTLE_MARGIN, PRESET_ZOOM_SETTLE_MAX)

    def _start_preset_poll(self, ip: str, cam_id: str,
                           active_ip: str, ceiling: float) -> None:
        """Cancela el poll anterior para esta cámara (si existe) y arranca uno nuevo."""
        with self._stop_lock:
            prev = self._preset_stop_events.pop(ip, None)
            ev = threading.Event()
            self._preset_stop_events[ip] = ev
        if prev is not None:
            prev.set()  # fuera del lock: evita que el thread de cleanup haga busy-wait
        threading.Thread(
            target=self._preset_poll_loop,
            args=(ip, cam_id, active_ip, ceiling, ev),
            daemon=True,
            name=f"PresetPoll-{ip}",
        ).start()

    def _preset_poll_loop(self, ip: str, cam_id: str,
                          active_ip: str, ceiling: float,
                          stop: threading.Event) -> None:
        """
        Consulta posición PTZ y zoom cada PRESET_ZOOM_POLL_INTERVAL segundos.

        Actualiza el ZoomSlider en cada ciclo (actualización progresiva mientras
        la cámara se mueve). Para cuando AMBOS —posición PTZ y zoom— llevan 2
        ciclos sin cambiar, o se alcanza el techo de tiempo.

        active_ip: snapshot del hilo Qt en el momento del recall. Evita leer
        widgets desde este thread de background.

        Si la cámara no soporta PTZ Position Inquiry (pos siempre None), se
        usa estabilidad de zoom únicamente como criterio de parada.
        """
        deadline   = time.monotonic() + ceiling
        prev_pos   = None
        prev_zoom  = None
        stable_cnt = 0

        try:
            while not stop.is_set() and time.monotonic() < deadline:
                try:
                    pos, zoom_raw = self._query_position_and_zoom(ip, cam_id)
                except Exception as exc:
                    logger.error("_preset_poll_loop %s: ciclo abortado: %s", ip, exc)
                    break

                if zoom_raw is not None:
                    pct = vparse.zoom_to_pct(zoom_raw)
                    self._cameras.set_zoom(ip, pct)
                    if active_ip == ip:
                        self._ui_cb.update_zoom_slider(pct)

                # Criterio de estabilidad:
                #   pos_stable  = pos es None (cámara no lo soporta → ignorar) o no cambió
                #   zoom_stable = zoom conocido y sin cambio respecto al ciclo anterior
                # Ambos deben cumplirse para incrementar el contador.
                pos_stable  = (pos      is None) or (pos      == prev_pos)
                zoom_stable = (zoom_raw is not None) and (zoom_raw == prev_zoom)

                if pos_stable and zoom_stable:
                    stable_cnt += 1
                    if stable_cnt >= 2:
                        break
                else:
                    stable_cnt = 0

                if pos is not None:
                    prev_pos = pos
                if zoom_raw is not None:
                    prev_zoom = zoom_raw

                stop.wait(PRESET_ZOOM_POLL_INTERVAL)

        finally:
            # Solo borramos nuestra entrada; si _start_preset_poll ya registró
            # un nuevo evento para esta ip entre medias, no lo tocamos.
            with self._stop_lock:
                if self._preset_stop_events.get(ip) is stop:
                    self._preset_stop_events.pop(ip, None)
            # Preset puede haber cambiado el modo AE: refrescar siempre.
            # Pasamos active_ip capturado en el hilo Qt para no leer widgets desde aquí.
            self.refresh_ae_mode_async(ip, cam_id, active_ip)

    def cancel_preset_polls(self) -> None:
        """Cancela todos los polls activos. Llamar al terminar la sesión."""
        with self._stop_lock:
            events = list(self._preset_stop_events.values())
            self._preset_stop_events.clear()
        for ev in events:
            ev.set()  # fuera del lock: los threads de cleanup pueden adquirirlo inmediatamente

    # ─────────────────────────────────────────────────────────────────────────
    #  Focus
    # ─────────────────────────────────────────────────────────────────────────

    def _set_focus_mode(self, mode: str, payload_fn):
        ip, cam_id = self._active_cam()
        cam_key = self._cameras.cam_key(ip)
        def _ok():
            self._cameras.focus_mode[cam_key] = mode
            self._ui(self._ui_cb.on_focus_changed)
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=payload_fn(cam_id),
            on_success=_ok,
            on_failure=lambda: self._ui(self._ui_cb.show_error),
        ))

    def AutoFocus(self):
        self._set_focus_mode('auto', vcmd.focus_auto)

    def ManualFocus(self):
        self._set_focus_mode('manual', vcmd.focus_manual)

    def OnePushAF(self):
        """Dispara un autofocus puntual y luego queda en modo manual."""
        ip, cam_id = self._active_cam()
        def _ok():
            self._ui(lambda: self._ui_cb.on_af_result(True))
        def _fail():
            self._ui(lambda: self._ui_cb.on_af_result(False))
            self._ui(self._ui_cb.show_error)
        self._dispatch(ViscaCommand(
            camera=self._cameras.cam_key(ip),
            payload=vcmd.one_push_af(cam_id),
            on_success=_ok,
            on_failure=_fail,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    #  Exposición
    # ─────────────────────────────────────────────────────────────────────────

    def _adjust_brightness(self, delta: int):
        """
        Ajusta la exposición un paso. delta=+1 sube, delta=-1 baja.

        Modos manual/bright: CAM_Bright (0D), directo.
        Modo auto:           CAM_ExpCompMode on (3E) encadenado → CAM_ExpComp (0E).
                             El segundo comando solo se envía si el primero recibe ACK,
                             evitando actualizar el cache si exp_comp_on fue rechazado.
        """
        ip, cam_id = self._active_cam()
        cam_key = self._cameras.cam_key(ip)
        ae = self._cameras.ae_mode[cam_key]

        result_cb = (self._ui_cb.on_brightness_up_result if delta > 0
                     else self._ui_cb.on_brightness_down_result)

        def _ok():
            self._cameras.exposure_level[cam_key] = max(
                -7, min(7, self._cameras.exposure_level[cam_key] + delta))
            self._ui(self._ui_cb.on_exposure_changed)
            self._ui(lambda: result_cb(True))

        def _fail():
            self._ui(lambda: result_cb(False))
            self._ui(self._ui_cb.show_error)

        if ae in ('manual', 'bright'):
            payload = vcmd.brightness_up_direct(cam_id) if delta > 0 else vcmd.brightness_down_direct(cam_id)
            self._dispatch(ViscaCommand(camera=cam_key, payload=payload,
                                        on_success=_ok, on_failure=_fail))
        else:
            adj_payload = vcmd.exp_comp_up(cam_id) if delta > 0 else vcmd.exp_comp_down(cam_id)
            def _on_comp_on():
                self._dispatch(ViscaCommand(camera=cam_key, payload=adj_payload,
                                            on_success=_ok, on_failure=_fail))
            self._dispatch(ViscaCommand(camera=cam_key, payload=vcmd.exp_comp_on(cam_id),
                                        on_success=_on_comp_on, on_failure=_fail))

    def BrightnessUp(self):
        """Sube la exposición un paso."""
        self._adjust_brightness(+1)

    def BrightnessDown(self):
        """Baja la exposición un paso."""
        self._adjust_brightness(-1)

    def BacklightToggle(self):
        """
        Activa/desactiva la compensación de contraluz.
        El estado se guarda por cámara (backlight_on dict) para que
        el botón refleje el estado real al cambiar entre cámaras.
        """
        ip, cam_id = self._active_cam()
        cam_key = self._cameras.cam_key(ip)
        if self._cameras.backlight_on[cam_key]:
            payload, new_state = vcmd.backlight_off(cam_id), False
        else:
            payload, new_state = vcmd.backlight_on(cam_id), True
        def _ok():
            self._cameras.backlight_on[cam_key] = new_state
            self._ui(self._ui_cb.on_backlight_changed)
        def _fail():
            self._ui(self._ui_cb.show_error)
            self._ui(self._ui_cb.on_backlight_changed)  # refresca el botón al estado real
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=payload,
            on_success=_ok,
            on_failure=_fail,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    #  Presets
    # ─────────────────────────────────────────────────────────────────────────

    def go_to_preset(self, preset_number: int):
        """
        Llama o guarda un preset según el modo seleccionado (Call/Set).

        Presets 1-3 (plataforma: Chairman/Left/Right):
            → Siempre van a la cámara Platform (Cam1), independientemente
              de qué cámara esté seleccionada en la UI.
              MOTIVO: son posiciones fijas del orador, siempre en Cam1.

        Presets 4-129 (asientos):
            → Van siempre a la cámara Comments (Cam2), independientemente
              de la cámara seleccionada en la UI.
              MOTIVO: los asientos son posiciones del público, siempre en Cam2.

        Modo Call: envía recall preset (02).
        Modo Set:  pide confirmación y envía save preset (01).
        """
        if self._ui_cb.is_call_mode():
            self._recall_preset(preset_number)
        elif self._ui_cb.is_set_mode():
            self._save_preset(preset_number)
        else:
            logger.debug("go_to_preset %d: ningún modo activo (Call/Set), ignorado", preset_number)

    def _recall_preset(self, preset_number: int):
        """Modo Call: envía recall preset → 01 04 3F 02 <preset> FF."""
        preset_hex, ip, cam_id = self._resolve_preset(preset_number)
        if preset_hex is None:
            return
        # Snapshot en el hilo Qt: evita leer widgets desde el thread del worker.
        active_ip = self._active_cam()[0]
        def _on_preset_ack():
            ceiling = self._compute_preset_ceiling()
            self._start_preset_poll(ip, cam_id, active_ip, ceiling)

        self._dispatch(ViscaCommand(
            camera=self._cameras.cam_key(ip),
            payload=vcmd.preset_recall(cam_id, preset_hex),
            on_success=_on_preset_ack,
            on_failure=lambda: self._ui(self._ui_cb.show_error),
        ))

    def _save_preset(self, preset_number: int):
        """Modo Set: pide confirmación y envía save preset → 01 04 3F 01 <preset> FF."""
        preset_hex, ip, cam_id = self._resolve_preset(preset_number)
        if preset_hex is None:
            return
        cam_name = 'Platform' if preset_number in (1, 2, 3) else 'Comments'
        if self._ui_cb.confirm_preset(preset_number, cam_name):
            self._dispatch(ViscaCommand(
                camera=self._cameras.cam_key(ip),
                payload=vcmd.preset_save(cam_id, preset_hex),
                on_failure=lambda: self._ui(self._ui_cb.show_error),
            ))

    def _resolve_preset(self, preset_number: int):
        """Devuelve (preset_hex, ip, cam_id) para el preset dado, o (None, None, None) si inválido."""
        preset_hex = PRESET_MAP.get(preset_number)
        if not preset_hex:
            logger.warning("go_to_preset: preset %d no está en PRESET_MAP", preset_number)
            return None, None, None
        if preset_number in (1, 2, 3):
            return preset_hex, CAM1.ip, CAM1.cam_id
        return preset_hex, CAM2.ip, CAM2.cam_id
