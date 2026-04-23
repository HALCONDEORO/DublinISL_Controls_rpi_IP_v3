#!/usr/bin/env python3
"""
test_persistence.py — Tests unitarios para la capa de persistencia de datos.

Cobertura:
  - chairman_presets : save / load / .bak / next_available / get_preset_for_name
  - config           : save_names_data / load_names_data / .bak
  - schedule_config  : save_schedule / load_schedule / .bak
  - data_paths       : migrate_legacy_files / export_backup / import_backup

Los tests usan monkeypatch de pytest para apuntar las rutas de archivos a
tmp_path, de forma que nunca tocan ~/.config/dublinisl/ del sistema.
"""

import json
import zipfile
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def preset_file(tmp_path, monkeypatch):
    """Apunta CHAIRMAN_PRESETS_FILE al directorio temporal."""
    import chairman_presets as cp
    f = tmp_path / 'chairman_presets.json'
    monkeypatch.setattr(cp, 'CHAIRMAN_PRESETS_FILE', f)
    return f


@pytest.fixture()
def names_file(tmp_path, monkeypatch):
    """Apunta NAMES_FILE al directorio temporal."""
    import config as cfg
    f = tmp_path / 'seat_names.json'
    monkeypatch.setattr(cfg, 'NAMES_FILE', f)
    return f


@pytest.fixture()
def schedule_file(tmp_path, monkeypatch):
    """Apunta SCHEDULE_FILE al directorio temporal."""
    import schedule_config as sc
    f = tmp_path / 'schedule.json'
    monkeypatch.setattr(sc, 'SCHEDULE_FILE', f)
    return f


# ═══════════════════════════════════════════════════════════════════════════════
#  chairman_presets
# ═══════════════════════════════════════════════════════════════════════════════

class TestChairmanPresets:

    def test_roundtrip(self, preset_file):
        from chairman_presets import save_chairman_presets, load_chairman_presets
        data = {'Alice': 10, 'Bob': 11, 'Carol': 12}
        save_chairman_presets(data)
        assert load_chairman_presets() == data

    def test_load_missing_file_returns_empty(self, preset_file):
        from chairman_presets import load_chairman_presets
        assert load_chairman_presets() == {}

    def test_load_corrupted_json_returns_empty(self, preset_file):
        from chairman_presets import load_chairman_presets
        preset_file.write_text("NOT JSON", encoding='utf-8')
        assert load_chairman_presets() == {}

    def test_load_filters_out_of_range_presets(self, preset_file):
        from chairman_presets import save_chairman_presets, load_chairman_presets
        # Escribir directamente JSON con valores fuera de rango
        preset_file.write_text(
            json.dumps({'Alice': 10, 'Bob': 5, 'Carol': 90}),
            encoding='utf-8'
        )
        result = load_chairman_presets()
        assert 'Alice' in result      # 10 — OK
        assert 'Bob' not in result    # 5 — por debajo de CHAIRMAN_PRESET_START (10)
        assert 'Carol' not in result  # 90 — por encima de CHAIRMAN_PRESET_MAX (89)

    def test_bak_created_on_second_save(self, preset_file):
        from chairman_presets import save_chairman_presets
        save_chairman_presets({'Alice': 10})
        save_chairman_presets({'Alice': 10, 'Bob': 11})
        bak = preset_file.with_suffix('.bak')
        assert bak.exists()
        assert json.loads(bak.read_text()) == {'Alice': 10}

    def test_no_bak_on_first_save(self, preset_file):
        from chairman_presets import save_chairman_presets
        save_chairman_presets({'Alice': 10})
        assert not preset_file.with_suffix('.bak').exists()

    def test_tmp_cleaned_up_on_success(self, preset_file):
        from chairman_presets import save_chairman_presets
        save_chairman_presets({'Alice': 10})
        assert not preset_file.with_suffix('.tmp').exists()

    def test_next_available_preset_starts_at_10(self, preset_file):
        from chairman_presets import next_available_preset
        assert next_available_preset({}) == 10

    def test_next_available_preset_skips_used(self, preset_file):
        from chairman_presets import next_available_preset
        used = {str(i): i for i in range(10, 15)}
        assert next_available_preset(used) == 15

    def test_next_available_preset_returns_none_when_full(self, preset_file):
        from chairman_presets import next_available_preset, CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX
        full = {str(i): i for i in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX + 1)}
        assert next_available_preset(full) is None

    def test_get_preset_for_name_known(self, preset_file):
        from chairman_presets import get_preset_for_name
        presets = {'Alice': 10}
        assert get_preset_for_name(presets, 'Alice') == 10

    def test_get_preset_for_name_fallback(self, preset_file):
        from chairman_presets import get_preset_for_name, CHAIRMAN_GENERIC_PRESET
        assert get_preset_for_name({}, 'Unknown') == CHAIRMAN_GENERIC_PRESET


