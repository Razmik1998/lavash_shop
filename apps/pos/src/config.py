"""Environment-based configuration. No secrets in source code."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_environment() -> None:
    # Dev-mode: search CWD and parent directories for a `.env` (unchanged).
    load_dotenv()
    # Production (installed, frozen) layout: an explicit, installer-managed
    # config file. Only consulted if present, and never overrides a value
    # already set by the real environment or the dev `.env` above.
    program_data_env = (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "FishShop"
        / "config"
        / ".env"
    )
    if program_data_env.is_file():
        load_dotenv(program_data_env, override=False)


_load_environment()


def _resolve_receipt_directory(raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    # Relative path: keep the exact dev behavior (CWD-relative) when running
    # from source. A frozen build's CWD is unpredictable and not guaranteed
    # writable, so resolve against a fixed, writable, per-machine location
    # instead (sys.frozen is the standard PyInstaller marker).
    if getattr(sys, "frozen", False):
        base = (
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            / "FishShop"
            / "data"
        )
        return base / path
    return path


@dataclass(frozen=True)
class Settings:
    admin_host: str
    admin_port: int
    terminal_id: str
    printer_name: str | None
    store_name: str
    store_phone_numbers: tuple[str, ...]
    store_address: str
    receipt_paper_width_mm: int
    receipt_directory: Path
    printer_enabled: bool
    receipt_chars_per_line: int
    receipt_cut: bool
    online_order_url: str
    receipt_language: str


def load_settings() -> Settings:
    admin_host = os.environ.get("ADMIN_HOST", "127.0.0.1")
    admin_port = int(os.environ.get("ADMIN_PORT", "8765"))
    terminal_id = os.environ.get("POS_TERMINAL_ID", "").strip()
    if not terminal_id:
        raise RuntimeError(
            "POS_TERMINAL_ID is not set. Copy .env.example to .env and configure it."
        )
    paper_width = int(os.environ.get("RECEIPT_PAPER_WIDTH", "80"))
    if paper_width not in (58, 80):
        raise RuntimeError("RECEIPT_PAPER_WIDTH must be 58 or 80")
    chars_per_line = int(os.environ.get("RECEIPT_CHARS_PER_LINE", "48"))
    if not 32 <= chars_per_line <= 48:
        raise RuntimeError("RECEIPT_CHARS_PER_LINE must be between 32 and 48")
    receipt_language = os.environ.get("RECEIPT_LANGUAGE", "en").strip().lower()
    if receipt_language not in {"en", "hy"}:
        raise RuntimeError("RECEIPT_LANGUAGE must be 'en' or 'hy'")
    phone_numbers = tuple(
        number.strip()
        for number in os.environ.get("STORE_PHONE_NUMBERS", "").split(",")
        if number.strip()
    )
    return Settings(
        admin_host=admin_host,
        admin_port=admin_port,
        terminal_id=terminal_id,
        printer_name=(
            os.environ.get(
                "PRINTER_NAME",
                os.environ.get("POS_PRINTER_NAME", "XP-80C"),
            ).strip()
            or None
        ),
        store_name=os.environ.get("STORE_NAME", "").strip(),
        store_phone_numbers=phone_numbers,
        store_address=os.environ.get("STORE_ADDRESS", "").strip(),
        receipt_paper_width_mm=paper_width,
        receipt_directory=_resolve_receipt_directory(
            os.environ.get("RECEIPT_DIRECTORY", "receipts")
        ),
        printer_enabled=os.environ.get("PRINTER_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        receipt_chars_per_line=chars_per_line,
        receipt_cut=os.environ.get("RECEIPT_CUT", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        online_order_url=os.environ.get(
            "ONLINE_ORDER_URL", "https://example.com/order"
        ).strip(),
        receipt_language=receipt_language,
    )
