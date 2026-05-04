#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# main_window.py — Ventana principal: layout de UI + wire-up de AsyncEventBus
#
# ARQUITECTURA:
#   MainWindow solo hace:
#     1. Construir widgets y layout
#     2. Instanciar las capas (SystemState, AsyncEventBus, servicios, Controller)
#     3. Conectar señales Qt → AsyncEventBus.emit()
#     4. Suscribirse a eventos del bus para actualizar display
#
#   Nunca llama a VISCA directamente.
#   Nunca llama a CameraManager directamente (excepto para workers de señales Qt).
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - Eliminados _chairman_recall() y _save_chairman_preset(): Controller los gestiona.
#   - ChairmanButton recibe bus + preset_svc en lugar de callbacks y presets_ref.
#   - SessionController se actualiza para usar SessionService vía Controller.
#   - AsyncEventBus conecta joystick, asientos, chairman → Controller → CameraService.

from __future__ import annotations

import logging
import os
import time

from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QLabel, QMainWindow,
    QPushButton, QToolButton, QVBoxLayout,
)

logger = logging.getLogger(__name__)

from config import (
    CAM1, CAM2,
    ATEM,
    SEAT_POSITIONS,
    load_names_data,
    PRESET_MAP,
    check_all_cameras,
    PAN_SPEED_MAX,
    TILT_SPEED_MAX,
    ZOOM_DRIVE_MAX,
)
from atem_monitor import ATEMMonitor
from ptz.visca import CameraManager
from widgets import GoButton, SpecialDragButton
from names_panel import NamesPanel
from ptz.visca.controller import ViscaController
from session_mixin import SessionController
from dialogs_mixin import DialogsController
from config_dialog import ConfigDialog
from seat_names_mixin import SeatNamesController

from platform_icons import SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT
from seat_builder import build_special_seat_button

from chairman_button import ChairmanButton
from camera_indicator import CameraIndicator
from auditorium_overlay import AuditoriumOverlay
from mode_border_overlay import ModeBorderOverlay

# ── Nueva arquitectura ────────────────────────────────────────────────────────
from core.state import SystemState
from core.events import AsyncEventBus, EventType
from core.controller import Controller
from core.supervisor import Supervisor
from application.preset_service import PresetService
from application.camera_service import CameraService
from application.session_service import SessionService
from domain.preset import PRESET_CHAIRMAN_GENERIC
from ptz.visca import commands as vcmd


