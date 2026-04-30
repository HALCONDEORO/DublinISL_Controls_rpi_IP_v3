#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# ptz/visca/parser.py — Parsers puros de respuestas VISCA
#
# Todas las funciones son puras: reciben bytes, devuelven el valor extraído o None.
# Sin efectos secundarios, sin red, sin Qt.

from __future__ import annotations

from typing import Optional

from .types import ZOOM_MAX


def zoom(data: bytes) -> Optional[int]:
    """
    Extrae el valor 0–0x4000 de una respuesta VISCA zoom inquiry.
    Formato esperado: y0 50 0p 0q 0r 0s FF
    """
    if len(data) >= 7 and data[1] == 0x50:
        return (
            (data[2] & 0xF) << 12
            | (data[3] & 0xF) << 8
            | (data[4] & 0xF) << 4
            | (data[5] & 0xF)
        )
    return None


def zoom_to_pct(raw: int) -> int:
    """Convierte valor VISCA 0–0x4000 a porcentaje 0–100."""
    return round(raw * 100 / ZOOM_MAX)


def ptz_position(data: bytes) -> Optional[tuple[int, int]]:
    """
    Extrae (pan, tilt) de una respuesta VISCA PTZ Position Inquiry.
    Formato: y0 58 0p 0q 0r 0s 0t 0u 0v 0w FF  (11 bytes mínimo)
    Los valores son enteros de 16 bits sin signo.
    """
    if len(data) >= 11 and data[1] == 0x58:
        pan  = (data[2] & 0xF) << 12 | (data[3] & 0xF) << 8 | (data[4] & 0xF) << 4 | (data[5] & 0xF)
        tilt = (data[6] & 0xF) << 12 | (data[7] & 0xF) << 8 | (data[8] & 0xF) << 4 | (data[9] & 0xF)
        return pan, tilt
    return None


def inquiry_frame(data: bytes, payload_len: int) -> Optional[bytes]:
    """
    Busca una trama VISCA Completion-with-data en el buffer recibido.

    Formato: 9x 50 [payload_len bytes] FF
    Escanea en lugar de asumir offset fijo porque algunas cámaras
    (PTZOptics, Datavideo…) envían ACK + Completion en el mismo paquete TCP:
    "9x 4y FF 9x 50 ... FF". Con offset fijo se leería el byte equivocado.
    """
    frame_len = payload_len + 3  # 9x + 50 + [payload] + FF
    for i in range(len(data) - frame_len + 1):
        if (
            (data[i] & 0xF0) == 0x90
            and data[i + 1] == 0x50
            and data[i + frame_len - 1] == 0xFF
        ):
            return data[i: i + frame_len]
    return None


def ae_mode(frame: bytes) -> str:
    """
    Extrae el modo AE de un frame de respuesta CAM_AE_ModeInq.
    Devuelve 'manual', 'bright' o 'auto' (fallback seguro).
    """
    pp = frame[2]
    if pp == 0x03:
        return 'manual'
    if pp == 0x0D:
        return 'bright'
    return 'auto'


def exp_comp_level(frame: bytes) -> int:
    """
    Extrae el nivel de compensación de exposición de un frame CAM_ExpCompPosInq.
    El valor VISCA (0–14) se mapea a -7..+7.
    """
    val = (
        ((frame[2] & 0x0F) << 12)
        | ((frame[3] & 0x0F) <<  8)
        | ((frame[4] & 0x0F) <<  4)
        |  (frame[5] & 0x0F)
    )
    return max(-7, min(7, val - 7))
