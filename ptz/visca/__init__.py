#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# ptz/visca/__init__.py — API pública del paquete VISCA

from .types import PanDir, TiltDir, ZOOM_MAX
from .errors import ViscaError, ViscaNetworkError, ViscaParseError
from . import commands, parser
from .worker import CameraWorker, CameraWorkerSignals, ViscaCommand
from .manager import CameraManager
from .protocol import ViscaProtocol, ViscaUICallbacks
# ViscaController no se re-exporta aquí: depende de Qt.
# Importar directamente: from ptz.visca.controller import ViscaController

__all__ = [
    "PanDir", "TiltDir", "ZOOM_MAX",
    "ViscaError", "ViscaNetworkError", "ViscaParseError",
    "commands", "parser",
    "CameraWorker", "CameraWorkerSignals", "ViscaCommand",
    "CameraManager",
    "ViscaProtocol", "ViscaUICallbacks",
]
