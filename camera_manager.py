#!/usr/bin/env python3
# camera_manager.py — Gestor centralizado de estado y workers de cámaras PTZ
#
# Responsabilidad única: encapsular todo el estado mutable de las cámaras
# y los workers de red. Nadie más guarda estado de cámara.
#
# MOTIVO DE SEPARACIÓN: antes MainWindow acumulaba _workers, _zoom_cache,
# backlight_on, focus_mode y exposure_level como atributos sueltos, y
# ViscaController los accedía todos vía self._w.*. Con CameraManager ese
# estado vive en un solo lugar: self._cameras en la ventana principal.
# ViscaController solo traduce intención → comandos VISCA.

from __future__ import annotations

from typing import Optional

from config import CAM1, CAM2, CameraConfig
from camera_worker import CameraWorker


class CameraManager:
    """
    Gestión centralizada de cámaras PTZ.

    Encapsula:
      - Workers TCP persistentes (uno por cámara).
      - Cache de zoom para evitar queries de red innecesarias.
      - Estado per-cámara: backlight, focus y nivel de exposición.

    Índices de cámara: 1 = CAM1 (Platform), 2 = CAM2 (Comments).
    """

    def __init__(self, cam1: CameraConfig, cam2: CameraConfig):
        self._cam1_ip = cam1.ip
        self._cam2_ip = cam2.ip

        # Workers creados bajo demanda: el thread TCP no arranca hasta el
        # primer acceso, evitando conexiones con IPs aún no validadas.
        self._workers: dict[str, CameraWorker] = {}

        # Cache de zoom: None = sin valor local, necesita query de red.
        # Clave: cam_key (1 o 2). Valor: último porcentaje enviado a la cámara.
        self._zoom_cache: dict[int, Optional[int]] = {1: None, 2: None}

        # Estado por cámara. Clave: cam_key (1 o 2).
        self.backlight_on:   dict[int, bool] = {1: False, 2: False}
        self.focus_mode:     dict[int, str]  = {1: 'auto', 2: 'auto'}
        self.exposure_level: dict[int, int]  = {1: 0,      2: 0     }

    # ─────────────────────────────────────────────────────────────────────────
    #  Identificación de cámara
    # ─────────────────────────────────────────────────────────────────────────

    def cam_key(self, ip: str) -> int:
        """Devuelve 1 para CAM1 y 2 para CAM2. Clave de todos los dicts internos."""
        return 1 if ip == self._cam1_ip else 2

    # ─────────────────────────────────────────────────────────────────────────
    #  Workers
    # ─────────────────────────────────────────────────────────────────────────

    def worker(self, ip: str) -> CameraWorker:
        """
        Devuelve el CameraWorker para la IP dada, creándolo si aún no existe.
        El thread TCP se inicia aquí, no en __init__, para diferir la conexión
        hasta que se sabe que la IP es válida y necesaria.
        """
        if ip not in self._workers:
            self._workers[ip] = CameraWorker(ip)
        return self._workers[ip]

    # ─────────────────────────────────────────────────────────────────────────
    #  Zoom cache
    # ─────────────────────────────────────────────────────────────────────────

    def get_zoom(self, ip: str) -> Optional[int]:
        """Último porcentaje de zoom enviado a esta cámara, o None si no hay cache."""
        return self._zoom_cache.get(self.cam_key(ip))

    def set_zoom(self, ip: str, pct: int):
        """Actualiza el cache con el porcentaje de zoom enviado."""
        self._zoom_cache[self.cam_key(ip)] = pct

    def invalidate_zoom(self, ip: str):
        """
        Borra el cache de zoom para esta cámara.
        Usar tras un preset recall: los presets mueven el zoom a una
        posición desconocida, así el slider se sincronizará con la red.
        """
        self._zoom_cache[self.cam_key(ip)] = None
