#!/usr/bin/env python3
# Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.
# Software propietario y de uso privado exclusivo. Queda prohibida su copia,
# distribución, modificación o uso sin autorización escrita del autor.
"""
test_json_io.py — Tests de la capa de I/O atómica (json_io.py).
"""

import json
import threading
from pathlib import Path

import pytest

from json_io import load_json, save_json


# ═══════════════════════════════════════════════════════════════════════════════
#  load_json
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadJson:

    def test_missing_file_returns_default_none(self, tmp_path):
        assert load_json(tmp_path / "nope.json") is None

    def test_missing_file_returns_custom_default(self, tmp_path):
        assert load_json(tmp_path / "nope.json", default={}) == {}

    def test_corrupted_json_returns_default(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("NOT JSON", encoding="utf-8")
        assert load_json(f, default=[]) == []

    def test_valid_dict(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": 42}', encoding="utf-8")
        assert load_json(f) == {"key": 42}

    def test_valid_list(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[1, 2, 3]', encoding="utf-8")
        assert load_json(f) == [1, 2, 3]

    def test_accepts_str_path(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"x": 1}', encoding="utf-8")
        assert load_json(str(f)) == {"x": 1}

    def test_unicode_content(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"nombre": "María José", "ciudad": "Dublín"}
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        assert load_json(f) == data

    def test_empty_file_returns_default(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_bytes(b"")
        assert load_json(f, default="fallback") == "fallback"

    def test_nested_structure(self, tmp_path):
        f = tmp_path / "nested.json"
        data = {"a": {"b": [1, 2, {"c": True}]}}
        f.write_text(json.dumps(data), encoding="utf-8")
        assert load_json(f) == data


# ═══════════════════════════════════════════════════════════════════════════════
#  save_json
# ═══════════════════════════════════════════════════════════════════════════════

class TestSaveJson:

    def test_roundtrip(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"Alice": 10, "Bob": 11}
        assert save_json(f, data) is True
        assert load_json(f) == data

    def test_returns_true_on_success(self, tmp_path):
        assert save_json(tmp_path / "ok.json", {"x": 1}) is True

    def test_returns_false_when_parent_is_a_file(self, tmp_path):
        # Si el padre de la ruta es un archivo (no un directorio), mkdir falla
        # con OSError → save_json debe capturarlo y devolver False.
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("soy un archivo", encoding="utf-8")
        target = blocker / "data.json"  # padre es un archivo → imposible crear
        assert save_json(target, {"x": 1}) is False

    def test_non_serializable_returns_false(self, tmp_path):
        assert save_json(tmp_path / "fail.json", object()) is False

    def test_no_tmp_left_after_success(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"x": 1})
        tmp_files = list(tmp_path.glob(".tmp_*.json"))
        assert tmp_files == []

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "a" / "b" / "c" / "data.json"
        assert save_json(f, {"y": 2}) is True
        assert f.exists()

    def test_accepts_str_path(self, tmp_path):
        f = tmp_path / "data.json"
        assert save_json(str(f), {"z": 3}) is True
        assert load_json(f) == {"z": 3}

    def test_overwrites_existing_file(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        save_json(f, {"v": 2})
        assert load_json(f) == {"v": 2}

    def test_unicode_preserved(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"nombre": "Ángel", "emoji_free": "ok"}
        save_json(f, data)
        assert load_json(f) == data

    def test_list_roundtrip(self, tmp_path):
        f = tmp_path / "list.json"
        data = ["a", "b", "c"]
        save_json(f, data)
        assert load_json(f) == data


# ═══════════════════════════════════════════════════════════════════════════════
#  Backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestSaveJsonBackup:

    def test_no_bak_on_first_save(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        assert not f.with_suffix('.bak').exists()

    def test_bak_created_on_second_save(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        save_json(f, {"v": 2})
        assert f.with_suffix('.bak').exists()

    def test_bak_contains_previous_content(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        save_json(f, {"v": 2})
        bak_data = load_json(f.with_suffix('.bak'))
        assert bak_data == {"v": 1}

    def test_bak_updated_on_third_save(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        save_json(f, {"v": 2})
        save_json(f, {"v": 3})
        bak_data = load_json(f.with_suffix('.bak'))
        assert bak_data == {"v": 2}
        assert load_json(f) == {"v": 3}

    def test_main_file_updated_correctly(self, tmp_path):
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        save_json(f, {"v": 2})
        assert load_json(f) == {"v": 2}

    def test_save_succeeds_even_if_bak_dir_is_read_only(self, tmp_path, monkeypatch):
        """Un fallo al crear el .bak no debe impedir el guardado principal."""
        import shutil as _shutil
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})

        def _fail_copy(*_args, **_kwargs):
            raise OSError("disco lleno")

        monkeypatch.setattr(_shutil, "copy2", _fail_copy)
        result = save_json(f, {"v": 2})
        assert result is True
        assert load_json(f) == {"v": 2}


# ═══════════════════════════════════════════════════════════════════════════════
#  Concurrencia
# ═══════════════════════════════════════════════════════════════════════════════

class TestJsonIoConcurrency:

    def test_concurrent_saves_no_corruption(self, tmp_path):
        """20 threads escribiendo el mismo archivo no deben corromper el resultado final.
        En Windows, os.replace puede fallar ocasionalmente con concurrencia alta —
        lo importante es que el archivo nunca quede con JSON inválido."""
        f = tmp_path / "concurrent.json"

        def _write(i):
            save_json(f, {"writer": i, "value": i * 10})

        threads = [threading.Thread(target=_write, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Al menos una escritura tuvo que completarse
        assert f.exists(), "Ningún thread completó una escritura sobre el archivo"
        # El contenido debe ser JSON válido (no parcial ni corrupto)
        result = load_json(f)
        assert isinstance(result, dict), "El archivo quedó corrupto tras escrituras concurrentes"
        assert "writer" in result
        assert isinstance(result["writer"], int), "El campo 'writer' debe ser un entero"

    def test_concurrent_reads_while_writing(self, tmp_path):
        """Leer mientras se escribe no debe lanzar excepción."""
        f = tmp_path / "rw.json"
        save_json(f, {"init": True})
        read_errors = []

        def _read():
            for _ in range(10):
                val = load_json(f, default={})
                if not isinstance(val, dict):
                    read_errors.append(val)

        def _write():
            for i in range(10):
                save_json(f, {"i": i})

        threads = [threading.Thread(target=_read) for _ in range(5)]
        threads += [threading.Thread(target=_write) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert read_errors == []

    def test_different_files_use_different_locks(self, tmp_path):
        """Archivos distintos no se bloquean entre sí."""
        f1 = tmp_path / "file1.json"
        f2 = tmp_path / "file2.json"

        results = {}

        def _write_f1():
            results["f1"] = save_json(f1, {"src": 1})

        def _write_f2():
            results["f2"] = save_json(f2, {"src": 2})

        t1 = threading.Thread(target=_write_f1)
        t2 = threading.Thread(target=_write_f2)
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert results == {"f1": True, "f2": True}
        assert load_json(f1) == {"src": 1}
        assert load_json(f2) == {"src": 2}
