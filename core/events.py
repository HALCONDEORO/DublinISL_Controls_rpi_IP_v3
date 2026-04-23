#!/usr/bin/env python3
# core/events.py — EventBus y tipos de evento
#
# Sin Qt. Sin I/O. El bus es síncrono: los handlers se invocan en el hilo
# que llama a emit(). En Qt, las conexiones de señales manejan el threading;
# aquí solo se garantiza que no haya estado global mutable fuera de SystemState.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List


class EventType(Enum):
    # ── Entrada de asientos ──────────────────────────────────
    SEAT_SELECTED       = auto()   # payload: name, camera, seat_number

    # ── Movimiento de cámara ─────────────────────────────────
    CAMERA_MOVE         = auto()   # payload: camera, pan_speed, tilt_speed
    CAMERA_STOP         = auto()   # payload: camera
    CAMERA_ZOOM         = auto()   # payload: camera, speed

    # ── Presets ──────────────────────────────────────────────
    CHAIRMAN_ASSIGNED   = auto()   # payload: name
    PRESET_SAVE_REQUESTED = auto() # payload: camera, name
    PRESET_SAVED        = auto()   # payload: camera, name, slot

    # ── Sesión ───────────────────────────────────────────────
    SESSION_START       = auto()
    SESSION_END         = auto()

    # ── Conexión ─────────────────────────────────────────────
    CONNECTION_CHANGED  = auto()   # payload: camera, connected


@dataclass
class Event:
    type: EventType
    payload: Dict[str, Any]


class EventBus:
    """
    Bus de eventos síncrono.

    Todos los handlers se llaman en el hilo del emisor.
    Para cruzar al hilo Qt desde workers, usa QTimer.singleShot(0, fn) en el handler.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: EventType,
                  handler: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType,
                    handler: Callable[[Event], None]) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event_type: EventType, **payload: Any) -> None:
        event = Event(type=event_type, payload=payload)
        for handler in list(self._subscribers.get(event_type, [])):
            handler(event)
