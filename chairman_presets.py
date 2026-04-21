#!/usr/bin/env python3
# chairman_presets.py — Persistencia de presets de cámara por persona para Chairman
from __future__ import annotations
#
# Responsabilidad única: cargar y guardar el archivo chairman_presets.json,
# que mapea nombre de asistente → número de preset VISCA en Cam1 (Platform).
#
# ESTRUCTURA DEL ARCHIVO:
#   {
#     "Marco": 10,
#     "Carol": 11,
#     "Gary":  12
#   }
#
# MOTIVO DE ARCHIVO SEPARADO:
#   seat_names.json gestiona asignaciones de asientos (quién está sentado dónde).
#   Los presets de Chairman son datos de cámara, no de sala — separarlo evita
#   mezclar dos responsabilidades distintas en el mismo archivo y facilita
#   exportar/importar configuraciones de cámara independientemente.
#
# RANGO DE PRESETS RESERVADOS PARA CHAIRMAN:
#   Presets 1-3 están ocupados por Chairman/Left/Right genéricos.
#   Los presets personales se asignan desde CHAIRMAN_PRESET_START (10)
#   hacia arriba, uno por persona, hasta CHAIRMAN_PRESET_MAX (89).
#   MOTIVO del 10: deja margen para otros presets de sistema en 4-9.
#   MOTIVO del 89: límite antes del bloque reservado VISCA (0x5A en adelante
#   según algunas cámaras; 89 = 0x59 es el último seguro del rango directo).

import logging
from json_io import load_json, save_json

logger = logging.getLogger(__name__)

CHAIRMAN_PRESETS_FILE  = 'chairman_presets.json'
CHAIRMAN_PRESET_START  = 10   # primer número de preset disponible para personas
CHAIRMAN_PRESET_MAX    = 89   # último número de preset seguro (0x59 hex)
CHAIRMAN_GENERIC_PRESET = 1   # preset genérico si la persona no tiene uno asignado


def load_chairman_presets() -> dict[str, int]:
    """
    Carga el mapa nombre→número_de_preset desde chairman_presets.json.
    Devuelve dict vacío si el archivo no existe o está corrupto.
    """
    data = load_json(CHAIRMAN_PRESETS_FILE, default={})
    if not isinstance(data, dict):
        logger.warning("%s: formato inesperado — iniciando sin presets personales", CHAIRMAN_PRESETS_FILE)
        return {}
    return {
        name: int(preset)
        for name, preset in data.items()
        if isinstance(preset, int) and CHAIRMAN_PRESET_START <= preset <= CHAIRMAN_PRESET_MAX
    }


def save_chairman_presets(presets: dict[str, int]) -> None:
    """Persiste el mapa nombre→preset en chairman_presets.json."""
    if not save_json(CHAIRMAN_PRESETS_FILE, presets):
        logger.error("Error guardando %s", CHAIRMAN_PRESETS_FILE)


def next_available_preset(presets: dict[str, int]) -> int | None:
    """
    Devuelve el siguiente número de preset libre en el rango reservado.
    Devuelve None si el rango está agotado (más de 79 personas con preset).
    MOTIVO: asignar automáticamente evita que el operador tenga que
    conocer los números internos de preset VISCA.
    """
    used = set(presets.values())
    for n in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX + 1):
        if n not in used:
            return n
    return None  # rango agotado — situación muy improbable (79 personas)


def get_preset_for_name(presets: dict[str, int], name: str) -> int:
    """
    Devuelve el número de preset asociado a name, o el genérico si no existe.
    Centraliza la lógica de fallback para no repetirla en MainWindow y en
    ChairmanButton.
    """
    return presets.get(name, CHAIRMAN_GENERIC_PRESET)
