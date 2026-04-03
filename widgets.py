#!/usr/bin/env python3
# widgets.py — Widgets personalizados de la UI
#
# Responsabilidad única: definir componentes visuales reutilizables
# que no contienen lógica de negocio (no saben nada de VISCA ni de presets).
#
# Widgets incluidos:
#   GoButton    — botón de asiento numerado con soporte drag-drop y nombre asignado
#   NameTag     — label arrastrable con el nombre de un consejero
#   NamesPanel  — panel flotante con lista editable de consejeros
#   make_arrow_btn — helper para crear botones de dirección con icono rotado

import os

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from config import BUTTON_COLOR


# ─────────────────────────────────────────────────────────────────────────────
#  GoButton — botón de asiento numerado con drag-drop y nombre asignado
# ─────────────────────────────────────────────────────────────────────────────

class GoButton(QPushButton):
    """
    Botón de asiento (70×82 px) con tres capacidades añadidas:

    1. Nombre asignado: se puede asignar un nombre de consejero mediante
       drag-drop desde NamesPanel.  El estilo cambia a borde verde para
       indicar visualmente que el asiento está asignado.

    2. Drag-drop: acepta drops de NameTag.  Al soltar, asigna el nombre
       y emite name_assigned para que MainWindow actualice el JSON.

    3. Doble-tap para borrar: muestra confirmación y borra la asignación.

    SEÑAL name_assigned(int, str):
       Emitida en cada cambio de nombre (asignar o borrar).
       Parámetros: (numero_asiento, nombre)  —  nombre="" = borrar.
       MainWindow la conecta para persistir en seat_names.json.

    IMPORTANTE: GoButton sobreescribe cualquier setStyleSheet() posterior
    porque su estilo se aplica en __init__ a través de _apply_style().
    Por eso los botones de plataforma (Chairman/Left/Right) usan QPushButton
    plano, no GoButton.
    """

    name_assigned = pyqtSignal(int, str)  # (seat_number, name)

    WIDTH  = 70
    HEIGHT = 82

    def __init__(self, seat_number: int, parent=None):
        # Conversión explícita a int: _build_seat_buttons puede pasar int o str
        super().__init__(str(seat_number), parent)
        self.seat_number   = int(seat_number)
        self.assigned_name = ""
        self.resize(self.WIDTH, self.HEIGHT)
        self.setAcceptDrops(True)   # habilitar recepción de drops de NameTag
        self._apply_style()

    # ── Estilo dinámico ───────────────────────────────────────────────────────

    def _apply_style(self):
        """
        Regenera el stylesheet.
        Con nombre asignado: borde verde + fondo semitransparente para
        distinguir visualmente los asientos con consejero asignado.
        Sin nombre: sin borde, igual que el comportamiento original.
        """
        if os.path.exists("seat.svg"):
            bg = "background-image: url(seat.svg);"
        else:
            # Degradación si falta el asset: fondo sólido funcional
            print("[WARNING] seat.svg no encontrado — usando fondo de color")
            bg = "background-color: #cccccc;"

        if self.assigned_name:
            border = (
                "border: 2px solid #2e7d32; border-radius: 4px; "
                "background-color: rgba(76,175,80,30);"
            )
        else:
            border = "border: none;"

        self.setStyleSheet(
            f"QPushButton {{"
            f"  {bg}"
            f"  background-repeat: no-repeat;"
            f"  background-position: center;"
            f"  {border}"
            f"  font: 9px; font-weight: bold;"
            f"  color: {BUTTON_COLOR};"
            f"}}"
            f"QPushButton:pressed {{ background-color: rgba(0,0,0,70); }}"
        )

    # ── API pública ───────────────────────────────────────────────────────────

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Asigna o borra el nombre del asiento.
        Actualiza el texto del botón, el estilo visual y emite la señal.

        emit_signal=False se usa en el arranque (_restore_seat_names) para
        no disparar guardados innecesarios al cargar datos ya persistidos.
        """
        self.assigned_name = name
        if name:
            # Número de asiento arriba + nombre truncado a 10 chars abajo
            # para que quepa dentro de los 70 px de ancho del botón
            self.setText(f"{self.seat_number}\n{name[:10]}")
        else:
            self.setText(str(self.seat_number))
        self._apply_style()
        if emit_signal:
            self.name_assigned.emit(self.seat_number, name)

    # ── Drag-drop: recepción ──────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        """Acepta el drag si contiene texto plano (el nombre del NameTag)."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Mantiene el cursor de aceptación mientras el drag está encima."""
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Al soltar: asigna el nombre al asiento y notifica a MainWindow."""
        name = event.mimeData().text().strip()
        if name:
            self.set_name(name)
            event.acceptProposedAction()

    # ── Doble-tap para borrar asignación ─────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        """
        Doble-tap en asiento asignado: pide confirmación y borra el nombre.
        En asiento vacío: comportamiento Qt estándar (no hace nada especial).
        """
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
#  NameTag — label arrastrable con el nombre de un consejero
# ─────────────────────────────────────────────────────────────────────────────

class NameTag(QLabel):
    """
    Label arrastrable que vive dentro de NamesPanel.

    Al superar un umbral de 10 px inicia un QDrag con el nombre como
    MIME text/plain.  GoButton lo recibe en su dropEvent.

    Usa Qt.CopyAction: el tag permanece en la lista de NamesPanel tras
    soltar — el nombre no se "consume", puede asignarse a varios asientos.

    El umbral de 10 px evita iniciar drags accidentales en touchscreen
    (un tap normal no viaja 10 px).
    """

    def __init__(self, name: str, parent=None):
        super().__init__(name, parent)
        self.setFixedHeight(36)
        self.setStyleSheet(
            "QLabel {"
            "  background: white; border: 1px solid #aaa;"
            "  border-radius: 4px; padding: 2px 10px; font: bold 12px;"
            "}"
            "QLabel:hover { background: #e8f5e9; border-color: #4caf50; }"
        )
        self._drag_start = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()  # guardar origen para calcular distancia
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or self._drag_start is None:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 10:
            return  # umbral no superado: ignorar
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(self.text())       # nombre como text/plain → GoButton.dropEvent
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())     # imagen fantasma durante el arrastre
        drag.setHotSpot(event.pos())
        drag.exec_(Qt.CopyAction)       # CopyAction: el tag sigue en la lista


# ─────────────────────────────────────────────────────────────────────────────
#  NamesPanel — panel flotante con lista editable de consejeros
# ─────────────────────────────────────────────────────────────────────────────

class NamesPanel(QWidget):
    """
    Panel semitransparente de 310×920 px posicionado en x:1150, y:50
    (zona libre entre el plano de asientos y el panel de control PTZ).

    Responsabilidades:
      - Mostrar los NameTags arrastrables de la lista de consejeros.
      - Gestionar la lista mediante botones Añadir / Editar / Borrar.
      - Notificar a MainWindow de cualquier cambio para que persista el JSON.

    Parámetro on_changed_cb:
      Callable que MainWindow proporciona.  Se llama tras cada cambio de lista.
      Firma: on_changed_cb(old_name=None, new_name=None)
        - Sin args → solo la lista cambió (añadir/borrar).
        - Con args → renombrado: MainWindow propaga el cambio a los asientos.

    MOTIVO de posición x:1150:
      Es la zona más vacía del layout — entre los asientos (max x≈1320)
      y el panel PTZ (x≥1500).  No tapa ningún botón de asiento ni control.
    """

    def __init__(self, names_list: list, on_changed_cb, parent=None):
        super().__init__(parent)
        self.names       = names_list       # referencia compartida con MainWindow
        self._on_changed = on_changed_cb
        self.setGeometry(1155, 50, 310, 920)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "NamesPanel {"
            "  background: rgba(245,245,245,235);"
            "  border: 2px solid #888; border-radius: 8px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Título del panel
        title = QLabel("👥  Consejeros")
        title.setStyleSheet("font: bold 16px; color: #333;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Instrucciones breves visibles siempre
        hint = QLabel("Arrastra un nombre a un asiento.\nDoble-tap en asiento para borrar.")
        hint.setStyleSheet("font: 10px; color: #666; padding: 2px;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # Área scrollable donde se insertan los NameTags
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        self._container   = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()  # empuja los tags hacia arriba
        scroll.setWidget(self._container)
        layout.addWidget(scroll)

        # Botones de gestión de la lista
        _btn_style = (
            "QPushButton { background: white; border: 1px solid #aaa; "
            "border-radius: 4px; font: bold 11px; padding: 4px; }"
            "QPushButton:pressed { background: #ddd; }"
        )
        btn_row = QHBoxLayout()
        for label, slot in [
            ("+ Añadir", self._add_name),
            ("✏ Editar",  self._edit_name),
            ("🗑 Borrar",  self._delete_name),
        ]:
            b = QPushButton(label)
            b.setStyleSheet(_btn_style)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        # Botón cerrar en la parte inferior
        close_btn = QPushButton("✕  Cerrar panel")
        close_btn.setStyleSheet(
            "QPushButton { background: #e0e0e0; border: 1px solid #aaa; "
            "border-radius: 4px; font: bold 12px; padding: 6px; }"
            "QPushButton:pressed { background: #bbb; }"
        )
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        self._rebuild()

    # ── Lista de NameTags ─────────────────────────────────────────────────────

    def _rebuild(self):
        """
        Elimina todos los NameTags existentes y los recrea desde self.names.
        Mantiene el stretch al final para alinear siempre los tags arriba.
        Llamar tras cualquier cambio en la lista.
        """
        # El stretch siempre es el último item; eliminar todo lo anterior
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Insertar un NameTag por nombre en orden alfabético
        for name in sorted(self.names):
            tag = NameTag(name, self._container)
            self._list_layout.insertWidget(self._list_layout.count() - 1, tag)

    # ── Gestión de la lista ───────────────────────────────────────────────────

    def _add_name(self):
        """Añade un nombre nuevo a la lista si no existe ya."""
        text, ok = QInputDialog.getText(self, "Añadir nombre", "Nombre completo:")
        if not (ok and text.strip()):
            return
        name = text.strip()
        if name in self.names:
            QMessageBox.information(self, "Nombre duplicado",
                                    f'"{name}" ya existe en la lista.')
            return
        self.names.append(name)
        self._on_changed()
        self._rebuild()

    def _edit_name(self):
        """
        Reemplaza un nombre existente por uno nuevo.
        Llama al callback con old_name/new_name para que MainWindow
        propague el renombrado a los asientos que tenían ese nombre.
        """
        if not self.names:
            return
        old_name, ok = QInputDialog.getItem(
            self, "Editar nombre", "Seleccionar consejero:",
            sorted(self.names), 0, False,
        )
        if not ok:
            return
        new_name, ok2 = QInputDialog.getText(
            self, "Editar nombre", "Nuevo nombre:", text=old_name,
        )
        if not (ok2 and new_name.strip()):
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self.names:
            QMessageBox.information(self, "Nombre duplicado",
                                    f'"{new_name}" ya existe en la lista.')
            return
        self.names[self.names.index(old_name)] = new_name
        # Pasar old/new para que MainWindow actualice asientos asignados
        self._on_changed(old_name=old_name, new_name=new_name)
        self._rebuild()

    def _delete_name(self):
        """
        Elimina un nombre de la lista.
        Los asientos ya asignados conservan el nombre hasta borrarlo manualmente
        (doble-tap), para no alterar el estado del plano de sala en curso.
        """
        if not self.names:
            return
        name, ok = QInputDialog.getItem(
            self, "Borrar nombre", "Seleccionar:", sorted(self.names), 0, False,
        )
        if not ok:
            return
        reply = QMessageBox.question(
            self, "Confirmar borrado",
            f'¿Borrar "{name}" de la lista?\n'
            "(Los asientos ya asignados conservan el nombre hasta borrarlo manualmente.)",
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

    BASELINE: angle.png apunta hacia ABAJO (0°).  La rotación es horaria:
        0°   → Abajo        90°  → Izquierda
        180° → Arriba       270° → Derecha

    Si angle.png no existe el botón queda vacío pero funcional,
    para que la app arranque aunque falten assets.
    """
    btn = QPushButton(parent)
    btn.setGeometry(x, y, 100, 100)
    btn.setStyleSheet("border: none; background: transparent")

    if os.path.exists("angle.png"):
        pix = QPixmap("angle.png").transformed(
            QtGui.QTransform().rotate(degrees), Qt.SmoothTransformation
        )
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(90, 90))
    else:
        print(f"[WARNING] angle.png no encontrado — botón {degrees}° sin icono")

    return btn