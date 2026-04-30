#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# tests/test_visca_protocol_dispatch.py — Tests de ViscaProtocol: dispatch, routing y callbacks
#
# Verifica:
#   - Bytes exactos de cada comando despachado al worker correcto
#   - Routing de presets: 1-3 → CAM1, 4+ → CAM2
#   - Flag priority=True en Stop()
#   - Transiciones de estado en BacklightToggle, Focus, BrightnessUp/Down
#   - Modo auto: dos comandos encadenados (exp_comp_on → exp_comp_up)
#   - _dispatch con camera key inválida: descarta el comando
#   - go_to_preset: ningún modo activo → no dispatch
#   - _save_preset: confirm=False → no dispatch; confirm=True → dispatch

from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ─── Stubs mínimos ────────────────────────────────────────────────────────────

_pyqt5     = types.ModuleType("PyQt5")
_qtcore    = types.ModuleType("PyQt5.QtCore")
_qtwidgets = types.ModuleType("PyQt5.QtWidgets")
_qtcore.QObject    = object
_qtcore.pyqtSignal = lambda *a, **kw: None
_qtcore.QTimer     = MagicMock()
_qtwidgets.QMessageBox = MagicMock()
_pyqt5.QtCore    = _qtcore
_pyqt5.QtWidgets = _qtwidgets
sys.modules.setdefault("PyQt5",           _pyqt5)
sys.modules.setdefault("PyQt5.QtCore",    _qtcore)
sys.modules.setdefault("PyQt5.QtWidgets", _qtwidgets)

_sm = types.ModuleType("secret_manager")
_sm.decrypt_password = lambda: "test"
sys.modules.setdefault("secret_manager", _sm)

_dp = types.ModuleType("data_paths")
_dp.SEAT_NAMES_FILE       = Path("seat_names_test.json")
_dp.CHAIRMAN_PRESETS_FILE = Path("chairman_presets_test.json")
_dp.SCHEDULE_FILE         = Path("schedule_test.json")
_dp.CONFIG_DIR            = Path(".")
sys.modules.setdefault("data_paths", _dp)

# Stubs de worker y manager para test_preset_poll (ya registrados si corremos con pytest)
_cw_stub = types.ModuleType("ptz.visca.worker")

class _ViscaCommand:
    def __init__(self, camera, payload, priority=False, on_success=None, on_failure=None):
        self.camera     = camera
        self.payload    = payload
        self.priority   = priority
        self.on_success = on_success
        self.on_failure = on_failure

_cw_stub.ViscaCommand = _ViscaCommand
sys.modules.setdefault("ptz.visca.worker", _cw_stub)

# ─── Importar módulos reales ──────────────────────────────────────────────────

import importlib
from config import CAM1, CAM2, PRESET_MAP
from ptz.visca import commands as vcmd

vp_module    = importlib.import_module("ptz.visca.protocol")
ViscaProtocol = vp_module.ViscaProtocol
ViscaUICallbacks = vp_module.ViscaUICallbacks


# ─── Workers capturadores ─────────────────────────────────────────────────────

class _CapturingWorker:
    """Worker que captura comandos enviados. invoke_success controla el callback."""

    def __init__(self, ip: str, invoke_success: bool = True):
        self.ip               = ip
        self.sent:            list = []
        self.priority_sent:   list = []
        self._invoke_success  = invoke_success

    def send(self, cmd) -> bool:
        self.sent.append(cmd)
        if self._invoke_success and cmd.on_success:
            cmd.on_success()
        elif not self._invoke_success and cmd.on_failure:
            cmd.on_failure()
        return True

    def send_priority(self, cmd) -> bool:
        self.priority_sent.append(cmd)
        return True

    @property
    def all_sent(self):
        return self.sent + self.priority_sent


# ─── Stub de CameraManager ────────────────────────────────────────────────────

