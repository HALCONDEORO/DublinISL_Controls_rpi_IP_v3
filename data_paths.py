#!/usr/bin/env python3
# data_paths.py — Directorio persistente de datos de usuario
#
# Centraliza la ubicación de todos los archivos JSON que deben sobrevivir
# una reinstalación del software (git pull, rm -rf + clone, etc.).
#
# Directorio de datos: ~/.config/dublinisl/  (por defecto)
#   Override: variable de entorno DUBLINISL_DATA_DIR
#   Ejemplo:  DUBLINISL_DATA_DIR=/mnt/usb/backup python3 main.py
#
#   - Vive en el home del usuario, fuera del árbol de la app.
#   - Se crea automáticamente al arrancar la aplicación.
#   - En reinstalaciones solo se toca el directorio de la app; ~/.config queda intacto.
#
# Migración automática:
#   Si los archivos existen en el directorio antiguo (directorio de la app)
#   y NO en el nuevo, se copian automáticamente la primera vez que arranque
#   la app con esta versión. Esto evita perder datos en instalaciones existentes.

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'dublinisl'

# DUBLINISL_DATA_DIR permite al administrador apuntar los datos a cualquier ruta
# (NAS, USB, directorio de pruebas) sin tocar el código.
CONFIG_DIR = Path(os.environ.get('DUBLINISL_DATA_DIR', _DEFAULT_CONFIG_DIR))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Rutas de archivos de datos
CHAIRMAN_PRESETS_FILE = CONFIG_DIR / 'chairman_presets.json'
SEAT_NAMES_FILE       = CONFIG_DIR / 'seat_names.json'
SCHEDULE_FILE         = CONFIG_DIR / 'schedule.json'

_LEGACY_FILES = ('chairman_presets.json', 'seat_names.json', 'schedule.json')


def migrate_legacy_files() -> None:
    """
    Migra archivos desde el directorio de la app al CONFIG_DIR si no existen ya.

    Llamar una vez al arrancar la aplicación (desde main.py), antes de que
    cualquier módulo intente leer los archivos de datos.
    """
    app_dir = Path(__file__).parent
    for filename in _LEGACY_FILES:
        src = app_dir / filename
        dst = CONFIG_DIR / filename
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
                logger.info("Migrado %s → %s", src, dst)
            except OSError as exc:
                logger.warning("No se pudo migrar %s: %s", src, exc)
