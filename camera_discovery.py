#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribuciÃ³n, modificaciÃ³n o uso sin autorizaciÃ³n escrita del autor.
# camera_discovery.py â€” Descubrimiento de IPs de cÃ¡maras en la red local
#
# Expone tres funciones independientes del framework UI:
#   get_camera_subnet()  â€” Prefijo /24 derivado de CAM1.ip
#   tcp_scan()           â€” Escaneo TCP paralelo (50 workers) en VISCA_PORT
#   arp_scan()           â€” Lectura de la tabla ARP del sistema operativo
#   discover_cameras()   â€” UniÃ³n de ambos mÃ©todos, IPs Ãºnicas y ordenadas
#
# Importado desde:
#   splash_screen.py  â€” tests de inicializaciÃ³n
#   config_dialog.py  â€” botÃ³n "Scan Network" en ajustes

from __future__ import annotations

import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import List

from config import CAM1, VISCA_PORT


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  SUBRED
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def get_camera_subnet() -> str:
    """Devuelve el prefijo /24 de la IP de Cam1 (ej. '172.16.1')."""
    parts = CAM1.ip.split('.')
    return '.'.join(parts[:3]) if len(parts) == 4 else '172.16.1'


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  TCP SCAN
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def tcp_scan(subnet: str = '', workers: int = 50, timeout: float = 0.3) -> List[str]:
    """
    Escanea las 254 IPs de la subred /24 en VISCA_PORT con 'workers' threads
    paralelos. Devuelve lista ordenada de IPs que aceptan conexiÃ³n TCP.

    ParÃ¡metros:
        subnet   â€” Prefijo /24 (p.ej. '172.16.1'). Si vacÃ­o, usa get_camera_subnet().
        workers  â€” NÃºmero de threads simultÃ¡neos (defecto 50).
        timeout  â€” Timeout por host en segundos (defecto 0.3 s).
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ARP TABLE
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def arp_scan(subnet: str = '') -> List[str]:
    """
    Ejecuta 'arp -a' y devuelve las IPs de la subred de las cÃ¡maras,
    sin broadcasts (.255) y sin duplicados.

    ParÃ¡metros:
        subnet â€” Prefijo /24. Si vacÃ­o, usa get_camera_subnet().
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  DESCUBRIMIENTO COMBINADO
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def discover_cameras(subnet: str = '') -> List[str]:
    """
    Combina TCP scan y ARP table.
    Devuelve la uniÃ³n de ambos resultados: IPs Ãºnicas ordenadas que
    pertenecen a la subred de las cÃ¡maras.
    """
    if not subnet:
        subnet = get_camera_subnet()
    tcp = set(tcp_scan(subnet))
    arp = set(arp_scan(subnet))
    return sorted(tcp | arp)
