#!/usr/bin/env python3
# config.py — Configuración de la aplicación con validación y seguridad

from __future__ import annotations

import json
import logging
import re
import socket
import binascii
import threading
from dataclasses import dataclass, field
from pathlib import Path

from data_paths import SEAT_NAMES_FILE as NAMES_FILE

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  LECTURA DE ARCHIVOS DE CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def _read_config(filename: str, default: str) -> str:
    """Leer una línea de archivo de configuración."""
    # Validar que ambos parámetros sean strings
    if not isinstance(filename, str) or not isinstance(default, str):
        return default
    
    try:
        config_path = Path(filename)
        # Si el archivo no existe, usar valor por defecto
        if not config_path.exists():
            return default
        
        # Leer contenido y eliminar espacios en blanco
        content = config_path.read_text(encoding='utf-8').strip()
        return content if content else default
    
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        # Si hay error, registrar y usar valor por defecto
        logger.warning("Error reading '%s': %s → using '%s'", filename, exc, default)
        return default


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES DE VELOCIDAD Y RED
# ═══════════════════════════════════════════════════════════════════════════════

SPEED_MIN = 1
SPEED_MAX = 18
SPEED_DEFAULT = 8

# Timeout para conexiones socket (1 s: suficiente en LAN local)
SOCKET_TIMEOUT = 1
VISCA_PORT = 5678
# Límite de cola del worker: descarta comandos nuevos si se llena
CAMERA_QUEUE_MAXSIZE = 20
# Segundos sin comando antes de enviar heartbeat (ping)
HEARTBEAT_TIMEOUT = 5.0
BUTTON_COLOR = "black"


# ═══════════════════════════════════════════════════════════════════════════════
#  DATACLASS DE CONFIGURACIÓN DE CÁMARA
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CameraConfig:
    """Configuración de una cámara PTZ: dirección IP, VISCA ID y estado de conectividad."""
    ip: str
    cam_id: str
    check: str = field(default="Red")


# ═══════════════════════════════════════════════════════════════════════════════
#  CARGAR CONFIGURACIÓN DESDE ARCHIVOS
# ═══════════════════════════════════════════════════════════════════════════════

CAM1 = CameraConfig(
    ip=_read_config('PTZ1IP.txt', '172.16.1.11'),
    cam_id=_read_config('Cam1ID.txt', '81'),
)
CAM2 = CameraConfig(
    ip=_read_config('PTZ2IP.txt', '172.16.1.12'),
    cam_id=_read_config('Cam2ID.txt', '82'),
)
ATEMAddress = _read_config('ATEMIP.txt', '192.168.1.240')
Contact = _read_config('Contact.txt', 'No contact information available.')
from secret_manager import decrypt_password as _decrypt_password
LOGIN_PASSWORD = _decrypt_password()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAPA DE PRESETS VISCA
# ═══════════════════════════════════════════════════════════════════════════════

PRESET_MAP: dict[int, str] = {}
# Presets 1-89
for i in range(1, 90):
    PRESET_MAP[i] = f"{i:02X}"
# Presets 90-99
for i in range(90, 100):
    PRESET_MAP[i] = f"{0x8C + (i - 90):02X}"
# Presets 100-131
for i in range(100, 132):
    PRESET_MAP[i] = f"{i:02X}"


# ═══════════════════════════════════════════════════════════════════════════════
#  POSICIONES DE ASIENTOS (COORDENADAS EN PÍXELES)
# ═══════════════════════════════════════════════════════════════════════════════

