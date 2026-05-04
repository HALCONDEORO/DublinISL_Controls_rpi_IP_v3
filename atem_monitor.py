#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# atem_monitor.py — Monitor de programa del switcher BlackMagic ATEM
#
# Corre en un hilo daemon y emite program_changed(int) con el input de programa
# activo cada vez que cambia. Emite state_changed(ATEMState) en cada transición.
# La lógica de qué acción tomar con cada input vive en ATEMDispatcher.
#
# POLÍTICA DE REINTENTOS:
#   Tras fallo de conexión realiza hasta len(_BACKOFFS) reintentos adicionales
#   con espera creciente. Si todos fallan emite DISCONNECTED y termina.
#   El hilo puede interrumpirse en cualquier momento (requestInterruption).
#
# MODO SIMULACIÓN:
#   Se activa automáticamente cuando sim_ip_backup.json existe.
#   En ese modo escucha hardware_simulator.atem_event_queue en lugar de
#   conectar al hardware real. El evento se dispara desde config_dialog.py
#   al pulsar "Run Test" (punto ATEM, el 7º indicador).

from __future__ import annotations

import logging
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from atem_state import ATEMState
from config import is_valid_ip

logger = logging.getLogger(__name__)

_SIM_FLAG = Path("sim_ip_backup.json")

# Segundos de espera entre reintentos de conexión (intento inicial + 3 reintentos).
_BACKOFFS: tuple[int, ...] = (2, 5, 15)


class ATEMMonitor(QThread):
    """
    Hilo daemon que monitoriza el programa del ATEM vía Ethernet (TCP 9910).
    Emite program_changed(int) con el input activo cada vez que cambia.
    Emite state_changed(ATEMState) en cada transición de estado relevante.

    Tras fallo de conexión reintenta con backoff creciente (_BACKOFFS).
    El hilo puede interrumpirse limpiamente en cualquier punto de espera.

    En modo simulación (sim_ip_backup.json presente) escucha la cola de
    hardware_simulator en lugar de conectar al hardware real.
    """

    program_changed = pyqtSignal(int)     # input de programa actual al cambiar
    state_changed   = pyqtSignal(object)  # ATEMState

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self._ip = ip.strip() if ip else ""
        self._state: ATEMState | None = None

    @property
    def state(self) -> ATEMState | None:
        return self._state

    def _emit_state(self, state: ATEMState) -> None:
        self._state = state
        self.state_changed.emit(state)

    # ── Punto de entrada del hilo ─────────────────────────────────────────────

    def run(self):
        if _SIM_FLAG.exists():
            self._run_simulated()
            return

        if not self._ip:
            logger.info("ATEM: IP no configurada — monitorización desactivada")
            self._emit_state(ATEMState.NOT_CONFIGURED)
            return

        if not is_valid_ip(self._ip):
            logger.warning("ATEM: IP inválida '%s' — monitorización desactivada", self._ip)
            self._emit_state(ATEMState.NOT_CONFIGURED)
            return

        try:
            import PyATEMMax
        except ImportError:
            logger.warning("PyATEMMax no instalado — monitorización ATEM desactivada")
            self._emit_state(ATEMState.DEPENDENCY_MISSING)
            return

        self._run_with_retry(PyATEMMax)

    # ── Ciclo de conexión con reintentos ──────────────────────────────────────

    def _run_with_retry(self, PyATEMMax) -> None:
        max_attempts = 1 + len(_BACKOFFS)

        for attempt in range(1, max_attempts + 1):
            if self.isInterruptionRequested():
                return

            self._emit_state(ATEMState.CONNECTING)
            atem = PyATEMMax.ATEMMax()
            connected = False

            try:
                atem.connect(self._ip)
                if atem.waitForConnection(timeout=10):
                    connected = True
                else:
                    logger.warning(
                        "ATEM no responde en %s (intento %d/%d)",
                        self._ip, attempt, max_attempts,
                    )
            except Exception as exc:
                logger.warning(
                    "Error conectando al ATEM %s (intento %d/%d): %s",
                    self._ip, attempt, max_attempts, exc,
                )

            if connected:
                logger.info("ATEM conectado en %s (intento %d)", self._ip, attempt)
                self._emit_state(ATEMState.CONNECTED)
                try:
                    self._poll_loop(atem)
                finally:
                    self._close_atem(atem)
                return

            self._close_atem(atem)

            if self.isInterruptionRequested():
                return

            # Última tentativa fallida → DISCONNECTED
            if attempt == max_attempts:
                logger.warning(
                    "ATEM: todos los intentos agotados (%d/%d) — marcando DISCONNECTED",
                    attempt, max_attempts,
                )
                self._emit_state(ATEMState.DISCONNECTED)
                return

            # Espera con backoff antes del siguiente intento
            backoff = _BACKOFFS[attempt - 1]
            logger.info(
                "ATEM: reintentando en %ds (intento %d/%d completado)",
                backoff, attempt, max_attempts,
            )
            self._emit_state(ATEMState.RECONNECTING)
            if self._wait_interruptible(backoff):
                return  # hilo interrumpido durante la espera

    def _close_atem(self, atem) -> None:
        """Cierra recursos del cliente ATEM si la librería expone un método compatible."""
        for method_name in ("disconnect", "close", "stop"):
            method = getattr(atem, method_name, None)
            if not callable(method):
                continue
            try:
                method()
            except Exception as exc:
                logger.debug("ATEM: error cerrando cliente con %s(): %s", method_name, exc)
            return

    # ── Bucle de polling del programa ─────────────────────────────────────────

    def _poll_loop(self, atem) -> None:
        prev_input = None
        while not self.isInterruptionRequested():
            try:
                cur = int(atem.programInput[0].videoSource)
                if self._state == ATEMState.ERROR:
                    self._emit_state(ATEMState.CONNECTED)
                if cur != prev_input:
                    self.program_changed.emit(cur)
                prev_input = cur
            except Exception as exc:
                logger.warning("ATEM poll error: %s", exc)
                if self._state != ATEMState.ERROR:
                    self._emit_state(ATEMState.ERROR)
            time.sleep(0.1)

    # ── Espera interrumpible ──────────────────────────────────────────────────

    def _wait_interruptible(self, seconds: float) -> bool:
        """Espera hasta `seconds` comprobando interrupción cada 0.2s.

        Devuelve True si el hilo fue interrumpido antes de que terminara la espera.
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.isInterruptionRequested():
                return True
            time.sleep(0.2)
        return False

    # ── Modo simulación ───────────────────────────────────────────────────────

    def _run_simulated(self):
        """Escucha hardware_simulator.atem_event_queue y emite la señal al recibirla."""
        import queue as _queue
        import hardware_simulator as _hw

        logger.info("ATEMMonitor: modo simulacion activo")
        self._emit_state(ATEMState.CONNECTED)

        while not self.isInterruptionRequested():
            try:
                event = _hw.atem_event_queue.get(timeout=0.5)
                if event == "switch_to_input2":
                    logger.info("ATEM sim: evento Input 3->2 recibido")
                    self.program_changed.emit(2)
                elif event == "switch_to_input3":
                    logger.info("ATEM sim: evento Input 2->3 recibido")
                    self.program_changed.emit(3)
            except _queue.Empty:
                pass
