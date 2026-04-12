#!/usr/bin/env python3
# visca_mixin.py — Controlador VISCA inyectado por composición en MainWindow
#
# Responsabilidad única: contener TODA la lógica de envío de comandos VISCA
# (movimiento, zoom, focus, exposición, presets).
#
# MOTIVO DE SEPARACIÓN: estos métodos son independientes del layout de la UI.
# Separarlos permite modificar comandos VISCA sin tocar main_window.py, y
# facilita añadir tests unitarios con un mock de la ventana.
#
# PATRÓN COMPOSICIÓN: esta clase recibe la ventana principal (window) en su
# constructor y accede a sus widgets y datos a través de self._w.
# Reemplaza el patrón mixin (herencia múltiple): para testear basta
# instanciar ViscaController con un SimpleNamespace o mock de ventana.

from __future__ import annotations

import logging
import socket
import binascii
import threading

from typing import Callable

from PyQt5.QtCore import QMetaObject, Qt, Q_ARG, QTimer
from PyQt5.QtWidgets import QMessageBox

from config import (
    CAM1, CAM2,
    PRESET_MAP, SPEED_MIN, SPEED_MAX, SOCKET_TIMEOUT, VISCA_PORT
)
from camera_worker import ViscaCommand

logger = logging.getLogger(__name__)


