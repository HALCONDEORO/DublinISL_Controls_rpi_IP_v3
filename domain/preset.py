#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# domain/preset.py — Modelos y constantes del dominio de presets

PRESET_SLOT_MIN = 10   # primer slot reservado para chairman personal
PRESET_SLOT_MAX = 89   # último slot seguro (0x59 hex)

# Presets de plataforma fija (no cambian por persona)
PRESET_CHAIRMAN_GENERIC = 1
PRESET_LEFT             = 2
PRESET_RIGHT            = 3

PLATFORM_PRESETS = frozenset({PRESET_CHAIRMAN_GENERIC, PRESET_LEFT, PRESET_RIGHT})
