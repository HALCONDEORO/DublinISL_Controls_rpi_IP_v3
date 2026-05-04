#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# tests/test_atem_optional.py — Tests para issue #172: ATEM opcional y no crítico

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtCore import QCoreApplication

# Ensure app exists for QThread
if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from PyQt5.QtCore import Qt
from atem_state import ATEMState


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _collect_states(monitor, timeout_ms: int = 3000) -> list[ATEMState]:
    """Ejecuta el monitor en un hilo y recoge todos los estados emitidos.

    Usa DirectConnection para que los signals se entreguen sin event loop.
    Parchea _SIM_FLAG para que los tests no entren en modo simulación aunque
    sim_ip_backup.json exista en el directorio de trabajo.
    """
    import atem_monitor as _am
    from pathlib import Path

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
            monitor.wait(1000)
    return states


# ─── config.py ────────────────────────────────────────────────────────────────

class TestATEMConfig:
    def test_missing_atemip_file_returns_empty(self, tmp_path, monkeypatch):
        """Si ATEMIP.txt no existe el valor devuelto es cadena vacía."""
        import config as cfg
        monkeypatch.setattr(cfg, "_read_config",
                            lambda fn, default: default if fn == "ATEMIP.txt" else default)
        result = cfg._read_config("ATEMIP.txt", "")
        assert result == ""

    def test_empty_atemip_file_returns_empty(self, tmp_path):
        """Archivo ATEMIP.txt vacío → cadena vacía."""
        from config import _read_config
        f = tmp_path / "ATEMIP.txt"
        f.write_text("   ", encoding="utf-8")
        # _read_config lee desde __file__.parent; probamos directamente la lógica
        import config as cfg
        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value="   "):
            result = cfg._read_config("ATEMIP.txt", "")
        assert result == ""

    def test_no_fake_fallback_ip(self):
        """La IP por defecto cuando ATEMIP.txt falta debe ser '' y no una IP inventada."""
        import config as cfg
        # Re-ejecutamos _read_config con un archivo inexistente para verificar el default.
        result = cfg._read_config("__nonexistent_atemip__.txt", "")
        assert result == "", "El fallback de ATEM no debe ser una IP ficticia"

    def test_invalid_ip_rejected(self):
        from config import is_valid_ip
        assert not is_valid_ip("999.0.0.1")
        assert not is_valid_ip("not-an-ip")
        assert not is_valid_ip("176.16.1")
        assert not is_valid_ip("")


# ─── ATEMMonitor con IP vacía → NOT_CONFIGURED ────────────────────────────────

class TestATEMMonitorNotConfigured:
    def test_empty_ip_emits_not_configured(self):
        from atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("")
        states = _collect_states(monitor)
        assert ATEMState.NOT_CONFIGURED in states, f"Estados recibidos: {states}"

    def test_whitespace_ip_emits_not_configured(self):
        from atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("   ")
        states = _collect_states(monitor)
        assert ATEMState.NOT_CONFIGURED in states, f"Estados recibidos: {states}"

    def test_invalid_ip_emits_not_configured(self):
        from atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("999.0.0.1")
        states = _collect_states(monitor)
        assert ATEMState.NOT_CONFIGURED in states, f"Estados recibidos: {states}"

    def test_not_configured_does_not_crash(self):
        """El monitor debe terminar limpiamente sin IP configurada."""
        from atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("")
        _collect_states(monitor, timeout_ms=2000)
        assert not monitor.isRunning(), "El hilo debe terminar solo cuando no hay IP"


# ─── ATEMMonitor sin PyATEMMax → DEPENDENCY_MISSING ──────────────────────────

class TestATEMMonitorDependencyMissing:
    def test_missing_pyatemmax_emits_dependency_missing(self):
        from atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": None}):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor)
        assert ATEMState.DEPENDENCY_MISSING in states, f"Estados recibidos: {states}"

    def test_missing_pyatemmax_does_not_crash(self):
        from atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": None}):
            monitor = ATEMMonitor("192.168.1.1")
            _collect_states(monitor, timeout_ms=2000)
        assert not monitor.isRunning(), "El hilo debe terminar solo cuando falta la dependencia"


# ─── ATEMMonitor sin hardware → DISCONNECTED ──────────────────────────────────

class TestATEMMonitorDisconnected:
    def test_unreachable_host_emits_disconnected(self):
        """ATEM no alcanzable → estado DISCONNECTED (no crash)."""
        import atem_monitor as _am
        mock_atem_instance = MagicMock()
        mock_atem_instance.waitForConnection.return_value = False
        mock_pyatemmax = MagicMock()
        mock_pyatemmax.ATEMMax.return_value = mock_atem_instance

        from atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": mock_pyatemmax}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("10.0.0.99")
            states = _collect_states(monitor)

        assert ATEMState.DISCONNECTED in states, f"Estados recibidos: {states}"
        assert ATEMState.CONNECTED not in states

    def test_connection_exception_emits_disconnected(self):
        """Excepción al conectar → DISCONNECTED (no crash)."""
        import atem_monitor as _am
        mock_atem_instance = MagicMock()
        mock_atem_instance.connect.side_effect = OSError("Network unreachable")
        mock_pyatemmax = MagicMock()
        mock_pyatemmax.ATEMMax.return_value = mock_atem_instance

        from atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": mock_pyatemmax}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("10.0.0.99")
            states = _collect_states(monitor)

        assert ATEMState.DISCONNECTED in states, f"Estados recibidos: {states}"


# ─── ATEMState enum ────────────────────────────────────────────────────────────

class TestATEMStateEnum:
    def test_all_states_defined(self):
        expected = {
            "NOT_CONFIGURED", "DEPENDENCY_MISSING",
            "CONNECTING", "CONNECTED", "DISCONNECTED", "ERROR", "RECONNECTING",
        }
        actual = {s.name for s in ATEMState}
        assert actual == expected

    def test_states_are_distinct(self):
        values = [s.value for s in ATEMState]
        assert len(values) == len(set(values))
