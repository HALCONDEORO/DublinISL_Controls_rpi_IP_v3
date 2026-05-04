import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PYTEST_RUNTIME_DIR = ROOT / ".pytest-runtime"
PYTEST_DATA_DIR = PYTEST_RUNTIME_DIR / "data"
PYTEST_PASSWORD_FILE = PYTEST_RUNTIME_DIR / "password.enc"

sys.path.insert(0, str(ROOT))

# Mantiene los tests lejos de los datos reales del operador y hace Qt
# importable en ejecuciones headless de CI/local.
os.environ.setdefault("DUBLINISL_DATA_DIR", str(PYTEST_DATA_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# config.py descifra la contraseña durante el import. En CI no existe
# password.enc real, así que los tests usan un archivo cifrado temporal.
PYTEST_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
import secret_manager as _secret_manager

_secret_manager._ENC_FILE = PYTEST_PASSWORD_FILE
if not PYTEST_PASSWORD_FILE.exists():
    _secret_manager.encrypt_password("pytest-password")
