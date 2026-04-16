#!/usr/bin/env python3
# chairman_button.py — Widget del botón Chairman con preset por persona
#
# Responsabilidad única: gestionar la UI del botón Chairman incluyendo:
#   - Asignación de nombre via drag-drop (hereda de SpecialDragButton)
#   - Recall automático del preset personal al asignar un nombre
#   - Botón "Save position" para guardar la posición actual de la cámara
#   - Botón "Edit" para mostrar/ocultar el botón Save cuando ya hay preset
#
# FLUJO DE USO:
#   1. Operador arrastra nombre al Chairman
#      → Si tiene preset guardado: cámara va a esa posición (recall)
#      → Si no tiene preset:       cámara va al preset genérico 1
#      → Botón "Save" NO se muestra si ya tiene preset
#      → Botón "Edit" aparece para permitir sobreescribir
#   2. Operador ajusta cámara manualmente
#   3. Pulsa "Save position" → se guarda el preset VISCA y se oculta Save
#
# MOTIVO DE ARCHIVO SEPARADO:
#   ChairmanButton tiene estado y lógica propios (presets, botones auxiliares)
#   que no pertenecen a widgets.py (widgets genéricos sin lógica de negocio).

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QPushButton

from widgets import SpecialDragButton
from chairman_presets import get_preset_for_name, CHAIRMAN_GENERIC_PRESET


