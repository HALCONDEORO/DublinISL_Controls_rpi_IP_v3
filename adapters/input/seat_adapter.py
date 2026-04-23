#!/usr/bin/env python3
# adapters/input/seat_adapter.py — Traduce presión de botón de asiento al EventBus

from __future__ import annotations

from core.events import EventBus, EventType


class SeatAdapter:
    """
    Conecta el click de un GoButton con el EventBus.

    Uso:
        adapter = SeatAdapter(bus, active_camera_fn, seat_names_fn)
        btn.clicked.connect(lambda: adapter.on_seat_pressed(seat_number))
    """

    def __init__(self, bus: EventBus, active_camera_fn, seat_name_fn) -> None:
        self._bus = bus
        self._get_active_camera = active_camera_fn
        self._get_seat_name = seat_name_fn

    def on_seat_pressed(self, seat_number: int) -> None:
        name = self._get_seat_name(seat_number)
        self._bus.emit(
            EventType.SEAT_SELECTED,
            name=name or "",
            camera=self._get_active_camera(),
            seat_number=seat_number,
        )
