#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribucion, modificacion o uso sin autorizacion escrita del autor.
"""
Tests de adaptadores de entrada: joystick y botones de asiento.
"""

from adapters.input.joystick_adapter import JoystickAdapter
from adapters.input.seat_adapter import SeatAdapter
from core.events import EventType


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, event_type, **payload):
        self.events.append((event_type, payload))


class TestJoystickAdapter:

    def test_handlers_expose_expected_direction_names_only(self):
        adapter = JoystickAdapter(_Bus(), lambda: 1)

        assert set(adapter.handlers()) == {
            "up", "down", "left", "right",
            "upleft", "upright", "downleft", "downright",
        }

    def test_direction_handlers_emit_signed_camera_move_events(self):
        bus = _Bus()
        adapter = JoystickAdapter(bus, lambda: 2)
        handlers = adapter.handlers()

        handlers["up"](5, 6)
        handlers["down"](5, 6)
        handlers["left"](5, 6)
        handlers["right"](5, 6)
        handlers["upleft"](5, 6)
        handlers["upright"](5, 6)
        handlers["downleft"](5, 6)
        handlers["downright"](5, 6)

        payloads = [payload for event_type, payload in bus.events]
        assert [event_type for event_type, _payload in bus.events] == [EventType.CAMERA_MOVE] * 8
        assert payloads == [
            {"camera": 2, "pan_speed": 0, "tilt_speed": 6},
            {"camera": 2, "pan_speed": 0, "tilt_speed": -6},
            {"camera": 2, "pan_speed": -5, "tilt_speed": 0},
            {"camera": 2, "pan_speed": 5, "tilt_speed": 0},
            {"camera": 2, "pan_speed": -5, "tilt_speed": 6},
            {"camera": 2, "pan_speed": 5, "tilt_speed": 6},
            {"camera": 2, "pan_speed": -5, "tilt_speed": -6},
            {"camera": 2, "pan_speed": 5, "tilt_speed": -6},
        ]

    def test_stop_uses_current_active_camera(self):
        bus = _Bus()
        current = {"camera": 1}
        adapter = JoystickAdapter(bus, lambda: current["camera"])

        current["camera"] = 2
        adapter.stop()

        assert bus.events == [(EventType.CAMERA_STOP, {"camera": 2})]


class TestSeatAdapter:

    def test_seat_press_emits_name_camera_and_seat_number(self):
        bus = _Bus()
        adapter = SeatAdapter(bus, lambda: 2, lambda seat: {7: "Alice"}.get(seat))

        adapter.on_seat_pressed(7)

        assert bus.events == [
            (
                EventType.SEAT_SELECTED,
                {"name": "Alice", "camera": 2, "seat_number": 7},
            )
        ]

    def test_seat_without_name_emits_empty_string(self):
        bus = _Bus()
        adapter = SeatAdapter(bus, lambda: 1, lambda _seat: None)

        adapter.on_seat_pressed(3)

        assert bus.events == [
            (
                EventType.SEAT_SELECTED,
                {"name": "", "camera": 1, "seat_number": 3},
            )
        ]
