#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# tests/test_atem_reconnect.py — Tests para issue #173: reintentos y reconexión ATEM

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QCoreApplication, Qt

if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from atem_state import ATEMState


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_mock_pyatemmax(*, connect_ok: bool = False, wait_ok: bool = False):
    """Construye un mock de PyATEMMax que falla o tiene éxito según los parámetros."""
    instance = MagicMock()
    instance.waitForConnection.return_value = wait_ok
    if not connect_ok:
        instance.connect.side_effect = OSError("Connection refused") if not connect_ok else None
    mock_module = MagicMock()
    mock_module.ATEMMax.return_value = instance
    return mock_module, instance


class _ProgramInputSequence:
    def __init__(self, monitor, sources):
        self._monitor = monitor
        self._sources = list(sources)
        self._index = 0

    def __getitem__(self, index):
        if self._index >= len(self._sources):
            self._monitor.requestInterruption()
            source = self._sources[-1]
        else:
            source = self._sources[self._index]
        self._index += 1
        item = MagicMock()
        item.videoSource = source
        return item


def _collect_states(monitor, timeout_ms: int = 5000) -> list[ATEMState]:
    """Ejecuta el monitor con DirectConnection y recoge estados emitidos."""
    import atem_monitor as _am

    states: list[ATEMState] = []
    monitor.state_changed.connect(states.append, Qt.DirectConnection)

    original_flag = _am._SIM_FLAG
    _am._SIM_FLAG = Path("__nonexistent_sim_flag_for_tests__")
    try:
        monitor.start()
        monitor.wait(timeout_ms)
    finally:
        _am._SIM_FLAG = original_flag
        if monitor.isRunning():
            monitor.requestInterruption()
            monitor.wait(2000)
    return states


# ─── Política de reintentos ───────────────────────────────────────────────────

