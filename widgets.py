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

import os
from typing import Optional  # reemplaza `int | None` (sintaxis 3.10+)

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget,
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

    def dragEnterEvent(self, event):
        """Acepta drops con contenido de texto (nombre de consejero)."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Al soltar un nombre sobre el botón, lo asigna al asiento."""
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
        Borde verde si hay nombre asignado → feedback visual de asiento ocupado.
        Usa seat.svg como fondo si existe; falla silenciosamente a color sólido.
        """
        bg = ("background-image: url(seat.svg);"
              if os.path.exists("seat.svg") else "background-color: #cccccc;")
        border = (
            "border: 2px solid #2e7d32; border-radius: 4px; background-color: rgba(76,175,80,30);"
            if self.assigned_name else "border: none;"
        )
        self.setStyleSheet(
            f"QPushButton {{ {bg} background-repeat: no-repeat; background-position: center;"
            f" {border} font: 9px; font-weight: bold; color: {BUTTON_COLOR}; }}"
            f"QPushButton:pressed {{ background-color: rgba(0,0,0,70); }}"
        )

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Asigna o borra el nombre del asiento.

        emit_signal=False durante el arranque (_restore_seat_names) para
        no disparar guardados al cargar datos ya persistidos.
        """
        self.assigned_name = name
        self.setText(f"{self.seat_number}\n{name[:10]}" if name else str(self.seat_number))
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
            self.setText(name[:12])
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
# NamesListWidget — lista de consejeros con doble modo de arrastre
# ─────────────────────────────────────────────────────────────────────────────

