"""RSS fetching and normalization."""

from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests


class FeedError(RuntimeError):
    """Raised when a feed cannot be fetched or parsed."""


@dataclass(frozen=True)
class FeedEntry:
    """Normalized article data used by the rest of the application."""

    post_id: str
    title: str
    link: str
    summary: str
    published_timestamp: float | None


def _entry_timestamp(entry: Any) -> float | None:
    for field_name in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field_name)
        if parsed:
            try:
                return time.mktime(parsed)
            except (OverflowError, TypeError, ValueError):
                pass

    for field_name in ("published", "updated"):
        value = entry.get(field_name)
        if not value or not isinstance(value, str):
            continue
        try:
            return parsedate_to_datetime(value).timestamp()
        except (TypeError, ValueError, OverflowError):
            pass
    return None


def _normalize_entry(entry: Any) -> FeedEntry | None:
    link = str(entry.get("link") or "").strip()
    post_id = str(entry.get("id") or entry.get("guid") or link).strip()
    if not post_id:
        return None

    title = str(entry.get("title") or "Artikel baru").strip() or "Artikel baru"
    summary = str(entry.get("summary") or entry.get("description") or "").strip()
    return FeedEntry(
        post_id=post_id,
        title=title,
        link=link,
        summary=summary,
        published_timestamp=_entry_timestamp(entry),
    )


def fetch_feed(url: str, timeout_seconds: int) -> list[FeedEntry]:
    """Fetch and normalize a feed using an explicit network timeout."""

    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "discord-blog-notification-bot/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FeedError(f"Gagal mengambil RSS {url}: {exc}") from exc

    parsed = feedparser.parse(response.content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        error = getattr(parsed, "bozo_exception", "format RSS tidak valid")
        raise FeedError(f"RSS {url} tidak valid: {error}")

    normalized: list[FeedEntry] = []
    seen_ids: set[str] = set()
    for raw_entry in parsed.entries:
        entry = _normalize_entry(raw_entry)
        if entry is None or entry.post_id in seen_ids:
            continue
        seen_ids.add(entry.post_id)
        normalized.append(entry)

    # RSS feeds conventionally list newest entries first. Reverse that order
    # when no timestamps are available; otherwise use the published dates for
    # predictable chronological delivery.
    if normalized and all(entry.published_timestamp is None for entry in normalized):
        normalized.reverse()
    else:
        normalized.sort(
            key=lambda entry: (
                entry.published_timestamp is None,
                entry.published_timestamp or 0,
            )
        )
    return normalized
