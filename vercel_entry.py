"""Vercel entrypoint for the existing Flask application.

The current Render version of app.py still creates its templates and starts a
background data refresh at import time. Vercel functions have an immutable
application filesystem, and long-running startup work is not appropriate for
a serverless function. This adapter keeps the existing application logic
intact while making the current version safe to import on Vercel.
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
    """Discard template-generation writes during app import."""

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
    """Prevent the import-time data refresh from running on Vercel."""

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


app = module.app
module.DATA_FILE = str(ROOT / "insurance_data.json")
