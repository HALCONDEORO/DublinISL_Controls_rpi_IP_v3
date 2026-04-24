#!/usr/bin/env python3
# main.py — Punto de entrada de la aplicación
#
# Wire-up mínimo: todo el estado, servicios y controller se instancian
# dentro de MainWindow.__init__ para mantener el arranque simple y testeable.
#
# Flujo completo: Login → Splash → MainWindow (ready)
#   MainWindow construye:
#     SystemState, AsyncEventBus, PresetService, CameraService,
#     SessionService, Controller, ViscaController (Qt layer)

from __future__ import annotations

import sys
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox

from data_paths import migrate_legacy_files
from main_window import MainWindow
from virtual_keyboard import install_virtual_keyboard

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    migrate_legacy_files()
    try:
        app = QApplication(sys.argv)
        install_virtual_keyboard(app)

        main_win = MainWindow()
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


if __name__ == '__main__':
    main()
