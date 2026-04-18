#!/usr/bin/env python3
# auditorium_overlay.py — Overlay semitransparente del panel izquierdo
#
# Dos modos visuales:
#   'set'  → relleno blanco semitransparente (más claro)
#   'call' → pequeños puntos blancos sobre fondo transparente
#
# El cambio de modo usa fundido cruzado de ~220 ms.

from PyQt5.QtCore import Qt, QPointF, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush
from PyQt5.QtWidgets import QWidget

_ANIM_INTERVAL_MS = 16      # ~60 fps
_ANIM_DURATION_MS = 220     # duración total del fundido
_ANIM_STEP = _ANIM_INTERVAL_MS / _ANIM_DURATION_MS


class AuditoriumOverlay(QWidget):
    """
    Widget transparente que cubre todo el panel izquierdo (0,0 → 1490,1080).
    Siempre visible; cambia su apariencia según el modo activo con fundido cruzado.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._mode      = 'call'
        self._prev_mode = 'call'
        self._blend     = 1.0       # 0.0 = prev_mode puro, 1.0 = mode puro

        self.setGeometry(0, 0, 1490, 1080)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._timer = QTimer(self)
        self._timer.setInterval(_ANIM_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def set_mode(self, mode: str):
        """'call' → puntos blancos  |  'set' → relleno blanco claro"""
        if mode == self._mode:
            return
        self._prev_mode = self._mode
        self._mode      = mode
        self._blend     = 0.0
        self._timer.start()

    def _tick(self):
        self._blend = min(1.0, self._blend + _ANIM_STEP)
        self.update()
        if self._blend >= 1.0:
            self._timer.stop()

    # ── pintado ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._blend >= 1.0:
            # Sin transición en curso — dibuja solo el modo actual
            self._draw_mode(painter, self._mode, 1.0)
        else:
            # Fundido cruzado: fade-out del modo anterior, fade-in del nuevo
            self._draw_mode(painter, self._prev_mode, 1.0 - self._blend)
            self._draw_mode(painter, self._mode,      self._blend)

        painter.end()

    def _draw_mode(self, painter: QPainter, mode: str, opacity: float):
        painter.setOpacity(opacity)

        if mode == 'set':
            painter.fillRect(self.rect(), QColor(255, 255, 255, 55))
        else:
            dot_r   = 2
            spacing = 24
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

        painter.setOpacity(1.0)
