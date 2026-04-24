#!/usr/bin/env python3
# login_screen.py — Pantalla de autenticación con auditoría y animaciones

from __future__ import annotations

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont
from datetime import datetime
from pathlib import Path
from json_io import load_json, save_json

from config import Contact
from secret_manager import decrypt_password as _get_password


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
        QTimer.singleShot(0, self._check_schedule_bypass)

    def _check_schedule_bypass(self):
        """Auto-login si la hora actual está dentro del horario configurado."""
        try:
            from schedule_config import is_within_schedule
            if is_within_schedule():
                self.login_successful.emit()
        except Exception:
            pass  # Si falla la lectura del schedule, pedir contraseña normalmente

    def _build_ui(self):
        """Construir interfaz de usuario."""
        layout = QVBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(400, 250, 400, 250)
        
        # Título
        title = QLabel('DublinISL Controls')
        title.setFont(QFont('Inter Tight', 48, QFont.Bold))
        title.setStyleSheet("color: #1A3318;")
        title.setAlignment(Qt.AlignCenter)
        title.setMinimumHeight(80)
        layout.addWidget(title)

        # Subtítulo
        subtitle = QLabel('Restricted Access')
        subtitle.setFont(QFont('Inter Tight', 28))
        subtitle.setStyleSheet("color: #2E5229;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(80)

        # Etiqueta de contraseña
        pwd_label = QLabel('Password:')
        pwd_label.setFont(QFont('Inter Tight', 20, QFont.Bold))
        pwd_label.setStyleSheet("color: #1A3318;")
        layout.addWidget(pwd_label)

        # Campo de contraseña
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText('Enter password')
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFont(QFont('Inter Tight', 18))
        self.password_input.setStyleSheet("""
            QLineEdit {
                background-color: #EBEBEB;
                color: #1A3318;
                border: 2px solid #4A7A44;
                border-radius: 5px;
                padding: 10px;
            }
            QLineEdit:focus {
                border: 2px solid #2E5229;
            }
        """)
        self.password_input.setMinimumHeight(60)
        # Ejecutar verificación al presionar Enter
        self.password_input.returnPressed.connect(self._verify_password)
        layout.addWidget(self.password_input)

        layout.addSpacing(40)

        # Botón de login
        self.login_btn = QPushButton('ACCESS')
        self.login_btn.setFont(QFont('Inter Tight', 20, QFont.Bold))
        self.login_btn.setMinimumHeight(70)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E5229;
                color: #FFFFFF;
                border: 2px solid #2E5229;
                border-radius: 8px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #1A3318;
            }
            QPushButton:pressed {
                background-color: #0F1F0F;
            }
        """)
        self.login_btn.clicked.connect(self._verify_password)
        layout.addWidget(self.login_btn)

        # Botón de ayuda / contacto
        self.help_btn = QPushButton('? HELP')
        self.help_btn.setFont(QFont('Inter Tight', 11))
        self.help_btn.setFixedHeight(32)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #2E5229;
                border: 1px solid #4A7A44;
                border-radius: 5px;
                padding: 4px 12px;
            }
            QPushButton:hover { color: #1A3318; border-color: #2E5229; }
            QPushButton:pressed { color: #0F1F0F; }
        """)
        self.help_btn.clicked.connect(self._show_help)
        layout.addWidget(self.help_btn, alignment=Qt.AlignRight)

        layout.addSpacing(40)

        # Etiqueta de estado
        self.status_label = QLabel('Enter password')
        self.status_label.setFont(QFont('Inter Tight', 14))
        self.status_label.setStyleSheet(
            "QLabel { color: #2E5229; background: transparent; border-radius: 8px; padding: 8px 16px; }"
        )
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
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
            self.status_label.setText('✗ Password required')
            self.status_label.setStyleSheet(
                "QLabel { color: #B84F00; background: #FFF3E6;"
                " border: 1px solid rgba(184,79,0,0.30);"
                " border-radius: 8px; padding: 8px 16px; }"
            )
            return
        
        # Comparar con contraseña correcta
        if pwd == _get_password():
            self._on_login_success()
        else:
            self._on_login_failure(pwd)
    
    def _on_login_success(self):
        """Manejar login exitoso."""
        self.password_input.clear()
        self.status_label.setText('✓ Access granted')
        self.status_label.setStyleSheet(
            "QLabel { color: #1B7F3E; background: #EAF6EE;"
            " border: 1px solid rgba(27,127,62,0.30);"
            " border-radius: 8px; padding: 8px 16px; }"
        )
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
            
            self.status_label.setText(
                f'⏱ Locked for {lockout_seconds}s ({self.attempts} attempts)'
            )
            self.status_label.setStyleSheet(
                "QLabel { color: #C0141F; background: #FCECEA;"
                " border: 1px solid rgba(192,20,31,0.30);"
                " border-radius: 8px; padding: 8px 16px; }"
            )
            
            # Iniciar countdown
            self._start_lockout_timer(lockout_seconds)
        else:
            # Permitir reintento inmediato
            remaining = 10 - self.attempts
            self.status_label.setText(
                f'✗ Wrong password ({remaining} attempts left)'
            )
            self.status_label.setStyleSheet(
                "QLabel { color: #B84F00; background: #FFF3E6;"
                " border: 1px solid rgba(184,79,0,0.30);"
                " border-radius: 8px; padding: 8px 16px; }"
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
                self.status_label.setText(f'⏱ Locked for {self.remaining_seconds}s')
            else:
                # Desbloquear cuando termine
                self.is_locked = False
                self.password_input.setEnabled(True)
                self.login_btn.setEnabled(True)
                self.status_label.setText('✓ Unlock complete - retry')
                self.status_label.setStyleSheet(
                    "QLabel { color: #1B7F3E; background: #EAF6EE;"
                    " border: 1px solid rgba(27,127,62,0.30);"
                    " border-radius: 8px; padding: 8px 16px; }"
                )
                self.password_input.setFocus()
                # Detener timer
                self.lockout_timer.stop()
        
        # Ejecutar actualización cada segundo
        self.lockout_timer.timeout.connect(update_countdown)
        self.lockout_timer.start(1000)