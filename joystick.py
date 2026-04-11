#!/usr/bin/env python3
# joystick.py — Widget DigitalJoystick
#
# Extraído de widgets.py para reducir el tamaño de ese módulo.

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget

from config import SPEED_MAX


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

    _SECTOR_HALF = 22.5   # grados por medio sector
    _HYSTERESIS  = 10.0   # banda de histéresis en grados

    # Paleta — colores fijos del aro
    _C_RING_BG      = QtGui.QColor(220, 220, 220, 230)
    _C_RING_BORDER  = QtGui.QColor(180, 180, 180)
    _C_KNOB_HI      = QtGui.QColor(255, 255, 255)
    _C_KNOB_LO      = QtGui.QColor(185, 185, 185)
    _C_KNOB_BORDER  = QtGui.QColor(160, 160, 160)

    # Paleta modo "set" — verde
    _COLORS_SET = {
        'tick':     QtGui.QColor(125, 196, 125),   # #7DC47D
        'tick_act': QtGui.QColor(25,  118, 210),   # #1976D2
        'knob_hi':  QtGui.QColor(232, 248, 232),
        'knob_lo':  QtGui.QColor(100, 180, 100),
        'knob_brd': QtGui.QColor(125, 196, 125),
    }

    # Paleta modo "call" — burdeo
    _COLORS_CALL = {
        'tick':     QtGui.QColor(155,  58,  58),   # burdeo tenue
        'tick_act': QtGui.QColor(180,  30,  30),   # burdeo activo
        'knob_hi':  QtGui.QColor(249, 220, 220),   # rojo muy claro
        'knob_lo':  QtGui.QColor(160,  50,  50),   # burdeo medio
        'knob_brd': QtGui.QColor(110,  18,  18),   # burdeo oscuro
    }

    def __init__(self, parent, x: int, y: int, size: int,
                 handlers: dict, stop_handler, speed_provider=None):
        """
        handlers       : dict con claves 'up','down','left','right',
                         'upleft','upright','downleft','downright'
                         Cada handler recibe (pan_spd: int, tilt_spd: int).
        stop_handler   : callable sin argumentos
        speed_provider : callable que devuelve int (velocidad máxima).
                         Si es None usa SPEED_MAX como máximo.
        """
        super().__init__(parent)
        if x is not None and y is not None:
            self.setGeometry(x, y, size, size)
        else:
            self.setFixedSize(size, size)
        self.handlers        = handlers
        self.stop_handler    = stop_handler
        self._speed_provider = speed_provider or (lambda: SPEED_MAX)
        self._palette        = self._COLORS_SET   # modo por defecto: set (verde)

        # Permite que la transparencia del aro se componga sobre el panel
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        r = size / 2.0
        self._r       = r            # radio total del widget
        self._outer_r = r * 0.90     # radio del aro
        self._knob_r  = r * 0.28     # radio de la bolita
        self._dead_r  = r * 0.22     # zona muerta

        self._knob_pos     = QtCore.QPointF(r, r)
        self._tracking     = False
        self._cur_dir      = None
        self._cur_sector   = None    # None = sin sector activo
        self._cur_pan_spd  = 1
        self._cur_tilt_spd = 1

        # Timer de reenvío continuo: mantiene el comando activo cada 150 ms
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._on_timer_tick)

    # ── modo de color ──────────────────────────────────────────────────────────
    def set_mode(self, mode: str):
        """'platform' → burdeo  |  'comments' → verde."""
        self._palette = self._COLORS_CALL if mode == 'platform' else self._COLORS_SET
        self.update()

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
            p.setBrush(self._palette['tick_act'] if is_active else self._palette['tick'])
            p.drawEllipse(QtCore.QPointF(tx, ty), tick_size, tick_size)

        # Knob (bolita) — color cambia según estado
        if self._tracking and self._cur_dir:
            hi  = self._palette['knob_hi']
            lo  = self._palette['knob_lo']
            brd = self._palette['knob_brd']
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
            self._timer.stop()
            self._tracking   = False
            self._knob_pos   = QtCore.QPointF(self._center)
            self._cur_dir    = None
            self._cur_sector = None
            self.stop_handler()
            self.update()

    # ── timer de reenvío ───────────────────────────────────────────────────────
    def _on_timer_tick(self):
        """Reenvía el comando activo cada 150 ms para robustez ante paquetes perdidos."""
        if self._cur_dir and self._tracking:
            self.handlers[self._cur_dir](self._cur_pan_spd, self._cur_tilt_spd)

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
            dist = self._outer_r
        self._knob_pos = center + QtCore.QPointF(dx, dy)

        # Zona muerta
        if dist < self._dead_r:
            if self._cur_dir is not None:
                self._timer.stop()
                self._cur_dir    = None
                self._cur_sector = None
                self.stop_handler()
            self.update()
            return

        # Velocidad proporcional: componente de cada eje escalada al máximo del slider
        max_spd  = self._speed_provider()
        pan_spd  = max(1, round((abs(dx) / self._outer_r) * max_spd))
        tilt_spd = max(1, round((abs(dy) / self._outer_r) * max_spd))

        # Ángulo: 0=arriba, 90=derecha, 180=abajo, 270=izquierda
        angle      = math.degrees(math.atan2(dx, -dy)) % 360
        raw_sector = int((angle + self._SECTOR_HALF) / 45) % 8

        # Histéresis: requiere ≥_HYSTERESIS grados dentro del nuevo sector para aceptarlo
        if self._cur_sector is None:
            accepted_sector = raw_sector
        elif raw_sector == self._cur_sector:
            accepted_sector = self._cur_sector
        else:
            sector_center      = raw_sector * 45.0
            delta              = (angle - sector_center + 180) % 360 - 180
            dist_from_boundary = self._SECTOR_HALF - abs(delta)
            accepted_sector    = raw_sector if dist_from_boundary >= self._HYSTERESIS else self._cur_sector

        new_dir = self._DIR_MAP[accepted_sector]

        if new_dir != self._cur_dir:
            self._cur_sector   = accepted_sector
            self._cur_dir      = new_dir
            self._cur_pan_spd  = pan_spd
            self._cur_tilt_spd = tilt_spd
            self.handlers[new_dir](pan_spd, tilt_spd)
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._cur_pan_spd  = pan_spd
            self._cur_tilt_spd = tilt_spd

        self.update()