class ChairmanButton(SpecialDragButton):
    """
    Botón Chairman con gestión de preset por persona.

    Extiende SpecialDragButton añadiendo:
      - Callback on_name_changed: notifica a MainWindow cuando cambia el nombre
        para que ejecute el recall del preset correspondiente.
      - Botones auxiliares "Save position" y "Edit" posicionados justo debajo
        del botón Chairman, dentro de la misma zona de plataforma.
      - Estado de visibilidad de los botones auxiliares según si la persona
        tiene preset guardado o no.

    PARÁMETROS:
      presets_ref  — referencia al dict vivo de presets (el mismo objeto que
                     MainWindow usa y persiste). Cambios aquí son visibles allá.
      on_recall_cb — Callable(preset_num: int) → ejecuta recall en la cámara
      on_save_cb   — Callable(name: str, preset_num: int) → guarda y persiste

    POSICIÓN DE BOTONES AUXILIARES:
      El Chairman está centrado en x=744. Los botones auxiliares se posicionan
      debajo (y=130), centrados en el mismo eje x.
    """

    # Posición del botón Chairman en main_window: cx=744, y=10, w=110, h=115
    # Los botones auxiliares van justo debajo: y=130
    _AUX_Y      = 130   # y de los botones auxiliares
    _AUX_CX     = 744   # centro x (mismo que el botón Chairman)
    _SAVE_W     = 110   # ancho del botón Save
    _SAVE_H     = 28    # alto del botón Save
    _EDIT_W     = 52    # ancho del botón Edit (más pequeño, a la derecha)
    _EDIT_H     = 28

    def __init__(self, presets_ref: dict, on_recall_cb, on_save_cb,
                 svg_data: str, icon_w: int, icon_h: int, parent=None):
        super().__init__(seat_id=1, default_label='Chairman', parent=parent)

        self._presets    = presets_ref  # referencia viva al dict de presets
        self._on_recall  = on_recall_cb
        self._on_save    = on_save_cb

        # Icono SVG del Chairman (atril)
        renderer = QSvgRenderer(QtCore.QByteArray(svg_data.encode('utf-8')))
        pix = QPixmap(icon_w, icon_h)
        pix.fill(Qt.transparent)
        painter = QtGui.QPainter(pix)
        renderer.render(painter, QtCore.QRectF(0, 0, icon_w, icon_h))
        painter.end()
        self.setIcon(QIcon(pix))
        self.setIconSize(QtCore.QSize(icon_w, icon_h))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setStyleSheet(
            "QToolButton {"
            "  background-color: transparent; border: none;"
            "  font: bold 13px; color: black;"
            "}"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )

        # ── Botón "Save position" ──────────────────────────────────────────
        # Visible solo cuando:
        #   a) Hay persona asignada, Y
        #   b) La persona no tiene preset aún, O el operador pulsó "Edit"
        self._btn_save = QPushButton('💾 Save position', parent)
        self._btn_save.setGeometry(
            self._AUX_CX - self._SAVE_W // 2, self._AUX_Y,
            self._SAVE_W, self._SAVE_H
        )
        self._btn_save.setStyleSheet(
            "QPushButton { background: #1976D2; border: none; border-radius: 4px;"
            " font: bold 11px; color: white; }"
            "QPushButton:pressed { background: #1255a0; }"
        )
        self._btn_save.clicked.connect(self._on_save_clicked)
        self._btn_save.hide()

        # ── Botón "Edit" ───────────────────────────────────────────────────
        # Visible solo cuando la persona ya tiene preset guardado.
        # Al pulsarlo muestra "Save position" para permitir sobreescribir.
        self._btn_edit = QPushButton('✏ Edit', parent)
        self._btn_edit.setGeometry(
            self._AUX_CX - self._EDIT_W // 2, self._AUX_Y,
            self._EDIT_W, self._EDIT_H
        )
        self._btn_edit.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,180); border: none; border-radius: 4px;"
            " font: 10px; color: #ddd; }"
            "QPushButton:pressed { background: rgba(50,50,50,200); }"
        )
        self._btn_edit.clicked.connect(self._on_edit_clicked)
        self._btn_edit.hide()

    # ── Override de set_name: añade recall y actualiza botones ────────────────

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Override de SpecialDragButton.set_name().

        Al asignar un nombre:
          - Ejecuta recall del preset personal (o genérico si no tiene).
          - Actualiza visibilidad de botones auxiliares.

        Al borrar el nombre (name=''):
          - Oculta todos los botones auxiliares.

        emit_signal=False durante _restore_seat_names (arranque).
        En ese caso no se hace recall — la cámara no se mueve al cargar.
        MOTIVO: el operador no ha pedido mover la cámara, solo se está
        restaurando el estado visual de la UI.
        """
        # Llamar al padre para que actualice texto, estilo y emita señal
        super().set_name(name, emit_signal=emit_signal)

        if name and emit_signal:
            # emit_signal=False → arranque → no mover la cámara
            preset_num = get_preset_for_name(self._presets, name)
            self._on_recall(preset_num)

        self._update_aux_buttons()

    def _update_aux_buttons(self):
        """
        Actualiza la visibilidad de Save y Edit según el estado actual.

        Lógica:
          Sin persona asignada → ambos ocultos
          Con persona, sin preset → Save visible, Edit oculto
          Con persona, con preset → Save oculto, Edit visible
            (el operador puede pulsar Edit para mostrar Save y sobreescribir)
        """
        name = self.assigned_name
        if not name:
            # Sin persona: limpiar todo
            self._btn_save.hide()
            self._btn_edit.hide()
            return

        has_preset = name in self._presets
        if has_preset:
            # Ya tiene preset: no mostrar Save por defecto, solo Edit
            self._btn_save.hide()
            self._btn_edit.show()
            self._btn_edit.raise_()
        else:
            # Sin preset: mostrar Save directamente, sin Edit
            self._btn_save.show()
            self._btn_save.raise_()
            self._btn_edit.hide()

    def _on_edit_clicked(self):
        """
        El operador quiere sobreescribir el preset guardado.
        Muestra Save y oculta Edit — el flujo de guardado es el mismo
        que para una persona sin preset.
        """
        self._btn_edit.hide()
        self._btn_save.show()
        self._btn_save.raise_()

    def _on_save_clicked(self):
        """
        Guarda la posición actual de la cámara como preset de esta persona.
        Delega en MainWindow (on_save_cb) para enviar el comando VISCA y
        persistir en chairman_presets.json.
        Después actualiza los botones: Save → oculto, Edit → visible.
        """
        name = self.assigned_name
        if not name:
            return  # no debería ocurrir, pero defensa
        self._on_save(name)
        # Tras guardar, volver al estado "ya tiene preset"
        self._btn_save.hide()
        self._btn_edit.show()
        self._btn_edit.raise_()

    def refresh_preset_state(self):
        """
        Fuerza actualización de botones auxiliares sin cambiar el nombre.
        Llamar desde MainWindow después de persistir un preset nuevo para
        asegurarse de que el estado visual es consistente con el dict.
        """
        self._update_aux_buttons()
