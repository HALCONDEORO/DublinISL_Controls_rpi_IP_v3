#!/usr/bin/env python3
# main_window.py — Ventana principal: layout de UI + wire-up de EventBus
#
# ARQUITECTURA:
#   MainWindow solo hace:
#     1. Construir widgets y layout
#     2. Instanciar las capas (SystemState, EventBus, servicios, Controller)
#     3. Conectar señales Qt → EventBus.emit()
#     4. Suscribirse a eventos del bus para actualizar display
#
#   Nunca llama a VISCA directamente.
#   Nunca llama a CameraManager directamente (excepto para workers de señales Qt).
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - Eliminados _chairman_recall() y _save_chairman_preset(): Controller los gestiona.
#   - ChairmanButton recibe bus + preset_svc en lugar de callbacks y presets_ref.
#   - SessionController se actualiza para usar SessionService vía Controller.
#   - EventBus conecta joystick, asientos, chairman → Controller → CameraService.

from __future__ import annotations

import logging
import os

from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QLabel, QMainWindow,
    QPushButton, QToolButton, QVBoxLayout,
)

logger = logging.getLogger(__name__)

from config import (
    CAM1, CAM2,
    ATEMAddress,
    SEAT_POSITIONS,
    load_names_data,
    PRESET_MAP,
    check_all_cameras,
)
from atem_monitor import ATEMMonitor
from camera_manager import CameraManager
from widgets import GoButton, SpecialDragButton
from names_panel import NamesPanel
from visca_mixin import ViscaController
from session_mixin import SessionController
from dialogs_mixin import DialogsController
from config_dialog import ConfigDialog
from seat_names_mixin import SeatNamesController

from platform_icons import SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT
from seat_builder import build_special_seat_button

from chairman_button import ChairmanButton
from camera_indicator import CameraIndicator
from auditorium_overlay import AuditoriumOverlay

# ── Nueva arquitectura ────────────────────────────────────────────────────────
from core.state import SystemState
from core.events import AsyncEventBus, EventType
from core.controller import Controller
from application.preset_service import PresetService
from application.camera_service import CameraService
from application.session_service import SessionService
from domain.preset import PRESET_CHAIRMAN_GENERIC


