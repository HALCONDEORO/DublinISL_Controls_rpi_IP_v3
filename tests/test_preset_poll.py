#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# test_preset_poll.py — Prueba antiestres del subsistema de polling de preset
#
# Corre sin QApplication: usa stubs mínimos para PyQt5, camera_worker y
# camera_manager. Ejecutar directamente:
#   python test_preset_poll.py
#
# Escenarios cubiertos:
#   1. Estabilidad normal         — el loop sale a los ~900 ms (3 ciclos × 300 ms)
#   2. Disparo rápido (rapid fire) — 20 presets en <10 ms → solo 1 poll activo
#   3. Cancelación                — cancel_preset_polls() para en < INTERVAL + margen
#   4. Fallo de red               — todo retorna (None, None) → corre hasta techo
#   5. Dos cámaras simultáneas    — CAM1 y CAM2 son independientes y limpian bien
#   6. Excepción en ciclo         — try/finally garantiza que el evento se elimina

from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

# ─── Stubs para módulos con dependencias Qt / hardware ───────────────────────

# PyQt5 stub (ninguna señal real necesaria en este test)
pyqt5_stub      = types.ModuleType("PyQt5")
qtcore_stub     = types.ModuleType("PyQt5.QtCore")
qtwidgets_stub  = types.ModuleType("PyQt5.QtWidgets")
qtcore_stub.QObject   = object
qtcore_stub.pyqtSignal = lambda *a, **kw: None
qtcore_stub.QTimer    = MagicMock()
qtwidgets_stub.QMessageBox = MagicMock()
pyqt5_stub.QtCore    = qtcore_stub
pyqt5_stub.QtWidgets = qtwidgets_stub
sys.modules.setdefault("PyQt5",          pyqt5_stub)
sys.modules.setdefault("PyQt5.QtCore",   qtcore_stub)
sys.modules.setdefault("PyQt5.QtWidgets", qtwidgets_stub)

# ptz.visca.worker stub (el módulo real vive ahora en ptz/visca/worker.py)
cw_stub = types.ModuleType("ptz.visca.worker")

class _ViscaCommand:
    def __init__(self, camera, payload, priority=False, on_success=None, on_failure=None):
        self.camera     = camera
        self.payload    = payload
        self.priority   = priority
        self.on_success = on_success
        self.on_failure = on_failure

cw_stub.ViscaCommand = _ViscaCommand

class _CameraWorkerSignals:
    connection_changed = MagicMock()
    visca_error        = MagicMock()

class _CameraWorker:
    def __init__(self, ip, port=5678):
        self.ip      = ip
        self.signals = _CameraWorkerSignals()
    def send(self, cmd):          return True
    def send_priority(self, cmd): pass
    def heartbeat_age(self):      return 0.0
    def restart(self):            pass

cw_stub.CameraWorkerSignals = _CameraWorkerSignals
cw_stub.CameraWorker        = _CameraWorker
sys.modules["ptz.visca.worker"] = cw_stub

# ptz.visca.manager stub (el módulo real vive ahora en ptz/visca/manager.py)
cm_stub = types.ModuleType("ptz.visca.manager")

class _CameraManager:
    def __init__(self):
        self._zoom: dict[str, int] = {}
        self.focus_mode: dict[int, str] = {}
        self.ae_mode: dict[int, str] = {1: 'auto', 2: 'auto'}
        self.exposure_level: dict[int, int] = {1: 0, 2: 0}
        self.backlight_on: dict[int, bool] = {1: False, 2: False}
    def set_zoom(self, ip, pct): self._zoom[ip] = pct
    def get_zoom(self, ip):      return self._zoom.get(ip, 0)
    def cam_key(self, ip):       return 1 if ip == IP1 else 2
    def ae_query_try_acquire(self, ip): return False  # no lanzar threads AE en tests
    def ae_query_release(self, ip):     pass
    def zoom_query_try_acquire(self, ip): return False
    def zoom_query_release(self, ip):     pass
    def worker(self, ip):        return _CameraWorker(ip)

