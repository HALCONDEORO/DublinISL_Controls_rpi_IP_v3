#!/usr/bin/env python3
# main_window.py — Ventana principal: solo layout de UI
#
# Responsabilidad única: construir y posicionar todos los widgets.
# NO contiene lógica de negocio: cada acción delega en un mixin.
#
# HERENCIA MÚLTIPLE (patrón mixin):
#   MainWindow hereda de ViscaMixin, SessionMixin y DialogsMixin.
#   Python resuelve los métodos por MRO (izquierda a derecha), por lo
#   que el orden de herencia importa si hay colisiones de nombres
#   (aquí no las hay: cada mixin tiene métodos disjuntos).
#
#   Diagrama:
#     ViscaMixin   → movimiento, zoom, focus, presets
#     SessionMixin → encendido, home, apagado
#     DialogsMixin → cambio IP/ID, help, quit
#     QMainWindow  → base Qt

from __future__ import annotations  # Permite type hints modernos en Python <3.10

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QToolButton,
    QLabel, QButtonGroup, QSlider
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    Cam1Check, Cam2Check,
    SPEED_MIN, SPEED_MAX, SPEED_DEFAULT,
    SEAT_POSITIONS, BUTTON_COLOR
)
from camera_worker import CameraWorker
from widgets import GoButton, make_arrow_btn
from visca_mixin import ViscaMixin
from session_mixin import SessionMixin
from dialogs_mixin import DialogsMixin

import os


