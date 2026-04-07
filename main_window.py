#!/usr/bin/env python3
# main_window.py — Ventana principal: solo layout de UI
#
# CAMBIOS v2→v3:
#   - bg_path: Background_ISL_v2.jpg → Background_ISL_v3.jpg
#   - Iconos Left/Chairman/Right: SVG embebido en código como
#     QSvgWidget sobre el fondo. El JPG queda limpio sin iconos.
#   MOTIVO: separar assets estáticos (fondo) de iconos editables
#   sin regenerar la imagen de fondo cada vez.
#
# CAMBIOS EN ESTE REFACTOR:
#   1. IMPORTS MOVIDOS AL NIVEL DE MÓDULO:
#      - QSvgRenderer, QToolButton, SVG_WHEELCHAIR estaban dentro de
#        _build_platform_icons() y _build_seat_buttons(), en algunos casos
#        dentro de un loop. Un import dentro de un loop se re-evalúa
#        (aunque Python cachea el módulo) y confunde al lector.
#        MOTIVO: PEP 8 — todos los imports al inicio del archivo.
#
#   2. _build_platform_presets() ELIMINADO:
#      El método existía solo con `pass` (código fusionado en _build_platform_icons),
#      pero seguía siendo llamado desde _build_ui(). Código muerto eliminado.
#      MOTIVO: llamar a un método vacío es ruido sin ningún beneficio.
#
#   3. `if seat_number < 4: continue` ELIMINADO:
#      SEAT_POSITIONS solo tiene claves ≥ 4, por lo que este check
#      nunca era verdadero. Código muerto que confunde.
#
#   4. COMENTARIO DE _build_table_seats() LIMPIADO:
#      El bloque de comentario describía una geometría antigua (90, 957, 195, 18)
#      que no coincidía con la geometría real (96, 900, 245, 50).
#      Se reescribió para reflejar la geometría actual.

from __future__ import annotations

import os

from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgRenderer          # MOVIDO: antes estaba dentro de _build_platform_icons() y _build_seat_buttons()
from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QToolButton,     # QToolButton: MOVIDO desde el interior del loop de _build_platform_icons()
    QLabel, QButtonGroup, QSlider,
)

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    Cam1Check, Cam2Check,
    SPEED_MIN, SPEED_MAX, SPEED_DEFAULT,
    SEAT_POSITIONS, BUTTON_COLOR,
    load_names_data, save_names_data,
)
from camera_worker import CameraWorker
from widgets import GoButton, SpecialDragButton, NamesPanel, make_arrow_btn
from visca_mixin import ViscaMixin
from session_mixin import SessionMixin
from dialogs_mixin import DialogsMixin