cm_stub.CameraManager = _CameraManager
sys.modules["ptz.visca.manager"] = cm_stub

# secret_manager stub (requerido por config.py)
sm_stub = types.ModuleType("secret_manager")
sm_stub.decrypt_password = lambda: "test"
sys.modules["secret_manager"] = sm_stub

# data_paths stub: incluye todos los atributos que otros modulos importan al nivel de modulo,
# para que la sustitucion temporal en sys.modules no rompa imports de config durante este archivo.
dp_stub = types.ModuleType("data_paths")
from pathlib import Path
dp_stub.SEAT_NAMES_FILE        = Path("seat_names_test.json")
dp_stub.CHAIRMAN_PRESETS_FILE  = Path("chairman_presets_test.json")
dp_stub.SCHEDULE_FILE          = Path("schedule_test.json")
dp_stub.CONFIG_DIR             = Path(".")
dp_stub._DATA_FILES            = (dp_stub.CHAIRMAN_PRESETS_FILE, dp_stub.SEAT_NAMES_FILE, dp_stub.SCHEDULE_FILE)
dp_stub._LEGACY_FILES          = tuple(f.name for f in dp_stub._DATA_FILES)
dp_stub._CONFIG_TXT_FILES      = ("PTZ1IP.txt", "PTZ2IP.txt", "Cam1ID.txt", "Cam2ID.txt", "ATEMIP.txt", "Contact.txt")
_prev_data_paths = sys.modules.get("data_paths")
sys.modules["data_paths"] = dp_stub
# ─── Ahora podemos importar el módulo real ────────────────────────────────────
from config import (
    PRESET_ZOOM_SETTLE_BASE, PRESET_ZOOM_SETTLE_MARGIN,
    PRESET_ZOOM_SETTLE_MAX, PRESET_ZOOM_POLL_INTERVAL, PAN_SPEED_MAX,
)

# Importar solo la clase de polling (no la clase completa que requiere workers)
import importlib
import inspect

# Importar ViscaProtocol directamente
vp_module = importlib.import_module("ptz.visca.protocol")
ViscaProtocol = vp_module.ViscaProtocol

# Evitar que el stub de data_paths contamine otros modulos de test que importan
# data_paths directamente durante su propia ejecucion.
if _prev_data_paths is None:
    sys.modules.pop("data_paths", None)
else:
    sys.modules["data_paths"] = _prev_data_paths

# ─── Fixture: instancia de ViscaProtocol con callbacks stubbed ───────────────

IP1 = "10.0.0.1"
IP2 = "10.0.0.2"
CAM_ID1 = "81"
CAM_ID2 = "82"
ZOOM_MAX = 0x4000  # 16384


def _make_protocol(query_fn=None, active_ip=IP1):
    """Construye un ViscaProtocol sin workers ni sockets reales.

    query_fn: callable(ip, cam_id) → (pos, zoom_raw).
              Por defecto simula cámara quieta en zoom 50 %.
    """
    cameras = _CameraManager()

    # ui_cb stub
    ui_cb = MagicMock()
    ui_cb.get_pan_cap.return_value = PAN_SPEED_MAX
    slider_calls: list[int] = []
    ui_cb.update_zoom_slider.side_effect = slider_calls.append

    # Parchear workers para que no intenten conectar
    w1 = _CameraWorker(IP1)
    w2 = _CameraWorker(IP2)

    proto = object.__new__(ViscaProtocol)
    proto._cameras              = cameras
    proto._ui_cb                = ui_cb
    proto._preset_stop_events   = {}
    proto._stop_lock            = threading.Lock()
    proto._worker               = {1: w1, 2: w2}
    proto._active_cam_idx       = 0
    proto._active_ip            = active_ip

    # _active_cam devuelve la IP activa actual
    proto._active_cam = lambda: (proto._active_ip, CAM_ID1 if proto._active_ip == IP1 else CAM_ID2)

    # _query_position_and_zoom: inyectable
    if query_fn is not None:
        proto._query_position_and_zoom = query_fn

    return proto, slider_calls


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _run_poll(proto, ip, cam_id, active_ip, ceiling, stop):
    """Arranca el loop en un thread y devuelve el thread."""
    t = threading.Thread(
        target=proto._preset_poll_loop,
        args=(ip, cam_id, active_ip, ceiling, stop),
        daemon=True,
    )
    t.start()
    return t


