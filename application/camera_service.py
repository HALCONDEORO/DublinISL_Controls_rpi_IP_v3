#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# application/camera_service.py — Servicio de comandos de cámara
#
# Único punto de entrada para enviar comandos VISCA desde la capa de aplicación.
# Usa conexiones TCP directas (stateless) para comandos confirmados (presets)
# y el worker persistente para movimiento continuo.
# Sin Qt.

from __future__ import annotations

import binascii
import logging
import socket
from typing import TYPE_CHECKING

from camera_worker import ViscaCommand
from config import CAM1, CAM2, PRESET_MAP, PAN_SPEED_MAX, TILT_SPEED_MAX, ZOOM_DRIVE_MAX, VISCA_PORT, SOCKET_TIMEOUT

if TYPE_CHECKING:
    from camera_manager import CameraManager

logger = logging.getLogger(__name__)


class CameraService:
    """
    Traduce intenciones de negocio en comandos VISCA.

    Dos canales de envío:
      - send_confirmed(): socket TCP nuevo por comando. Para preset recall/save.
        Bloquea hasta recibir ACK (o timeout). Llamar desde hilo no-Qt.
      - send_queued(): encola en CameraWorker (socket persistente). Para pan/tilt/zoom.
        No bloquea. Si la cola está llena, descarta silenciosamente.
    """

    def __init__(self, manager: 'CameraManager') -> None:
        self._mgr = manager
        # Caps dinámicos: el watchdog de main_window los reduce en caso de error VISCA
        self.pan_cap:       int = PAN_SPEED_MAX   # 24
        self.tilt_cap:      int = TILT_SPEED_MAX  # 20
        self.zoom_drive_cap: int = ZOOM_DRIVE_MAX  # 7

    # ── Comandos confirmados (preset recall/save, power) ──────────────────

    def recall_preset(self, camera: int, slot: int) -> bool:
        preset_hex = PRESET_MAP.get(slot)
        if not preset_hex:
            logger.warning("recall_preset: slot %d no está en PRESET_MAP", slot)
            return False
        ip, cam_id = self._cam(camera)
        return self._send_confirmed(ip, cam_id, f"01043f02{preset_hex}ff")

    def save_preset(self, camera: int, slot: int) -> bool:
        preset_hex = PRESET_MAP.get(slot)
        if not preset_hex:
            logger.warning("save_preset: slot %d no está en PRESET_MAP", slot)
            return False
        ip, cam_id = self._cam(camera)
        return self._send_confirmed(ip, cam_id, f"01043f01{preset_hex}ff")

    def power_on(self, camera: int) -> bool:
        ip, cam_id = self._cam(camera)
        return self._send_confirmed(ip, cam_id, "01040002FF")

    def power_standby(self, camera: int) -> bool:
        ip, cam_id = self._cam(camera)
        return self._send_confirmed(ip, cam_id, "01040003FF")

    def home(self, camera: int) -> bool:
        ip, cam_id = self._cam(camera)
        return self._send_confirmed(ip, cam_id, "010604FF")

    # ── Comandos en cola (movimiento continuo) ────────────────────────────

    def move(self, camera: int, pan_speed: int, tilt_speed: int) -> None:
        # Derive VISCA direction bytes from sign; use absolute value for speed magnitude.
        # pan_dir:  01=Left, 02=Right, 03=Stop  |  tilt_dir: 01=Up, 02=Down, 03=Stop
        pan_dir  = 0x02 if pan_speed  > 0 else (0x01 if pan_speed  < 0 else 0x03)
        tilt_dir = 0x01 if tilt_speed > 0 else (0x02 if tilt_speed < 0 else 0x03)
        pan_abs  = 0 if pan_dir  == 0x03 else max(1, min(self.pan_cap,  abs(pan_speed)))
        tilt_abs = 0 if tilt_dir == 0x03 else max(1, min(self.tilt_cap, abs(tilt_speed)))
        _, cam_id = self._cam(camera)
        self._send_queued(camera, bytes.fromhex(
            cam_id + f"010601{pan_abs:02X}{tilt_abs:02X}{pan_dir:02X}{tilt_dir:02X}FF"
        ))

    def stop(self, camera: int) -> None:
        _, cam_id = self._cam(camera)
        self._send_queued(camera, bytes.fromhex(cam_id + "01060100000303FF"), priority=True)

    def zoom(self, camera: int, speed: int) -> None:
        # VISCA zoom drive: 8x 01 04 07 <byte> FF
        # 0x20-0x27 = tele (in), 0x30-0x37 = wide (out), 0x00 = stop
        _, cam_id = self._cam(camera)
        if speed == 0:
            zoom_byte = 0x00
        elif speed > 0:
            zoom_byte = 0x20 | min(self.zoom_drive_cap, abs(speed))
        else:
            zoom_byte = 0x30 | min(self.zoom_drive_cap, abs(speed))
        self._send_queued(camera, bytes.fromhex(cam_id + f"010407{zoom_byte:02X}FF"))

    # ── Zoom cache (delegado a CameraManager) ────────────────────────────

    def invalidate_zoom(self, camera: int) -> None:
        ip, _ = self._cam(camera)
        self._mgr.invalidate_zoom(ip)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _cam(self, camera: int) -> tuple[str, str]:
        """Devuelve (ip, cam_id_hex) para el índice dado."""
        if camera == 1:
            return CAM1.ip, CAM1.cam_id
        return CAM2.ip, CAM2.cam_id

    def _send_confirmed(self, ip: str, cam_id: str, cmd_hex: str) -> bool:
        """Abre TCP, envía, lee ACK. Bloquea hasta SOCKET_TIMEOUT."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((ip, VISCA_PORT))
                s.send(binascii.unhexlify(cam_id + cmd_hex))
                s.recv(64)
            return True
        except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
            logger.error("CameraService._send_confirmed %s: %s", ip, exc)
            return False

    def _send_queued(self, camera: int, payload: bytes, priority: bool = False) -> None:
        """Encola en CameraWorker (no bloquea)."""
        ip, _ = self._cam(camera)
        worker = self._mgr.worker(ip)
        cmd = ViscaCommand(camera=camera, payload=payload)
        if priority:
            worker.send_priority(cmd)
        else:
            worker.send(cmd)
