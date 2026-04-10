#!/usr/bin/env python3
# config_dialog.py — Diálogo modal de configuración técnica
#
# Responsabilidad única: mostrar en un diálogo modal todos los controles
# técnicos que antes estaban siempre visibles en el panel derecho:
#   - IP y VISCA ID de cámara Platform
#   - IP y VISCA ID de cámara Comments
#   - Label de versión
#   - Botón de ayuda (contacto soporte)
#
# MOTIVO DE EXTRACCIÓN:
#   Estos controles los usa el técnico/administrador, no el operador de cámara.
#   Esconderlos bajo un engranaje ⚙ reduce el ruido visual del panel derecho
#   y evita cambios accidentales de IP durante una sesión en directo.
#
# DISEÑO DEL DIÁLOGO:
#   - QDialog modal (bloquea la ventana principal mientras está abierto)
#   - No tiene botón OK/Cancel: cada acción (cambiar IP, cambiar ID) se
#     ejecuta directamente con su botón propio, igual que antes.
#   - Se cierra con el botón "Close" del diálogo o con Escape.
#   - Los colores de los labels de IP/ID reflejan el estado de conectividad
#     (Cam1Check / Cam2Check): verde = responde, rojo = no responde.
#
# USO EN main_window.py:
#   from config_dialog import ConfigDialog
#   dlg = ConfigDialog(self)
#   dlg.exec_()   # modal — bloquea hasta que se cierre

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame,
)

from schedule_dialog import ScheduleDialog

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID,
    Cam1Check, Cam2Check,
)


