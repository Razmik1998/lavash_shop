"""Root logging configuration for the Admin app.

Configures three destinations before anything else runs (called first
in ``main()``): a rotating ``app.log`` with everything at INFO+, a
rotating ``error.log`` with ERROR/CRITICAL only (so operators can open one
small file to see just the problems), and a console stream for dev
visibility. Also installs a ``sys.excepthook`` so exceptions PySide6 would
otherwise swallow are still recorded.

Never logs secrets: callers must mask ``DATABASE_URL`` before logging it.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
import types
from pathlib import Path

from native_stderr import suppress_macos_input_diagnostic

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
    suppress_macos_input_diagnostic()
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
    # Reconfiguration replaces only our handlers; preserve framework/test handlers.
    for handler in list(root.handlers):
        if (handler.get_name() or "").startswith("shop_admin."):
            root.removeHandler(handler)
            handler.close()
    handlers: list[logging.Handler] = [app_handler, error_handler, console_handler]
    for index, handler in enumerate(handlers):
        handler.set_name(f"shop_admin.{index}")
        root.addHandler(handler)

    sys.excepthook = _log_unhandled_exception
    threading.excepthook = _log_thread_exception
    logging.getLogger(__name__).info(
        "logging configured directory=%s", log_dir.resolve()
    )


def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit or args.exc_value is None:
        return
    logging.getLogger(__name__).critical(
        "unhandled thread exception thread=%s",
        args.thread.name if args.thread is not None else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


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


def mask_database_url(database_url: str) -> str:
    """Redact the password portion of a Postgres DSN for safe logging."""
    scheme_sep = database_url.find("://")
    at_sep = database_url.rfind("@")
    if scheme_sep == -1 or at_sep == -1 or at_sep < scheme_sep:
        return database_url
    credentials = database_url[scheme_sep + 3 : at_sep]
    colon_sep = credentials.find(":")
    if colon_sep == -1:
        return database_url
    user = credentials[:colon_sep]
    return f"{database_url[: scheme_sep + 3]}{user}:***{database_url[at_sep:]}"
