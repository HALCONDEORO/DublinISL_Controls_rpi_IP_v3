#!/usr/bin/env python3
# atem_monitor.py — Monitor de programa del switcher BlackMagic ATEM
#
# Corre en un hilo y emite switched_to_input2 cuando el ATEM cambia
# su salida de programa de Input 3 → Input 2.
# Se reconecta automáticamente si el ATEM se reinicia o pierde red.
# Si PyATEMMax no está instalado, falla silenciosamente.

from __future__ import annotations

import logging
import time

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

_POLL_INTERVAL   = 0.1  # segundos entre lecturas del programa
_RECONNECT_WAIT  = 5    # segundos entre intentos de reconexión
_ERROR_THRESHOLD = 10   # errores consecutivos antes de forzar reconexión


class ATEMMonitor(QThread):
    """
    Hilo que monitoriza el programa del ATEM vía Ethernet (TCP 9910).
    Emite switched_to_input2 cuando el programa pasa de Input 3 → Input 2.
    Se reconecta automáticamente si el ATEM se reinicia o pierde red.

    Ciclo de vida:
      - start()  → llamado desde MainWindow.__init__
      - requestInterruption() + wait() → llamado desde MainWindow.closeEvent
    """

    switched_to_input2 = pyqtSignal()

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self._ip = ip

    def run(self):
        try:
            import PyATEMMax
        except ImportError:
            logger.warning("PyATEMMax no instalado — monitorización ATEM desactivada")
            return

        while not self.isInterruptionRequested():
            atem = PyATEMMax.ATEMMax()
            try:
                atem.connect(self._ip)
                if not atem.waitForConnection(timeout=10):
                    logger.warning("ATEM no responde en %s — reintentando en %ds",
                                   self._ip, _RECONNECT_WAIT)
                    self._sleep_interruptible(_RECONNECT_WAIT)
                    continue
            except Exception as exc:
                logger.warning("Error conectando al ATEM (%s): %s — reintentando en %ds",
                               self._ip, exc, _RECONNECT_WAIT)
                self._sleep_interruptible(_RECONNECT_WAIT)
                continue

            logger.info("ATEM conectado en %s", self._ip)
            self._poll_loop(atem)

    def _poll_loop(self, atem) -> None:
        """
        Bucle interno de lectura del programa del ATEM.
        Sale al detectar demasiados errores consecutivos (señal de desconexión)
        o cuando el hilo recibe requestInterruption().

        Nota: programInput[0] = M/E 1 (primer Mix Effect, índice 0 en PyATEMMax).
        """
        prev_input = None
        consecutive_errors = 0

        while not self.isInterruptionRequested():
            try:
                vs = atem.programInput[0].videoSource
                if vs is None:
                    raise ValueError("videoSource es None")
                cur = int(vs)
                consecutive_errors = 0

                if prev_input == 3 and cur == 2:
                    logger.info("ATEM: canal 3→2 — enviando Comments a Home")
                    self.switched_to_input2.emit()
                prev_input = cur

            except Exception as exc:
                consecutive_errors += 1
                logger.warning("ATEM poll error (%d/%d): %s",
                               consecutive_errors, _ERROR_THRESHOLD, exc)
                if consecutive_errors >= _ERROR_THRESHOLD:
                    logger.warning("ATEM: demasiados errores — reconectando")
                    return

            time.sleep(_POLL_INTERVAL)

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep en tramos cortos para responder rápido a requestInterruption()."""
        end = time.monotonic() + seconds
        while not self.isInterruptionRequested() and time.monotonic() < end:
            time.sleep(0.2)
