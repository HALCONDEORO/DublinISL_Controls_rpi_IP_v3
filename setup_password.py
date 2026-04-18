#!/usr/bin/env python3
# setup_password.py — Utilidad para establecer/cambiar la contraseña de acceso
#
# Uso:  python setup_password.py
#
# Migra password.txt a password.enc y lo elimina si existe.

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from secret_manager import encrypt_password, decrypt_password, _ENC_FILE


def main() -> None:
    print("=" * 50)
    print("  DublinISL Controls — Configuración de contraseña")
    print("=" * 50)

    # Migración automática desde password.txt
    old_file = Path("password.txt")
    if old_file.exists() and not _ENC_FILE.exists():
        old_pwd = old_file.read_text(encoding="utf-8").strip()
        if old_pwd:
            encrypt_password(old_pwd)
            old_file.unlink()
            print(f"\n[OK] Contrasena migrada desde password.txt -> password.enc")
            print("  (password.txt eliminado)")
            return

    # Cambio manual de contraseña
    if _ENC_FILE.exists():
        current = decrypt_password()
        confirm = getpass.getpass("\nContraseña actual: ")
        if confirm != current:
            print("✗ Contraseña actual incorrecta.")
            sys.exit(1)

    while True:
        new_pwd = getpass.getpass("\nNueva contraseña: ")
        if not new_pwd:
            print("✗ La contraseña no puede estar vacía.")
            continue
        confirm2 = getpass.getpass("Confirmar contraseña: ")
        if new_pwd != confirm2:
            print("✗ Las contraseñas no coinciden.")
            continue
        break

    encrypt_password(new_pwd)
    print(f"\n[OK] Contrasena guardada en {_ENC_FILE}")


if __name__ == "__main__":
    main()
