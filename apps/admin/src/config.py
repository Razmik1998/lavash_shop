"""Environment-based configuration. No secrets in source code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_lan_port: int
    business_timezone: str = "Asia/Yerevan"
    web_sync_url: str | None = None
    web_sync_api_key: str | None = None


def load_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and configure it."
        )
    admin_lan_port = int(os.environ.get("ADMIN_LAN_PORT", "8765"))
    business_timezone = os.environ.get("BUSINESS_TIMEZONE", "Asia/Yerevan")
    try:
        ZoneInfo(business_timezone)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError("BUSINESS_TIMEZONE is not a valid timezone.") from exc
    # Optional: only needed to enable "Synchronize with Web" in the
    # Products screen. Left unset, that button stays hidden.
    web_sync_url = os.environ.get("ADMIN_WEB_SYNC_URL") or None
    web_sync_api_key = os.environ.get("ADMIN_WEB_SYNC_API_KEY") or None
    return Settings(
        database_url=database_url,
        admin_lan_port=admin_lan_port,
        business_timezone=business_timezone,
        web_sync_url=web_sync_url,
        web_sync_api_key=web_sync_api_key,
    )
