#!/usr/bin/env python3
# right_panel.py — Panel derecho de controles PTZ (layout-based)
#
# Todos los widgets viven dentro de un QFrame container con QVBoxLayout.
# Se eliminan las coordenadas absolutas; la estructura visual es idéntica
# a la versión anterior pero el panel se adapta al container blanco.
#
# Atributos que crea en main_window:
#   mw.Cam1, mw.Cam2, mw.Camgroup
#   mw.SpeedSlider, mw.SpeedValueLabel
#   mw.BtnBacklight, mw._backlight_style_off, mw._backlight_style_on
# Nota: mw.BtnCall, mw.BtnSet y mw.PresetModeGroup se crean en main_window._build_mode_buttons()
#   Los frames visuales call_frame/set_frame se crean aquí (_add_mode_buttons) y se exponen como
#   self.call_frame y self.set_frame para que main_window los conecte con la lógica de estado.

from __future__ import annotations

import os

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from config import SPEED_MIN, SPEED_MAX, SPEED_DEFAULT


class RightPanel:
    """
    Construye el panel derecho usando layouts (sin coordenadas absolutas).
    El container blanco ocupa (1490, 10, 380, 1062) sobre el fondo gris.
    Todos los widgets son hijos del container, pero sus referencias
    se asignan como atributos de main_window para compatibilidad total.
    """

    # Estilo base compartido para ambos sliders — handle 22 px, groove 6 px
    _SLIDER_STYLE = (
        "QSlider::groove:horizontal {{"
        "  background: #E0E0E0; height: 6px; border-radius: 3px;"
        "}}"
        "QSlider::sub-page:horizontal {{"
        "  background: {fill}; border-radius: 3px;"
        "}}"
        "QSlider::handle:horizontal {{"
        "  background: {handle}; border: 2px solid {border};"
        "  width: 22px; height: 22px; margin: -9px 0; border-radius: 11px;"
        "}}"
    )
    _SLIDER_STYLE_PLATFORM = _SLIDER_STYLE.format(
        fill='#9B3A3A', handle='#B41E1E', border='#6E1212')  # burdeo
    _SLIDER_STYLE_COMMENTS = _SLIDER_STYLE.format(
        fill='#64B464', handle='#7DC47D', border='#3A8A3A')  # verde

    # Estilo vertical para el slider de zoom (a la derecha del joystick)
    # Con invertedAppearance=True el handle sube al aumentar el valor;
    # add-page:vertical es la zona DEBAJO del handle → se llena de abajo hacia arriba.
    _ZOOM_VERTICAL_STYLE = (
        "QSlider:vertical {{"
        "  padding: 11px 0px;"
        "}}"
        "QSlider::groove:vertical {{"
        "  background: #E0E0E0; width: 6px; border-radius: 3px;"
        "}}"
        "QSlider::add-page:vertical {{"
        "  background: {fill}; border-radius: 3px;"
        "}}"
        "QSlider::handle:vertical {{"
        "  background: {handle}; border: 2px solid {border};"
        "  width: 22px; height: 22px; margin: 0 -9px; border-radius: 11px;"
        "}}"
    )
    _ZOOM_STYLE_PLATFORM = _ZOOM_VERTICAL_STYLE.format(
        fill='#9B3A3A', handle='#B41E1E', border='#6E1212')  # burdeo
    _ZOOM_STYLE_COMMENTS = _ZOOM_VERTICAL_STYLE.format(
        fill='#64B464', handle='#7DC47D', border='#3A8A3A')  # verde

    TOGGLE_STYLE = (
        "QPushButton {"
        "  background-color: #DCDCDC; border: none; border-radius: 10px;"
        "  font: 600 18px 'Segoe UI'; color: #777777; padding: 6px 0px;"
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
        slot = self._joystick_slot
        self._joystick = DigitalJoystick(slot, None, None, slot.width(),
                                         handlers, stop_handler, speed_provider)

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
        outer.setGeometry(1490, 0, 430, 1080)
        outer.setStyleSheet("QFrame { background-color: #B0B0B0; border: none; }")
        outer.lower()

    # ── Container principal con layout ────────────────────────────────────────

    def _build_panel(self):
        mw = self._mw

        # Container blanco — hijo directo de mw, posicionado absolutamente
        self._container = QFrame(mw)
        self._container.setGeometry(1490, 10, 380, 1062)
        self._container.setStyleSheet(
            "QFrame#RightPanelContainer {"
            "  background-color: #F4F4F6;"
            "  border-radius: 8px;"
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
        no_cam_text.setStyleSheet("QLabel { font: 700 22px 'Segoe UI'; color: #AAAAAA; }")
        no_cam_layout.addWidget(no_cam_icon, 0, Qt.AlignCenter)
        no_cam_layout.addWidget(no_cam_text, 0, Qt.AlignCenter)
        self._no_camera_label = no_cam_container
        self._no_camera_label.hide()
        layout.addWidget(self._no_camera_label)

        layout.addSpacing(20)
        self._add_config_buttons(layout)

        QtCore.QTimer.singleShot(0, self._fit_container_height)

    def _fit_container_height(self):
        """Ajusta la altura del container exactamente al contenido."""
        h = self._container.sizeHint().height()
        self._container.setGeometry(1490, 10, 380, h)

    # ── Secciones ─────────────────────────────────────────────────────────────

    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    _MODE_STYLE_ACTIVE_CALL = (
        "QFrame { background-color: #9B3A3A; border-radius: 8px; border: none; }"
    )
    _MODE_STYLE_ACTIVE_SET = (
        "QFrame { background-color: #4A8C4A; border-radius: 8px; border: none; }"
    )
    _MODE_STYLE_INACTIVE = (
        "QFrame { background-color: transparent; border-radius: 8px; border: none; }"
    )
    _MODE_LBL_STYLE_ACT   = "QLabel { font: 700 15px 'Segoe UI'; color: #FFFFFF; background: transparent; border: none; }"
    _MODE_LBL_STYLE_INACT = "QLabel { font: 600 15px 'Segoe UI'; color: #888888; background: transparent; border: none; }"

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
        """Bloque unificado: Speed (fila superior) · Joystick + Zoom (fila inferior)."""
        mw = self._mw

        block = QFrame(self._container)
        block.setStyleSheet(
            "QFrame { background-color: #F2F2F2; border-radius: 12px; border: none; }"
        )
        bl = QVBoxLayout(block)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(6)

        # ── Fila 1: Speed label dinámico ──────────────────────────────────────
        mw.SpeedTitleLabel = QLabel(f'Speed  <b>({SPEED_DEFAULT})</b>', block)
        mw.SpeedTitleLabel.setTextFormat(Qt.RichText)
        mw.SpeedTitleLabel.setAlignment(Qt.AlignCenter)
        mw.SpeedTitleLabel.setStyleSheet("font: 15px 'Segoe UI'; color: #555555; padding-bottom: 10px;")
        bl.addWidget(mw.SpeedTitleLabel)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)

        slow = QLabel('SLOW', block)
        slow.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slow.setStyleSheet("font: bold 13px; color: #444;")
        slow.setFixedWidth(38)

        mw.SpeedSlider = QSlider(Qt.Horizontal, block)
        mw.SpeedSlider.setMinimum(SPEED_MIN)
        mw.SpeedSlider.setMaximum(SPEED_MAX)
        mw.SpeedSlider.setValue(SPEED_DEFAULT)
        mw.SpeedSlider.setTickPosition(QSlider.TicksBelow)
        mw.SpeedSlider.setTickInterval(3)
        mw.SpeedSlider.setFixedHeight(48)
        mw.SpeedSlider.setStyleSheet(self._SLIDER_STYLE_PLATFORM)

        fast = QLabel('FAST', block)
        fast.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        fast.setStyleSheet("font: bold 13px; color: #444;")
        fast.setFixedWidth(38)

        speed_row.addWidget(slow)
        speed_row.addWidget(mw.SpeedSlider)
        speed_row.addWidget(fast)
        bl.addLayout(speed_row)

        mw.SpeedSlider.valueChanged.connect(mw._visca._on_speed_changed)
        mw.Cam1.clicked.connect(
            lambda: mw.SpeedSlider.setStyleSheet(self._SLIDER_STYLE_PLATFORM))
        mw.Cam2.clicked.connect(
            lambda: mw.SpeedSlider.setStyleSheet(self._SLIDER_STYLE_COMMENTS))

        # ── Fila 2: Joystick (izquierda) + Zoom vertical (derecha) ───────────
        joy_size = 248
        slot = QWidget(block)
        slot.setFixedSize(joy_size, joy_size)
        self._joystick_slot = slot

        # Contenedor zoom con altura fija = joystick → slider arriba, label abajo
        zoom_w = QWidget(block)
        zoom_w.setFixedSize(56, joy_size)
        zoom_lay = QVBoxLayout(zoom_w)
        zoom_lay.setContentsMargins(0, 0, 0, 0)
        zoom_lay.setSpacing(4)

        mw.ZoomSlider = QSlider(Qt.Vertical, zoom_w)
        mw.ZoomSlider.setRange(0, 100)
        mw.ZoomSlider.setValue(0)
        mw.ZoomSlider.setTickPosition(QSlider.TicksRight)
        mw.ZoomSlider.setTickInterval(10)
        mw.ZoomSlider.setFixedHeight(joy_size - 44)
        mw.ZoomSlider.setStyleSheet(self._ZOOM_STYLE_PLATFORM)
        zoom_lay.addWidget(mw.ZoomSlider, alignment=Qt.AlignHCenter)

        mw.ZoomValueLabel = QLabel("0%", zoom_w)
        mw.ZoomValueLabel.setAlignment(Qt.AlignCenter)
        mw.ZoomValueLabel.setStyleSheet("font: 600 13px 'Segoe UI'; color: #444444;")
        zoom_lay.addWidget(mw.ZoomValueLabel)

        zoom_title = _section_label('Zoom', zoom_w)
        zoom_title.setAlignment(Qt.AlignCenter)
        zoom_lay.addWidget(zoom_title)

        # Debounce: envía zoom cada 150 ms mientras se arrastra; al soltar, envío inmediato
        mw._zoom_timer = QtCore.QTimer(block)
        mw._zoom_timer.setSingleShot(True)
        mw._zoom_timer.setInterval(150)
        mw._zoom_timer.timeout.connect(mw._visca.ZoomAbsolute)
        mw.ZoomSlider.valueChanged.connect(
            lambda v: (mw.ZoomValueLabel.setText(f"{v}%"), mw._zoom_timer.start()))
        mw.ZoomSlider.sliderReleased.connect(
            lambda: (mw._zoom_timer.stop(), mw._visca.ZoomAbsolute()))

        mw.Cam1.clicked.connect(mw._visca._refresh_zoom_slider)
        mw.Cam2.clicked.connect(mw._visca._refresh_zoom_slider)
        mw.Cam1.clicked.connect(
            lambda: mw.ZoomSlider.setStyleSheet(self._ZOOM_STYLE_PLATFORM))
        mw.Cam2.clicked.connect(
            lambda: mw.ZoomSlider.setStyleSheet(self._ZOOM_STYLE_COMMENTS))

        joy_zoom_row = QHBoxLayout()
        joy_zoom_row.setSpacing(8)
        joy_zoom_row.addStretch()
        joy_zoom_row.addWidget(slot, alignment=Qt.AlignTop)
        joy_zoom_row.addWidget(zoom_w, alignment=Qt.AlignTop)
        joy_zoom_row.addStretch()
        bl.addLayout(joy_zoom_row)

        # ── Display de estado de cámara simulada (solo en modo sim) ──────────
        import sim_mode as _sm
        if _sm.is_active():
            import hardware_simulator as _hw

            bl.addSpacing(42)
            sim_lbl = QLabel("", block)
            sim_lbl.setAlignment(Qt.AlignCenter)
            sim_lbl.setWordWrap(True)
            sim_lbl.setStyleSheet(
                "font: 14px 'Consolas'; color: #333;"
                " background: #E8E8E8; border-radius: 6px; padding: 8px 10px;"
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
                    last = (cam.last_cmd or "-")[:20]
                sim_lbl.setText(
                    f"zoom {z:3d}%\n"
                    f"pan  {p:+6d}   tilt {t:+6d}\n"
                    f"{last}"
                )

            _sim_timer = QtCore.QTimer(block)
            _sim_timer.setInterval(150)
            _sim_timer.timeout.connect(_refresh_sim_lbl)
            _sim_timer.start()

        layout.addWidget(block)

    def _add_separator(self, layout: QVBoxLayout):
        layout.addSpacing(20)
        line = QFrame(self._container)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(line)
        layout.addSpacing(20)

    def _add_focus_exposure(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Focus & Exposure', self._container))

        self._btn_focus_base_style = (
            "QPushButton {"
            "  background-color: #DCDCDC; border: none; border-radius: 10px;"
            "  font: 600 13px 'Segoe UI'; color: #555555; padding: 4px 0px;"
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
            " font: 600 13px 'Segoe UI'; color: #555555; padding: 4px 0px; }"
        )
        mw._backlight_style_on = (
            "QPushButton { background-color: #e6a800; border: none; border-radius: 10px;"
            " font: 600 13px 'Segoe UI'; color: white; padding: 4px 0px; }"
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
            "QPushButton { background-color: #4a90d9; border: none; border-radius: 10px;"
            " font: 600 13px 'Segoe UI'; color: white; padding: 4px 0px; }"
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
            f" font: 600 13px 'Segoe UI'; color: white; padding: 4px 0px; }}"
        )
        QtCore.QTimer.singleShot(
            duration_ms, lambda: btn.setStyleSheet(self._btn_focus_base_style))


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
            " border-radius: 8px; font: 600 13px 'Segoe UI'; color: #444; padding: 0 14px; }"
            "QPushButton:pressed { background: rgba(80,80,80,120); }"
        )
        btn_gear.clicked.connect(mw._open_config_dialog)
        gear_row.addWidget(btn_gear, stretch=1)

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
            halo_color = QColor(40, 180, 80, 60)
            led_color  = QColor(35, 170, 70, 210)
        else:
            halo_color = QColor(200, 40, 40, 60)
            led_color  = QColor(190, 35, 35, 210)
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo_color)
        painter.drawEllipse(lx - 2, ly - 2, r * 2 + 4, r * 2 + 4)
        painter.setBrush(led_color)
        painter.drawEllipse(lx, ly, r * 2, r * 2)

        painter.end()


# ── Helpers de módulo ─────────────────────────────────────────────────────────

def _section_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("font: 600 15px 'Segoe UI'; color: #555555; padding-bottom: 10px;")
    return lbl