class MainWindow(QMainWindow):
    """Ventana principal 1920x1080 px."""

    _WATCHDOG_COOLDOWN       = 1.5     # s mínimos entre dos reducciones del mismo tipo
    _WATCHDOG_RECOVERY_MS    = 20_000  # ms hasta el primer intento de recuperación
    _WATCHDOG_WINDOW_SECS    = 300     # ventana de 5 min: más de 3 fallos → bloqueado
    _WATCHDOG_MAX_RETRIES    = 3       # intentos de recuperación antes de bloquear

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Camera Controls')
        self.setGeometry(0, 0, 1920, 1080)

        self.session_active = False
        self._last_activity: float = time.time()
        self._pan_cap:        int = PAN_SPEED_MAX   # 24 — watchdog lo reduce en error move
        self._tilt_cap:       int = TILT_SPEED_MAX  # 20 — watchdog lo reduce en error move
        self._zoom_drive_cap: int = ZOOM_DRIVE_MAX  # 7  — watchdog lo reduce en error zoom_drive
        self._watchdog_state: dict = {
            'move':       self._fresh_watchdog_state(),
            'zoom_drive': self._fresh_watchdog_state(),
        }
        self._cameras = CameraManager(CAM1, CAM2, on_worker_ready=self._on_worker_ready)

        _data = load_names_data()
        self._names_list = _data["names"]
        self._seat_names = _data["seats"]

        # ── Nueva arquitectura: instanciar capas ──────────────────────────
        self._state      = SystemState()
        self._bus        = AsyncEventBus()
        self._bus.start()
        for _evt in (EventType.CAMERA_MOVE, EventType.CAMERA_ZOOM, EventType.SEAT_SELECTED):
            self._bus.subscribe(_evt, lambda _e: self._record_activity())
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

        self._atem_monitor = ATEMMonitor(ATEM.ip, parent=self)
        self._atem_monitor.switched_to_input2.connect(self._visca._send_comments_cam_home)
        self._atem_monitor.program_changed.connect(self._right_panel.set_atem_program)
        self._atem_monitor.atem_connected.connect(self._right_panel.set_atem_connected)
        self._atem_monitor.start()

        # Auto-apagado por inactividad (2 horas)
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start(60_000)  # comprueba cada minuto

        # Flag que evita reinicios durante el cierre de la aplicación.
        self._shutting_down = False
        self._supervisor = self._build_supervisor()

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

        # _mode_border debe existir antes de conectar las señales porque
        # _update_mode_indicator lo referencia en cada pulsación de modo.
        self._mode_border = ModeBorderOverlay(self)
        self._mode_border.raise_()

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
        self._mode_border.set_mode(mode)
        GoButton.set_call_mode(mode == 'call')
        for btn in self.findChildren(GoButton):
            btn._apply_style()
        for btn in self.findChildren(SpecialDragButton):
            btn._apply_style()

    def _build_set_overlay(self):
        self._set_overlay = AuditoriumOverlay(self)
        self._set_overlay.set_mode('call')

    def _build_background(self):
        from pathlib import Path
        bg_path = Path(__file__).resolve().parent / "Background_ISL_v3.jpg"
        if not bg_path.exists():
            logger.warning("%s no encontrado — fondo vacío", bg_path)
            return
        pixmap = QPixmap(str(bg_path)).scaled(
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

        # ── Chairman (preset 1) — ChairmanButton con AsyncEventBus ──────────
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
        self._chairman_btn.clicked.connect(self._on_chairman_btn_clicked)
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

    def _zoom_to_speed(self, zoom: int) -> int:
        # zoom %     velocidad   (~% de TILT_SPEED_MAX=20; pan puede llegar a 24 via _pan_cap)
        # ─────────────────────────────────────────
        #   0 –  9      20          100 %
        #  10 – 18      19           95 %
        #  19 – 27      18           90 %
        #  28 – 36      16           80 %
        #  37 – 45      15           75 %
        #  46 – 54      14           70 %
        #  55 – 63      13           65 %
        #  64 – 72      11           55 %
        #  73 – 81      10           50 %
        #  82 – 90       9           45 %
        #  91 – 100      8           40 %
        if zoom <=  9:   raw = 20
        elif zoom <= 18: raw = 19
        elif zoom <= 27: raw = 18
        elif zoom <= 36: raw = 16
        elif zoom <= 45: raw = 15
        elif zoom <= 54: raw = 14
        elif zoom <= 63: raw = 13
        elif zoom <= 72: raw = 11
        elif zoom <= 81: raw = 10
        elif zoom <= 90: raw = 9
        else:            raw = 8
        return min(raw, self._tilt_cap)

    # ── Watchdog de velocidad VISCA ───────────────────────────────────────────

    @staticmethod
    def _fresh_watchdog_state() -> dict:
        return {'last_reduction': 0.0, 'window_start': 0.0, 'retries': 0}

    def _reset_watchdog_state(self) -> None:
        """Restablece caps y estado al iniciar sesión."""
        self._pan_cap        = PAN_SPEED_MAX
        self._tilt_cap       = TILT_SPEED_MAX
        self._zoom_drive_cap = ZOOM_DRIVE_MAX
        self._camera_svc.pan_cap        = self._pan_cap
        self._camera_svc.tilt_cap       = self._tilt_cap
        self._camera_svc.zoom_drive_cap = self._zoom_drive_cap
        self._watchdog_state = {
            'move':       self._fresh_watchdog_state(),
            'zoom_drive': self._fresh_watchdog_state(),
        }
        logger.info("Watchdog VISCA: estado y caps restablecidos al inicio de sesión")

    def _on_worker_ready(self, worker) -> None:
        worker.signals.visca_error.connect(self._on_visca_speed_error)
        worker.signals.connection_changed.connect(
            lambda ok, _ip=worker.ip: self._on_cam_connected(ok, _ip))

    def _on_cam_connected(self, ok: bool, ip: str) -> None:
        if not ok:
            return
        cam_id = CAM1.cam_id if ip == CAM1.ip else CAM2.cam_id
        self._visca.refresh_ae_mode_async(ip, cam_id)

    def _on_visca_speed_error(self, ip: str, cmd_type: str) -> None:
        if cmd_type not in self._watchdog_state:
            return
        now  = time.monotonic()
        st   = self._watchdog_state[cmd_type]

        # Ventana de 5 min expirada → empezar ciclo nuevo
        if st['window_start'] > 0 and (now - st['window_start']) > self._WATCHDOG_WINDOW_SECS:
            self._watchdog_state[cmd_type] = st = self._fresh_watchdog_state()

        # Bloqueado (agotados los reintentos en esta ventana)
        if st['retries'] >= self._WATCHDOG_MAX_RETRIES:
            return

        # Cooldown: evita cascada de reducciones por errores rápidos consecutivos
        if (now - st['last_reduction']) < self._WATCHDOG_COOLDOWN:
            return

        st['last_reduction'] = now
        if st['window_start'] == 0.0:
            st['window_start'] = now

        self._apply_reduction(cmd_type, ip)

        # Programar intento de recuperación si quedan reintentos
        st['retries'] += 1
        if st['retries'] < self._WATCHDOG_MAX_RETRIES:
            QTimer.singleShot(
                self._WATCHDOG_RECOVERY_MS,
                lambda ct=cmd_type: self._recover_cap(ct),
            )
        else:
            logger.warning(
                "Watchdog VISCA [%s] %s: %d reducciones en %.0f s — cap bloqueado hasta reinicio de sesión",
                cmd_type, ip, self._WATCHDOG_MAX_RETRIES, self._WATCHDOG_WINDOW_SECS,
            )

    def _apply_reduction(self, cmd_type: str, ip: str) -> None:
        if cmd_type == 'move':
            changed = False
            if self._pan_cap > 8:
                self._pan_cap = max(8, self._pan_cap - 2)
                self._camera_svc.pan_cap = self._pan_cap
                changed = True
            if self._tilt_cap > 8:
                self._tilt_cap = max(8, self._tilt_cap - 2)
                self._camera_svc.tilt_cap = self._tilt_cap
                changed = True
            if changed:
                logger.warning(
                    "Watchdog VISCA [move] %s — pan_cap→%d  tilt_cap→%d",
                    ip, self._pan_cap, self._tilt_cap,
                )
        elif cmd_type == 'zoom_drive':
            if self._zoom_drive_cap > 1:
                self._zoom_drive_cap -= 1
                self._camera_svc.zoom_drive_cap = self._zoom_drive_cap
                logger.warning(
                    "Watchdog VISCA [zoom_drive] %s — zoom_drive_cap→%d",
                    ip, self._zoom_drive_cap,
                )

    def _recover_cap(self, cmd_type: str) -> None:
        """Sube el cap un paso para comprobar si la cámara admite mayor velocidad."""
        st = self._watchdog_state.get(cmd_type)
        if st is None or st['retries'] >= self._WATCHDOG_MAX_RETRIES:
            return
        if cmd_type == 'move':
            self._pan_cap  = min(PAN_SPEED_MAX,  self._pan_cap  + 2)
            self._tilt_cap = min(TILT_SPEED_MAX, self._tilt_cap + 2)
            self._camera_svc.pan_cap  = self._pan_cap
            self._camera_svc.tilt_cap = self._tilt_cap
            logger.info(
                "Watchdog VISCA [move]: intento recuperación %d/%d — pan_cap→%d tilt_cap→%d",
                st['retries'], self._WATCHDOG_MAX_RETRIES, self._pan_cap, self._tilt_cap,
            )
        elif cmd_type == 'zoom_drive':
            self._zoom_drive_cap = min(ZOOM_DRIVE_MAX, self._zoom_drive_cap + 1)
            self._camera_svc.zoom_drive_cap = self._zoom_drive_cap
            logger.info(
                "Watchdog VISCA [zoom_drive]: intento recuperación %d/%d — cap→%d",
                st['retries'], self._WATCHDOG_MAX_RETRIES, self._zoom_drive_cap,
            )

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
            speed_provider=lambda: self._zoom_to_speed(self.ZoomSlider.value()),
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

    def _on_chairman_btn_clicked(self):
        name = self._chairman_btn.assigned_name
        if name:
            self._bus.emit(EventType.CHAIRMAN_ASSIGNED, name=name)
        else:
            self._visca.go_to_preset(PRESET_CHAIRMAN_GENERIC)

    def _on_preset_mode_changed(self):
        if self.BtnCall.isChecked():
            if self.BtnNames.isChecked():
                self.BtnNames.setChecked(False)
                self._names_panel.hide()
            self.BtnNames.hide()
        else:
            self.BtnNames.show()
            self.BtnNames.raise_()

    def _build_supervisor(self) -> Supervisor:
        """Registra los workers y arranca el supervisor de threads."""
        sup = Supervisor()

        # Workers ya creados al conectar señales de connection_changed en __init__.
        cam1 = self._cameras.worker(CAM1.ip)
        cam2 = self._cameras.worker(CAM2.ip)

        # Los lambdas capturan el objeto worker (no la variable local), así que
        # seguirán apuntando al mismo worker aunque _build_supervisor ya haya retornado.
        sup.registrar(
            "camera_worker_cam1",
            lambda: cam1._thread.is_alive(),
            cam1.restart,
        )
        sup.registrar(
            "camera_worker_cam2",
            lambda: cam2._thread.is_alive(),
            cam2.restart,
        )
        # El lambda evalúa self._atem_monitor en tiempo de ejecución, por lo que
        # siempre comprueba la instancia activa incluso tras un reinicio.
        sup.registrar(
            "atem_monitor",
            lambda: self._atem_monitor.isRunning(),
            self._restart_atem_monitor,
        )

        sup.start()
        return sup

    def _restart_atem_monitor(self):
        # Llamado desde el hilo del supervisor: delegar al hilo principal de Qt.
        QTimer.singleShot(0, self._do_restart_atem_monitor)

    def _do_restart_atem_monitor(self):
        # Ejecutado en el hilo principal de Qt (vía QTimer.singleShot).
        if self._shutting_down:
            return
        self._atem_monitor.requestInterruption()
        self._atem_monitor.wait(2000)
        self._atem_monitor = ATEMMonitor(ATEM.ip, parent=self)
        self._atem_monitor.switched_to_input2.connect(self._visca._send_comments_cam_home)
        self._atem_monitor.program_changed.connect(self._right_panel.set_atem_program)
        self._atem_monitor.atem_connected.connect(self._right_panel.set_atem_connected)
        self._atem_monitor.start()
        logger.info("ATEMMonitor reiniciado por el supervisor")

    def _record_activity(self):
        self._last_activity = time.time()

    _INACTIVITY_TIMEOUT = 2 * 3600  # 2 horas en segundos

    def _check_inactivity(self):
        if not self.session_active:
            return
        if time.time() - self._last_activity < self._INACTIVITY_TIMEOUT:
            return
        logger.info("Auto power-off: 2 horas sin actividad")
        self._visca._send_cmd(CAM1.ip, vcmd.power_off(CAM1.cam_id))
        self._visca._send_cmd(CAM2.ip, vcmd.power_off(CAM2.cam_id))
        self.session_active = False
        self.BtnSession.setStyleSheet(SessionController._STYLE_BTN_OFF)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.SessionStatus.setText('OFF')
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

    def closeEvent(self, event):
        # Marcar antes de parar el supervisor para que cualquier QTimer.singleShot
        # pendiente de _restart_atem_monitor no relance el ATEMMonitor durante el cierre.
        self._shutting_down = True
        self._supervisor.stop()
        self._bus.stop()
        self._atem_monitor.requestInterruption()
        self._atem_monitor.wait(2000)

        # Power OFF ambas cámaras al salir (VISCA 01 04 00 03 FF)
        self._visca._send_cmd(CAM1.ip, vcmd.power_off(CAM1.cam_id))
        self._visca._send_cmd(CAM2.ip, vcmd.power_off(CAM2.cam_id))

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

    @pyqtSlot(int)
    def _set_zoom_feedback(self, pct: int):
        """Actualiza el slider desde el feedback de red sin disparar ZoomAbsolute."""
        self._zoom_feedback = True
        self.ZoomSlider.setValue(pct)
        self._zoom_feedback = False