# ═══════════════════════════════════════════════════════════════════════════════
#  config — save_names_data / load_names_data
# ═══════════════════════════════════════════════════════════════════════════════

class TestNamesData:

    def test_roundtrip(self, names_file):
        from config import save_names_data, load_names_data
        names = ['Alice', 'Bob']
        seats = {'4': 'Alice', '5': 'Bob'}
        assert save_names_data(names, seats) is True
        result = load_names_data()
        assert result['names'] == names
        assert result['seats'] == seats

    def test_load_missing_file_returns_empty(self, names_file):
        from config import load_names_data
        result = load_names_data()
        assert result == {'names': [], 'seats': {}}

    def test_load_corrupted_returns_empty(self, names_file):
        from config import load_names_data
        names_file.write_text("{bad json", encoding='utf-8')
        assert load_names_data() == {'names': [], 'seats': {}}

    def test_save_rejects_wrong_types(self, names_file):
        from config import save_names_data
        assert save_names_data("not a list", {}) is False
        assert save_names_data([], "not a dict") is False

    def test_bak_created_on_second_save(self, names_file):
        from config import save_names_data
        save_names_data(['Alice'], {'4': 'Alice'})
        save_names_data(['Alice', 'Bob'], {'4': 'Alice', '5': 'Bob'})
        bak = names_file.with_suffix('.bak')
        assert bak.exists()
        bak_data = json.loads(bak.read_text())
        assert bak_data['names'] == ['Alice']

    def test_no_bak_on_first_save(self, names_file):
        from config import save_names_data
        save_names_data(['Alice'], {})
        assert not names_file.with_suffix('.bak').exists()

    def test_tmp_cleaned_up_on_success(self, names_file):
        from config import save_names_data
        save_names_data(['Alice'], {})
        assert not names_file.with_suffix('.tmp').exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  schedule_config
# ═══════════════════════════════════════════════════════════════════════════════

