#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribucion, modificacion o uso sin autorizacion escrita del autor.
"""
Tests de servicios de aplicacion: presets, camaras y ciclo de sesion.
"""

from types import SimpleNamespace

from application.session_service import SessionService
from domain.preset import PRESET_SLOT_MIN, PRESET_SLOT_MAX


class TestPresetService:

    def _service(self, monkeypatch, initial=None, saved=None):
        import application.preset_service as ps

        if initial is None:
            initial = {}
        if saved is None:
            saved = []

        monkeypatch.setattr(ps, "load_chairman_presets", lambda: dict(initial))
        monkeypatch.setattr(ps, "save_chairman_presets", lambda data: saved.append(dict(data)) or True)
        return ps.PresetService()

    def test_assign_slot_starts_at_minimum_and_marks_new(self, monkeypatch):
        svc = self._service(monkeypatch)

        assert svc.assign_slot("Alice") == (PRESET_SLOT_MIN, True)
        assert svc.snapshot() == {"Alice": PRESET_SLOT_MIN}

    def test_assign_slot_skips_used_slots(self, monkeypatch):
        svc = self._service(monkeypatch, {"Alice": PRESET_SLOT_MIN})

        assert svc.assign_slot("Bob") == (PRESET_SLOT_MIN + 1, True)

    def test_assign_existing_slot_is_not_new(self, monkeypatch):
        svc = self._service(monkeypatch, {"Alice": 12})

        assert svc.assign_slot("Alice") == (12, False)

    def test_assign_slot_returns_none_when_range_is_full(self, monkeypatch):
        full = {f"Person{slot}": slot for slot in range(PRESET_SLOT_MIN, PRESET_SLOT_MAX + 1)}
        svc = self._service(monkeypatch, full)

        assert svc.assign_slot("Extra") == (None, False)

    def test_snapshot_is_a_copy(self, monkeypatch):
        svc = self._service(monkeypatch, {"Alice": 10})

        snap = svc.snapshot()
        snap["Bob"] = 11

        assert svc.snapshot() == {"Alice": 10}

    def test_persist_saves_current_snapshot(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"Alice": 10}, saved)
        svc.assign_slot("Bob")

        svc.persist()

        assert saved == [{"Alice": 10, "Bob": 11}]

    def test_release_slot_is_idempotent(self, monkeypatch):
        svc = self._service(monkeypatch, {"Alice": 10})

        svc.release_slot("Alice")
        svc.release_slot("Alice")

        assert svc.snapshot() == {}

    def test_rename_migrates_and_persists_when_target_is_free(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"Alice": 10}, saved)

        svc.rename("Alice", "Alicia")

        assert svc.snapshot() == {"Alicia": 10}
        assert saved == [{"Alicia": 10}]

    def test_rename_does_nothing_when_target_exists(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"Alice": 10, "Bob": 11}, saved)

        svc.rename("Alice", "Bob")

        assert svc.snapshot() == {"Alice": 10, "Bob": 11}
        assert saved == []
    def test_get_preset_for_name_falls_back_to_generic(self, monkeypatch):
        svc = self._service(monkeypatch, {"Alice": 10})

        assert svc.get_preset_for_name("Alice") == 10
        assert svc.get_preset_for_name("Unknown") == 1

    def test_has_preset_tracks_current_state(self, monkeypatch):
        svc = self._service(monkeypatch, {"Alice": 10})

        assert svc.has_preset("Alice") is True
        assert svc.has_preset("Bob") is False

    def test_rename_missing_source_does_not_persist(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"Alice": 10}, saved)

        svc.rename("Missing", "Bob")

        assert svc.snapshot() == {"Alice": 10}
        assert saved == []


class _Worker:
    def __init__(self):
        self.sent = []
        self.priority = []

    def send(self, cmd):
        self.sent.append(cmd)
        return True

    def send_priority(self, cmd):
        self.priority.append(cmd)
        return True


class _Manager:
    def __init__(self):
        self.workers = {}
        self.invalidated = []

    def worker(self, ip):
        self.workers.setdefault(ip, _Worker())
        return self.workers[ip]

    def invalidate_zoom(self, ip):
        self.invalidated.append(ip)


