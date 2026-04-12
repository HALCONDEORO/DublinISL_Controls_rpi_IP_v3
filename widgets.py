#!/usr/bin/env python3
# widgets.py — Widgets personalizados de la UI
#
# Responsabilidad única: definir componentes visuales reutilizables
# que no contienen lógica de negocio (no saben nada de VISCA ni de presets).
#
# Widgets incluidos:
#   DragDropButton    — clase base con drag-drop y doble-tap compartidos
#   GoButton          — botón de asiento numerado (hereda DragDropButton + QPushButton)
#   SpecialDragButton — QToolButton especial (hereda DragDropButton + QToolButton)
#   NamesListWidget   — QListWidget con reordenamiento interno + arrastre externo
#   NamesPanel        — panel flotante compacto con lista editable de consejeros
#   make_arrow_btn    — helper para crear botones de dirección con icono rotado
#
# CAMBIOS EN ESTE REFACTOR:
#
#   1. DUPLICACIÓN ELIMINADA — nueva clase DragDropButton:
#      GoButton y SpecialDragButton tenían estos 4 métodos idénticos o casi:
#        dragEnterEvent, dragMoveEvent, dropEvent → byte-for-byte idénticos
#        mouseDoubleClickEvent → misma estructura, solo difería el mensaje
#      Se extrae DragDropButton como mixin de comportamiento.
#      Cualquier cambio en lógica de drag (p.ej. filtrar MIME) ahora es
#      una sola edición, no dos.
#      El mensaje del diálogo de confirmación se parametriza via
#      _clear_confirm_msg() — cada subclase lo implementa con su contexto.
#
#   2. FIX PYTHON 3.9: `int | None` → Optional[int] en _dragging_row.
#      MOTIVO: `|` en anotaciones de variables de instancia no está cubierto
#      por `from __future__ import annotations` en Python 3.9.
#
#   3. FIX _apply_assigned_style(): reemplaza str.replace() frágil por
#      concatenación directa del bloque CSS de borde verde al estilo base.
#      La versión anterior fallaba silenciosamente si el estilo base no
#      contenía exactamente 'border: 0px solid black;' o 'border: none;'.

import logging
import os
from typing import Optional  # reemplaza `int | None` (sintaxis 3.10+)

logger = logging.getLogger(__name__)

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QPushButton, QToolButton,
)

from config import BUTTON_COLOR


# ─────────────────────────────────────────────────────────────────────────────
# DragDropButton — mixin de drag-drop y doble-tap compartido
# ─────────────────────────────────────────────────────────────────────────────

