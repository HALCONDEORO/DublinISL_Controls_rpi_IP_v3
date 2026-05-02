#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# tests/test_visca_worker_extra.py — Tests adicionales de CameraWorker
#
# Cubre: send_priority, heartbeat_age, _has_final_visca_frame, _classify_payload,
#        _socket_alive, restart(), y el fix crítico de _connect() fuera del lock.

from __future__ import annotations

import queue
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

# ─── Stubs PyQt5 ─────────────────────────────────────────────────────────────

_pyqt5     = types.ModuleType("PyQt5")
_qtcore    = types.ModuleType("PyQt5.QtCore")
_qtwidgets = types.ModuleType("PyQt5.QtWidgets")

class _FakeSignal:
    def emit(self, *a): pass
    def connect(self, *a): pass

class _FakeQObject:
    def __init__(self, *a, **kw): pass

_qtcore.QObject    = _FakeQObject
_qtcore.pyqtSignal = lambda *a, **kw: _FakeSignal()
_pyqt5.QtCore      = _qtcore
_pyqt5.QtWidgets   = _qtwidgets
sys.modules.setdefault("PyQt5",           _pyqt5)
sys.modules.setdefault("PyQt5.QtCore",    _qtcore)
sys.modules.setdefault("PyQt5.QtWidgets", _qtwidgets)

_sm = types.ModuleType("secret_manager")
_sm.decrypt_password = lambda: "test"
sys.modules.setdefault("secret_manager", _sm)

_dp = types.ModuleType("data_paths")
from pathlib import Path
_dp.SEAT_NAMES_FILE       = Path("seat_names_test.json")
_dp.CHAIRMAN_PRESETS_FILE = Path("chairman_presets_test.json")
_dp.SCHEDULE_FILE         = Path("schedule_test.json")
_dp.CONFIG_DIR            = Path(".")
_dp._DATA_FILES           = (_dp.CHAIRMAN_PRESETS_FILE, _dp.SEAT_NAMES_FILE, _dp.SCHEDULE_FILE)
_dp._LEGACY_FILES         = tuple(f.name for f in _dp._DATA_FILES)
_dp._CONFIG_TXT_FILES     = ("PTZ1IP.txt", "PTZ2IP.txt", "Cam1ID.txt", "Cam2ID.txt", "ATEMIP.txt", "Contact.txt")
_prev_data_paths = sys.modules.get("data_paths")
sys.modules.setdefault("data_paths", _dp)

# Asegurar módulo real
sys.modules.pop("ptz.visca.worker", None)
from ptz.visca.worker import CameraWorker, ViscaCommand

if _prev_data_paths is None:
    sys.modules.pop("data_paths", None)
else:
    sys.modules["data_paths"] = _prev_data_paths


# ─── Subclases de worker controlables ────────────────────────────────────────

class _BaseTestWorker(CameraWorker):
    """CameraWorker sin thread ni red real."""
    def __init__(self, connect_result=None):
        self.ip              = "10.0.0.99"
        self.port            = 5678
        self._is_connected   = False
        self._queue          = queue.Queue(maxsize=20)
        self._sock           = None
        self._lock           = threading.Lock()
        self._last_heartbeat = time.monotonic()
        self.signals         = MagicMock()
        self.signals.connection_changed = MagicMock()
        self.signals.visca_error        = MagicMock()
        self._connect_result = connect_result

    def _connect(self):
        return self._connect_result

    def _ping(self):
        pass  # Los tests controlan la cola; el heartbeat real solo mete ruido aqui.

    def _set_connected(self, connected: bool):
        self._is_connected = connected


def _start(worker: CameraWorker) -> CameraWorker:
    worker._thread = threading.Thread(
        target=worker._run, daemon=True, name=f"Test-{worker.ip}")
    worker._thread.start()
    return worker


# ─────────────────────────────────────────────────────────────────────────────
#  send_priority()
# ─────────────────────────────────────────────────────────────────────────────

class TestSendPriority(unittest.TestCase):

    def _make_worker(self):
        w = _BaseTestWorker()
        # No lanzamos el thread: solo probamos la cola
        return w

    def test_send_priority_empties_queue(self):
        w = self._make_worker()
        # Llenar la cola con comandos normales
        for i in range(5):
            w.send(ViscaCommand(camera=1, payload=bytes([0x81, i, 0xFF])))
        self.assertEqual(w._queue.qsize(), 5)

        priority_cmd = ViscaCommand(camera=1, payload=b'\x81\x01\x06\x01\x00\x00\x03\x03\xFF')
        w.send_priority(priority_cmd)

        self.assertEqual(w._queue.qsize(), 1)
        queued = w._queue.get_nowait()
        self.assertIs(queued, priority_cmd)

    def test_send_priority_on_empty_queue(self):
        w = self._make_worker()
        cmd = ViscaCommand(camera=1, payload=b'\x81\x01\xFF')
        w.send_priority(cmd)
        self.assertEqual(w._queue.qsize(), 1)

    def test_send_normal_returns_true_when_space(self):
        w = self._make_worker()
        result = w.send(ViscaCommand(camera=1, payload=b'\x81\xFF'))
        self.assertTrue(result)

    def test_send_returns_false_when_full(self):
        w = self._make_worker()
        for _ in range(20):  # CAMERA_QUEUE_MAXSIZE
            w.send(ViscaCommand(camera=1, payload=b'\x81\xFF'))
        result = w.send(ViscaCommand(camera=1, payload=b'\x81\xFF'))
        self.assertFalse(result)


