#!/usr/bin/env python3
# auditorium_overlay.py — Overlay semitransparente del panel izquierdo
#
# Dos modos visuales:
#   'set'  → relleno blanco semitransparente (más claro)
#   'call' → pequeños puntos blancos sobre fondo transparente

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QPainter, QBrush
from PyQt5.QtWidgets import QWidget


class AuditoriumOverlay(QWidget):
    """
    Widget transparente que cubre todo el panel izquierdo (0,0 → 1490,1080).
    Siempre visible; cambia su apariencia según el modo activo.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._mode = 'call'
        self.setGeometry(0, 0, 1490, 1080)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_mode(self, mode: str):
        """'call' → puntos blancos  |  'set' → relleno blanco claro"""
        self._mode = mode
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._mode == 'set':
            # Relleno semitransparente blanco — un poco más claro que antes
            painter.fillRect(self.rect(), QColor(255, 255, 255, 55))

        else:
            # Pequeños puntos blancos distribuidos en cuadrícula
            dot_r   = 2       # radio del punto en px
            spacing = 24      # separación entre centros de puntos
            color   = QColor(255, 255, 255, 55)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))

            x = spacing // 2
            while x < self.width():
                y = spacing // 2
                while y < self.height():
                    painter.drawEllipse(QPointF(x, y), dot_r, dot_r)
                    y += spacing
                x += spacing

        painter.end()