class DragDropButton:
    """
    Mixin de comportamiento para botones que aceptan drag-drop de nombres
    desde NamesListWidget y permiten borrar la asignación con doble-tap.

    NO hereda de ningún widget Qt — se combina con QPushButton o QToolButton
    mediante herencia múltiple en GoButton y SpecialDragButton.

    CONTRATO CON SUBCLASES (deben definir):
      self.assigned_name  — str, nombre actualmente asignado ('' = vacío)
      set_name(name: str) — aplica el borrado/asignación
      _clear_confirm_msg()→ str — texto del diálogo de confirmación de borrado

    MOTIVO DE EXTRACCIÓN:
      Los 4 métodos estaban copiados byte-a-byte en GoButton y SpecialDragButton.
      Un cambio (p.ej. filtrar por tipo MIME, cambiar el botón del diálogo)
      antes requería dos ediciones en dos clases distintas.
    """

    _call_mode: bool = True  # compartida por todas las subclases (GoButton, SpecialDragButton)

    def dragEnterEvent(self, event):
        """Acepta drops solo en modo SET. En modo CALL ignora el drag."""
        if self._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Al soltar un nombre sobre el botón, lo asigna al asiento (solo en modo SET)."""
        if self._call_mode:
            event.ignore()
            return
        name = event.mimeData().text().strip()
        if name:
            self.set_name(name)
            event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event):
        """
        Doble-tap con nombre asignado → confirmación → borrado.

        PARAMETRIZADO: el texto del diálogo lo aporta _clear_confirm_msg()
        porque varía entre subclases:
          GoButton:          'Clear "X" from seat 42?'
          SpecialDragButton: 'Clear "X" from Wheelchair?'
        """
        if self.assigned_name:
            reply = QMessageBox.question(
                self.parent(), "Clear Assignment",
                self._clear_confirm_msg(),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.set_name("")
        else:
            # Delegar al siguiente en el MRO (QPushButton o QToolButton)
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._call_mode or not (event.buttons() & Qt.LeftButton) or not self.assigned_name:
            super().mouseMoveEvent(event)
            return
        dist = (event.pos() - self._drag_start_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(self.assigned_name)
        drag.setMimeData(mime)
        result = drag.exec_(Qt.MoveAction | Qt.CopyAction)
        if result == Qt.MoveAction:
            self.set_name("")

    def _clear_confirm_msg(self) -> str:
        """
        Texto del diálogo de confirmación de borrado.
        Debe ser implementado por cada subclase con su contexto.
        Falla explícitamente si se olvida implementar.
        """
        raise NotImplementedError(
            f"{type(self).__name__} debe implementar _clear_confirm_msg()")


# ─────────────────────────────────────────────────────────────────────────────
# GoButton — botón de asiento numerado con drag-drop y nombre asignado
# ─────────────────────────────────────────────────────────────────────────────

class GoButton(DragDropButton, QPushButton):
    """
    Botón de asiento (71×82 px).

    Hereda drag-drop y doble-tap de DragDropButton.
    Hereda el widget Qt de QPushButton.

    SEÑAL name_assigned(int, str):
      (seat_number, name) — name='' borra la asignación.
      MainWindow la conecta para persistir en seat_names.json.

    NOTA: _apply_style() sobreescribe cualquier setStyleSheet() posterior.
    Los botones de plataforma usan QPushButton plano por este motivo.

    ORDEN MRO: DragDropButton primero → sus eventos (drag, doble-tap) tienen
    prioridad. QPushButton aporta __init__, setStyleSheet, etc.
    """

    name_assigned = pyqtSignal(int, str)

    @classmethod
    def set_call_mode(cls, call: bool):
        DragDropButton._call_mode = call  # propaga a GoButton y SpecialDragButton

    WIDTH  = 71
    HEIGHT = 82

    def __init__(self, seat_number: int, parent=None):
        # Inicializar QPushButton explícitamente (necesita parent para el árbol Qt)
        QPushButton.__init__(self, str(seat_number), parent)
        self.seat_number   = int(seat_number)  # int explícito: evita bugs si llega str
        self.assigned_name = ""
        self.resize(self.WIDTH, self.HEIGHT)
        self.setAcceptDrops(True)
        self._apply_style()

    def _clear_confirm_msg(self) -> str:
        """Mensaje con el número de asiento — implementación requerida por DragDropButton."""
        return f'Clear "{self.assigned_name}" from seat {self.seat_number}?'

    def _apply_style(self):
        """
        Call mode : burdeo pastel vacío / burdeo oscuro si tiene nombre.
        Set mode  : gris, borde verde si tiene nombre.
        Usa seat.svg como fondo si existe; falla silenciosamente a color sólido.
        """
        if self._call_mode:
            svg = "seat_occupied.svg" if self.assigned_name else "seat_call.svg"
            bg = f"background-image: url({svg}); background-repeat: no-repeat; background-position: center;"
            border = "border: none;"
            text_color = "white" if self.assigned_name else BUTTON_COLOR
        elif os.path.exists("seat.svg"):
            bg = "background-image: url(seat.svg); background-repeat: no-repeat; background-position: center;"
            border = (
                "border: 2px solid #2e7d32; border-radius: 4px; background-color: rgba(76,175,80,30);"
                if self.assigned_name else "border: none;"
            )
            text_color = BUTTON_COLOR
        else:
            bg = "background-color: #cccccc;"
            border = (
                "border: 2px solid #2e7d32; border-radius: 4px; background-color: rgba(76,175,80,30);"
                if self.assigned_name else "border: none;"
            )
            text_color = BUTTON_COLOR
        self.setStyleSheet(
            f"QPushButton {{ {bg} {border} font: 12px; font-weight: bold; color: {text_color}; }}"
            f"QPushButton:pressed {{ background-color: rgba(0,0,0,70); }}"
        )

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Asigna o borra el nombre del asiento.

        emit_signal=False durante el arranque (_restore_seat_names) para
        no disparar guardados al cargar datos ya persistidos.
        """
        self.assigned_name = name
        self.setText(name.split()[0] if name else str(self.seat_number))
        self._apply_style()
        if emit_signal:
            self.name_assigned.emit(self.seat_number, name)


