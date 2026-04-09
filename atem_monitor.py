#!/usr/bin/env python3
# atem_monitor.py — Monitor de programa del switcher BlackMagic ATEM
#
# Corre en un hilo daemon y emite switched_to_input1 cuando el ATEM
# cambia su salida de programa de Input 2 → Input 1.
# Si el ATEM no es alcanzable, falla silenciosamente sin afectar la app.

from __future__ import annotations

import logging
import time

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ATEMMonitor(QThread):
    """
    Hilo daemon que monitoriza el programa del ATEM vía Ethernet (TCP 9910).
    Emite switched_to_input1 cuando el programa pasa de Input 2 → Input 1.
    """

    switched_to_input1 = pyqtSignal()

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self._ip = ip
        self.setDaemon(True)

    def run(self):
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
                    logger.info("ATEM: canal 3→2 — enviando Comments a Home")
                    self.switched_to_input1.emit()
                prev_input = cur
            except Exception as exc:
                logger.warning("ATEM poll error: %s", exc)
            time.sleep(0.1)