class _StubCameraManager:
    def __init__(self, w1: _CapturingWorker, w2: _CapturingWorker):
        self._w1 = w1
        self._w2 = w2
        self.backlight_on:   dict = {1: False, 2: False}
        self.focus_mode:     dict = {1: 'auto', 2: 'auto'}
        self.exposure_level: dict = {1: 0, 2: 0}
        self.ae_mode:        dict = {1: 'auto', 2: 'auto'}
        self._zoom:          dict = {}

    def cam_key(self, ip: str) -> int:
        return 1 if ip == CAM1.ip else 2

    def worker(self, ip: str) -> _CapturingWorker:
        return self._w1 if ip == CAM1.ip else self._w2

    def set_zoom(self, ip: str, pct: int): self._zoom[ip] = pct
    def get_zoom(self, ip: str): return self._zoom.get(ip)
    def invalidate_zoom(self, ip: str): self._zoom.pop(ip, None)
    def zoom_query_try_acquire(self, ip): return False
    def zoom_query_release(self, ip): pass
    def ae_query_try_acquire(self, ip): return False
    def ae_query_release(self, ip): pass


# ─── Fixture ─────────────────────────────────────────────────────────────────

def _make_proto(
    active_ip: str = None,
    invoke_success: bool = True,
    call_mode: bool = True,
    set_mode: bool = False,
    confirm: bool = True,
):
    if active_ip is None:
        active_ip = CAM1.ip

    w1 = _CapturingWorker(CAM1.ip, invoke_success)
    w2 = _CapturingWorker(CAM2.ip, invoke_success)
    cameras = _StubCameraManager(w1, w2)

    ui_cb = MagicMock()
    ui_cb.get_active_cam.return_value   = (active_ip, CAM1.cam_id if active_ip == CAM1.ip else CAM2.cam_id)
    ui_cb.get_pan_cap.return_value      = 24
    ui_cb.get_tilt_cap.return_value     = 20
    ui_cb.get_speed.return_value        = 10
    ui_cb.get_zoom_value.return_value   = 50
    ui_cb.is_call_mode.return_value     = call_mode
    ui_cb.is_set_mode.return_value      = set_mode
    ui_cb.confirm_preset.return_value   = confirm
    ui_cb.schedule_ui.side_effect       = lambda fn: fn()  # síncrono en tests

    proto                  = ViscaProtocol(cameras, ui_cb)
    proto._stop_lock       = threading.Lock()
    return proto, w1, w2, ui_cb


# ═══════════════════════════════════════════════════════════════════════════════
#  Movimiento Pan/Tilt
# ═══════════════════════════════════════════════════════════════════════════════

