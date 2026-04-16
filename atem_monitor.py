#!/usr/bin/env python3
# atem_monitor.py — Monitor de programa del switcher BlackMagic ATEM
#
# Corre en un hilo daemon y emite switched_to_input2 cuando el ATEM
# cambia su salida de programa de Input 3 → Input 2.
# Si el ATEM no es alcanzable, falla silenciosamente sin afectar la app.
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

logger = logging.getLogger(__name__)

_SIM_FLAG = Path("sim_ip_backup.json")


class ATEMMonitor(QThread):
    """
    Hilo daemon que monitoriza el programa del ATEM vía Ethernet (TCP 9910).
    Emite switched_to_input2 cuando el programa pasa de Input 3 → Input 2.

    En modo simulación (sim_ip_backup.json presente) escucha la cola de
    hardware_simulator en lugar de conectar al hardware real.
    """

    switched_to_input2 = pyqtSignal()

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self._ip = ip

    def run(self):
        if _SIM_FLAG.exists():
            self._run_simulated()
            return

        try:
            import PyATEMMax
        except ImportError:
            logger.warning("PyATEMMax no instalado — monitorización ATEM desactivada")
            return

        atem = PyATEMMax.ATEMMax()
        try:
            atem.connect(self._ip)
            if not atem.waitForConnection(timeout=10):
                logger.warning("ATEM no responde en %s — monitorización desactivada", self._ip)
                return
        except Exception as exc:
            logger.warning("Error conectando al ATEM (%s): %s", self._ip, exc)
            return

        logger.info("ATEM conectado en %s", self._ip)
        prev_input = None

        while not self.isInterruptionRequested():
            try:
                cur = int(atem.programInput[0].videoSource)
                if prev_input == 3 and cur == 2:
                    logger.info("ATEM: canal 3->2 — enviando Comments a Home")
                    self.switched_to_input2.emit()
                prev_input = cur
            except Exception as exc:
                logger.warning("ATEM poll error: %s", exc)
            time.sleep(0.1)

    def _run_simulated(self):
        """Escucha hardware_simulator.atem_event_queue y emite la señal al recibirla."""
        import queue as _queue
        import hardware_simulator as _hw

        logger.info("ATEMMonitor: modo simulacion activo")

        while not self.isInterruptionRequested():
            try:
                event = _hw.atem_event_queue.get(timeout=0.5)
                if event == "switch_to_input2":
                    logger.info("ATEM sim: evento Input 3->2 recibido")
                    self.switched_to_input2.emit()
            except _queue.Empty:
                pass
