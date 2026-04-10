#!/usr/bin/env python3
# right_panel.py — Construcción del panel derecho de controles PTZ
#
# RightPanel es una clase coordinadora (no hereda de ningún widget Qt).
# Crea todos los widgets como hijos directos del QMainWindow que se le pasa,
# preservando las coordenadas absolutas de pantalla sin ningún ajuste.
#
# Atributos que crea en main_window:
#   mw.Cam1, mw.Cam2, mw.Camgroup
#   mw.SpeedSlider, mw.SpeedValueLabel
#   mw.BtnCall, mw.BtnSet, mw.PresetModeGroup
#   mw.BtnBacklight, mw._backlight_style_off, mw._backlight_style_on

from __future__ import annotations

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QLabel, QPushButton, QSlider,
)

from config import SPEED_MIN, SPEED_MAX, SPEED_DEFAULT
from config_dialog import ConfigDialog


class RightPanel:
    """
    Agrupa la construcción del panel derecho (x=1490..1920).
    Los widgets son hijos del QMainWindow recibido, no de esta clase.
    """

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
        self._build_bg()
        self._build_section_labels()
        self._build_camera_selector()
        self._build_speed_slider()
        self._build_preset_mode()
        self._build_zoom_buttons()
        self._build_focus_exposure()
        self._build_config_buttons()
        # El joystick se construye por separado desde MainWindow (necesita handlers)

    def connect_joystick(self, handlers: dict, stop_handler):
        """Construye el DigitalJoystick con los handlers de movimiento de MainWindow."""
        from joystick import DigitalJoystick
        DigitalJoystick(self._mw, 1500, 510, 310, handlers, stop_handler)

    # ── Fondo del panel ───────────────────────────────────────────────────────

    def _build_bg(self):
        mw = self._mw
        # Fondo exterior oscuro — se manda al fondo absoluto
        outer = QFrame(mw)
        outer.setGeometry(1490, 0, 430, 1080)
        outer.setStyleSheet("QFrame { background-color: #B0B0B0; border: none; }")
        outer.lower()

        # Container interior claro — creado después, queda naturalmente encima del outer
        container = QFrame(mw)
        container.setGeometry(1490, 10, 380, 1062)
        container.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: none; border-radius: 8px; }"
        )
        # Sin lower() ni raise_(): z-order natural lo deja sobre 'outer'

    # ── Labels de sección ─────────────────────────────────────────────────────

    def _build_section_labels(self):
        mw = self._mw
        for text, geom in [
            ('Camera Selection', (1500, 20, 360, 30)),
            ('PTZ Speed',        (1500, 138, 360, 30)),
            ('Camera Presets',   (1500, 253, 360, 30)),
            ('Camera Controls',  (1500, 367, 360, 30)),
        ]:
            lbl = QLabel(text, mw)
            lbl.setGeometry(*geom)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("font: 600 15px 'Segoe UI'; color: #555555;")

    # ── Selector de cámara ────────────────────────────────────────────────────

    def _build_camera_selector(self):
        mw = self._mw
        _make_toggle_frame(mw, 1496, 56, 368, 78)

        mw.Cam1 = QPushButton('Platform', mw)
        mw.Cam1.setGeometry(1500, 60, 180, 70)
        mw.Cam1.setCheckable(True)
        mw.Cam1.setAutoExclusive(True)
        mw.Cam1.setChecked(True)
        mw.Cam1.setToolTip('Select Platform Camera')
        mw.Cam1.setStyleSheet(self.TOGGLE_STYLE)

        mw.Cam2 = QPushButton('Comments', mw)
        mw.Cam2.setGeometry(1680, 60, 180, 70)
        mw.Cam2.setCheckable(True)
        mw.Cam2.setAutoExclusive(True)
        mw.Cam2.setToolTip('Select Comments Camera')
        mw.Cam2.setStyleSheet(self.TOGGLE_STYLE)

        mw.Camgroup = QButtonGroup(mw)
        mw.Camgroup.addButton(mw.Cam1)
        mw.Camgroup.addButton(mw.Cam2)

        mw.Cam1.clicked.connect(mw._update_backlight_ui)
        mw.Cam2.clicked.connect(mw._update_backlight_ui)

    # ── Slider de velocidad ───────────────────────────────────────────────────

    def _build_speed_slider(self):
        mw = self._mw

        slow = QLabel('SLOW', mw)
        slow.setGeometry(1500, 190, 55, 20)
        slow.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        slow.setStyleSheet("font: bold 13px; color: #444")

        mw.SpeedSlider = QSlider(Qt.Horizontal, mw)
        mw.SpeedSlider.setGeometry(1560, 172, 230, 48)
        mw.SpeedSlider.setMinimum(SPEED_MIN)
        mw.SpeedSlider.setMaximum(SPEED_MAX)
        mw.SpeedSlider.setValue(SPEED_DEFAULT)
        mw.SpeedSlider.setTickPosition(QSlider.TicksBelow)
        mw.SpeedSlider.setTickInterval(3)
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

        fast = QLabel('FAST', mw)
        fast.setGeometry(1797, 190, 55, 20)
        fast.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        fast.setStyleSheet("font: bold 13px; color: #444")

        mw.SpeedValueLabel = QLabel(mw._speed_label_text(SPEED_DEFAULT), mw)
        mw.SpeedValueLabel.setGeometry(1500, 224, 360, 20)
        mw.SpeedValueLabel.setAlignment(QtCore.Qt.AlignCenter)
        mw.SpeedValueLabel.setStyleSheet("font: 12px; color: #555")

        mw.SpeedSlider.valueChanged.connect(mw._on_speed_changed)

    # ── Modo preset (Call / Set) ───────────────────────────────────────────────

    def _build_preset_mode(self):
        mw = self._mw
        _make_toggle_frame(mw, 1496, 286, 368, 78)

        mw.BtnCall = QPushButton('Call', mw)
        mw.BtnCall.setGeometry(1500, 290, 180, 70)
        mw.BtnCall.setCheckable(True)
        mw.BtnCall.setAutoExclusive(True)
        mw.BtnCall.setChecked(True)
        mw.BtnCall.setStyleSheet(self.TOGGLE_STYLE)

        mw.BtnSet = QPushButton('Set', mw)
        mw.BtnSet.setGeometry(1680, 290, 180, 70)
        mw.BtnSet.setCheckable(True)
        mw.BtnSet.setAutoExclusive(True)
        mw.BtnSet.setStyleSheet(self.TOGGLE_STYLE)

        mw.PresetModeGroup = QButtonGroup(mw)
        mw.PresetModeGroup.addButton(mw.BtnCall)
        mw.PresetModeGroup.addButton(mw.BtnSet)

        mw.BtnCall.clicked.connect(mw._on_preset_mode_changed)
        mw.BtnSet.clicked.connect(mw._on_preset_mode_changed)

    # ── Botones de zoom ───────────────────────────────────────────────────────

    def _build_zoom_buttons(self):
        mw = self._mw

        zoom_in = QPushButton(mw)
        zoom_in.setGeometry(1680, 403, 100, 100)
        zoom_in.pressed.connect(mw.ZoomIn)
        zoom_in.released.connect(mw.ZoomStop)
        zoom_in.setStyleSheet("background-image: url(ZoomIn_120.png); border: none")

        zoom_out = QPushButton(mw)
        zoom_out.setGeometry(1510, 403, 100, 100)
        zoom_out.pressed.connect(mw.ZoomOut)
        zoom_out.released.connect(mw.ZoomStop)
        zoom_out.setStyleSheet("background-image: url(ZoomOut_120.png); border: none")

    # ── Foco y exposición ─────────────────────────────────────────────────────

    def _build_focus_exposure(self):
        mw = self._mw

        lbl = QLabel('Focus & Exposure', mw)
        lbl.setGeometry(1500, 835, 360, 25)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setStyleSheet("font: bold 16px; color: black")

        _btn_style = (
            "QPushButton{background-color: white; border: 2px solid #555;"
            " font: bold 13px; color: black; border-radius: 4px}"
            "QPushButton:pressed{background-color: #ccc}"
        )

        for label, geom, tooltip, handler in [
            ('Auto\nFocus',    (1500, 863, 110, 50), 'Auto Focus ON',                   mw.AutoFocus),
            ('One Push\nAF',   (1625, 863, 110, 50), 'One-shot autofocus, then manual', mw.OnePushAF),
            ('Manual\nFocus',  (1750, 863, 110, 50), 'Manual Focus mode',               mw.ManualFocus),
            ('▼ Darker',       (1500, 920, 110, 45), 'Decrease exposure one step',      mw.BrightnessDown),
            ('▲ Brighter',     (1750, 920, 110, 45), 'Increase exposure one step',      mw.BrightnessUp),
        ]:
            btn = QPushButton(label, mw)
            btn.setGeometry(*geom)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_btn_style)
            btn.clicked.connect(handler)

        mw.BtnBacklight = QPushButton('Backlight\nOFF', mw)
        mw.BtnBacklight.setGeometry(1625, 920, 110, 45)
        mw.BtnBacklight.setToolTip('Toggle backlight compensation')
        # Estilos guardados en mw para que _update_backlight_ui (en ViscaMixin) los encuentre
        mw._backlight_style_off = (
            "QPushButton{background-color: white; border: 2px solid #555;"
            " font: bold 13px; color: black; border-radius: 4px}"
        )
        mw._backlight_style_on = (
            "QPushButton{background-color: #e6a800; border: 2px solid #b37f00;"
            " font: bold 13px; color: white; border-radius: 4px}"
        )
        mw.BtnBacklight.setStyleSheet(mw._backlight_style_off)
        mw.BtnBacklight.clicked.connect(mw.BacklightToggle)

    # ── Botones de configuración ──────────────────────────────────────────────

    def _build_config_buttons(self):
        mw = self._mw

        btn_gear = QPushButton('⚙', mw)
        btn_gear.setGeometry(1820, 900, 40, 40)
        btn_gear.setToolTip('Camera configuration')
        btn_gear.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,60); border: 1px solid #999;"
            " border-radius: 6px; font: 18px; color: #444; }"
            "QPushButton:pressed { background: rgba(80,80,80,140); }"
        )
        btn_gear.clicked.connect(mw._open_config_dialog)

        btn_close = QPushButton('Close window', mw)
        btn_close.setGeometry(1500, 1050, 360, 22)
        btn_close.setStyleSheet(
            "background-color: lightgrey; font: 15px; color: black; border: none")
        btn_close.clicked.connect(mw.Quit)


# ── Helper de módulo ──────────────────────────────────────────────────────────

def _make_toggle_frame(parent, x: int, y: int, w: int, h: int) -> QFrame:
    """Crea el fondo gris redondeado detrás de los toggle buttons."""
    frame = QFrame(parent)
    frame.setGeometry(x, y, w, h)
    frame.setStyleSheet("QFrame { background-color: #E8E8E8; border-radius: 12px; }")
    frame.lower()
    return frame
