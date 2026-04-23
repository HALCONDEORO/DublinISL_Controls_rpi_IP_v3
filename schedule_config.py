#!/usr/bin/env python3
# schedule_config.py — Persistencia y consulta del calendario semanal de bypass de contraseña

from __future__ import annotations

import json
import os
from datetime import datetime

from data_paths import SCHEDULE_FILE

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

DEFAULT_SCHEDULE: dict = {
    day: {"enabled": False, "start": "09:00", "end": "17:00"}
    for day in DAYS
}


def load_schedule() -> dict:
    """Leer schedule.json. Devuelve DEFAULT_SCHEDULE si no existe o hay error."""
    try:
        if not SCHEDULE_FILE.exists():
            return {day: dict(DEFAULT_SCHEDULE[day]) for day in DAYS}
        data = json.loads(SCHEDULE_FILE.read_text(encoding='utf-8'))
        # Asegurar que todos los días existen con valores válidos
        result = {}
        for day in DAYS:
            entry = data.get(day, DEFAULT_SCHEDULE[day])
            result[day] = {
                "enabled": bool(entry.get("enabled", False)),
                "start":   str(entry.get("start", "09:00")),
                "end":     str(entry.get("end",   "17:00")),
            }
        return result
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        return {day: dict(DEFAULT_SCHEDULE[day]) for day in DAYS}


def save_schedule(data: dict) -> bool:
    """Guardar calendario en schedule.json (escritura atómica). Devuelve True si tiene éxito."""
    tmp = SCHEDULE_FILE.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, SCHEDULE_FILE)
        return True
    except OSError:
        tmp.unlink(missing_ok=True)
        return False


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

    current_minutes = now.hour * 60 + now.minute
    start_minutes   = start_h  * 60 + start_m
    end_minutes     = end_h    * 60 + end_m

    return start_minutes <= current_minutes < end_minutes
