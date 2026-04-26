#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# session_mixin.py — Mixin de gestión de sesión
#
# Responsabilidad única: controlar el ciclo de vida de la sesión:
# encender cámaras, esperar arranque de motores, ir a Home, apagar.
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - REDUNDANCIA ELIMINADA: el CSS de BtnSession se repetía 3 veces
#     (estado OFF, estado Starting, estado ON) con strings literales idénticos
#     dentro de ToggleSession() y _session_home().
#     Ahora son constantes de clase _STYLE_BTN_OFF, _STYLE_BTN_STARTING,
#     _STYLE_BTN_ON. Un solo lugar para cambiar el estilo.
#   - MOTIVO: si se cambia el radio del botón (actualmente 25px) o el color
#     base, antes había que modificar 3 strings en 2 métodos distintos.
#     Con constantes, un solo cambio lo afecta todo.

from PyQt5 import QtCore
from PyQt5.QtWidgets import QMessageBox

from config import CAM1, CAM2


class SessionController:

    # ── Estilos del botón de sesión ────────────────────────────────────────
    # Extraídos como constantes de clase para evitar duplicación.
    # Antes estaban inline en ToggleSession() y _session_home() como strings
    # repetidos — cualquier cambio de color/radio requería 3 ediciones.

    _STYLE_BTN_OFF = (
        "QPushButton{background-color: #8b1a1a; border: 2px solid #5a0d0d;"
        " font: bold 26px; color: white; border-radius: 25px}"
        "QPushButton:pressed{background-color: #5a0d0d}"
    )

    _STYLE_BTN_STARTING = (
        # Gris: indica que el botón está temporalmente deshabilitado
        # mientras las cámaras inicializan los motores (8 segundos).
        "QPushButton{background-color: #555; border: 2px solid #333;"
        " font: bold 26px; color: #aaa; border-radius: 25px}"
    )

    _STYLE_BTN_ON = (
        "QPushButton{background-color: #1a7a1a; border: 2px solid #0d4d0d;"
        " font: bold 26px; color: white; border-radius: 25px}"
        "QPushButton:pressed{background-color: #0d4d0d}"
    )

    def __init__(self, window):
        self._w = window

    def ToggleSession(self):
        """
        Botón ⏻: alterna entre iniciar y terminar la sesión.

        INICIO DE SESIÓN:
          1. Envía Power ON a ambas cámaras (01 04 00 02 FF).
          2. Deshabilita el botón durante 8 s: las cámaras PTZ necesitan
             ese tiempo para inicializar los motores antes de aceptar movimiento.
          3. Tras 8 s, _session_home() mueve ambas a Home y reactiva el botón.

        FIN DE SESIÓN:
          1. Pide confirmación para evitar apagados accidentales.
          2. Envía Standby (01 04 00 03 FF) a ambas cámaras.
          3. Actualiza UI a estado OFF.
        """
        if not self._w.session_active:
            # ── Arrancar sesión ───────────────────────────────────────────
            self._w.session_active = True
            self._w._reset_watchdog_state()  # restaura caps y reintentos

            # Deshabilitar botón mientras las cámaras arrancan
            self._w.BtnSession.setEnabled(False)
            self._w.BtnSession.setStyleSheet(self._STYLE_BTN_STARTING)  # gris: en proceso
            self._w.SessionStatus.setText('Starting...')
            self._w.SessionStatus.setStyleSheet("font: bold 12px; color: #888")

            # Power ON ambas cámaras: 8x 01 04 00 02 FF
            self._w._visca._send_cmd(CAM1.ip, CAM1.cam_id, "01040002FF")
            self._w._visca._send_cmd(CAM2.ip, CAM2.cam_id, "01040002FF")

            # Esperar 8 s antes de enviar Home: los motores PTZ necesitan
            # este tiempo para inicializarse después de encenderse.
            QtCore.QTimer.singleShot(8000, self._session_home)

        else:
            # ── Terminar sesión ───────────────────────────────────────────
            reply = QMessageBox.question(
                self._w, 'End Session',
                'Power off both cameras and end the session?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._w._visca.cancel_preset_polls()

                # Standby ambas cámaras: 8x 01 04 00 03 FF
                self._w._visca._send_cmd(CAM1.ip, CAM1.cam_id, "01040003FF")
                self._w._visca._send_cmd(CAM2.ip, CAM2.cam_id, "01040003FF")

                self._w.session_active = False
                self._w.BtnSession.setStyleSheet(self._STYLE_BTN_OFF)  # rojo: apagado
                self._w.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
                self._w.SessionStatus.setText('OFF')
                self._w.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

    def _session_home(self):
        """
        Llamado por QTimer 8 s después del Power ON.
        Envía Home a ambas cámaras y activa el botón de sesión (verde = ON).
        """
        # Home: 8x 01 06 04 FF
        self._w._visca._send_cmd(CAM1.ip, CAM1.cam_id, "010604FF")
        self._w._visca._send_cmd(CAM2.ip, CAM2.cam_id, "010604FF")

        self._w.BtnSession.setStyleSheet(self._STYLE_BTN_ON)  # verde: sesión activa
        self._w.BtnSession.setToolTip('End Session: Power OFF (standby) both cameras')
        self._w.BtnSession.setEnabled(True)
        self._w.SessionStatus.setText('ON')
        self._w.SessionStatus.setStyleSheet("font: bold 12px; color: #1a7a1a")