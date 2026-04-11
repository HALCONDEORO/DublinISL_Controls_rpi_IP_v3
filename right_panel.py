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
#   mw.BtnCall, mw.BtnSet, mw.PresetModeGroup
#   mw.BtnBacklight, mw._backlight_style_off, mw._backlight_style_on

from __future__ import annotations

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSlider, QSpacerItem,
    QVBoxLayout, QWidget,
)

from config import SPEED_MIN, SPEED_MAX, SPEED_DEFAULT
from config_dialog import ConfigDialog


class RightPanel:
    """
    Construye el panel derecho usando layouts (sin coordenadas absolutas).
    El container blanco ocupa (1490, 10, 380, 1062) sobre el fondo gris.
    Todos los widgets son hijos del container, pero sus referencias
    se asignan como atributos de main_window para compatibilidad total.
    """

    # Estilos del slider de zoom — misma paleta que el joystick
    _ZOOM_STYLE = (
        "QSlider::groove:horizontal {{"
        "  background: #E0E0E0; height: 6px; border-radius: 3px;"
        "}}"
        "QSlider::sub-page:horizontal {{"
        "  background: {fill}; border-radius: 3px;"
        "}}"
        "QSlider::handle:horizontal {{"
        "  background: {handle}; border: 2px solid {border};"
        "  width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;"
        "}}"
    )
    _ZOOM_STYLE_PLATFORM = _ZOOM_STYLE.format(
        fill='#9B3A3A', handle='#B41E1E', border='#6E1212')  # burdeo
    _ZOOM_STYLE_COMMENTS = _ZOOM_STYLE.format(
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

    def set_joystick_mode(self, mode: str):
        """'platform' → burdeo  |  'comments' → verde."""
        if hasattr(self, '_joystick'):
            self._joystick.set_mode(mode)

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
            "  background-color: #FFFFFF;"
            "  border-radius: 8px;"
            "  border: none;"
            "}"
        )
        self._container.setObjectName("RightPanelContainer")

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(14, 16, 14, 10)
        layout.setSpacing(7)

        self._add_camera_selector(layout)
        self._add_speed_slider(layout)
        self._add_preset_mode(layout)
        self._add_zoom_buttons(layout)
        self._add_joystick_slot(layout)
        self._add_separator(layout)
        self._add_focus_exposure(layout)
        self._add_config_buttons(layout)

    # ── Secciones ─────────────────────────────────────────────────────────────

    def _add_camera_selector(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Camera Selection', self._container))

        toggle = _toggle_frame(self._container)
        row = QHBoxLayout(toggle)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(0)

        mw.Cam1 = _IndicatorButton('Platform', toggle)
        mw.Cam1.setCheckable(True)
        mw.Cam1.setAutoExclusive(True)
        mw.Cam1.setChecked(True)
        mw.Cam1.setToolTip('Select Platform Camera')
        mw.Cam1.setStyleSheet(self.TOGGLE_STYLE)
        mw.Cam1.setFixedHeight(62)

        mw.Cam2 = _IndicatorButton('Comments', toggle)
        mw.Cam2.setCheckable(True)
        mw.Cam2.setAutoExclusive(True)
        mw.Cam2.setToolTip('Select Comments Camera')
        mw.Cam2.setStyleSheet(self.TOGGLE_STYLE)
        mw.Cam2.setFixedHeight(62)

        row.addWidget(mw.Cam1)
        row.addWidget(mw.Cam2)
        layout.addWidget(toggle)

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

    def _add_speed_slider(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('PTZ Speed', self._container))

        row = QHBoxLayout()
        row.setSpacing(6)

        slow = QLabel('SLOW', self._container)
        slow.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slow.setStyleSheet("font: bold 13px; color: #444;")
        slow.setFixedWidth(38)

        mw.SpeedSlider = QSlider(Qt.Horizontal, self._container)
        mw.SpeedSlider.setMinimum(SPEED_MIN)
        mw.SpeedSlider.setMaximum(SPEED_MAX)
        mw.SpeedSlider.setValue(SPEED_DEFAULT)
        mw.SpeedSlider.setTickPosition(QSlider.TicksBelow)
        mw.SpeedSlider.setTickInterval(3)
        mw.SpeedSlider.setFixedHeight(48)
        mw.SpeedSlider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px; background: #E0E0E0; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: white; border: 2px solid #7DC47D;
                width: 22px; height: 22px; margin: -9px 0; border-radius: 11px;
            }
            QSlider::sub-page:horizontal {
                background: #7DC47D; border-radius: 3px;
            }
        """)

        fast = QLabel('FAST', self._container)
        fast.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        fast.setStyleSheet("font: bold 13px; color: #444;")
        fast.setFixedWidth(38)

        row.addWidget(slow)
        row.addWidget(mw.SpeedSlider)
        row.addWidget(fast)
        layout.addLayout(row)

        mw.SpeedValueLabel = QLabel(
            mw._speed_label_text(SPEED_DEFAULT), self._container)
        mw.SpeedValueLabel.setAlignment(Qt.AlignCenter)
        mw.SpeedValueLabel.setStyleSheet("font: 12px; color: #555;")
        layout.addWidget(mw.SpeedValueLabel)

        mw.SpeedSlider.valueChanged.connect(mw._on_speed_changed)

    def _add_preset_mode(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Camera Presets', self._container))

        toggle = _toggle_frame(self._container)
        row = QHBoxLayout(toggle)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(0)

        mw.BtnCall = QPushButton('Call', toggle)
        mw.BtnCall.setCheckable(True)
        mw.BtnCall.setAutoExclusive(True)
        mw.BtnCall.setChecked(True)
        mw.BtnCall.setStyleSheet(self.TOGGLE_STYLE)
        mw.BtnCall.setFixedHeight(62)

        mw.BtnSet = QPushButton('Set', toggle)
        mw.BtnSet.setCheckable(True)
        mw.BtnSet.setAutoExclusive(True)
        mw.BtnSet.setStyleSheet(self.TOGGLE_STYLE)
        mw.BtnSet.setFixedHeight(62)

        row.addWidget(mw.BtnCall)
        row.addWidget(mw.BtnSet)
        layout.addWidget(toggle)

        mw.PresetModeGroup = QButtonGroup(mw)
        mw.PresetModeGroup.addButton(mw.BtnCall)
        mw.PresetModeGroup.addButton(mw.BtnSet)
        mw.BtnCall.clicked.connect(mw._on_preset_mode_changed)
        mw.BtnSet.clicked.connect(mw._on_preset_mode_changed)

    def _add_zoom_buttons(self, layout: QVBoxLayout):
        mw = self._mw

        header = QHBoxLayout()
        header.addWidget(_section_label('Zoom', self._container))
        mw.ZoomValueLabel = QLabel("0%", self._container)
        mw.ZoomValueLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        mw.ZoomValueLabel.setStyleSheet("font: 600 14px 'Segoe UI'; color: #444444;")
        header.addWidget(mw.ZoomValueLabel)
        layout.addLayout(header)

        mw.ZoomSlider = QSlider(Qt.Horizontal, self._container)
        mw.ZoomSlider.setRange(0, 100)
        mw.ZoomSlider.setValue(0)
        mw.ZoomSlider.setTickPosition(QSlider.TicksBelow)
        mw.ZoomSlider.setTickInterval(10)
        mw.ZoomSlider.setStyleSheet(self._ZOOM_STYLE_PLATFORM)  # Cam1 activa por defecto
        layout.addWidget(mw.ZoomSlider)

        # Debounce: envía zoom cada 150 ms mientras se arrastra; al soltar, envío inmediato
        mw._zoom_timer = QtCore.QTimer(self._container)
        mw._zoom_timer.setSingleShot(True)
        mw._zoom_timer.setInterval(150)
        mw._zoom_timer.timeout.connect(mw.ZoomAbsolute)
        mw.ZoomSlider.valueChanged.connect(
            lambda v: (mw.ZoomValueLabel.setText(f"{v}%"), mw._zoom_timer.start()))
        mw.ZoomSlider.sliderReleased.connect(
            lambda: (mw._zoom_timer.stop(), mw.ZoomAbsolute()))

        mw.Cam1.clicked.connect(mw._refresh_zoom_slider)
        mw.Cam2.clicked.connect(mw._refresh_zoom_slider)
        mw.Cam1.clicked.connect(
            lambda: mw.ZoomSlider.setStyleSheet(self._ZOOM_STYLE_PLATFORM))
        mw.Cam2.clicked.connect(
            lambda: mw.ZoomSlider.setStyleSheet(self._ZOOM_STYLE_COMMENTS))

    def _add_joystick_slot(self, layout: QVBoxLayout):
        """Reserva un bloque cuadrado centrado para el DigitalJoystick."""
        size = 310
        slot = QWidget(self._container)
        slot.setFixedSize(size, size)
        self._joystick_slot = slot

        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(slot)
        center_row.addStretch()
        layout.addLayout(center_row)

    def _add_separator(self, layout: QVBoxLayout):
        line = QFrame(self._container)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(line)

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
            (self.btn_auto_focus,   'Auto Focus ON',                   mw.AutoFocus),
            (self.btn_one_push_af,  'One-shot autofocus, then manual', mw.OnePushAF),
            (self.btn_manual_focus, 'Manual Focus mode',               mw.ManualFocus),
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
            (self.btn_darker,   'Decrease exposure one step', mw.BrightnessDown),
            (self.btn_brighter, 'Increase exposure one step', mw.BrightnessUp),
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
        mw.BtnBacklight.clicked.connect(mw.BacklightToggle)

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

        gear_row = QHBoxLayout()
        gear_row.addStretch()
        btn_gear = QPushButton('⚙', self._container)
        btn_gear.setFixedSize(40, 40)
        btn_gear.setToolTip('Camera configuration')
        btn_gear.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,60); border: 1px solid #999;"
            " border-radius: 6px; font: 18px; color: #444; }"
            "QPushButton:pressed { background: rgba(80,80,80,140); }"
        )
        btn_gear.clicked.connect(mw._open_config_dialog)
        gear_row.addWidget(btn_gear)
        layout.addLayout(gear_row)

        btn_close = QPushButton('Close window', self._container)
        btn_close.setFixedHeight(24)
        btn_close.setStyleSheet(
            "background-color: lightgrey; font: 15px; color: black; border: none;")
        btn_close.clicked.connect(mw.Quit)
        layout.addWidget(btn_close)


# ── Widgets personalizados ────────────────────────────────────────────────────

class _IndicatorButton(QPushButton):
    """QPushButton que dibuja un pequeño punto rojo tenue en la esquina
    superior derecha cuando el botón está seleccionado (checked)."""

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = 5
        margin = 8
        x = self.width() - r * 2 - margin
        y = margin
        # Halo tenue
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(220, 50, 50, 50))
        painter.drawEllipse(x - 2, y - 2, r * 2 + 4, r * 2 + 4)
        # Punto rojo principal
        painter.setBrush(QColor(210, 45, 45, 180))
        painter.drawEllipse(x, y, r * 2, r * 2)
        painter.end()


# ── Helpers de módulo ─────────────────────────────────────────────────────────

def _section_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("font: 600 15px 'Segoe UI'; color: #555555;")
    return lbl


def _toggle_frame(parent: QWidget) -> QFrame:
    frame = QFrame(parent)
    frame.setStyleSheet(
        "QFrame { background-color: #E8E8E8; border-radius: 12px; border: none; }"
    )
    return frame
