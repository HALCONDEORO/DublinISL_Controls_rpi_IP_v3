#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
"""
Tests del orquestador central core.controller.
"""

from core.controller import Controller
from core.events import AsyncEventBus, EventType
from core.state import SystemState


def _drain(bus: AsyncEventBus) -> None:
    bus._queue.join()


class _CameraSvc:
    def __init__(self):
        self.calls = []
        self.recall_ok = True
        self.save_ok = True

    def recall_preset(self, camera, preset):
        self.calls.append(("recall_preset", camera, preset))
        return self.recall_ok

    def save_preset(self, camera, slot):
        self.calls.append(("save_preset", camera, slot))
        return self.save_ok

    def invalidate_zoom(self, camera):
        self.calls.append(("invalidate_zoom", camera))

    def move(self, camera, pan, tilt):
        self.calls.append(("move", camera, pan, tilt))

    def stop(self, camera):
        self.calls.append(("stop", camera))

    def zoom(self, camera, speed):
        self.calls.append(("zoom", camera, speed))


class _PresetSvc:
    def __init__(self):
        self.map = {"Alice": 10}
        self.assign_result = (12, True)
        self.calls = []

    def get_preset_for_name(self, name):
        self.calls.append(("get_preset_for_name", name))
        return self.map.get(name, 1)

    def assign_slot(self, name):
        self.calls.append(("assign_slot", name))
        slot, is_new = self.assign_result
        if slot is not None and is_new:
            self.map[name] = slot
        return self.assign_result

    def persist(self):
        self.calls.append(("persist",))

    def release_slot(self, name):
        self.calls.append(("release_slot", name))
        self.map.pop(name, None)


class _SessionSvc:
    def __init__(self):
        self.calls = []

    def set_chairman(self, name):
        self.calls.append(("set_chairman", name))

    def start(self):
        self.calls.append(("start",))

    def end(self):
        self.calls.append(("end",))


class _Harness:
    def __init__(self):
        self.state = SystemState()
        self.bus = AsyncEventBus()
        self.camera = _CameraSvc()
        self.presets = _PresetSvc()
        self.session = _SessionSvc()
        self.saved_events = []
        self.bus.subscribe(EventType.PRESET_SAVED, lambda event: self.saved_events.append(event.payload))
        self.controller = Controller(self.state, self.bus, self.camera, self.presets, self.session)

    def __enter__(self):
        self.bus.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.bus.stop()

    def emit(self, event_type, **payload):
        self.bus.emit(event_type, **payload)
        _drain(self.bus)


class TestControllerSeatSelection:

    def test_named_seat_uses_personal_preset_and_invalidates_zoom_on_success(self):
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="Alice", camera=2, seat_number=7)

        assert h.camera.calls == [("recall_preset", 2, 10), ("invalidate_zoom", 2)]
        assert h.state.cam2.active_preset == 10

    def test_unnamed_seat_uses_seat_number_as_preset(self):
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, seat_number=7)

        assert h.camera.calls == [("recall_preset", 1, 7), ("invalidate_zoom", 1)]
        assert h.state.cam1.active_preset == 7
    def test_seat_selection_defaults_to_active_camera_when_payload_omits_camera(self):
        with _Harness() as h:
            h.state.active_camera = 2
            h.emit(EventType.SEAT_SELECTED, name="", seat_number=8)

        assert h.camera.calls == [("recall_preset", 2, 8), ("invalidate_zoom", 2)]
        assert h.state.cam2.active_preset == 8

    def test_invalid_seat_zero_does_not_call_camera(self):
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, seat_number=0)

        assert h.camera.calls == []
        assert h.state.cam1.active_preset is None

    def test_failed_recall_does_not_update_active_preset_or_invalidate_zoom(self):
        with _Harness() as h:
            h.camera.recall_ok = False
            h.emit(EventType.SEAT_SELECTED, name="Alice", camera=1, seat_number=7)

        assert h.camera.calls == [("recall_preset", 1, 10)]
        assert h.state.cam1.active_preset is None


