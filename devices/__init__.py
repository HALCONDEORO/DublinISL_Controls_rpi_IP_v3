#!/usr/bin/env python3
# devices/__init__.py — Re-exports del paquete de dispositivos
#
# Los archivos fuente viven en la raíz durante la migración.
# Este paquete los re-exporta para que el código nuevo use
# `from devices import CameraManager` manteniendo compatibilidad.

from camera_worker import CameraWorker, ViscaCommand
from camera_manager import CameraManager
from visca_protocol import ViscaProtocol, ViscaUICallbacks

__all__ = [
    "CameraWorker",
    "ViscaCommand",
    "CameraManager",
    "ViscaProtocol",
    "ViscaUICallbacks",
]
