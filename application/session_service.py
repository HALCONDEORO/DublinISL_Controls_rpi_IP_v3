#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# application/session_service.py — Estado y lógica de ciclo de vida de sesión
#
# Sin Qt. Trackea estado de sesión; la UI (SessionController) gestiona QTimer y diálogos.

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from application.camera_service import CameraService

logger = logging.getLogger(__name__)


class SessionService:
    """
    Encapsula el estado de sesión y los comandos de cámara asociados.

    La lógica de QTimer y diálogos permanece en SessionController (capa Qt).
    Esta clase solo gestiona el estado y los comandos VISCA de encendido/apagado.
    """

    def __init__(self, camera_svc: 'CameraService') -> None:
        self._camera = camera_svc
        self._active = False
        self._chairman: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._active

    def set_chairman(self, name: str) -> None:
        self._chairman = name
        logger.info("SessionService: chairman = '%s'", name)

    def start(self) -> None:
        """Envía Power ON a ambas cámaras. QTimer para Home lo gestiona SessionController."""
        self._camera.power_on(1)
        self._camera.power_on(2)
        self._active = True
        logger.info("SessionService: sesión iniciada")

    def home_both(self) -> None:
        """Envía Home a ambas cámaras. Llamar desde QTimer callback en SessionController."""
        self._camera.home(1)
        self._camera.home(2)

    def end(self) -> None:
        """Envía Standby a ambas cámaras."""
        self._camera.power_standby(1)
        self._camera.power_standby(2)
        self._active = False
        self._chairman = None
        logger.info("SessionService: sesión terminada")
