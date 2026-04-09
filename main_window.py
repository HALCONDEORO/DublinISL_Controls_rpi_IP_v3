#!/usr/bin/env python3
# main_window.py — Ventana principal: solo layout de UI
#
# CAMBIOS v2→v3:
#   - bg_path: Background_ISL_v2.jpg → Background_ISL_v3.jpg
#   - Iconos Left/Chairman/Right: SVG embebido como QToolButton sobre el fondo.
#
# CAMBIOS EN REFACTORS ANTERIORES:
#   - Imports movidos al nivel de módulo (PEP 8)
#   - _build_platform_presets() eliminado (método vacío, código muerto)
#   - `if seat_number < 4: continue` eliminado (SEAT_POSITIONS no tiene claves <4)
#   - Cam1Address → self._cam1_addr_btn para consistencia con _cam2_addr_btn
#
# CAMBIOS ENGRANAJE DE CONFIGURACIÓN:
#   - _build_config_buttons() reemplazado por un único botón ⚙ que abre
#     ConfigDialog (modal) con IP, ID, versión y ayuda.
#   - "Close window" permanece siempre visible en el panel (no requiere engranaje).
#   MOTIVO: los controles técnicos los usa el administrador, no el operador.
#   Esconderlos evita cambios accidentales durante una sesión en directo y
#   reduce el ruido visual del panel derecho.
#
# CAMBIOS CHAIRMAN PRESET POR PERSONA:
#   - Chairman usa ChairmanButton en lugar de SpecialDragButton genérico.
#   - Al arrastrar un nombre al Chairman:
#       · Si la persona tiene preset guardado → recall a esa posición
#       · Si no tiene → recall al preset genérico 1
#       · Si ya tiene preset → botón "Edit" visible (Save oculto)
#       · Si no tiene preset → botón "Save position" visible directamente
#   - _save_chairman_preset(name): asigna número de preset libre, envía
#     Save Preset VISCA a Cam1, persiste en chairman_presets.json.
#   - _on_names_list_changed: al renombrar un consejero, migra su entrada
#     en chairman_presets para no perder el preset guardado.
#   MOTIVO: distintos oradores tienen estaturas y distancias distintas;
#   guardar la posición por persona evita reajustar la cámara manualmente.

from __future__ import annotations

import os

from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QToolButton,
    QLabel, QButtonGroup, QSlider,
)

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    Cam1Check, Cam2Check,
    SPEED_MIN, SPEED_MAX, SPEED_DEFAULT,
    SEAT_POSITIONS, BUTTON_COLOR,
    load_names_data, save_names_data,
    PRESET_MAP,
)
from camera_worker import CameraWorker
from widgets import GoButton, SpecialDragButton, NamesPanel, make_arrow_btn
from visca_mixin import ViscaMixin
from session_mixin import SessionMixin
from dialogs_mixin import DialogsMixin

from platform_icons import (
    SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT,
    SVG_WHEELCHAIR,
)

from config_dialog import ConfigDialog

from chairman_presets import (
    load_chairman_presets, save_chairman_presets,
    next_available_preset, CHAIRMAN_GENERIC_PRESET,
)
from chairman_button import ChairmanButton


