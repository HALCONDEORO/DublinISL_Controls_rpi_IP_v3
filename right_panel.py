#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# right_panel.py — Panel derecho de controles PTZ (layout-based)
#
# Todos los widgets viven dentro de un QFrame container con QVBoxLayout.
# Se eliminan las coordenadas absolutas; la estructura visual es idéntica
# a la versión anterior pero el panel se adapta al container blanco.
#
# Atributos que crea en main_window:
#   mw.Cam1, mw.Cam2, mw.Camgroup
#   mw.BtnBacklight, mw._backlight_style_off, mw._backlight_style_on
# Nota: mw.BtnCall, mw.BtnSet y mw.PresetModeGroup se crean en main_window._build_mode_buttons()
#   Los frames visuales call_frame/set_frame se crean aquí (_add_mode_buttons) y se exponen como
#   self.call_frame y self.set_frame para que main_window los conecte con la lógica de estado.

from __future__ import annotations

import os

from PyQt5 import QtCore
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)



class RightPanel:
    """
    Panel derecho de controles PTZ (layout-based).
    Container blanco sobre (1446, 0, 474, 1080). Todos los widgets son hijos
    del container; sus referencias se asignan como atributos de main_window.
    """

    TOGGLE_STYLE = (
        "QPushButton {"
        "  background-color: #DCDCDC; border: none; border-radius: 10px;"
        "  font: 600 18px 'Inter Tight', 'Segoe UI'; color: #777777; padding: 6px 0px;"
        "}"
        "QPushButton:checked {"
        "  background-color: white; color: #111111;"
        "  border: 1px solid #C8C8C8;"
        "}"
    )

    def __init__(self, main_window):
        self._mw = main_window
        self._joystick_slot = None   # QWidget placeholder para el joystick
        self._build_outer_bg()
        self._build_panel()

    def connect_joystick(self, handlers: dict, stop_handler, speed_provider=None):
        """Inserta el DigitalJoystick en el slot reservado en el layout."""
        from joystick import DigitalJoystick
        mw = self._mw
        slot = self._joystick_slot
        self._joystick = DigitalJoystick(slot, None, None, slot.width(),
                                         handlers, stop_handler, speed_provider)

        # Anillo → slider oculto → VISCA debounce
        self._joystick.zoom_changed.connect(
            lambda pct: mw.ZoomSlider.setValue(int(round(pct))))

        # Slider oculto (actualizado por VISCA feedback) → anillo visual
        mw.ZoomSlider.valueChanged.connect(self._joystick.set_zoom)

        # Botones +/− → slider (la cadena slider→anillo→VISCA ya está cableada)
        self._zoom_plus_btn.clicked.connect(
            lambda: mw.ZoomSlider.setValue(min(100, mw.ZoomSlider.value() + 5)))
        self._zoom_minus_btn.clicked.connect(
            lambda: mw.ZoomSlider.setValue(max(0, mw.ZoomSlider.value() - 5)))

    def set_active_mode(self, mode: str):
        """'call' → activa call_frame rojo  |  'set' → activa set_frame verde."""
        if mode == 'call':
            active, inactive = self.call_frame, self.set_frame
            active_style = self._MODE_STYLE_ACTIVE_CALL
        else:
            active, inactive = self.set_frame, self.call_frame
            active_style = self._MODE_STYLE_ACTIVE_SET
        active.setStyleSheet(active_style)
        active._label.setStyleSheet(self._MODE_LBL_STYLE_ACT)
        inactive.setStyleSheet(self._MODE_STYLE_INACTIVE)
        inactive._label.setStyleSheet(self._MODE_LBL_STYLE_INACT)
        if hasattr(self, '_btn_gear'):
            visible = mode == 'set'
            self._btn_gear.setVisible(visible)
            self._gear_sep.setVisible(visible)
            QtCore.QTimer.singleShot(0, self._fit_container_height)

    def set_joystick_mode(self, mode: str):
        """'platform' → burdeo  |  'comments' → verde."""
        if hasattr(self, '_joystick'):
            self._joystick.set_mode(mode)

    def show_camera_controls(self, visible: bool):
        """Muestra u oculta los controles PTZ/Focus según si la cámara está conectada."""
        self._controls_widget.setVisible(visible)
        self._no_camera_label.setVisible(not visible)
        QtCore.QTimer.singleShot(0, self._fit_container_height)

    # ── Fondo exterior oscuro ─────────────────────────────────────────────────

    def _build_outer_bg(self):
        mw = self._mw
        outer = QFrame(mw)
        outer.setGeometry(1446, 0, 474, 1080)
        outer.setStyleSheet("QFrame { background-color: #B0B0B0; border: none; }")
        outer.lower()

    # ── Container principal con layout ────────────────────────────────────────

    def _build_panel(self):
        mw = self._mw

        # Container blanco — hijo directo de mw, posicionado absolutamente
        self._container = QFrame(mw)
        self._container.setGeometry(1446, 0, 474, 1080)
        self._container.setStyleSheet(
            "QFrame#RightPanelContainer {"
            "  background-color: #F4F4F6;"
            "  border-top-left-radius: 0px;"
            "  border-top-right-radius: 0px;"
            "  border-bottom-left-radius: 8px;"
            "  border-bottom-right-radius: 0px;"
            "  border: none;"
            "}"
        )
        self._container.setObjectName("RightPanelContainer")

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(4)

        self._add_mode_buttons(layout)
        self._add_separator(layout)
        self._add_camera_selector(layout)

        # ── Contenedor de controles PTZ + Focus/Exposure ──────────────────────
        self._controls_widget = QWidget(self._container)
        ctrl_layout = QVBoxLayout(self._controls_widget)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(4)
        self._add_separator(ctrl_layout)
        self._add_ptz_block(ctrl_layout)
        self._add_separator(ctrl_layout)
        self._add_focus_exposure(ctrl_layout)
        layout.addWidget(self._controls_widget)

        # Widget "Camera not found" — visible solo cuando no hay cámara conectada
        no_cam_container = QWidget(self._container)
        no_cam_layout = QVBoxLayout(no_cam_container)
        no_cam_layout.setContentsMargins(0, 40, 0, 40)
        no_cam_layout.setSpacing(12)
        no_cam_layout.setAlignment(Qt.AlignCenter)
        no_cam_icon = QSvgWidget(os.path.join(self._BASE_DIR, 'no-camera.svg'), no_cam_container)
        no_cam_icon.setFixedSize(64, 64)
        no_cam_text = QLabel('Camera\nnot found', no_cam_container)
        no_cam_text.setAlignment(Qt.AlignCenter)
        no_cam_text.setStyleSheet("QLabel { font: 700 22px 'Inter Tight', 'Segoe UI'; color: #AAAAAA; }")
        no_cam_layout.addWidget(no_cam_icon, 0, Qt.AlignCenter)
        no_cam_layout.addWidget(no_cam_text, 0, Qt.AlignCenter)
        self._no_camera_label = no_cam_container
        self._no_camera_label.hide()
        layout.addWidget(self._no_camera_label)

        layout.addSpacing(6)
        self._add_config_buttons(layout)
        layout.addStretch()

        QtCore.QTimer.singleShot(0, self._fit_container_height)

    def _fit_container_height(self):
        """El panel ocupa siempre toda la altura de la pantalla."""
        self._container.setGeometry(1446, 0, 474, 1080)

    # ── Secciones ─────────────────────────────────────────────────────────────

    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    _ON_AIR_STYLE_STANDBY = (
        "QLabel { font: 700 12px 'Inter Tight', 'Segoe UI'; color: #999999;"
        " background: #EBEBEB; border-radius: 6px; padding: 0px; }"
    )
    _ON_AIR_STYLE_LIVE = (
        "QLabel { font: 700 12px 'Inter Tight', 'Segoe UI'; color: white;"
        " background: #CC2200; border-radius: 6px; padding: 0px; }"
    )

    _MODE_STYLE_ACTIVE_CALL = (
        "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        " stop:0 #B84A4A, stop:1 #7A2020);"
        " border-radius: 8px; border: none; }"
    )
    _MODE_STYLE_ACTIVE_SET = (
        "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
        " stop:0 #5EA85E, stop:1 #2E6B2E);"
        " border-radius: 8px; border: none; }"
    )
    _MODE_STYLE_INACTIVE = (
        "QFrame { background-color: transparent; border-radius: 8px; border: none; }"
    )
    _MODE_LBL_STYLE_ACT   = "QLabel { font: 700 15px 'Inter Tight', 'Segoe UI'; color: #FFFFFF; background: transparent; border: none; }"
    _MODE_LBL_STYLE_INACT = "QLabel { font: 600 15px 'Inter Tight', 'Segoe UI'; color: #888888; background: transparent; border: none; }"

    def _add_mode_buttons(self, layout: QVBoxLayout):
        """Fila CALL / SET estilo tab segmented control."""
        # Wrapper: fondo tenue que da contexto de "pestaña"
        wrapper = QFrame(self._container)
        wrapper.setStyleSheet(
            "QFrame { background-color: #EBEBEB; border-radius: 10px; border: none; }"
        )
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)

        def make_btn(label_text, icon_name):
            frame = QFrame(wrapper)
            frame.setFixedHeight(58)
            frame.setCursor(Qt.PointingHandCursor)
            hbox = QHBoxLayout(frame)
            hbox.setContentsMargins(10, 6, 10, 6)
            hbox.setSpacing(8)
            hbox.addStretch()
            icon = QSvgWidget(os.path.join(self._BASE_DIR, icon_name), frame)
            icon.setFixedSize(26, 26)
            lbl = QLabel(label_text, frame)
            lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            hbox.addWidget(icon)
            hbox.addWidget(lbl)
            hbox.addStretch()
            frame._label = lbl
            return frame

        self.call_frame = make_btn("CALL", "camera.svg")
        self.set_frame  = make_btn("SET",  "edit.svg")

        # Estado inicial: CALL activo
        self.set_active_mode('call')

        row.addWidget(self.set_frame)
        row.addWidget(self.call_frame)
        layout.addWidget(wrapper)

    def _add_camera_selector(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Camera Selection', self._container))

        cam_row = QFrame(self._container)
        cam_row.setStyleSheet("QFrame { background: transparent; border: none; }")
        row = QHBoxLayout(cam_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        mw.Cam1 = _IndicatorButton('Platform', cam_row)
        mw.Cam1.setCheckable(True)
        mw.Cam1.setAutoExclusive(True)
        mw.Cam1.setChecked(True)
        mw.Cam1.setToolTip('Select Platform Camera')
        mw.Cam1.setStyleSheet(self.TOGGLE_STYLE)
        mw.Cam1.setFixedHeight(62)

        mw.Cam2 = _IndicatorButton('Comments', cam_row)
        mw.Cam2.setCheckable(True)
        mw.Cam2.setAutoExclusive(True)
        mw.Cam2.setToolTip('Select Comments Camera')
        mw.Cam2.setStyleSheet(self.TOGGLE_STYLE)
        mw.Cam2.setFixedHeight(62)

        row.addWidget(mw.Cam1)
        row.addWidget(mw.Cam2)
        layout.addWidget(cam_row)

        # ── ON AIR indicator (oculto hasta que ATEM confirme conexión) ──────
        self._on_air_label = QLabel('● STANDBY', self._container)
        self._on_air_label.setAlignment(Qt.AlignCenter)
        self._on_air_label.setFixedHeight(34)
        self._on_air_label.setStyleSheet(self._ON_AIR_STYLE_STANDBY)
        self._on_air_label.hide()
        layout.addWidget(self._on_air_label)

        mw.Camgroup = QButtonGroup(mw)
        mw.Camgroup.addButton(mw.Cam1)
        mw.Camgroup.addButton(mw.Cam2)
        mw.Cam1.clicked.connect(mw._update_backlight_ui)
        mw.Cam2.clicked.connect(mw._update_backlight_ui)
        mw.Cam1.clicked.connect(mw._update_focus_ui)
        mw.Cam2.clicked.connect(mw._update_focus_ui)
        mw.Cam1.clicked.connect(mw._update_exposure_ui)
        mw.Cam2.clicked.connect(mw._update_exposure_ui)
        mw.Cam1.clicked.connect(lambda: self.set_joystick_mode('platform'))
        mw.Cam2.clicked.connect(lambda: self.set_joystick_mode('comments'))
        mw.Cam1.clicked.connect(mw._update_controls_visibility)
        mw.Cam2.clicked.connect(mw._update_controls_visibility)

    def _add_ptz_block(self, layout: QVBoxLayout):
        """Bloque unificado: Joystick con anillo de zoom + botones +/- a la derecha."""
        mw = self._mw

        block = QFrame(self._container)
        block.setStyleSheet(
            "QFrame { background-color: #F2F2F2; border-radius: 12px; border: none; }"
        )
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 8, 0, 8)
        bl.setSpacing(6)

        # ── Slot del joystick (incluirá el anillo de zoom pintado) ───────────
        joy_size = 374
        slot = QWidget(block)
        slot.setFixedSize(joy_size, joy_size)
        self._joystick_slot = slot

        # Slider oculto — conserva toda la lógica VISCA existente
        mw.ZoomSlider = QSlider(Qt.Vertical)
        mw.ZoomSlider.setRange(0, 100)
        mw.ZoomSlider.setValue(0)
        mw.ZoomSlider.hide()

        # ── Columna derecha: botón +, lectura %, botón − ──────────────────────
        right_col = QWidget(block)
        right_col.setFixedWidth(60)
        rc_lay = QVBoxLayout(right_col)
        rc_lay.setContentsMargins(0, 0, 0, 0)
        rc_lay.setSpacing(10)
        rc_lay.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self._zoom_plus_btn = _CircleButton('+', right_col)
        self._zoom_plus_btn.setFixedSize(38, 38)

        mw.ZoomValueLabel = QLabel('0%', right_col)
        mw.ZoomValueLabel.setAlignment(Qt.AlignCenter)
        mw.ZoomValueLabel.setStyleSheet(
            "font: 600 12px 'IBM Plex Mono', 'Consolas'; color: #666666;")

        zoom_lbl = QLabel('ZOOM', right_col)
        zoom_lbl.setAlignment(Qt.AlignCenter)
        zoom_lbl.setStyleSheet(
            "font: 700 8px 'Inter Tight', 'Segoe UI'; color: #AAAAAA; letter-spacing: 1px;")

        self._zoom_minus_btn = _CircleButton('−', right_col)
        self._zoom_minus_btn.setFixedSize(38, 38)

        rc_lay.addStretch()
        rc_lay.addWidget(self._zoom_plus_btn, alignment=Qt.AlignHCenter)
        rc_lay.addWidget(mw.ZoomValueLabel)
        rc_lay.addWidget(zoom_lbl)
        rc_lay.addWidget(self._zoom_minus_btn, alignment=Qt.AlignHCenter)
        rc_lay.addStretch()

        joy_right_row = QHBoxLayout()
        joy_right_row.setSpacing(0)
        joy_right_row.addWidget(slot, alignment=Qt.AlignTop)
        joy_right_row.addSpacing(12)
        joy_right_row.addWidget(right_col, alignment=Qt.AlignVCenter)
        bl.addLayout(joy_right_row)

        # ── HOME manual (solo visible si ATEM no detectado) ──────────────
        self._home_btn = QPushButton('⌂   Comments → Home', block)
        self._home_btn.setFixedHeight(44)
        self._home_btn.setContentsMargins(0, 0, 0, 0)
        self._home_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #E8A020, stop:1 #B06010);"
            "  border: none; border-radius: 10px;"
            "  font: 700 14px 'Inter Tight', 'Segoe UI'; color: white;"
            "}"
            "QPushButton:pressed { background: #805010; }"
        )
        self._home_btn.clicked.connect(mw._visca._send_comments_cam_home)
        self._home_btn.hide()
        bl.addSpacing(6)
        bl.addWidget(self._home_btn)

        # Debounce: slider oculto → VISCA (lógica sin cambios)
        mw._zoom_timer = QtCore.QTimer(block)
        mw._zoom_timer.setSingleShot(True)
        mw._zoom_timer.setInterval(150)
        mw._zoom_timer.timeout.connect(mw._visca.ZoomAbsolute)
        mw.ZoomSlider.valueChanged.connect(
            lambda v: (mw.ZoomValueLabel.setText(f"{v}%"), mw._zoom_timer.start()))

        mw.Cam1.clicked.connect(mw._visca._refresh_zoom_slider)
        mw.Cam2.clicked.connect(mw._visca._refresh_zoom_slider)

        # ── Display de estado de cámara simulada (solo en modo sim) ──────────
        import sim_mode as _sm
        if _sm.is_active():
            import hardware_simulator as _hw

            bl.addSpacing(8)
            sim_lbl = QLabel("", block)
            sim_lbl.setAlignment(Qt.AlignCenter)
            sim_lbl.setWordWrap(True)
            sim_lbl.setStyleSheet(
                "font: 700 16px 'IBM Plex Mono', 'Consolas'; color: #222;"
                " background: #E0E0E0; border-radius: 8px; padding: 12px 14px;"
            )
            bl.addWidget(sim_lbl)

            def _refresh_sim_lbl():
                cam = _hw.active_cam1 if mw.Cam1.isChecked() else _hw.active_cam2
                if cam is None:
                    return
                with cam._lock:
                    z    = int(cam.zoom / 0x4000 * 100)
                    p    = int(cam.pan)
                    t    = int(cam.tilt)
                    ps   = int(cam.pan_spd)
                    ts   = int(cam.tilt_spd)
                    last = cam.last_cmd or "-"
                sim_lbl.setText(
                    f"zoom  {z:3d}%\n"
                    f"pan   {p:+7d}   spd {ps:2d}\n"
                    f"tilt  {t:+7d}   spd {ts:2d}\n"
                    f"cmd   {last}"
                )

            _sim_timer = QtCore.QTimer(block)
            _sim_timer.setInterval(150)
            _sim_timer.timeout.connect(_refresh_sim_lbl)
            _sim_timer.start()

        layout.addWidget(block)

    def _add_separator(self, layout: QVBoxLayout):
        layout.addSpacing(14)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(line)
        layout.addSpacing(14)

    def _add_focus_exposure(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Focus & Exposure', self._container))

        self._btn_focus_base_style = (
            "QPushButton {"
            "  background-color: #DCDCDC; border: none; border-radius: 10px;"
            "  font: 600 13px 'Inter Tight', 'Segoe UI'; color: #555555; padding: 4px 0px;"
            "}"
            "QPushButton:pressed { background-color: #B8B8B8; color: #111111; }"
        )

        # Fila superior: foco
        focus_row = QHBoxLayout()
        focus_row.setSpacing(5)
        self.btn_auto_focus   = QPushButton('Auto\nFocus',   self._container)
        self.btn_one_push_af  = QPushButton('One Push\nAF',  self._container)
        self.btn_manual_focus = QPushButton('Manual\nFocus', self._container)
        for btn, tooltip, handler in [
            (self.btn_auto_focus,   'Auto Focus ON',                   mw._visca.AutoFocus),
            (self.btn_one_push_af,  'One-shot autofocus, then manual', mw._visca.OnePushAF),
            (self.btn_manual_focus, 'Manual Focus mode',               mw._visca.ManualFocus),
        ]:
            btn.setFixedHeight(50)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(self._btn_focus_base_style)
            btn.clicked.connect(handler)
            focus_row.addWidget(btn)
        layout.addLayout(focus_row)

        # Fila inferior: exposición + backlight
        exp_row = QHBoxLayout()
        exp_row.setSpacing(5)
        self.btn_darker   = QPushButton('▼ Darker\n0',   self._container)
        self.btn_brighter = QPushButton('▲ Brighter\n0', self._container)
        for btn, tooltip, handler in [
            (self.btn_darker,   'Decrease exposure one step', mw._visca.BrightnessDown),
            (self.btn_brighter, 'Increase exposure one step', mw._visca.BrightnessUp),
        ]:
            btn.setFixedHeight(50)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(self._btn_focus_base_style)
            btn.clicked.connect(handler)
            exp_row.addWidget(btn)

        mw.BtnBacklight = QPushButton('Backlight\nOFF', self._container)
        mw.BtnBacklight.setFixedHeight(50)
        mw.BtnBacklight.setToolTip('Toggle backlight compensation')
        mw._backlight_style_off = (
            "QPushButton { background-color: #DCDCDC; border: none; border-radius: 10px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: #555555; padding: 4px 0px; }"
        )
        mw._backlight_style_on = (
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #F5B820, stop:1 #B87800);"
            " border: none; border-radius: 10px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }"
        )
        mw.BtnBacklight.setStyleSheet(mw._backlight_style_off)
        mw.BtnBacklight.clicked.connect(mw._visca.BacklightToggle)

        # Insertar backlight en posición central
        exp_row.insertWidget(1, mw.BtnBacklight)
        layout.addLayout(exp_row)

    # ── Helpers de feedback visual ─────────────────────────────────────────────

    def set_focus_mode(self, mode: str):
        """Destaca el botón de foco activo (auto/manual). One Push AF nunca persiste."""
        _ACTIVE = (
            "QPushButton { background-color: #2979D9; border: none; border-radius: 10px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }"
        )
        self.btn_auto_focus.setStyleSheet(
            _ACTIVE if mode == 'auto' else self._btn_focus_base_style)
        self.btn_manual_focus.setStyleSheet(
            _ACTIVE if mode == 'manual' else self._btn_focus_base_style)
        self.btn_one_push_af.setStyleSheet(self._btn_focus_base_style)

    def set_exposure_level(self, level: int):
        """Actualiza el texto de los botones Darker/Brighter con el nivel numérico."""
        sign = '+' if level > 0 else ''
        self.btn_darker.setText(f'▼ Darker\n{sign}{level}')
        self.btn_brighter.setText(f'▲ Brighter\n{sign}{level}')

    def _flash_button(self, btn: QPushButton, success: bool, duration_ms: int = 1400):
        """Flash verde (éxito) o rojo (fallo) en el botón, luego restaura el estilo base."""
        color = '#3d9e3d' if success else '#b33030'
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border: none; border-radius: 10px;"
            f" font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }}"
        )
        QtCore.QTimer.singleShot(
            duration_ms, lambda: btn.setStyleSheet(self._btn_focus_base_style))


    def set_atem_connected(self, connected: bool):
        """Muestra/oculta el indicador ON AIR y el botón HOME según si el ATEM está disponible."""
        self._on_air_label.setVisible(connected)
        self._home_btn.setVisible(not connected)
        QtCore.QTimer.singleShot(0, self._fit_container_height)

    def set_atem_program(self, input_num: int):
        """Actualiza el indicador ON AIR según el input de programa del ATEM.
        Input 3 = Platform (cam 1), Input 2 = Comments (cam 2).
        """
        if input_num == 3:
            text  = '● ON AIR — Platform'
            style = self._ON_AIR_STYLE_LIVE
        elif input_num == 2:
            text  = '● ON AIR — Comments'
            style = self._ON_AIR_STYLE_LIVE
        else:
            text  = '● STANDBY'
            style = self._ON_AIR_STYLE_STANDBY
        self._on_air_label.setText(text)
        self._on_air_label.setStyleSheet(style)

    def _add_config_buttons(self, layout: QVBoxLayout):
        mw = self._mw

        sep = QFrame(self._container)
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(sep)
        layout.addSpacing(10)

        gear_row = QHBoxLayout()
        gear_row.setSpacing(8)

        btn_gear = QPushButton('⚙  Settings', self._container)
        btn_gear.setFixedHeight(36)
        btn_gear.setToolTip('Camera configuration')
        btn_gear.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,50); border: 1px solid #B8B8B8;"
            " border-radius: 8px; font: 600 13px 'Inter Tight', 'Segoe UI'; color: #444; padding: 0 14px; }"
            "QPushButton:pressed { background: rgba(80,80,80,120); }"
        )
        btn_gear.clicked.connect(mw._open_config_dialog)
        gear_row.addWidget(btn_gear, stretch=1)
        self._btn_gear = btn_gear
        self._gear_sep = sep
        self._btn_gear.hide()
        self._gear_sep.hide()

        layout.addLayout(gear_row)


