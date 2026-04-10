#!/usr/bin/env python3
# camera_indicator.py — Indicador visual de cámara activa (cono de luz / spotlight)
#
# CameraIndicator es un widget transparente sin interacción que dibuja
# un cono de luz entre la plataforma y los asientos 11-12:
#
#   Platform (Cam1):  lámpara cerca de los asientos 11-12 → cono apunta
#                     hacia arriba (ilumina la plataforma).
#   Comments (Cam2):  lámpara a nivel de la plataforma → cono apunta
#                     hacia abajo (ilumina la zona de comentarios/asientos).
#
# USO en MainWindow:
#   self._cam_indicator = CameraIndicator(self)
#   self._cam_indicator.set_mode('platform')   # o 'comments'

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QPolygonF, QBrush,
)
from PyQt5.QtWidgets import QWidget


class CameraIndicator(QWidget):
    """
    Widget transparente que dibuja un spotlight (lámpara + cono de luz)
    indicando qué cámara está activa.

    Geometría en MainWindow:
      - Centrado sobre los asientos 11-12 (x≈720) en la franja vertical
        entre la plataforma (y≈10) y la primera fila (y≈211).
      - setGeometry(600, 5, 240, 225)

    No captura eventos de ratón (WA_TransparentForMouseEvents).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._mode = 'platform'

        # Platform mode: justo debajo del botón Chairman (x=689-799, y=10-125).
        # El widget arranca en y=125 (borde inferior del Chairman), centrado en
        # x=744 (centro del Chairman), y cubre hasta la primera fila de asientos (y≈213).
        # width=340 para un cono más ancho que el icono.
        self.setGeometry(574, 125, 340, 90)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_mode(self, mode: str):
        """
        Cambia la dirección del cono y redibuja.
        mode: 'platform'  → lámpara abajo, cono hacia la plataforma (arriba)
              'comments'  → lámpara arriba, cono hacia los asientos (abajo)
        """
        self._mode = mode
        self.update()

    # ── Dibujo ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx = w // 2          # centro horizontal del widget

        if self._mode == 'platform':
            # Lámpara en la parte inferior (asientos), cono apunta hacia arriba → plataforma.
            lamp    = QPointF(cx, h - 10)
            base_y  = 6
            half_open = 155
        else:
            # Lámpara en la parte superior (Chairman/plataforma), cono apunta hacia abajo → comments.
            lamp    = QPointF(cx, 10)
            base_y  = h - 6
            half_open = 155

        base_l = QPointF(cx - half_open, base_y)
        base_r = QPointF(cx + half_open, base_y)

        # ── Cono de luz — muy tenue, blanco ───────────────────────────────
        cone = QPolygonF([lamp, base_l, base_r])

        grad = QLinearGradient(lamp, QPointF(cx, base_y))
        grad.setColorAt(0.0, QColor(255, 255, 252,  55))   # blanco casi puro, muy tenue
        grad.setColorAt(0.5, QColor(255, 255, 255,  25))
        grad.setColorAt(1.0, QColor(255, 255, 255,   0))   # se desvanece

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(cone)

        # ── Halo de la lámpara — blanco suave ─────────────────────────────
        glow_r = 14
        glow = QRadialGradient(lamp, glow_r)
        glow.setColorAt(0.0, QColor(255, 255, 255,  90))
        glow.setColorAt(0.6, QColor(230, 240, 255,  35))
        glow.setColorAt(1.0, QColor(255, 255, 255,   0))

        painter.setBrush(QBrush(glow))
        painter.drawEllipse(lamp, glow_r, glow_r)

        # ── Núcleo de la lámpara — blanco puro ────────────────────────────
        core_r = 4
        core = QRadialGradient(lamp, core_r)
        core.setColorAt(0.0, QColor(255, 255, 255, 210))
        core.setColorAt(1.0, QColor(240, 245, 255, 120))

        painter.setBrush(QBrush(core))
        painter.drawEllipse(lamp, core_r, core_r)

        painter.end()
