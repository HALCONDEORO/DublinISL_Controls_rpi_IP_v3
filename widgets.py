#!/usr/bin/env python3
# widgets.py — Widgets personalizados de la UI
#
# Responsabilidad única: definir componentes visuales reutilizables
# que no contienen lógica de negocio (no saben nada de VISCA ni de presets).
#
# Widgets incluidos:
#   GoButton          — botón de asiento numerado con drag-drop y nombre asignado
#   SpecialDragButton — QToolButton con drag-drop para botones especiales
#                       (Wheelchair seat 128, Second Room seat 129, Chairman preset 1)
#   NamesListWidget   — QListWidget con reordenamiento interno + arrastre externo a GoButton
#   NamesPanel        — panel flotante compacto con lista editable de consejeros
#   make_arrow_btn    — helper para crear botones de dirección con icono rotado

import os

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from config import BUTTON_COLOR


# ─────────────────────────────────────────────────────────────────────────────
# GoButton — botón de asiento numerado con drag-drop y nombre asignado
# ─────────────────────────────────────────────────────────────────────────────

class GoButton(QPushButton):
    """
    Botón de asiento (70×82 px) con tres capacidades añadidas:

    1. Nombre asignado: se asigna via drag-drop desde NamesListWidget.
       El estilo cambia a borde verde para indicar asiento ocupado.

    2. Drag-drop: acepta cualquier drop con MIME text/plain.
       NamesListWidget lo envía con CopyAction → el nombre permanece
       en la lista aunque se asigne a múltiples asientos.

    3. Doble-tap para borrar: confirmación + borrado de asignación.

    SEÑAL name_assigned(int, str):
      Parámetros: (seat_number, name) — name="" = borrar asignación.
      MainWindow la conecta para persistir en seat_names.json.

    NOTA: _apply_style() sobreescribe cualquier setStyleSheet() posterior.
    Los botones de plataforma usan QPushButton plano por este motivo.
    """

    name_assigned = pyqtSignal(int, str)

    WIDTH  = 71
    HEIGHT = 82

    def __init__(self, seat_number: int, parent=None):
        super().__init__(str(seat_number), parent)
        self.seat_number   = int(seat_number)  # int explícito: evita bugs si llega str
        self.assigned_name = ""
        self.resize(self.WIDTH, self.HEIGHT)
        self.setAcceptDrops(True)
        self._apply_style()

    # ── Estilo ────────────────────────────────────────────────────────────────

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

    # ── API pública ───────────────────────────────────────────────────────────

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

    # ── Drag-drop ─────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        name = event.mimeData().text().strip()
        if name:
            self.set_name(name)
            event.acceptProposedAction()

    # ── Doble-tap para borrar ─────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        if self.assigned_name:
            reply = QMessageBox.question(
                self.parent(), "Clear Assignment",
                f'Clear "{self.assigned_name}" from seat {self.seat_number}?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.set_name("")
        else:
            super().mouseDoubleClickEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# SpecialDragButton — QToolButton con drag-drop para botones especiales
# ─────────────────────────────────────────────────────────────────────────────

class SpecialDragButton(QToolButton):
    """
    QToolButton que acepta drag-drop de nombres desde NamesListWidget,
    para los botones especiales: Wheelchair (128), Second Room (129)
    y Chairman (preset 1).

    Comportamiento:
    - Al soltar un nombre encima: muestra el nombre, borde verde, emite name_assigned.
    - Doble-tap con nombre asignado: confirmación + restaura el label original.
    - Sin nombre: comportamiento de click normal (preset).
    - Participa en la exclusividad de nombres de MainWindow igual que GoButton.

    DIFERENCIA CON GoButton:
    - Hereda de QToolButton (necesario para icono arriba + texto abajo).
    - El texto mostrado al asignar nombre reemplaza solo el label,
      no el número de asiento (no hay número visible en estos botones).
    - El label original se guarda en _default_label para restaurarlo al borrar.

    SEÑAL name_assigned(int, str):
      Misma firma que GoButton: (seat_id, name). seat_id es la clave usada
      en seat_names.json (128, 129, o la clave de Chairman).
      name="" indica borrado de asignación.
    """

    name_assigned = pyqtSignal(int, str)

    def __init__(self, seat_id: int, default_label: str, parent=None):
        super().__init__(parent)
        self.seat_number   = seat_id        # clave para seat_names.json
        self._default_label = default_label  # texto a restaurar al borrar ("Wheelchair", etc.)
        self.assigned_name  = ""
        self.setText(default_label)          # texto inicial visible
        self.setAcceptDrops(True)

    # ── API pública ───────────────────────────────────────────────────────────

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Asigna o borra el nombre.
        Con nombre: muestra el nombre truncado + borde verde.
        Sin nombre: restaura _default_label + estilo original.
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
        """Borde verde sobre el estilo base del botón cuando hay nombre asignado."""
        base = self.styleSheet()
        # Inyecta borde verde y fondo tenue sin sobreescribir el resto del estilo.
        # Se guarda el estilo original en _base_style la primera vez.
        if not hasattr(self, '_base_style'):
            self._base_style = base
        self.setStyleSheet(
            self._base_style.replace(
                "border: 0px solid black;",
                "border: 2px solid #2e7d32; background-color: rgba(76,175,80,30);"
            ).replace(
                "border: none;",
                "border: 2px solid #2e7d32; background-color: rgba(76,175,80,30);"
            )
        )

    def _apply_default_style(self):
        """Restaura el estilo sin borde de asignación."""
        if hasattr(self, '_base_style'):
            self.setStyleSheet(self._base_style)

    # ── Drag-drop ─────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        name = event.mimeData().text().strip()
        if name:
            self.set_name(name)
            event.acceptProposedAction()

    # ── Doble-tap para borrar ─────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        if self.assigned_name:
            reply = QMessageBox.question(
                self.parent(), "Clear Assignment",
                f'Clear "{self.assigned_name}" from {self._default_label}?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.set_name("")
        else:
            super().mouseDoubleClickEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# NamesListWidget — lista de consejeros con doble modo de arrastre
# ─────────────────────────────────────────────────────────────────────────────

class NamesListWidget(QListWidget):
    """
    Lista de consejeros que soporta dos tipos de drag simultáneamente:

    1. REORDENAMIENTO INTERNO: arrastra un nombre arriba/abajo dentro del panel.
       Detectado porque event.source() == self.
       Se gestiona manualmente para poder emitir order_changed y sincronizar
       self.names en NamesPanel.

    2. ARRASTRE EXTERNO (a GoButton): arrastra un nombre fuera del panel
       y suéltalo sobre un asiento para asignarlo.
       Usa MIME text/plain con CopyAction → el ítem permanece en la lista.

    SEÑAL order_changed(list):
      Emitida tras cada reordenamiento. NamesPanel la conecta para
      sincronizar self.names y persistir en seat_names.json.
    """

    order_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        # DragDrop manual: NO usamos InternalMove de Qt porque necesitamos
        # control sobre el MIME type (text/plain para GoButton) y sobre
        # la emisión de order_changed tras cada reordenamiento.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)  # optimiza renderizado al ser todos iguales

        self._dragging_row: int | None = None

        # Cuando True, dropEvent ignora drops internos (reordenamiento bloqueado).
        # El drag externo hacia GoButton no se ve afectado: GoButton gestiona
        # su propio dropEvent independientemente de este flag.
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

    # ── Drag: inicio ──────────────────────────────────────────────────────────

    def startDrag(self, supported_actions):
        """
        Override para:
        1. Guardar _dragging_row → dropEvent lo usa para reordenar.
        2. Poner el nombre como text/plain → GoButton.dropEvent lo acepta.
        3. CopyAction: el ítem permanece en la lista tras soltar sobre GoButton.
        """
        item = self.currentItem()
        if item is None:
            return
        self._dragging_row = self.row(item)

        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(item.text())  # text/plain para GoButton
        drag.setMimeData(mime)

        # Ghost visual: captura el ítem renderizado en pantalla
        rect = self.visualItemRect(item)
        drag.setPixmap(self.viewport().grab(rect))
        drag.setHotSpot(QtCore.QPoint(rect.width() // 2, rect.height() // 2))

        drag.exec_(Qt.CopyAction | Qt.MoveAction)
        self._dragging_row = None

    # ── Drag: recepción interna ───────────────────────────────────────────────

    def dragEnterEvent(self, event):
        """
        Solo acepta drags de esta misma lista (reorden interno).
        Rechaza drops externos para evitar que nombres de GoButton
        se peguen accidentalmente en la lista.
        """
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
        """
        Reordenamiento interno: extrae el ítem de origen e inserta en destino.
        Emite order_changed con la lista completa para que NamesPanel
        sincronice self.names y llame al callback de persistencia.
        """
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
    Panel semitransparente posicionado en la franja libre entre el área
    de asientos (max x≈1322) y el panel PTZ (x=1500).

    Geometría: x=1325, y=55, w=160, h=960

    on_changed_cb — Callable de MainWindow:
      Firma: on_changed_cb(old_name=None, new_name=None)
      sin args → lista cambia por añadir/borrar
      con args → renombrado; MainWindow actualiza GoButtons afectados
    """

    PX, PY, PW, PH = 1325, 55, 160, 960

    def __init__(self, names_list: list, on_changed_cb, clear_all_cb, parent=None):
        super().__init__(parent)
        self.names       = names_list
        self._on_changed = on_changed_cb
        # Callback para limpiar todos los asientos — ejecutado en MainWindow
        # porque NamesPanel no tiene acceso directo a los GoButtons.
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

        # CAMBIO: título unificado a "Attendees".
        # Antes mostraba "👥 Attendees", pero el tooltip del botón BtnNames
        # decía "Attendees panel". Dos términos para el mismo concepto.
        # MOTIVO: consistencia de UX — el operador debe ver siempre el mismo nombre.
        title = QLabel("👥 Attendees")
        title.setStyleSheet("font: bold 12px; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Drag to seat\nDouble-tap to clear")
        hint.setStyleSheet("font: 9px; color: #666;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # Lista reordenable — ocupa la mayor parte del panel
        self._list = NamesListWidget()
        self._list.order_changed.connect(self._on_order_changed)
        layout.addWidget(self._list, stretch=1)

        # Botones de gestión apilados verticalmente
        _btn_style = (
            "QPushButton { background: white; border: 1px solid #bbb;"
            " border-radius: 3px; font: bold 11px; padding: 3px 4px; text-align: left; }"
            "QPushButton:pressed  { background: #ddd; }"
            "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
        )

        # Add/Edit/Delete: deshabilitados en modo Call (solo activos en modo Set)
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

        # "Clear All": también deshabilitado en modo Call (acción destructiva).
        # MOTIVO: requiere que el operador cambie a Set deliberadamente.
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

        # Conjunto de nombres actualmente asignados a asientos.
        # Mantenido por MainWindow vía set_assigned().
        self._assigned: set = set()

        self._rebuild()
        self.set_edit_mode(False)  # Call es el modo por defecto

    # ── Control de modo edición ──────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        """
        Habilita o deshabilita la edición según el modo Call/Set.

        Modo Call (enabled=False):
          - Botones Add/Edit/Delete/Clear All deshabilitados visualmente.
          - Reordenamiento por drag dentro de la lista bloqueado.
          - El drag de nombre hacia un GoButton sigue funcionando.

        Modo Set (enabled=True): todo habilitado.
        """
        self._list._reorder_locked = not enabled
        for btn in self._edit_buttons:
            btn.setEnabled(enabled)

    # ── Sincronización de la lista ────────────────────────────────────────────

    def set_assigned(self, assigned: set):
        """
        Actualiza el conjunto de nombres asignados y refresca la lista visible.
        Un nombre asignado desaparece del panel; al liberarse, vuelve a aparecer.
        """
        self._assigned = assigned
        self._rebuild()

    def _rebuild(self):
        """
        Recarga NamesListWidget mostrando solo los nombres NO asignados.
        Llamar tras add/edit/delete y tras cualquier cambio de asignaciones.
        """
        visible = [n for n in self.names if n not in self._assigned]
        self._list.populate(visible)

    def _on_order_changed(self, new_order: list):
        """
        Slot de NamesListWidget.order_changed.
        Reconstruye self.names in-place intercalando los asignados en su
        posición original para no perder ningún nombre de la lista maestra.
        """
        visible_iter = iter(new_order)
        reconstructed = [
            name if name in self._assigned else next(visible_iter)
            for name in self.names
        ]
        self.names[:] = reconstructed  # in-place: mantiene referencia compartida
        self._on_changed()

    # ── CRUD de la lista ──────────────────────────────────────────────────────

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
        Libera todos los nombres de todos los asientos.
        MOTIVO: operación habitual al inicio de sesión para resetear la sala.
        MainWindow ejecuta el borrado real; aquí solo confirmamos y disparamos
        el callback — el panel se actualiza cuando MainWindow llama set_assigned({}).
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
      0°  → Abajo      90°  → Izquierda
      180° → Arriba    270° → Derecha

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