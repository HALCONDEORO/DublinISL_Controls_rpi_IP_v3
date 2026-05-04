#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# atem_dispatcher.py — Capa de despacho entre ATEMMonitor y acciones de cámara
#
# El monitor ATEM emite eventos limpios (program_changed, state_changed).
# Este dispatcher decide si esos eventos producen acciones de cámara,
# aplicando todas las capas de seguridad antes de emitir action_triggered.
#
# CAPAS DE SEGURIDAD (en orden de evaluación):
#   1. armed      — si False, solo monitoriza (no emite acciones)
#   2. session    — si sesión inactiva, ignora
#   3. cooldown   — N segundos de espera tras control manual
#   4. reconnect  — pausa hasta confirmación explícita tras reconexión
#   5. log_only   — registra la acción pero no la emite (modo ensayo)
#
# MAPEO DE ENTRADAS:
#   Cargado desde atem_mapping.json; formato {"<from>-><to>": "<action>"}.
#   También acepta {"<input_id>": "<action>"} para actuar al entrar en un input.
#   Acciones reconocidas: "none", "comments_home", "platform_home".
#   Transiciones/entradas sin mapeo → "none".

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from atem_state import ATEMState

logger = logging.getLogger(__name__)

_MAPPING_FILE = Path("atem_mapping.json")
_DEFAULT_MAPPING: dict[str, str] = {"3->2": "comments_home"}
_MANUAL_COOLDOWN_SECS = 30

KNOWN_ACTIONS = frozenset({"none", "comments_home", "platform_home"})


def _is_valid_mapping_key(key: str) -> bool:
    if key.isdigit():
        return True
    parts = key.split("->")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


def _load_mapping() -> dict[str, str]:
    if not _MAPPING_FILE.exists():
        return dict(_DEFAULT_MAPPING)
    try:
        raw = json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("expected JSON object")
        result: dict[str, str] = {}
        for k, v in raw.items():
            key = str(k)
            if not _is_valid_mapping_key(key):
                logger.warning(
                    "[ATEM] mapping: clave inválida %r (debe ser dígito o transición A->B) — omitida",
                    k,
                )
                continue
            if v not in KNOWN_ACTIONS:
                logger.warning("[ATEM] mapping: acción desconocida %r para input %s — usando 'none'", v, k)
                v = "none"
            result[key] = v
        return result
    except Exception as exc:
        logger.warning("[ATEM] error leyendo mapping: %s — usando valores por defecto", exc)
        return dict(_DEFAULT_MAPPING)


def _save_mapping(mapping: dict[str, str]) -> None:
    try:
        _MAPPING_FILE.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("[ATEM] no se pudo guardar mapping: %s", exc)


class ATEMDispatcher(QObject):
    """
    Recibe eventos de programa del ATEMMonitor y decide si disparar acciones de cámara.

    Nunca mueve cámaras directamente; emite action_triggered(str) para que
    la capa superior (MainWindow) ejecute la acción correspondiente.
    """

    action_triggered = pyqtSignal(str)

    def __init__(self, session_provider, parent=None):
        """
        session_provider — callable sin argumentos que devuelve bool:
                           True si hay una sesión activa.
        """
        super().__init__(parent)
        self._session_provider = session_provider
        self._mapping = _load_mapping()
        self._armed = False
        self._log_only = False
        self._manual_cooldown_until = 0.0
        self._reconnect_guard = False
        self._last_input: int | None = None

    # ── Propiedades de estado ─────────────────────────────────────────────────

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def log_only(self) -> bool:
        return self._log_only

    @property
    def reconnect_guard(self) -> bool:
        return self._reconnect_guard

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    # ── API pública ───────────────────────────────────────────────────────────

    def set_armed(self, armed: bool) -> None:
        if self._armed == armed:
            return
        self._armed = armed
        logger.info("[ATEM] Automatización %s", "ARMADA" if armed else "DESARMADA")

    def set_log_only(self, log_only: bool) -> None:
        self._log_only = log_only
        logger.info("[ATEM] Modo solo-registro %s", "ACTIVADO" if log_only else "DESACTIVADO")

    def update_mapping(self, mapping: dict[str, str]) -> None:
        """Actualiza el mapeo en memoria y lo persiste a disco."""
        self._mapping = dict(mapping)
        _save_mapping(self._mapping)
        logger.info("[ATEM] Mapeo actualizado: %s", self._mapping)

    def notify_manual_control(self) -> None:
        """Registra un control manual; suprime ATEM durante _MANUAL_COOLDOWN_SECS."""
        self._manual_cooldown_until = time.monotonic() + _MANUAL_COOLDOWN_SECS

    def on_atem_state_changed(self, state: ATEMState) -> None:
        """Activa el reconnect guard cuando el ATEM se reconecta."""
        if state == ATEMState.CONNECTED and self._last_input is not None:
            self._reconnect_guard = True
            logger.info("[ATEM] Reconnect guard activado — confirmar para reanudar automatización")

    def mark_reconnecting(self) -> None:
        """Activa el guard al reiniciar el monitor si la automatización está armada."""
        if self._armed:
            self._reconnect_guard = True
            logger.info("[ATEM] Reconnect guard activado por reinicio del monitor")

    def clear_reconnect_guard(self) -> None:
        self._reconnect_guard = False
        logger.info("[ATEM] Reconnect guard desactivado")

    def reset_input_tracking(self) -> None:
        """Limpia el input previo (llamar tras reconexión para no perder el primer evento)."""
        self._last_input = None

    # ── Receptor de eventos del monitor ──────────────────────────────────────

    def on_program_changed(self, input_id: int) -> None:
        """Recibe el input de programa actual y decide la acción."""
        if input_id == self._last_input:
            return  # deduplicación: mismo input repetido → ignorar
        prev_input = self._last_input
        self._last_input = input_id

        action = self._action_for(prev_input, input_id)
        reason = self._blocked_reason()

        if reason:
            logger.info("[ATEM] Input %d → %s | Bloqueado: %s", input_id, action, reason)
            return

        if action == "none":
            logger.info("[ATEM] Input %d → sin acción (mapeado a none)", input_id)
            return

        if self._log_only:
            logger.info("[ATEM] Input %d → %s (solo-registro — no ejecutado)", input_id, action)
            return

        logger.info("[ATEM] Input %d → %s", input_id, action)
        self.action_triggered.emit(action)

    # ── Dry-run ───────────────────────────────────────────────────────────────

    def dry_run(self, input_id: int) -> str:
        """
        Simula qué pasaría con input_id sin mover cámaras.
        Devuelve una cadena descriptiva del resultado esperado.
        """
        action = self._action_for(self._last_input, input_id)
        reason = self._blocked_reason()
        if reason:
            return f"Would trigger: {action} | Blocked because: {reason}"
        if action == "none":
            return f"Input {input_id}: no action (mapped to none)"
        if self._log_only:
            return f"Would trigger: {action} | Mode: log-only (not executed)"
        return f"Would trigger: {action}"

    # ── Internos ──────────────────────────────────────────────────────────────

    def _action_for(self, prev_input: int | None, input_id: int) -> str:
        if prev_input is not None:
            transition_key = f"{prev_input}->{input_id}"
            if transition_key in self._mapping:
                return self._mapping[transition_key]
        return self._mapping.get(str(input_id), "none")

    def _blocked_reason(self) -> str:
        if not self._armed:
            return "automation disarmed"
        if not self._session_provider():
            return "session inactive"
        if time.monotonic() < self._manual_cooldown_until:
            return "manual override cooldown"
        if self._reconnect_guard:
            return "reconnect guard active"
        return ""