# ═══════════════════════════════════════════════════════════════════════════════
#  TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPresetPollStability(unittest.TestCase):
    """Escenario 1: estabilidad normal — sale tras 2 ciclos sin cambio."""

    def test_exits_after_two_stable_cycles(self):
        zoom_stable = round(0.5 * ZOOM_MAX)  # 50 %
        pan_stable  = (1000, 500)

        def _query(ip, cam_id):
            return pan_stable, zoom_stable

        proto, slider_calls = _make_protocol(_query)
        stop = threading.Event()
        ceiling = 5.0  # margen generoso

        t0 = time.monotonic()
        t = _run_poll(proto, IP1, CAM_ID1, IP1, ceiling, stop)
        t.join(timeout=3.0)
        elapsed = time.monotonic() - t0

        self.assertFalse(t.is_alive(), "Poll loop no terminó")
        # Mínimo: primer ciclo (prev=None → inestable) + 2 ciclos estables × INTERVAL
        self.assertGreaterEqual(elapsed, 2 * PRESET_ZOOM_POLL_INTERVAL - 0.05)
        # Máximo: no debería tardarse más de 10 ciclos
        self.assertLess(elapsed, 10 * PRESET_ZOOM_POLL_INTERVAL + 0.5)
        # El slider se actualizó al menos 3 veces
        self.assertGreaterEqual(len(slider_calls), 3)
        # El valor final del slider es 50 %
        self.assertEqual(slider_calls[-1], 50)
        # Limpieza: evento eliminado del dict
        self.assertNotIn(IP1, proto._preset_stop_events)

    def test_slider_not_updated_for_inactive_camera(self):
        """Si la cámara no está activa (usuario cambió de cámara), el slider no se toca."""
        zoom_stable = round(0.3 * ZOOM_MAX)

        def _query(ip, cam_id):
            return None, zoom_stable

        proto, slider_calls = _make_protocol(_query, active_ip=IP2)  # activa = CAM2
        stop = threading.Event()

        t = _run_poll(proto, IP1, CAM_ID1, IP2, 3.0, stop)  # active_ip=IP2 ≠ IP1
        t.join(timeout=3.0)

        # El zoom del cache de CAM1 sí se actualiza
        self.assertEqual(proto._cameras.get_zoom(IP1), 30)
        # Pero el slider (perteneciente a la cámara activa = CAM2) NO
        self.assertEqual(len(slider_calls), 0)


class TestPresetPollRapidFire(unittest.TestCase):
    """Escenario 2: 20 presets en <10 ms → solo 1 poll vivo al final."""

    def test_only_one_poll_survives(self):
        lock = threading.Lock()
        active_threads: list[threading.Event] = []

        def _query(ip, cam_id):
            time.sleep(PRESET_ZOOM_POLL_INTERVAL)
            return None, round(0.5 * ZOOM_MAX)

        proto, _ = _make_protocol(_query)

        events_created = []
        for _ in range(20):
            ceiling = 2.0
            proto._start_preset_poll(IP1, CAM_ID1, IP1, ceiling)
            if IP1 in proto._preset_stop_events:
                events_created.append(proto._preset_stop_events[IP1])

        # Dar tiempo a que los threads arrranquen y los anteriores sean cancelados
        time.sleep(PRESET_ZOOM_POLL_INTERVAL * 3 + 0.3)

        alive = [e for e in events_created if not e.is_set()]
        # Solo el último evento debe seguir activo (o ya terminó limpiamente)
        self.assertLessEqual(len(alive), 1, f"Más de 1 poll activo: {len(alive)}")


