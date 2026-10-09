"""Root logging configuration for the POS app.

Configures three destinations before anything else runs (called first
in ``main()``): a rotating ``app.log`` with everything at INFO+, a
rotating ``error.log`` with ERROR/CRITICAL only (so operators can open one
small file to see just the problems), and a console stream for dev
visibility. Also installs a ``sys.excepthook`` so exceptions PySide6 would
otherwise swallow are still recorded.

Never logs secrets: callers must never pass the login password to any
logger call here or elsewhere (see networking/local_connection.py).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import types
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5


def _resolve_log_dir() -> Path:
    override = os.environ.get("LOG_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(program_data) / "FishShop" / "logs"
    return Path(__file__).resolve().parent.parent / "logs"


def configure_logging() -> None:
    log_dir = _resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT)

    app_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)

    error_handler = logging.handlers.RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(console_handler)

    sys.excepthook = _log_unhandled_exception


def _log_unhandled_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: types.TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger(__name__).critical(
        "unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
    )
