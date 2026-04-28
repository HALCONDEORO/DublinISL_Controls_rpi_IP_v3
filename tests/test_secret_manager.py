#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
"""
test_secret_manager.py — Tests de la capa de cifrado XOR-stream y del ciclo
encrypt/decrypt. Lógica pura: sin Qt, sin hardware, sin red.
"""

import sys

# test_preset_poll.py inyecta sys.modules["secret_manager"] = stub a nivel de módulo
# durante la fase de colección de pytest. Lo eliminamos aquí para garantizar que
# este archivo siempre importa la implementación real, independientemente del orden
# en que pytest coleccione los módulos.
sys.modules.pop("secret_manager", None)

import pytest
from pathlib import Path
import secret_manager as _sm

_xor_stream      = _sm._xor_stream
encrypt_password = _sm.encrypt_password
decrypt_password = _sm.decrypt_password
_DEFAULT_PASSWORD = _sm._DEFAULT_PASSWORD


# ═══════════════════════════════════════════════════════════════════════════════
#  _xor_stream — propiedades de la primitiva XOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestXorStream:

    def test_empty_input(self):
        assert _xor_stream(b"", b"anykey") == b""

    def test_xor_is_self_inverse(self):
        """Propiedad fundamental: aplicar el stream dos veces recupera el original."""
        data = b"hello world - datos de prueba"
        key  = b"x" * 32
        assert _xor_stream(_xor_stream(data, key), key) == data

    def test_output_length_equals_input_length(self):
        """El output siempre tiene la misma longitud que el input."""
        key = b"k" * 32
        for n in [1, 7, 31, 32, 33, 64, 100, 255]:
            assert len(_xor_stream(bytes(n), key)) == n

    def test_output_is_not_plaintext(self):
        """El output cifrado no debe coincidir con el input (keystream no es todo ceros)."""
        data = b"A" * 32
        key  = b"testkey" + bytes(25)
        assert _xor_stream(data, key) != data

    def test_different_keys_produce_different_ciphertext(self):
        data = b"mismo mensaje"
        out1 = _xor_stream(data, b"a" * 32)
        out2 = _xor_stream(data, b"b" * 32)
        assert out1 != out2

    def test_same_key_same_output_is_deterministic(self):
        data = b"deterministic"
        key  = b"z" * 32
        assert _xor_stream(data, key) == _xor_stream(data, key)

    def test_crosses_sha256_block_boundary(self):
        """SHA256 produce bloques de 32 bytes; datos >32 bytes usan más de un bloque."""
        data = bytes(range(256))  # 256 bytes = 8 bloques SHA256
        key  = b"longkey" + bytes(25)
        assert _xor_stream(_xor_stream(data, key), key) == data

    def test_single_byte_is_invertible(self):
        data = bytes([0xAB])
        key  = bytes(32)
        result = _xor_stream(data, key)
        assert len(result) == 1
        assert _xor_stream(result, key) == data


# ═══════════════════════════════════════════════════════════════════════════════
#  encrypt_password / decrypt_password — ciclo completo
# ═══════════════════════════════════════════════════════════════════════════════

class TestEncryptDecryptRoundtrip:

    @pytest.fixture(autouse=True)
    def isolated_enc_file(self, tmp_path, monkeypatch):
        """Redirige _ENC_FILE a un archivo temporal para no tocar password.enc real."""
        fake = tmp_path / "password.enc"
        monkeypatch.setattr(_sm, "_ENC_FILE", fake)
        self.enc_file = fake

    def test_roundtrip_simple_password(self):
        encrypt_password("dublin2024")
        assert decrypt_password() == "dublin2024"

    def test_roundtrip_complex_password(self):
        pw = "P@ss!w0rd#2026-Ñoño"
        encrypt_password(pw)
        assert decrypt_password() == pw

    def test_roundtrip_unicode_password(self):
        pw = "cámara-PTZ-€"
        encrypt_password(pw)
        assert decrypt_password() == pw

    def test_roundtrip_empty_password(self):
        encrypt_password("")
        assert decrypt_password() == ""

    def test_roundtrip_long_password(self):
        pw = "a" * 1000
        encrypt_password(pw)
        assert decrypt_password() == pw

    def test_missing_file_returns_default(self):
        assert not self.enc_file.exists()
        assert decrypt_password() == _DEFAULT_PASSWORD

    def test_enc_file_created_after_encrypt(self):
        encrypt_password("test")
        assert self.enc_file.exists()

    def test_enc_file_format_is_salt_colon_cipher(self):
        """El archivo debe tener formato 'hex_salt:hex_cipher' legible como ASCII."""
        encrypt_password("test")
        content = self.enc_file.read_text(encoding="ascii").strip()
        parts = content.split(":")
        assert len(parts) == 2, "El archivo no tiene formato 'salt:cipher'"
        salt_hex, cipher_hex = parts
        # Ambas partes deben ser hex decodificable
        assert bytes.fromhex(salt_hex)
        assert bytes.fromhex(cipher_hex)
        # Salt debe ser 16 bytes → 32 caracteres hex
        assert len(salt_hex) == 32, f"Salt inesperado: {len(salt_hex)} chars (esperado 32)"

    def test_two_encryptions_differ_due_to_random_salt(self):
        """Salt aleatorio → cada cifrado produce un blob distinto para la misma contraseña."""
        encrypt_password("same_password")
        blob1 = self.enc_file.read_text()
        encrypt_password("same_password")
        blob2 = self.enc_file.read_text()
        assert blob1 != blob2

    def test_corrupted_file_returns_default(self):
        self.enc_file.write_text("not_valid_blob", encoding="ascii")
        assert decrypt_password() == _DEFAULT_PASSWORD

    def test_truncated_file_returns_default(self):
        """Un archivo con solo el salt (sin ':cipher') devuelve el default."""
        self.enc_file.write_text("a" * 32, encoding="ascii")
        assert decrypt_password() == _DEFAULT_PASSWORD

    def test_decrypted_value_differs_from_default_when_set(self):
        """Confirma que decrypt devuelve la contraseña real, no siempre el default."""
        custom = "mi_password_especifico_12345"
        encrypt_password(custom)
        result = decrypt_password()
        assert result == custom
        assert result != _DEFAULT_PASSWORD
