#!/usr/bin/env python3
# main_window.py — Ventana principal: solo layout de UI
#
# Responsabilidad única: construir y posicionar todos los widgets.
# NO contiene lógica de negocio: cada acción delega en un mixin.
#
# HERENCIA MÚLTIPLE (patrón mixin):
#   MainWindow hereda de ViscaMixin, SessionMixin y DialogsMixin.
#   Python resuelve los métodos por MRO (izquierda a derecha).
#
#   Diagrama:
#     ViscaMixin   → movimiento, zoom, focus, presets
#     SessionMixin → encendido, home, apagado
#     DialogsMixin → cambio IP/ID, help, quit
#     QMainWindow  → base Qt
#
# SISTEMA DE NOMBRES:
#   Los métodos de gestión de nombres (_toggle_names_panel,
#   _on_seat_name_assigned, _on_names_list_changed, _restore_seat_names)
#   viven aquí y NO en un mixin porque interactúan directamente con
#   los widgets del layout (GoButton, NamesPanel).

from __future__ import annotations

import os

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QToolButton,
    QLabel, QButtonGroup, QSlider,
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    Cam1Check, Cam2Check,
    SPEED_MIN, SPEED_MAX, SPEED_DEFAULT,
    SEAT_POSITIONS, BUTTON_COLOR,
    load_names_data, save_names_data,   # ← NUEVO: persistencia de nombres
)
from camera_worker import CameraWorker
from widgets import GoButton, NamesPanel, make_arrow_btn   # ← NamesPanel añadido
from visca_mixin import ViscaMixin
from session_mixin import SessionMixin
from dialogs_mixin import DialogsMixin


