#!/usr/bin/env python3
# widgets.py — Widgets personalizados de la UI
#
# Responsabilidad única: definir componentes visuales reutilizables
# que no contienen lógica de negocio (no saben nada de VISCA ni de presets).
#
# MOTIVO DE SEPARACIÓN: GoButton y _arrow_btn se instancian muchas veces
# en main_window.py.  Mantenerlos aquí permite cambiar su aspecto sin
# tocar la ventana principal, y hace main_window.py más legible.

import os
from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from config import BUTTON_COLOR


class GoButton(QPushButton):
    """
    Botón de asiento numerado (70×82 px).

    Muestra seat.svg como fondo mediante background-image en el stylesheet.
    El número del asiento se dibuja encima del SVG por Qt de forma nativa.

    IMPORTANTE: GoButton sobreescribe cualquier setStyleSheet() posterior
    porque su estilo se aplica en __init__.  Por eso los botones de plataforma
    (Chairman/Left/Right) usan QPushButton plano, no GoButton.

    Estado :pressed aplica una capa rgba semitransparente para feedback táctil
    sin ocultar la imagen de fondo.
    """

    WIDTH  = 70
    HEIGHT = 82

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.resize(self.WIDTH, self.HEIGHT)

        # Intentar cargar el SVG; si no existe, degradar a fondo sólido
        # para evitar que la app crashee solo por un asset faltante.
        if os.path.exists("seat.svg"):
            bg_image = "background-image: url(seat.svg);"
        else:
            print("[WARNING] seat.svg no encontrado — usando fondo de color")
            bg_image = "background-color: #cccccc;"

        self.setStyleSheet(
            "QPushButton {"
            f"  {bg_image}"
            "  background-repeat: no-repeat;"
            "  background-position: center;"
            "  border: none;"
            "  font: 11px; font-weight: bold;"
            f"  color: {BUTTON_COLOR};"
            "}"
            # Feedback visual al pulsar: capa oscura semitransparente
            "QPushButton:pressed {"
            "  background-color: rgba(0, 0, 0, 70);"
            "}"
        )


def make_arrow_btn(parent, x: int, y: int, degrees: int) -> QPushButton:
    """
    Crea un QPushButton con angle.png rotado a los grados indicados.

    BASELINE: angle.png apunta hacia ABAJO (0°).  La rotación se aplica
    en sentido horario, por lo que:
        0°   → Abajo
        90°  → Izquierda
        180° → Arriba
        270° → Derecha

    Si angle.png no existe, el botón queda vacío pero funcional,
    para que la app arranque aunque falten assets.

    MOTIVO de helper independiente: se llama 8 veces en main_window.py.
    Centralizar la creación evita duplicar la lógica de carga y rotación
    del pixmap.
    """
    btn = QPushButton(parent)
    btn.setGeometry(x, y, 100, 100)
    btn.setStyleSheet("border: none; background: transparent")

    if os.path.exists("angle.png"):
        pix = QPixmap("angle.png").transformed(
            QtGui.QTransform().rotate(degrees), Qt.SmoothTransformation
        )
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(90, 90))
    else:
        print(f"[WARNING] angle.png no encontrado — botón de dirección {degrees}° sin icono")

    return btn