class MainWindow(QMainWindow):
    """Ventana principal 1920x1080 px."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Camera Controls')
        self.setGeometry(0, 0, 1920, 1080)

        self.session_active = False
        self._cameras = CameraManager(CAM1, CAM2)

        _data = load_names_data()
        self._names_list = _data["names"]
        self._seat_names = _data["seats"]

        # ── Nueva arquitectura: instanciar capas ──────────────────────────
        self._state      = SystemState()
        self._bus        = AsyncEventBus()
        self._bus.start()
        self._preset_svc = PresetService()
        self._camera_svc = CameraService(self._cameras)
        self._session_svc = SessionService(self._camera_svc)
        self._controller = Controller(
            state=self._state,
            bus=self._bus,
            camera_svc=self._camera_svc,
            preset_svc=self._preset_svc,
            session_svc=self._session_svc,
        )

        # ── Controladores Qt heredados (siguen activos durante la migración) ──
        self._visca           = ViscaController(self)
        self._session         = SessionController(self)
        self._dialogs         = DialogsController(self)
        self._seat_names_ctrl = SeatNamesController(self)

        self._build_ui()
        self._build_overlays()

        # Señales de conexión a indicadores visuales
        self._cameras.worker(CAM1.ip).signals.connection_changed.connect(
            lambda ok: (self.Cam1.set_connected(ok), self._update_controls_visibility()))
        self._cameras.worker(CAM2.ip).signals.connection_changed.connect(
            lambda ok: (self.Cam2.set_connected(ok), self._update_controls_visibility()))
        self._update_controls_visibility()

        # ── Modo simulación ───────────────────────────────────────────────
        from pathlib import Path as _Path
        if _Path("sim_ip_backup.json").exists():
            from simulation.sim_worker import start_simulation
            start_simulation(CAM1.ip, CAM2.ip)

        self._atem_monitor = ATEMMonitor(ATEMAddress, parent=self)
        self._atem_monitor.switched_to_input2.connect(self._visca._send_comments_cam_home)
        self._atem_monitor.start()

    # ─────────────────────────────────────────────────────────────────────
    # Overlays de inicio
    # ─────────────────────────────────────────────────────────────────────

    def _build_overlays(self):
        from login_screen import LoginScreen
        self._login_overlay = LoginScreen(parent=self)
        self._login_overlay.setGeometry(0, 0, 1920, 1080)
        self._login_overlay.raise_()
        self._login_overlay.login_successful.connect(self._on_login_done)

    def _on_login_done(self):
        from splash_screen import SplashScreen
        self._login_overlay.hide()
        self._splash_overlay = SplashScreen(parent=self)
        self._splash_overlay.setGeometry(0, 0, 1920, 1080)
        self._splash_overlay.raise_()
        self._splash_overlay.show()
        self._splash_overlay.startup_complete.connect(self._on_startup_done)
        self._splash_overlay._start_initialization()

    def _on_startup_done(self):
        self._splash_overlay.hide()
        self._visca._refresh_zoom_slider()

    # ─────────────────────────────────────────────────────────────────────
    # Construcción de la UI
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_background()
        self._build_set_overlay()
        self._build_seat_buttons()
        self._build_session_controls()
        self._build_right_panel()
        self._build_names_panel()
        self._seat_names_ctrl._restore_seat_names()
        self._build_table_seats()
        self._build_platform_icons()
        self._build_camera_indicator()
        self._build_mode_buttons()

        self.BtnNames.raise_()
        self.BtnNames.hide()

        self.BtnCall.clicked.connect(lambda: self._names_panel.set_edit_mode(False))
        self.BtnCall.clicked.connect(lambda: self._update_mode_indicator('call'))
        self.BtnSet.clicked.connect(lambda:  self._names_panel.set_edit_mode(True))
        self.BtnSet.clicked.connect(lambda:  self._update_mode_indicator('set'))

    def _build_camera_indicator(self):
        self._cam_indicator = CameraIndicator(self)
        self._cam_indicator.set_mode('platform')
        self._cam_indicator.raise_()

    def _build_mode_buttons(self):
        rp         = self._right_panel
        call_frame = rp.call_frame
        set_frame  = rp.set_frame

        self.BtnCall = QPushButton(self)
        self.BtnCall.setCheckable(True)
        self.BtnCall.setAutoExclusive(True)
        self.BtnCall.setChecked(True)
        self.BtnCall.hide()

        self.BtnSet = QPushButton(self)
        self.BtnSet.setCheckable(True)
        self.BtnSet.setAutoExclusive(True)
        self.BtnSet.hide()

        self.PresetModeGroup = QButtonGroup(self)
        self.PresetModeGroup.addButton(self.BtnCall)
        self.PresetModeGroup.addButton(self.BtnSet)

        def _call_press(e):
            self.BtnCall.click()
            rp.set_active_mode('call')

        def _set_press(e):
            self.BtnSet.click()
            rp.set_active_mode('set')

        call_frame.mousePressEvent = _call_press
        set_frame.mousePressEvent  = _set_press

        self.BtnCall.clicked.connect(self._on_preset_mode_changed)
        self.BtnSet.clicked.connect(self._on_preset_mode_changed)

    def _update_mode_indicator(self, mode: str):
        self._set_overlay.set_mode(mode)
        GoButton.set_call_mode(mode == 'call')
        for btn in self.findChildren(GoButton):
            btn._apply_style()

    def _build_set_overlay(self):
        self._set_overlay = AuditoriumOverlay(self)
        self._set_overlay.set_mode('call')

    def _build_background(self):
        bg_path = "Background_ISL_v3.jpg"
        if not os.path.exists(bg_path):
            logger.warning("%s no encontrado — fondo vacío", bg_path)
            return
        pixmap = QPixmap(bg_path).scaled(
            1920, 1080, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        background = QLabel(self)
        background.setPixmap(pixmap)
        background.setGeometry(0, 0, 1920, 1080)
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
        btn.setGeometry(cx - btn_w // 2, 30, btn_w, btn_h)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 13px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        btn.clicked.connect(lambda checked=False: self._visca.go_to_preset(2))
        btn.raise_()

        # ── Chairman (preset 1) — ChairmanButton con EventBus ─────────────
        cx = 744
        self._chairman_btn = ChairmanButton(
            bus        = self._bus,
            preset_svc = self._preset_svc,
            svg_data   = SVG_CHAIRMAN,
            icon_w=90, icon_h=90,
            parent=self,
        )
        self._chairman_btn.setGeometry(cx - btn_w // 2, 30, btn_w, btn_h)
        self._chairman_btn.name_assigned.connect(self._seat_names_ctrl._on_seat_name_assigned)
        self._chairman_btn.clicked.connect(
            lambda checked=False: self._visca.go_to_preset(PRESET_CHAIRMAN_GENERIC))
        self._chairman_btn.raise_()
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
        btn.setGeometry(cx - btn_w // 2, 30, btn_w, btn_h)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 13px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        btn.clicked.connect(lambda checked=False: self._visca.go_to_preset(3))
        btn.raise_()

    # ─────────────────────────────────────────────────────────────────────
    # Seat buttons
    # ─────────────────────────────────────────────────────────────────────

    def _build_seat_buttons(self):
        for seat_number, (x, y) in SEAT_POSITIONS.items():
            if seat_number in (128, 129, 130, 131):
                button = build_special_seat_button(seat_number, x, y, parent=self)
            else:
                button = GoButton(seat_number, self)
                button.move(x, y)
            button.name_assigned.connect(self._seat_names_ctrl._on_seat_name_assigned)
            button.clicked.connect(
                lambda checked=False, n=seat_number: self._visca.go_to_preset(n))
            setattr(self, f"Seat{seat_number}", button)

    def _build_session_controls(self):
        self.BtnSession = QPushButton('\u23fb', self)
        self.BtnSession.setGeometry(10, 10, 50, 50)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.BtnSession.setStyleSheet(SessionController._STYLE_BTN_OFF)
        self.BtnSession.clicked.connect(self._session.ToggleSession)
        self.BtnSession.setVisible(False)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")
        self.SessionStatus.setVisible(False)

        self.BtnNames = QPushButton(self)
        self.BtnNames.setGeometry(1392, 15, 50, 40)
        self.BtnNames.setCheckable(True)
        self.BtnNames.setToolTip('Attendees panel')
        self.BtnNames.setStyleSheet(
            "QPushButton { background: white; border: 2px solid #1976D2;"
            " border-radius: 6px; }"
            "QPushButton:checked { background: #1976D2; }"
            "QPushButton:pressed  { background: #e3f2fd; }"
        )
        _pe_svg = QSvgRenderer(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'person-edit.svg'))
        _pe_pix = QPixmap(26, 26)
        _pe_pix.fill(Qt.transparent)
        _p = QtGui.QPainter(_pe_pix)
        _pe_svg.render(_p)
        _p.end()
        self.BtnNames.setIcon(QtGui.QIcon(_pe_pix))
        self.BtnNames.setIconSize(_pe_pix.size())
        self.BtnNames.clicked.connect(self._toggle_names_panel)

    def _build_right_panel(self):
        from right_panel import RightPanel
        self._right_panel = RightPanel(self)
        self._right_panel.connect_joystick(
            handlers={
                'up':        self._visca.Up,
                'down':      self._visca.Down,
                'left':      self._visca.Left,
                'right':     self._visca.Right,
                'upleft':    self._visca.UpLeft,
                'upright':   self._visca.UpRight,
                'downleft':  self._visca.DownLeft,
                'downright': self._visca.DownRight,
            },
            stop_handler=self._visca.Stop,
        )
        self._right_panel.set_joystick_mode('platform')
        self._update_focus_ui()
        self._update_exposure_ui()

        self._cameras.worker(CAM1.ip).signals.connection_changed.connect(self.Cam1.set_connected)
        self._cameras.worker(CAM2.ip).signals.connection_changed.connect(self.Cam2.set_connected)

    def _open_config_dialog(self):
        check_all_cameras()
        dlg = ConfigDialog(parent=self)
        dlg.exec_()

    # ─────────────────────────────────────────────────────────────────────
    # Panel de asistentes
    # ─────────────────────────────────────────────────────────────────────

    def _build_names_panel(self):
        self._names_panel = NamesPanel(
            self._names_list, self._seat_names_ctrl._on_names_list_changed,
            self._seat_names_ctrl._clear_all_seats, parent=self)
        self._names_panel.hide()

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

    def closeEvent(self, event):
        self._bus.stop()
        self._atem_monitor.requestInterruption()
        self._atem_monitor.wait(2000)
        event.accept()

    def _update_focus_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        self._right_panel.set_focus_mode(self._cameras.focus_mode[cam_key])

    def _update_exposure_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        self._right_panel.set_exposure_level(self._cameras.exposure_level[cam_key])

    def _update_controls_visibility(self):
        connected = self.Cam1._connected if self.Cam1.isChecked() else self.Cam2._connected
        self._right_panel.show_camera_controls(connected)

    def _update_backlight_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self._cameras.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)
        self._cam_indicator.set_mode('platform' if cam_key == 1 else 'comments')
