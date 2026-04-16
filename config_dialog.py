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
#     (CAM1.check / CAM2.check): verde = responde, rojo = no responde.
#
# USO EN main_window.py:
#   from config_dialog import ConfigDialog
#   dlg = ConfigDialog(self)
#   dlg.exec_()   # modal — bloquea hasta que se cierre

import os
import sys
import socket
import threading

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QScrollArea, QWidget,
)

from schedule_dialog import ScheduleDialog
import sim_mode as _sim_mode

from config import CAM1, CAM2, ATEMAddress


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
        self.setFixedSize(400, 940)
        # Sin barra de título del SO en pantalla táctil (RPi fullscreen)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self._build_ui(parent)

    def _build_ui(self, mw):
        """
        Construye el contenido del diálogo.
        mw — referencia a MainWindow para conectar los callbacks existentes.
        """
        # Calculado una vez aquí y reutilizado en todas las secciones
        sim_active = _sim_mode.is_active()

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
        btn_session.clicked.connect(lambda: (mw._session.ToggleSession(), self.accept()))
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
        btn_ip1 = QPushButton('Platform  ' + CAM1.ip)
        btn_ip1.setStyleSheet(self._cam_btn_style(CAM1.check, align_left=True))
        btn_ip1.setToolTip('Change Platform camera IP address')
        btn_ip1.clicked.connect(lambda: (mw._dialogs.PTZ1Address(), self._try_close()))
        row1.addWidget(btn_ip1)

        # Botón ID: más pequeño, a la derecha
        btn_id1 = QPushButton('ID  ' + CAM1.cam_id)
        btn_id1.setFixedWidth(80)
        btn_id1.setStyleSheet(self._cam_btn_style(CAM1.check))
        btn_id1.setToolTip('Change Platform camera VISCA ID')
        btn_id1.clicked.connect(lambda: (mw._dialogs.PTZ1IDchange(), self._try_close()))
        row1.addWidget(btn_id1)
        layout.addLayout(row1)

        # ── Sección: Comments camera ──────────────────────────────────────
        layout.addWidget(self._section_label('Comments Camera'))

        row2 = QHBoxLayout()
        btn_ip2 = QPushButton('Comments  ' + CAM2.ip)
        btn_ip2.setStyleSheet(self._cam_btn_style(CAM2.check, align_left=True))
        btn_ip2.setToolTip('Change Comments camera IP address')
        btn_ip2.clicked.connect(lambda: (mw._dialogs.PTZ2Address(), self._try_close()))
        row2.addWidget(btn_ip2)

        btn_id2 = QPushButton('ID  ' + CAM2.cam_id)
        btn_id2.setFixedWidth(80)
        btn_id2.setStyleSheet(self._cam_btn_style(CAM2.check))
        btn_id2.setToolTip('Change Comments camera VISCA ID')
        btn_id2.clicked.connect(lambda: (mw._dialogs.PTZ2IDchange(), self._try_close()))
        row2.addWidget(btn_id2)
        layout.addLayout(row2)

        # ── Sección: Camera Discovery ─────────────────────────────────────
        layout.addWidget(self._section_label('Camera Discovery'))

        # Etiqueta de estado del escaneo
        disc_status = QLabel('Press Scan to detect cameras on the network.')
        disc_status.setStyleSheet(
            "font: 11px 'Segoe UI'; color: #666; padding: 2px 0;"
        )
        disc_status.setWordWrap(True)
        layout.addWidget(disc_status)

        # Contenedor con scroll para los resultados (máx 110 px visible)
        disc_inner = QWidget()
        disc_inner.setStyleSheet("background: transparent;")
        disc_layout = QVBoxLayout(disc_inner)
        disc_layout.setContentsMargins(0, 0, 0, 0)
        disc_layout.setSpacing(4)

        disc_scroll = QScrollArea()
        disc_scroll.setWidgetResizable(True)
        disc_scroll.setFixedHeight(0)   # oculto hasta que haya resultados
        disc_scroll.setFrameShape(QFrame.NoFrame)
        disc_scroll.setStyleSheet("background: transparent;")
        disc_scroll.setWidget(disc_inner)
        layout.addWidget(disc_scroll)

        btn_scan = QPushButton('🔍  Scan Network')
        btn_scan.setFixedHeight(34)
        btn_scan.setStyleSheet(
            "QPushButton { background: #1565C0; border: none; border-radius: 6px;"
            " font: 13px; color: white; }"
            "QPushButton:pressed { background: #0D47A1; }"
            "QPushButton:disabled { background: #90A4AE; }"
        )
        layout.addWidget(btn_scan)

        # ── Helpers de asignación ─────────────────────────────────────────

        def _apply_ip(ip: str, cam_num: int):
            """Guarda la IP en el fichero correspondiente y reinicia la app."""
            filename = 'PTZ1IP.txt' if cam_num == 1 else 'PTZ2IP.txt'
            with open(filename, 'w') as fh:
                fh.write(ip)
            os.execv(sys.executable, [sys.executable] + sys.argv)

        def _clear_results():
            while disc_layout.count():
                child = disc_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        def _show_results(found: list):
            _clear_results()
            if not found:
                disc_status.setText('No VISCA devices found on the network.')
                disc_scroll.setFixedHeight(0)
            else:
                disc_status.setText(f'{len(found)} device(s) found:')
                for ip in found:
                    row_w = QWidget()
                    row_w.setStyleSheet("background: #f5f5f5; border-radius: 4px;")
                    row_h = QHBoxLayout(row_w)
                    row_h.setContentsMargins(6, 2, 6, 2)
                    row_h.setSpacing(6)

                    lbl = QLabel(ip)
                    lbl.setStyleSheet("font: bold 12px; color: #222; background: transparent;")
                    row_h.addWidget(lbl)
                    row_h.addStretch()

                    btn_p = QPushButton('→ Platform')
                    btn_p.setFixedHeight(24)
                    btn_p.setFixedWidth(86)
                    btn_p.setStyleSheet(
                        "QPushButton { background: #2e7d32; border: none; border-radius: 4px;"
                        " font: 11px; color: white; }"
                        "QPushButton:pressed { background: #1b5e20; }"
                    )
                    btn_p.clicked.connect(lambda _=False, _ip=ip: _apply_ip(_ip, 1))
                    row_h.addWidget(btn_p)

                    btn_c = QPushButton('→ Comments')
                    btn_c.setFixedHeight(24)
                    btn_c.setFixedWidth(86)
                    btn_c.setStyleSheet(
                        "QPushButton { background: #c62828; border: none; border-radius: 4px;"
                        " font: 11px; color: white; }"
                        "QPushButton:pressed { background: #8b1a1a; }"
                    )
                    btn_c.clicked.connect(lambda _=False, _ip=ip: _apply_ip(_ip, 2))
                    row_h.addWidget(btn_c)

                    disc_layout.addWidget(row_w)

                # Altura: máx 4 filas × 32 px
                disc_scroll.setFixedHeight(min(len(found), 4) * 32)

            btn_scan.setEnabled(True)
            btn_scan.setText('🔍  Scan Network')

        def _run_scan():
            from camera_discovery import discover_cameras
            found = discover_cameras()
            QTimer.singleShot(0, lambda: _show_results(found))

        def _on_scan_clicked():
            _clear_results()
            disc_scroll.setFixedHeight(0)
            disc_status.setText('Scanning…')
            btn_scan.setEnabled(False)
            btn_scan.setText('Scanning…')
            threading.Thread(target=_run_scan, daemon=True).start()

        btn_scan.clicked.connect(_on_scan_clicked)

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
        btn_pwd.clicked.connect(lambda: (mw._dialogs.ChangePassword(), self._try_close()))
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

        # ── Sección: Simulation Mode ──────────────────────────────────────
        layout.addWidget(self._section_label('Simulation Mode'))
        self._build_sim_section(layout, mw, sim_active)

        line_sim = QFrame()
        line_sim.setFrameShape(QFrame.HLine)
        line_sim.setStyleSheet("color: #ccc;")
        layout.addWidget(line_sim)

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
        btn_help.clicked.connect(mw._dialogs.HelpMsg)
        bottom.addWidget(btn_help)

        layout.addLayout(bottom)

        # ── Sección: Test Focus & Exposure ────────────────────────────────
        line5 = QFrame()
        line5.setFrameShape(QFrame.HLine)
        line5.setStyleSheet("color: #ccc;")
        layout.addWidget(line5)

        layout.addWidget(self._section_label('Focus & Exposure Test'))

        # 7 indicadores: ● con etiqueta debajo
        test_indicators = []
        ind_row = QHBoxLayout()
        ind_row.setSpacing(2)
        for label_text in ['AF', '1PAF', 'MF', 'Dark', 'Bright', 'BL', 'ATEM']:
            dot = QLabel('●')
            dot.setAlignment(Qt.AlignCenter)
            dot.setFixedHeight(16)
            dot.setStyleSheet("color: #AAAAAA; font: 14px;")
            test_indicators.append(dot)

            cap = QLabel(label_text)
            cap.setAlignment(Qt.AlignCenter)
            cap.setStyleSheet("font: 9px 'Segoe UI'; color: #888;")
            cap.setFixedHeight(12)

            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(dot)
            col.addWidget(cap)
            ind_row.addLayout(col)

        layout.addLayout(ind_row)

        btn_run_test = QPushButton('▶  Run Test')
        btn_run_test.setFixedHeight(28)
        btn_run_test.setStyleSheet(
            "QPushButton { background: #546E7A; border: none; border-radius: 6px;"
            " font: 12px 'Segoe UI'; color: white; }"
            "QPushButton:pressed { background: #37474F; }"
            "QPushButton:disabled { background: #90A4AE; }"
        )
        layout.addWidget(btn_run_test)

        def _test_atem_connection():
            if sim_active:
                import hardware_simulator as _hw
                _hw.atem_event_queue.put("switch_to_input2")
                color = '#3d9e3d'
            else:
                try:
                    with socket.create_connection((ATEMAddress, 9910), timeout=3):
                        ok = True
                except OSError as exc:
                    import logging as _log
                    _log.getLogger(__name__).warning("ATEM test failed: %s", exc)
                    ok = False
                color = '#3d9e3d' if ok else '#b33030'
            test_indicators[6].setStyleSheet(f"color: {color}; font: 14px;")
            btn_run_test.setEnabled(True)
            btn_run_test.setText('▶  Run Test')

        def _on_test_clicked():
            for dot in test_indicators:
                dot.setStyleSheet("color: #AAAAAA; font: 14px;")
            btn_run_test.setEnabled(False)
            btn_run_test.setText('Testing...')
            commands = [
                ("01043802FF", 0),   # Auto Focus
                ("01041801FF", 1),   # One Push AF
                ("01043803FF", 2),   # Manual Focus
                ("01040D03FF", 3),   # Darker
                ("01040D02FF", 4),   # Brighter
                ("01043302FF", 5),   # Backlight ON
            ]

            def _after_visca():
                threading.Thread(target=_test_atem_connection, daemon=True).start()

            def _run_with_atem(step):
                if step >= len(commands):
                    QTimer.singleShot(100, _after_visca)
                    return
                cmd, idx = commands[step]
                ip, cam_id = mw._visca._active_cam()
                ok = mw._visca._send_cmd(ip, cam_id, cmd)
                color = '#3d9e3d' if ok else '#b33030'
                test_indicators[idx].setStyleSheet(f"color: {color}; font: 14px;")
                QTimer.singleShot(500, lambda: _run_with_atem(step + 1))

            QTimer.singleShot(100, lambda: _run_with_atem(0))

        btn_run_test.clicked.connect(_on_test_clicked)

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

    def _build_sim_section(self, layout, mw, sim_active: bool):
        """Sección de modo simulación: toggle ON/OFF."""

        status_text  = "ACTIVE — cameras simulated locally" if sim_active else "INACTIVE — using real hardware"
        status_color = "#1a7a1a" if sim_active else "#555"
        status_bg    = "#e8f5e9" if sim_active else "#f5f5f5"
        lbl_status = QLabel(status_text)
        lbl_status.setAlignment(Qt.AlignCenter)
        lbl_status.setStyleSheet(
            f"font: bold 11px; color: {status_color};"
            f" background: {status_bg}; border-radius: 5px; padding: 5px;"
        )
        layout.addWidget(lbl_status)

        if sim_active:
            btn_toggle = QPushButton("Disable Simulation Mode")
            btn_toggle.setStyleSheet(
                "QPushButton { background: #c62828; border: none; border-radius: 6px;"
                " font: bold 13px; color: white; }"
                "QPushButton:pressed { background: #8b1a1a; }"
            )
        else:
            btn_toggle = QPushButton("Enable Simulation Mode")
            btn_toggle.setStyleSheet(
                "QPushButton { background: #1565C0; border: none; border-radius: 6px;"
                " font: bold 13px; color: white; }"
                "QPushButton:pressed { background: #0D47A1; }"
            )
        btn_toggle.setFixedHeight(38)

        def _toggle_sim():
            try:
                if _sim_mode.is_active():
                    _sim_mode.deactivate()
                else:
                    _sim_mode.activate()
            except RuntimeError as exc:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(None, "Simulation Mode",
                                    str(exc) or "Unknown error toggling simulation mode.")
                return
            os.execv(sys.executable, [sys.executable] + sys.argv)

        btn_toggle.clicked.connect(_toggle_sim)
        layout.addWidget(btn_toggle)


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