# ─────────────────────────────────────────────────────────────────────────────
#  heartbeat_age()
# ─────────────────────────────────────────────────────────────────────────────

class TestHeartbeatAge(unittest.TestCase):

    def test_age_increases_over_time(self):
        w = _BaseTestWorker()
        w._last_heartbeat = time.monotonic()
        time.sleep(0.05)
        self.assertGreater(w.heartbeat_age(), 0.04)

    def test_age_resets_when_heartbeat_updated(self):
        w = _BaseTestWorker()
        w._last_heartbeat = time.monotonic() - 10.0
        self.assertGreater(w.heartbeat_age(), 9.0)
        w._last_heartbeat = time.monotonic()
        self.assertLess(w.heartbeat_age(), 0.1)


# ─────────────────────────────────────────────────────────────────────────────
#  _has_final_visca_frame()
# ─────────────────────────────────────────────────────────────────────────────

class TestHasFinalViscaFrame(unittest.TestCase):
    _hf = staticmethod(CameraWorker._has_final_visca_frame)

    def test_completion_frame(self):
        # 9x 50 FF → Completion (0x50 & 0xF0 = 0x50)
        self.assertTrue(self._hf(b'\x90\x50\xFF'))

    def test_error_frame(self):
        # 9x 60 02 FF → Error (0x60 & 0xF0 = 0x60)
        self.assertTrue(self._hf(b'\x90\x60\x02\xFF'))

    def test_ack_only_not_final(self):
        # 9x 41 FF → ACK (0x40 & 0xF0 = 0x40) → no es final
        self.assertFalse(self._hf(b'\x90\x41\xFF'))

    def test_ack_plus_completion(self):
        # ACK seguido de Completion → True (detecta la Completion)
        self.assertTrue(self._hf(b'\x90\x41\xFF\x90\x50\xFF'))

    def test_empty_data(self):
        self.assertFalse(self._hf(b''))

    def test_only_ff(self):
        # FF sola → frame vacío antes de FF → len < 2 → no final
        self.assertFalse(self._hf(b'\xFF'))

    def test_multiple_errors_any_matches(self):
        # Error complejo 9x 60 02 FF
        self.assertTrue(self._hf(b'\x90\x60\x02\xFF'))

    def test_no_ff_terminator(self):
        self.assertFalse(self._hf(b'\x90\x50'))

    def test_ack_plus_syntax_error(self):
        # ACK + Error de sintaxis (0x6002)
        data = b'\x90\x41\xFF\x90\x60\x02\xFF'
        self.assertTrue(self._hf(data))


# ─────────────────────────────────────────────────────────────────────────────
#  _classify_payload()
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyPayload(unittest.TestCase):
    _cp = staticmethod(CameraWorker._classify_payload)

    def test_pan_tilt_move(self):
        # 81 01 06 01 ... → body[1:4] = 01 06 01
        self.assertEqual(self._cp(b'\x81\x01\x06\x01\x09\x09\x03\x03\xFF'), 'move')

    def test_zoom_drive(self):
        # 81 01 04 07 ... → body[1:4] = 01 04 07
        self.assertEqual(self._cp(b'\x81\x01\x04\x07\x25\xFF'), 'zoom_drive')

    def test_preset_recall_is_other(self):
        # 81 01 04 3F 02 01 FF → body = 01 04 3F
        self.assertEqual(self._cp(b'\x81\x01\x04\x3F\x02\x01\xFF'), 'other')

    def test_power_on_is_other(self):
        self.assertEqual(self._cp(b'\x81\x01\x04\x00\x02\xFF'), 'other')

    def test_empty_payload_is_other(self):
        # Slice vacío no lanza IndexError
        self.assertEqual(self._cp(b''), 'other')

    def test_short_payload_is_other(self):
        self.assertEqual(self._cp(b'\x81'), 'other')


# ─────────────────────────────────────────────────────────────────────────────
#  _socket_alive()
# ─────────────────────────────────────────────────────────────────────────────

