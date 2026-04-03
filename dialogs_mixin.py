#!/usr/bin/env python3
# dialogs_mixin.py — Mixin de diálogos de configuración y ayuda
#
# Responsabilidad única: gestionar todos los diálogos modales de la app:
# cambio de IP, cambio de VISCA ID, ayuda y cierre.
#
# MOTIVO DE SEPARACIÓN: estos métodos son largos (validación, escritura
# a disco, reinicio) y no tienen relación con el layout ni con VISCA.
# Separarlos hace main_window.py más corto y estos métodos más fáciles
# de modificar y testear de forma aislada.

import os
import sys

from PyQt5.QtWidgets import QMessageBox, QInputDialog

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID, Contact,
    is_valid_ip, is_valid_cam_id
)


class DialogsMixin:

    # ─────────────────────────────────────────────────────────────────────────
    #  Cambio de IP
    # ─────────────────────────────────────────────────────────────────────────

    def _change_ip(self, cam_num: int):
        """
        Muestra un diálogo para cambiar la IP de la cámara indicada (1 o 2).
        Si el usuario confirma y la IP es válida:
          1. Escribe la nueva IP en el archivo de configuración (.txt).
          2. Reinicia la app con os.execv para recargar la configuración.

        MOTIVO del reinicio: la IP se carga al importar config.py.
        Recargarla en caliente requeriría reimportar el módulo, lo que es
        complejo y propenso a errores.  Un reinicio limpio es más seguro.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        current  = IPAddress  if cam_num == 1 else IPAddress2
        filename = 'PTZ1IP.txt' if cam_num == 1 else 'PTZ2IP.txt'
        title    = f'{cam_name} PTZ Control'

        # Confirmación previa para evitar cambios accidentales
        if QMessageBox.warning(
            self, title,
            f'Do you want to change the IP address used to control the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        ) != QMessageBox.Ok:
            return

        text, ok = QInputDialog.getText(
            self, title,
            f'New IP address for {cam_name} Camera  (current: {current}):',
            text=current
        )

        if not (ok and text):
            return  # Usuario canceló o dejó vacío

        if not is_valid_ip(text):
            QMessageBox.warning(
                self, 'Invalid IP Address',
                f'"{text}" is not a valid IPv4 address.\n'
                'Please enter four numbers separated by dots (e.g. 172.16.1.11).'
            )
            return

        # Guardar y reiniciar
        with open(filename, "w") as f:
            f.write(text.strip())
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ─────────────────────────────────────────────────────────────────────────
    #  Cambio de VISCA ID
    # ─────────────────────────────────────────────────────────────────────────

    def _change_cam_id(self, cam_num: int):
        """
        Muestra un diálogo para cambiar el ID VISCA hex de la cámara indicada.
        Valida que sea un valor hexadecimal válido antes de guardar.
        Reinicia la app igual que _change_ip.
        """
        cam_name = 'Platform' if cam_num == 1 else 'Comments'
        current  = Cam1ID  if cam_num == 1 else Cam2ID
        filename = 'Cam1ID.txt' if cam_num == 1 else 'Cam2ID.txt'
        title    = f'{cam_name} PTZ Control'

        if QMessageBox.warning(
            self, title,
            f'Do you want to change the VISCA ID used to control the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        ) != QMessageBox.Ok:
            return

        text, ok = QInputDialog.getText(
            self, title,
            f'New VISCA ID for {cam_name} Camera  (current: {current}):',
            text=current
        )

        if not (ok and text):
            return

        if not is_valid_cam_id(text):
            QMessageBox.warning(
                self, 'Invalid Camera ID',
                f'"{text}" is not a valid hexadecimal ID.\n'
                'Please enter a hex value such as "81" or "82".'
            )
            return

        with open(filename, "w") as f:
            f.write(text.strip())
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ─────────────────────────────────────────────────────────────────────────
    #  Wrappers públicos (conectados a los botones en main_window.py)
    # ─────────────────────────────────────────────────────────────────────────

    def PTZ1Address(self):  self._change_ip(1)
    def PTZ2Address(self):  self._change_ip(2)
    def PTZ1IDchange(self): self._change_cam_id(1)
    def PTZ2IDchange(self): self._change_cam_id(2)

    def Quit(self):
        """Cierra la aplicación limpiamente."""
        sys.exit()

    def HelpMsg(self):
        """Muestra el mensaje de contacto de soporte técnico."""
        QMessageBox.information(self, 'For Technical Assistance', Contact, QMessageBox.Ok)
