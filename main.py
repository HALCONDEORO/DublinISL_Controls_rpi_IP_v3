#!/usr/bin/env python3
# main.py — Punto de entrada de la aplicación con control robusto de flujo

from __future__ import annotations

import sys
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox

from login_screen import LoginScreen
from splash_screen import SplashScreen
from main_window import MainWindow


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN DE LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

# Configurar sistema de logging para registro de eventos
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
    Punto de entrada principal de la aplicación.
    
    Flujo: LoginScreen → SplashScreen → MainWindow
    
    Cada transición incluye manejo de errores y recuperación.
    """
    try:
        # Crear aplicación Qt
        app = QApplication(sys.argv)
        
        # Crear y mostrar pantalla de login
        login = LoginScreen()
        login.show()
        
        # Conectar señal de login exitoso
        login.login_successful.connect(
            lambda: _on_login_successful(app, login)
        )
        
        # Registrar inicio
        logger.info("Application started - waiting for authentication")
        # Ejecutar loop de eventos
        sys.exit(app.exec_())
    
    except Exception as exc:
        # Capturar cualquier error fatal
        logger.error(f"Fatal error in main(): {exc}", exc_info=True)
        # Mostrar diálogo de error
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"Failed to start application:\n{str(exc)}"
        )
        sys.exit(1)


def _on_login_successful(app: QApplication, login: LoginScreen):
    """
    Callback: Login exitoso → mostrar pantalla de splash.
    
    Propósito: Transición limpia a fase de inicialización.
    """
    # Registrar login exitoso
    logger.info("Login successful - starting initialization")
    # Ocultar ventana de login
    login.hide()
    
    try:
        # Crear pantalla de splash
        splash = SplashScreen()
        splash.show()
        
        # Conectar señal de finalización
        splash.startup_complete.connect(
            lambda: _on_startup_complete(app, splash)
        )
    
    except Exception as exc:
        # Error creando splash screen
        logger.error(f"Error creating splash screen: {exc}", exc_info=True)
        # Mostrar diálogo de error
        QMessageBox.critical(
            None,
            "Initialization Error",
            f"Failed to initialize system:\n{str(exc)}"
        )
        app.quit()


def _on_startup_complete(app: QApplication, splash: SplashScreen):
    """
    Callback: Inicialización completa → mostrar ventana principal.
    """
    # Registrar finalización
    logger.info("Initialization complete - opening main window")
    # Ocultar splash screen
    splash.hide()
    
    try:
        # Crear ventana principal (crea sus propios CameraWorkers internamente)
        main_win = MainWindow()
        
        # Para Raspberry Pi, descomentar:
        # main_win.showFullScreen()
        # Para desarrollo:
        main_win.show()
        
        # Registrar éxito
        logger.info("Main window opened successfully")
    
    except Exception as exc:
        # Error abriendo ventana principal
        logger.error(f"Error opening main window: {exc}", exc_info=True)
        # Mostrar diálogo de error
        QMessageBox.critical(
            None,
            "Error",
            f"Failed to open main window:\n{str(exc)}"
        )
        app.quit()


# ═══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    main()