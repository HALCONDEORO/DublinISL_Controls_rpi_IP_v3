#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# json_io.py — Lectura/escritura atómica de JSON con bloqueo por archivo

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _registry_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def load_json(path: Path | str, default: Any = None) -> Any:
    """Lee un JSON de forma segura. Devuelve `default` si el archivo no existe o está corrupto."""
    p = Path(path)
    lock = _lock_for(p)
    with lock:
        try:
            if not p.exists():
                return default
            data = json.loads(p.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return default


def save_json(path: Path | str, data: Any, indent: int = 2) -> bool:
    """
    Escribe `data` en `path` de forma atómica (temp-file + os.replace) con backup
    y bloqueo por archivo. Si el archivo ya existe, crea `.bak` antes de reemplazarlo.
    Devuelve True si tuvo éxito.
    """
    p = Path(path)
    lock = _lock_for(p)
    with lock:
        try:
            text = json.dumps(data, ensure_ascii=False, indent=indent)
            dir_ = p.parent
            dir_.mkdir(parents=True, exist_ok=True)

            if p.exists():
                bak = p.with_suffix('.bak')
                try:
                    shutil.copy2(p, bak)
                except OSError as exc:
                    logger.warning("No se pudo crear backup de %s: %s", p, exc)

            fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except OSError:
                        pass
                os.replace(tmp, p)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            return True
        except (OSError, TypeError, ValueError):
            return False
