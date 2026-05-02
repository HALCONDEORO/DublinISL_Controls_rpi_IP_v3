#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribucion, modificacion o uso sin autorizacion escrita del autor.
"""
Tests de sim_mode aislando todos los archivos en un directorio temporal local.
"""

import uuid
from pathlib import Path

import pytest

from json_io import load_json
import sim_mode


@pytest.fixture()
def isolated_sim_mode(monkeypatch):
    root = Path(__file__).resolve().parents[1] / ".test_tmp" / f"sim_mode_{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    monkeypatch.setattr(sim_mode, "BACKUP", root / "sim_ip_backup.json")

    def read_from_tmp(path: str) -> str:
        p = root / path
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    def write_to_tmp(path: str, value: str) -> None:
        (root / path).write_text(value, encoding="utf-8")

    monkeypatch.setattr(sim_mode, "_read", read_from_tmp)
    monkeypatch.setattr(sim_mode, "_write", write_to_tmp)
    try:
        yield root
    finally:
        for child in root.iterdir():
            child.unlink()
        root.rmdir()
        parent = root.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


class TestSimMode:

    def test_activate_saves_original_values_and_writes_simulated_ips(self, isolated_sim_mode):
        (isolated_sim_mode / "PTZ1IP.txt").write_text("172.16.1.11\n", encoding="utf-8")
        (isolated_sim_mode / "PTZ2IP.txt").write_text("172.16.1.12\n", encoding="utf-8")
        (isolated_sim_mode / "ATEMIP.txt").write_text("192.168.1.240\n", encoding="utf-8")

        assert sim_mode.activate() is True

        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "127.0.0.1"
        assert (isolated_sim_mode / "PTZ2IP.txt").read_text(encoding="utf-8") == "127.0.0.2"
        assert load_json(sim_mode.BACKUP) == {
            "PTZ1IP.txt": "172.16.1.11",
            "PTZ2IP.txt": "172.16.1.12",
            "ATEMIP.txt": "192.168.1.240",
        }

    def test_activate_is_idempotent_when_backup_exists(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text("{}", encoding="utf-8")
        (isolated_sim_mode / "PTZ1IP.txt").write_text("real", encoding="utf-8")

        assert sim_mode.activate() is False

        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "real"

    def test_activate_records_missing_original_files_as_empty_strings(self, isolated_sim_mode):
        assert sim_mode.activate() is True

        assert load_json(sim_mode.BACKUP) == {
            "PTZ1IP.txt": "",
            "PTZ2IP.txt": "",
            "ATEMIP.txt": "",
        }

    def test_deactivate_restores_backup_values_and_removes_backup(self, isolated_sim_mode):
        (isolated_sim_mode / "PTZ1IP.txt").write_text("127.0.0.1", encoding="utf-8")
        sim_mode.BACKUP.write_text(
            '{"PTZ1IP.txt": "172.16.1.11", "ATEMIP.txt": "192.168.1.240"}',
            encoding="utf-8",
        )

        assert sim_mode.deactivate() is True

        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "172.16.1.11"
        assert (isolated_sim_mode / "ATEMIP.txt").read_text(encoding="utf-8") == "192.168.1.240"
        assert not sim_mode.BACKUP.exists()

    def test_deactivate_returns_false_when_not_active(self, isolated_sim_mode):
        assert sim_mode.deactivate() is False

    def test_deactivate_raises_on_corrupt_backup(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text("not json", encoding="utf-8")

        with pytest.raises(RuntimeError):
            sim_mode.deactivate()

    def test_is_active_tracks_backup_file(self, isolated_sim_mode):
        assert sim_mode.is_active() is False

        sim_mode.BACKUP.write_text("{}", encoding="utf-8")

        assert sim_mode.is_active() is True