class TestPresetPollCancellation(unittest.TestCase):
    """Escenario 3: cancel_preset_polls() detiene el poll en < INTERVAL + margen."""

    def test_cancel_stops_quickly(self):
        # Query que nunca estabiliza
        def _query(ip, cam_id):
            return (int(time.monotonic() * 1000) % 0xFFFF, 0), int(time.monotonic() * 100) % ZOOM_MAX

        proto, _ = _make_protocol(_query)
        ceiling = 60.0  # techo largo para que no expire solo

        stop = threading.Event()
        proto._preset_stop_events[IP1] = stop
        t = _run_poll(proto, IP1, CAM_ID1, IP1, ceiling, stop)

        # Dejar que al menos un ciclo corra
        time.sleep(PRESET_ZOOM_POLL_INTERVAL + 0.1)

        t0 = time.monotonic()
        proto.cancel_preset_polls()
        t.join(timeout=PRESET_ZOOM_POLL_INTERVAL + 0.5)
        elapsed = time.monotonic() - t0

        self.assertFalse(t.is_alive(), "Poll no se canceló a tiempo")
        self.assertLess(elapsed, PRESET_ZOOM_POLL_INTERVAL + 0.3,
                        f"cancel tardó demasiado: {elapsed:.3f}s")
        self.assertNotIn(IP1, proto._preset_stop_events)

    def test_cancel_all_two_cameras(self):
        """cancel_preset_polls() cancela CAM1 y CAM2 simultáneamente."""
        def _query(ip, cam_id):
            time.sleep(0.05)
            return None, None  # siempre inestable

        proto, _ = _make_protocol(_query)
        proto._active_ip = IP1

        for ip, cam_id in [(IP1, CAM_ID1), (IP2, CAM_ID2)]:
            proto._start_preset_poll(ip, cam_id, IP1, 60.0)

        time.sleep(0.2)
        # Ambos eventos deben existir antes de cancelar
        self.assertIn(IP1, proto._preset_stop_events)
        self.assertIn(IP2, proto._preset_stop_events)

        proto.cancel_preset_polls()
        time.sleep(PRESET_ZOOM_POLL_INTERVAL + 0.3)

        self.assertNotIn(IP1, proto._preset_stop_events)
        self.assertNotIn(IP2, proto._preset_stop_events)


class TestPresetPollNetworkFailure(unittest.TestCase):
    """Escenario 4: red caída → todo retorna (None, None) → corre hasta techo."""

    def test_runs_to_ceiling_on_total_failure(self):
        def _query(ip, cam_id):
            return None, None

        ceiling = PRESET_ZOOM_POLL_INTERVAL * 4  # ~1.2 s
        proto, slider_calls = _make_protocol(_query)
        stop = threading.Event()

        t0 = time.monotonic()
        t = _run_poll(proto, IP1, CAM_ID1, IP1, ceiling, stop)
        t.join(timeout=ceiling + 1.0)
        elapsed = time.monotonic() - t0

        self.assertFalse(t.is_alive(), "Poll no terminó al llegar al techo")
        self.assertGreaterEqual(elapsed, ceiling - 0.1, "Terminó antes del techo")
        # Sin datos de zoom → slider nunca actualizado
        self.assertEqual(len(slider_calls), 0)
        self.assertNotIn(IP1, proto._preset_stop_events)


