#!/usr/bin/env python3
# visca_mixin.py — Mixin con todos los métodos de control VISCA
#
# Responsabilidad única: contener TODA la lógica de envío de comandos VISCA
# (movimiento, zoom, focus, exposición, presets).
#
# MOTIVO DE SEPARACIÓN: estos métodos son independientes del layout de la UI.
# Separarlos permite modificar comandos VISCA sin tocar main_window.py, y
# facilita añadir tests unitarios con un mock de _send_cmd.
#
# PATRÓN MIXIN: esta clase no hereda de QMainWindow.  Se mezcla con
# MainWindow en main_window.py mediante herencia múltiple.  Accede a
# atributos de MainWindow (self.Cam1, self.SpeedSlider, etc.) porque
# en tiempo de ejecución self es una instancia de MainWindow.

from __future__ import annotations  # Permite type hints modernos en Python <3.10

import logging
import socket
import binascii
import threading

from PyQt5.QtWidgets import QMessageBox

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    PRESET_MAP, SPEED_MIN, SPEED_MAX, SOCKET_TIMEOUT, VISCA_PORT
    # SPEED_MIN se importa aquí (nivel de módulo) y NO dentro de _speed_label_text()
    # — importar dentro de una función es válido pero va contra PEP 8 y confunde.
)

logger = logging.getLogger(__name__)