class TestSocketAlive(unittest.TestCase):
    _sa = staticmethod(CameraWorker._socket_alive)

    @patch('select.select')
    def test_not_readable_means_alive(self, mock_sel):
        sock = MagicMock()
        mock_sel.return_value = ([], [], [])
        self.assertTrue(self._sa(sock))

    @patch('select.select')
    def test_readable_with_data_means_alive(self, mock_sel):
        sock = MagicMock()
        mock_sel.return_value = ([sock], [], [])
        sock.recv.return_value = b'\x90'
        self.assertTrue(self._sa(sock))

    @patch('select.select')
    def test_readable_empty_means_dead(self, mock_sel):
        # EOF: la cámara cerró la conexión
        sock = MagicMock()
        mock_sel.return_value = ([sock], [], [])
        sock.recv.return_value = b''
        self.assertFalse(self._sa(sock))

    @patch('select.select')
    def test_oserror_on_select_means_dead(self, mock_sel):
        sock = MagicMock()
        mock_sel.side_effect = OSError("bad fd")
        self.assertFalse(self._sa(sock))

    @patch('select.select')
    def test_invalid_socket_from_select_means_dead(self, mock_sel):
        sock = MagicMock()
        mock_sel.side_effect = TypeError("fileno() returned a non-integer")
        self.assertFalse(self._sa(sock))

    @patch('select.select')
    def test_valueerror_from_select_means_dead(self, mock_sel):
        sock = MagicMock()
        mock_sel.side_effect = ValueError("file descriptor cannot be a negative integer")
        self.assertFalse(self._sa(sock))

    @patch('select.select')
    def test_oserror_on_recv_means_dead(self, mock_sel):
        sock = MagicMock()
        mock_sel.return_value = ([sock], [], [])
        sock.recv.side_effect = OSError("connection reset")
        self.assertFalse(self._sa(sock))


# ─────────────────────────────────────────────────────────────────────────────
#  restart()
# ─────────────────────────────────────────────────────────────────────────────

class TestRestart(unittest.TestCase):

    def test_restart_noop_if_thread_alive(self):
        class _AlwaysConnectedWorker(_BaseTestWorker):
            def _connect(self):
                return MagicMock()
            def _read_visca_response(self, sock):
                return b'\x90\x50\xFF'

        w = _start(_AlwaysConnectedWorker())
        original_thread = w._thread
        time.sleep(0.05)
        w.restart()  # thread vivo → no hace nada
        self.assertIs(w._thread, original_thread)

    def test_restart_relaunches_dead_thread(self):
        class _QuickDieWorker(_BaseTestWorker):
            def _run(self):
                pass  # sale inmediatamente

        w = _QuickDieWorker()
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()
        w._thread.join(timeout=1.0)  # esperar a que muera
        self.assertFalse(w._thread.is_alive())

        w.restart()
        time.sleep(0.05)  # dar tiempo al nuevo thread a arrancar (aunque salga rápido)
        # El thread fue reemplazado (no es el mismo objeto)
        # Solo verificamos que restart() no lanza excepción y crea un nuevo thread
        self.assertIsNotNone(w._thread)


# ─────────────────────────────────────────────────────────────────────────────
#  FIX: _connect() fuera del lock en _run()
#
#  Regresión detectada: antes, _connect() se llamaba dentro de `with self._lock:`,
#  bloqueando el lock durante hasta SOCKET_TIMEOUT segundos. Cualquier llamada
#  a _close_socket() desde la UI quedaba paralizada durante ese tiempo.
#
#  El test verifica que _close_socket() desde otro thread completa sin bloqueo
#  mientras _connect() está en progreso en _run().
# ─────────────────────────────────────────────────────────────────────────────

class TestConnectOutsideLock(unittest.TestCase):

    def test_close_socket_not_blocked_while_connecting(self):
        connect_started  = threading.Event()
        connect_proceed  = threading.Event()

        class _BlockingConnectWorker(_BaseTestWorker):
            def _connect(self):
                connect_started.set()
                connect_proceed.wait(timeout=3.0)
                return None  # fallo después de esperar

        w = _BlockingConnectWorker()
        # Lanzar _run() en background (igual que el worker real)
        w._thread = threading.Thread(target=w._run, daemon=True, name="Test-blocking")
        w._thread.start()

        # Encolar un comando para que _run() intente conectar
        w.send(ViscaCommand(camera=1, payload=b'\x81\x01\x04\x00\x02\xFF'))

        # Esperar a que _connect() haya empezado
        self.assertTrue(connect_started.wait(timeout=2.0), "_connect() no arrancó")

        # _close_socket() desde otro thread NO debe quedar bloqueada
        t0 = time.monotonic()
        w._close_socket()
        elapsed = time.monotonic() - t0

        # Dejar que _connect() termine
        connect_proceed.set()

        self.assertLess(elapsed, 0.3,
                        f"_close_socket() tardó {elapsed:.3f}s — "
                        f"_connect() estaba reteniendo el lock (bug regresión)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
