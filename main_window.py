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
    QMainWindow, QPushButton, QToolButton, QLabel, QFrame,
)

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    ATEMAddress,
    SEAT_POSITIONS,
    load_names_data,
    PRESET_MAP,
)
from atem_monitor import ATEMMonitor
from camera_worker import CameraWorker
from widgets import GoButton, SpecialDragButton
from names_panel import NamesPanel
from visca_mixin import ViscaMixin
from session_mixin import SessionMixin
from dialogs_mixin import DialogsMixin
from config_dialog import ConfigDialog
from seat_names_mixin import SeatNamesMixin

from platform_icons import SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT
from seat_builder import build_special_seat_button

from chairman_presets import (
    load_chairman_presets, save_chairman_presets,
    next_available_preset, CHAIRMAN_GENERIC_PRESET,
)
from chairman_button import ChairmanButton
from camera_indicator import CameraIndicator
from auditorium_overlay import AuditoriumOverlay


class MainWindow(ViscaMixin, SessionMixin, DialogsMixin, SeatNamesMixin, QMainWindow):
    """Ventana principal 1920x1080 px."""

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

        self._atem_monitor = ATEMMonitor(ATEMAddress, parent=self)
        self._atem_monitor.switched_to_input2.connect(self._send_comments_cam_home)
        self._atem_monitor.start()

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
        self._build_set_overlay()
        self._build_seat_buttons()
        self._build_session_controls()
        self._build_right_panel()
        self._build_names_panel()
        self._restore_seat_names()
        self._build_table_seats()
        self._build_platform_icons()   # AL FINAL: z-order
        self._build_camera_indicator()
        self._build_mode_indicator()

        self.BtnNames.raise_()
        self.BtnNames.hide()

        self.BtnCall.clicked.connect(lambda: self._names_panel.set_edit_mode(False))
        self.BtnCall.clicked.connect(lambda: self._update_mode_indicator('call'))
        self.BtnSet.clicked.connect(lambda:  self._names_panel.set_edit_mode(True))
        self.BtnSet.clicked.connect(lambda:  self._update_mode_indicator('set'))

    def _build_camera_indicator(self):
        """Crea el indicador visual de cámara activa (spotlight entre plataforma y asientos 11-12)."""
        self._cam_indicator = CameraIndicator(self)
        self._cam_indicator.set_mode('platform')   # Cam1 está activa por defecto
        self._cam_indicator.raise_()

    def _build_mode_indicator(self):
        """
        Badge en la esquina superior derecha del panel izquierdo que muestra
        el modo actual: 📷 (Call) o ✏ (Set).
        Se posiciona a la derecha de los iconos de plataforma, antes del panel derecho.
        """
        self._mode_indicator = QLabel('📷', self)
        self._mode_indicator.setGeometry(1100, 18, 68, 68)
        self._mode_indicator.setAlignment(Qt.AlignCenter)
        self._mode_indicator.setStyleSheet(
            "QLabel {"
            "  font-size: 32px;"
            "  background-color: rgba(0, 0, 0, 55);"
            "  border-radius: 12px;"
            "  border: 1px solid rgba(255,255,255,60);"
            "}"
        )
        self._mode_indicator.raise_()

    def _update_mode_indicator(self, mode: str):
        """Actualiza el icono del badge y el overlay: 'call' → 📷+puntos  |  'set' → ✏+relleno"""
        if mode == 'set':
            self._mode_indicator.setText('✏')
        else:
            self._mode_indicator.setText('📷')
        self._set_overlay.set_mode(mode)

    def _build_set_overlay(self):
        """
        Overlay del panel izquierdo con dos modos visuales:
          call → puntitos blancos sutiles
          set  → relleno blanco semitransparente
        Creado entre background y seat_buttons para z-order correcto.
        """
        self._set_overlay = AuditoriumOverlay(self)
        self._set_overlay.set_mode('call')

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
            if seat_number in (128, 129, 130, 131):
                button = build_special_seat_button(seat_number, x, y, parent=self)
            else:
                button = GoButton(seat_number, self)
                button.move(x, y)
            button.name_assigned.connect(self._on_seat_name_assigned)
            button.clicked.connect(
                lambda checked=False, n=seat_number: self.go_to_preset(n))
            setattr(self, f"Seat{seat_number}", button)

    def _build_session_controls(self):
        # BtnSession y SessionStatus se mantienen como atributos de MainWindow
        # para que SessionMixin pueda actualizarlos, pero están ocultos:
        # el control de sesión se muestra en el modal del engranaje (ConfigDialog).
        self.BtnSession = QPushButton('\u23fb', self)
        self.BtnSession.setGeometry(10, 10, 50, 50)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.BtnSession.setStyleSheet(self._STYLE_BTN_OFF)
        self.BtnSession.clicked.connect(self.ToggleSession)
        self.BtnSession.setVisible(False)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")
        self.SessionStatus.setVisible(False)

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
        from right_panel import RightPanel
        self._right_panel = RightPanel(self)
        self._right_panel.connect_joystick(
            handlers={
                'up':        self.Up,
                'down':      self.Down,
                'left':      self.Left,
                'right':     self.Right,
                'upleft':    self.UpLeft,
                'upright':   self.UpRight,
                'downleft':  self.DownLeft,
                'downright': self.DownRight,
            },
            stop_handler=self.Stop,
        )

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
        """Para el hilo del ATEM antes de cerrar la ventana."""
        self._atem_monitor.requestInterruption()
        self._atem_monitor.wait(2000)
        event.accept()

    def _update_backlight_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)
        # Actualizar indicador de cámara activa
        self._cam_indicator.set_mode('platform' if cam_key == 1 else 'comments')