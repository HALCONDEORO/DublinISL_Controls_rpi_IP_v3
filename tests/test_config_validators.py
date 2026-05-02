#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. All rights reserved.
# Proprietary software — use, copying, distribution or modification requires written permission.
"""
test_config_validators.py — Tests de is_valid_ip, is_valid_cam_id y PRESET_MAP.
Lógica pura: sin I/O, sin hardware, sin Qt.
"""

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
#  is_valid_ip
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsValidIp:

    @pytest.fixture(autouse=True)
    def _import(self):
        from config import is_valid_ip
        self.fn = is_valid_ip

    @pytest.mark.parametrize("ip", [
        "192.168.1.1",
        "0.0.0.0",
        "255.255.255.255",
        "10.0.0.1",
        "172.16.1.11",
        "1.2.3.4",
    ])
    def test_valid_ips(self, ip):
        assert self.fn(ip) is True

    @pytest.mark.parametrize("ip", [
        "256.0.0.1",        # octeto > 255
        "192.168.1.256",
        "192.168.1",        # solo 3 octetos
        "192.168.1.1.1",    # 5 octetos
        "",
        "abc.def.ghi.jkl",
        "192.168.1.-1",
        "192.168.1.1/24",   # con máscara
        "192.168.1.1:80",   # con puerto
    ])
    def test_invalid_ips(self, ip):
        assert self.fn(ip) is False

    def test_non_string_returns_false(self):
        assert self.fn(None) is False
        assert self.fn(192168) is False
        assert self.fn(["192.168.1.1"]) is False

    def test_strips_whitespace(self):
        # _read_config ya llama .strip(), pero is_valid_ip también debe tolerarlo
        assert self.fn("  192.168.1.1  ") is True

    def test_empty_string_is_invalid(self):
        assert self.fn("") is False


# ═══════════════════════════════════════════════════════════════════════════════
#  is_valid_cam_id
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsValidCamId:

    @pytest.fixture(autouse=True)
    def _import(self):
        from config import is_valid_cam_id
        self.fn = is_valid_cam_id

    @pytest.mark.parametrize("cam_id", [
        "81",    # Cam1 real
        "82",    # Cam2 real
        "FF",
        "ff",    # minúsculas también son hex válido
        "00",
        "8181",  # longitud 4 — par y hex válido
        "FFFF",
    ])
    def test_valid_cam_ids(self, cam_id):
        assert self.fn(cam_id) is True

    @pytest.mark.parametrize("cam_id", [
        "",       # vacío
        "8",      # longitud impar
        "819",    # longitud impar
        "GG",     # no es hex
        "8X",
    ])
    def test_invalid_cam_ids(self, cam_id):
        assert self.fn(cam_id) is False

    def test_non_string_returns_false(self):
        assert self.fn(81) is False
        assert self.fn(None) is False

    def test_strips_whitespace_before_check(self):
        # "  81  " → stripped "81" → longitud par, hex válido
        assert self.fn("  81  ") is True


# ═══════════════════════════════════════════════════════════════════════════════
#  PRESET_MAP — mapeo preset_number → hex string VISCA
# ═══════════════════════════════════════════════════════════════════════════════

class TestPresetMap:

    @pytest.fixture(autouse=True)
    def _import(self):
        from config import PRESET_MAP
        self.pm = PRESET_MAP

    def test_total_count(self):
        # Presets 1-89 + 90-99 + 100-131 = 131 entradas
        assert len(self.pm) == 131

    def test_range_1_to_89_is_direct_hex(self):
        # Preset 1 → "01", preset 10 → "0A", preset 89 → "59"
        assert self.pm[1]  == "01"
        assert self.pm[10] == "0A"
        assert self.pm[15] == "0F"
        assert self.pm[89] == "59"

    def test_range_90_to_99_has_offset(self):
        # 0x8C + (i - 90): 90→"8C", 95→"91", 99→"95"
        assert self.pm[90] == "8C"
        assert self.pm[91] == "8D"
        assert self.pm[95] == "91"
        assert self.pm[99] == "95"

    def test_range_100_to_131_is_direct_hex(self):
        # Vuelta al hex directo: 100 → "64", 131 → "83"
        assert self.pm[100] == "64"
        assert self.pm[110] == "6E"
        assert self.pm[131] == "83"

    def test_no_collision_between_ranges(self):
        # Cada número VISCA hex es único en el mapa
        hex_values = list(self.pm.values())
        assert len(hex_values) == len(set(hex_values)), "Colisión detectada en PRESET_MAP"

    def test_all_values_are_valid_hex(self):
        import binascii
        for preset, hex_str in self.pm.items():
            try:
                binascii.unhexlify(hex_str)
            except Exception:
                pytest.fail(f"Preset {preset} → '{hex_str}' no es hex válido")

    def test_all_values_are_two_chars(self):
        for preset, hex_str in self.pm.items():
            assert len(hex_str) == 2, f"Preset {preset} tiene hex de longitud {len(hex_str)}: '{hex_str}'"

    def test_90_to_99_not_contiguous_with_1_to_89(self):
        # El salto de 89→90 en valores hex: "59" vs "8C" (no son consecutivos)
        assert int(self.pm[89], 16) + 1 != int(self.pm[90], 16)

    def test_boundary_between_offset_and_direct_again(self):
        # Preset 99 → "95" y preset 100 → "64": tampoco son consecutivos
        assert int(self.pm[99], 16) + 1 != int(self.pm[100], 16)
