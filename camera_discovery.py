#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
# camera_discovery.py — Descubrimiento de IPs de cámaras en la red local
#
# Expone tres funciones independientes del framework UI:
#   get_camera_subnet()  — Prefijo /24 derivado de CAM1.ip
#   tcp_scan()           — Escaneo TCP paralelo (50 workers) en VISCA_PORT
#   arp_scan()           — Lectura de la tabla ARP del sistema operativo
#   discover_cameras()   — Unión de ambos métodos, IPs únicas y ordenadas
#
# Importado desde:
#   splash_screen.py  — tests de inicialización
#   config_dialog.py  — botón "Scan Network" en ajustes

from __future__ import annotations

import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import List

from config import CAM1, VISCA_PORT


# ─────────────────────────────────────────────────────────────────────────────
#  SUBRED
# ─────────────────────────────────────────────────────────────────────────────

def get_camera_subnet() -> str:
    """Devuelve el prefijo /24 de la IP de Cam1 (ej. '172.16.1')."""
    parts = CAM1.ip.split('.')
    return '.'.join(parts[:3]) if len(parts) == 4 else '172.16.1'


# ─────────────────────────────────────────────────────────────────────────────
#  TCP SCAN
# ─────────────────────────────────────────────────────────────────────────────

def tcp_scan(subnet: str = '', workers: int = 50, timeout: float = 0.3) -> List[str]:
    """
    Escanea las 254 IPs de la subred /24 en VISCA_PORT con 'workers' threads
    paralelos. Devuelve lista ordenada de IPs que aceptan conexión TCP.

    Parámetros:
        subnet   — Prefijo /24 (p.ej. '172.16.1'). Si vacío, usa get_camera_subnet().
        workers  — Número de threads simultáneos (defecto 50).
        timeout  — Timeout por host en segundos (defecto 0.3 s).
    """
    if not subnet:
        subnet = get_camera_subnet()

    def _probe(host: str):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                if s.connect_ex((host, VISCA_PORT)) == 0:
                    return host
        except OSError:
            pass
        return None

    hosts = [f"{subnet}.{i}" for i in range(1, 255)]
    found: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for result in ex.map(_probe, hosts):
            if result:
                found.append(result)
    return sorted(found)


# ─────────────────────────────────────────────────────────────────────────────
#  ARP TABLE
# ─────────────────────────────────────────────────────────────────────────────

def arp_scan(subnet: str = '') -> List[str]:
    """
    Ejecuta 'arp -a' y devuelve las IPs de la subred de las cámaras,
    sin broadcasts (.255) y sin duplicados.

    Parámetros:
        subnet — Prefijo /24. Si vacío, usa get_camera_subnet().
    """
    if not subnet:
        subnet = get_camera_subnet()
    try:
        proc = subprocess.run(
            ['arp', '-a'],
            capture_output=True, text=True, timeout=5
        )
        found: List[str] = []
        seen: set = set()
        for line in proc.stdout.splitlines():
            if line.strip().lower().startswith('interface'):
                continue
            m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
            if m:
                ip = m.group(1)
                if (ip.startswith(subnet + '.')
                        and not ip.endswith('.255')
                        and ip not in seen):
                    found.append(ip)
                    seen.add(ip)
        return found
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  DESCUBRIMIENTO COMBINADO
# ─────────────────────────────────────────────────────────────────────────────

def discover_cameras(subnet: str = '') -> List[str]:
    """
    Combina TCP scan y ARP table.
    Devuelve la unión de ambos resultados: IPs únicas ordenadas que
    pertenecen a la subred de las cámaras.
    """
    if not subnet:
        subnet = get_camera_subnet()
    tcp = set(tcp_scan(subnet))
    arp = set(arp_scan(subnet))
    return sorted(tcp | arp)
