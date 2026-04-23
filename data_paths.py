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

import json
import logging
import os
import shutil
import zipfile
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

_DATA_FILES = (CHAIRMAN_PRESETS_FILE, SEAT_NAMES_FILE, SCHEDULE_FILE)
_LEGACY_FILES = ('chairman_presets.json', 'seat_names.json', 'schedule.json')


def migrate_legacy_files(app_dir: Path | None = None) -> None:
    """
    Migra archivos desde el directorio de la app al CONFIG_DIR si no existen ya.

    Llamar una vez al arrancar la aplicación (desde main.py), antes de que
    cualquier módulo intente leer los archivos de datos.
    app_dir se puede pasar explícitamente en tests para aislar la llamada.
    """
    if app_dir is None:
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


def export_backup(dest_zip: Path) -> list[str]:
    """
    Crea un archivo ZIP con todos los archivos de datos existentes.

    Devuelve la lista de nombres de archivos incluidos en el ZIP.
    Lanza OSError / zipfile.BadZipFile si la escritura falla.
    """
    included: list[str] = []
    with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in _DATA_FILES:
            if f.exists():
                zf.write(f, f.name)
                included.append(f.name)
    logger.info("Backup exportado a %s (%d archivos)", dest_zip, len(included))
    return included


def import_backup(zip_path: Path) -> list[str]:
    """
    Restaura archivos de datos desde un ZIP de backup.

    - Valida que cada entrada sea JSON válido antes de escribir.
    - Guarda copia .bak del archivo existente antes de sobreescribir.
    - Devuelve la lista de nombres restaurados.
    - Lanza ValueError si el ZIP no contiene ningún archivo reconocido.
    - Lanza json.JSONDecodeError si algún archivo no es JSON válido.
    - Lanza zipfile.BadZipFile si el ZIP está corrupto.
    """
    valid_names = {f.name for f in _DATA_FILES}
    restored: list[str] = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        found = [n for n in zf.namelist() if n in valid_names]
        if not found:
            raise ValueError(
                "El ZIP no contiene archivos de datos reconocidos "
                f"({', '.join(sorted(valid_names))})"
            )

        for name in found:
            raw = zf.read(name).decode('utf-8')
            json.loads(raw)  # valida JSON antes de tocar disco — lanza JSONDecodeError si corrupto

            dst = CONFIG_DIR / name
            if dst.exists():
                shutil.copy2(dst, dst.with_suffix('.bak'))

            # Escritura atómica: si el proceso muere a mitad, dst no queda corrupto
            tmp = dst.with_suffix('.tmp')
            try:
                tmp.write_text(raw, encoding='utf-8')
                os.replace(tmp, dst)
            except OSError as exc:
                tmp.unlink(missing_ok=True)
                logger.error("No se pudo restaurar %s: %s", name, exc)
                continue  # no añadir a restored si la escritura falló

            restored.append(name)
            logger.info("Restaurado %s desde %s", name, zip_path)

    return restored