class TestControllerCameraCommands:

    def test_camera_move_delegates_and_updates_state(self):
        with _Harness() as h:
            h.emit(EventType.CAMERA_MOVE, camera=2, pan_speed=-3, tilt_speed=4)

        assert h.camera.calls == [("move", 2, -3, 4)]
        assert h.state.cam2.pan_speed == -3
        assert h.state.cam2.tilt_speed == 4

    def test_camera_stop_delegates_and_resets_motion_state(self):
        with _Harness() as h:
            h.state.cam1.pan_speed = 5
            h.state.cam1.tilt_speed = -2
            h.emit(EventType.CAMERA_STOP, camera=1)

        assert h.camera.calls == [("stop", 1)]
        assert h.state.cam1.pan_speed == 0
        assert h.state.cam1.tilt_speed == 0

    def test_camera_zoom_delegates_without_state_mutation(self):
        with _Harness() as h:
            h.emit(EventType.CAMERA_ZOOM, camera=1, speed=-4)

        assert h.camera.calls == [("zoom", 1, -4)]


class TestControllerChairmanAndPresets:

    def test_chairman_assigned_updates_session_and_recalls_cam1(self):
        with _Harness() as h:
            h.emit(EventType.CHAIRMAN_ASSIGNED, name="Alice")

        assert h.session.calls == [("set_chairman", "Alice")]
        assert h.state.session.chairman_name == "Alice"
        assert h.camera.calls == [("recall_preset", 1, 10), ("invalidate_zoom", 1)]
        assert h.state.cam1.active_preset == 10
    def test_chairman_recall_failure_keeps_assignment_but_does_not_update_camera_state(self):
        with _Harness() as h:
            h.camera.recall_ok = False
            h.emit(EventType.CHAIRMAN_ASSIGNED, name="Alice")

        assert h.session.calls == [("set_chairman", "Alice")]
        assert h.state.session.chairman_name == "Alice"
        assert h.camera.calls == [("recall_preset", 1, 10)]
        assert h.state.cam1.active_preset is None

    def test_preset_save_new_slot_persists_and_emits_saved_event(self):
        with _Harness() as h:
            h.presets.assign_result = (12, True)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=2, name="Bob")

        assert h.camera.calls == [("save_preset", 2, 12)]
        assert h.presets.calls == [("assign_slot", "Bob"), ("persist",)]
        assert h.saved_events == [{"camera": 2, "name": "Bob", "slot": 12}]

    def test_saved_new_preset_can_be_recalled_by_later_seat_selection(self):
        with _Harness() as h:
            h.presets.assign_result = (12, True)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=2, name="Bob")
            h.emit(EventType.SEAT_SELECTED, name="Bob", camera=2, seat_number=4)

        assert h.camera.calls == [
            ("save_preset", 2, 12),
            ("recall_preset", 2, 12),
            ("invalidate_zoom", 2),
        ]
        assert h.presets.calls == [
            ("assign_slot", "Bob"),
            ("persist",),
            ("get_preset_for_name", "Bob"),
        ]
        assert h.state.cam2.active_preset == 12
        assert h.saved_events == [{"camera": 2, "name": "Bob", "slot": 12}]
    def test_preset_save_existing_slot_does_not_persist_again(self):
        with _Harness() as h:
            h.presets.assign_result = (10, False)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="Alice")

        assert h.camera.calls == [("save_preset", 1, 10)]
        assert h.presets.calls == [("assign_slot", "Alice")]
        assert h.saved_events == [{"camera": 1, "name": "Alice", "slot": 10}]

    def test_preset_save_failure_rolls_back_new_slot_and_emits_nothing(self):
        with _Harness() as h:
            h.camera.save_ok = False
            h.presets.assign_result = (12, True)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="Bob")

        assert h.camera.calls == [("save_preset", 1, 12)]
        assert h.presets.calls == [("assign_slot", "Bob"), ("release_slot", "Bob")]
        assert h.saved_events == []
    def test_preset_save_failure_for_existing_slot_does_not_release_slot(self):
        with _Harness() as h:
            h.camera.save_ok = False
            h.presets.assign_result = (10, False)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="Alice")

        assert h.camera.calls == [("save_preset", 1, 10)]
        assert h.presets.calls == [("assign_slot", "Alice")]
        assert h.saved_events == []

    def test_preset_save_range_exhausted_does_not_call_camera(self):
        with _Harness() as h:
            h.presets.assign_result = (None, False)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="Bob")

        assert h.camera.calls == []
        assert h.saved_events == []


class TestControllerSession:

    def test_session_start_updates_state_and_starts_service(self):
        with _Harness() as h:
            h.emit(EventType.SESSION_START)

        assert h.state.session.active is True
        assert h.session.calls == [("start",)]

    def test_session_end_updates_state_and_ends_service(self):
        with _Harness() as h:
            h.state.session.active = True
            h.emit(EventType.SESSION_END)

        assert h.state.session.active is False
        assert h.session.calls == [("end",)]
