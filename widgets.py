#!/usr/bin/env python3
# widgets.py — Widgets personalizados de la UI
#
# Responsabilidad única: definir componentes visuales reutilizables
# que no contienen lógica de negocio (no saben nada de VISCA ni de presets).
#
# Widgets incluidos:
#   GoButton         — botón de asiento numerado con drag-drop y nombre asignado
#   NamesListWidget  — QListWidget con reordenamiento interno + arrastre externo a GoButton
#   NamesPanel       — panel flotante compacto con lista editable de consejeros
#   make_arrow_btn   — helper para crear botones de dirección con icono rotado
#
# CAMBIO RESPECTO A VERSIÓN ANTERIOR:
#   NameTag (QLabel arrastrable) eliminado. Sustituido por NamesListWidget
#   que unifica en un solo widget:
#     - Reordenamiento interno (drag arriba/abajo dentro del panel)
#     - Arrastre externo (drag a GoButton para asignar asiento)
#   Esto elimina el QScrollArea + layout manual de NameTags, simplificando
#   NamesPanel considerablemente.

import os

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from config import BUTTON_COLOR


# ─────────────────────────────────────────────────────────────────────────────
#  GoButton — botón de asiento numerado con drag-drop y nombre asignado
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
        self.seat_number   = int(seat_number)   # int explícito: evita bugs si llega str
        self.assigned_name = ""
        self.resize(self.WIDTH, self.HEIGHT)
        self.setAcceptDrops(True)
        self._apply_style()

    # ── Estilo ────────────────────────────────────────────────────────────────

    def _apply_style(self):
        """
        Borde verde si hay nombre asignado → feedback visual de asiento ocupado.
        Falla silenciosamente a color sólido si falta seat.svg.
        """
        bg = "background-image: url(seat.svg);" if os.path.exists("seat.svg") \
             else "background-color: #cccccc;"
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
                self.parent(), "Borrar asignación",
                f'¿Borrar "{self.assigned_name}" del asiento {self.seat_number}?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.set_name("")
        else:
            super().mouseDoubleClickEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
#  NamesListWidget — lista de consejeros con doble modo de arrastre
# ─────────────────────────────────────────────────────────────────────────────