class TestCameraService:

    def _service(self, monkeypatch):
        import application.camera_service as cs

        monkeypatch.setattr(cs, "CAM1", SimpleNamespace(ip="10.0.0.11", cam_id="81"))
        monkeypatch.setattr(cs, "CAM2", SimpleNamespace(ip="10.0.0.12", cam_id="82"))
        monkeypatch.setattr(cs, "PRESET_MAP", {10: "0A", 11: "0B"})
        mgr = _Manager()
        return cs.CameraService(mgr), mgr

    def test_recall_and_save_preset_send_expected_confirmed_hex(self, monkeypatch):
        svc, _mgr = self._service(monkeypatch)
        calls = []
        monkeypatch.setattr(svc, "_send_confirmed", lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True)

        assert svc.recall_preset(1, 10) is True
        assert svc.save_preset(2, 11) is True

        assert calls == [
            ("10.0.0.11", "81", "01043f020Aff"),
            ("10.0.0.12", "82", "01043f010Bff"),
        ]

    def test_invalid_preset_slot_does_not_send(self, monkeypatch):
        svc, _mgr = self._service(monkeypatch)
        calls = []
        monkeypatch.setattr(svc, "_send_confirmed", lambda *args: calls.append(args) or True)

        assert svc.recall_preset(1, 99) is False
        assert svc.save_preset(1, 99) is False
        assert calls == []

    def test_power_and_home_commands_use_selected_camera(self, monkeypatch):
        svc, _mgr = self._service(monkeypatch)
        calls = []
        monkeypatch.setattr(svc, "_send_confirmed", lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True)

        svc.power_on(1)
        svc.power_standby(2)
        svc.home(1)

        assert calls == [
            ("10.0.0.11", "81", "01040002FF"),
            ("10.0.0.12", "82", "01040003FF"),
            ("10.0.0.11", "81", "010604FF"),
        ]

    def test_move_clamps_speeds_and_encodes_directions(self, monkeypatch):
        svc, mgr = self._service(monkeypatch)
        svc.pan_cap = 4
        svc.tilt_cap = 3

        svc.move(1, pan_speed=-99, tilt_speed=99)

        cmd = mgr.workers["10.0.0.11"].sent[0]
        assert cmd.camera == 1
        assert cmd.payload.hex().upper() == "8101060104030101FF"

    def test_stop_uses_priority_queue(self, monkeypatch):
        svc, mgr = self._service(monkeypatch)

        svc.stop(2)

        worker = mgr.workers["10.0.0.12"]
        assert worker.sent == []
        assert worker.priority[0].payload.hex().upper() == "8201060100000303FF"

    def test_zoom_encodes_tele_wide_and_stop(self, monkeypatch):
        svc, mgr = self._service(monkeypatch)
        svc.zoom_drive_cap = 5

        svc.zoom(1, 99)
        svc.zoom(1, -99)
        svc.zoom(1, 0)

        payloads = [cmd.payload.hex().upper() for cmd in mgr.workers["10.0.0.11"].sent]
        assert payloads == ["8101040725FF", "8101040735FF", "8101040700FF"]

    def test_invalidate_zoom_delegates_to_manager_ip(self, monkeypatch):
        svc, mgr = self._service(monkeypatch)

        svc.invalidate_zoom(2)

        assert mgr.invalidated == ["10.0.0.12"]


    def test_send_confirmed_sends_full_frame_and_reads_ack(self, monkeypatch):
        import application.camera_service as cs

        svc, _mgr = self._service(monkeypatch)
        socket_calls = []

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                socket_calls.append(("close",))
                return False

            def settimeout(self, timeout):
                socket_calls.append(("settimeout", timeout))

            def connect(self, address):
                socket_calls.append(("connect", address))

            def send(self, payload):
                socket_calls.append(("send", payload.hex().upper()))

            def recv(self, size):
                socket_calls.append(("recv", size))
                return b"\x90\x41\xff"

        monkeypatch.setattr(cs.socket, "socket", lambda *_args, **_kwargs: FakeSocket())
        monkeypatch.setattr(cs, "VISCA_PORT", 5678)
        monkeypatch.setattr(cs, "SOCKET_TIMEOUT", 0.5)

        assert svc._send_confirmed("10.0.0.11", "81", "01040002FF") is True
        assert socket_calls == [
            ("settimeout", 0.5),
            ("connect", ("10.0.0.11", 5678)),
            ("send", "8101040002FF"),
            ("recv", 64),
            ("close",),
        ]
    def test_send_confirmed_returns_false_on_invalid_hex(self, monkeypatch):
        svc, _mgr = self._service(monkeypatch)

        assert svc._send_confirmed("127.0.0.1", "not-hex", "01040002FF") is False


class _Camera:
    def __init__(self):
        self.calls = []

    def power_on(self, camera):
        self.calls.append(("power_on", camera))
        return True

    def power_standby(self, camera):
        self.calls.append(("power_standby", camera))
        return True

    def home(self, camera):
        self.calls.append(("home", camera))
        return True


class TestSessionService:

    def test_start_powers_both_cameras_and_marks_active(self):
        camera = _Camera()
        svc = SessionService(camera)

        svc.start()

        assert svc.active is True
        assert camera.calls == [("power_on", 1), ("power_on", 2)]

    def test_home_both_sends_home_to_both_cameras(self):
        camera = _Camera()
        svc = SessionService(camera)

        svc.home_both()

        assert camera.calls == [("home", 1), ("home", 2)]

    def test_end_standbys_both_cameras_and_clears_state(self):
        camera = _Camera()
        svc = SessionService(camera)
        svc.set_chairman("Alice")
        svc.start()
        camera.calls.clear()

        svc.end()

        assert svc.active is False
        assert svc._chairman is None
        assert camera.calls == [("power_standby", 1), ("power_standby", 2)]
