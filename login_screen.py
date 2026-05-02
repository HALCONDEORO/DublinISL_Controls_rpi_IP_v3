#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# login_screen.py — Pantalla de autenticación con auditoría y animaciones

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QFrame, QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette
from datetime import datetime
from pathlib import Path
from json_io import load_json, save_json

from config import Contact
from secret_manager import decrypt_password as _get_password, PasswordNotConfiguredError, password_is_configured


# ═══════════════════════════════════════════════════════════════════════════════
#  AUDITORÍA DE LOGIN
# ═══════════════════════════════════════════════════════════════════════════════

class LoginAudit:
    """Auditoría de intentos de login y detección de ataques."""

    def __init__(self, log_file: str = "audit_log.json"):
        self.log_file = Path(log_file)
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Crear archivo de log si no existe."""
        if not self.log_file.exists():
            try:
                self.log_file.write_text("[]", encoding='utf-8')
            except OSError:
                pass

    def log_attempt(self, success: bool, attempts: int = 0,
                    lockout_seconds: int = 0, attempted_password: str = "") -> bool:
        """Registrar intento de login."""
        # Crear entrada de auditoría con timestamp
        entry = {
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "attempts": attempts,
            "lockout_seconds": lockout_seconds,
            "event_type": "login_success" if success else "login_failure",
        }
        if not success and attempted_password:
            entry["attempted_password"] = attempted_password

        try:
            # Leer logs existentes
            logs = self._read_logs()
            logs.append(entry)

            # Mantener solo últimas 1000 entradas
            if len(logs) > 1000:
                logs = logs[-1000:]

            return save_json(self.log_file, logs)

        except (OSError, TypeError):
            return False

    def _read_logs(self) -> list:
        """Leer logs existentes de forma segura."""
        data = load_json(self.log_file, default=[])
        return data if isinstance(data, list) else []

    def detect_suspicious_activity(self) -> dict:
        """Detectar patrones de ataque (>20 fallos/hora = riesgo alto)."""
        logs = self._read_logs()
        # Si no hay logs, retornar estado seguro
        if not logs:
            return {
                "attack_detected": False,
                "failed_attempts_last_hour": 0,
                "risk_level": "low",
                "recommendation": "No activity recorded"
            }

        now = datetime.now()
        failures_last_hour = 0

        # Contar fallos en la última hora
        for log in reversed(logs):
            try:
                ts = datetime.fromisoformat(log.get("timestamp", ""))
                # Si el log es más viejo que 1 hora, parar
                if (now - ts).total_seconds() > 3600:
                    break
                # Contar si fue un fallo
                if not log.get("success", False):
                    failures_last_hour += 1
            except (KeyError, ValueError):
                continue

        # Determinar nivel de riesgo
        if failures_last_hour > 20:
            risk = "high"
            rec = "CRITICAL: Possible attack. Consider blocking."
        elif failures_last_hour > 10:
            risk = "medium"
            rec = "WARNING: Multiple failures detected."
        else:
            risk = "low"
            rec = "OK: Normal activity."

        return {
            "attack_detected": risk == "high",
            "failed_attempts_last_hour": failures_last_hour,
            "risk_level": risk,
            "recommendation": rec
        }



# ═══════════════════════════════════════════════════════════════════════════════
#  PANTALLA DE LOGIN
# ═══════════════════════════════════════════════════════════════════════════════

class LoginScreen(QWidget):
    """
    Panel de login embebido en MainWindow.
    - Bloqueo progresivo (0s, 10s, 30s, 60s, 3600s)
    - Auditoría de todos los intentos
    - Detección de ataques
    """

    login_successful = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("QWidget { background-color: #DCDCDC; }")

        # Atributos
        self.attempts = 0
        self.max_attempts = 10
        self.is_locked = False
        self.lockout_timer = None
        self.remaining_seconds = 0

        # Horarios de bloqueo: 0, 0, 10s, 10s, 30s, 30s, 60s, 60s, 3600s, 3600s
        self.lockout_schedule = [0, 0, 10, 10, 30, 30, 60, 60, 3600, 3600]

        # Sistema de auditoría
        # self.audit = LoginAudit()

        self._build_ui()
        QTimer.singleShot(0, self._check_password_configured)
        QTimer.singleShot(0, self._check_schedule_bypass)

    def _check_password_configured(self):
        """Block login with a clear message if no valid password is configured."""
        if not password_is_configured():
            self.password_input.setEnabled(False)
            self.login_btn.setEnabled(False)
            self._set_status(
                '⚠ No password configured — run: python3 setup_password.py',
                'error'
            )

    def _check_schedule_bypass(self):
        """Auto-login si la hora actual está dentro del horario configurado."""
        try:
            from schedule_config import is_within_schedule
            if is_within_schedule():
                self.login_successful.emit()
        except Exception:
            pass  # Si falla la lectura del schedule, pedir contraseña normalmente

    def _build_ui(self):
        """Construir interfaz de usuario con card centrada."""
        # ── Outer layout: centra la card en pantalla ───────────────────────────
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        # ── Card blanca ────────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("LoginCard")
        card.setFixedWidth(580)
        card.setStyleSheet(
            "QFrame#LoginCard { background-color: #FFFFFF; border-radius: 20px; border: none; }"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 20)
        shadow.setColor(QColor(0, 0, 0, 36))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(56, 52, 56, 48)
        card_layout.setSpacing(0)

        # ── Logo mark ─────────────────────────────────────────────────────────
        logo_wrap = QHBoxLayout()
        logo_mark = QFrame()
        logo_mark.setObjectName("LogoMark")
        logo_mark.setFixedSize(64, 64)
        logo_mark.setStyleSheet(
            "QFrame#LogoMark {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "    stop:0 #4A7A44, stop:1 #1A3318);"
            "  border-radius: 16px; border: none;"
            "}"
        )
        logo_lbl = QLabel('ISL', logo_mark)
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setGeometry(0, 0, 64, 64)
        logo_lbl.setStyleSheet(
            "QLabel { color: rgba(255,255,255,200); font: 700 18px 'Inter Tight', 'Segoe UI';"
            " background: transparent; border: none; }"
        )
        logo_shadow = QGraphicsDropShadowEffect()
        logo_shadow.setBlurRadius(24)
        logo_shadow.setOffset(0, 4)
        logo_shadow.setColor(QColor(26, 51, 24, 90))
        logo_mark.setGraphicsEffect(logo_shadow)
        logo_wrap.addStretch()
        logo_wrap.addWidget(logo_mark)
        logo_wrap.addStretch()
        card_layout.addLayout(logo_wrap)
        card_layout.addSpacing(20)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel('DublinISL Controls')
        title.setStyleSheet(
            "QLabel {"
            "  font: 700 36px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #1A3318;"
            "  background: transparent;"
            "  border: none;"
            "  letter-spacing: -1px;"
            "}"
        )
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)
        card_layout.addSpacing(8)

        # ── Subtitle ──────────────────────────────────────────────────────────
        subtitle = QLabel('Restricted Access')
        subtitle.setStyleSheet(
            "QLabel {"
            "  font: 400 19px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #2E5229;"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(44)

        # ── Password label ────────────────────────────────────────────────────
        pwd_label = QLabel('Password')
        pwd_label.setStyleSheet(
            "QLabel {"
            "  font: 600 15px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #444444;"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        card_layout.addWidget(pwd_label)
        card_layout.addSpacing(10)

        # ── Password input ────────────────────────────────────────────────────
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText('Enter password')
        self.password_input.setEchoMode(QLineEdit.Password)
        input_font = QFont('Segoe UI', 18)
        self.password_input.setFont(input_font)
        self.password_input.setAlignment(Qt.AlignCenter)
        self.password_input.setStyleSheet("""
            QLineEdit {
                background-color: #FAFAFA;
                border: 2px solid #4A7A44;
                border-radius: 8px;
                padding: 0 20px;
            }
            QLineEdit:focus {
                border: 2px solid #2E5229;
                background-color: #FFFFFF;
            }
        """)
        # Color de texto y placeholder via paleta (el QSS no define color,
        # así Qt respeta QPalette.PlaceholderText para el hint)
        pal = self.password_input.palette()
        pal.setColor(QPalette.Text, QColor(0x11, 0x11, 0x11))
        pal.setColor(QPalette.PlaceholderText, QColor(160, 160, 160))
        self.password_input.setPalette(pal)
        self.password_input.setMinimumHeight(64)
        self.password_input.returnPressed.connect(self._verify_password)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(12)

        # ── Status label ──────────────────────────────────────────────────────
        self.status_label = QLabel('')
        self.status_label.setFont(QFont('Inter Tight', 13))
        self.status_label.setStyleSheet(
            "QLabel { color: transparent; background: transparent;"
            " border: none; border-radius: 8px; padding: 10px 14px; }"
        )
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setMinimumHeight(44)
        card_layout.addWidget(self.status_label)
        card_layout.addSpacing(8)

        # ── ACCESS button — gradiente ─────────────────────────────────────────
        self.login_btn = QPushButton('ACCESS')
        self.login_btn.setFont(QFont('Inter Tight', 20, QFont.Bold))
        self.login_btn.setMinimumHeight(80)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4A7A44, stop:1 #1A3318);
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3A6A34, stop:1 #0F1F0F);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2E5229, stop:1 #0A1408);
            }
            QPushButton:disabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #B0B0B0, stop:1 #888888);
                color: rgba(255,255,255,160);
            }
        """)
        self.login_btn.clicked.connect(self._verify_password)
        card_layout.addWidget(self.login_btn)
        card_layout.addSpacing(28)

        # ── Footer: help ──────────────────────────────────────────────────────
        self.help_btn = QPushButton('? Help')
        self.help_btn.setFont(QFont('Inter Tight', 13))
        self.help_btn.setFixedHeight(28)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #4A7A44;
                border: none;
                padding: 0;
            }
            QPushButton:hover { color: #2E5229; }
            QPushButton:pressed { color: #1A3318; }
        """)
        self.help_btn.clicked.connect(self._show_help)
        card_layout.addWidget(self.help_btn, alignment=Qt.AlignLeft)

        outer.addWidget(card, alignment=Qt.AlignVCenter)
        outer.addStretch()

        # Auto-focus en campo de contraseña
        self.password_input.setFocus()

    def _show_help(self):
        QMessageBox.information(self, 'For Technical Assistance', Contact, QMessageBox.Ok)

    def _verify_password(self):
        """Verificar contraseña ingresada."""
        # No hacer nada si está bloqueado
        if self.is_locked:
            return

        pwd = self.password_input.text()

        # Validar que no esté vacía
        if not pwd:
            self._set_status('✗ Password required', 'warning')
            return

        # Comparar con contraseña correcta
        try:
            correct = _get_password()
        except PasswordNotConfiguredError:
            self.password_input.setEnabled(False)
            self.login_btn.setEnabled(False)
            self._set_status(
                '⚠ No password configured — run: python3 setup_password.py',
                'error'
            )
            return

        if pwd == correct:
            self._on_login_success()
        else:
            self._on_login_failure(pwd)

    # ── Status helper ──────────────────────────────────────────────────────────

    def _set_status(self, text: str, variant: str):
        """Actualiza status_label con el variant visual correcto."""
        styles = {
            'warning': (
                "QLabel { color: #B84F00; background: #FFF3E6;"
                " border: 1px solid rgba(184,79,0,0.30);"
                " border-radius: 8px; padding: 10px 14px; }"
            ),
            'error': (
                "QLabel { color: #C0141F; background: #FCECEA;"
                " border: 1px solid rgba(192,20,31,0.30);"
                " border-radius: 8px; padding: 10px 14px; }"
            ),
            'success': (
                "QLabel { color: #1B7F3E; background: #EAF6EE;"
                " border: 1px solid rgba(27,127,62,0.30);"
                " border-radius: 8px; padding: 10px 14px; }"
            ),
            'hidden': (
                "QLabel { color: transparent; background: transparent;"
                " border: none; border-radius: 8px; padding: 10px 14px; }"
            ),
        }
        self.status_label.setText(text)
        self.status_label.setStyleSheet(styles.get(variant, styles['hidden']))

    # ── Login logic ────────────────────────────────────────────────────────────

    def _on_login_success(self):
        """Manejar login exitoso."""
        self.password_input.clear()
        self._set_status('✓ Access granted', 'success')
        self.login_btn.setEnabled(False)
        self.password_input.setEnabled(False)

        # Registrar éxito en auditoría
        # self.audit.log_attempt(success=True, attempts=0, lockout_seconds=0)

        # Animar fade out
        self._animate_fade_out()

    def _animate_fade_out(self):
        """
        Transición login → splash: emite la señal directamente.
        (Como widget embebido, la ocultación la gestiona MainWindow.)
        """
        self.login_successful.emit()

    def _on_login_failure(self, attempted_password: str = ""):
        """Manejar login fallido con bloqueo progresivo."""
        self.attempts += 1
        self.password_input.clear()

        # Obtener duración de bloqueo según número de intentos
        lockout_seconds = self.lockout_schedule[min(self.attempts - 1, 9)]

        # Registrar intento fallido en auditoría (incluye contraseña intentada)
        # self.audit.log_attempt(
        #     success=False,
        #     attempts=self.attempts,
        #     lockout_seconds=lockout_seconds,
        #     attempted_password=attempted_password,
        # )

        # Verificar si hay patrón de ataque
        # suspicious = self.audit.detect_suspicious_activity()
        # if suspicious["attack_detected"]:
        #     # Alertar sobre posible ataque
        #     print(f"[LOGIN SECURITY] {suspicious['recommendation']}")

        if lockout_seconds > 0:
            # Aplicar bloqueo temporal
            self.is_locked = True
            self.password_input.setEnabled(False)
            self.login_btn.setEnabled(False)

            self._set_status(
                f'⏱ Locked for {lockout_seconds}s ({self.attempts} attempts)',
                'error'
            )
            # Iniciar countdown
            self._start_lockout_timer(lockout_seconds)
        else:
            # Permitir reintento inmediato
            remaining = 10 - self.attempts
            self._set_status(
                f'✗ Wrong password ({remaining} attempts left)',
                'warning'
            )
            self.password_input.setFocus()

    def _start_lockout_timer(self, seconds: int):
        """Countdown de bloqueo temporal."""
        self.lockout_timer = QTimer()
        self.remaining_seconds = seconds

        def update_countdown():
            """Decrementar contador cada segundo."""
            self.remaining_seconds -= 1

            if self.remaining_seconds > 0:
                self._set_status(f'⏱ Locked for {self.remaining_seconds}s', 'error')
            else:
                # Desbloquear cuando termine
                self.is_locked = False
                self.password_input.setEnabled(True)
                self.login_btn.setEnabled(True)
                self._set_status('✓ Unlock complete — retry', 'success')
                self.password_input.setFocus()
                # Detener timer
                self.lockout_timer.stop()

        # Ejecutar actualización cada segundo
        self.lockout_timer.timeout.connect(update_countdown)
        self.lockout_timer.start(1000)
