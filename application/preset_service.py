#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# application/preset_service.py — Servicio de presets personales del Chairman
#
# Dueño único del mapa nombre→slot. Ningún otro componente escribe en él.
# Sin Qt. Sin I/O de red. Solo lógica de negocio + persistencia JSON.

from __future__ import annotations

import logging
import threading
from typing import Optional

from domain.preset import PRESET_SLOT_MIN, PRESET_SLOT_MAX
from chairman_presets import (
    load_chairman_presets,
    save_chairman_presets,
    CHAIRMAN_GENERIC_PRESET,
)

logger = logging.getLogger(__name__)


class PresetService:
    """
    Gestiona el mapa nombre→número_de_slot VISCA para presets personales.

    Thread-safety: el lock protege solo lecturas/escrituras del dict en memoria.
    La I/O de disco se realiza fuera del lock para no bloquear hilos de worker.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._presets: dict[str, int] = load_chairman_presets()

    # ── Consulta ──────────────────────────────────────────────────────────

    def get_preset_for_name(self, name: str) -> int:
        """Devuelve el slot de preset para 'name', o el genérico si no existe."""
        with self._lock:
            return self._presets.get(name, CHAIRMAN_GENERIC_PRESET)

    def has_preset(self, name: str) -> bool:
        with self._lock:
            return name in self._presets

    def snapshot(self) -> dict[str, int]:
        """Copia inmutable del mapa actual (para display en UI)."""
        with self._lock:
            return dict(self._presets)

    # ── Mutación ──────────────────────────────────────────────────────────

    def assign_slot(self, name: str) -> tuple[Optional[int], bool]:
        """
        Reserva un slot en memoria. NO escribe en disco.

        Devuelve (slot, is_new).
          is_new=True  → slot recién asignado; llamar persist() si VISCA tiene éxito,
                         o release_slot(name) para rollback si falla.
          is_new=False → slot ya existía; no necesita persist() ni rollback.
          (None, False) → rango agotado.
        """
        with self._lock:
            if name in self._presets:
                return self._presets[name], False

            used = set(self._presets.values())
            for slot in range(PRESET_SLOT_MIN, PRESET_SLOT_MAX + 1):
                if slot not in used:
                    self._presets[name] = slot
                    return slot, True

        logger.error("PresetService: rango de slots agotado (>%d personas)",
                     PRESET_SLOT_MAX - PRESET_SLOT_MIN + 1)
        return None, False

    def persist(self) -> None:
        """Persiste el estado actual en disco. Llamar solo tras confirmar VISCA."""
        with self._lock:
            to_persist = dict(self._presets)
        save_chairman_presets(to_persist)

    def release_slot(self, name: str) -> None:
        """
        Elimina el slot de 'name' de memoria sin tocar el disco.
        Solo para rollback de assign_slot() cuando VISCA falla antes de persist().
        """
        with self._lock:
            self._presets.pop(name, None)

    def rename(self, old_name: str, new_name: str) -> None:
        """Migra el preset de old_name a new_name sin cambiar el número de slot."""
        to_persist: Optional[dict] = None

        with self._lock:
            if old_name in self._presets and new_name not in self._presets:
                self._presets[new_name] = self._presets.pop(old_name)
                to_persist = dict(self._presets)

        if to_persist is not None:
            save_chairman_presets(to_persist)
