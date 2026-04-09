#!/usr/bin/env python3
# main.py — Punto de entrada de la aplicación

from __future__ import annotations

import sys
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox

from main_window import MainWindow


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN DE LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Punto de entrada principal.

    Todo el flujo Login → Splash → Contenido ocurre dentro de MainWindow.
    """
    try:
        app = QApplication(sys.argv)

        main_win = MainWindow()
        # Para Raspberry Pi, descomentar:
        # main_win.showFullScreen()
        main_win.show()

        logger.info("Application started")
        sys.exit(app.exec_())

    except Exception as exc:
        logger.error(f"Fatal error in main(): {exc}", exc_info=True)
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"Failed to start application:\n{str(exc)}"
        )
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    main()
