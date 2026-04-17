#!/usr/bin/env python3
# names_panel.py — Panel de asistentes y lista de asistentes
#
# Extraído de widgets.py para reducir el tamaño de ese módulo.
#
# Clases:
#   NamesListWidget — QListWidget con reordenamiento interno + arrastre externo
#   NamesPanel      — panel flotante compacto con lista editable de asistentes

from typing import Optional

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from widgets import DragDropButton


# ─────────────────────────────────────────────────────────────────────────────
# NamesListWidget — lista de asistentes con doble modo de arrastre
# ─────────────────────────────────────────────────────────────────────────────

class NamesListWidget(QListWidget):
    """
    Lista de asistentes que soporta dos tipos de drag simultáneamente:

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
        Solo activo en modo SET; en modo CALL el drag externo está bloqueado.
        """
        item = self.currentItem()
        if item is None:
            return
        if DragDropButton._call_mode:
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
# NamesPanel — panel flotante compacto con lista editable de asistentes
# ─────────────────────────────────────────────────────────────────────────────

class NamesPanel(QWidget):
    """
    Panel semitransparente: x=1255, y=65, w=220, h=430. Arrastrable por toda la ventana.

    on_changed_cb — Callable de MainWindow:
      Firma: on_changed_cb(old_name=None, new_name=None)
      sin args → lista cambia (add/delete)
      con args → renombrado; MainWindow actualiza botones afectados
    """

    PX, PY, PW, PH = 1255, 65, 220, 730

    def __init__(self, names_list: list, on_changed_cb, clear_all_cb, parent=None):
        super().__init__(parent)
        self.names         = names_list
        self._on_changed   = on_changed_cb
        self._clear_all_cb = clear_all_cb
        self._drag_pos     = None

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

        hint = QLabel("Drag to seat · drag back to unassign\nDouble-tap seat to clear")
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
        self.setAcceptDrops(True)

    # ── Drop desde asientos (desasignar) ──────────────────────────────────────

    def dragEnterEvent(self, event):
        if DragDropButton._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def dragMoveEvent(self, event):
        if DragDropButton._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def dropEvent(self, event):
        if DragDropButton._call_mode:
            event.ignore()
            return
        name = event.mimeData().text().strip()
        if name:
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    # ─────────────────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        """
        Call (False): botones CRUD deshabilitados, reordenamiento bloqueado, drag desactivado.
        Set  (True):  todo habilitado, drag activo.
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
            self, "Edit Name", "Select asistente:", self.names, 0, False)
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
            self, "Delete Name", "Select asistente to remove:", self.names, 0, False)
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

    # ── Arrastre del panel ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _clear_all(self):
        """
        Dispara borrado de todas las asignaciones.
        MainWindow ejecuta el borrado real; aquí solo se confirma y delega.
        """
        if not self._assigned:
            return
        reply = QMessageBox.question(
            self, "Clear All Seats",
            "Remove all asistente assignments from seats?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._clear_all_cb()
