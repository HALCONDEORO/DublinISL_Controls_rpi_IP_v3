import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PYTEST_RUNTIME_DIR = ROOT / ".pytest-runtime"
PYTEST_DATA_DIR = PYTEST_RUNTIME_DIR / "data"

sys.path.insert(0, str(ROOT))

# Keep test runs away from the operator's real persistent data and make Qt
# importable in headless CI/local verification runs.
os.environ.setdefault("DUBLINISL_DATA_DIR", str(PYTEST_DATA_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
