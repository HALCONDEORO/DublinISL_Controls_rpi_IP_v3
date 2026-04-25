#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# schedule_config.py — Persistencia y consulta del calendario semanal de bypass de contraseña

from __future__ import annotations

from datetime import datetime
from json_io import load_json, save_json

from data_paths import SCHEDULE_FILE

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

DEFAULT_SCHEDULE: dict = {
    day: {"enabled": False, "start": "09:00", "end": "17:00"}
    for day in DAYS
}


def load_schedule() -> dict:
    """Leer schedule.json. Devuelve DEFAULT_SCHEDULE si no existe o hay error."""
    data = load_json(SCHEDULE_FILE)
    if not isinstance(data, dict):
        return {day: dict(DEFAULT_SCHEDULE[day]) for day in DAYS}
    try:
        result = {}
        for day in DAYS:
            entry = data.get(day, DEFAULT_SCHEDULE[day])
            result[day] = {
                "enabled": bool(entry.get("enabled", False)),
                "start":   str(entry.get("start", "09:00")),
                "end":     str(entry.get("end",   "17:00")),
            }
        return result
    except (TypeError, AttributeError):
        return {day: dict(DEFAULT_SCHEDULE[day]) for day in DAYS}


def save_schedule(data: dict) -> bool:
    """Guardar calendario en schedule.json. Devuelve True si tiene éxito."""
    return save_json(SCHEDULE_FILE, data)


def is_within_schedule() -> bool:
    """
    Comprobar si la hora actual está dentro de algún intervalo activo del calendario.
    Devuelve True → auto-login permitido.
    Devuelve False → pedir contraseña normalmente.
    """
    now = datetime.now()
    day_name = DAYS[now.weekday()]  # weekday(): 0=lunes … 6=domingo

    schedule = load_schedule()
    entry = schedule.get(day_name, {})

    if not entry.get("enabled", False):
        return False

    try:
        start_h, start_m = map(int, entry["start"].split(":"))
        end_h,   end_m   = map(int, entry["end"].split(":"))
    except (ValueError, KeyError):
        return False

    if not (0 <= start_h <= 23 and 0 <= start_m <= 59
            and 0 <= end_h <= 23 and 0 <= end_m <= 59):
        return False

    current_minutes = now.hour * 60 + now.minute
    start_minutes   = start_h  * 60 + start_m
    end_minutes     = end_h    * 60 + end_m

    if end_minutes <= start_minutes:
        # Horario nocturno que cruza la medianoche (ej. 22:00 → 06:00)
        return current_minutes >= start_minutes or current_minutes < end_minutes
    return start_minutes <= current_minutes < end_minutes
