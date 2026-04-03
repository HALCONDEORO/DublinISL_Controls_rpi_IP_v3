#!/usr/bin/env python3
# main.py — Entry point de la aplicación
#
# Responsabilidad única: inicializar QApplication y lanzar MainWindow.
# No contiene lógica de negocio ni de UI.
#
# EJECUCIÓN:
#   python3 main.py
#
# Para producción en Raspberry Pi con pantalla táctil,
# descomentar showFullScreen() y comentar show().

import sys
from PyQt5.QtWidgets import QApplication
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()

    # Desarrollo / escritorio:
    window.show()

    # Producción en Raspberry Pi (pantalla táctil, sin decoración de ventana):
    # window.showFullScreen()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