class ViscaMixin:

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
        Para comandos frecuentes (movimiento continuo) se usa _send_cmd_async
        que delega en CameraWorker con socket persistente.
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

    def _send_cmd_async(self, ip: str, cam_id_hex: str, cmd_suffix: str):
        """
        Envía un comando VISCA en background sin esperar respuesta.
        Delega en CameraWorker (socket persistente, cola, reconexión automática).
        """
        worker = self._workers.get(ip)
        if worker:
            worker.send(cam_id_hex + cmd_suffix)
        else:
            # Fallback: thread puntual si el worker no existe (no debería ocurrir)
            threading.Thread(
                target=self._send_cmd,
                args=(ip, cam_id_hex, cmd_suffix),
                daemon=True
            ).start()

    def _send_cmd_priority(self, ip: str, cam_id_hex: str, cmd_suffix: str):
        """
        Vacía la cola del worker y coloca este comando en primer lugar.
        Usar exclusivamente para STOP: garantiza que ningún comando de
        movimiento acumulado retrase la parada.
        """
        worker = self._workers.get(ip)
        if worker:
            worker.send_priority(cam_id_hex + cmd_suffix)
        else:
            threading.Thread(
                target=self._send_cmd,
                args=(ip, cam_id_hex, cmd_suffix),
                daemon=True
            ).start()

    def _active_cam(self) -> tuple[str, str]:
        """
        Devuelve (ip, cam_id) de la cámara actualmente seleccionada en la UI.
        Centraliza la lectura del toggle Cam1/Cam2 para no repetirlo en cada método.
        """
        if self.Cam1.isChecked():
            return IPAddress, Cam1ID
        return IPAddress2, Cam2ID

    def ErrorCapture(self):
        """Muestra diálogo de error de red. Se llama cuando _send_cmd devuelve False."""
        QMessageBox.warning(self, 'Camera Control Error',
                            'A network error occurred. Check camera connections.')

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers de velocidad
    # ─────────────────────────────────────────────────────────────────────────

    def _get_speed(self) -> int:
        """
        Lee la velocidad actual del slider (1-18).
        Se usa directamente como byte de velocidad pan/tilt en los comandos VISCA.
        """
        return self.SpeedSlider.value()

    def _get_zoom_speed(self) -> int:
        """
        Convierte la velocidad del slider (1-18) a escala de zoom (1-7).
        El protocolo VISCA limita la velocidad de zoom a 0x00-0x07.
        Se escala proporcionalmente y se clampea para evitar valores fuera de rango.
        """
        return max(1, min(7, round(self.SpeedSlider.value() * 7 / SPEED_MAX)))

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
        self.SpeedValueLabel.setText(self._speed_label_text(value))

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
        self._send_cmd_async(ip, cam_id,
            f"010601{pan_spd:02X}{tilt_spd:02X}{pan_dir:02X}{tilt_dir:02X}FF")

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
        self._send_cmd_priority(ip, cam_id, "01060100000303FF")

    def HomeButton(self):
        """Mueve la cámara activa a su posición Home."""
        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, "010604FF")

    def _send_comments_cam_home(self):
        """Manda la cámara Comments (Cam2) a Home. Llamado por el ATEMMonitor."""
        self._send_cmd_async(IPAddress2, Cam2ID, "010604FF")

    # ─────────────────────────────────────────────────────────────────────────
    #  Zoom
    # ─────────────────────────────────────────────────────────────────────────
    # Formato VISCA zoom variable: 8x 01 04 07 <speed_nibble> FF
    #   Zoom In:  speed = 0x20 | zoom_speed  (nibble alto = 2)
    #   Zoom Out: speed = 0x30 | zoom_speed  (nibble alto = 3)
    #   Stop:     0x00

    def ZoomIn(self):
        ip, cam_id = self._active_cam()
        # OR con 0x20: nibble alto = 2 (zoom in), nibble bajo = velocidad
        self._send_cmd_async(ip, cam_id, f"010407{0x20 | self._get_zoom_speed():02X}FF")

    def ZoomOut(self):
        ip, cam_id = self._active_cam()
        # OR con 0x30: nibble alto = 3 (zoom out), nibble bajo = velocidad
        self._send_cmd_async(ip, cam_id, f"010407{0x30 | self._get_zoom_speed():02X}FF")

    def ZoomStop(self):
        ip, cam_id = self._active_cam()
        self._send_cmd_async(ip, cam_id, "01040700FF")

    # ─────────────────────────────────────────────────────────────────────────
    #  Focus
    # ─────────────────────────────────────────────────────────────────────────

    def AutoFocus(self):
        ip, cam_id = self._active_cam()
        ok = self._send_cmd(ip, cam_id, "01043802FF")
        if ok:
            cam_key = 1 if ip == IPAddress else 2
            self.focus_mode[cam_key] = 'auto'
            self._update_focus_ui()
        else:
            self.ErrorCapture()

    def ManualFocus(self):
        ip, cam_id = self._active_cam()
        ok = self._send_cmd(ip, cam_id, "01043803FF")
        if ok:
            cam_key = 1 if ip == IPAddress else 2
            self.focus_mode[cam_key] = 'manual'
            self._update_focus_ui()
        else:
            self.ErrorCapture()

    def OnePushAF(self):
        """Dispara un autofocus puntual y luego queda en modo manual."""
        ip, cam_id = self._active_cam()
        ok = self._send_cmd(ip, cam_id, "01041801FF")
        self._right_panel._flash_button(self._right_panel.btn_one_push_af, ok)
        if not ok:
            self.ErrorCapture()

    # ─────────────────────────────────────────────────────────────────────────
    #  Exposición
    # ─────────────────────────────────────────────────────────────────────────

    def BrightnessUp(self):
        """Sube la exposición un paso (modo exposición manual)."""
        ip, cam_id = self._active_cam()
        ok = self._send_cmd(ip, cam_id, "01040D02FF")
        if ok:
            cam_key = 1 if ip == IPAddress else 2
            self.exposure_level[cam_key] = min(7, self.exposure_level[cam_key] + 1)
            self._update_exposure_ui()
        self._right_panel._flash_button(self._right_panel.btn_brighter, ok)
        if not ok:
            self.ErrorCapture()

    def BrightnessDown(self):
        """Baja la exposición un paso."""
        ip, cam_id = self._active_cam()
        ok = self._send_cmd(ip, cam_id, "01040D03FF")
        if ok:
            cam_key = 1 if ip == IPAddress else 2
            self.exposure_level[cam_key] = max(-7, self.exposure_level[cam_key] - 1)
            self._update_exposure_ui()
        self._right_panel._flash_button(self._right_panel.btn_darker, ok)
        if not ok:
            self.ErrorCapture()

    def BacklightToggle(self):
        """
        Activa/desactiva la compensación de contraluz.
        El estado se guarda por cámara (backlight_on dict) para que
        el botón refleje el estado real al cambiar entre cámaras.
        """
        ip, cam_id = self._active_cam()
        cam_key = 1 if ip == IPAddress else 2

        if self.backlight_on[cam_key]:
            # Desactivar backlight compensation
            if self._send_cmd(ip, cam_id, "01043303FF"):
                self.backlight_on[cam_key] = False
        else:
            # Activar backlight compensation
            if self._send_cmd(ip, cam_id, "01043302FF"):
                self.backlight_on[cam_key] = True

        self._update_backlight_ui()

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
            ip, cam_id = IPAddress, Cam1ID
            cam_name = 'Platform'
        else:
            # Presets de asiento: cámara activa en la UI
            ip, cam_id = self._active_cam()
            cam_name = "Platform" if self.Cam1.isChecked() else "Comments"

        if self.BtnCall.isChecked():
            # Modo Call: recall preset → 01 04 3F 02 <preset> FF
            if not self._send_cmd(ip, cam_id, f"01043f02{preset_hex}ff"):
                self.ErrorCapture()

        elif self.BtnSet.isChecked():
            # Modo Set: confirmar antes de sobreescribir un preset
            reply = QMessageBox.question(
                self, f'Record Preset {preset_number} ({cam_name})',
                "Are you sure you want to record this preset?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Save preset → 01 04 3F 01 <preset> FF
                if not self._send_cmd(ip, cam_id, f"01043f01{preset_hex}ff"):
                    self.ErrorCapture()