class TestMovementDispatch(unittest.TestCase):

    def test_up_dispatches_correct_payload(self):
        proto, w1, w2, _ = _make_proto()
        proto.Up(pan_spd=5, tilt_spd=8)
        self.assertEqual(len(w1.sent), 1)
        cmd = w1.sent[0]
        # pan_dir=STOP(03), tilt_dir=UP(01)
        self.assertEqual(cmd.payload[-3], 0x03)  # pan_dir STOP
        self.assertEqual(cmd.payload[-2], 0x01)  # tilt_dir UP
        self.assertEqual(cmd.payload[-1], 0xFF)

    def test_right_dispatches_correct_direction(self):
        proto, w1, w2, _ = _make_proto()
        proto.Right(pan_spd=5, tilt_spd=5)
        cmd = w1.sent[0]
        self.assertEqual(cmd.payload[-3], 0x02)  # pan_dir RIGHT
        self.assertEqual(cmd.payload[-2], 0x03)  # tilt_dir STOP

    def test_left_dispatches_correct_direction(self):
        proto, w1, w2, _ = _make_proto()
        proto.Left(pan_spd=5, tilt_spd=5)
        cmd = w1.sent[0]
        self.assertEqual(cmd.payload[-3], 0x01)  # pan_dir LEFT
        self.assertEqual(cmd.payload[-2], 0x03)  # tilt_dir STOP

    def test_down_dispatches_correct_direction(self):
        proto, w1, w2, _ = _make_proto()
        proto.Down(pan_spd=5, tilt_spd=5)
        cmd = w1.sent[0]
        self.assertEqual(cmd.payload[-3], 0x03)  # STOP
        self.assertEqual(cmd.payload[-2], 0x02)  # DOWN

    def test_upleft_diagonal(self):
        proto, w1, w2, _ = _make_proto()
        proto.UpLeft(pan_spd=5, tilt_spd=5)
        cmd = w1.sent[0]
        self.assertEqual(cmd.payload[-3], 0x01)  # LEFT
        self.assertEqual(cmd.payload[-2], 0x01)  # UP

    def test_downright_diagonal(self):
        proto, w1, w2, _ = _make_proto()
        proto.DownRight(pan_spd=5, tilt_spd=5)
        cmd = w1.sent[0]
        self.assertEqual(cmd.payload[-3], 0x02)  # RIGHT
        self.assertEqual(cmd.payload[-2], 0x02)  # DOWN

    def test_stop_uses_priority_flag(self):
        proto, w1, w2, _ = _make_proto()
        proto.Stop()
        self.assertEqual(len(w1.priority_sent), 1)
        self.assertEqual(len(w1.sent), 0)
        cmd = w1.priority_sent[0]
        self.assertEqual(cmd.payload, vcmd.pan_tilt_stop(CAM1.cam_id))

    def test_stop_does_not_send_to_cam2(self):
        proto, w1, w2, _ = _make_proto()
        proto.Stop()
        self.assertEqual(len(w2.priority_sent), 0)

    def test_movement_goes_to_active_camera(self):
        # Activa CAM2: el movimiento va al worker de CAM2
        proto, w1, w2, _ = _make_proto(active_ip=CAM2.ip)
        proto.Up(pan_spd=5, tilt_spd=5)
        self.assertEqual(len(w1.sent), 0)
        self.assertEqual(len(w2.sent), 1)

    def test_home_button_dispatches(self):
        proto, w1, w2, _ = _make_proto()
        proto.HomeButton()
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(w1.sent[0].payload, vcmd.home(CAM1.cam_id))

    def test_speed_capped_by_pan_cap(self):
        """Velocidades mayores al cap se recortan al cap."""
        proto, w1, w2, ui_cb = _make_proto()
        ui_cb.get_pan_cap.return_value  = 10
        ui_cb.get_tilt_cap.return_value = 8
        proto.Up(pan_spd=99, tilt_spd=99)
        cmd = w1.sent[0]
        # tilt_spd: pantalla usa tilt_cap=8
        self.assertEqual(cmd.payload[-4], 8)   # tilt_spd capped

    def test_stop_direction_sends_zero_speed(self):
        proto, w1, w2, _ = _make_proto()
        proto.Up(pan_spd=5, tilt_spd=8)
        cmd = w1.sent[0]
        # pan parado → speed 0
        self.assertEqual(cmd.payload[-5], 0)   # pan_spd = 0 (STOP)

    def test_dispatch_invalid_camera_drops(self):
        proto, w1, w2, _ = _make_proto()
        bad_cmd = _ViscaCommand(camera=99, payload=b'\x81\x01\x04\x00\x02\xFF')
        proto._dispatch(bad_cmd)
        self.assertEqual(len(w1.sent + w2.sent), 0)


# ═══════════════════════════════════════════════════════════════════════════════
#  Zoom
# ═══════════════════════════════════════════════════════════════════════════════

class TestZoomDispatch(unittest.TestCase):

    def test_zoom_absolute_dispatches_correct_cam(self):
        proto, w1, w2, _ = _make_proto()
        proto.ZoomAbsolute()
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(len(w2.sent), 0)

    def test_zoom_absolute_updates_cache(self):
        proto, w1, w2, ui_cb = _make_proto()
        ui_cb.get_zoom_value.return_value = 75
        proto.ZoomAbsolute()
        self.assertEqual(proto._cameras.get_zoom(CAM1.ip), 75)

    def test_zoom_absolute_payload(self):
        proto, w1, w2, ui_cb = _make_proto()
        ui_cb.get_zoom_value.return_value = 50
        proto.ZoomAbsolute()
        expected = vcmd.zoom_absolute(CAM1.cam_id, 50)
        self.assertEqual(w1.sent[0].payload, expected)


# ═══════════════════════════════════════════════════════════════════════════════
#  Focus
# ═══════════════════════════════════════════════════════════════════════════════