class TestPresetPollConcurrent(unittest.TestCase):
    """Escenario 5: CAM1 y CAM2 en paralelo son independientes."""

    def test_two_cameras_independent(self):
        zoom1 = round(0.25 * ZOOM_MAX)
        zoom2 = round(0.75 * ZOOM_MAX)

        def _query(ip, cam_id):
            if ip == IP1:
                return (100, 50), zoom1
            return (200, 100), zoom2

        proto, _ = _make_protocol(_query)
        proto._active_ip = IP1

        stop1 = threading.Event()
        stop2 = threading.Event()
        proto._preset_stop_events[IP1] = stop1
        proto._preset_stop_events[IP2] = stop2

        t1 = _run_poll(proto, IP1, CAM_ID1, IP1, 5.0, stop1)
        t2 = _run_poll(proto, IP2, CAM_ID2, IP1, 5.0, stop2)

        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        self.assertFalse(t1.is_alive(), "Poll CAM1 no terminó")
        self.assertFalse(t2.is_alive(), "Poll CAM2 no terminó")

        self.assertEqual(proto._cameras.get_zoom(IP1), 25)
        self.assertEqual(proto._cameras.get_zoom(IP2), 75)
        self.assertNotIn(IP1, proto._preset_stop_events)
        self.assertNotIn(IP2, proto._preset_stop_events)


class TestPresetPollExceptionSafety(unittest.TestCase):
    """Escenario 6: excepción en ciclo → try/finally limpia _preset_stop_events."""

    def test_exception_in_cycle_cleans_up(self):
        calls = [0]

        def _query(ip, cam_id):
            calls[0] += 1
            if calls[0] >= 2:
                raise RuntimeError("fallo simulado de red profundo")
            return None, round(0.5 * ZOOM_MAX)

        proto, _ = _make_protocol(_query)
        stop = threading.Event()
        proto._preset_stop_events[IP1] = stop

        t = _run_poll(proto, IP1, CAM_ID1, IP1, 5.0, stop)
        t.join(timeout=2.0)

        self.assertFalse(t.is_alive(), "Poll no terminó tras excepción")
        self.assertNotIn(IP1, proto._preset_stop_events, "Evento no limpiado tras excepción")

    def test_exception_does_not_kill_other_camera_poll(self):
        """Excepción en CAM1 no afecta al poll de CAM2."""
        calls = [0]

        def _query(ip, cam_id):
            if ip == IP1:
                calls[0] += 1
                if calls[0] >= 2:
                    raise RuntimeError("CAM1 fallo")
                return None, None
            return (10, 10), round(0.5 * ZOOM_MAX)  # CAM2 estable

        proto, _ = _make_protocol(_query)

        stop1 = threading.Event()
        stop2 = threading.Event()
        proto._preset_stop_events[IP1] = stop1
        proto._preset_stop_events[IP2] = stop2

        t1 = _run_poll(proto, IP1, CAM_ID1, IP1, 5.0, stop1)
        t2 = _run_poll(proto, IP2, CAM_ID2, IP1, 5.0, stop2)

        t1.join(timeout=2.0)
        t2.join(timeout=3.0)

        self.assertFalse(t1.is_alive(), "Poll CAM1 no terminó")
        self.assertFalse(t2.is_alive(), "Poll CAM2 no terminó")
        self.assertNotIn(IP1, proto._preset_stop_events)
        self.assertNotIn(IP2, proto._preset_stop_events)


