#!/usr/bin/env python3
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

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

from config import CAM1, CAM2, SOCKET_TIMEOUT, VISCA_PORT, SEAT_POSITIONS, ATEMAddress


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
    _sig_log    = pyqtSignal(str)
    _sig_status = pyqtSignal(str, str)   # mensaje, color
    _sig_progress = pyqtSignal(int)      # 0-100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("QWidget { background-color: #000000; }")

        self.tests_passed    = 0
        self.tests_total     = 0
        self.test_results: dict = {}
        self.boot_start_time = time.time()
        self.diagnostic_mode = False

        self.boot_stats = BootStatistics()

        self._build_ui()
        # Conectar señales internas → slots en hilo principal
        self._sig_log.connect(self._do_log)
        self._sig_status.connect(self._do_status)
        self._sig_progress.connect(self.progress_bar.setValue)

    # ─────────────────────────────────────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(100, 200, 100, 200)

        title = QLabel('DublinISL Controls')
        title.setFont(QFont('Arial', 48, QFont.Bold))
        title.setStyleSheet("color: #00AA00;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel('Initializing system...')
        subtitle.setFont(QFont('Arial', 24))
        subtitle.setStyleSheet("color: #CCCCCC;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(50)

        self.log_label = QLabel('Starting tests...')
        self.log_label.setFont(QFont('Courier', 13))
        self.log_label.setStyleSheet(
            "color: #00FF00; background-color: #000000;"
            "padding: 20px; border: 2px solid #00AA00;"
        )
        self.log_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.log_label.setMinimumHeight(380)
        self.log_label.setWordWrap(True)
        layout.addWidget(self.log_label)

        layout.addSpacing(20)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #00AA00; border-radius: 5px;
                background-color: #000000; height: 30px;
            }
            QProgressBar::chunk { background-color: #00AA00; }
        """)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel('Status: initializing...')
        self.status_label.setFont(QFont('Arial', 16, QFont.Bold))
        self.status_label.setStyleSheet("color: #FFFF00;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

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
        colors = {"green": "#00FF00", "yellow": "#FFFF00", "red": "#FF0000"}
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {colors.get(color, 'white')};")

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
        thread = threading.Thread(target=self._run_initialization, daemon=True)
        thread.start()

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

            time.sleep(1)

        except Exception as exc:
            self._update_log(f"\nWarning during initialization: {exc}")
            self._update_status("Starting with warnings...", "yellow")
            time.sleep(1)

        finally:
            # Siempre continuar: las cámaras no son requisito para arrancar
            self.startup_complete.emit()

    def _run_single_test(self, name: str, test_func) -> dict:
        """
        Ejecuta un test con hasta 3 reintentos (backoff exponencial).
        Solo reintenta si lanza excepción; False se acepta como resultado.
        """
        result = TestResult(name)
        max_retries = 3
        backoff_ms  = 100

        for attempt in range(1, max_retries + 1):
            try:
                success = test_func()
                result.finish(success)
                return result.to_dict()
            except Exception as exc:
                if attempt < max_retries:
                    wait = backoff_ms * (2 ** (attempt - 1)) / 1000
                    self._update_log(f"  retry {name} ({int(wait*1000)}ms)...")
                    time.sleep(wait)
                else:
                    result.finish(False, str(exc))
                    return result.to_dict()

        return result.to_dict()

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
        """Verifica que seat_names.json y schedule.json son legibles y válidos."""
        from config import load_names_data
        names_ok = bool(load_names_data().get("names") is not None)
        sched_ok = True
        try:
            p = Path("schedule.json")
            if p.exists():
                json.loads(p.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
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

