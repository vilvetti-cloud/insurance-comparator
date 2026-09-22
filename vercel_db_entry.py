"""Vercel entrypoint with PostgreSQL-backed persistence.

The legacy app.py is loaded through a small compatibility layer because it
still creates templates and starts an import-time worker. The worker remains
disabled on Vercel; data access is redirected to db.py instead.
"""

import builtins
import importlib.util
import io
import os
from pathlib import Path
import threading


ROOT = Path(__file__).resolve().parent
APP_FILE = ROOT / "app.py"

_original_open = builtins.open
_original_makedirs = os.makedirs
_original_thread = threading.Thread


class _NoOpTextFile(io.StringIO):
    """Discard legacy template-generation writes during import."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


def _vercel_open(file, mode="r", *args, **kwargs):
    try:
        path = Path(file)
        relative = path if not path.is_absolute() else path.relative_to(ROOT)
        normalized = relative.as_posix()
    except (TypeError, ValueError):
        normalized = str(file).replace("\\", "/")

    if "w" in mode and normalized in {
        "templates/index.html",
        "templates/result.html",
    }:
        return _NoOpTextFile()

    return _original_open(file, mode, *args, **kwargs)


def _vercel_makedirs(name, mode=0o777, exist_ok=False):
    normalized = str(name).replace("\\", "/").rstrip("/")
    if normalized == "templates" or normalized.endswith("/templates"):
        return None
    return _original_makedirs(name, mode=mode, exist_ok=exist_ok)


class _DisabledStartupThread:
    """Prevent the long import-time refresh from running in a serverless function."""

    def __init__(self, *args, **kwargs):
        self.daemon = kwargs.get("daemon", False)

    def start(self):
        return None


builtins.open = _vercel_open
os.makedirs = _vercel_makedirs
threading.Thread = _DisabledStartupThread

try:
    spec = importlib.util.spec_from_file_location("insurance_comparator_app", APP_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Не удалось загрузить app.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
finally:
    builtins.open = _original_open
    os.makedirs = _original_makedirs
    threading.Thread = _original_thread


# PostgreSQL is the persistent source of truth when DATABASE_URL exists.
# The legacy JSON implementation remains the local-development fallback.
import db
from core.services.comparison_service import ComparisonService

db.init_db()
comparison_service = ComparisonService()

legacy_load_data = module.load_data
legacy_save_data = module.save_data


def load_data():
    # The normalized collector tables are the primary source for the UI.
    data = comparison_service.load_snapshot()
    if data:
        return data

    # app_state is kept as a migration fallback for deployments that have not
    # collected normalized conditions yet.
    data = db.load_data()
    if data:
        return data

    return legacy_load_data()


def save_data(data):
    if db._database_url():
        return db.save_data(data)
    return legacy_save_data(data)


module.load_data = load_data
module.save_data = save_data
module.DATA_FILE = str(ROOT / "insurance_data.json")

app = module.app
