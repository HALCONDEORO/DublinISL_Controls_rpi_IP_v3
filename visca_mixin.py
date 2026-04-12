#!/usr/bin/env python3
# visca_mixin.py — Adaptador Qt sobre ViscaProtocol
#
# ViscaController es una capa fina que:
#   1. Construye ViscaUICallbacks inyectando implementaciones Qt en ViscaProtocol.
#   2. Expone la misma API pública que antes (métodos de movimiento, zoom, etc.)
#      delegándola en self._proto.
#
# TODA la lógica VISCA vive en visca_protocol.ViscaProtocol (sin Qt).
# Este archivo solo contiene código Qt: QTimer, QMetaObject, QMessageBox.
#
# PATRÓN COMPOSICIÓN: recibe la ventana principal (window) en el constructor
# y accede a sus widgets a través de self._w.

from __future__ import annotations

from PyQt5.QtCore import QMetaObject, Qt, Q_ARG, QTimer
from PyQt5.QtWidgets import QMessageBox

from config import CAM1, CAM2
from visca_protocol import ViscaProtocol, ViscaUICallbacks


class ViscaController:

    def __init__(self, window):
        self._w = window

        self._proto = ViscaProtocol(
            cameras=window._cameras,
            ui=ViscaUICallbacks(
                # ── Lectura de estado UI ──────────────────────────────────────
                get_active_cam=self._active_cam,
                get_speed=lambda: window.SpeedSlider.value(),
                get_zoom_value=lambda: window.ZoomSlider.value(),
                is_call_mode=lambda: window.BtnCall.isChecked(),
                is_set_mode=lambda: window.BtnSet.isChecked(),

                # ── Threading ────────────────────────────────────────────────
                schedule_ui=lambda fn: QTimer.singleShot(0, fn),
                # QMetaObject.invokeMethod es thread-safe: funciona tanto desde
                # el hilo principal como desde threads de worker (query de zoom).
                update_zoom_slider=lambda pct: QMetaObject.invokeMethod(
                    window.ZoomSlider, "setValue",
                    Qt.QueuedConnection, Q_ARG(int, pct)
                ),

                # ── Diálogos ─────────────────────────────────────────────────
                show_error=lambda: QMessageBox.warning(
                    window, 'Camera Control Error',
                    'A network error occurred. Check camera connections.'
                ),
                confirm_preset=lambda num, cam_name: QMessageBox.question(
                    window, f'Record Preset {num} ({cam_name})',
                    "Are you sure you want to record this preset?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) == QMessageBox.Yes,

                # ── Notificaciones de cambio de estado ───────────────────────
                # Las lambdas acceden a window._right_panel en el momento de la
                # llamada (lazy), no en la construcción: _right_panel aún no
                # existe cuando ViscaController se instancia en MainWindow.__init__.
                on_focus_changed=window._update_focus_ui,
                on_exposure_changed=window._update_exposure_ui,
                on_backlight_changed=window._update_backlight_ui,
                on_af_result=lambda ok: window._right_panel._flash_button(
                    window._right_panel.btn_one_push_af, ok),
                on_brightness_up_result=lambda ok: window._right_panel._flash_button(
                    window._right_panel.btn_brighter, ok),
                on_brightness_down_result=lambda ok: window._right_panel._flash_button(
                    window._right_panel.btn_darker, ok),
            ),
        )

    def _active_cam(self) -> tuple[str, str]:
        """Devuelve (ip, cam_id) de la cámara actualmente seleccionada en la UI."""
        if self._w.Cam1.isChecked():
            return CAM1.ip, CAM1.cam_id
        return CAM2.ip, CAM2.cam_id

    def _on_speed_changed(self, value: int):
        """Callback del slider: actualiza la etiqueta de velocidad en tiempo real."""
        self._w.SpeedValueLabel.setText(self._proto._speed_label_text(value))

    def __getattr__(self, name):
        return getattr(self._proto, name)