from platform_icons import (
    SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT,
    SVG_WHEELCHAIR,   # MOVIDO: antes se importaba dentro del loop de _build_seat_buttons()
)


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
        self._names_list  = _data["names"]
        self._seat_names  = _data["seats"]

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────
    # Construcción de la UI
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_background()
        # ELIMINADO: _build_platform_presets() — método vacío (pass), código muerto.
        # Los botones de plataforma se crean en _build_platform_icons().
        self._build_seat_buttons()
        self._build_session_controls()
        self._build_right_panel()
        self._build_names_panel()
        self._restore_seat_names()
        self._build_table_seats()

        # Iconos AL FINAL: z-order — el último widget creado queda al frente.
        self._build_platform_icons()

        # FIX z-order: BtnNames se crea antes que _build_right_panel(), por lo que
        # el label "Camera Selection" (x=1500, y=20, w=360, h=30) queda encima y
        # bloquea los clicks. raise_() lo sube al frente después de todo el layout.
        self.BtnNames.raise_()

        # Estado inicial: Call es el modo por defecto → BtnNames oculto.
        self.BtnNames.hide()

        # Conectar BtnCall/BtnSet al modo edición del panel.
        # No se puede hacer en _build_preset_mode() porque _names_panel no existe aún.
        self.BtnCall.clicked.connect(lambda: self._names_panel.set_edit_mode(False))
        self.BtnSet.clicked.connect(lambda:  self._names_panel.set_edit_mode(True))

    def _build_background(self):
        """
        Carga y escala la imagen de fondo.
        Si el archivo no existe, la ventana arranca con fondo vacío
        en lugar de lanzar un error fatal — robustez en RPi sin assets.
        """
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
        """
        Dibuja un rectángulo que simula la mesa compartida por los asientos 124 y 125.

        Geometría actual: x=96, y=900, w=245, h=50
          - x=96:  18px antes del seat 124 (x=114)
          - y=900: encima de los asientos (y=960), con margen de 60px
          - w=245: abarca seat 124 (71px) + hueco + seat 125 con margen
          - h=50:  altura visible del borde de la mesa

        MOTIVO: los asientos 124 y 125 están pegados a la pared inferior
        de la sala. Un rectángulo semitransparente debajo de ambos los
        identifica como asientos de mesa, diferenciándolos del resto.
        """
        mesa = QLabel(self)
        mesa.setGeometry(96, 900, 245, 50)
        mesa.setStyleSheet(
            "background-color: rgba(100, 80, 60, 120);"  # marrón semitransparente
            "border: 2px solid rgba(70, 50, 30, 200);"   # borde oscuro
            "border-radius: 4px;"
        )

    def _build_platform_icons(self):
        """
        Crea los 3 botones de plataforma (Left/Chairman/Right) como QToolButton
        con icono SVG + label de texto en un único widget.

        MOTIVO DE UNIFICACIÓN icono+botón:
        Antes eran dos widgets separados (QLabel para el SVG + QPushButton para el texto),
        lo que causaba problemas de z-order y de área de click.
        Un solo QToolButton = un solo click area = sin solapamientos.

        IMPORTS: QSvgRenderer y QToolButton están ahora al inicio del módulo,
        no dentro de este método (y menos dentro del loop).
        MOTIVO: PEP 8 — los imports van al principio del archivo.

        Posiciones centradas sobre la zona de plataforma (x 0-1450):
          Left (dos personas): centro x≈562
          Chairman (atril):    centro x≈744
          Right (mesa+sillas): centro x≈938
        """
        # (svg_data, label_en_pantalla, x_center, preset_num, icon_w, icon_h, drag_drop)
        # drag_drop=True: solo Chairman acepta asignación de nombre.
        # Left y Right son posiciones fijas sin orador asignado.
        icons = [
            (SVG_LEFT,     'Left',     562, 2, 70, 70, False),
            (SVG_CHAIRMAN, 'Chairman', 744, 1, 90, 90, True),
            (SVG_RIGHT,    'Right',    938, 3, 70, 70, False),
        ]
        btn_w, btn_h = 110, 115

        for svg_data, label, cx, preset_num, icon_w, icon_h, drag_drop in icons:
            # Renderizar SVG a QPixmap transparente para usarlo como QIcon
            renderer = QSvgRenderer(QtCore.QByteArray(svg_data.encode('utf-8')))
            if not renderer.isValid():
                print(f"[WARNING] SVG inválido para '{label}' — icono no mostrado")

            pixmap = QPixmap(icon_w, icon_h)
            pixmap.fill(Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            renderer.render(painter, QtCore.QRectF(0, 0, icon_w, icon_h))
            painter.end()

            if drag_drop:
                # Chairman: SpecialDragButton — acepta arrastre de nombre desde NamesPanel.
                # seat_id=1 coincide con la clave de preset de Chairman en PRESET_MAP
                # y se usa como clave en seat_names.json ("1": "Nombre").
                btn = SpecialDragButton(seat_id=1, default_label=label, parent=self)
                btn.setGeometry(cx - btn_w // 2, 10, btn_w, btn_h)
                btn.setIcon(QtGui.QIcon(pixmap))
                btn.setIconSize(QtCore.QSize(icon_w, icon_h))
                btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                btn.setStyleSheet(
                    "QToolButton {"
                    "  background-color: transparent; border: none;"
                    "  font: bold 13px; color: black;"
                    "}"
                    "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
                )
                btn.name_assigned.connect(self._on_seat_name_assigned)
                btn.clicked.connect(
                    lambda checked=False, n=preset_num: self.go_to_preset(n))
                btn.raise_()
                # Guardar referencia para _restore_seat_names
                setattr(self, f"Seat{1}", btn)
            else:
                # Left / Right: QToolButton estándar sin drag-drop
                btn = QToolButton(self)
                btn.setText(label)
                btn.setIcon(QtGui.QIcon(pixmap))
                btn.setIconSize(QtCore.QSize(icon_w, icon_h))
                btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                btn.setGeometry(cx - btn_w // 2, 10, btn_w, btn_h)
                btn.setStyleSheet(
                    "QToolButton {"
                    "  background-color: transparent; border: none;"
                    "  font: bold 13px; color: black;"
                    "}"
                    "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
                )
                btn.clicked.connect(
                    lambda checked=False, n=preset_num: self.go_to_preset(n))
                btn.raise_()

    def _build_seat_buttons(self):
        """
        Crea un botón por cada asiento definido en SEAT_POSITIONS.

        CAMBIOS EN ESTE REFACTOR:
          - ELIMINADO: `if seat_number < 4: continue`
            SEAT_POSITIONS no tiene claves < 4, así que nunca se cumplía.
            Era código muerto que confundía la lectura.

          - IMPORTS MOVIDOS: QSvgRenderer y SVG_WHEELCHAIR estaban dentro
            del cuerpo del `if seat_number == 128:`, es decir, dentro del
            loop. Ahora están al inicio del módulo.
        """
        for seat_number, (x, y) in SEAT_POSITIONS.items():

            if seat_number == 128:
                # Asiento de accesibilidad (silla de ruedas): SpecialDragButton con icono SVG.
                renderer = QSvgRenderer(
                    QtCore.QByteArray(SVG_WHEELCHAIR.encode('utf-8')))
                if not renderer.isValid():
                    print("[WARNING] SVG_WHEELCHAIR inválido — asiento 128 sin icono")

                pix = QPixmap(40, 40)
                pix.fill(Qt.transparent)
                painter = QtGui.QPainter(pix)
                renderer.render(painter, QtCore.QRectF(0, 0, 40, 40))
                painter.end()

                button = SpecialDragButton(seat_id=128, default_label='Wheelchair', parent=self)
                button.move(x, y)
                button.resize(55, 65)
                button.setIcon(QtGui.QIcon(pix))
                button.setIconSize(QtCore.QSize(40, 40))
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
                # Botón "Second Room": SpecialDragButton con imagen PNG opcional.
                button = SpecialDragButton(seat_id=129, default_label='Second Room', parent=self)
                button.move(x, y)
                button.resize(55, 65)
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black;"
                    " border-radius: 5px; font: 8px; font-weight: bold; color: "
                    + BUTTON_COLOR + "; }"
                )
                if os.path.exists("second_room.png"):
                    pix = QPixmap("second_room.png").scaled(
                        40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    button.setIcon(QtGui.QIcon(pix))
                    button.setIconSize(QtCore.QSize(40, 40))
                else:
                    print("[WARNING] second_room.png no encontrado")
                button.name_assigned.connect(self._on_seat_name_assigned)
                button.clicked.connect(
                    lambda checked=False, n=seat_number: self.go_to_preset(n))
                setattr(self, f"Seat{seat_number}", button)

            else:
                # Asiento numerado estándar: GoButton con drag-drop y nombre
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
        self.BtnSession.setStyleSheet(self._STYLE_BTN_OFF)  # usa constante de SessionMixin
        self.BtnSession.clicked.connect(self.ToggleSession)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

        # Botón de panel de consejeros — solo visible en modo Set.
        # x=1500: panel derecho de controles. Solo emoji (40×40px).
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

        # Al cambiar entre Call/Set se muestra u oculta BtnNames.
        # El panel de consejeros solo es accesible en modo Set.
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
            ('Auto\nFocus',    (1500, 863, 110, 50), 'Auto Focus ON',                      self.AutoFocus),
            ('One Push\nAF',   (1625, 863, 110, 50), 'One-shot autofocus, then manual',    self.OnePushAF),
            ('Manual\nFocus',  (1750, 863, 110, 50), 'Manual Focus mode',                  self.ManualFocus),
            ('▼ Darker',       (1500, 920, 110, 45), 'Decrease exposure one step',         self.BrightnessDown),
            ('▲ Brighter',     (1750, 920, 110, 45), 'Increase exposure one step',         self.BrightnessUp),
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
        Cam1Address = QPushButton(
            'Platform [Platform] - ' + IPAddress, self)
        Cam1Address.setGeometry(1500, 975, 310, 22)
        Cam1Address.setStyleSheet("font: bold 15px; color:" + Cam1Check)
        Cam1Address.clicked.connect(self.PTZ1Address)

        self._cam2_addr_btn = QPushButton(
            'Comments [Audience] - ' + IPAddress2, self)
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
                btn.set_name(name, emit_signal=False)
        # Sincronizar el set de asignados en el panel tras restaurar desde disco.
        # Sin esto el panel no sabe qué nombres están ocupados al arrancar.
        self._sync_assigned_to_panel()

    def _toggle_names_panel(self, checked: bool):
        if checked:
            self._names_panel.raise_()
            self._names_panel.show()
        else:
            self._names_panel.hide()

    def _on_preset_mode_changed(self):
        """
        Muestra u oculta BtnNames según el modo activo (Call/Set).

        Modo Call → BtnNames invisible.
          Si el panel estaba abierto: se cierra y BtnNames queda sin marcar.
          MOTIVO: en Call no se editan asignaciones.

        Modo Set → BtnNames visible (panel no se abre automáticamente).
        """
        if self.BtnCall.isChecked():
            if self.BtnNames.isChecked():
                self.BtnNames.setChecked(False)
                self._names_panel.hide()
            self.BtnNames.hide()
        else:
            self.BtnNames.show()
            self.BtnNames.raise_()  # mantener z-order sobre el label "Camera Selection"

    def _on_seat_name_assigned(self, seat_number: int, name: str):
        key = str(seat_number)
        if name:
            # Exclusividad: un nombre solo puede estar en un asiento a la vez.
            # Se aplica a GoButton Y SpecialDragButton (Chairman, Wheelchair, Second Room).
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
        save_names_data(self._names_list, self._seat_names)

    def _sync_assigned_to_panel(self):
        """
        Pasa al NamesPanel el set actualizado de nombres asignados a asientos.
        LLAMAR siempre que cambie _seat_names (asignación, borrado, clear all).
        """
        self._names_panel.set_assigned(set(self._seat_names.values()))

    def _clear_all_seats(self):
        """
        Borra todos los nombres asignados de una vez.
        El borrado real se hace aquí (MainWindow tiene acceso a los GoButtons
        y SpecialDragButtons).
        NamesPanel solo dispara este callback después de pedir confirmación.
        """
        for key in list(self._seat_names.keys()):
            btn = getattr(self, f"Seat{key}", None)
            if isinstance(btn, (GoButton, SpecialDragButton)):
                btn.set_name("", emit_signal=False)
        self._seat_names.clear()
        save_names_data(self._names_list, self._seat_names)
        self._sync_assigned_to_panel()

    # ─────────────────────────────────────────────────────────────────────
    # Helper UI
    # ─────────────────────────────────────────────────────────────────────

    def _update_backlight_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)