class TestRefreshAEActiveIP(unittest.TestCase):
    """Bug B: refresh_ae_mode_async recibe active_ip como parámetro cuando se llama
    desde un thread de background, evitando leer widgets Qt fuera del hilo principal."""

    def test_active_ip_param_skips_get_active_cam(self):
        """Si se pasa active_ip, _active_cam no debe invocarse."""
        proto, _ = _make_protocol()
        # ae_query_try_acquire devuelve True para que el thread se lance
        proto._cameras.ae_query_try_acquire = lambda ip: True
        proto._cameras.ae_query_release     = lambda ip: None

        # _query_ae_and_exp_comp devuelve siempre fallo → thread termina rápido
        proto._query_ae_and_exp_comp = lambda ip, cam_id: ('auto', None)

        get_active_cam_called = [False]
        original = proto._active_cam
        def _spy():
            get_active_cam_called[0] = True
            return original()
        proto._active_cam = _spy

        # Llamar con active_ip explícito → no debe llamar _active_cam
        proto.refresh_ae_mode_async(IP1, CAM_ID1, active_ip=IP1)
        time.sleep(0.2)

        self.assertFalse(get_active_cam_called[0],
                         "_active_cam fue invocado aunque se pasó active_ip explícito")

    def test_active_ip_none_calls_get_active_cam(self):
        """Si no se pasa active_ip (None), sí debe invocar _active_cam."""
        proto, _ = _make_protocol()
        proto._cameras.ae_query_try_acquire = lambda ip: True
        proto._cameras.ae_query_release     = lambda ip: None
        proto._query_ae_and_exp_comp        = lambda ip, cam_id: ('auto', None)

        get_active_cam_called = [False]
        original = proto._active_cam
        def _spy():
            get_active_cam_called[0] = True
            return original()
        proto._active_cam = _spy

        proto.refresh_ae_mode_async(IP1, CAM_ID1)  # sin active_ip
        time.sleep(0.2)

        self.assertTrue(get_active_cam_called[0],
                        "_active_cam no fue invocado cuando active_ip es None")

    def test_poll_loop_passes_active_ip_to_refresh(self):
        """_preset_poll_loop pasa active_ip capturado a refresh_ae_mode_async
        en lugar de dejar que refresh lo capture desde el thread de background."""
        refresh_received_active_ip = [None]

        def _query(ip, cam_id):
            return (100, 50), round(0.5 * ZOOM_MAX)

        proto, _ = _make_protocol(_query, active_ip=IP2)

        original_refresh = proto.refresh_ae_mode_async
        def _spy_refresh(ip, cam_id, active_ip=None):
            refresh_received_active_ip[0] = active_ip
        proto.refresh_ae_mode_async = _spy_refresh

        stop = threading.Event()
        # Pasar active_ip=IP2 al poll: debe llegar a refresh_ae_mode_async
        t = _run_poll(proto, IP1, CAM_ID1, IP2, 3.0, stop)
        t.join(timeout=3.0)

        self.assertEqual(refresh_received_active_ip[0], IP2,
                         f"refresh recibió active_ip={refresh_received_active_ip[0]!r} "
                         f"en lugar de IP2={IP2!r}")


class TestComputePresetCeiling(unittest.TestCase):
    """Verifica que el techo escala correctamente con la reducción de velocidad."""

    def test_ceiling_at_full_speed(self):
        proto, _ = _make_protocol()
        proto._ui_cb.get_pan_cap.return_value = PAN_SPEED_MAX
        ceiling = proto._compute_preset_ceiling()
        expected = min(PRESET_ZOOM_SETTLE_BASE * PRESET_ZOOM_SETTLE_MARGIN, PRESET_ZOOM_SETTLE_MAX)
        self.assertAlmostEqual(ceiling, expected, places=3)

    def test_ceiling_scales_with_halved_speed(self):
        proto, _ = _make_protocol()
        proto._ui_cb.get_pan_cap.return_value = PAN_SPEED_MAX // 2
        ceiling = proto._compute_preset_ceiling()
        expected_unclipped = PRESET_ZOOM_SETTLE_BASE * 2 * PRESET_ZOOM_SETTLE_MARGIN
        expected = min(expected_unclipped, PRESET_ZOOM_SETTLE_MAX)
        self.assertAlmostEqual(ceiling, expected, places=3)

    def test_ceiling_never_exceeds_max(self):
        proto, _ = _make_protocol()
        proto._ui_cb.get_pan_cap.return_value = 1  # velocidad casi cero → techo enorme
        ceiling = proto._compute_preset_ceiling()
        self.assertLessEqual(ceiling, PRESET_ZOOM_SETTLE_MAX)

    def test_ceiling_never_zero_with_cap_zero(self):
        """cap=0 no debe causar ZeroDivisionError (max(...,1) lo evita)."""
        proto, _ = _make_protocol()
        proto._ui_cb.get_pan_cap.return_value = 0
        try:
            ceiling = proto._compute_preset_ceiling()
        except ZeroDivisionError:
            self.fail("_compute_preset_ceiling lanzó ZeroDivisionError con cap=0")
        self.assertGreater(ceiling, 0)


# ─── Runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
