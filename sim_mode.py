#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# sim_mode.py — Activa / desactiva el modo simulación
#
# Llamado desde config_dialog.py (_build_sim_section) y opcionalmente
# desde terminal:
#   python sim_mode.py on    -> guarda IPs reales y escribe IPs del simulador
#   python sim_mode.py off   -> restaura las IPs reales
#   python sim_mode.py show  -> muestra la configuracion actual

import sys
from pathlib import Path
from json_io import load_json, save_json

BACKUP = Path("sim_ip_backup.json")

# IPs que se escriben al activar el modo simulacion
SIM_VALUES = {
    "PTZ1IP.txt": "127.0.0.1",
    "PTZ2IP.txt": "127.0.0.2",
}

# Ficheros cuyo valor original se guarda en el backup
BACKUP_FILES = ["PTZ1IP.txt", "PTZ2IP.txt", "ATEMIP.txt"]


def _read(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _write(path: str, value: str):
    Path(path).write_text(value, encoding="utf-8")


def _load_backup() -> dict:
    data = load_json(BACKUP)
    if data is None:
        raise RuntimeError("No se pudo leer sim_ip_backup.json")
    return data


def activate() -> bool:
    """
    Guarda las IPs reales en sim_ip_backup.json y escribe las IPs del simulador.
    Devuelve True si se activó, False si ya estaba activo.
    """
    if BACKUP.exists():
        return False  # ya activo

    backup = {f: _read(f) for f in BACKUP_FILES}
    save_json(BACKUP, backup)

    for filename, sim_val in SIM_VALUES.items():
        _write(filename, sim_val)

    return True


def deactivate() -> bool:
    """
    Restaura las IPs reales desde el backup y elimina sim_ip_backup.json.
    Devuelve True si se desactivó, False si no estaba activo.
    Lanza RuntimeError si el backup está corrupto.
    """
    if not BACKUP.exists():
        return False  # ya inactivo

    backup = _load_backup()
    for filename, original in backup.items():
        _write(filename, original)

    BACKUP.unlink()
    return True


def is_active() -> bool:
    return BACKUP.exists()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "show"

    if cmd == "on":
        if activate():
            print("Modo simulacion ACTIVADO.")
            for f, v in SIM_VALUES.items():
                print(f"  {f}  ->  {v!r}")
        else:
            print("Ya estaba activo (sim_ip_backup.json existe).")

    elif cmd == "off":
        try:
            if deactivate():
                print("Modo simulacion DESACTIVADO. IPs reales restauradas.")
            else:
                print("No estaba activo.")
        except RuntimeError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    elif cmd == "show":
        active = is_active()
        print(f"Modo simulacion: {'ACTIVO' if active else 'INACTIVO'}")
        for f in ["PTZ1IP.txt", "PTZ2IP.txt", "ATEMIP.txt", "Cam1ID.txt", "Cam2ID.txt"]:
            print(f"  {f:<15}  {_read(f)!r}")
        if active:
            try:
                backup = _load_backup()
                print("\nIPs reales guardadas:")
                for f, v in backup.items():
                    print(f"  {f:<15}  {v!r}")
            except RuntimeError as e:
                print(f"  ERROR leyendo backup: {e}")

    else:
        print(f"Uso: python sim_mode.py [on|off|show]")
        sys.exit(1)