class ConfigDialog(QDialog):
    """
    Diálogo modal de configuración técnica de cámaras.

    Recibe la MainWindow como parent para heredar posición y para poder
    llamar a sus métodos PTZ1Address, PTZ2Address, PTZ1IDchange,
    PTZ2IDchange y HelpMsg directamente — los mismos callbacks que antes
    conectaban los botones del panel derecho.
    MOTIVO: no duplicar lógica; el diálogo es solo una nueva superficie
    de acceso a los mismos métodos ya existentes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Camera Configuration')
        # Modal: bloquea la ventana principal mientras está abierto.
        # Evita que el operador mueva cámaras mientras el técnico cambia IPs.
        self.setModal(True)
        self.setFixedSize(400, 580)
        # Sin barra de título del SO en pantalla táctil (RPi fullscreen)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self._build_ui(parent)

    def _build_ui(self, mw):
        """
        Construye el contenido del diálogo.
        mw — referencia a MainWindow para conectar los callbacks existentes.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Título ────────────────────────────────────────────────────────
        title = QLabel('⚙  Camera Configuration')
        title.setStyleSheet("font: bold 16px; color: #222;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Separador visual
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ccc;")
        layout.addWidget(line)

        # ── Sección: Session ON / OFF ─────────────────────────────────────
        layout.addWidget(self._section_label('Session'))

        is_on   = getattr(mw, 'session_active', False)
        clr_on  = '#1a7a1a'
        clr_off = '#8b1a1a'
        status_color = clr_on if is_on else clr_off
        status_text  = '⏻  ON — Session running'  if is_on else '⏻  OFF — Standby'
        btn_text     = 'End Session'               if is_on else 'Start Session'
        btn_bg       = clr_on                      if is_on else clr_off
        btn_pressed  = '#0d4d0d'                   if is_on else '#5a0d0d'

        session_status = QLabel(status_text)
        session_status.setAlignment(Qt.AlignCenter)
        session_status.setStyleSheet(
            f"font: bold 14px; color: {status_color};"
            " background: #f5f5f5; border-radius: 6px; padding: 6px;"
        )
        layout.addWidget(session_status)

        btn_session = QPushButton(btn_text)
        btn_session.setFixedHeight(40)
        btn_session.setStyleSheet(
            f"QPushButton {{ background: {btn_bg}; border: none; border-radius: 6px;"
            f" font: bold 14px; color: white; }}"
            f"QPushButton:pressed {{ background: {btn_pressed}; }}"
        )
        btn_session.clicked.connect(lambda: (mw.ToggleSession(), self.accept()))
        layout.addWidget(btn_session)

        # Separador
        line_s = QFrame()
        line_s.setFrameShape(QFrame.HLine)
        line_s.setStyleSheet("color: #ccc;")
        layout.addWidget(line_s)

        # ── Sección: Platform camera ──────────────────────────────────────
        layout.addWidget(self._section_label('Platform Camera'))

        row1 = QHBoxLayout()
        # Botón IP: muestra la IP actual, color según conectividad
        btn_ip1 = QPushButton('Platform  ' + IPAddress)
        btn_ip1.setStyleSheet(self._cam_btn_style(Cam1Check, align_left=True))
        btn_ip1.setToolTip('Change Platform camera IP address')
        btn_ip1.clicked.connect(lambda: (mw.PTZ1Address(), self._try_close()))
        row1.addWidget(btn_ip1)

        # Botón ID: más pequeño, a la derecha
        btn_id1 = QPushButton('ID  ' + Cam1ID)
        btn_id1.setFixedWidth(80)
        btn_id1.setStyleSheet(self._cam_btn_style(Cam1Check))
        btn_id1.setToolTip('Change Platform camera VISCA ID')
        btn_id1.clicked.connect(lambda: (mw.PTZ1IDchange(), self._try_close()))
        row1.addWidget(btn_id1)
        layout.addLayout(row1)

        # ── Sección: Comments camera ──────────────────────────────────────
        layout.addWidget(self._section_label('Comments Camera'))

        row2 = QHBoxLayout()
        btn_ip2 = QPushButton('Comments  ' + IPAddress2)
        btn_ip2.setStyleSheet(self._cam_btn_style(Cam2Check, align_left=True))
        btn_ip2.setToolTip('Change Comments camera IP address')
        btn_ip2.clicked.connect(lambda: (mw.PTZ2Address(), self._try_close()))
        row2.addWidget(btn_ip2)

        btn_id2 = QPushButton('ID  ' + Cam2ID)
        btn_id2.setFixedWidth(80)
        btn_id2.setStyleSheet(self._cam_btn_style(Cam2Check))
        btn_id2.setToolTip('Change Comments camera VISCA ID')
        btn_id2.clicked.connect(lambda: (mw.PTZ2IDchange(), self._try_close()))
        row2.addWidget(btn_id2)
        layout.addLayout(row2)

        # Separador
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #ccc;")
        layout.addWidget(line2)

        # ── Sección: Contraseña ───────────────────────────────────────────
        layout.addWidget(self._section_label('Access'))

        btn_pwd = QPushButton('🔒  Change Password')
        btn_pwd.setFixedHeight(36)
        btn_pwd.setStyleSheet(
            "QPushButton { background: #546E7A; border: none; border-radius: 6px;"
            " font: 13px; color: white; }"
            "QPushButton:pressed { background: #37474F; }"
        )
        btn_pwd.setToolTip('Change the login password')
        btn_pwd.clicked.connect(lambda: (mw.ChangePassword(), self._try_close()))
        layout.addWidget(btn_pwd)

        # Separador
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setStyleSheet("color: #ccc;")
        layout.addWidget(line3)

        # ── Sección: Schedule ─────────────────────────────────────────────
        layout.addWidget(self._section_label('Schedule'))

        btn_schedule = QPushButton('📅  Weekly Schedule')
        btn_schedule.setFixedHeight(36)
        btn_schedule.setStyleSheet(
            "QPushButton { background: #1565C0; border: none; border-radius: 6px;"
            " font: 13px; color: white; }"
            "QPushButton:pressed { background: #0D47A1; }"
        )
        btn_schedule.setToolTip('Configure days and hours when no password is required')
        btn_schedule.clicked.connect(lambda: ScheduleDialog(self).exec_())
        layout.addWidget(btn_schedule)

        # Separador
        line4 = QFrame()
        line4.setFrameShape(QFrame.HLine)
        line4.setStyleSheet("color: #ccc;")
        layout.addWidget(line4)

        # ── Versión y ayuda ───────────────────────────────────────────────
        bottom = QHBoxLayout()

        version = QLabel('v3 — IP RPI — March 2026')
        version.setStyleSheet("font: 11px; color: #888;")
        bottom.addWidget(version)

        bottom.addStretch()

        btn_help = QPushButton('? Help')
        btn_help.setFixedWidth(70)
        btn_help.setStyleSheet(
            "QPushButton { background: #f5f5f5; border: 1px solid #bbb;"
            " border-radius: 4px; font: 12px; color: #333; }"
            "QPushButton:pressed { background: #e0e0e0; }"
        )
        btn_help.clicked.connect(mw.HelpMsg)
        bottom.addWidget(btn_help)

        layout.addLayout(bottom)

        # ── Botón cerrar ──────────────────────────────────────────────────
        # Siempre al final y centrado — el único modo de salir en táctil
        # (no hay barra de título con X por FramelessWindowHint).
        btn_close = QPushButton('Close')
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet(
            "QPushButton { background: #424242; border: none; border-radius: 6px;"
            " font: bold 13px; color: white; }"
            "QPushButton:pressed { background: #212121; }"
        )
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        # Estilo del diálogo: fondo blanco, borde sutil, sombra si el SO lo soporta
        self.setStyleSheet(
            "ConfigDialog {"
            "  background: white;"
            "  border: 2px solid #9e9e9e;"
            "  border-radius: 10px;"
            "}"
        )

    # ── Helpers de estilo ─────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        """Etiqueta de sección con estilo consistente."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font: bold 12px; color: #555; padding-top: 4px;")
        return lbl

    def _cam_btn_style(self, check_color: str, *, align_left: bool = False) -> str:
        """
        Estilo unificado para botones IP e ID.
        check_color: 'Green' → texto verde, otro valor → texto rojo.
        align_left=True añade text-align: left; padding-left: 8px (botones IP).
        """
        text_color = '#2e7d32' if check_color == 'Green' else '#c62828'
        align = " text-align: left; padding-left: 8px;" if align_left else ""
        return (
            f"QPushButton {{ background: #fafafa; border: 1px solid #ccc;"
            f" border-radius: 4px; font: bold 12px; color: {text_color};{align} }}"
            f"QPushButton:pressed {{ background: #eeeeee; }}"
        )

    def _try_close(self):
        """
        Cierra el diálogo después de que el usuario confirma un cambio de IP/ID.
        PTZ1Address y PTZ2Address hacen os.execv para reiniciar la app,
        así que este close solo aplica si el usuario cancela el diálogo de cambio.
        MOTIVO: si el usuario cancela el cambio de IP, el diálogo de config
        queda abierto en lugar de cerrarse automáticamente — comportamiento
        más consistente que dejarlo abierto.
        """
        self.accept()