# ── Widgets personalizados ────────────────────────────────────────────────────

class _IndicatorButton(QPushButton):
    """QPushButton con dos indicadores pintados:
      - Esquina superior derecha: punto rojo cuando está seleccionado (checked).
      - Esquina superior izquierda: LED verde/rojo de estado de conexión, siempre visible.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connected: bool = False  # False = desconectado, True = conectado

    def set_connected(self, connected: bool):
        """Actualiza el estado de conexión y repinta el botón."""
        if connected != self._connected:
            self._connected = connected
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = 5
        margin = 8

        # ── LED de conexión (esquina superior izquierda) ─────────────────
        lx = margin
        ly = margin
        if self._connected:
            outer_halo = QColor(35, 170, 70, 46)   # outer glow ring
            inner_halo = QColor(35, 170, 70, 102)  # inner glow ring
            core_color = QColor(95, 217, 127, 230) # bright core
        else:
            outer_halo = QColor(190, 35, 35, 46)
            inner_halo = QColor(190, 35, 35, 115)
            core_color = QColor(224, 80, 80, 230)
        painter.setPen(Qt.NoPen)
        # Outer glow ring (largest, most transparent)
        painter.setBrush(outer_halo)
        painter.drawEllipse(lx - 5, ly - 5, r * 2 + 10, r * 2 + 10)
        # Inner glow ring
        painter.setBrush(inner_halo)
        painter.drawEllipse(lx - 2, ly - 2, r * 2 + 4, r * 2 + 4)
        # Bright core
        painter.setBrush(core_color)
        painter.drawEllipse(lx, ly, r * 2, r * 2)

        painter.end()


class _CircleButton(QLabel):
    """Botón circular con símbolo centrado garantizado vía paintEvent manual."""

    clicked = pyqtSignal()

    _S_NORMAL  = "QLabel { background:#FFFFFF; border:1.5px solid #E0E0E0; border-radius:19px; }"
    _S_HOVER   = "QLabel { background:#F2F2F2; border:1.5px solid #BBBBBB; border-radius:19px; }"
    _S_PRESSED = "QLabel { background:#E0E0E0; border:1.5px solid #BBBBBB; border-radius:19px; }"
    _FONT      = QFont('Inter Tight', 20, QFont.Bold)

    def __init__(self, symbol: str, parent=None):
        super().__init__('', parent)        # texto vacío: QLabel no dibuja nada
        self._symbol = symbol
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._S_NORMAL)

    def paintEvent(self, event):
        super().paintEvent(event)           # fondo + borde del stylesheet
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self._FONT)
        p.setPen(QColor('#444444'))
        p.drawText(self.rect(), Qt.AlignCenter, self._symbol)
        p.end()

    def enterEvent(self, _):
        self.setStyleSheet(self._S_HOVER)

    def leaveEvent(self, _):
        self.setStyleSheet(self._S_NORMAL)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setStyleSheet(self._S_PRESSED)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setStyleSheet(self._S_NORMAL)
            if self.rect().contains(event.pos()):
                self.clicked.emit()


# ── Helpers de módulo ─────────────────────────────────────────────────────────

def _section_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("font: 600 15px 'Inter Tight', 'Segoe UI'; color: #555555; padding-bottom: 10px;")
    return lbl