class NamesListWidget(QListWidget):
    """
    Lista de consejeros que soporta dos tipos de drag simultáneamente:

    1. REORDENAMIENTO INTERNO: arrastra un nombre arriba o abajo para
       cambiar su posición en la lista. Se detecta porque event.source() == self.
       Se gestiona manualmente en dropEvent para poder emitir order_changed
       y sincronizar self.names en NamesPanel.

    2. ARRASTRE EXTERNO (a GoButton): arrastra un nombre fuera del panel
       y suéltalo sobre un botón de asiento para asignar el nombre.
       Usa MIME text/plain con CopyAction → el ítem permanece en la lista.

    DISEÑO:
    - startDrag(): registra _dragging_row, construye QDrag con text/plain.
    - dragEnterEvent/dragMoveEvent: solo aceptan drags internos (source==self),
      rechazando drops externos no deseados en la lista.
    - dropEvent: gestiona el reordenamiento manualmente y emite order_changed.

    SEÑAL order_changed(list):
      Emitida tras cada reordenamiento. NamesPanel la conecta para
      sincronizar self.names y persistir en seat_names.json.
    """

    order_changed = pyqtSignal(list)  # nuevo orden completo de nombres tras reordenar

    def __init__(self, parent=None):
        super().__init__(parent)
        # DragDrop manual: NO usamos InternalMove de Qt porque necesitamos
        # control sobre el MIME type (text/plain para GoButton) y sobre
        # la emisión de order_changed tras cada reordenamiento.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)    # indicador visual de posición de drop
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)      # optimiza renderizado al ser todos iguales
        self._dragging_row: int | None = None
        # Cuando True, dropEvent ignora drops internos (reordenamiento bloqueado).
        # El drag externo hacia GoButton sigue funcionando porque GoButton gestiona
        # su propio dropEvent — este flag no le afecta.
        self._reorder_locked = False
        self.setStyleSheet("""
            QListWidget {
                background: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #eee;
                font: bold 12px;
                color: #222;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                color: #1565C0;
                border-bottom-color: #bbdefb;
            }
            QListWidget::item:hover:!selected {
                background: #f1f8e9;
            }
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
        mime.setText(item.text())                           # text/plain para GoButton
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
        Reordenamiento interno: saca el ítem de origen e inserta en destino.
        Emite order_changed con la lista completa para que NamesPanel
        sincronice self.names y llame al callback de persistencia.
        """
        if event.source() is not self or self._dragging_row is None:
            event.ignore()
            return

        # Bloqueo de reordenamiento: modo Call activo → ignorar drops internos.
        # El drag hacia GoButton ya terminó antes de llegar aquí (source != self),
        # por lo que este check no afecta la asignación de nombres a asientos.
        if self._reorder_locked:
            event.ignore()
            return

        target_item = self.itemAt(event.pos())
        target_row  = self.row(target_item) if target_item else self.count() - 1
        src_row     = self._dragging_row

        if src_row == target_row:
            event.ignore()
            return

        # Reordenar: extraer e insertar en nueva posición
        text = self.item(src_row).text()
        self.takeItem(src_row)
        self.insertItem(target_row, QListWidgetItem(text))
        self.setCurrentRow(target_row)

        # Notificar nuevo orden completo → NamesPanel sincroniza y persiste
        self.order_changed.emit([self.item(i).text() for i in range(self.count())])
        event.acceptProposedAction()


# ─────────────────────────────────────────────────────────────────────────────
#  NamesPanel — panel flotante compacto con lista editable de consejeros
# ─────────────────────────────────────────────────────────────────────────────

class NamesPanel(QWidget):
    """
    Panel semitransparente compacto posicionado en el espacio entre el área
    de controles superior y la primera fila de asientos (que empieza en y=210).

    Geometría: x=320, y=55, w=416, h=152  →  termina en y=207 (< y=210 ✓)

    Layout interior (vertical):
      ┌─ título/instrucciones ────────────────────────────────────┐
      │  NamesListWidget (scrollable, drag-to-reorder)            │
      │  [＋  Añadir consejero ]                                  │
      │  [✏   Editar nombre   ]                                   │
      │  [🗑   Borrar de lista ]                                   │
      └───────────────────────────────────────────────────────────┘

    El botón de apertura/cierre (👥) vive en MainWindow en la esquina
    superior derecha del panel (x=PX+PW-40, y=PY) para que sea visible
    incluso cuando el panel está oculto.

    on_changed_cb — Callable de MainWindow:
      Firma: on_changed_cb(old_name=None, new_name=None)
        sin args → lista cambia por añadir/borrar
        con args → renombrado; MainWindow actualiza GoButtons afectados
    """

    # Geometría del panel — franja libre entre asientos (max x≈1322) y PTZ panel (x=1500).
    # Ancho 160px cabe justo en ese espacio. Altura 960px cubre toda la zona de asientos.
    PX, PY, PW, PH = 1325, 55, 160, 960

    def __init__(self, names_list: list, on_changed_cb, parent=None):
        super().__init__(parent)
        self.names       = names_list       # referencia compartida con MainWindow
        self._on_changed = on_changed_cb

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

        # ── Título (panel estrecho: texto corto centrado)
        title = QLabel("👥 Consejeros")
        title.setStyleSheet("font: bold 12px; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Instrucción breve en dos líneas por el ancho reducido
        hint = QLabel("Arrastra a asiento\nDoble-tap para borrar")
        hint.setStyleSheet("font: 9px; color: #666;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # ── Lista reordenable — ocupa la mayor parte del panel
        self._list = NamesListWidget()
        # Sin fixedHeight: se expande para aprovechar los 960px de altura
        self._list.order_changed.connect(self._on_order_changed)
        layout.addWidget(self._list, stretch=1)

        # ── Botones de gestión apilados verticalmente
        # Etiquetas cortas para caber en 150px de ancho interior.
        # El estado deshabilitado (modo Call) se indica visualmente mediante CSS.
        _btn_style = (
            "QPushButton { background: white; border: 1px solid #bbb; "
            "border-radius: 3px; font: bold 11px; padding: 3px 4px; text-align: left; }"
            "QPushButton:pressed { background: #ddd; }"
            "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
        )
        self._edit_buttons = []
        for label, slot in [
            ("＋ Añadir",  self._add_name),
            ("✏ Editar",   self._edit_name),
            ("🗑 Borrar",   self._delete_name),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setStyleSheet(_btn_style)
            b.clicked.connect(slot)
            layout.addWidget(b)
            self._edit_buttons.append(b)

        # Conjunto de nombres actualmente asignados a asientos.
        # Mantenido por MainWindow vía set_assigned(). _rebuild() lo usa para
        # filtrar la lista visible: un nombre asignado no aparece en el panel.
        self._assigned: set = set()

        # Estado inicial: se sincroniza con BtnCall/BtnSet desde MainWindow
        # tras la construcción. Call es el modo por defecto → edición bloqueada.
        self._rebuild()
        self.set_edit_mode(False)   # desactiva edición hasta que el operador ponga Set

    # ── Control de modo edición ──────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        """
        Habilita o deshabilita la edición de la lista según el modo Call/Set.

        Modo Call (enabled=False):
          - Los botones Añadir/Editar/Borrar quedan deshabilitados visualmente.
          - El reordenamiento por drag dentro de la lista queda bloqueado
            (NamesListWidget._reorder_locked = True).
          - El drag de nombre hacia un GoButton sigue funcionando: el operador
            puede seguir asignando nombres a asientos en modo Call.

        Modo Set (enabled=True):
          - Todo habilitado: CRUD completo + reordenamiento.

        MainWindow llama a este método al cambiar BtnCall/BtnSet.
        """
        self._list._reorder_locked = not enabled
        for btn in self._edit_buttons:
            btn.setEnabled(enabled)

    # ── Sincronización de la lista ────────────────────────────────────────────

    def set_assigned(self, assigned: set):
        """
        Actualiza el conjunto de nombres asignados a asientos y refresca la lista.
        MainWindow llama a este método cada vez que cambia una asignación de asiento
        (drag a GoButton o borrado con doble-tap).

        Un nombre en `assigned` desaparece del panel — ya está "usado" en un asiento.
        Cuando se libera el asiento (assigned pierde ese nombre), vuelve a aparecer.
        """
        self._assigned = assigned
        self._rebuild()

    def _rebuild(self):
        """
        Recarga NamesListWidget mostrando solo los nombres NO asignados.
        Los nombres asignados a asientos no aparecen aquí: visualmente están
        "en el asiento", no en la lista de disponibles.
        Llamar tras add/edit/delete y tras cualquier cambio de asignaciones.
        NO llamar tras reorden interno (_on_order_changed lo gestiona).
        """
        visible = [n for n in self.names if n not in self._assigned]
        self._list.populate(visible)

    def _on_order_changed(self, new_order: list):
        """
        Slot de NamesListWidget.order_changed.
        new_order contiene solo los nombres VISIBLES (no asignados) en su nuevo orden.
        Reconstruye self.names in-place intercalando los asignados en su posición
        original para no perder ningún nombre de la lista maestra.

        Algoritmo: recorre self.names; los nombres asignados se mantienen en su
        posición; los no asignados se reemplazan por el nuevo orden visible.
        """
        visible_iter = iter(new_order)
        reconstructed = [
            name if name in self._assigned else next(visible_iter)
            for name in self.names
        ]
        self.names[:] = reconstructed   # in-place: mantiene referencia compartida con MainWindow
        self._on_changed()

    # ── CRUD de la lista ──────────────────────────────────────────────────────

    def _add_name(self):
        text, ok = QInputDialog.getText(self, "Añadir nombre", "Nombre completo:")
        if not (ok and text.strip()):
            return
        name = text.strip()
        if name in self.names:
            QMessageBox.information(self, "Nombre duplicado", f'"{name}" ya existe.')
            return
        self.names.append(name)
        self._on_changed()
        self._rebuild()

    def _edit_name(self):
        if not self.names:
            return
        old_name, ok = QInputDialog.getItem(
            self, "Editar nombre", "Seleccionar consejero:", self.names, 0, False)
        if not ok:
            return
        new_name, ok2 = QInputDialog.getText(
            self, "Editar nombre", "Nuevo nombre:", text=old_name)
        if not (ok2 and new_name.strip()):
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self.names:
            QMessageBox.information(self, "Nombre duplicado", f'"{new_name}" ya existe.')
            return
        self.names[self.names.index(old_name)] = new_name
        self._on_changed(old_name=old_name, new_name=new_name)
        self._rebuild()

    def _delete_name(self):
        if not self.names:
            return
        name, ok = QInputDialog.getItem(
            self, "Borrar nombre", "Seleccionar:", self.names, 0, False)
        if not ok:
            return
        reply = QMessageBox.question(
            self, "Confirmar borrado",
            f'¿Borrar "{name}" de la lista?\n'
            "(Los asientos asignados conservan el nombre hasta borrarlo con doble-tap.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.names.remove(name)
            self._on_changed()
            self._rebuild()


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: make_arrow_btn
# ─────────────────────────────────────────────────────────────────────────────

def make_arrow_btn(parent, x: int, y: int, degrees: int) -> QPushButton:
    """
    Crea un QPushButton con angle.png rotado a los grados indicados.

    BASELINE: angle.png apunta hacia ABAJO (0°). La rotación es horaria:
        0°   → Abajo        90°  → Izquierda
        180° → Arriba       270° → Derecha

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