#!/usr/bin/env python3
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

from PyQt5.QtWidgets import QMessageBox, QInputDialog

from config import (
    IPAddress, IPAddress2, Cam1ID, Cam2ID, Contact,
    is_valid_ip, is_valid_cam_id,
)


class DialogsMixin:

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
            current  = IPAddress  if cam_num == 1 else IPAddress2
            filename = 'PTZ1IP.txt' if cam_num == 1 else 'PTZ2IP.txt'
            field    = 'IP address'
            validate = is_valid_ip
            hint     = 'four numbers separated by dots (e.g. 172.16.1.11)'
            label    = 'IP Address'
        else:  # 'id'
            current  = Cam1ID      if cam_num == 1 else Cam2ID
            filename = 'Cam1ID.txt' if cam_num == 1 else 'Cam2ID.txt'
            field    = 'VISCA ID'
            validate = is_valid_cam_id
            hint     = 'a hex value such as "81" or "82"'
            label    = 'Camera ID'

        title = f'{cam_name} PTZ Control'

        # Paso 1: confirmación — evitar cambios accidentales
        if QMessageBox.warning(
            self, title,
            f'Do you want to change the {field} used to control the {cam_name} camera?',
            QMessageBox.Ok, QMessageBox.Cancel
        ) != QMessageBox.Ok:
            return

        # Paso 2: pedir nuevo valor
        text, ok = QInputDialog.getText(
            self, title,
            f'New {field} for {cam_name} Camera (current: {current}):',
            text=current,
        )
        if not (ok and text.strip()):
            return  # Usuario canceló o dejó vacío

        text = text.strip()

        # Paso 3: validar
        if not validate(text):
            QMessageBox.warning(
                self, f'Invalid {label}',
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

    def Quit(self):
        """Cierra la aplicación limpiamente."""
        sys.exit()

    def HelpMsg(self):
        """Muestra el mensaje de contacto de soporte técnico."""
        QMessageBox.information(self, 'For Technical Assistance', Contact, QMessageBox.Ok)