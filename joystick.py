#!/usr/bin/env python3
# joystick.py — Widget DigitalJoystick
#
# Extraído de widgets.py para reducir el tamaño de ese módulo.

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget


class DigitalJoystick(QWidget):
    """
    Joystick digital que reemplaza la botonera de 8 flechas.
    - Click + arrastre → llama al handler de la dirección correspondiente
    - Release          → llama a stop_handler
    - Zona muerta central → sin movimiento

    Colores adaptados al panel claro del entorno (#F2F2F2 / #E8E8E8).
    """

    _DIR_MAP = {
        0: 'up', 1: 'upright', 2: 'right', 3: 'downright',
        4: 'down', 5: 'downleft', 6: 'left', 7: 'upleft',
    }

    # Paleta — coincide con el esquema del panel derecho
    _C_RING_BG      = QtGui.QColor(220, 220, 220, 230)   # ~#DCDCDC, toggle buttons
    _C_RING_BORDER  = QtGui.QColor(180, 180, 180)         # ~#B4B4B4
    _C_TICK         = QtGui.QColor(125, 196, 125)         # #7DC47D, acento verde slider
    _C_TICK_ACTIVE  = QtGui.QColor(25, 118, 210)          # #1976D2, azul selector cámara
    _C_KNOB_HI      = QtGui.QColor(255, 255, 255)         # blanco
    _C_KNOB_LO      = QtGui.QColor(185, 185, 185)         # gris claro
    _C_KNOB_BORDER  = QtGui.QColor(160, 160, 160)
    _C_KNOB_ACT_HI  = QtGui.QColor(232, 248, 232)         # verde muy claro
    _C_KNOB_ACT_LO  = QtGui.QColor(100, 180, 100)         # verde medio
    _C_KNOB_ACT_BRD = QtGui.QColor(125, 196, 125)         # #7DC47D

    def __init__(self, parent, x: int, y: int, size: int,
                 handlers: dict, stop_handler):
        """
        handlers     : dict con claves 'up','down','left','right',
                       'upleft','upright','downleft','downright'
        stop_handler : callable sin argumentos
        """
        super().__init__(parent)
        self.setGeometry(x, y, size, size)
        self.handlers     = handlers
        self.stop_handler = stop_handler

        # Permite que la transparencia del aro se componga sobre el panel
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        r = size / 2.0
        self._r       = r            # radio total del widget
        self._outer_r = r * 0.90     # radio del aro
        self._knob_r  = r * 0.28     # radio de la bolita
        self._dead_r  = r * 0.22     # zona muerta

        self._knob_pos = QtCore.QPointF(r, r)
        self._tracking = False
        self._cur_dir  = None

    # ── helpers ────────────────────────────────────────────────────────────────
    @property
    def _center(self) -> QtCore.QPointF:
        """Centro del widget — correcto aunque cambie el tamaño."""
        return QtCore.QPointF(self.width() / 2.0, self.height() / 2.0)

    # ── paint ──────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        center = self._center
        cx, cy = center.x(), center.y()

        # Aro exterior
        p.setPen(QtGui.QPen(self._C_RING_BORDER, 2))
        p.setBrush(self._C_RING_BG)
        p.drawEllipse(center, self._outer_r, self._outer_r)

        # Marcas de las 8 direcciones — resalta la activa
        tick_r    = self._outer_r * 0.72
        tick_size = self._outer_r * 0.10
        p.setPen(Qt.NoPen)
        for i, angle_deg in enumerate(range(0, 360, 45)):
            rad = math.radians(angle_deg)
            tx  = cx + tick_r * math.sin(rad)
            ty  = cy - tick_r * math.cos(rad)
            is_active = (self._cur_dir == self._DIR_MAP[i])
            p.setBrush(self._C_TICK_ACTIVE if is_active else self._C_TICK)
            p.drawEllipse(QtCore.QPointF(tx, ty), tick_size, tick_size)

        # Knob (bolita) — color cambia según estado
        if self._tracking and self._cur_dir:
            hi, lo, brd = self._C_KNOB_ACT_HI, self._C_KNOB_ACT_LO, self._C_KNOB_ACT_BRD
        else:
            hi, lo, brd = self._C_KNOB_HI, self._C_KNOB_LO, self._C_KNOB_BORDER

        grad = QtGui.QRadialGradient(self._knob_pos, self._knob_r)
        grad.setColorAt(0.0, hi)
        grad.setColorAt(1.0, lo)
        p.setPen(QtGui.QPen(brd, 1.5))
        p.setBrush(grad)
        p.drawEllipse(self._knob_pos, self._knob_r, self._knob_r)

    # ── mouse events ───────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._tracking = True
            self._process(event.pos())

    def mouseMoveEvent(self, event):
        if self._tracking:
            self._process(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._tracking = False
            self._knob_pos = QtCore.QPointF(self._center)
            self._cur_dir  = None
            self.stop_handler()
            self.update()

    # ── lógica de dirección ────────────────────────────────────────────────────
    def _process(self, qpoint):
        center = self._center
        dx   = qpoint.x() - center.x()
        dy   = qpoint.y() - center.y()
        dist = math.hypot(dx, dy)

        # Clamp al círculo exterior
        if dist > self._outer_r:
            scale = self._outer_r / dist
            dx, dy = dx * scale, dy * scale
        self._knob_pos = center + QtCore.QPointF(dx, dy)

        # Zona muerta
        if dist < self._dead_r:
            if self._cur_dir is not None:
                self._cur_dir = None
                self.stop_handler()
            self.update()
            return

        # Ángulo: 0=arriba, 90=derecha, 180=abajo, 270=izquierda
        angle   = math.degrees(math.atan2(dx, -dy)) % 360
        sector  = int((angle + 22.5) / 45) % 8
        new_dir = self._DIR_MAP[sector]

        if new_dir != self._cur_dir:
            self._cur_dir = new_dir
            self.handlers[new_dir]()

        self.update()