class NamesListWidget(QListWidget):
    """
    Lista de consejeros que soporta dos tipos de drag simultáneamente:

    1. REORDENAMIENTO INTERNO: arrastra un nombre arriba/abajo dentro del panel.
       Detectado porque event.source() == self.

    2. ARRASTRE EXTERNO (a botones de asiento): MIME text/plain con CopyAction
       → el ítem permanece en la lista tras soltarlo sobre un asiento.

    SEÑAL order_changed(list):
      Emitida tras cada reordenamiento. NamesPanel la conecta para persistir.
    """

    order_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)

        # CAMBIADO: Optional[int] en lugar de `int | None`
        # MOTIVO: `|` en anotaciones de variables de instancia no funciona
        # en Python 3.9 aunque haya `from __future__ import annotations`.
        self._dragging_row: Optional[int] = None
        self._reorder_locked = False

        self.setStyleSheet("""
            QListWidget {
                background: white; border: 1px solid #ccc;
                border-radius: 4px; outline: none;
            }
            QListWidget::item {
                padding: 4px 8px; border-bottom: 1px solid #eee;
                font: bold 12px; color: #222;
            }
            QListWidget::item:selected {
                background: #e3f2fd; color: #1565C0; border-bottom-color: #bbdefb;
            }
            QListWidget::item:hover:!selected { background: #f1f8e9; }
        """)

    def populate(self, names: list):
        """Recarga la lista completa. Llamar desde NamesPanel._rebuild()."""
        self.clear()
        for name in names:
            self.addItem(QListWidgetItem(name))

    def startDrag(self, supported_actions):
        """
        Override para poner el nombre como text/plain (DragDropButton lo acepta)
        y para guardar _dragging_row (dropEvent lo usa para reordenar).
        CopyAction: el ítem permanece en la lista al soltar sobre un asiento.
        """
        item = self.currentItem()
        if item is None:
            return
        self._dragging_row = self.row(item)

        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(item.text())
        drag.setMimeData(mime)

        rect = self.visualItemRect(item)
        drag.setPixmap(self.viewport().grab(rect))
        drag.setHotSpot(QtCore.QPoint(rect.width() // 2, rect.height() // 2))

        drag.exec_(Qt.CopyAction | Qt.MoveAction)
        self._dragging_row = None

    def dragEnterEvent(self, event):
        """Solo acepta drags internos (reorden). Rechaza drops externos."""
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Reordenamiento interno: mueve ítem de src_row a target_row."""
        if event.source() is not self or self._dragging_row is None:
            event.ignore()
            return
        if self._reorder_locked:
            event.ignore()
            return

        target_item = self.itemAt(event.pos())
        target_row  = self.row(target_item) if target_item else self.count() - 1
        src_row     = self._dragging_row

        if src_row == target_row:
            event.ignore()
            return

        text = self.item(src_row).text()
        self.takeItem(src_row)
        self.insertItem(target_row, QListWidgetItem(text))
        self.setCurrentRow(target_row)

        self.order_changed.emit([self.item(i).text() for i in range(self.count())])
        event.acceptProposedAction()


# ─────────────────────────────────────────────────────────────────────────────
# NamesPanel — panel flotante compacto con lista editable de consejeros
# ─────────────────────────────────────────────────────────────────────────────

class NamesPanel(QWidget):
    """
    Panel semitransparente: x=1325, y=55, w=160, h=960.

    on_changed_cb — Callable de MainWindow:
      Firma: on_changed_cb(old_name=None, new_name=None)
      sin args → lista cambia (add/delete)
      con args → renombrado; MainWindow actualiza botones afectados
    """

    PX, PY, PW, PH = 1325, 55, 160, 960

    def __init__(self, names_list: list, on_changed_cb, clear_all_cb, parent=None):
        super().__init__(parent)
        self.names         = names_list
        self._on_changed   = on_changed_cb
        self._clear_all_cb = clear_all_cb

        self.setGeometry(self.PX, self.PY, self.PW, self.PH)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "NamesPanel {"
            "  background: rgba(240,240,240,242);"
            "  border: 2px solid #999; border-radius: 6px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        title = QLabel("👥 Attendees")
        title.setStyleSheet("font: bold 12px; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Drag to seat\nDouble-tap to clear")
        hint.setStyleSheet("font: 9px; color: #666;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        self._list = NamesListWidget()
        self._list.order_changed.connect(self._on_order_changed)
        layout.addWidget(self._list, stretch=1)

        _btn_style = (
            "QPushButton { background: white; border: 1px solid #bbb;"
            " border-radius: 3px; font: bold 11px; padding: 3px 4px; text-align: left; }"
            "QPushButton:pressed  { background: #ddd; }"
            "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
        )

        self._edit_buttons = []
        for label, slot in [
            ("＋ Add",    self._add_name),
            ("✏ Edit",   self._edit_name),
            ("🗑 Delete", self._delete_name),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setStyleSheet(_btn_style)
            b.clicked.connect(slot)
            layout.addWidget(b)
            self._edit_buttons.append(b)

        btn_clear = QPushButton("✖ Clear All")
        btn_clear.setFixedHeight(26)
        btn_clear.setStyleSheet(
            "QPushButton { background: white; border: 1px solid #e57373;"
            " border-radius: 3px; font: bold 11px; color: #c62828; padding: 3px 4px; text-align: left; }"
            "QPushButton:pressed  { background: #ffebee; }"
            "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
        )
        btn_clear.clicked.connect(self._clear_all)
        layout.addWidget(btn_clear)
        self._edit_buttons.append(btn_clear)

        self._assigned: set = set()
        self._rebuild()
        self.set_edit_mode(False)  # Call es el modo por defecto

    def set_edit_mode(self, enabled: bool):
        """
        Call (False): botones CRUD deshabilitados, reordenamiento bloqueado.
        Set  (True):  todo habilitado.
        El drag de nombre hacia asientos funciona en ambos modos.
        """
        self._list._reorder_locked = not enabled
        for btn in self._edit_buttons:
            btn.setEnabled(enabled)

    def set_assigned(self, assigned: set):
        """Actualiza nombres asignados y refresca la lista visible."""
        self._assigned = assigned
        self._rebuild()

    def _rebuild(self):
        """Muestra solo los nombres NO asignados a ningún asiento."""
        visible = [n for n in self.names if n not in self._assigned]
        self._list.populate(visible)

    def _on_order_changed(self, new_order: list):
        """
        Reconstruye self.names in-place preservando los nombres asignados
        (no aparecen en new_order porque están ocultos en la lista).
        """
        visible_iter = iter(new_order)
        reconstructed = [
            name if name in self._assigned else next(visible_iter)
            for name in self.names
        ]
        self.names[:] = reconstructed
        self._on_changed()

    def _add_name(self):
        text, ok = QInputDialog.getText(self, "Add Name", "Full name:")
        if not (ok and text.strip()):
            return
        name = text.strip()
        if name in self.names:
            QMessageBox.information(self, "Duplicate Name", f'"{name}" already exists.')
            return
        self.names.append(name)
        self._on_changed()
        self._rebuild()

    def _edit_name(self):
        if not self.names:
            return
        old_name, ok = QInputDialog.getItem(
            self, "Edit Name", "Select councillor:", self.names, 0, False)
        if not ok:
            return
        new_name, ok2 = QInputDialog.getText(
            self, "Edit Name", "New name:", text=old_name)
        if not (ok2 and new_name.strip()):
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self.names:
            QMessageBox.information(self, "Duplicate Name", f'"{new_name}" already exists.')
            return
        self.names[self.names.index(old_name)] = new_name
        self._on_changed(old_name=old_name, new_name=new_name)
        self._rebuild()

    def _delete_name(self):
        if not self.names:
            return
        name, ok = QInputDialog.getItem(
            self, "Delete Name", "Select councillor to remove:", self.names, 0, False)
        if not ok:
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f'Remove "{name}" from the list?\n'
            "(Seats keep the assigned name until cleared with double-tap.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.names.remove(name)
            self._on_changed()
            self._rebuild()

    def _clear_all(self):
        """
        Dispara borrado de todas las asignaciones.
        MainWindow ejecuta el borrado real; aquí solo se confirma y delega.
        """
        if not self._assigned:
            return
        reply = QMessageBox.question(
            self, "Clear All Seats",
            "Remove all councillor assignments from seats?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._clear_all_cb()


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
        print(f"[WARNING] angle.png no encontrado — botón {degrees}° sin icono")

    return btn