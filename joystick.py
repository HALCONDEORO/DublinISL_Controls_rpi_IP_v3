#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# joystick.py — Widget DigitalJoystick

import math

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
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
    - Anillo de zoom superior (semicírculo W→T) arrastrable; emite zoom_changed(int)
    """

    zoom_changed = pyqtSignal(int)  # emite pct 0-100

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

        # ── Anillo de zoom (semicírculo superior) ─────────────────────────────
        self._ring_r      = r * 0.94      # radio del arco, separado del disco
        self._ring_stroke = max(18, int(r * 0.096))  # grosor del trazo del arco
        self._ring_pct    = 0.0               # 0–100
        self._ring_dragging = False
        self._ring_platform_color = QtGui.QColor(155, 58, 58)   # #9B3A3A
        self._ring_comments_color = QtGui.QColor(74, 140, 74)   # #4A8C4A
        self._ring_active_color   = self._ring_platform_color   # default: platform

    # ── modo de color ──────────────────────────────────────────────────────────
    def set_mode(self, mode: str):
        """'platform' → rojo  |  cualquier otro → verde."""
        self._palette           = self._COLORS_CALL if mode == 'platform' else self._COLORS_SET
        self._glow_grad         = self._glow_grads[id(self._palette)]
        self._ring_active_color = (self._ring_platform_color if mode == 'platform'
                                   else self._ring_comments_color)
        self.update()

    def set_zoom(self, pct):
        """Actualiza el anillo de zoom desde una fuente externa (sin emitir señal)."""
        self._ring_pct = max(0.0, min(100.0, float(pct)))
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

        # Anillo de zoom encima del joystick
        self._draw_zoom_ring(p)

    # ── anillo de zoom ─────────────────────────────────────────────────────────

    def _ring_pct_to_pos(self, pct: float) -> QtCore.QPointF:
        """Convierte 0–100% a coordenada de pantalla sobre el arco."""
        # Qt: 0°=este, 90°=norte, 180°=oeste. Arco va de 180° (izq) a 0° (der) CW.
        deg = 180.0 - pct * 1.8
        rad = math.radians(deg)
        cx, cy = self._center.x(), self._center.y()
        return QtCore.QPointF(
            cx + self._ring_r * math.cos(rad),
            cy - self._ring_r * math.sin(rad),
        )

    def _pos_to_ring_pct(self, pos) -> float:
        """Convierte posición de mouse a porcentaje de zoom (restringido al semiarco superior)."""
        cx, cy = self._center.x(), self._center.y()
        dx = pos.x() - cx
        dy = pos.y() - cy
        deg = math.degrees(math.atan2(-dy, dx))  # CCW desde este
        if deg < 0:
            deg += 360.0
        if 0.0 <= deg <= 180.0:
            return max(0.0, min(100.0, (180.0 - deg) / 1.8))
        return 0.0 if (dx < 0) else 100.0  # semianillo inferior: snap

    def _is_ring_hit(self, pos) -> bool:
        """True si el click cae sobre el arco del anillo (mitad superior)."""
        cx, cy = self._center.x(), self._center.y()
        dx = pos.x() - cx
        dy = pos.y() - cy
        dist = math.hypot(dx, dy)
        tolerance = self._ring_stroke * 1.6
        return abs(dist - self._ring_r) < tolerance and dy <= self._ring_stroke

    def _draw_zoom_ring(self, p: QtGui.QPainter):
        """Dibuja el semiarco de zoom encima del joystick."""
        cx, cy = self._center.x(), self._center.y()
        R  = self._ring_r
        sw = self._ring_stroke
        rect = QtCore.QRectF(cx - R, cy - R, R * 2, R * 2)

        p.setBrush(Qt.NoBrush)

        # Arco de pista (gris, de 180° a 0° en sentido horario = span −180)
        track_pen = QtGui.QPen(QtGui.QColor(212, 212, 212), sw, Qt.SolidLine,
                               Qt.RoundCap, Qt.RoundJoin)
        p.setPen(track_pen)
        p.drawArc(rect, 180 * 16, -180 * 16)

        # Arco relleno (color cámara, de 180° hasta la posición actual)
        if self._ring_pct > 0.5:
            span = int(round(self._ring_pct * 1.8 * 16))
            fill_pen = QtGui.QPen(self._ring_active_color, sw, Qt.SolidLine,
                                  Qt.RoundCap, Qt.RoundJoin)
            p.setPen(fill_pen)
            p.drawArc(rect, 180 * 16, -span)

        # Marcas de tick (0%, 50%, 100% mayores; 25%, 75% menores)
        for i in range(11):
            pct_t = i * 10
            deg   = 180.0 - pct_t * 1.8
            rad   = math.radians(deg)
            major = (i % 5 == 0)
            r1 = R - (sw * 0.55 if major else sw * 0.35)
            r2 = R + (sw * 0.55 if major else sw * 0.35)
            x1 = cx + r1 * math.cos(rad)
            y1 = cy - r1 * math.sin(rad)
            x2 = cx + r2 * math.cos(rad)
            y2 = cy - r2 * math.sin(rad)
            tick_pen = QtGui.QPen(
                QtGui.QColor(160, 160, 160) if major else QtGui.QColor(200, 200, 200),
                2.0 if major else 1.2, Qt.SolidLine, Qt.RoundCap,
            )
            p.setPen(tick_pen)
            p.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

        # Handle — disco plano, ligeramente mayor que el trazo, difuminado en bordes
        hp = self._ring_pct_to_pos(self._ring_pct)
        hr = sw * 0.58  # diámetro = 1.16×sw → sobresale un poco del canal
        ac = self._ring_active_color

        p.setPen(Qt.NoPen)
        soft_g = QtGui.QRadialGradient(hp.x(), hp.y(), hr)
        soft_g.setColorAt(0.00, ac)
        soft_g.setColorAt(0.62, ac)
        soft_g.setColorAt(1.00, QtGui.QColor(ac.red(), ac.green(), ac.blue(), 0))
        p.setBrush(soft_g)
        p.drawEllipse(hp, hr, hr)

        # Etiquetas W / T
        p.setPen(QtGui.QColor(175, 175, 175))
        lbl_font = QtGui.QFont('Inter Tight', max(7, int(sw * 0.72)), QtGui.QFont.Bold)
        p.setFont(lbl_font)
        fm = QtGui.QFontMetricsF(lbl_font)
        # 0 (debajo del extremo izquierdo)
        w_x = cx - R - fm.width('0') * 0.5
        w_y = cy + sw + fm.ascent() + 2
        p.drawText(QtCore.QPointF(w_x, w_y), '0')
        # 100 (debajo del extremo derecho)
        t_x = cx + R - fm.width('100') * 0.5
        t_y = cy + sw + fm.ascent() + 2
        p.drawText(QtCore.QPointF(t_x, t_y), '100')

    # ── mouse events ───────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = QtCore.QPointF(event.pos())
            if self._is_ring_hit(pos):
                self._ring_dragging = True
                self._ring_pct = self._pos_to_ring_pct(pos)
                self.zoom_changed.emit(int(round(self._ring_pct)))
                self.update()
            else:
                self._tracking = True
                self._process(event.pos())

    def mouseMoveEvent(self, event):
        pos = QtCore.QPointF(event.pos())
        if self._ring_dragging:
            self._ring_pct = self._pos_to_ring_pct(pos)
            self.zoom_changed.emit(int(round(self._ring_pct)))
            self.update()
        elif self._tracking:
            self._process(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._ring_dragging:
                self._ring_dragging = False
                self.zoom_changed.emit(int(round(self._ring_pct)))
            elif self._tracking:
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