class MainWindow(ViscaMixin, SessionMixin, DialogsMixin, QMainWindow):
    """Ventana principal 1920x1080 px."""

    _TOGGLE_STYLE = (
        "QPushButton{background-color: white; border: 3px solid green; "
        "font: bold 20px; color: black}"
        "QPushButton:Checked{background-color: green; font: bold 20px; color: white}"
    )

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Camera Controls')
        self.setGeometry(0, 0, 1920, 1080)

        self.backlight_on   = {1: False, 2: False}
        self.session_active = False

        self._workers = {
            IPAddress:  CameraWorker(IPAddress),
            IPAddress2: CameraWorker(IPAddress2),
        }

        _data = load_names_data()
        self._names_list = _data["names"]
        self._seat_names = _data["seats"]

        # Cargar presets personales del Chairman al arrancar.
        # Se pasa como referencia viva a ChairmanButton para que ambos
        # vean siempre el mismo dict sin necesidad de sincronizar copias.
        self._chairman_presets = load_chairman_presets()

        self._build_ui()
        self._build_overlays()

    # ─────────────────────────────────────────────────────────────────────
    # Overlays de inicio (Login → Splash → Contenido principal)
    # ─────────────────────────────────────────────────────────────────────

    def _build_overlays(self):
        """Crea el overlay de login encima de todo el contenido."""
        from login_screen import LoginScreen
        self._login_overlay = LoginScreen(parent=self)
        self._login_overlay.setGeometry(0, 0, 1920, 1080)
        self._login_overlay.raise_()
        self._login_overlay.login_successful.connect(self._on_login_done)

    def _on_login_done(self):
        """Login correcto: oculta login, muestra splash e inicia tests."""
        from splash_screen import SplashScreen
        self._login_overlay.hide()

        self._splash_overlay = SplashScreen(parent=self)
        self._splash_overlay.setGeometry(0, 0, 1920, 1080)
        self._splash_overlay.raise_()
        self._splash_overlay.show()
        self._splash_overlay.startup_complete.connect(self._on_startup_done)
        # Arrancar tests ahora (no en __init__ de SplashScreen)
        self._splash_overlay._start_initialization()

    def _on_startup_done(self):
        """Tests completados: oculta splash y deja visible el contenido principal."""
        self._splash_overlay.hide()

    # ─────────────────────────────────────────────────────────────────────
    # Construcción de la UI
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_background()
        self._build_seat_buttons()
        self._build_session_controls()
        self._build_right_panel()
        self._build_names_panel()
        self._restore_seat_names()
        self._build_table_seats()
        self._build_platform_icons()   # AL FINAL: z-order

        self.BtnNames.raise_()
        self.BtnNames.hide()

        self.BtnCall.clicked.connect(lambda: self._names_panel.set_edit_mode(False))
        self.BtnSet.clicked.connect(lambda:  self._names_panel.set_edit_mode(True))

    def _build_background(self):
        """Carga fondo. Falla silenciosamente si el archivo no existe."""
        bg_path = "Background_ISL_v3.jpg"
        if not os.path.exists(bg_path):
            print(f"[WARNING] {bg_path} no encontrado — fondo vacío")
            return
        pixmap = QPixmap(bg_path).scaled(
            1920, 1080, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        background = QLabel(self)
        background.setPixmap(pixmap)
        background.setGeometry(0, -30, 1920, 1080)
        background.lower()

    def _build_table_seats(self):
        mesa = QLabel(self)
        mesa.setGeometry(96, 900, 245, 50)
        mesa.setStyleSheet(
            "background-color: rgba(100, 80, 60, 120);"
            "border: 2px solid rgba(70, 50, 30, 200);"
            "border-radius: 4px;"
        )

    def _build_platform_icons(self):
        """
        Crea los 3 botones de plataforma.

        Left y Right: QToolButton estándar, sin cambios respecto a versiones anteriores.

        Chairman: ChairmanButton (hereda SpecialDragButton) con preset por persona.
          - Al soltar un nombre encima → recall automático al preset de esa persona
          - Botón "Save position" visible si la persona no tiene preset aún
          - Botón "Edit" visible si ya tiene preset (Save oculto por defecto)
          Los botones auxiliares (Save/Edit) se crean como hijos de self (MainWindow),
          posicionados justo debajo del icono Chairman (y=130).
        """
        btn_w, btn_h = 110, 115

        # ── Left (preset 2) ───────────────────────────────────────────────
        cx = 562
        renderer = QSvgRenderer(QtCore.QByteArray(SVG_LEFT.encode('utf-8')))
        pix = QPixmap(70, 70); pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix); renderer.render(p, QtCore.QRectF(0, 0, 70, 70)); p.end()
        btn = QToolButton(self)
        btn.setText('Left')
        btn.setIcon(QtGui.QIcon(pix)); btn.setIconSize(QtCore.QSize(70, 70))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setGeometry(cx - btn_w // 2, 10, btn_w, btn_h)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 13px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        btn.clicked.connect(lambda checked=False: self.go_to_preset(2))
        btn.raise_()

        # ── Chairman (preset 1) — ChairmanButton ──────────────────────────
        cx = 744
        self._chairman_btn = ChairmanButton(
            presets_ref  = self._chairman_presets,  # referencia viva al dict
            on_recall_cb = self._chairman_recall,
            on_save_cb   = self._save_chairman_preset,
            svg_data     = SVG_CHAIRMAN,
            icon_w=90, icon_h=90,
            parent=self,
        )
        self._chairman_btn.setGeometry(cx - btn_w // 2, 10, btn_w, btn_h)
        self._chairman_btn.name_assigned.connect(self._on_seat_name_assigned)
        # Click sin nombre asignado → preset genérico 1
        self._chairman_btn.clicked.connect(
            lambda checked=False: self.go_to_preset(CHAIRMAN_GENERIC_PRESET))
        self._chairman_btn.raise_()
        # Clave "1" en seat_names.json y en _restore_seat_names
        setattr(self, "Seat1", self._chairman_btn)

        # ── Right (preset 3) ──────────────────────────────────────────────
        cx = 938
        renderer = QSvgRenderer(QtCore.QByteArray(SVG_RIGHT.encode('utf-8')))
        pix = QPixmap(70, 70); pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix); renderer.render(p, QtCore.QRectF(0, 0, 70, 70)); p.end()
        btn = QToolButton(self)
        btn.setText('Right')
        btn.setIcon(QtGui.QIcon(pix)); btn.setIconSize(QtCore.QSize(70, 70))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setGeometry(cx - btn_w // 2, 10, btn_w, btn_h)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 13px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        btn.clicked.connect(lambda checked=False: self.go_to_preset(3))
        btn.raise_()

    # ─────────────────────────────────────────────────────────────────────
    # Callbacks Chairman preset
    # ─────────────────────────────────────────────────────────────────────

    def _chairman_recall(self, preset_num: int):
        """
        Recall del preset dado siempre en Cam1 (Platform).
        MOTIVO: el Chairman controla siempre Cam1 independientemente de
        qué cámara esté seleccionada en el panel PTZ.
        Llamado por ChairmanButton al asignar un nombre.
        """
        preset_hex = PRESET_MAP.get(preset_num)
        if not preset_hex:
            print(f"[CHAIRMAN] Preset {preset_num} no está en PRESET_MAP")
            return
        if not self._send_cmd(IPAddress, Cam1ID, f"01043f02{preset_hex}ff"):
            self.ErrorCapture()

    def _save_chairman_preset(self, name: str):
        """
        Asigna un número de preset libre a 'name', envía Save Preset a Cam1,
        y persiste en chairman_presets.json.

        Si la persona ya tenía preset: lo reutiliza y sobreescribe la posición
        guardada sin consumir un número nuevo.
        Si no tenía: asigna el siguiente número libre en el rango 10-89.

        Solo persiste si el comando VISCA tiene éxito.
        Llamado por ChairmanButton._on_save_clicked().
        """
        if name in self._chairman_presets:
            preset_num = self._chairman_presets[name]
        else:
            preset_num = next_available_preset(self._chairman_presets)
            if preset_num is None:
                print(f"[CHAIRMAN] Rango de presets agotado — no se puede guardar para '{name}'")
                return
            self._chairman_presets[name] = preset_num

        preset_hex = PRESET_MAP.get(preset_num)
        if not preset_hex:
            print(f"[CHAIRMAN] Preset {preset_num} no está en PRESET_MAP")
            return

        if not self._send_cmd(IPAddress, Cam1ID, f"01043f01{preset_hex}ff"):
            self.ErrorCapture()
            return

        save_chairman_presets(self._chairman_presets)
        print(f"[CHAIRMAN] Preset {preset_num} guardado para '{name}'")
        # ChairmanButton ya actualiza sus botones en _on_save_clicked,
        # pero refresh garantiza consistencia si el dict cambió externamente.
        self._chairman_btn.refresh_preset_state()

    # ─────────────────────────────────────────────────────────────────────
    # Seat buttons
    # ─────────────────────────────────────────────────────────────────────

    def _build_seat_buttons(self):
        for seat_number, (x, y) in SEAT_POSITIONS.items():

            if seat_number == 128:
                renderer = QSvgRenderer(
                    QtCore.QByteArray(SVG_WHEELCHAIR.encode('utf-8')))
                if not renderer.isValid():
                    print("[WARNING] SVG_WHEELCHAIR inválido — asiento 128 sin icono")
                pix = QPixmap(40, 40); pix.fill(Qt.transparent)
                painter = QtGui.QPainter(pix)
                renderer.render(painter, QtCore.QRectF(0, 0, 40, 40))
                painter.end()
                button = SpecialDragButton(seat_id=128, default_label='Wheelchair', parent=self)
                button.move(x, y); button.resize(55, 65)
                button.setIcon(QtGui.QIcon(pix)); button.setIconSize(QtCore.QSize(40, 40))
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black;"
                    " border-radius: 5px; font: 8px; font-weight: bold; color: "
                    + BUTTON_COLOR + "; }"
                )
                button.name_assigned.connect(self._on_seat_name_assigned)
                button.clicked.connect(
                    lambda checked=False, n=seat_number: self.go_to_preset(n))
                setattr(self, f"Seat{seat_number}", button)

            elif seat_number == 129:
                button = SpecialDragButton(seat_id=129, default_label='Second Room', parent=self)
                button.move(x, y); button.resize(55, 65)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black;"
                    " border-radius: 5px; font: 8px; font-weight: bold; color: "
                    + BUTTON_COLOR + "; }"
                )
                renderer_sr = QSvgRenderer("second_room.svg")
                if renderer_sr.isValid():
                    pix = QPixmap(40, 40); pix.fill(Qt.transparent)
                    painter = QtGui.QPainter(pix)
                    renderer_sr.render(painter, QtCore.QRectF(0, 0, 40, 40))
                    painter.end()
                    button.setIcon(QtGui.QIcon(pix))
                    button.setIconSize(QtCore.QSize(40, 40))
                else:
                    print("[WARNING] second_room.svg no encontrado o inválido")
                button.name_assigned.connect(self._on_seat_name_assigned)
                button.clicked.connect(
                    lambda checked=False, n=seat_number: self.go_to_preset(n))
                setattr(self, f"Seat{seat_number}", button)

            elif seat_number == 130:
                renderer = QSvgRenderer(
                    QtCore.QByteArray(SVG_WHEELCHAIR.encode('utf-8')))
                if not renderer.isValid():
                    print("[WARNING] SVG_WHEELCHAIR inválido — asiento 130 sin icono")
                pix = QPixmap(40, 40); pix.fill(Qt.transparent)
                painter = QtGui.QPainter(pix)
                renderer.render(painter, QtCore.QRectF(0, 0, 40, 40))
                painter.end()
                button = SpecialDragButton(seat_id=130, default_label='Wheelchair', parent=self)
                button.move(x, y); button.resize(55, 65)
                button.setIcon(QtGui.QIcon(pix)); button.setIconSize(QtCore.QSize(40, 40))
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black;"
                    " border-radius: 5px; font: 8px; font-weight: bold; color: "
                    + BUTTON_COLOR + "; }"
                )
                button.name_assigned.connect(self._on_seat_name_assigned)
                button.clicked.connect(
                    lambda checked=False, n=seat_number: self.go_to_preset(n))
                setattr(self, f"Seat{seat_number}", button)

            elif seat_number == 131:
                button = SpecialDragButton(seat_id=131, default_label='Library', parent=self)
                button.move(x, y); button.resize(55, 65)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black;"
                    " border-radius: 5px; font: 8px; font-weight: bold; color: "
                    + BUTTON_COLOR + "; }"
                )
                renderer_lib = QSvgRenderer("library.svg")
                if renderer_lib.isValid():
                    pix = QPixmap(40, 40); pix.fill(Qt.transparent)
                    painter = QtGui.QPainter(pix)
                    renderer_lib.render(painter, QtCore.QRectF(0, 0, 40, 40))
                    painter.end()
                    button.setIcon(QtGui.QIcon(pix))
                    button.setIconSize(QtCore.QSize(40, 40))
                else:
                    print("[WARNING] library.svg no encontrado o inválido")
                button.name_assigned.connect(self._on_seat_name_assigned)
                button.clicked.connect(
                    lambda checked=False, n=seat_number: self.go_to_preset(n))
                setattr(self, f"Seat{seat_number}", button)

            else:
                button = GoButton(seat_number, self)
                button.move(x, y)
                button.name_assigned.connect(self._on_seat_name_assigned)
                button.clicked.connect(
                    lambda checked=False, n=seat_number: self.go_to_preset(n))
                setattr(self, f"Seat{seat_number}", button)

    def _build_session_controls(self):
        self.BtnSession = QPushButton('\u23fb', self)
        self.BtnSession.setGeometry(10, 10, 50, 50)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.BtnSession.setStyleSheet(self._STYLE_BTN_OFF)
        self.BtnSession.clicked.connect(self.ToggleSession)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

        self.BtnNames = QPushButton('\U0001f465', self)
        self.BtnNames.setGeometry(1500, 15, 40, 40)
        self.BtnNames.setCheckable(True)
        self.BtnNames.setToolTip('Attendees panel')
        self.BtnNames.setStyleSheet(
            "QPushButton { background: white; border: 2px solid #1976D2;"
            " font: 22px; border-radius: 6px; }"
            "QPushButton:checked { background: #1976D2; color: white; }"
            "QPushButton:pressed  { background: #e3f2fd; }"
        )
        self.BtnNames.clicked.connect(self._toggle_names_panel)

    def _build_right_panel(self):
        self._build_section_labels()
        self._build_camera_selector()
        self._build_speed_slider()
        self._build_preset_mode()
        self._build_zoom_buttons()
        self._build_arrow_buttons()
        self._build_focus_exposure()
        self._build_config_buttons()

    def _build_section_labels(self):
        for text, geom in [
            ('Camera Selection', (1500, 20, 360, 30)),
            ('PTZ Speed',        (1500, 138, 360, 30)),
            ('Camera Presets',   (1500, 253, 360, 30)),
            ('Camera Controls',  (1500, 367, 360, 30)),
        ]:
            lbl = QLabel(text, self)
            lbl.setGeometry(*geom)
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("font: bold 20px; color: black")

    def _build_camera_selector(self):
        self.Cam1 = QPushButton('Platform', self)
        self.Cam1.setGeometry(1500, 60, 180, 70)
        self.Cam1.setCheckable(True); self.Cam1.setAutoExclusive(True)
        self.Cam1.setChecked(True)
        self.Cam1.setToolTip('Select Platform Camera')
        self.Cam1.setStyleSheet(self._TOGGLE_STYLE)

        self.Cam2 = QPushButton('Comments', self)
        self.Cam2.setGeometry(1680, 60, 180, 70)
        self.Cam2.setCheckable(True); self.Cam2.setAutoExclusive(True)
        self.Cam2.setToolTip('Select Comments Camera')
        self.Cam2.setStyleSheet(self._TOGGLE_STYLE)

        self.Camgroup = QButtonGroup(self)
        self.Camgroup.addButton(self.Cam1)
        self.Camgroup.addButton(self.Cam2)

        self.Cam1.clicked.connect(self._update_backlight_ui)
        self.Cam2.clicked.connect(self._update_backlight_ui)

    def _build_speed_slider(self):
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
        self.BtnCall = QPushButton('Call', self)
        self.BtnCall.setGeometry(1500, 290, 180, 70)
        self.BtnCall.setCheckable(True); self.BtnCall.setAutoExclusive(True)
        self.BtnCall.setChecked(True)
        self.BtnCall.setStyleSheet(self._TOGGLE_STYLE)

        self.BtnSet = QPushButton('Set', self)
        self.BtnSet.setGeometry(1680, 290, 180, 70)
        self.BtnSet.setCheckable(True); self.BtnSet.setAutoExclusive(True)
        self.BtnSet.setStyleSheet(self._TOGGLE_STYLE)

        self.PresetModeGroup = QButtonGroup(self)
        self.PresetModeGroup.addButton(self.BtnCall)
        self.PresetModeGroup.addButton(self.BtnSet)

        self.BtnCall.clicked.connect(self._on_preset_mode_changed)
        self.BtnSet.clicked.connect(self._on_preset_mode_changed)

    def _build_zoom_buttons(self):
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
        arrow_config = [
            (1500, 510, 135, self.UpLeft),
            (1605, 510, 180, self.Up),
            (1710, 510, 225, self.UpRight),
            (1500, 617,  90, self.Left),
            (1710, 617, 270, self.Right),
            (1500, 724,  45, self.DownLeft),
            (1605, 724,   0, self.Down),
            (1710, 724, 315, self.DownRight),
        ]
        for x, y, deg, handler in arrow_config:
            btn = make_arrow_btn(self, x, y, deg)
            btn.pressed.connect(handler)
            btn.released.connect(self.Stop)

        Home = QPushButton('', self)
        Home.setGeometry(1605, 617, 100, 100)
        Home.clicked.connect(self.HomeButton)
        Home.setStyleSheet("background-image: url(home.png); border: none")

    def _build_focus_exposure(self):
        FocusExposureLabel = QLabel('Focus & Exposure', self)
        FocusExposureLabel.setGeometry(1500, 835, 360, 25)
        FocusExposureLabel.setAlignment(QtCore.Qt.AlignCenter)
        FocusExposureLabel.setStyleSheet("font: bold 16px; color: black")

        _btn_style = (
            "QPushButton{background-color: white; border: 2px solid #555;"
            " font: bold 13px; color: black; border-radius: 4px}"
            "QPushButton:pressed{background-color: #ccc}"
        )

        for label, geom, tooltip, handler in [
            ('Auto\nFocus',    (1500, 863, 110, 50), 'Auto Focus ON',                   self.AutoFocus),
            ('One Push\nAF',   (1625, 863, 110, 50), 'One-shot autofocus, then manual', self.OnePushAF),
            ('Manual\nFocus',  (1750, 863, 110, 50), 'Manual Focus mode',               self.ManualFocus),
            ('▼ Darker',       (1500, 920, 110, 45), 'Decrease exposure one step',      self.BrightnessDown),
            ('▲ Brighter',     (1750, 920, 110, 45), 'Increase exposure one step',      self.BrightnessUp),
        ]:
            btn = QPushButton(label, self)
            btn.setGeometry(*geom)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(_btn_style)
            btn.clicked.connect(handler)

        self.BtnBacklight = QPushButton('Backlight\nOFF', self)
        self.BtnBacklight.setGeometry(1625, 920, 110, 45)
        self.BtnBacklight.setToolTip('Toggle backlight compensation')
        self._backlight_style_off = (
            "QPushButton{background-color: white; border: 2px solid #555;"
            " font: bold 13px; color: black; border-radius: 4px}"
        )
        self._backlight_style_on = (
            "QPushButton{background-color: #e6a800; border: 2px solid #b37f00;"
            " font: bold 13px; color: white; border-radius: 4px}"
        )
        self.BtnBacklight.setStyleSheet(self._backlight_style_off)
        self.BtnBacklight.clicked.connect(self.BacklightToggle)

    def _build_config_buttons(self):
        """
        CAMBIADO: los 6 controles técnicos (4 botones IP/ID, versión, ayuda)
        se reemplazaron por un único botón ⚙ que abre ConfigDialog (modal).

        MOTIVO: esos controles los usa el administrador al configurar el sistema,
        no el operador durante una sesión. Esconderlos bajo el engranaje:
          - Elimina 6 widgets siempre visibles del panel derecho
          - Evita cambios accidentales de IP durante una transmisión en directo
          - El color de indicación de conectividad (verde/rojo) sigue visible
            dentro del diálogo, no se pierde información

        LO QUE PERMANECE SIEMPRE VISIBLE:
          - Botón "Close window": acción frecuente del operador, no técnica.
          - Botón ⚙: poco intrusivo, claro para el administrador.

        POSICIÓN DEL ENGRANAJE: y=1022 (donde antes estaba el label de versión),
        alineado a la derecha del panel (x=1820) para no interferir con
        "Close window" que queda a la izquierda.
        """
        # ── Botón engranaje ───────────────────────────────────────────────
        # Abre ConfigDialog con IP, ID, versión y ayuda.
        # Pequeño e icónico: no llama la atención durante la sesión.
        btn_gear = QPushButton('⚙', self)
        btn_gear.setGeometry(1820, 900, 40, 40)
        btn_gear.setToolTip('Camera configuration')
        btn_gear.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,60); border: 1px solid #999;"
            " border-radius: 6px; font: 18px; color: #444; }"
            "QPushButton:pressed { background: rgba(80,80,80,140); }"
        )
        btn_gear.clicked.connect(self._open_config_dialog)

        # ── Close window — siempre visible ────────────────────────────────
        # No es un control técnico: el operador lo usa al terminar la sesión.
        # MOTIVO para no meterlo en el engranaje: requeriría abrir el diálogo
        # solo para cerrar la app — un paso innecesario en el flujo normal.
        btn_close = QPushButton('Close window', self)
        btn_close.setGeometry(1500, 1050, 360, 22)
        btn_close.setStyleSheet(
            "background-color: lightgrey; font: 15px; color: black; border: none")
        btn_close.clicked.connect(self.Quit)

    def _open_config_dialog(self):
        """Instancia y abre el diálogo de configuración técnica."""
        dlg = ConfigDialog(parent=self)
        dlg.exec_()

    # ─────────────────────────────────────────────────────────────────────
    # Panel de consejeros
    # ─────────────────────────────────────────────────────────────────────

    def _build_names_panel(self):
        self._names_panel = NamesPanel(
            self._names_list, self._on_names_list_changed,
            self._clear_all_seats, parent=self)
        self._names_panel.hide()

    def _restore_seat_names(self):
        for seat_str, name in self._seat_names.items():
            btn = getattr(self, f"Seat{seat_str}", None)
            if isinstance(btn, (GoButton, SpecialDragButton)) and name:
                # emit_signal=False: no mueve cámara ni persiste al arrancar
                btn.set_name(name, emit_signal=False)
        self._sync_assigned_to_panel()

    def _toggle_names_panel(self, checked: bool):
        if checked:
            self._names_panel.raise_()
            self._names_panel.show()
        else:
            self._names_panel.hide()

    def _on_preset_mode_changed(self):
        if self.BtnCall.isChecked():
            if self.BtnNames.isChecked():
                self.BtnNames.setChecked(False)
                self._names_panel.hide()
            self.BtnNames.hide()
        else:
            self.BtnNames.show()
            self.BtnNames.raise_()

    def _on_seat_name_assigned(self, seat_number: int, name: str):
        key = str(seat_number)
        if name:
            # Exclusividad: un nombre solo puede estar en un asiento a la vez
            for other_key, other_name in list(self._seat_names.items()):
                if other_name == name and other_key != key:
                    other_btn = getattr(self, f"Seat{other_key}", None)
                    if isinstance(other_btn, (GoButton, SpecialDragButton)):
                        other_btn.set_name("", emit_signal=False)
                    del self._seat_names[other_key]
                    break
            self._seat_names[key] = name
        else:
            self._seat_names.pop(key, None)

        save_names_data(self._names_list, self._seat_names)
        self._sync_assigned_to_panel()

    def _on_names_list_changed(self, old_name: str = None, new_name: str = None):
        if old_name and new_name:
            for key, v in self._seat_names.items():
                if v == old_name:
                    self._seat_names[key] = new_name
                    btn = getattr(self, f"Seat{key}", None)
                    if isinstance(btn, (GoButton, SpecialDragButton)):
                        btn.set_name(new_name, emit_signal=False)

            # Migrar preset de Chairman si la persona renombrada tenía uno.
            # Sin esto, el preset queda huérfano con el nombre viejo y la
            # próxima vez que se asigne a la persona renombrada no se encontraría.
            if old_name in self._chairman_presets:
                self._chairman_presets[new_name] = self._chairman_presets.pop(old_name)
                save_chairman_presets(self._chairman_presets)

        save_names_data(self._names_list, self._seat_names)

    def _sync_assigned_to_panel(self):
        """Pasa al NamesPanel el set actualizado de nombres asignados."""
        self._names_panel.set_assigned(set(self._seat_names.values()))

    def _clear_all_seats(self):
        """Borra todos los nombres asignados de los asientos."""
        for key in list(self._seat_names.keys()):
            btn = getattr(self, f"Seat{key}", None)
            if isinstance(btn, (GoButton, SpecialDragButton)):
                btn.set_name("", emit_signal=False)
        self._seat_names.clear()
        save_names_data(self._names_list, self._seat_names)
        self._sync_assigned_to_panel()

    def _update_backlight_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)