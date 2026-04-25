#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
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
