#!/usr/bin/env python3
# session_mixin.py — Mixin de gestión de sesión
#
# Responsabilidad única: controlar el ciclo de vida de la sesión:
# encender cámaras, esperar arranque de motores, ir a Home, apagar.
#
# MOTIVO DE SEPARACIÓN: la lógica de sesión es independiente del layout
# y de los comandos VISCA individuales.  Separarla facilita cambiar
# tiempos de espera o comportamiento de inicio sin tocar nada más.

from PyQt5 import QtCore
from PyQt5.QtWidgets import QMessageBox

from config import IPAddress, IPAddress2, Cam1ID, Cam2ID


class SessionMixin:

    def ToggleSession(self):
        """
        Botón ⏻: alterna entre iniciar y terminar la sesión.

        INICIO DE SESIÓN:
        1. Envía Power ON a ambas cámaras (comando 01 04 00 02 FF).
        2. Deshabilita el botón durante 8 segundos: las cámaras PTZ necesitan
           ese tiempo para inicializar los motores antes de aceptar movimiento.
        3. Tras 8 s, _session_home() mueve ambas a Home y reactiva el botón.

        FIN DE SESIÓN:
        1. Pide confirmación para evitar apagados accidentales.
        2. Envía Standby (01 04 00 03 FF) a ambas cámaras.
        3. Actualiza UI a estado OFF.
        """
        if not self.session_active:
            # ── Arrancar sesión ───────────────────────────────────────────────
            self.session_active = True

            # Deshabilitar botón mientras las cámaras arrancan
            self.BtnSession.setEnabled(False)
            self.BtnSession.setStyleSheet(
                "QPushButton{background-color: #555; border: 2px solid #333; "
                "font: bold 26px; color: #aaa; border-radius: 25px}"
            )
            self.SessionStatus.setText('Starting...')
            self.SessionStatus.setStyleSheet("font: bold 12px; color: #888")

            # Power ON ambas cámaras: 8x 01 04 00 02 FF
            self._send_cmd(IPAddress,  Cam1ID, "01040002FF")
            self._send_cmd(IPAddress2, Cam2ID, "01040002FF")

            # Esperar 8 s antes de enviar Home: los motores PTZ necesitan
            # este tiempo para inicializarse después de encenderse.
            QtCore.QTimer.singleShot(8000, self._session_home)

        else:
            # ── Terminar sesión ───────────────────────────────────────────────
            reply = QMessageBox.question(
                self, 'End Session',
                'Power off both cameras and end the session?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Standby ambas cámaras: 8x 01 04 00 03 FF
                self._send_cmd(IPAddress,  Cam1ID, "01040003FF")
                self._send_cmd(IPAddress2, Cam2ID, "01040003FF")

                self.session_active = False

                # Restaurar estilo del botón a "apagado" (rojo oscuro)
                self.BtnSession.setStyleSheet(
                    "QPushButton{background-color: #8b1a1a; border: 2px solid #5a0d0d; "
                    "font: bold 26px; color: white; border-radius: 25px}"
                    "QPushButton:pressed{background-color: #5a0d0d}"
                )
                self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
                self.SessionStatus.setText('OFF')
                self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

    def _session_home(self):
        """
        Llamado por QTimer 8 s después del Power ON.
        Envía Home a ambas cámaras y activa el botón de sesión (verde = ON).
        """
        # Home: 8x 01 06 04 FF
        self._send_cmd(IPAddress,  Cam1ID, "010604FF")
        self._send_cmd(IPAddress2, Cam2ID, "010604FF")

        # Estilo del botón a "activo" (verde)
        self.BtnSession.setStyleSheet(
            "QPushButton{background-color: #1a7a1a; border: 2px solid #0d4d0d; "
            "font: bold 26px; color: white; border-radius: 25px}"
            "QPushButton:pressed{background-color: #0d4d0d}"
        )
        self.BtnSession.setToolTip('End Session: Power OFF (standby) both cameras')
        self.BtnSession.setEnabled(True)
        self.SessionStatus.setText('ON')
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #1a7a1a")