# ─────────────────────────────────────────────────────────────────────────────
# SpecialDragButton — QToolButton con drag-drop para botones especiales
# ─────────────────────────────────────────────────────────────────────────────

class SpecialDragButton(DragDropButton, QToolButton):
    """
    QToolButton para botones especiales: Wheelchair (128), Second Room (129),
    Chairman (preset 1).

    Hereda drag-drop y doble-tap de DragDropButton.
    Hereda el widget Qt de QToolButton (necesario para icono arriba + texto abajo).

    DIFERENCIA CON GoButton:
      set_name() muestra el nombre truncado reemplazando _default_label,
      no un número de asiento.

    SEÑAL name_assigned(int, str):
      (seat_id, name). seat_id es la clave en seat_names.json. name='' = borrado.

    ORDEN MRO: DragDropButton primero → sus eventos tienen prioridad.
    QToolButton aporta el widget Qt subyacente.
    """

    name_assigned = pyqtSignal(int, str)

    def __init__(self, seat_id: int, default_label: str, parent=None):
        QToolButton.__init__(self, parent)
        self.seat_number    = seat_id
        self._default_label = default_label  # texto a restaurar al borrar la asignación
        self.assigned_name  = ""
        self._base_style    = ""             # capturado lazy en _apply_assigned_style
        self.setText(default_label)
        self.setAcceptDrops(True)

    def _clear_confirm_msg(self) -> str:
        """Mensaje con el nombre del botón especial — implementación requerida por DragDropButton."""
        return f'Clear "{self.assigned_name}" from {self._default_label}?'

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Asigna o borra el nombre.
        Con nombre: texto truncado + borde verde.
        Sin nombre: restaura _default_label + estilo base.
        """
        self.assigned_name = name
        if name:
            self.setText(name.split()[0])
            self._apply_assigned_style()
        else:
            self.setText(self._default_label)
            self._apply_default_style()
        if emit_signal:
            self.name_assigned.emit(self.seat_number, name)

    def _apply_assigned_style(self):
        """
        Añade borde verde al estilo base cuando hay nombre asignado.

        CAMBIADO: la versión anterior usaba str.replace() buscando
        'border: 0px solid black;' o 'border: none;' dentro del CSS.
        Si el estilo base no contenía ninguna de esas cadenas exactas,
        el borde no se aplicaba silenciosamente — bug difícil de detectar.

        AHORA: captura _base_style lazy (la primera vez que se asigna un
        nombre, cuando MainWindow ya aplicó su setStyleSheet), y concatena
        el borde verde como bloque CSS adicional sin depender del contenido
        exacto del estilo base.
        """
        if not self._base_style:
            # Primera asignación: capturar el estilo que MainWindow ya aplicó.
            # Lazy porque en __init__ el estilo aún no está aplicado.
            self._base_style = self.styleSheet()

        self.setStyleSheet(
            self._base_style
            + "\nQToolButton { border: 2px solid #2e7d32;"
              " background-color: rgba(76,175,80,30); }"
        )

    def _apply_default_style(self):
        """Restaura el estilo base sin borde de asignación."""
        if self._base_style:
            self.setStyleSheet(self._base_style)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: make_arrow_btn
# ─────────────────────────────────────────────────────────────────────────────

def make_arrow_btn(parent, x: int, y: int, degrees: int) -> QPushButton:
    """
    Crea un QPushButton con angle.png rotado a los grados indicados.

    BASELINE: angle.png apunta hacia ABAJO (0°). Rotación horaria:
      0°   → Abajo       90°  → Izquierda
      180° → Arriba     270°  → Derecha

    Si angle.png no existe el botón queda vacío pero funcional.
    """
    btn = QPushButton(parent)
    btn.setGeometry(x, y, 100, 100)
    btn.setStyleSheet("border: none; background: transparent")

    if os.path.exists("angle.png"):
        pix = QPixmap("angle.png").transformed(
            QtGui.QTransform().rotate(degrees), Qt.SmoothTransformation)
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(90, 90))
    else:
        logger.warning("angle.png no encontrado — botón %d° sin icono", degrees)

    return btn

