#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
# secret_manager.py — Cifrado de contraseña ligado a la máquina (sin dependencias externas)
#
# Esquema: PBKDF2-HMAC-SHA256(machine_guid, salt, 200_000) → clave 32 bytes
#          XOR-stream con SHA256 en modo contador → cifrado simétrico
#          Almacenamiento: 16 bytes salt (hex) + ':' + datos cifrados (hex) en password.enc
#
# El archivo password.enc es inútil fuera de esta máquina porque la clave
# se deriva del MachineGuid de Windows (o del hostname como fallback).

from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

_ENC_FILE = Path("password.enc")
_DEFAULT_PASSWORD = "dublin2024"


# ─────────────────────────────────────────────────────────────────
#  IDENTIFICADOR DE MÁQUINA
# ─────────────────────────────────────────────────────────────────

def _machine_id() -> str:
    """Obtener identificador único de la máquina."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography"
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return guid
    except Exception:
        return socket.gethostname()


# ─────────────────────────────────────────────────────────────────
#  DERIVACIÓN DE CLAVE
# ─────────────────────────────────────────────────────────────────

def _derive_key(salt: bytes) -> bytes:
    """Derivar clave de 32 bytes a partir del ID de máquina y sal aleatoria."""
    machine = _machine_id().encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", machine, salt, 200_000, dklen=32)


# ─────────────────────────────────────────────────────────────────
#  CIFRADO / DESCIFRADO  (XOR-stream con SHA256 en modo contador)
# ─────────────────────────────────────────────────────────────────

def _xor_stream(data: bytes, key: bytes) -> bytes:
    """Aplicar cifrado XOR-stream: genera keystream con SHA256 por bloques de 32 bytes."""
    out = bytearray(len(data))
    block = 0
    offset = 0
    while offset < len(data):
        ks_block = hashlib.sha256(key + block.to_bytes(4, "big")).digest()
        for i, byte in enumerate(ks_block):
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ byte
            offset += 1
        block += 1
    return bytes(out)


def encrypt_password(plaintext: str) -> None:
    """Cifrar contraseña y guardarla en password.enc."""
    salt = os.urandom(16)
    key = _derive_key(salt)
    encrypted = _xor_stream(plaintext.encode("utf-8"), key)
    blob = salt.hex() + ":" + encrypted.hex()
    _ENC_FILE.write_text(blob, encoding="ascii")


def decrypt_password() -> str:
    """Descifrar contraseña desde password.enc. Devuelve el default si falla."""
    try:
        if not _ENC_FILE.exists():
            return _DEFAULT_PASSWORD
        blob = _ENC_FILE.read_text(encoding="ascii").strip()
        salt_hex, enc_hex = blob.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        encrypted = bytes.fromhex(enc_hex)
        key = _derive_key(salt)
        return _xor_stream(encrypted, key).decode("utf-8")
    except Exception:
        return _DEFAULT_PASSWORD