class TestRetryPolicy:
    def test_retry_count_bounded(self):
        """El monitor no debe reintentar más de len(_BACKOFFS) veces."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None  # connect no lanza; waitForConnection False

        expected_attempts = 1 + len(_am._BACKOFFS)

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert mock_module.ATEMMax.call_count == expected_attempts, (
            f"Esperados {expected_attempts} intentos, got {mock_module.ATEMMax.call_count}"
        )

    def test_failed_attempts_close_atem_client(self):
        """Cada intento fallido debe cerrar el cliente ATEM creado."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None
        expected_attempts = 1 + len(_am._BACKOFFS)

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            _collect_states(monitor, timeout_ms=5000)

        assert instance.disconnect.call_count == expected_attempts

    def test_emits_disconnected_after_all_retries(self):
        """Tras agotar todos los reintentos el estado final debe ser DISCONNECTED."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert ATEMState.DISCONNECTED in states, f"Estados: {states}"
        assert states[-1] == ATEMState.DISCONNECTED, f"Último estado debe ser DISCONNECTED: {states}"

    def test_emits_reconnecting_between_attempts(self):
        """Entre intentos fallidos debe emitirse RECONNECTING."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert ATEMState.RECONNECTING in states, f"Estados: {states}"
        # Exactamente len(_BACKOFFS) emisiones de RECONNECTING
        reconnecting_count = states.count(ATEMState.RECONNECTING)
        assert reconnecting_count == len(_am._BACKOFFS), (
            f"Esperados {len(_am._BACKOFFS)} RECONNECTING, got {reconnecting_count}"
        )

    def test_emits_connecting_on_each_attempt(self):
        """Cada intento (inicial + reintentos) debe emitir CONNECTING primero."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None
        expected_attempts = 1 + len(_am._BACKOFFS)

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        connecting_count = states.count(ATEMState.CONNECTING)
        assert connecting_count == expected_attempts, (
            f"Esperados {expected_attempts} CONNECTING, got {connecting_count}"
        )

    def test_no_retry_on_success(self):
        """Si el primer intento tiene éxito no debe haber RECONNECTING."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=True)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}):
            monitor = ATEMMonitor("192.168.1.1")
            instance.programInput = _ProgramInputSequence(monitor, [3])
            states = _collect_states(monitor, timeout_ms=3000)

        assert mock_module.ATEMMax.call_count == 1
        assert ATEMState.CONNECTED in states
        assert ATEMState.RECONNECTING not in states
        instance.disconnect.assert_called_once_with()

    def test_poll_recovery_restores_connected_after_error(self):
        """Un poll correcto después de ERROR debe restaurar CONNECTED."""
        from atem_monitor import ATEMMonitor

        class _ProgramInput:
            def __init__(self):
                self.calls = 0

            def __getitem__(self, index):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary")
                if self.calls == 3:
                    monitor.requestInterruption()
                item = MagicMock()
                item.videoSource = 3
                return item

        monitor = ATEMMonitor("192.168.1.1")
        atem = MagicMock()
        atem.programInput = _ProgramInput()
        states = []
        monitor.state_changed.connect(states.append, Qt.DirectConnection)
        monitor._emit_state(ATEMState.CONNECTED)

        with patch.object(monitor, "isInterruptionRequested",
                          side_effect=[False, False, True]):
            monitor._poll_loop(atem)

        assert states == [
            ATEMState.CONNECTED,
            ATEMState.ERROR,
            ATEMState.CONNECTED,
        ]

    def test_interruption_during_backoff_stops_retries(self):
        """Interrumpir durante el backoff debe detener los reintentos limpiamente."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None
        # _wait_interruptible devuelve True = fue interrumpido
        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=True):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=3000)

        # Solo debe haber un intento (el primero) + ningún RECONNECTING procesado
        assert mock_module.ATEMMax.call_count == 1, (
            f"Interrumpido en el primer backoff: esperado 1 intento, got {mock_module.ATEMMax.call_count}"
        )
        instance.disconnect.assert_called_once_with()


# ─── Espera interrumpible ─────────────────────────────────────────────────────

class TestWaitInterruptible:
    def test_returns_false_when_wait_completes(self):
        """Espera corta sin interrupción → devuelve False."""
        from atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("")
        result = monitor._wait_interruptible(0.05)
        assert result is False

    def test_interruption_exits_retry_loop_early(self):
        """Interrupción durante backoff causa salida anticipada del bucle de reintentos.

        Verifica que el monitor se detiene antes de completar todos los reintentos cuando
        se interrumpe dentro del QThread (comportamiento real de producción).
        """
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        interrupted_at = []

        def _fake_wait(self, seconds):
            interrupted_at.append(seconds)
            return True  # simula interrupción en el primer backoff

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", _fake_wait):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=3000)

        # Solo el primer backoff debe haberse ejecutado antes de la interrupción
        assert len(interrupted_at) == 1, f"Solo debe haber un backoff antes de la interrupción: {interrupted_at}"
        # El hilo no debe emitir DISCONNECTED (salió limpiamente por interrupción)
        assert ATEMState.DISCONNECTED not in states, f"No debe emitirse DISCONNECTED por interrupción: {states}"

    def test_close_atem_ignores_close_errors(self):
        from atem_monitor import ATEMMonitor

        atem = MagicMock()
        atem.disconnect.side_effect = RuntimeError("already closed")

        ATEMMonitor("")._close_atem(atem)

        atem.disconnect.assert_called_once_with()

    def test_close_atem_uses_close_when_disconnect_missing(self):
        from atem_monitor import ATEMMonitor

        class _Atem:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        atem = _Atem()

        ATEMMonitor("")._close_atem(atem)

        assert atem.closed is True

    def test_close_atem_accepts_client_without_close_method(self):
        from atem_monitor import ATEMMonitor

        ATEMMonitor("")._close_atem(object())


# ─── Escenario de reconexión manual ──────────────────────────────────────────

class TestManualReconnect:
    def test_second_monitor_starts_after_first_disconnected(self):
        """Simula reconexión: primer monitor falla → DISCONNECTED → nuevo monitor → éxito."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        # Primera ronda: siempre falla
        mock_fail, instance_fail = _make_mock_pyatemmax(wait_ok=False)
        instance_fail.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_fail}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            mon1 = ATEMMonitor("192.168.1.1")
            states1 = _collect_states(mon1, timeout_ms=5000)

        assert ATEMState.DISCONNECTED in states1
        assert not mon1.isRunning()

        # Segunda ronda: tiene éxito (simula reconexión manual)
        mock_ok, instance_ok = _make_mock_pyatemmax(wait_ok=True)
        instance_ok.connect.side_effect = None
        instance_ok.programInput = MagicMock(side_effect=Exception("exit poll"))

        with patch.dict(sys.modules, {"PyATEMMax": mock_ok}):
            mon2 = ATEMMonitor("192.168.1.1")
            states2 = _collect_states(mon2, timeout_ms=3000)

        assert ATEMState.CONNECTED in states2

    def test_reconnect_does_not_emit_connected_when_still_failing(self):
        """Tras reconexión que también falla, el nuevo monitor emite DISCONNECTED (no CONNECTED)."""
        import atem_monitor as _am
        from atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert ATEMState.CONNECTED not in states
        assert ATEMState.DISCONNECTED in states


# ─── Backoffs configurados son razonables ────────────────────────────────────

class TestATEMSupervisorHealth:
    def test_terminal_expected_states_are_healthy(self):
        from atem_state import is_atem_supervisor_healthy

        for state in (
            ATEMState.NOT_CONFIGURED,
            ATEMState.DEPENDENCY_MISSING,
            ATEMState.DISCONNECTED,
        ):
            assert is_atem_supervisor_healthy(
                is_running=False,
                restart_pending=False,
                state=state,
            ) is True

    def test_stopped_error_state_is_unhealthy(self):
        from atem_state import is_atem_supervisor_healthy

        assert is_atem_supervisor_healthy(
            is_running=False,
            restart_pending=False,
            state=ATEMState.ERROR,
        ) is False


class TestBackoffConstants:
    def test_backoffs_are_positive_and_increasing(self):
        from atem_monitor import _BACKOFFS
        assert all(b > 0 for b in _BACKOFFS), "Todos los backoffs deben ser positivos"
        assert list(_BACKOFFS) == sorted(_BACKOFFS), "Los backoffs deben ser crecientes"

    def test_at_least_two_retries(self):
        from atem_monitor import _BACKOFFS
        assert len(_BACKOFFS) >= 2, "Debe haber al menos 2 reintentos (3 intentos totales)"
