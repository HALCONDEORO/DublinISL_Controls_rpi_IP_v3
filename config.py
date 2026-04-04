#!/usr/bin/env python3
# config.py — Configuración central de la aplicación
#
# Responsabilidad única: leer archivos de configuración (.txt), definir
# constantes globales, validar IPs/IDs, persistencia de nombres de consejeros,
# y hacer el chequeo de conectividad inicial con cada cámara.

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

SOCKET_TIMEOUT = 1
VISCA_PORT = 5678
BUTTON_COLOR = "black"
NAMES_FILE = 'seat_names.json'


# ─────────────────────────────────────────────────────────────────────────────
#  Lectura de archivos de configuración
# ─────────────────────────────────────────────────────────────────────────────

def _read_config(filename: str, default: str) -> str:
    """Lee una línea de texto de un archivo de configuración."""
    try:
        with open(filename, 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, IOError) as exc:
        print(f"[CONFIG] No se pudo leer '{filename}': {exc}  → usando '{default}'")
        return default


IPAddress  = _read_config('PTZ1IP.txt',  '172.16.1.11')
IPAddress2 = _read_config('PTZ2IP.txt',  '172.16.1.12')
Cam1ID     = _read_config('Cam1ID.txt',  '81')
Cam2ID     = _read_config('Cam2ID.txt',  '82')
Contact    = _read_config('Contact.txt', 'No contact information available.')


# ─────────────────────────────────────────────────────────────────────────────
#  Mapa de presets VISCA
# ─────────────────────────────────────────────────────────────────────────────
PRESET_MAP: dict[int, str] = {}
for _i in range(1, 90):
    PRESET_MAP[_i] = f"{_i:02X}"
for _i in range(90, 100):
    PRESET_MAP[_i] = f"{0x8C + (_i - 90):02X}"
for _i in range(100, 130):
    PRESET_MAP[_i] = f"{_i:02X}"


# ─────────────────────────────────────────────────────────────────────────────
#  Posiciones de asientos en píxeles
#  CAMBIO v3: offset +29px en x para centrar simétricamente en 0..1450px.
#  MOTIVO: la distribución original tenía 70px de margen izquierdo y 128px
#  de margen derecho. Con +29px ambos márgenes quedan en 99px.
#  Asientos 128 (silla ruedas) y 129 (segunda sala) no se desplazan —
#  tienen posiciones especiales independientes del bloque principal.
# ─────────────────────────────────────────────────────────────────────────────

SEAT_POSITIONS: dict[int, tuple[int, int]] = {
    # Fila 1
    4:(96,211),5:(159,211),6:(222,211),7:(285,211),
    8:(500,211),9:(563,211),10:(626,211),11:(689,211),12:(752,211),13:(815,211),14:(878,211),
    15:(1094,211),16:(1157,211),17:(1220,211),18:(1283,211),
    # Fila 2
    19:(96,296),20:(159,296),21:(222,296),22:(285,296),
    23:(500,296),24:(563,296),25:(626,296),26:(689,296),27:(752,296),28:(815,296),29:(878,296),
    30:(1094,296),31:(1157,296),32:(1220,296),33:(1283,296),
    # Fila 3
    34:(96,383),35:(159,383),36:(222,383),37:(285,383),
    38:(500,383),39:(563,383),40:(626,383),41:(689,383),42:(752,383),43:(815,383),44:(878,383),
    45:(1094,383),46:(1157,383),47:(1220,383),48:(1283,383),
    # Fila 4
    49:(96,466),50:(159,466),51:(222,466),52:(285,466),
    53:(500,466),54:(563,466),55:(626,466),56:(689,466),57:(752,466),58:(815,466),59:(878,466),
    60:(1094,466),61:(1157,466),62:(1220,466),63:(1283,466),
    # Fila 5
    64:(96,551),65:(159,551),66:(222,551),67:(285,551),
    68:(500,551),69:(563,551),70:(626,551),71:(689,551),72:(752,551),73:(815,551),74:(878,551),
    75:(1094,551),76:(1157,551),77:(1220,551),78:(1283,551),
    # Fila 6
    79:(96,636),80:(159,636),81:(222,636),82:(285,636),
    83:(500,636),84:(563,636),85:(626,636),86:(689,636),87:(752,636),88:(815,636),89:(878,636),
    90:(1094,636),91:(1157,636),92:(1220,636),93:(1283,636),
    # Fila 7
    94:(96,721),95:(159,721),96:(222,721),97:(285,721),
    98:(500,721),99:(563,721),100:(626,721),101:(689,721),102:(752,721),103:(815,721),104:(878,721),
    105:(1094,721),106:(1157,721),107:(1220,721),108:(1283,721),
    # Fila 8
    109:(96,806),110:(159,806),111:(222,806),112:(285,806),
    113:(500,806),114:(563,806),115:(626,806),116:(689,806),117:(752,806),118:(815,806),119:(878,806),
    120:(1094,806),121:(1157,806),122:(1220,806),123:(1283,806),
    # Fila 9
    124:(140,960),125:(230,960),126:(530,960),127:(620,960),
    # Espacio silla de ruedas
    128:(150,111),
        # Segunda sala
    129:(380,961),
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
    """Valida que el texto sea un valor hexadecimal decodificable."""
    text = text.strip()
    if not text:
        return False
    try:
        binascii.unhexlify(text)
        return True
    except (binascii.Error, ValueError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Persistencia de nombres de consejeros
# ─────────────────────────────────────────────────────────────────────────────

def load_names_data() -> dict:
    """Carga lista de nombres y asignaciones desde NAMES_FILE."""
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
    """Guarda lista y asignaciones en NAMES_FILE."""
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
    """Intenta conectar a la cámara. Devuelve 'Green' si responde, 'Red' si falla."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((ip, VISCA_PORT))
            s.send(binascii.unhexlify(cam_id + "090400FF"))
            s.recv(1024)
        return "Green"
    except (socket.timeout, socket.error, OSError):
        return "Red"


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