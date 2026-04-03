#!/usr/bin/env python3
# config.py — Configuración central de la aplicación
#
# Responsabilidad única: leer archivos de configuración (.txt), definir
# constantes globales, validar IPs/IDs, persistencia de nombres de consejeros,
# y hacer el chequeo de conectividad inicial con cada cámara.
#
# MOTIVO DE SEPARACIÓN: estos valores se importan en varios módulos.
# Tenerlos aquí evita dependencias circulares y hace que cualquier cambio
# de configuración solo afecte a este archivo.

from __future__ import annotations
import json
import re
import socket
import binascii
import threading

# ─────────────────────────────────────────────────────────────────────────────
#  Constantes de velocidad del slider
# ─────────────────────────────────────────────────────────────────────────────
SPEED_MIN     = 1
SPEED_MAX     = 18
SPEED_DEFAULT = 8

# Timeout de socket en segundos.
SOCKET_TIMEOUT = 1

# Puerto VISCA-over-IP estándar.
VISCA_PORT = 5678

# Color por defecto del texto de los botones de asiento.
BUTTON_COLOR = "black"

# Archivo JSON para persistencia de nombres de consejeros y asignaciones.
# MOTIVO: centralizar el nombre del archivo para que widgets.py y main_window.py
# no lo dupliquen como string literal.
NAMES_FILE = 'seat_names.json'


# ─────────────────────────────────────────────────────────────────────────────
#  Lectura de archivos de configuración
# ─────────────────────────────────────────────────────────────────────────────

def _read_config(filename: str, default: str) -> str:
    """
    Lee una línea de texto de un archivo de configuración.
    Si el archivo no existe o no se puede leer, devuelve el valor por defecto
    y lo informa por consola sin abortar la aplicación.
    """
    try:
        with open(filename, 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, IOError) as exc:
        print(f"[CONFIG] No se pudo leer '{filename}': {exc}  → usando '{default}'")
        return default


# Cargar configuración al importar el módulo.
IPAddress  = _read_config('PTZ1IP.txt',  '172.16.1.11')
IPAddress2 = _read_config('PTZ2IP.txt',  '172.16.1.12')
Cam1ID     = _read_config('Cam1ID.txt',  '81')
Cam2ID     = _read_config('Cam2ID.txt',  '82')
Contact    = _read_config('Contact.txt', 'No contact information available.')


# ─────────────────────────────────────────────────────────────────────────────
#  Mapa de presets VISCA (número lógico → byte hex)
# ─────────────────────────────────────────────────────────────────────────────
PRESET_MAP: dict[int, str] = {}
for _i in range(1, 90):
    PRESET_MAP[_i] = f"{_i:02X}"
for _i in range(90, 100):
    # Presets 90-99 → 0x8C-0x95 según spec VISCA extendida del fabricante
    PRESET_MAP[_i] = f"{0x8C + (_i - 90):02X}"
for _i in range(100, 130):
    PRESET_MAP[_i] = f"{_i:02X}"


# ─────────────────────────────────────────────────────────────────────────────
#  Posiciones de asientos en píxeles sobre la imagen de fondo
# ─────────────────────────────────────────────────────────────────────────────
SEAT_POSITIONS: dict[int, tuple[int, int]] = {
    # Fila 1
     4:(70,210),  5:(131,210),  6:(192,210),  7:(253,210),
     8:(479,210), 9:(540,210), 10:(601,210), 11:(662,210),
    12:(722,210),13:(783,210), 14:(844,210),
    15:(1070,210),16:(1130,210),17:(1191,210),18:(1252,210),
    # Fila 2
    19:(70,295), 20:(131,295), 21:(192,295), 22:(253,295),
    23:(479,295),24:(540,295), 25:(601,295), 26:(662,295),
    27:(722,295),28:(783,295), 29:(844,295),
    30:(1070,295),31:(1130,295),32:(1191,295),33:(1252,295),
    # Fila 3
    34:(70,382), 35:(131,382), 36:(192,382), 37:(253,382),
    38:(479,382),39:(540,382), 40:(601,382), 41:(662,382),
    42:(723,382),43:(783,382), 44:(844,382),
    45:(1070,382),46:(1130,382),47:(1191,382),48:(1252,382),
    # Fila 4
    49:(70,465), 50:(131,465), 51:(192,465), 52:(253,465),
    53:(479,465),54:(540,465), 55:(601,465), 56:(662,465),
    57:(722,465),58:(783,465), 59:(844,465),
    60:(1070,465),61:(1130,465),62:(1191,465),63:(1252,465),
    # Fila 5
    64:(70,550), 65:(131,550), 66:(192,550), 67:(253,550),
    68:(479,550),69:(540,550), 70:(601,550), 71:(662,550),
    72:(722,550),73:(783,550), 74:(844,550),
    75:(1070,550),76:(1130,550),77:(1191,550),78:(1252,550),
    # Fila 6
    79:(70,635), 80:(131,635), 81:(192,635), 82:(253,635),
    83:(479,635),84:(540,635), 85:(601,635), 86:(662,635),
    87:(722,635),88:(783,635), 89:(844,635),
    90:(1070,635),91:(1130,635),92:(1191,635),93:(1252,635),
    # Fila 7
    94:(70,720), 95:(131,720), 96:(192,720), 97:(253,720),
    98:(479,720),99:(540,720),100:(601,720),101:(662,720),
   102:(722,720),103:(783,720),104:(844,720),
   105:(1070,720),106:(1130,720),107:(1191,720),108:(1252,720),
    # Fila 8
   109:(70,805), 110:(131,805),111:(192,805),112:(253,805),
   113:(479,805),114:(540,805),115:(601,805),116:(662,805),
   117:(722,805),118:(783,805),119:(844,805),
   120:(1070,805),121:(1130,805),122:(1191,805),123:(1252,805),
    # Fila 9
   124:(108,975),125:(201,975),126:(481,975),127:(578,975),
    # Espacio silla de ruedas
   128:(150,110),
    # Segunda sala
   129:(380,960),
}


