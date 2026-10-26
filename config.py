"""Application configuration loaded from .env and config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when the application configuration is invalid."""


@dataclass(frozen=True)
class SiteConfig:
    """Configuration for one monitored website."""

    site_id: str
    name: str
    enabled: bool
    rss_url: str
    channel_id: int | None


@dataclass(frozen=True)
class AppConfig:
    """Validated runtime configuration for the bot."""

    token: str
    default_channel_id: int | None
    poll_interval_minutes: int
    request_timeout_seconds: int
    database_path: Path
    config_path: Path
    rsshub_base_url: str
    initial_sync: str
    sites: tuple[SiteConfig, ...]


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} wajib diisi.")
    return value.strip()


def _positive_int(value: object, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{field_name} harus berupa angka.") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{field_name} harus lebih besar dari 0.")
    return parsed


def _optional_channel_id(value: object, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        channel_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{field_name} harus berupa angka.") from exc
    if channel_id <= 0:
        raise ConfigurationError(f"{field_name} harus lebih besar dari 0.")
    return channel_id


def _validate_url(value: object, field_name: str) -> str:
    url = _required_text(value, field_name)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"{field_name} harus berupa URL HTTP/HTTPS yang valid.")
    return url


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigurationError(f"File konfigurasi tidak ditemukan: {path}")
    try:
        raw_config = os.path.expandvars(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(raw_config) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Gagal membaca konfigurasi {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("Isi config.yaml harus berupa object/map.")
    return data


def load_config(
    config_path: str | Path = "config.yaml",
    env_path: str | Path | None = None,
) -> AppConfig:
    """Load and validate application configuration."""

    if env_path is None:
        load_dotenv()
    else:
        load_dotenv(dotenv_path=env_path)

    token = _required_text(os.getenv("DISCORD_TOKEN"), "DISCORD_TOKEN")
    default_channel_id = _optional_channel_id(
        os.getenv("DEFAULT_CHANNEL_ID", os.getenv("CHANNEL_ID")),
        "DEFAULT_CHANNEL_ID/CHANNEL_ID",
    )
    poll_interval_minutes = _positive_int(
        os.getenv("POLL_INTERVAL_MINUTES", "20"),
        "POLL_INTERVAL_MINUTES",
    )
    request_timeout_seconds = _positive_int(
        os.getenv("REQUEST_TIMEOUT_SECONDS", "20"),
        "REQUEST_TIMEOUT_SECONDS",
    )
    database_path = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))
    rsshub_base_url = _validate_url(
        os.getenv("RSSHUB_BASE_URL", "http://localhost:1200"),
        "RSSHUB_BASE_URL",
    ).rstrip("/")

    # Allow config.yaml to use ${RSSHUB_BASE_URL} while still providing a
    # useful localhost default when the variable is not present in .env.
    os.environ.setdefault("RSSHUB_BASE_URL", rsshub_base_url)
    config_path = Path(os.getenv("CONFIG_PATH", str(config_path)))
    data = _load_yaml(config_path)

    initial_sync = data.get("initial_sync", "skip_existing")
    if initial_sync not in {"skip_existing", "send_existing"}:
        raise ConfigurationError(
            "initial_sync harus bernilai 'skip_existing' atau 'send_existing'."
        )

    raw_sites = data.get("sites")
    if not isinstance(raw_sites, list) or not raw_sites:
        raise ConfigurationError("config.yaml harus memiliki minimal satu site.")

    sites: list[SiteConfig] = []
    site_ids: set[str] = set()
    for index, raw_site in enumerate(raw_sites, start=1):
        if not isinstance(raw_site, dict):
            raise ConfigurationError(f"Konfigurasi site #{index} harus berupa object/map.")

        site_id = _required_text(raw_site.get("id"), f"sites[{index}].id")
        if site_id in site_ids:
            raise ConfigurationError(f"ID site duplikat: {site_id}")
        site_ids.add(site_id)

        name = _required_text(raw_site.get("name", site_id), f"sites[{index}].name")
        enabled = raw_site.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigurationError(f"sites[{index}].enabled harus berupa boolean.")

        rss_url = _validate_url(raw_site.get("rss_url"), f"sites[{index}].rss_url")
        channel_id = _optional_channel_id(
            raw_site.get("channel_id"),
            f"sites[{index}].channel_id",
        )
        if enabled and channel_id is None and default_channel_id is None:
            raise ConfigurationError(
                f"Site aktif '{site_id}' tidak memiliki channel_id dan default channel.")

        sites.append(
            SiteConfig(
                site_id=site_id,
                name=name,
                enabled=enabled,
                rss_url=rss_url,
                channel_id=channel_id,
            )
        )

    return AppConfig(
        token=token,
        default_channel_id=default_channel_id,
        poll_interval_minutes=poll_interval_minutes,
        request_timeout_seconds=request_timeout_seconds,
        database_path=database_path,
        config_path=config_path,
        rsshub_base_url=rsshub_base_url,
        initial_sync=initial_sync,
        sites=tuple(sites),
    )