SEAT_POSITIONS: dict[int, tuple[int, int]] = {
    # Fila 1
    4: (96, 211), 5: (159, 211), 6: (222, 211), 7: (285, 211),
    8: (500, 211), 9: (563, 211), 10: (626, 211), 11: (689, 211),
    12: (752, 211), 13: (815, 211), 14: (878, 211),
    15: (1094, 211), 16: (1157, 211), 17: (1220, 211), 18: (1283, 211),
    # Fila 2
    19: (96, 296), 20: (159, 296), 21: (222, 296), 22: (285, 296),
    23: (500, 296), 24: (563, 296), 25: (626, 296), 26: (689, 296),
    27: (752, 296), 28: (815, 296), 29: (878, 296),
    30: (1094, 296), 31: (1157, 296), 32: (1220, 296), 33: (1283, 296),
    # Fila 3
    34: (96, 383), 35: (159, 383), 36: (222, 383), 37: (285, 383),
    38: (500, 383), 39: (563, 383), 40: (626, 383), 41: (689, 383),
    42: (752, 383), 43: (815, 383), 44: (878, 383),
    45: (1094, 383), 46: (1157, 383), 47: (1220, 383), 48: (1283, 383),
    # Fila 4
    49: (96, 466), 50: (159, 466), 51: (222, 466), 52: (285, 466),
    53: (500, 466), 54: (563, 466), 55: (626, 466), 56: (689, 466),
    57: (752, 466), 58: (815, 466), 59: (878, 466),
    60: (1094, 466), 61: (1157, 466), 62: (1220, 466), 63: (1283, 466),
    # Fila 5
    64: (96, 551), 65: (159, 551), 66: (222, 551), 67: (285, 551),
    68: (500, 551), 69: (563, 551), 70: (626, 551), 71: (689, 551),
    72: (752, 551), 73: (815, 551), 74: (878, 551),
    75: (1094, 551), 76: (1157, 551), 77: (1220, 551), 78: (1283, 551),
    # Fila 6
    79: (96, 636), 80: (159, 636), 81: (222, 636), 82: (285, 636),
    83: (500, 636), 84: (563, 636), 85: (626, 636), 86: (689, 636),
    87: (752, 636), 88: (815, 636), 89: (878, 636),
    90: (1094, 636), 91: (1157, 636), 92: (1220, 636), 93: (1283, 636),
    # Fila 7
    94: (96, 721), 95: (159, 721), 96: (222, 721), 97: (285, 721),
    98: (500, 721), 99: (563, 721), 100: (626, 721), 101: (689, 721),
    102: (752, 721), 103: (815, 721), 104: (878, 721),
    105: (1094, 721), 106: (1157, 721), 107: (1220, 721), 108: (1283, 721),
    # Fila 8
    109: (96, 806), 110: (159, 806), 111: (222, 806), 112: (285, 806),
    113: (500, 806), 114: (563, 806), 115: (626, 806), 116: (689, 806),
    117: (752, 806), 118: (815, 806), 119: (878, 806),
    120: (1094, 806), 121: (1157, 806), 122: (1220, 806), 123: (1283, 806),
    # Fila 9
    124: (140, 960), 125: (230, 960), 126: (530, 960), 127: (620, 960),
    # Silla de ruedas
    128: (150, 121),
    # Segunda sala
    129: (380, 961),
    # Silla de ruedas espejo (auditorio, lado derecho)
    130: (1220, 121),
    # Library (espejo de Second Room)
    131: (1157, 961),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  VALIDADORES
# ═══════════════════════════════════════════════════════════════════════════════

def is_valid_ip(text: str) -> bool:
    """Validar dirección IPv4 (4 octetos 0-255)."""
    # Validar tipo de dato
    if not isinstance(text, str):
        return False
    
    text = text.strip()
    # Usar regex para validar formato XXX.XXX.XXX.XXX
    match = re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', text)
    
    if not match:
        return False
    
    try:
        # Validar que cada octeto esté entre 0-255
        return all(0 <= int(octet) <= 255 for octet in match.groups())
    except (ValueError, TypeError):
        return False


def is_valid_cam_id(text: str) -> bool:
    """Validar ID de cámara VISCA (formato hexadecimal, longitud par)."""
    # Validar tipo de dato
    if not isinstance(text, str):
        return False
    
    text = text.strip()
    
    # El hexadecimal debe tener longitud par (2 caracteres por byte)
    if not text or len(text) % 2 != 0:
        return False
    
    try:
        # Intentar convertir de hexadecimal
        binascii.unhexlify(text)
        return True
    except (binascii.Error, ValueError, TypeError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  PERSISTENCIA DE NOMBRES DE ASISTENTES
# ═══════════════════════════════════════════════════════════════════════════════

def load_names_data() -> dict:
    """Cargar nombres de asistentes y asignaciones de asientos desde JSON."""
    try:
        names_path = Path(NAMES_FILE)
        # Si el archivo no existe, retornar estructura vacía
        if not names_path.exists():
            return {"names": [], "seats": {}}
        
        # Parsear JSON
        data = json.loads(names_path.read_text(encoding='utf-8'))
        
        # Validar estructura del JSON
        if not isinstance(data, dict):
            raise ValueError("Root must be dict")
        
        names = data.get("names", [])
        seats = data.get("seats", {})
        
        # Validar tipos
        if not isinstance(names, list):
            names = []
        if not isinstance(seats, dict):
            seats = {}
        
        return {"names": names, "seats": seats}
    
    except (json.JSONDecodeError, OSError, ValueError, UnicodeDecodeError) as exc:
        # Si hay error, retornar estructura vacía y registrar
        logger.warning("Error loading %s: %s", NAMES_FILE, exc)
        return {"names": [], "seats": {}}


def save_names_data(names_list: list, seat_assignments: dict) -> bool:
    """Guardar nombres de asistentes y asignaciones en JSON."""
    # Validar tipos de parámetros
    if not isinstance(names_list, list) or not isinstance(seat_assignments, dict):
        logger.warning("save_names_data: names must be list, seats must be dict")
        return False
    
    try:
        data = {"names": names_list, "seats": seat_assignments}
        names_path = Path(NAMES_FILE)
        # Guardar JSON con formato legible
        names_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        return True
    
    except (OSError, TypeError, ValueError) as exc:
        # Registrar error si hay problema guardando
        logger.error("Error saving %s: %s", NAMES_FILE, exc)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  VERIFICACIÓN DE CONECTIVIDAD DE CÁMARAS (PARALELA)
# ═══════════════════════════════════════════════════════════════════════════════

def check_camera(ip: str, cam_id: str, timeout: int = SOCKET_TIMEOUT) -> bool:
    """Verificar disponibilidad de cámara mediante conexión TCP."""
    # Validar parámetros de entrada
    if not is_valid_ip(ip) or not is_valid_cam_id(cam_id):
        logger.warning("check_camera: parámetros inválidos ip=%s cam_id=%s", ip, cam_id)
        return False
    
    try:
        # Crear socket y conectar a cámara
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            # Comando VISCA: Power Status 8x 09 04 00 FF
            sock.connect((ip, VISCA_PORT))
            sock.send(binascii.unhexlify(cam_id + "090400FF"))
            sock.recv(1024)
        return True
    
    except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
        # Si hay error de conexión, retornar False
        logger.warning("check_camera %s: %s", ip, exc)
        return False


def check_all_cameras() -> None:
    """Verificar conectividad de todas las cámaras en paralelo y actualizar su campo .check.

    En modo simulación los servidores VISCA arrancan después de este punto,
    así que se marcan directamente como Green.
    Llamar explícitamente desde main_window.__init__ o equivalente.
    """
    if Path("sim_ip_backup.json").exists():
        CAM1.check = "Green"
        CAM2.check = "Green"
        return

    cam1_result = [False]
    cam2_result = [False]
    try:
        def _run_cam1(): cam1_result[0] = check_camera(CAM1.ip, CAM1.cam_id)
        def _run_cam2(): cam2_result[0] = check_camera(CAM2.ip, CAM2.cam_id)
        t1 = threading.Thread(target=_run_cam1, daemon=True)
        t2 = threading.Thread(target=_run_cam2, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)
    except Exception as exc:
        logger.error("Error en threads de verificacion de camaras: %s", exc)
    CAM1.check = "Green" if cam1_result[0] else "Red"
    CAM2.check = "Green" if cam2_result[0] else "Red"