class TestScheduleConfig:

    def _sample(self):
        return {
            'monday': {'enabled': True, 'start': '09:00', 'end': '17:00'},
            'tuesday': {'enabled': False, 'start': '09:00', 'end': '17:00'},
        }

    def test_roundtrip(self, schedule_file):
        from schedule_config import save_schedule, load_schedule
        assert save_schedule(self._sample()) is True
        result = load_schedule()
        assert result['monday']['enabled'] is True
        assert result['monday']['start'] == '09:00'

    def test_load_missing_returns_defaults(self, schedule_file):
        from schedule_config import load_schedule, DEFAULT_SCHEDULE, DAYS
        result = load_schedule()
        for day in DAYS:
            assert day in result
            assert result[day]['enabled'] == DEFAULT_SCHEDULE[day]['enabled']

    def test_load_partial_json_fills_defaults(self, schedule_file):
        from schedule_config import save_schedule, load_schedule, DAYS
        save_schedule({'monday': {'enabled': True, 'start': '08:00', 'end': '16:00'}})
        result = load_schedule()
        assert result['monday']['enabled'] is True
        assert result['tuesday']['enabled'] is False  # default

    def test_bak_created_on_second_save(self, schedule_file):
        from schedule_config import save_schedule
        save_schedule(self._sample())
        updated = {**self._sample(), 'wednesday': {'enabled': True, 'start': '10:00', 'end': '18:00'}}
        save_schedule(updated)
        bak = schedule_file.with_suffix('.bak')
        assert bak.exists()

    def test_no_bak_on_first_save(self, schedule_file):
        from schedule_config import save_schedule
        save_schedule(self._sample())
        assert not schedule_file.with_suffix('.bak').exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  data_paths — migrate_legacy_files / export_backup / import_backup
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataPaths:

    @pytest.fixture()
    def isolated(self, tmp_path, monkeypatch):
        """Aísla CONFIG_DIR y todas las rutas derivadas en tmp_path."""
        import data_paths
        config_dir = tmp_path / 'config'
        config_dir.mkdir()
        monkeypatch.setattr(data_paths, 'CONFIG_DIR', config_dir)
        monkeypatch.setattr(data_paths, 'CHAIRMAN_PRESETS_FILE', config_dir / 'chairman_presets.json')
        monkeypatch.setattr(data_paths, 'SEAT_NAMES_FILE',       config_dir / 'seat_names.json')
        monkeypatch.setattr(data_paths, 'SCHEDULE_FILE',         config_dir / 'schedule.json')
        monkeypatch.setattr(data_paths, '_DATA_FILES', (
            config_dir / 'chairman_presets.json',
            config_dir / 'seat_names.json',
            config_dir / 'schedule.json',
        ))
        return config_dir

    def test_migrate_copies_existing_files(self, tmp_path, isolated):
        import data_paths
        app_dir = tmp_path / 'app'
        app_dir.mkdir()
        (app_dir / 'chairman_presets.json').write_text('{"Alice": 10}', encoding='utf-8')
        (app_dir / 'seat_names.json').write_text('{"names":[], "seats":{}}', encoding='utf-8')
        # schedule.json no existe en app_dir

        data_paths.migrate_legacy_files(app_dir=app_dir)

        assert (isolated / 'chairman_presets.json').exists()
        assert (isolated / 'seat_names.json').exists()
        assert not (isolated / 'schedule.json').exists()

    def test_migrate_does_not_overwrite_existing(self, tmp_path, isolated):
        import shutil as _shutil
        app_dir = tmp_path / 'app'
        app_dir.mkdir()
        (app_dir / 'chairman_presets.json').write_text('{"legacy": 99}', encoding='utf-8')

        existing_dst = isolated / 'chairman_presets.json'
        existing_dst.write_text('{"current": 10}', encoding='utf-8')

        # La migración no debe sobreescribir el destino existente
        for filename in ('chairman_presets.json',):
            src = app_dir / filename
            dst = isolated / filename
            if src.exists() and not dst.exists():
                _shutil.copy2(src, dst)

        assert json.loads(existing_dst.read_text()) == {'current': 10}

    def test_export_creates_zip_with_existing_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        (isolated / 'chairman_presets.json').write_text('{"Alice": 10}', encoding='utf-8')
        (isolated / 'seat_names.json').write_text('{"names": [], "seats": {}}', encoding='utf-8')
        # schedule.json no existe — no se incluye

        zip_path = tmp_path / 'backup.zip'
        included = data_paths.export_backup(zip_path)

        assert zip_path.exists()
        assert 'chairman_presets.json' in included
        assert 'seat_names.json' in included
        assert 'schedule.json' not in included

        with zipfile.ZipFile(zip_path) as zf:
            names_in_zip = zf.namelist()
        assert 'chairman_presets.json' in names_in_zip
        assert 'seat_names.json' in names_in_zip

    def test_export_empty_when_no_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'empty.zip'
        included = data_paths.export_backup(zip_path)
        assert included == []

    def test_import_restores_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        # Crear un ZIP con datos
        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"Alice": 10}')
            zf.writestr('seat_names.json', '{"names": ["Alice"], "seats": {"4": "Alice"}}')

        restored = data_paths.import_backup(zip_path)

        assert 'chairman_presets.json' in restored
        assert 'seat_names.json' in restored
        assert json.loads((isolated / 'chairman_presets.json').read_text()) == {'Alice': 10}

    def test_import_creates_bak_for_existing_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        existing = isolated / 'chairman_presets.json'
        existing.write_text('{"original": 10}', encoding='utf-8')

        zip_path = tmp_path / 'backup.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', '{"new": 20}')

        data_paths.import_backup(zip_path)

        bak = existing.with_suffix('.bak')
        assert bak.exists()
        assert json.loads(bak.read_text()) == {'original': 10}
        assert json.loads(existing.read_text()) == {'new': 20}

    def test_import_raises_on_invalid_json(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'bad.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('chairman_presets.json', 'NOT JSON')

        with pytest.raises(json.JSONDecodeError):
            data_paths.import_backup(zip_path)

    def test_import_raises_on_no_recognized_files(self, tmp_path, isolated, monkeypatch):
        import data_paths
        zip_path = tmp_path / 'unknown.zip'
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('unrelated.txt', 'hello')

        with pytest.raises(ValueError, match="reconocidos"):
            data_paths.import_backup(zip_path)

    def test_export_then_import_roundtrip(self, tmp_path, isolated, monkeypatch):
        import data_paths
        # Crear datos originales
        (isolated / 'chairman_presets.json').write_text('{"Alice": 10, "Bob": 11}', encoding='utf-8')
        (isolated / 'seat_names.json').write_text(
            '{"names": ["Alice", "Bob"], "seats": {"4": "Alice"}}', encoding='utf-8'
        )

        # Exportar
        zip_path = tmp_path / 'roundtrip.zip'
        data_paths.export_backup(zip_path)

        # Borrar datos
        (isolated / 'chairman_presets.json').unlink()
        (isolated / 'seat_names.json').unlink()

        # Importar
        restored = data_paths.import_backup(zip_path)
        assert len(restored) == 2
        assert json.loads((isolated / 'chairman_presets.json').read_text()) == {'Alice': 10, 'Bob': 11}
