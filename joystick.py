#!/usr/bin/env python3
# joystick.py — Widget DigitalJoystick

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget

from config import SPEED_MAX


def _with_alpha(color: QtGui.QColor, alpha: int) -> QtGui.QColor:
    c = QtGui.QColor(color)
    c.setAlpha(alpha)
    return c


class DigitalJoystick(QWidget):
    """
    Joystick digital que reemplaza la botonera de 8 flechas.
    - Click + arrastre → llama al handler de la dirección correspondiente
    - Release          → llama a stop_handler
    - Zona muerta central → sin movimiento
    """

    _DIR_MAP = {
        0: 'up', 1: 'upright', 2: 'right', 3: 'downright',
        4: 'down', 5: 'downleft', 6: 'left', 7: 'upleft',
    }

    _SECTOR_HALF = 22.5
    _HYSTERESIS  = 10.0

    _COLORS_SET = {
        'accent':   QtGui.QColor( 34, 197, 150),
        'tick':     QtGui.QColor(130, 200, 170, 180),
        'tick_act': QtGui.QColor( 34, 197, 150),
        'knob_hi':  QtGui.QColor(220, 255, 245),
        'knob_mid': QtGui.QColor( 60, 180, 140),
        'knob_lo':  QtGui.QColor( 20, 110,  80),
        'knob_brd': QtGui.QColor( 15,  90,  65),
        'glow':     QtGui.QColor( 34, 197, 150,  60),
    }

    _COLORS_CALL = {
        'accent':   QtGui.QColor(200,  45,  45),
        'tick':     QtGui.QColor(190,  90,  90, 180),
        'tick_act': QtGui.QColor(220,  50,  50),
        'knob_hi':  QtGui.QColor(255, 220, 220),
        'knob_mid': QtGui.QColor(180,  55,  55),
        'knob_lo':  QtGui.QColor(110,  18,  18),
        'knob_brd': QtGui.QColor( 80,  10,  10),
        'glow':     QtGui.QColor(200,  45,  45,  60),
    }

    _COLORS_INACTIVE = {
        'knob_hi':  QtGui.QColor(255, 255, 255),
        'knob_mid': QtGui.QColor(200, 200, 205),
        'knob_lo':  QtGui.QColor(150, 150, 158),
        'knob_brd': QtGui.QColor(120, 120, 128),
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
        self._palette        = self._COLORS_SET

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        r  = size / 2.0
        cx = cy = r
        self._r       = r
        self._outer_r = r * 0.72
        self._knob_r  = r * 0.18
        self._dead_r  = r * 0.10
        R = self._outer_r

        # Centro fijo (widget de tamaño fijo — nunca cambia)
        self._center = QtCore.QPointF(r, r)

        self._knob_pos     = QtCore.QPointF(r, r)
        self._tracking     = False
        self._cur_dir      = None
        self._cur_sector   = None
        self._cur_pan_spd  = 1
        self._cur_tilt_spd = 1

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._on_timer_tick)

        # ── Objetos gráficos estáticos pre-calculados ─────────────────────────
        self._shadow_grad = QtGui.QRadialGradient(cx + R * 0.05, cy + R * 0.08, R * 1.05)
        self._shadow_grad.setColorAt(0.82, QtGui.QColor(0, 0, 0,  0))
        self._shadow_grad.setColorAt(1.00, QtGui.QColor(0, 0, 0, 60))

        self._base_grad = QtGui.QRadialGradient(cx - R * 0.25, cy - R * 0.25, R * 1.2)
        self._base_grad.setColorAt(0.00, QtGui.QColor(245, 245, 248))
        self._base_grad.setColorAt(0.55, QtGui.QColor(215, 215, 220))
        self._base_grad.setColorAt(1.00, QtGui.QColor(175, 175, 182))

        self._base_pen = QtGui.QPen(QtGui.QColor(140, 140, 148), 1.5)
        self._dead_pen = QtGui.QPen(QtGui.QColor(180, 180, 188, 120), 0.8, Qt.DashLine)

        # Glow pre-calculado por paleta; _glow_grad apunta al activo
        self._glow_grads = {}
        for pal in (self._COLORS_SET, self._COLORS_CALL):
            g    = pal['glow']
            grad = QtGui.QRadialGradient(cx, cy, R)
            grad.setColorAt(0.70, _with_alpha(g,  0))
            grad.setColorAt(0.88, _with_alpha(g, 80))
            grad.setColorAt(1.00, _with_alpha(g,  0))
            self._glow_grads[id(pal)] = grad
        self._glow_grad = self._glow_grads[id(self._palette)]

        # Triángulos de dirección y centros de halo (geometría fija)
        tick_r    = R * 0.71
        arrow_len = R * 0.115
        arrow_w   = R * 0.055
        self._arrow_triangles = []
        self._arrow_halo_pts  = []
        for angle_deg in range(0, 360, 45):
            rad    = math.radians(angle_deg)
            sin_r  = math.sin(rad)
            cos_r  = math.cos(rad)
            tip_x  = cx + (tick_r + arrow_len * 0.6) * sin_r
            tip_y  = cy - (tick_r + arrow_len * 0.6) * cos_r
            base_x = cx + (tick_r - arrow_len * 0.6) * sin_r
            base_y = cy - (tick_r - arrow_len * 0.6) * cos_r
            self._arrow_triangles.append(QtGui.QPolygonF([
                QtCore.QPointF(tip_x,             tip_y),
                QtCore.QPointF(base_x - cos_r * arrow_w, base_y - sin_r * arrow_w),
                QtCore.QPointF(base_x + cos_r * arrow_w, base_y + sin_r * arrow_w),
            ]))
            self._arrow_halo_pts.append(QtCore.QPointF(
                cx + tick_r * sin_r,
                cy - tick_r * cos_r,
            ))
        self._arrow_halo_r = arrow_len * 1.4

    # ── modo de color ──────────────────────────────────────────────────────────
    def set_mode(self, mode: str):
        """'platform' → rojo  |  cualquier otro → verde."""
        self._palette   = self._COLORS_CALL if mode == 'platform' else self._COLORS_SET
        self._glow_grad = self._glow_grads[id(self._palette)]
        self.update()

    # ── paint ──────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        center = self._center
        R   = self._outer_r
        pal = self._palette
        active = self._tracking and self._cur_dir is not None

        # Sombra exterior
        p.setPen(Qt.NoPen)
        p.setBrush(self._shadow_grad)
        p.drawEllipse(center, R * 1.05, R * 1.05)

        # Plato base
        p.setBrush(self._base_grad)
        p.setPen(self._base_pen)
        p.drawEllipse(center, R, R)

        # Anillo de zona muerta
        p.setPen(self._dead_pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, self._dead_r, self._dead_r)

        # Glow de activación
        if active:
            p.setPen(Qt.NoPen)
            p.setBrush(self._glow_grad)
            p.drawEllipse(center, R, R)

        # Flechas (8 triángulos pre-calculados)
        p.setPen(Qt.NoPen)
        for i in range(8):
            is_active = (self._cur_dir == self._DIR_MAP[i])
            color     = pal['tick_act'] if is_active else pal['tick']
            if is_active:
                p.setBrush(_with_alpha(color, 70))
                p.drawEllipse(self._arrow_halo_pts[i], self._arrow_halo_r, self._arrow_halo_r)
            p.setBrush(color)
            p.drawPolygon(self._arrow_triangles[i])

        # Knob — esfera 3D
        kp = self._knob_pos
        kr = self._knob_r

        knob_shadow = QtGui.QRadialGradient(kp.x() + kr * 0.15, kp.y() + kr * 0.2, kr * 1.1)
        knob_shadow.setColorAt(0.75, QtGui.QColor(0, 0, 0,  0))
        knob_shadow.setColorAt(1.00, QtGui.QColor(0, 0, 0, 50))
        p.setPen(Qt.NoPen)
        p.setBrush(knob_shadow)
        p.drawEllipse(kp, kr * 1.12, kr * 1.12)

        ik = pal if active else self._COLORS_INACTIVE
        sphere_grad = QtGui.QRadialGradient(kp.x() - kr * 0.3, kp.y() - kr * 0.35, kr * 1.1)
        sphere_grad.setColorAt(0.00, ik['knob_hi'])
        sphere_grad.setColorAt(0.45, ik['knob_mid'])
        sphere_grad.setColorAt(1.00, ik['knob_lo'])
        p.setPen(QtGui.QPen(ik['knob_brd'], 1.2))
        p.setBrush(sphere_grad)
        p.drawEllipse(kp, kr, kr)

        # Reflejo especular
        spec_x  = kp.x() - kr * 0.30
        spec_y  = kp.y() - kr * 0.32
        spec_rx = kr * 0.28
        spec_ry = kr * 0.18
        spec_grad = QtGui.QRadialGradient(spec_x, spec_y, spec_rx)
        spec_grad.setColorAt(0.0, QtGui.QColor(255, 255, 255, 200))
        spec_grad.setColorAt(1.0, QtGui.QColor(255, 255, 255,   0))
        p.setPen(Qt.NoPen)
        p.setBrush(spec_grad)
        p.drawEllipse(QtCore.QPointF(spec_x, spec_y), spec_rx, spec_ry)

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
        if self._cur_dir and self._tracking:
            self.handlers[self._cur_dir](self._cur_pan_spd, self._cur_tilt_spd)

    # ── lógica de dirección ────────────────────────────────────────────────────
    def _process(self, qpoint):
        center = self._center
        dx   = qpoint.x() - center.x()
        dy   = qpoint.y() - center.y()
        dist = math.hypot(dx, dy)

        if dist > self._outer_r:
            scale = self._outer_r / dist
            dx, dy = dx * scale, dy * scale
            dist = self._outer_r

        if dist < self._dead_r:
            self._knob_pos = center + QtCore.QPointF(dx, dy)
            if self._cur_dir is not None:
                self._timer.stop()
                self._cur_dir    = None
                self._cur_sector = None
                self.stop_handler()
            self.update()
            return

        max_spd   = self._speed_provider()
        t         = (dist - self._dead_r) / (self._outer_r - self._dead_r)
        t         = min(1.0, t)
        total_spd = max(1, round(1 + t * (max_spd - 1)))

        angle      = math.degrees(math.atan2(dx, -dy)) % 360
        raw_sector = int((angle + self._SECTOR_HALF) / 45) % 8

        if self._cur_sector is None:
            accepted_sector = raw_sector
        elif raw_sector == self._cur_sector:
            accepted_sector = self._cur_sector
        else:
            sector_center      = raw_sector * 45.0
            delta              = (angle - sector_center + 180) % 360 - 180
            dist_from_boundary = self._SECTOR_HALF - abs(delta)
            accepted_sector    = raw_sector if dist_from_boundary >= self._HYSTERESIS else self._cur_sector

        # Snap knob visual y velocidades al ángulo exacto del sector
        snap_rad       = math.radians(accepted_sector * 45.0)
        self._knob_pos = center + QtCore.QPointF(dist * math.sin(snap_rad),
                                                 -dist * math.cos(snap_rad))
        pan_spd  = max(1, round(total_spd * abs(math.sin(snap_rad))))
        tilt_spd = max(1, round(total_spd * abs(math.cos(snap_rad))))

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