class MainWindow(ViscaMixin, SessionMixin, DialogsMixin, QMainWindow):
    """
    Ventana principal 1920×1080 px.

    __init__ solo construye la UI.  Toda la lógica de negocio vive
    en los mixins importados arriba.
    """

    # Estilo compartido para botones toggle (Camera selector y Preset mode).
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
        self.backlight_on = {1: False, 2: False}

        # Estado de sesión
        self.session_active = False

        # Workers de red: uno por cámara, indexados por IP
        self._workers = {
            IPAddress:  CameraWorker(IPAddress),
            IPAddress2: CameraWorker(IPAddress2),
        }

        # ── NUEVO: cargar nombres y asignaciones guardados ────────────────────
        # Se hace antes de _build_ui para que _restore_seat_names (llamado al
        # final de _build_ui) ya tenga los datos disponibles.
        _data            = load_names_data()
        self._names_list = _data["names"]   # lista editable de consejeros
        self._seat_names = _data["seats"]   # {str(seat_num): nombre_asignado}

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
        self._build_names_panel()       # ← NUEVO: panel flotante de nombres
        self._restore_seat_names()      # ← NUEVO: aplica nombres guardados a botones

    def _build_background(self):
        """Carga y escala la imagen de fondo del plano de asientos."""
        bg_path = "Background_ISL_v2.jpg"
        if not os.path.exists(bg_path):
            print(f"[WARNING] {bg_path} no encontrado — fondo vacío")
            return
        pixmap = QPixmap(bg_path).scaled(
            1920, 1080, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        background = QLabel(self)
        background.setPixmap(pixmap)
        background.setGeometry(0, -30, 1920, 1080)
        background.lower()

    def _build_platform_presets(self):
        """
        Crea los 3 botones de preset de plataforma (Chairman, Left, Right).
        Son QPushButton planos — NO GoButton — para preservar el estilo
        transparente con padding-top que muestra el texto bajo el icono del fondo.
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
        GoButton ahora acepta drags y emite name_assigned — se conecta aquí.
        El asiento 129 (Second Room) usa QToolButton con icono especial.
        """
        for seat_number, (x, y) in SEAT_POSITIONS.items():
            if seat_number < 4:
                continue  # los presets 1-3 son de plataforma, no de asiento

            if seat_number == 129:
                # Segunda sala: QToolButton con imagen específica
                button = QToolButton(self)
                button.move(x, y)
                button.resize(55, 65)
                button.setText('Second Room')
                button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                button.setStyleSheet(
                    "QToolButton { background-color: rgba(0,0,0,10); border: 0px solid black; "
                    "border-radius: 5px; font: 8px; font-weight: bold; color: " + BUTTON_COLOR + "; }"
                )
                if os.path.exists("second_room.png"):
                    pix = QPixmap("second_room.png").scaled(
                        40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    button.setIcon(QtGui.QIcon(pix))
                    button.setIconSize(QtCore.QSize(40, 40))
                else:
                    print("[WARNING] second_room.png no encontrado")
            else:
                button = GoButton(seat_number, self)
                button.move(x, y)
                # ── NUEVO: conectar señal de nombre asignado ──────────────────
                # Cada GoButton notifica a MainWindow cuando se le asigna o
                # se le borra un nombre, para persistir en seat_names.json.
                button.name_assigned.connect(self._on_seat_name_assigned)

            button.clicked.connect(
                lambda checked=False, n=seat_number: self.go_to_preset(n)
            )
            setattr(self, f"Seat{seat_number}", button)

    def _build_session_controls(self):
        """Botón de encendido ⏻ y etiqueta OFF/Starting.../ON."""
        self.BtnSession = QPushButton('\u23fb', self)   # ⏻
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

        # BtnNames: siempre visible e independiente del modo Call/Set.
        # El modo solo controla si se puede editar la lista dentro del panel;
        # el botón de apertura siempre está disponible.
        self.BtnNames = QPushButton('👥  Consejeros', self)
        self.BtnNames.setGeometry(140, 15, 170, 35)
        self.BtnNames.setCheckable(True)
        self.BtnNames.setStyleSheet(
            "QPushButton { background: white; border: 2px solid #1976D2; "
            "font: bold 13px; color: #1976D2; border-radius: 6px; }"
            "QPushButton:Checked { background: #1976D2; color: white; }"
            "QPushButton:pressed  { background: #1565C0; color: white; }"
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
        """
        8 botones de dirección + botón Home central.
        angle.png apunta hacia abajo (0°) — rotaciones calculadas desde esa base.
        """
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
    #  NUEVO: Panel de nombres — construcción y gestión
    # ─────────────────────────────────────────────────────────────────────────

    def _build_names_panel(self):
        """
        Instancia NamesPanel como widget hijo (queda dentro de la ventana).
        Se pasa la referencia a self._names_list para que NamesPanel la
        modifique directamente — no hay copia, hay referencia compartida.
        Se pasa _on_names_list_changed como callback para persistir cambios.
        El panel se crea oculto y se muestra con BtnNames.

        MODO EDICIÓN:
          La edición de la lista (CRUD + reordenamiento) solo está disponible
          en modo Set. Se conecta BtnCall y BtnSet para que actualicen el
          estado del panel automáticamente al cambiar de modo.
          El estado inicial es Call (edición bloqueada), que coincide con
          BtnCall.isChecked() = True por defecto en _build_preset_mode().
        """
        self._names_panel = NamesPanel(
            self._names_list,
            self._on_names_list_changed,
            parent=self,
        )
        self._names_panel.hide()

        # Sincronizar asignaciones iniciales: _restore_seat_names() ya aplicó
        # los nombres guardados a los GoButtons; aquí actualizamos el panel
        # para que oculte esos nombres de la lista desde el primer arranque.
        self._sync_panel_assigned()

        # Edición bloqueada en Call (modo por defecto) y habilitada en Set.
        # BtnNames siempre visible: el operador puede abrir el panel en cualquier
        # modo para ver los nombres disponibles, aunque no pueda modificar la lista.
        self.BtnCall.clicked.connect(lambda: self._names_panel.set_edit_mode(False))
        self.BtnSet.clicked.connect(lambda:  self._names_panel.set_edit_mode(True))

    def _restore_seat_names(self):
        """
        Aplica los nombres guardados en self._seat_names a los GoButtons
        justo después de construir la UI.

        emit_signal=False: evita llamar a _on_seat_name_assigned durante
        la carga inicial, lo que dispararía save_names_data innecesariamente
        (los datos ya están en el archivo y no han cambiado).
        """
        for seat_str, name in self._seat_names.items():
            btn = getattr(self, f"Seat{seat_str}", None)
            if isinstance(btn, GoButton) and name:
                btn.set_name(name, emit_signal=False)

    def _assigned_names(self) -> set:
        """
        Devuelve el conjunto de nombres actualmente asignados a algún asiento.
        Fuente única de verdad: evita calcular set(self._seat_names.values())
        en varios sitios con riesgo de inconsistencia.
        """
        return set(self._seat_names.values())

    def _sync_panel_assigned(self):
        """
        Notifica a NamesPanel el conjunto actual de nombres asignados.
        Llamar tras cualquier cambio en self._seat_names para mantener
        la vista del panel sincronizada (quitar/añadir nombres de la lista).
        """
        self._names_panel.set_assigned(self._assigned_names())

    def _toggle_names_panel(self, checked: bool):
        """
        Muestra u oculta el NamesPanel al pulsar BtnNames.
        raise_() trae el panel al frente; luego BtnNames.raise_() lo mantiene
        encima del panel para que el botón siempre sea visible y pulsable.
        """
        if checked:
            self._names_panel.raise_()
            self._names_panel.show()
            self.BtnNames.raise_()  # botón siempre encima del panel
        else:
            self._names_panel.hide()

    def _on_seat_name_assigned(self, seat_number: int, name: str):
        """
        Slot conectado a GoButton.name_assigned.
        Se llama cada vez que el usuario arrastra un nombre a un asiento
        o borra la asignación con doble-tap.

        Actualiza self._seat_names en memoria y persiste en seat_names.json.
        Usar str(seat_number) como clave para consistencia con el JSON
        (JSON solo admite strings como claves de objeto).
        """
        key = str(seat_number)

        # Si el asiento ya tenía un nombre asignado y se está sobreescribiendo,
        # el nombre anterior vuelve a estar disponible en la lista del panel.
        # _sync_panel_assigned() lo refleja automáticamente al recalcular el set.
        if name:
            self._seat_names[key] = name
        else:
            self._seat_names.pop(key, None)  # pop silencioso si no existía

        save_names_data(self._names_list, self._seat_names)
        self._sync_panel_assigned()  # actualizar panel: quitar o devolver nombre

    def _on_names_list_changed(self, old_name: str = None, new_name: str = None):
        """
        Callback de NamesPanel tras añadir / editar / borrar un nombre de la lista.

        Si es un renombrado (old_name y new_name no son None):
          - Actualiza self._seat_names con el nombre nuevo.
          - Llama a GoButton.set_name() con emit_signal=False en los asientos
            afectados para no disparar un guardado extra (ya guardamos aquí).

        Si no hay renombrado (solo añadir/borrar):
          - Solo persiste la lista actualizada.
        """
        if old_name and new_name:
            for key, v in self._seat_names.items():
                if v == old_name:
                    self._seat_names[key] = new_name
                    # Actualizar visualmente el botón sin emitir señal (evita doble guardado)
                    btn = getattr(self, f"Seat{key}", None)
                    if isinstance(btn, GoButton):
                        btn.set_name(new_name, emit_signal=False)
        save_names_data(self._names_list, self._seat_names)
        # Resincronizar panel: un renombrado cambia qué nombre aparece como asignado.
        self._sync_panel_assigned()

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