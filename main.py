#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
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
import logging.handlers
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMessageBox

from data_paths import migrate_legacy_files
from main_window import MainWindow
from power_management import disable_screen_blanking
from virtual_keyboard import install_virtual_keyboard
import sim_mode as _sim_mode

# def _setup_logging():
#     Path("logs").mkdir(exist_ok=True)
#     root = logging.getLogger()
#     root.setLevel(logging.INFO)
#
#     console = logging.StreamHandler()
#     console.setFormatter(logging.Formatter('[%(levelname)s] %(name)s: %(message)s'))
#
#     file_handler = logging.handlers.RotatingFileHandler(
#         "logs/app.log",
#         maxBytes=5 * 1024 * 1024,  # 5 MB por fichero
#         backupCount=5,
#         encoding="utf-8",
#     )
#     file_handler.setFormatter(logging.Formatter(
#         '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
#         datefmt='%Y-%m-%d %H:%M:%S',
#     ))
#
#     root.addHandler(console)
#     root.addHandler(file_handler)
#
# _setup_logging()
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    migrate_legacy_files()
    disable_screen_blanking()
    try:
        app = QApplication(sys.argv)
        install_virtual_keyboard(app)

        main_win = MainWindow()
        if _sim_mode.is_active():
            main_win.show()
        else:
            main_win.showFullScreen()

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