class ViscaController:

    def __init__(self, window):
        self._w = window

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers de envío VISCA
    # ─────────────────────────────────────────────────────────────────────────

    def _send_cmd(self, ip: str, cam_id_hex: str, cmd_suffix: str) -> bool:
        """
        Abre una conexión TCP, envía el comando VISCA y lee el ACK.
        Devuelve True si tuvo éxito, False si falló.

        Se usa para comandos que necesitan confirmación (presets, focus,
        sesión) donde importa saber si el comando llegó.

        NOTA: abre y cierra el socket en cada llamada (stateless).
        Para comandos frecuentes (movimiento continuo) usa _dispatch con ViscaCommand,
        que delega en CameraWorker con socket persistente y callbacks.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(binascii.unhexlify(cam_id_hex + cmd_suffix))
                s.recv(64)
            return True
        except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
            logger.error("_send_cmd %s: %s", ip, exc)
            return False

    def _ui(self, fn: Callable[[], None]):
        """
        Programa fn para ejecutarse en el hilo principal de Qt.
        Seguro llamarlo desde cualquier thread (p.ej. callbacks de ViscaCommand).
        """
        QTimer.singleShot(0, fn)

    def _dispatch(self, cmd: ViscaCommand):
        """
        Enruta ViscaCommand al worker de la cámara indicada en cmd.camera.
        Si cmd.priority=True vacía la cola antes de encolar (para STOP).
        Fallback a thread directo si el worker no existe (no debería ocurrir).
        """
        ip = CAM1.ip if cmd.camera == 1 else CAM2.ip
        worker = self._w._cameras.worker(ip)
        if worker:
            if cmd.priority:
                worker.send_priority(cmd)
            else:
                worker.send(cmd)
        else:
            threading.Thread(
                target=self._fallback_send, args=(ip, cmd), daemon=True
            ).start()

    def _fallback_send(self, ip: str, cmd: ViscaCommand):
        """
        Envío directo (sin worker) usado solo cuando CameraManager no tiene
        worker para esa IP. En la práctica no debería ejecutarse.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(cmd.payload)
                s.recv(64)
            if cmd.on_success:
                cmd.on_success()
        except (socket.timeout, socket.error, OSError) as exc:
            logger.error("_fallback_send %s: %s", ip, exc)
            if cmd.on_failure:
                cmd.on_failure()

    def _active_cam(self) -> tuple[str, str]:
        """
        Devuelve (ip, cam_id) de la cámara actualmente seleccionada en la UI.
        Centraliza la lectura del toggle Cam1/Cam2 para no repetirlo en cada método.
        """
        if self._w.Cam1.isChecked():
            return CAM1.ip, CAM1.cam_id
        return CAM2.ip, CAM2.cam_id

    def _cam_key(self, ip: str) -> int:
        """Devuelve 1 para Cam1 y 2 para Cam2. Clave de los dicts por cámara."""
        return 1 if ip == CAM1.ip else 2

    def ErrorCapture(self):
        """Muestra diálogo de error de red. Se llama cuando _send_cmd devuelve False."""
        QMessageBox.warning(self._w, 'Camera Control Error',
                            'A network error occurred. Check camera connections.')

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers de velocidad
    # ─────────────────────────────────────────────────────────────────────────

    def _get_speed(self) -> int:
        """
        Lee la velocidad actual del slider (1-18).
        Se usa directamente como byte de velocidad pan/tilt en los comandos VISCA.
        """
        return self._w.SpeedSlider.value()

    def _get_zoom_speed(self) -> int:
        """
        Convierte la velocidad del slider (1-18) a escala de zoom (1-7).
        El protocolo VISCA limita la velocidad de zoom a 0x00-0x07.
        Se escala proporcionalmente y se clampea para evitar valores fuera de rango.
        """
        return max(1, min(7, round(self._w.SpeedSlider.value() * 7 / SPEED_MAX)))

    def _speed_label_text(self, value: int) -> str:
        """
        Devuelve una etiqueta descriptiva de la velocidad para mostrar al operador.
        Hace la UI más comprensible que mostrar solo el número raw del slider.
        SPEED_MIN y SPEED_MAX se importan al nivel del módulo, no aquí.
        """
        mid = (SPEED_MIN + SPEED_MAX) / 2
        if value <= SPEED_MIN:
            desc = "minimum"
        elif value >= SPEED_MAX:
            desc = "maximum"
        elif value < mid - 2:
            desc = "slow"
        elif value > mid + 2:
            desc = "fast"
        else:
            desc = "medium"
        return f"Speed: {value}  ({desc})"

    def _on_speed_changed(self, value: int):
        """Callback del slider: actualiza la etiqueta de velocidad en tiempo real."""
        self._w.SpeedValueLabel.setText(self._speed_label_text(value))

    # ─────────────────────────────────────────────────────────────────────────
    #  Movimiento Pan/Tilt
    # ─────────────────────────────────────────────────────────────────────────
    # Formato VISCA: 8x 01 06 01 <pan_spd> <tilt_spd> <pan_dir> <tilt_dir> FF
    #   pan_dir:  01=Izq, 02=Der, 03=Parado
    #   tilt_dir: 01=Arriba, 02=Abajo, 03=Parado
    # La velocidad de los ejes parados se envía como 0x00 para no mover nada.

    def _move(self, pan_dir: int, tilt_dir: int,
              pan_spd: int = None, tilt_spd: int = None):
        """
        Envía comando de movimiento pan/tilt a la cámara activa.
        Si pan_spd/tilt_spd son None, lee la velocidad del SpeedSlider (retrocompatible).
        Los ejes con dirección 0x03 (parado) reciben velocidad 0 para
        no producir deriva accidental.
        """
        ip, cam_id = self._active_cam()
        if pan_spd is None:
            pan_spd = tilt_spd = self._get_speed()
        pan_spd  = 0 if pan_dir  == 0x03 else pan_spd
        tilt_spd = 0 if tilt_dir == 0x03 else tilt_spd
        self._dispatch(ViscaCommand(
            camera=self._cam_key(ip),
            payload=bytes.fromhex(
                cam_id + f"010601{pan_spd:02X}{tilt_spd:02X}{pan_dir:02X}{tilt_dir:02X}FF"
            ),
        ))

    # 8 direcciones: combinación de pan (01/02/03) y tilt (01/02/03)
    def UpLeft(self, pan_spd=None, tilt_spd=None):    self._move(0x01, 0x01, pan_spd, tilt_spd)
    def Up(self, pan_spd=None, tilt_spd=None):        self._move(0x03, 0x01, pan_spd, tilt_spd)
    def UpRight(self, pan_spd=None, tilt_spd=None):   self._move(0x02, 0x01, pan_spd, tilt_spd)
    def Left(self, pan_spd=None, tilt_spd=None):      self._move(0x01, 0x03, pan_spd, tilt_spd)
    def Right(self, pan_spd=None, tilt_spd=None):     self._move(0x02, 0x03, pan_spd, tilt_spd)
    def DownLeft(self, pan_spd=None, tilt_spd=None):  self._move(0x01, 0x02, pan_spd, tilt_spd)
    def Down(self, pan_spd=None, tilt_spd=None):      self._move(0x03, 0x02, pan_spd, tilt_spd)
    def DownRight(self, pan_spd=None, tilt_spd=None): self._move(0x02, 0x02, pan_spd, tilt_spd)

    def Stop(self):
        """
        Para el movimiento pan/tilt.
        Vacía la cola de comandos pendientes y coloca STOP en primer lugar,
        garantizando que ningún comando de movimiento acumulado retrase la parada.
        """
        ip, cam_id = self._active_cam()
        self._dispatch(ViscaCommand(
            camera=self._cam_key(ip),
            payload=bytes.fromhex(cam_id + "01060100000303FF"),
            priority=True,
        ))

    def HomeButton(self):
        """Mueve la cámara activa a su posición Home."""
        ip, cam_id = self._active_cam()
        self._dispatch(ViscaCommand(
            camera=self._cam_key(ip),
            payload=bytes.fromhex(cam_id + "010604FF"),
        ))

    def _send_comments_cam_home(self):
        """Manda la cámara Comments (Cam2) a Home. Llamado por el ATEMMonitor."""
        self._dispatch(ViscaCommand(
            camera=2,
            payload=bytes.fromhex(CAM2.cam_id + "010604FF"),
        ))

    # ─────────────────────────────────────────────────────────────────────────
    #  Zoom
    # ─────────────────────────────────────────────────────────────────────────
    # Formato VISCA zoom absoluto: 8x 01 04 47 0p 0q 0r 0s FF
    #   pqrs = 4 nibbles del valor (0x0000 wide–0x4000 tele)
    # Formato inquiry zoom:        8x 09 04 47 FF
    #   Respuesta:                 y0 50 0p 0q 0r 0s FF

    _ZOOM_MAX = 0x4000  # 16384 — valor VISCA máximo de zoom

    def ZoomAbsolute(self):
        """Envía la posición de zoom absoluta según el valor del ZoomSlider (0–100 %)."""
        ip, cam_id = self._active_cam()
        pct = self._w.ZoomSlider.value()
        self._w._cameras.set_zoom(ip, pct)          # actualizar cache con valor enviado
        pos = round(pct * self._ZOOM_MAX / 100)
        p, q, r, s = (pos >> 12) & 0xF, (pos >> 8) & 0xF, (pos >> 4) & 0xF, pos & 0xF
        self._dispatch(ViscaCommand(
            camera=self._cam_key(ip),
            payload=bytes.fromhex(cam_id + f"010447{p:02X}{q:02X}{r:02X}{s:02X}FF"),
        ))

    def _query_zoom(self, ip: str, cam_id: str) -> int | None:
        """Consulta el zoom actual vía VISCA inquiry. Devuelve valor 0–0x4000 o None."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(binascii.unhexlify(cam_id + "090447FF"))
                data = s.recv(64)
            if len(data) >= 7 and data[1] == 0x50:
                return ((data[2] & 0xF) << 12 | (data[3] & 0xF) << 8
                        | (data[4] & 0xF) << 4 | (data[5] & 0xF))
        except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
            logger.error("_query_zoom %s: %s", ip, exc)
        return None

    def _refresh_zoom_slider(self):
        """
        Actualiza el slider con el zoom de la cámara activa.
        Usa el cache si ya existe un valor enviado; hace query de red solo si es None.
        """
        ip, cam_id = self._active_cam()
        cached = self._w._cameras.get_zoom(ip)
        if cached is not None:
            self._w.ZoomSlider.setValue(cached)
            return

        def _fetch():
            val = self._query_zoom(ip, cam_id)
            if val is not None:
                pct = round(val * 100 / self._ZOOM_MAX)
                self._w._cameras.set_zoom(ip, pct)  # poblar cache desde red
                QMetaObject.invokeMethod(
                    self._w.ZoomSlider, "setValue",
                    Qt.QueuedConnection, Q_ARG(int, pct)
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _invalidate_zoom_cache(self, ip: str):
        """
        Invalida el cache de zoom para la cámara dada (preset recall mueve el zoom).
        Si es la cámara activa, refresca el slider inmediatamente vía red.
        """
        self._w._cameras.invalidate_zoom(ip)
        if self._active_cam()[0] == ip:
            self._refresh_zoom_slider()

    # ─────────────────────────────────────────────────────────────────────────
    #  Focus
    # ─────────────────────────────────────────────────────────────────────────

    def AutoFocus(self):
        ip, cam_id = self._active_cam()
        cam_key = self._cam_key(ip)
        def _ok():
            self._w._cameras.focus_mode[cam_key] = 'auto'
            self._ui(self._w._update_focus_ui)
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=bytes.fromhex(cam_id + "01043802FF"),
            on_success=_ok,
            on_failure=lambda: self._ui(self.ErrorCapture),
        ))

    def ManualFocus(self):
        ip, cam_id = self._active_cam()
        cam_key = self._cam_key(ip)
        def _ok():
            self._w._cameras.focus_mode[cam_key] = 'manual'
            self._ui(self._w._update_focus_ui)
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=bytes.fromhex(cam_id + "01043803FF"),
            on_success=_ok,
            on_failure=lambda: self._ui(self.ErrorCapture),
        ))

    def OnePushAF(self):
        """Dispara un autofocus puntual y luego queda en modo manual."""
        ip, cam_id = self._active_cam()
        btn = self._w._right_panel.btn_one_push_af
        def _ok():
            self._ui(lambda: self._w._right_panel._flash_button(btn, True))
        def _fail():
            self._ui(lambda: self._w._right_panel._flash_button(btn, False))
            self._ui(self.ErrorCapture)
        self._dispatch(ViscaCommand(
            camera=self._cam_key(ip),
            payload=bytes.fromhex(cam_id + "01041801FF"),
            on_success=_ok,
            on_failure=_fail,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    #  Exposición
    # ─────────────────────────────────────────────────────────────────────────

    def BrightnessUp(self):
        """Sube la exposición un paso (modo exposición manual)."""
        ip, cam_id = self._active_cam()
        cam_key = self._cam_key(ip)
        btn = self._w._right_panel.btn_brighter
        def _ok():
            self._w._cameras.exposure_level[cam_key] = min(
                7, self._w._cameras.exposure_level[cam_key] + 1)
            self._ui(self._w._update_exposure_ui)
            self._ui(lambda: self._w._right_panel._flash_button(btn, True))
        def _fail():
            self._ui(lambda: self._w._right_panel._flash_button(btn, False))
            self._ui(self.ErrorCapture)
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=bytes.fromhex(cam_id + "01040D02FF"),
            on_success=_ok,
            on_failure=_fail,
        ))

    def BrightnessDown(self):
        """Baja la exposición un paso."""
        ip, cam_id = self._active_cam()
        cam_key = self._cam_key(ip)
        btn = self._w._right_panel.btn_darker
        def _ok():
            self._w._cameras.exposure_level[cam_key] = max(
                -7, self._w._cameras.exposure_level[cam_key] - 1)
            self._ui(self._w._update_exposure_ui)
            self._ui(lambda: self._w._right_panel._flash_button(btn, True))
        def _fail():
            self._ui(lambda: self._w._right_panel._flash_button(btn, False))
            self._ui(self.ErrorCapture)
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=bytes.fromhex(cam_id + "01040D03FF"),
            on_success=_ok,
            on_failure=_fail,
        ))

    def BacklightToggle(self):
        """
        Activa/desactiva la compensación de contraluz.
        El estado se guarda por cámara (backlight_on dict) para que
        el botón refleje el estado real al cambiar entre cámaras.
        """
        ip, cam_id = self._active_cam()
        cam_key = self._cam_key(ip)
        if self._w._cameras.backlight_on[cam_key]:
            suffix, new_state = "01043303FF", False
        else:
            suffix, new_state = "01043302FF", True
        def _ok():
            self._w._cameras.backlight_on[cam_key] = new_state
            self._ui(self._w._update_backlight_ui)
        self._dispatch(ViscaCommand(
            camera=cam_key,
            payload=bytes.fromhex(cam_id + suffix),
            on_success=_ok,
            on_failure=lambda: self._ui(self._w._update_backlight_ui),
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
            → Van a la cámara activa (la que el operador haya seleccionado).

        Modo Call: envía recall preset (02).
        Modo Set:  pide confirmación y envía save preset (01).
        """
        preset_hex = PRESET_MAP.get(preset_number)
        if not preset_hex:
            logger.warning("go_to_preset: preset %d no está en PRESET_MAP", preset_number)
            return

        # Determinar qué cámara controlar
        if preset_number in (1, 2, 3):
            # Presets de plataforma: siempre Cam1 (Platform)
            ip, cam_id = CAM1.ip, CAM1.cam_id
            cam_name = 'Platform'
        else:
            # Presets de asiento: siempre Cam2 (Comments)
            ip, cam_id = CAM2.ip, CAM2.cam_id
            cam_name = 'Comments'

        if self._w.BtnCall.isChecked():
            # Modo Call: recall preset → 01 04 3F 02 <preset> FF
            self._dispatch(ViscaCommand(
                camera=self._cam_key(ip),
                payload=bytes.fromhex(cam_id + f"01043f02{preset_hex}ff"),
                on_success=lambda: self._invalidate_zoom_cache(ip),
                on_failure=lambda: self._ui(self.ErrorCapture),
            ))

        elif self._w.BtnSet.isChecked():
            # Modo Set: confirmar antes de sobreescribir un preset
            reply = QMessageBox.question(
                self._w, f'Record Preset {preset_number} ({cam_name})',
                "Are you sure you want to record this preset?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Save preset → 01 04 3F 01 <preset> FF
                self._dispatch(ViscaCommand(
                    camera=self._cam_key(ip),
                    payload=bytes.fromhex(cam_id + f"01043f01{preset_hex}ff"),
                    on_failure=lambda: self._ui(self.ErrorCapture),
                ))