class TestFocusDispatch(unittest.TestCase):

    def test_autofocus_payload(self):
        proto, w1, w2, _ = _make_proto()
        proto.AutoFocus()
        self.assertEqual(w1.sent[0].payload, vcmd.focus_auto(CAM1.cam_id))

    def test_autofocus_on_success_updates_focus_mode(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto.AutoFocus()
        self.assertEqual(proto._cameras.focus_mode[1], 'auto')

    def test_manual_focus_payload(self):
        proto, w1, w2, _ = _make_proto()
        proto.ManualFocus()
        self.assertEqual(w1.sent[0].payload, vcmd.focus_manual(CAM1.cam_id))

    def test_manual_focus_on_success_updates_focus_mode(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto.ManualFocus()
        self.assertEqual(proto._cameras.focus_mode[1], 'manual')

    def test_focus_failure_calls_show_error(self):
        proto, w1, w2, ui_cb = _make_proto(invoke_success=False)
        proto.AutoFocus()
        ui_cb.show_error.assert_called_once()

    def test_focus_failure_does_not_update_mode(self):
        proto, w1, w2, _ = _make_proto(invoke_success=False)
        proto._cameras.focus_mode[1] = 'manual'
        proto.AutoFocus()
        # on_failure no toca focus_mode
        self.assertEqual(proto._cameras.focus_mode[1], 'manual')

    def test_one_push_af_payload(self):
        proto, w1, w2, _ = _make_proto()
        proto.OnePushAF()
        self.assertEqual(w1.sent[0].payload, vcmd.one_push_af(CAM1.cam_id))

    def test_one_push_af_success_result(self):
        proto, w1, w2, ui_cb = _make_proto(invoke_success=True)
        proto.OnePushAF()
        ui_cb.on_af_result.assert_called_once_with(True)

    def test_one_push_af_failure_result(self):
        proto, w1, w2, ui_cb = _make_proto(invoke_success=False)
        proto.OnePushAF()
        ui_cb.on_af_result.assert_called_once_with(False)


# ═══════════════════════════════════════════════════════════════════════════════
#  Backlight
# ═══════════════════════════════════════════════════════════════════════════════

class TestBacklightDispatch(unittest.TestCase):

    def test_off_to_on_sends_backlight_on(self):
        proto, w1, w2, _ = _make_proto()
        proto._cameras.backlight_on[1] = False
        proto.BacklightToggle()
        self.assertEqual(w1.sent[0].payload, vcmd.backlight_on(CAM1.cam_id))

    def test_on_to_off_sends_backlight_off(self):
        proto, w1, w2, _ = _make_proto()
        proto._cameras.backlight_on[1] = True
        proto.BacklightToggle()
        self.assertEqual(w1.sent[0].payload, vcmd.backlight_off(CAM1.cam_id))

    def test_success_updates_state_off_to_on(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto._cameras.backlight_on[1] = False
        proto.BacklightToggle()
        self.assertTrue(proto._cameras.backlight_on[1])

    def test_success_updates_state_on_to_off(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto._cameras.backlight_on[1] = True
        proto.BacklightToggle()
        self.assertFalse(proto._cameras.backlight_on[1])

    def test_failure_preserves_state(self):
        proto, w1, w2, _ = _make_proto(invoke_success=False)
        proto._cameras.backlight_on[1] = False
        proto.BacklightToggle()
        self.assertFalse(proto._cameras.backlight_on[1])

    def test_failure_calls_on_backlight_changed(self):
        # on_failure también llama a on_backlight_changed para sincronizar la UI
        proto, w1, w2, ui_cb = _make_proto(invoke_success=False)
        proto.BacklightToggle()
        ui_cb.on_backlight_changed.assert_called_once()

    def test_failure_calls_show_error(self):
        proto, w1, w2, ui_cb = _make_proto(invoke_success=False)
        proto.BacklightToggle()
        ui_cb.show_error.assert_called_once()

    def test_cam2_gets_its_own_backlight_state(self):
        proto, w1, w2, _ = _make_proto(active_ip=CAM2.ip, invoke_success=True)
        proto._cameras.backlight_on[2] = False
        proto.BacklightToggle()
        self.assertTrue(proto._cameras.backlight_on[2])
        self.assertFalse(proto._cameras.backlight_on[1])  # cam1 sin tocar


# ═══════════════════════════════════════════════════════════════════════════════
#  Brillo / Exposición
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrightnessDispatch(unittest.TestCase):

    def _brightness_up_with_mode(self, ae_mode: str, invoke_success=True):
        proto, w1, w2, ui_cb = _make_proto(invoke_success=invoke_success)
        proto._cameras.ae_mode[1] = ae_mode
        proto.BrightnessUp()
        return proto, w1, ui_cb

    def test_brightness_up_manual_mode_direct_command(self):
        _, w1, _ = self._brightness_up_with_mode('manual')
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(w1.sent[0].payload, vcmd.brightness_up_direct(CAM1.cam_id))

    def test_brightness_up_bright_mode_direct_command(self):
        _, w1, _ = self._brightness_up_with_mode('bright')
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(w1.sent[0].payload, vcmd.brightness_up_direct(CAM1.cam_id))

    def test_brightness_up_auto_mode_two_commands(self):
        # auto: exp_comp_on → exp_comp_up (encadenado vía on_success)
        _, w1, _ = self._brightness_up_with_mode('auto')
        self.assertEqual(len(w1.sent), 2)
        self.assertEqual(w1.sent[0].payload, vcmd.exp_comp_on(CAM1.cam_id))
        self.assertEqual(w1.sent[1].payload, vcmd.exp_comp_up(CAM1.cam_id))

    def test_brightness_up_auto_mode_on_success_updates_level(self):
        proto, w1, _ = self._brightness_up_with_mode('auto', invoke_success=True)
        self.assertEqual(proto._cameras.exposure_level[1], 1)

    def test_brightness_up_manual_on_success_updates_level(self):
        proto, w1, _ = self._brightness_up_with_mode('manual', invoke_success=True)
        self.assertEqual(proto._cameras.exposure_level[1], 1)

    def test_brightness_down_decrements_level(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto._cameras.ae_mode[1] = 'manual'
        proto._cameras.exposure_level[1] = 0
        proto.BrightnessDown()
        self.assertEqual(proto._cameras.exposure_level[1], -1)

    def test_brightness_down_auto_sends_exp_comp_down(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto._cameras.ae_mode[1] = 'auto'
        proto.BrightnessDown()
        self.assertEqual(w1.sent[1].payload, vcmd.exp_comp_down(CAM1.cam_id))

    def test_brightness_up_failure_calls_show_error(self):
        _, w1, ui_cb = self._brightness_up_with_mode('manual', invoke_success=False)
        ui_cb.show_error.assert_called_once()

    def test_brightness_up_success_calls_result_cb_true(self):
        _, w1, ui_cb = self._brightness_up_with_mode('manual', invoke_success=True)
        ui_cb.on_brightness_up_result.assert_called_once_with(True)

    def test_brightness_up_failure_calls_result_cb_false(self):
        _, w1, ui_cb = self._brightness_up_with_mode('manual', invoke_success=False)
        ui_cb.on_brightness_up_result.assert_called_once_with(False)

    def test_exposure_level_clamped_at_plus7(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto._cameras.ae_mode[1] = 'manual'
        proto._cameras.exposure_level[1] = 7
        proto.BrightnessUp()
        self.assertEqual(proto._cameras.exposure_level[1], 7)  # no sube de +7

    def test_exposure_level_clamped_at_minus7(self):
        proto, w1, w2, _ = _make_proto(invoke_success=True)
        proto._cameras.ae_mode[1] = 'manual'
        proto._cameras.exposure_level[1] = -7
        proto.BrightnessDown()
        self.assertEqual(proto._cameras.exposure_level[1], -7)

    def test_auto_mode_first_command_failure_does_not_send_second(self):
        # Si exp_comp_on falla, exp_comp_up NO debe enviarse
        proto, w1, w2, _ = _make_proto(invoke_success=False)
        proto._cameras.ae_mode[1] = 'auto'
        proto.BrightnessUp()
        # Solo 1 comando (exp_comp_on) — el segundo no se encola
        self.assertEqual(len(w1.sent), 1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Presets: routing y modos
# ═══════════════════════════════════════════════════════════════════════════════

class TestPresetRouting(unittest.TestCase):

    def test_preset_1_goes_to_cam1(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(1)
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(len(w2.sent), 0)

    def test_preset_2_goes_to_cam1(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(2)
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(len(w2.sent), 0)

    def test_preset_3_goes_to_cam1(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(3)
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(len(w2.sent), 0)

    def test_preset_4_goes_to_cam2(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(4)
        self.assertEqual(len(w1.sent), 0)
        self.assertEqual(len(w2.sent), 1)

    def test_preset_50_goes_to_cam2(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(50)
        self.assertEqual(len(w2.sent), 1)

    def test_recall_payload_contains_preset_byte(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(1)
        payload = w1.sent[0].payload
        expected_preset_hex = PRESET_MAP[1]
        expected_byte = int(expected_preset_hex, 16)
        self.assertIn(expected_byte, payload)

    def test_recall_payload_opcode_02(self):
        # Recall usa 0x02. Formato final: ... 3F 02 <preset> FF
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(1)
        payload = w1.sent[0].payload
        # -3=opcode(02), -2=preset_byte, -1=FF
        self.assertEqual(payload[-3], 0x02)

    def test_no_mode_active_does_not_dispatch(self):
        proto, w1, w2, _ = _make_proto(call_mode=False, set_mode=False)
        proto.go_to_preset(1)
        self.assertEqual(len(w1.sent + w2.sent), 0)

    def test_invalid_preset_number_does_not_dispatch(self):
        proto, w1, w2, _ = _make_proto(call_mode=True)
        proto.go_to_preset(9999)  # no en PRESET_MAP
        self.assertEqual(len(w1.sent + w2.sent), 0)

    def test_recall_on_success_starts_poll(self):
        poll_calls = []
        proto, w1, w2, _ = _make_proto(call_mode=True, invoke_success=True)
        proto._start_preset_poll = lambda *a: poll_calls.append(a)
        proto.go_to_preset(1)
        self.assertEqual(len(poll_calls), 1)
        ip, cam_id, active_ip, ceiling = poll_calls[0]
        self.assertEqual(ip, CAM1.ip)
        self.assertEqual(cam_id, CAM1.cam_id)

    def test_recall_on_failure_shows_error(self):
        proto, w1, w2, ui_cb = _make_proto(call_mode=True, invoke_success=False)
        proto.go_to_preset(1)
        ui_cb.show_error.assert_called_once()


class TestPresetSave(unittest.TestCase):

    def test_save_dispatches_when_confirmed(self):
        proto, w1, w2, _ = _make_proto(set_mode=True, call_mode=False, confirm=True)
        proto.go_to_preset(1)
        self.assertEqual(len(w1.sent), 1)

    def test_save_opcode_is_01(self):
        # Save usa 0x01. Formato final: ... 3F 01 <preset> FF
        proto, w1, w2, _ = _make_proto(set_mode=True, call_mode=False, confirm=True)
        proto.go_to_preset(1)
        payload = w1.sent[0].payload
        self.assertEqual(payload[-3], 0x01)  # save = 0x01

    def test_save_does_not_dispatch_when_not_confirmed(self):
        proto, w1, w2, _ = _make_proto(set_mode=True, call_mode=False, confirm=False)
        proto.go_to_preset(1)
        self.assertEqual(len(w1.sent + w2.sent), 0)

    def test_save_preset_1_goes_to_cam1(self):
        proto, w1, w2, _ = _make_proto(set_mode=True, call_mode=False, confirm=True)
        proto.go_to_preset(1)
        self.assertEqual(len(w1.sent), 1)
        self.assertEqual(len(w2.sent), 0)

    def test_save_preset_10_goes_to_cam2(self):
        proto, w1, w2, _ = _make_proto(set_mode=True, call_mode=False, confirm=True)
        proto.go_to_preset(10)
        self.assertEqual(len(w2.sent), 1)

    def test_save_failure_shows_error(self):
        proto, w1, w2, ui_cb = _make_proto(
            set_mode=True, call_mode=False, confirm=True, invoke_success=False)
        proto.go_to_preset(1)
        ui_cb.show_error.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
#  Comandos a cámara fija (no activa)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFixedCameraCommands(unittest.TestCase):

    def test_send_comments_cam_home_goes_to_cam2(self):
        """_send_comments_cam_home siempre manda a CAM2, independiente de la activa."""
        proto, w1, w2, _ = _make_proto(active_ip=CAM1.ip)
        proto._send_comments_cam_home()
        self.assertEqual(len(w2.sent), 1)
        self.assertEqual(len(w1.sent), 0)
        self.assertEqual(w2.sent[0].payload, vcmd.home(CAM2.cam_id))


if __name__ == '__main__':
    unittest.main(verbosity=2)
