#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# splash_screen.py — Pantalla de inicialización

from __future__ import annotations

import socket
import binascii
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from camera_discovery import get_camera_subnet, tcp_scan, arp_scan
from data_paths import SCHEDULE_FILE

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt5.QtGui import (
    QFont, QPainter, QColor, QRadialGradient, QPen, QBrush, QLinearGradient
)

from config import CAM1, CAM2, SOCKET_TIMEOUT, VISCA_PORT, SEAT_POSITIONS, ATEMAddress
import sim_mode as _sim_mode


# ═══════════════════════════════════════════════════════════════════════════════
#  RASTREO DE RESULTADOS DE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestResult:
    """Rastrear resultado individual de test y timing."""

    def __init__(self, name: str):
        self.name = name
        self.start_time = time.time()
        self.success = False
        self.error_msg: Optional[str] = None
        self.duration_ms = 0

    def finish(self, success: bool, error: Optional[str] = None):
        self.success = success
        self.error_msg = error
        self.duration_ms = int((time.time() - self.start_time) * 1000)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error_msg,
            "timestamp": datetime.now().isoformat()
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  ESTADÍSTICAS DE BOOTS
# ═══════════════════════════════════════════════════════════════════════════════

class BootStatistics:
    """Rastrear historial de boots para monitoreo de salud del sistema."""

    def __init__(self, stats_file: str = "boot_stats.json"):
        self.stats_file = Path(stats_file)
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.stats_file.exists():
            try:
                self.stats_file.write_text("[]", encoding='utf-8')
            except OSError:
                pass

    # def record_boot(self, duration_ms: int, tests_passed: int, total_tests: int) -> bool:
    #     entry = {
    #         "timestamp": datetime.now().isoformat(),
    #         "duration_ms": duration_ms,
    #         "tests_passed": tests_passed,
    #         "total_tests": total_tests,
    #         "success": tests_passed == total_tests
    #     }
    #     try:
    #         stats = self._read_stats()
    #         stats.append(entry)
    #         if len(stats) > 100:
    #             stats = stats[-100:]
    #         self.stats_file.write_text(json.dumps(stats, indent=2), encoding='utf-8')
    #         return True
    #     except (OSError, json.JSONDecodeError, TypeError):
    #         return False

    def _read_stats(self) -> list:
        try:
            if not self.stats_file.exists():
                return []
            data = json.loads(self.stats_file.read_text(encoding='utf-8'))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return []

    def get_summary(self) -> dict:
        stats = self._read_stats()
        if not stats:
            return {}
        successful = sum(1 for s in stats if s.get("success", False))
        avg_duration = int(sum(s.get("duration_ms", 0) for s in stats) / len(stats))
        success_rate = successful / len(stats) * 100
        return {
            "total_boots": len(stats),
            "successful": successful,
            "success_rate": f"{success_rate:.1f}%",
            "avg_duration_ms": avg_duration,
            "last_boot": stats[-1].get("timestamp", "")
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  TICKER DE TESTS — lista rodante una línea por resultado
# ═══════════════════════════════════════════════════════════════════════════════

class TestTickerWidget(QWidget):
    """
    Muestra los resultados de los tests como filas individuales que van
    apareciendo desde abajo con una animación de deslizamiento.
    Cada fila: nombre alineado a la izquierda, marca ✓/✗ a la derecha.
    """

    _ROW_H    = 20   # altura de cada fila en píxeles
    _MAX_ROWS = 4    # filas visibles simultáneamente
    _STEPS    = 6    # pasos de la animación slide-in

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self.setFixedHeight(self._MAX_ROWS * self._ROW_H)
        self._entries: list[tuple[str, bool]] = []
        self._slide = 0   # desplazamiento vertical actual de la animación

        self._timer = QTimer(self)
        self._timer.setInterval(18)   # ~55 fps
        self._timer.timeout.connect(self._advance)

    def add_result(self, name: str, success: bool):
        self._entries.append((name, success))
        self._slide = self._ROW_H          # nueva entrada empieza fuera de vista (abajo)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _advance(self):
        if self._slide > 0:
            self._slide = max(0, self._slide - 3)
            self.update()
        else:
            self._timer.stop()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipRect(0, 0, self.width(), self.height())

        font = QFont('IBM Plex Mono', 11)
        p.setFont(font)

        # Mostrar las últimas MAX_ROWS+1 entradas (una extra para la animación)
        visible = self._entries[-(self._MAX_ROWS + 1):]
        n = len(visible)

        for idx, (name, success) in enumerate(visible):
            rows_from_bottom = n - 1 - idx   # 0 = más reciente (abajo)
            y = self.height() - (rows_from_bottom + 1) * self._ROW_H + self._slide

            if y + self._ROW_H < 0:
                continue   # salió por arriba

            # Opacidad: la más reciente brilla, las antiguas se atenúan
            age = rows_from_bottom
            alpha = 210 if age == 0 else max(45, 160 - age * 38)

            row_rect = QRect(0, y, self.width(), self._ROW_H)

            # Nombre — izquierda
            p.setPen(QColor(255, 255, 255, alpha))
            p.drawText(row_rect, Qt.AlignLeft | Qt.AlignVCenter, name)

            # Marca — derecha
            if success:
                p.setPen(QColor(35, 170, 70, alpha))
                p.drawText(row_rect, Qt.AlignRight | Qt.AlignVCenter, '✓')
            else:
                p.setPen(QColor(190, 35, 35, alpha))
                p.drawText(row_rect, Qt.AlignRight | Qt.AlignVCenter, '✗')

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  PANTALLA DE SPLASH
# ═══════════════════════════════════════════════════════════════════════════════

class SplashScreen(QWidget):
    """
    Pantalla de inicialización con tests paralelos y carga adaptativa.

    Siempre emite startup_complete al terminar, con o sin cámaras.
    startup_failed se conserva para errores verdaderamente fatales (no usados
    actualmente; el flujo de main.py ya no los requiere).
    """

    startup_complete = pyqtSignal()

    # Señales internas para actualizar UI de forma thread-safe.
    # Qt enruta señales emitidas desde hilos de fondo al hilo principal
    # automáticamente con conexión QueuedConnection.
    _sig_log        = pyqtSignal(str)
    _sig_status     = pyqtSignal(str, str)   # mensaje, color
    _sig_progress   = pyqtSignal(int)        # 0-100
    _sig_cam_update = pyqtSignal(int, str)   # cam_idx (1/2), estado
    _sig_ticker     = pyqtSignal(str, bool)  # nombre_corto, éxito

    # Estilos por estado de cámara
    _CAM_STATE = {
        'connecting': {
            'border': 'rgba(212,134,10,0.30)',
            'bg':     'rgba(212,134,10,0.05)',
            'led':    '#D4860A',
            'glow':   (212, 134, 10),
            'text':   '#D4860A',
            'label':  'Connecting...',
        },
        'connected': {
            'border': 'rgba(35,170,70,0.30)',
            'bg':     'rgba(35,170,70,0.06)',
            'led':    '#23AA46',
            'glow':   (35, 170, 70),
            'text':   '#23AA46',
            'label':  'Connected',
        },
        'disconnected': {
            'border': 'rgba(190,35,35,0.30)',
            'bg':     'rgba(190,35,35,0.05)',
            'led':    '#BE2323',
            'glow':   (190, 35, 35),
            'text':   '#BE2323',
            'label':  'No response',
        },
    }


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)

        self.tests_passed    = 0
        self.tests_total     = 0
        self.test_results: dict = {}
        self.boot_start_time = time.time()
        self.diagnostic_mode = False
        self._cam1_status    = 'connecting'
        self._cam2_status    = 'connecting'
        self._led_pulse_on   = True

        self.boot_stats = BootStatistics()

        self._build_ui()

        # Conectar señales internas → slots en hilo principal
        self._sig_log.connect(self._do_log)
        self._sig_status.connect(self._do_status)
        self._sig_progress.connect(self.progress_bar.setValue)
        self._sig_cam_update.connect(self._do_cam_update)
        self._sig_ticker.connect(self._do_ticker)   # str, bool

        # Pulso para LEDs en estado "connecting"
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_leds)
        self._pulse_timer.start(600)

    # ─────────────────────────────────────────────────────────────────────────
    #  BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Fondo sólido #1A1F19
        p.fillRect(0, 0, w, h, QColor(0x1A, 0x1F, 0x19))

        # Radial verde suave centrado (70% × 60% del canvas, a 50% / 40%)
        glow = QRadialGradient(w * 0.50, h * 0.40, max(w, h) * 0.55)
        glow.setColorAt(0.0, QColor(46, 82, 41, 76))   # rgba 0.30
        glow.setColorAt(1.0, QColor(46, 82, 41, 0))
        p.fillRect(0, 0, w, h, QBrush(glow))

        # Radial verde oscuro, esquina inferior-izquierda
        accent = QRadialGradient(w * 0.20, h * 0.80, max(w, h) * 0.38)
        accent.setColorAt(0.0, QColor(26, 51, 24, 51))  # rgba 0.20
        accent.setColorAt(1.0, QColor(26, 51, 24, 0))
        p.fillRect(0, 0, w, h, QBrush(accent))

        # Grid 80×80 px, rgba(255,255,255,0.015)
        grid_pen = QPen(QColor(255, 255, 255, 4))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for x in range(0, w, 80):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 80):
            p.drawLine(0, y, w, y)

        p.end()

    # ─────────────────────────────────────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Contenido central ─────────────────────────────────────────────
        center = QWidget()
        center.setFixedWidth(620)
        center.setAttribute(Qt.WA_TranslucentBackground)
        col = QVBoxLayout(center)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.setAlignment(Qt.AlignHCenter)

        # Logo (88×88, gradiente verde, border-radius 22px)
        logo = QLabel('ISL')
        logo.setFixedSize(88, 88)
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(QFont('Inter Tight', 22, QFont.Bold))
        logo.setStyleSheet(
            "QLabel {"
            "  color: rgba(255,255,255,0.85);"
            "  background: qlineargradient(x1:0.15,y1:0,x2:0.85,y2:1,"
            "    stop:0 #4A7A44, stop:1 #1A3318);"
            "  border-radius: 22px;"
            "  border: 1px solid rgba(255,255,255,0.10);"
            "  letter-spacing: 3px;"
            "}"
        )
        logo_glow = QGraphicsDropShadowEffect(logo)
        logo_glow.setBlurRadius(28)
        logo_glow.setColor(QColor(35, 170, 70, 90))
        logo_glow.setOffset(0, 0)
        logo.setGraphicsEffect(logo_glow)
        logo_row = QHBoxLayout()
        logo_row.addStretch()
        logo_row.addWidget(logo)
        logo_row.addStretch()
        col.addSpacing(80)
        col.addLayout(logo_row)
        col.addSpacing(32)

        # Título — 52px bold, tracking -.04em, sin wrap
        title = QLabel('DublinISL Controls')
        title.setFont(QFont('Inter Tight', 52, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; background: transparent; letter-spacing: -2px;")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(False)
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        col.addWidget(title)
        col.addSpacing(12)

        # Subtítulo — 22px, 40% opacidad
        self.subtitle_label = QLabel('Initializing camera connections...')
        self.subtitle_label.setFont(QFont('Inter Tight', 18))
        self.subtitle_label.setStyleSheet(
            "color: rgba(255,255,255,102); background: transparent;"
        )
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self.subtitle_label)
        col.addSpacing(72)

        # Tarjetas de cámara (280px c/u, gap 24px)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        cards_row.setContentsMargins(0, 0, 0, 0)
        self._cam1_card = self._make_cam_card(
            1, 'Camera 1', 'Platform', 'Chairman / Lectern area', CAM1.ip, 'connecting'
        )
        self._cam2_card = self._make_cam_card(
            2, 'Camera 2', 'Comments', 'Auditorium seating area', CAM2.ip, 'connecting'
        )
        cards_row.addWidget(self._cam1_card)
        cards_row.addWidget(self._cam2_card)
        col.addLayout(cards_row)
        col.addSpacing(56)

        # Barra de progreso (400px, 3px)
        bar_wrap = QWidget()
        bar_wrap.setFixedWidth(440)
        bar_wrap.setAttribute(Qt.WA_TranslucentBackground)
        bar_col = QVBoxLayout(bar_wrap)
        bar_col.setContentsMargins(0, 0, 0, 0)
        bar_col.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 2px;
                background-color: rgba(255,255,255,18);
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2E5229, stop:0.5 #4A7A44, stop:1 #23AA46);
                border-radius: 2px;
            }
        """)
        self.progress_bar.setValue(0)
        bar_col.addWidget(self.progress_bar)

        # Ticker de tests — lista rodante con animación slide-in
        self.ticker_widget = TestTickerWidget()
        bar_col.addWidget(self.ticker_widget)

        bar_row = QHBoxLayout()
        bar_row.addStretch()
        bar_row.addWidget(bar_wrap)
        bar_row.addStretch()
        col.addLayout(bar_row)

        # Buffer interno para el log (no visible)
        self.log_label = QLabel('')
        self.log_label.hide()
        col.addWidget(self.log_label)

        root.addStretch()
        root.addWidget(center, 0, Qt.AlignHCenter)
        root.addStretch()

        # ── Footer absoluto ───────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(48, 0, 48, 36)
        org_lbl = QLabel('Dublin Islamic Society, Ireland')
        org_lbl.setFont(QFont('Inter Tight', 13))
        org_lbl.setStyleSheet("color: rgba(255,255,255,51); background: transparent;")
        ver_lbl = QLabel('v2.0 · rpi')
        ver_lbl.setFont(QFont('IBM Plex Mono', 12))
        ver_lbl.setStyleSheet("color: rgba(255,255,255,46); background: transparent;")
        footer.addWidget(org_lbl)
        footer.addStretch()
        footer.addWidget(ver_lbl)
        root.addLayout(footer)

    def _make_cam_card(self, cam_idx: int, cam_label: str, name: str,
                       subtitle: str, ip: str, status: str) -> QFrame:
        card = QFrame()
        card.setObjectName("cam_card")
        card.setFrameShape(QFrame.NoFrame)
        card.setFrameShadow(QFrame.Plain)
        card.setLineWidth(0)
        card.setMidLineWidth(0)
        card.setFixedSize(300, 188)
        self._style_card(card, status)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)

        # ── Encabezado: etiqueta de cámara (izq) + LED (der) ──────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        mode_lbl = QLabel(cam_label.upper())
        mode_lbl.setFont(QFont('Inter Tight', 11, QFont.Bold))
        mode_lbl.setStyleSheet(
            "color: rgba(255,255,255,89); background: transparent; letter-spacing: 3px;"
        )
        led = QLabel()
        led.setFixedSize(14, 14)
        self._style_led(led, status)
        header.addWidget(mode_lbl)
        header.addStretch()
        header.addWidget(led)
        layout.addLayout(header)
        layout.addSpacing(14)

        # ── Nombre + subtítulo ─────────────────────────────────────────────
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont('Inter Tight', 22, QFont.Bold))
        name_lbl.setStyleSheet("color: rgba(255,255,255,217); background: transparent;")
        layout.addWidget(name_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setFont(QFont('Inter Tight', 13))
        sub_lbl.setStyleSheet("color: rgba(255,255,255,89); background: transparent;")
        layout.addWidget(sub_lbl)
        layout.addSpacing(10)

        # ── IP ────────────────────────────────────────────────────────────
        ip_lbl = QLabel(ip)
        ip_lbl.setFont(QFont('IBM Plex Mono', 12))
        ip_lbl.setStyleSheet(
            "color: rgba(255,255,255,64);"
            "background: rgba(255,255,255,13);"
            "padding: 4px 10px;"
            "border-radius: 6px;"
        )
        layout.addWidget(ip_lbl)
        layout.addSpacing(10)

        # ── Fila de estado ─────────────────────────────────────────────────
        status_lbl = QLabel(self._CAM_STATE[status]['label'])
        status_lbl.setFont(QFont('Inter Tight', 13, QFont.Medium))
        self._style_status_text(status_lbl, status)
        layout.addWidget(status_lbl)

        # Guardar referencias
        if cam_idx == 1:
            self._cam1_led        = led
            self._cam1_status_lbl = status_lbl
            self._cam1_card_ref   = card
        else:
            self._cam2_led        = led
            self._cam2_status_lbl = status_lbl
            self._cam2_card_ref   = card

        return card

    # ── Helpers de estilo ─────────────────────────────────────────────────

    def _style_card(self, card: QFrame, status: str):
        st = self._CAM_STATE.get(status, self._CAM_STATE['connecting'])
        # Selector con objectName para que el borde NO se propague a los
        # QLabel hijos (QLabel hereda QFrame en Qt, así que un selector
        # genérico "QFrame {}" les aplica a ellos también).
        card.setStyleSheet(
            f"QFrame#cam_card {{"
            f"  background: {st['bg']};"
            f"  border: 1px solid {st['border']};"
            f"  border-radius: 16px;"
            f"}}"
        )

    def _style_led(self, led: QLabel, status: str, dimmed: bool = False):
        st = self._CAM_STATE.get(status, self._CAM_STATE['connecting'])
        color = st['led']
        r, g, b = st['glow']
        led.setStyleSheet(
            f"QLabel {{"
            f"  background: {color};"
            f"  border-radius: 7px;"
            f"}}"
        )
        effect = QGraphicsDropShadowEffect(led)
        effect.setOffset(0, 0)
        if dimmed:
            effect.setBlurRadius(6)
            effect.setColor(QColor(r, g, b, 80))
        else:
            effect.setBlurRadius(12)
            effect.setColor(QColor(r, g, b, 160))
        led.setGraphicsEffect(effect)

    def _style_status_text(self, lbl: QLabel, status: str):
        st = self._CAM_STATE.get(status, self._CAM_STATE['connecting'])
        lbl.setStyleSheet(f"color: {st['text']}; background: transparent;")

    # ── Pulso LED ─────────────────────────────────────────────────────────

    def _pulse_leds(self):
        self._led_pulse_on = not self._led_pulse_on
        for cam_idx in (1, 2):
            status = self._cam1_status if cam_idx == 1 else self._cam2_status
            if status == 'connecting':
                led = self._cam1_led if cam_idx == 1 else self._cam2_led
                self._style_led(led, 'connecting', dimmed=not self._led_pulse_on)

    # ─────────────────────────────────────────────────────────────────────────
    #  Slots de UI (siempre en hilo principal)
    # ─────────────────────────────────────────────────────────────────────────

    def _do_log(self, message: str):
        """Actualizar log — llamado sólo desde el hilo principal vía señal."""
        current = self.log_label.text()
        lines = (current + message + "\n").split('\n')
        # Mantener solo las últimas 20 líneas para no desbordar el label
        if len(lines) > 20:
            lines = lines[-20:]
        self.log_label.setText('\n'.join(lines))

    def _do_status(self, message: str, color: str):
        """Actualizar etiqueta de estado — llamado sólo desde el hilo principal."""
        colors = {"green": "rgba(35,170,70,0.7)", "yellow": "#F5A623", "red": "rgba(190,35,35,0.7)"}
        self.subtitle_label.setText(message)
        self.subtitle_label.setStyleSheet(
            f"color: {colors.get(color, 'rgba(255,255,255,102)')}; background: transparent;"
        )

    def _do_cam_update(self, cam_idx: int, status: str):
        """Actualizar tarjeta de cámara — llamado sólo desde el hilo principal."""
        if cam_idx == 1:
            self._cam1_status = status
            card = self._cam1_card_ref
            led  = self._cam1_led
            lbl  = self._cam1_status_lbl
        else:
            self._cam2_status = status
            card = self._cam2_card_ref
            led  = self._cam2_led
            lbl  = self._cam2_status_lbl

        self._style_card(card, status)
        self._style_led(led, status)
        self._style_status_text(lbl, status)
        lbl.setText(self._CAM_STATE.get(status, self._CAM_STATE['connecting'])['label'])

    def _do_ticker(self, name: str, success: bool):
        """Añadir resultado al ticker rodante."""
        self.ticker_widget.add_result(name, success)

    # ─────────────────────────────────────────────────────────────────────────
    #  API pública para hilos de fondo (emiten señales, nunca tocan widgets)
    # ─────────────────────────────────────────────────────────────────────────

    def _update_log(self, message: str):
        self._sig_log.emit(message)

    def _update_status(self, message: str, color: str = "white"):
        self._sig_status.emit(message, color)

    def _update_progress(self, value: int):
        self._sig_progress.emit(value)

    # ─────────────────────────────────────────────────────────────────────────
    #  Teclado
    # ─────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            self.diagnostic_mode = True
            self._update_log("DIAGNOSTIC MODE ACTIVATED")
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    #  INICIALIZACIÓN (hilo de fondo)
    # ─────────────────────────────────────────────────────────────────────────

    def _start_initialization(self):
        threading.Thread(target=self._startup_cameras, daemon=True).start()
        thread = threading.Thread(target=self._run_initialization, daemon=True)
        thread.start()

    def _startup_cameras(self):
        """Enciende ambas cámaras y las lleva a Home (igual que el botón Start Session)."""
        self._power_on_camera(CAM1.ip, CAM1.cam_id)
        self._power_on_camera(CAM2.ip, CAM2.cam_id)
        time.sleep(8)
        self._home_camera(CAM1.ip, CAM1.cam_id)
        self._home_camera(CAM2.ip, CAM2.cam_id)

    def _run_initialization(self):
        """
        Ejecuta todos los tests en paralelo.
        Siempre emite startup_complete al finalizar (con o sin errores).
        """
        tests = [
            ("Operating System",       self._test_os),
            ("Network Connectivity",   self._test_network),
            ("Camera 1 (Platform)",    self._test_camera1),
            ("Camera 2 (Audience)",    self._test_camera2),
            ("Configuration",          self._test_config),
            ("Statistics",             self._test_statistics),
            ("Focus & Exposure Cam1",  self._test_focus_exposure_cam1),
            ("Focus & Exposure Cam2",  self._test_focus_exposure_cam2),
            ("ATEM Switcher",          self._test_atem),
            ("Data Files",             self._test_data_files),
            ("TCP Scan (cameras)",     self._test_tcp_scan),
            ("ARP Table",              self._test_arp_table),
        ]
        self.tests_total = len(tests)

        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self._run_single_test, name, func): name
                    for name, func in tests
                }
                for future in as_completed(futures):
                    test_name = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"success": False, "error": str(exc), "duration_ms": 0}
                    self._process_test_result(test_name, result)

            # # Estadísticas de boot
            # duration_ms = int((time.time() - self.boot_start_time) * 1000)
            # self.boot_stats.record_boot(duration_ms, self.tests_passed, self.tests_total)

            # # Resumen de tiempos
            # self._update_log("\nTEST DURATION SUMMARY:")
            # for name, result in self.test_results.items():
            #     status = "OK" if result.get("success") else "FAIL"
            #     self._update_log(f"  [{status}] {name}: {result.get('duration_ms', 0)}ms")
            # self._update_log(f"\nTotal: {duration_ms}ms")

            # summary = self.boot_stats.get_summary()
            # if summary:
            #     self._update_log(
            #         f"\nBoots: {summary['total_boots']} | "
            #         f"OK: {summary['success_rate']} | "
            #         f"Avg: {summary['avg_duration_ms']}ms"
            #     )

            # Estado final
            if self.tests_passed == self.tests_total:
                self._update_log("\nAll tests passed")
                self._update_status(f"Ready ({self.tests_passed}/{self.tests_total})", "green")
            else:
                self._update_status(
                    f"{self.tests_passed}/{self.tests_total} tests passed — continuing",
                    "yellow"
                )
                self._update_log(f"\n{self.tests_passed}/{self.tests_total} passed. Continuing...")

            time.sleep(3 if _sim_mode.is_active() else 1)

        except Exception as exc:
            self._update_log(f"\nWarning during initialization: {exc}")
            self._update_status("Starting with warnings...", "yellow")
            time.sleep(3 if _sim_mode.is_active() else 1)

        finally:
            # Siempre continuar: las cámaras no son requisito para arrancar
            self.startup_complete.emit()

    def _run_single_test(self, name: str, test_func) -> dict:
        """
        Ejecuta un test con hasta 3 reintentos (backoff exponencial).
        Solo reintenta si lanza excepción; False se acepta como resultado.
        En modo simulación añade un retardo por test para que el ticker
        sea legible y el splash no desaparezca de inmediato.
        """
        result = TestResult(name)
        max_retries = 3
        backoff_ms  = 100

        for attempt in range(1, max_retries + 1):
            try:
                success = test_func()
                result.finish(success)
                if _sim_mode.is_active():
                    time.sleep(0.45)
                return result.to_dict()
            except Exception as exc:
                if attempt < max_retries:
                    wait = backoff_ms * (2 ** (attempt - 1)) / 1000
                    self._update_log(f"  retry {name} ({int(wait*1000)}ms)...")
                    time.sleep(wait)
                else:
                    result.finish(False, str(exc))
                    if _sim_mode.is_active():
                        time.sleep(0.45)
                    return result.to_dict()

        return result.to_dict()

    # Nombres cortos para el ticker
    _TICKER_SHORT = {
        "Operating System":      "OS",
        "Network Connectivity":  "Net",
        "Camera 1 (Platform)":   "Cam1",
        "Camera 2 (Audience)":   "Cam2",
        "Configuration":         "Config",
        "Statistics":            "Stats",
        "Focus & Exposure Cam1": "Focus1",
        "Focus & Exposure Cam2": "Focus2",
        "ATEM Switcher":         "ATEM",
        "Data Files":            "Files",
        "TCP Scan (cameras)":    "TCP",
        "ARP Table":             "ARP",
    }

    def _process_test_result(self, test_name: str, result: dict):
        """Procesar resultado de un test completado."""
        self.test_results[test_name] = result

        if result.get("success"):
            self._update_log(f"  OK  {test_name} ({result.get('duration_ms', 0)}ms)")
            self.tests_passed += 1
        else:
            error = result.get("error") or ""
            suffix = f" — {error}" if error else ""
            self._update_log(f"  --  {test_name}{suffix}")

        # Ticker
        short = self._TICKER_SHORT.get(test_name, test_name[:6])
        self._sig_ticker.emit(short, bool(result.get("success")))

        # Actualizar tarjetas de cámara
        cam_status = 'connected' if result.get('success') else 'disconnected'
        if 'Camera 1' in test_name:
            self._sig_cam_update.emit(1, cam_status)
        elif 'Camera 2' in test_name:
            self._sig_cam_update.emit(2, cam_status)

        progress = int(len(self.test_results) / self.tests_total * 100)
        self._update_progress(progress)

    # ─────────────────────────────────────────────────────────────────────────
    #  TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def _send_visca_cmd(self, ip: str, cam_id: str, cmd: str) -> bool:
        """Envía un comando VISCA y devuelve True si la cámara responde."""
        try:
            full_cmd = cam_id + cmd
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(binascii.unhexlify(full_cmd))
                data = sock.recv(64)
                return len(data) > 0
        except Exception:
            return False

    def _test_focus_exposure_cam1(self) -> bool:
        """
        Verifica que los comandos de foco y exposición llegan correctamente a Cam1.
        Envía Auto Focus, Brightness Up y Backlight ON.
        """
        af_ok = self._send_visca_cmd(CAM1.ip, CAM1.cam_id, "01043802FF")  # Auto Focus
        br_ok = self._send_visca_cmd(CAM1.ip, CAM1.cam_id, "01040D02FF")  # Brightness Up
        bl_ok = self._send_visca_cmd(CAM1.ip, CAM1.cam_id, "01043302FF")  # Backlight ON
        return af_ok and br_ok and bl_ok

    def _test_focus_exposure_cam2(self) -> bool:
        """
        Verifica que los comandos de foco y exposición llegan correctamente a Cam2.
        Envía Auto Focus y Brightness Up.
        """
        af_ok = self._send_visca_cmd(CAM2.ip, CAM2.cam_id, "01043802FF")  # Auto Focus
        br_ok = self._send_visca_cmd(CAM2.ip, CAM2.cam_id, "01040D02FF")  # Brightness Up
        return af_ok and br_ok

    def _test_atem(self) -> bool:
        """Verifica conectividad TCP con el ATEM Switcher (puerto 9910)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                return sock.connect_ex((ATEMAddress, 9910)) == 0
        except OSError:
            return False

    def _test_data_files(self) -> bool:
        """Verifica que seat_names.json y schedule.json son legibles y JSON válido."""
        from config import NAMES_FILE
        names_ok = True
        try:
            if NAMES_FILE.exists():
                json.loads(NAMES_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            names_ok = False

        sched_ok = True
        try:
            if SCHEDULE_FILE.exists():
                json.loads(SCHEDULE_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            sched_ok = False

        return names_ok and sched_ok

    def _test_os(self) -> bool:
        import platform
        return bool(platform.system())

    def _test_network(self) -> bool:
        socket.gethostbyname('localhost')
        return True

    def _test_camera1(self) -> bool:
        return self._test_camera(CAM1.ip, CAM1.cam_id)

    def _test_camera2(self) -> bool:
        return self._test_camera(CAM2.ip, CAM2.cam_id)

    def _test_camera(self, ip: str, cam_id: str) -> bool:
        """
        Prueba conexión TCP con una cámara y la enciende si responde.
        Usa context manager para garantizar que el socket se cierra aunque
        connect_ex lance OSError (evita leak de file descriptors).
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                connected = sock.connect_ex((ip, VISCA_PORT)) == 0
        except OSError:
            return False

        if connected:
            self._power_on_camera(ip, cam_id)
        return connected

    def _test_config(self) -> bool:
        return all([CAM1.ip, CAM1.cam_id, CAM2.ip, CAM2.cam_id, SEAT_POSITIONS])

    def _test_statistics(self) -> bool:
        self.boot_stats._ensure_file_exists()
        return self.boot_stats.stats_file.exists()

    # ─────────────────────────────────────────────────────────────────────────
    #  HELPERS DE CÁMARA
    # ─────────────────────────────────────────────────────────────────────────

    def _power_on_camera(self, ip: str, cam_id: str):
        """Envía comando VISCA Power On. Falla silenciosamente."""
        try:
            cmd = cam_id + "01040002FF"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(binascii.unhexlify(cmd))
                sock.recv(64)
        except Exception:
            pass

    def _home_camera(self, ip: str, cam_id: str):
        """Envía comando VISCA Home. Falla silenciosamente."""
        try:
            cmd = cam_id + "010604FF"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(binascii.unhexlify(cmd))
                sock.recv(64)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    #  DESCUBRIMIENTO DE CÁMARAS  (lógica en camera_discovery.py)
    # ─────────────────────────────────────────────────────────────────────────

    def _test_tcp_scan(self) -> bool:
        """
        Escanea toda la subred /24 de las cámaras en VISCA_PORT con 50 workers
        paralelos y registra los hosts que responden.
        Delega en camera_discovery.tcp_scan().
        """
        subnet = get_camera_subnet()
        self._update_log(f"  Scanning {subnet}.1-254 port {VISCA_PORT}...")
        found = tcp_scan(subnet)
        if found:
            self._update_log(f"  VISCA found: {', '.join(found)}")
        else:
            self._update_log(f"  No VISCA devices on {subnet}.x")
        return bool(found)

    def _test_arp_table(self) -> bool:
        """
        Lee la tabla ARP del sistema y registra las entradas que pertenecen
        a la subred de las cámaras.
        Delega en camera_discovery.arp_scan().
        """
        subnet = get_camera_subnet()
        unique = arp_scan(subnet)
        if unique:
            self._update_log(f"  ARP ({subnet}.x): {', '.join(unique)}")
        else:
            self._update_log(f"  ARP: no entries for {subnet}.x")
        return bool(unique)
