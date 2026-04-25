#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# schedule_dialog.py — Editor visual del calendario semanal de bypass de contraseña

from __future__ import annotations

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QCheckBox, QTimeEdit,
    QPushButton, QFrame,
)

from schedule_config import load_schedule, save_schedule, DAYS

DAY_LABELS = {
    'monday':    'Monday',
    'tuesday':   'Tuesday',
    'wednesday': 'Wednesday',
    'thursday':  'Thursday',
    'friday':    'Friday',
    'saturday':  'Saturday',
    'sunday':    'Sunday',
}


class ScheduleDialog(QDialog):
    """
    Diálogo para editar el horario semanal de auto-login.
    Durante los intervalos configurados el programa no pedirá contraseña.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Weekly Schedule')
        self.setModal(True)
        self.setFixedSize(440, 530)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(
            "ScheduleDialog {"
            "  background: white;"
            "  border: 2px solid #9e9e9e;"
            "  border-radius: 10px;"
            "}"
        )

        # Filas de widgets: {day: (checkbox, time_start, time_end)}
        self._rows: dict = {}

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        # ── Título ────────────────────────────────────────────────────────
        title = QLabel('📅  Weekly Schedule')
        title.setStyleSheet("font: bold 16px; color: #222;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel('During these times, you will not be asked for a password when logging in.')
        subtitle.setStyleSheet("font: 11px; color: #666;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ccc;")
        layout.addWidget(line)

        # ── Cabecera de columnas ──────────────────────────────────────────
        header = QHBoxLayout()
        lbl_day   = QLabel('Day')
        lbl_start = QLabel('Start')
        lbl_end   = QLabel('End')
        for lbl in (lbl_day, lbl_start, lbl_end):
            lbl.setStyleSheet("font: bold 11px; color: #555;")
        lbl_day.setFixedWidth(110)
        lbl_start.setFixedWidth(90)
        lbl_end.setFixedWidth(90)
        header.addWidget(lbl_day)
        header.addStretch()
        header.addWidget(lbl_start)
        header.addSpacing(10)
        header.addWidget(lbl_end)
        layout.addLayout(header)

        # ── Fila por día ──────────────────────────────────────────────────
        for day in DAYS:
            row = QHBoxLayout()
            row.setSpacing(8)

            chk = QCheckBox(DAY_LABELS[day])
            chk.setFixedWidth(110)
            chk.setStyleSheet("font: 13px; color: #222;")

            t_start = QTimeEdit()
            t_start.setDisplayFormat("HH:mm")
            t_start.setFixedWidth(80)
            t_start.setStyleSheet(self._time_style())

            t_end = QTimeEdit()
            t_end.setDisplayFormat("HH:mm")
            t_end.setFixedWidth(80)
            t_end.setStyleSheet(self._time_style())

            # Habilitar/deshabilitar QTimeEdit según checkbox
            def _toggle(state, ts=t_start, te=t_end):
                enabled = bool(state)
                ts.setEnabled(enabled)
                te.setEnabled(enabled)
                ts.setStyleSheet(self._time_style(enabled))
                te.setStyleSheet(self._time_style(enabled))

            chk.stateChanged.connect(_toggle)

            row.addWidget(chk)
            row.addStretch()
            row.addWidget(t_start)
            row.addWidget(QLabel('—'))
            row.addWidget(t_end)

            layout.addLayout(row)
            self._rows[day] = (chk, t_start, t_end)

        # ── Separador ─────────────────────────────────────────────────────
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("color: #ccc;")
        layout.addWidget(line2)

        # ── Botones Save / Cancel ─────────────────────────────────────────
        btn_row = QHBoxLayout()

        btn_cancel = QPushButton('Cancel')
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            "QPushButton { background: #424242; border: none; border-radius: 6px;"
            " font: bold 13px; color: white; }"
            "QPushButton:pressed { background: #212121; }"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton('Save')
        btn_save.setFixedHeight(36)
        btn_save.setStyleSheet(
            "QPushButton { background: #2e7d32; border: none; border-radius: 6px;"
            " font: bold 13px; color: white; }"
            "QPushButton:pressed { background: #1b5e20; }"
        )
        btn_save.clicked.connect(self._save)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _load_values(self):
        """Cargar valores actuales desde schedule.json."""
        schedule = load_schedule()
        for day, (chk, t_start, t_end) in self._rows.items():
            entry = schedule.get(day, {})
            enabled = entry.get("enabled", False)

            chk.setChecked(enabled)
            t_start.setEnabled(enabled)
            t_end.setEnabled(enabled)
            t_start.setStyleSheet(self._time_style(enabled))
            t_end.setStyleSheet(self._time_style(enabled))

            try:
                sh, sm = map(int, entry.get("start", "00:00").split(":"))
                eh, em = map(int, entry.get("end",   "23:59").split(":"))
            except ValueError:
                sh, sm, eh, em = 0, 0, 23, 59

            t_start.setTime(QTime(sh, sm))
            t_end.setTime(QTime(eh, em))

    def _save(self):
        """Guardar configuración y cerrar."""
        data = {}
        for day, (chk, t_start, t_end) in self._rows.items():
            data[day] = {
                "enabled": chk.isChecked(),
                "start":   t_start.time().toString("HH:mm"),
                "end":     t_end.time().toString("HH:mm"),
            }
        save_schedule(data)
        self.accept()

    @staticmethod
    def _time_style(enabled: bool = True) -> str:
        color = "#222" if enabled else "#aaa"
        bg    = "white" if enabled else "#f5f5f5"
        return (
            f"QTimeEdit {{ background: {bg}; color: {color};"
            " border: 1px solid #bbb; border-radius: 4px;"
            " font: 13px; padding: 2px 4px; }"
        )
