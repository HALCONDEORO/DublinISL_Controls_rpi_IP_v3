#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# atem_state.py — Estado explícito del switcher ATEM

from __future__ import annotations

from enum import Enum, auto


class ATEMState(Enum):
    NOT_CONFIGURED     = auto()   # IP vacía o archivo ATEMIP.txt ausente
    DEPENDENCY_MISSING = auto()   # PyATEMMax no instalado
    CONNECTING         = auto()   # intento de conexión en curso
    CONNECTED          = auto()   # conexión activa y funcionando
    DISCONNECTED       = auto()   # timeout o pérdida de conexión limpia
    ERROR              = auto()   # excepción inesperada durante operación
    RECONNECTING       = auto()   # reintento de conexión tras desconexión


ATEM_SUPERVISOR_TERMINAL_OK = frozenset({
    ATEMState.NOT_CONFIGURED,
    ATEMState.DEPENDENCY_MISSING,
    ATEMState.DISCONNECTED,
})


def is_atem_supervisor_healthy(
    *,
    is_running: bool,
    restart_pending: bool,
    state: ATEMState | None,
) -> bool:
    """Devuelve si el supervisor debe considerar sano el monitor ATEM."""
    if is_running or restart_pending:
        return True
    return state in ATEM_SUPERVISOR_TERMINAL_OK
