#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# dialogs_mixin.py — Mixin de diálogos de configuración y ayuda
#
# Responsabilidad única: gestionar todos los diálogos modales de la app:
# cambio de IP, cambio de VISCA ID, ayuda y cierre.
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - REDUNDANCIA ELIMINADA: _change_ip() y _change_cam_id() compartían
#     un 80% de código idéntico (confirmación, input, validación, escritura,
#     reinicio). Se han fusionado en _change_config(cam_num, config_type).
#
#     Flujo compartido:
#       1. Determinar nombre, valor actual y archivo según cam_num + config_type.
#       2. Pedir confirmación.
#       3. Pedir nuevo valor (QInputDialog).
#       4. Validar (is_valid_ip o is_valid_cam_id).
#       5. Escribir al archivo .txt y reiniciar con os.execv.
#
#     Los wrappers públicos PTZ1Address(), PTZ2Address(), etc. siguen existiendo
#     para no cambiar las conexiones de señal en main_window.py.

import os
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMessageBox, QInputDialog,
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton,
)

from config import (
    CAM1, CAM2, Contact,
    is_valid_ip, is_valid_cam_id,
)
from secret_manager import decrypt_password as _get_password, encrypt_password as _save_password


class ChangePasswordDialog(QDialog):
    """Diálogo modal para cambiar la contraseña de acceso."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Change Password')
        self.setWindowModality(Qt.WindowModal)
        self.setFixedSize(340, 230)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.new_password = ''
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel('🔒  Change Password')
        title.setStyleSheet("font: bold 15px; color: #222;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Campos de contraseña
        form = QFormLayout()
        form.setSpacing(8)

        self._cur = QLineEdit()
        self._cur.setEchoMode(QLineEdit.Password)
        self._cur.setPlaceholderText('Current password')

        self._new = QLineEdit()
        self._new.setEchoMode(QLineEdit.Password)
        self._new.setPlaceholderText('New password')

        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.Password)
        self._confirm.setPlaceholderText('Repeat new password')

        field_style = (
            "QLineEdit { border: 1px solid #bbb; border-radius: 4px;"
            " padding: 4px 6px; font: 13px; }"
            "QLineEdit:focus { border-color: #1976D2; }"
        )
        for w in (self._cur, self._new, self._confirm):
            w.setStyleSheet(field_style)

        form.addRow('Current:', self._cur)
        form.addRow('New:', self._new)
        form.addRow('Confirm:', self._confirm)
        layout.addLayout(form)

        # Etiqueta de error inline
        self._err = QLabel('')
        self._err.setStyleSheet("color: #c62828; font: 12px;")
        self._err.setAlignment(Qt.AlignCenter)
        self._err.setWordWrap(True)
        layout.addWidget(self._err)

        # Botones OK / Cancel
        btn_row = QHBoxLayout()
        btn_ok = QPushButton('OK')
        btn_ok.setFixedHeight(32)
        btn_ok.setStyleSheet(
            "QPushButton { background: #1976D2; border: none; border-radius: 5px;"
            " font: bold 12px; color: white; }"
            "QPushButton:pressed { background: #1251a0; }"
        )
        btn_ok.clicked.connect(self._validate)

        btn_cancel = QPushButton('Cancel')
        btn_cancel.setFixedHeight(32)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #e0e0e0; border: none; border-radius: 5px;"
            " font: 12px; color: #333; }"
            "QPushButton:pressed { background: #bdbdbd; }"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.setStyleSheet(
            "ChangePasswordDialog {"
            "  background: white;"
            "  border: 2px solid #9e9e9e;"
            "  border-radius: 10px;"
            "}"
        )

    def _validate(self):
        cur = self._cur.text()
        new = self._new.text()
        confirm = self._confirm.text()

        if not cur or not new or not confirm:
            self._err.setText('All fields are required.')
            return
        if cur != _get_password():
            self._err.setText('Current password is incorrect.')
            self._cur.clear()
            self._cur.setFocus()
            return
        if new != confirm:
            self._err.setText('New passwords do not match.')
            self._new.clear()
            self._confirm.clear()
            self._new.setFocus()
            return

        self.new_password = new
        self.accept()


class DialogsController:

    def __init__(self, window):
        self._w = window

    def _change_config(self, cam_num: int, config_type: str):
        """
        Diálogo genérico para cambiar IP o VISCA ID de una cámara.

        Parámetros:
          cam_num:     1 (Platform) o 2 (Comments).
          config_type: 'ip' o 'id'.

        MOTIVO DE UNIFICACIÓN:
        _change_ip() y _change_cam_id() eran prácticamente idénticos:
        misma estructura de confirmación → input → validación → escritura → reinicio.
        La única diferencia era qué constante leer, qué archivo escribir
        y qué función de validación llamar. Con un solo método parametrizado,
        cualquier cambio en el flujo (p.ej. el mensaje de confirmación) solo
        se hace en un sitio.

        MOTIVO DEL REINICIO (os.execv):
        Las IPs e IDs se cargan al importar config.py (ejecución a nivel de módulo).
        Recargarlas en caliente requeriría reimportar el módulo y redistribuir
        las referencias, lo que es complejo y propenso a errores de estado.
        Un reinicio limpio garantiza que todo el estado arranca desde cero.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'

        # Determinar qué campo cambiar según config_type
        if config_type == 'ip':
            current  = CAM1.ip  if cam_num == 1 else CAM2.ip
            filename = 'PTZ1IP.txt' if cam_num == 1 else 'PTZ2IP.txt'
            field    = 'IP address'
            validate = is_valid_ip
            hint     = 'four numbers separated by dots (e.g. 172.16.1.11)'
            label    = 'IP Address'
        else:  # 'id'
            current  = CAM1.cam_id if cam_num == 1 else CAM2.cam_id
            filename = 'Cam1ID.txt' if cam_num == 1 else 'Cam2ID.txt'
            field    = 'VISCA ID'
            validate = is_valid_cam_id
            hint     = 'a hex value such as "81" or "82"'
            label    = 'Camera ID'

        title = f'{cam_name} PTZ Control'

        # Paso 1: confirmación — evitar cambios accidentales
        if QMessageBox.warning(
            self._w, title,
            f'Do you want to change the {field} used to control the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        ) != QMessageBox.Ok:
            return

        # Paso 2: pedir nuevo valor
        dlg = QInputDialog(self._w)
        dlg.setWindowTitle(title)
        dlg.setLabelText(f'New {field} for {cam_name} Camera (current: {current}):')
        dlg.setTextValue(current)
        dlg.setWindowModality(Qt.WindowModal)
        ok = dlg.exec_() == QDialog.Accepted
        text = dlg.textValue()
        if not (ok and text.strip()):
            return  # Usuario canceló o dejó vacío

        text = text.strip()

        # Paso 3: validar
        if not validate(text):
            QMessageBox.warning(
                self._w, f'Invalid {label}',
                f'"{text}" is not a valid {field}.\nPlease enter {hint}.'
            )
            return

        # Paso 4: guardar y reiniciar
        with open(filename, 'w') as f:
            f.write(text)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Wrappers públicos ─────────────────────────────────────────────────
    # Conectados a los botones en main_window.py — no cambian la interfaz pública.

    def PTZ1Address(self):  self._change_config(1, 'ip')
    def PTZ2Address(self):  self._change_config(2, 'ip')
    def PTZ1IDchange(self): self._change_config(1, 'id')
    def PTZ2IDchange(self): self._change_config(2, 'id')

    def ChangePassword(self):
        """Diálogo para cambiar la contraseña de acceso."""
        dlg = ChangePasswordDialog(self._w)
        if dlg.exec_() == QDialog.Accepted:
            _save_password(dlg.new_password)
            QMessageBox.information(
                self._w, 'Password Changed',
                'Password updated successfully.\n'
                'The new password will be required on next login.',
                QMessageBox.Ok,
            )

    def HelpMsg(self):
        """Muestra el mensaje de contacto de soporte técnico."""
        QMessageBox.information(self._w, 'For Technical Assistance', Contact, QMessageBox.Ok)