# ─────────────────────────────────────────────────────────────────────────────
#  Validadores
# ─────────────────────────────────────────────────────────────────────────────

def is_valid_ip(text: str) -> bool:
    """Valida que el texto sea una IPv4 con cuatro octetos 0-255."""
    match = re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', text.strip())
    if not match:
        return False
    return all(0 <= int(g) <= 255 for g in match.groups())


def is_valid_cam_id(text: str) -> bool:
    """Valida que el texto sea un valor hexadecimal decodificable (ej. '81', '82')."""
    text = text.strip()
    if not text:
        return False
    try:
        binascii.unhexlify(text)
        return True
    except (binascii.Error, ValueError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Persistencia de nombres de consejeros  ← NUEVO
# ─────────────────────────────────────────────────────────────────────────────
# Formato de seat_names.json:
#   {
#     "names": ["Ana López", "Pedro Ruiz", ...],
#     "seats": {"7": "Ana López", "12": "Pedro Ruiz", ...}
#   }
#
# MOTIVO de ubicación aquí: config.py ya gestiona toda la E/S de archivos
# de la app.  Centralizar aquí evita que widgets.py y main_window.py
# dependan de 'json' y de la ruta del archivo directamente.

def load_names_data() -> dict:
    """
    Carga lista de nombres y asignaciones desde NAMES_FILE.
    Primera ejecución o archivo corrupto: devuelve estructura vacía sin error.
    Garantiza que las claves 'names' y 'seats' siempre existen en el resultado.
    """
    try:
        with open(NAMES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "names": data.get("names", []),
            "seats": data.get("seats", {}),
        }
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[NAMES] {NAMES_FILE}: {exc} — iniciando con datos vacíos.")
        return {"names": [], "seats": {}}


def save_names_data(names_list: list, seat_assignments: dict) -> None:
    """
    Guarda lista y asignaciones en NAMES_FILE.
    Se llama en cada cambio para no perder datos entre sesiones.
    Falla silenciosamente con un warning si no hay permisos de escritura.
    """
    try:
        with open(NAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(
                {"names": names_list, "seats": seat_assignments},
                f, ensure_ascii=False, indent=2,
            )
    except IOError as exc:
        print(f"[NAMES] Error guardando {NAMES_FILE}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  Chequeo de conectividad al inicio
# ─────────────────────────────────────────────────────────────────────────────

def check_camera(ip: str, cam_id: str) -> str:
    """
    Intenta conectar a la cámara y enviar un query de estado.
    Devuelve "Green" si responde correctamente, "Red" si falla.
    Se llama UNA sola vez al arrancar (en paralelo para ambas cámaras).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((ip, VISCA_PORT))
            s.send(binascii.unhexlify(cam_id + "090400FF"))
            s.recv(1024)
        return "Green"
    except (socket.timeout, socket.error, OSError):
        return "Red"


# Ejecutar chequeos en paralelo para no bloquear el arranque.
_cam1_result = ["Red"]
_cam2_result = ["Red"]

def _check1(): _cam1_result[0] = check_camera(IPAddress, Cam1ID)
def _check2(): _cam2_result[0] = check_camera(IPAddress2, Cam2ID)

_t1 = threading.Thread(target=_check1, daemon=True)
_t2 = threading.Thread(target=_check2, daemon=True)
_t1.start(); _t2.start()
_t1.join();  _t2.join()

Cam1Check = _cam1_result[0]
Cam2Check = _cam2_result[0]