class MainWindow(ViscaMixin, SessionMixin, DialogsMixin, QMainWindow):
    """
    Ventana principal 1920×1080 px.

    __init__ solo construye la UI.  Toda la lógica de negocio vive
    en los mixins importados arriba.
    """

    # Estilo compartido para botones toggle (Camera selector y Preset mode).
    # Definido como constante de clase para evitar duplicación — se usaba
    # la misma cadena en _build_camera_selector() Y en _build_preset_mode().
    _TOGGLE_STYLE = (
        "QPushButton{background-color: white; border: 3px solid green; "
        "font: bold 20px; color: black}"
        "QPushButton:Checked{background-color: green; font: bold 20px; color: white}"
    )

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Camera Controls')
        self.setGeometry(0, 0, 1920, 1080)

        # Estado del backlight por cámara (False = OFF).
        # Dict con clave 1 (Platform) y 2 (Comments).
        self.backlight_on = {1: False, 2: False}

        # Estado de sesión: False = apagada, True = activa
        self.session_active = False

        # Workers de red: uno por cámara, indexados por IP
        self._workers = {
            IPAddress:  CameraWorker(IPAddress),
            IPAddress2: CameraWorker(IPAddress2),
        }

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────────
    #  Construcción de la UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Construye todos los widgets de la ventana."""
        self._build_background()
        self._build_platform_presets()
        self._build_seat_buttons()
        self._build_session_controls()
        self._build_right_panel()

    def _build_background(self):
        """Carga y escala la imagen de fondo del plano de asientos."""
        bg_path = "Background_ISL_v2.jpg"
        if not os.path.exists(bg_path):
            print(f"[WARNING] {bg_path} no encontrado — fondo vacío")
            return

        pixmap = QPixmap(bg_path)
        scaled = pixmap.scaled(1920, 1080, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        background = QLabel(self)
        background.setPixmap(scaled)
        background.setGeometry(0, -30, 1920, 1080)
        background.lower()  # Enviar al fondo para que los botones queden encima

    def _build_platform_presets(self):
        """
        Crea los 3 botones de preset de plataforma (Chairman, Left, Right).
        Usan QPushButton plano con fondo transparente para superponerse
        sobre los iconos de la imagen de fondo.

        IMPORTANTE: no usar GoButton aquí — GoButton sobreescribiría el
        stylesheet con el de asiento.  El padding-top:70px empuja el texto
        al tercio inferior del botón, debajo del icono de la imagen.
        """
        _platform_style = (
            "background-color: rgba(0,0,0,0); font: 14px; font-weight: bold; "
            "color: black; padding-top: 70px"
        )

        for label, x, preset_num in [
            ('Left',     460, 2),
            ('Chairman', 623, 1),
            ('Right',    803, 3),
        ]:
            btn = QPushButton(label, self)
            btn.resize(110, 110)
            btn.move(x, 35)
            btn.setStyleSheet(_platform_style)
            btn.clicked.connect(lambda checked=False, n=preset_num: self.go_to_preset(n))

    def _build_seat_buttons(self):
        """
        Crea un GoButton por cada asiento definido en SEAT_POSITIONS.
        El asiento 129 (Second Room) recibe tratamiento especial:
        usa QToolButton con icono second_room.png en lugar de seat.svg.
        """
        for seat_number in range(4, 130):
            if seat_number not in SEAT_POSITIONS:
                continue

            x, y = SEAT_POSITIONS[seat_number]

            if seat_number == 129:
                # Segunda sala: QToolButton con icono específico
                button = QToolButton(self)
                button.move(x, y)
                button.resize(55, 65)
                button.setText('Second Room')
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black; "
                    "border-radius: 5px; font: 8px; font-weight: bold; color: " + BUTTON_COLOR + "; }"
                )
                # Cargar icono con degradación si falta el asset
                if os.path.exists("second_room.png"):
                    pix = QPixmap("second_room.png").scaled(
                        40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    button.setIcon(QtGui.QIcon(pix))
                    button.setIconSize(QtCore.QSize(40, 40))
                else:
                    print("[WARNING] second_room.png no encontrado")
            else:
                button = GoButton(str(seat_number), self)
                button.move(x, y)

            button.clicked.connect(
                lambda checked=False, n=seat_number: self.go_to_preset(n)
            )
            # Guardar referencia para poder acceder al botón por número si hace falta
            setattr(self, f"Seat{seat_number}", button)

    def _build_session_controls(self):
        """Botón de encendido ⏻ y etiqueta de estado (OFF/Starting.../ON)."""
        self.BtnSession = QPushButton('\u23fb', self)  # ⏻
        self.BtnSession.setGeometry(10, 10, 50, 50)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.BtnSession.setStyleSheet(
            "QPushButton{background-color: #8b1a1a; border: 2px solid #5a0d0d; "
            "font: bold 26px; color: white; border-radius: 25px}"
            "QPushButton:pressed{background-color: #5a0d0d}"
        )
        self.BtnSession.clicked.connect(self.ToggleSession)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

    def _build_right_panel(self):
        """
        Construye el panel derecho (x≥1500):
        selector de cámara, slider de velocidad, botones Call/Set,
        zoom, flechas, home, focus/exposición, configuración.
        """
        self._build_section_labels()
        self._build_camera_selector()
        self._build_speed_slider()
        self._build_preset_mode()
        self._build_zoom_buttons()
        self._build_arrow_buttons()
        self._build_focus_exposure()
        self._build_config_buttons()

    def _build_section_labels(self):
        """Etiquetas de sección del panel derecho (solo texto, sin lógica)."""
        for text, geom in [
            ('Camera Selection', (1500,  20, 360, 30)),
            ('PTZ Speed',        (1500, 138, 360, 30)),
            ('Camera Presets',   (1500, 253, 360, 30)),
            ('Camera Controls',  (1500, 367, 360, 30)),
        ]:
            lbl = QLabel(text, self)
            lbl.setGeometry(*geom)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("font: bold 20px; color: black")

    def _build_camera_selector(self):
        """
        Botones toggle Platform / Comments para seleccionar la cámara activa.
        Son mutuamente exclusivos mediante QButtonGroup + setAutoExclusive.
        Al cambiar de cámara se actualiza el estado del botón Backlight.
        """
        self.Cam1 = QPushButton('Platform', self)
        self.Cam1.setGeometry(1500, 60, 180, 70)
        self.Cam1.setCheckable(True)
        self.Cam1.setAutoExclusive(True)
        self.Cam1.setChecked(True)
        self.Cam1.setToolTip('Select Platform Camera')
        self.Cam1.setStyleSheet(self._TOGGLE_STYLE)

        self.Cam2 = QPushButton('Comments', self)
        self.Cam2.setGeometry(1680, 60, 180, 70)
        self.Cam2.setCheckable(True)
        self.Cam2.setAutoExclusive(True)
        self.Cam2.setToolTip('Select Comments Camera')
        self.Cam2.setStyleSheet(self._TOGGLE_STYLE)

        self.Camgroup = QButtonGroup(self)
        self.Camgroup.addButton(self.Cam1)
        self.Camgroup.addButton(self.Cam2)

        # Al cambiar de cámara, sincronizar el estado del botón Backlight
        self.Cam1.clicked.connect(self._update_backlight_ui)
        self.Cam2.clicked.connect(self._update_backlight_ui)

    def _build_speed_slider(self):
        """
        Slider horizontal de velocidad (1-18).
        SpeedValueLabel muestra una descripción textual debajo del slider.
        """
        SlowLabel = QLabel('SLOW', self)
        SlowLabel.setGeometry(1500, 190, 55, 20)
        SlowLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        SlowLabel.setStyleSheet("font: bold 13px; color: #444")

        self.SpeedSlider = QSlider(Qt.Horizontal, self)
        self.SpeedSlider.setGeometry(1560, 172, 230, 48)
        self.SpeedSlider.setMinimum(SPEED_MIN)
        self.SpeedSlider.setMaximum(SPEED_MAX)
        self.SpeedSlider.setValue(SPEED_DEFAULT)
        self.SpeedSlider.setTickPosition(QSlider.TicksBelow)
        self.SpeedSlider.setTickInterval(3)
        self.SpeedSlider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px; background: #cccccc; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #1a7a1a; border: 2px solid #0d4d0d;
                width: 24px; height: 24px; margin: -9px 0; border-radius: 12px;
            }
            QSlider::sub-page:horizontal {
                background: #4caf50; border-radius: 4px;
            }
        """)

        FastLabel = QLabel('FAST', self)
        FastLabel.setGeometry(1797, 190, 55, 20)
        FastLabel.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        FastLabel.setStyleSheet("font: bold 13px; color: #444")

        self.SpeedValueLabel = QLabel(self._speed_label_text(SPEED_DEFAULT), self)
        self.SpeedValueLabel.setGeometry(1500, 224, 360, 20)
        self.SpeedValueLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.SpeedValueLabel.setStyleSheet("font: 12px; color: #555")

        self.SpeedSlider.valueChanged.connect(self._on_speed_changed)

    def _build_preset_mode(self):
        """
        Botones Call / Set para el modo de preset.
        Call = recordar preset, Set = guardar preset (con confirmación).
        """
        self.BtnCall = QPushButton('Call', self)
        self.BtnCall.setGeometry(1500, 290, 180, 70)
        self.BtnCall.setCheckable(True)
        self.BtnCall.setAutoExclusive(True)
        self.BtnCall.setChecked(True)
        self.BtnCall.setStyleSheet(self._TOGGLE_STYLE)

        self.BtnSet = QPushButton('Set', self)
        self.BtnSet.setGeometry(1680, 290, 180, 70)
        self.BtnSet.setCheckable(True)
        self.BtnSet.setAutoExclusive(True)
        self.BtnSet.setStyleSheet(self._TOGGLE_STYLE)

        self.PresetModeGroup = QButtonGroup(self)
        self.PresetModeGroup.addButton(self.BtnCall)
        self.PresetModeGroup.addButton(self.BtnSet)

    def _build_zoom_buttons(self):
        """Botones de Zoom In / Zoom Out con imagen PNG."""
        ZoomIn = QPushButton(self)
        ZoomIn.setGeometry(1680, 403, 100, 100)
        ZoomIn.pressed.connect(self.ZoomIn)
        ZoomIn.released.connect(self.ZoomStop)
        ZoomIn.setStyleSheet("background-image: url(ZoomIn_120.png); border: none")

        ZoomOut = QPushButton(self)
        ZoomOut.setGeometry(1510, 403, 100, 100)
        ZoomOut.pressed.connect(self.ZoomOut)
        ZoomOut.released.connect(self.ZoomStop)
        ZoomOut.setStyleSheet("background-image: url(ZoomOut_120.png); border: none")

    def _build_arrow_buttons(self):
        """
        8 botones de dirección + botón Home central.
        Usa make_arrow_btn() de widgets.py para crear cada botón con
        angle.png rotado al ángulo correcto.

        TABLA DE ROTACIONES (baseline: angle.png apunta hacia abajo = 0°):
            UpLeft=135°  Up=180°  UpRight=225°
            Left=90°              Right=270°
            DownLeft=45° Down=0°  DownRight=315°
        """
        arrow_config = [
            # (x,    y,   grados, handler_pressed)
            (1500, 510,  135, self.UpLeft),
            (1605, 510,  180, self.Up),
            (1710, 510,  225, self.UpRight),
            (1500, 617,   90, self.Left),
            (1710, 617,  270, self.Right),
            (1500, 724,   45, self.DownLeft),
            (1605, 724,    0, self.Down),
            (1710, 724,  315, self.DownRight),
        ]

        for x, y, deg, handler in arrow_config:
            btn = make_arrow_btn(self, x, y, deg)
            btn.pressed.connect(handler)
            btn.released.connect(self.Stop)  # Siempre parar al soltar

        # Botón Home en el centro del grid de flechas
        Home = QPushButton('', self)
        Home.setGeometry(1605, 617, 100, 100)
        Home.clicked.connect(self.HomeButton)
        Home.setStyleSheet("background-image: url(home.png); border: none")

    def _build_focus_exposure(self):
        """
        Sección Focus & Exposure: Auto/OnePush/Manual focus +
        Brighter/Darker exposure + toggle Backlight.
        """
        FocusExposureLabel = QLabel('Focus & Exposure', self)
        FocusExposureLabel.setGeometry(1500, 835, 360, 25)
        FocusExposureLabel.setAlignment(QtCore.Qt.AlignCenter)
        FocusExposureLabel.setStyleSheet("font: bold 16px; color: black")

        _btn_style = (
            "QPushButton{background-color: white; border: 2px solid #555; "
            "font: bold 13px; color: black; border-radius: 4px}"
            "QPushButton:pressed{background-color: #ccc}"
        )

        for label, geom, tooltip, handler in [
            ('Auto\nFocus',   (1500, 863, 110, 50), 'Auto Focus ON',                   self.AutoFocus),
            ('One Push\nAF',  (1625, 863, 110, 50), 'One-shot autofocus, then manual', self.OnePushAF),
            ('Manual\nFocus', (1750, 863, 110, 50), 'Manual Focus mode',               self.ManualFocus),
            ('▼ Darker',      (1500, 920, 110, 45), 'Decrease exposure one step',      self.BrightnessDown),
            ('▲ Brighter',    (1750, 920, 110, 45), 'Increase exposure one step',      self.BrightnessUp),
        ]:
            btn = QPushButton(label, self)
            btn.setGeometry(*geom)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_btn_style)
            btn.clicked.connect(handler)

        # Botón Backlight: cambia color según estado ON/OFF
        self.BtnBacklight = QPushButton('Backlight\nOFF', self)
        self.BtnBacklight.setGeometry(1625, 920, 110, 45)
        self.BtnBacklight.setToolTip('Toggle backlight compensation (contraluz)')
        self._backlight_style_off = (
            "QPushButton{background-color: white; border: 2px solid #555; "
            "font: bold 13px; color: black; border-radius: 4px}"
        )
        self._backlight_style_on = (
            "QPushButton{background-color: #e6a800; border: 2px solid #b37f00; "
            "font: bold 13px; color: white; border-radius: 4px}"
        )
        self.BtnBacklight.setStyleSheet(self._backlight_style_off)
        self.BtnBacklight.clicked.connect(self.BacklightToggle)

    def _build_config_buttons(self):
        """
        Botones de configuración en la parte inferior del panel derecho:
        IP y VISCA ID de cada cámara, versión, cerrar, ayuda.
        """
        Cam1Address = QPushButton(
            'Platform [Platform]  -  ' + IPAddress, self)
        Cam1Address.setGeometry(1500, 975, 310, 22)
        Cam1Address.setStyleSheet("font: bold 15px; color:" + Cam1Check)
        Cam1Address.clicked.connect(self.PTZ1Address)

        self._cam2_addr_btn = QPushButton(
            'Comments [Audience]  -  ' + IPAddress2, self)
        self._cam2_addr_btn.setGeometry(1500, 995, 310, 22)
        self._cam2_addr_btn.setStyleSheet("font: bold 15px; color:" + Cam2Check)
        self._cam2_addr_btn.clicked.connect(self.PTZ2Address)

        self._ptz1_id_btn = QPushButton(' ID-' + Cam1ID, self)
        self._ptz1_id_btn.setGeometry(1815, 975, 45, 22)
        self._ptz1_id_btn.setStyleSheet("font: bold 15px; color:" + Cam1Check)
        self._ptz1_id_btn.clicked.connect(self.PTZ1IDchange)

        self._ptz2_id_btn = QPushButton(' ID-' + Cam2ID, self)
        self._ptz2_id_btn.setGeometry(1815, 995, 45, 22)
        self._ptz2_id_btn.setStyleSheet("font: bold 15px; color:" + Cam2Check)
        self._ptz2_id_btn.clicked.connect(self.PTZ2IDchange)

        # Etiqueta de versión
        VersionLabel = QLabel('v3 — IP RPI — March 2026', self)
        VersionLabel.setGeometry(1500, 1022, 360, 20)
        VersionLabel.setAlignment(QtCore.Qt.AlignCenter)
        VersionLabel.setStyleSheet("font: 12px; color: grey")

        Version = QPushButton('Close window', self)
        Version.setGeometry(1500, 1050, 310, 22)
        Version.setStyleSheet(
            "background-color: lightgrey; font: 15px; color: black; border: none")
        Version.clicked.connect(self.Quit)

        Help = QPushButton('?', self)
        Help.setGeometry(1815, 1050, 45, 22)
        Help.setStyleSheet(
            "background-color: lightgrey; font: 15px; color: black; border: none")
        Help.clicked.connect(self.HelpMsg)

    # ─────────────────────────────────────────────────────────────────────────
    #  Helper de UI (no es VISCA, no es diálogo — vive aquí)
    # ─────────────────────────────────────────────────────────────────────────

    def _update_backlight_ui(self):
        """
        Sincroniza el botón Backlight con el estado real de la cámara activa.
        Se llama al cambiar de cámara para que el botón refleje el estado
        correcto (cada cámara tiene su propio estado de backlight).
        """
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)
