#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# ptz/visca/manager.py — Gestor centralizado de estado y workers de cámaras PTZ
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

import threading
from typing import Callable, Optional

from config import CAM1, CAM2, CameraConfig
from .worker import CameraWorker


class CameraManager:
    """
    Gestión centralizada de cámaras PTZ.

    Encapsula:
      - Workers TCP persistentes (uno por cámara).
      - Cache de zoom para evitar queries de red innecesarias.
      - Estado per-cámara: backlight, focus y nivel de exposición.

    Índices de cámara: 1 = CAM1 (Platform), 2 = CAM2 (Comments).
    """

    def __init__(self, cam1: CameraConfig, cam2: CameraConfig,
                 on_worker_ready: Optional[Callable[['CameraWorker'], None]] = None):
        self._cam1_ip = cam1.ip
        self._cam2_ip = cam2.ip
        self._on_worker_ready = on_worker_ready

        # Workers creados bajo demanda: el thread TCP no arranca hasta el
        # primer acceso, evitando conexiones con IPs aún no validadas.
        self._workers: dict[str, CameraWorker] = {}

        # Cache de zoom: None = sin valor local, necesita query de red.
        # Clave: cam_key (1 o 2). Valor: último porcentaje enviado a la cámara.
        self._zoom_cache: dict[int, Optional[int]] = {1: None, 2: None}

        # Flags de query en vuelo: evitan lanzar un segundo thread si ya hay uno
        # consultando zoom o AE de esa cámara (race condition tras preset recall).
        # _inflight_lock protege el check-and-set de ambos flags: sin lock, dos
        # threads pueden leer False simultáneamente y ambos proceder (TOCTOU).
        self._inflight_lock:      threading.Lock  = threading.Lock()
        self._zoom_query_inflight: dict[int, bool] = {1: False, 2: False}
        self._ae_query_inflight:   dict[int, bool] = {1: False, 2: False}

        # Estado por cámara. Clave: cam_key (1 o 2).
        self.backlight_on:   dict[int, bool] = {1: False, 2: False}
        self.focus_mode:     dict[int, str]  = {1: 'auto', 2: 'auto'}
        self.exposure_level: dict[int, int]  = {1: 0,      2: 0     }
        # 'auto' cubre Full Auto, Shutter Priority, Iris Priority.
        # 'manual' y 'bright' usan CAM_Bright (0D) en lugar de CAM_ExpComp (0E).
        self.ae_mode:        dict[int, str]  = {1: 'auto', 2: 'auto'}

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
            w = CameraWorker(ip)
            self._workers[ip] = w
            if self._on_worker_ready:
                self._on_worker_ready(w)
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

    def zoom_query_try_acquire(self, ip: str) -> bool:
        """
        Intenta reservar el slot de query de zoom para esta cámara.
        Devuelve True (y marca inflight) si no había query en vuelo.
        Devuelve False si ya hay uno activo: el llamador debe descartarse.
        Operación atómica mediante _inflight_lock para evitar TOCTOU.
        """
        with self._inflight_lock:
            key = self.cam_key(ip)
            if self._zoom_query_inflight[key]:
                return False
            self._zoom_query_inflight[key] = True
            return True

    def zoom_query_release(self, ip: str):
        """Libera el slot de query de zoom tras completarse el thread."""
        with self._inflight_lock:
            self._zoom_query_inflight[self.cam_key(ip)] = False

    def ae_query_try_acquire(self, ip: str) -> bool:
        """
        Intenta reservar el slot de query de AE para esta cámara.
        Devuelve True (y marca inflight) si no había query en vuelo.
        Devuelve False si ya hay uno activo: el llamador debe descartarse.
        Operación atómica mediante _inflight_lock para evitar TOCTOU.
        """
        with self._inflight_lock:
            key = self.cam_key(ip)
            if self._ae_query_inflight[key]:
                return False
            self._ae_query_inflight[key] = True
            return True

    def ae_query_release(self, ip: str):
        """Libera el slot de query de AE tras completarse el thread."""
        with self._inflight_lock:
            self._ae_query_inflight[self.cam_key(ip)] = False
