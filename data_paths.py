#!/usr/bin/env python3
# data_paths.py — Directorio persistente de datos de usuario
#
# Centraliza la ubicación de todos los archivos JSON que deben sobrevivir
# una reinstalación del software (git pull, rm -rf + clone, etc.).
#
# Directorio de datos: ~/.config/dublinisl/
#   - Vive en el home del usuario, fuera del árbol de la app.
#   - Se crea automáticamente al importar este módulo.
#   - En reinstalaciones solo se toca el directorio de la app; ~/.config queda intacto.
#
# Migración automática:
#   Si los archivos existen en el directorio antiguo (directorio de la app)
#   y NO en el nuevo, se copian automáticamente la primera vez que arranque
#   la app con esta versión. Esto evita perder datos en instalaciones existentes.

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio persistente de configuración del usuario
CONFIG_DIR = Path.home() / '.config' / 'dublinisl'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Rutas de archivos de datos
CHAIRMAN_PRESETS_FILE = CONFIG_DIR / 'chairman_presets.json'
SEAT_NAMES_FILE       = CONFIG_DIR / 'seat_names.json'
SCHEDULE_FILE         = CONFIG_DIR / 'schedule.json'


def _migrate_if_needed(app_dir: Path) -> None:
    """
    Copia archivos de datos desde el directorio de la app al nuevo CONFIG_DIR
    si no existen ya en el destino.

    Llamar una vez al arrancar la aplicación (desde main.py).
    """
    for filename in ('chairman_presets.json', 'seat_names.json', 'schedule.json'):
        src = app_dir / filename
        dst = CONFIG_DIR / filename
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
                logger.info("Migrado %s → %s", src, dst)
            except OSError as exc:
                logger.warning("No se pudo migrar %s: %s", src, exc)


def migrate_legacy_files() -> None:
    """Migra archivos de datos desde el directorio de la app al CONFIG_DIR."""
    app_dir = Path(__file__).parent
    _migrate_if_needed(app_dir)
