"""SQLite persistence for article deduplication and delivery state."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class SQLiteStorage:
    """Small SQLite repository used by the notification bot."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sent_posts (
                site_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                article_url TEXT,
                title TEXT,
                sent_at TEXT NOT NULL,
                discord_message_id TEXT,
                status TEXT NOT NULL DEFAULT 'sent',
                PRIMARY KEY (site_id, post_id)
            );

            CREATE TABLE IF NOT EXISTS site_state (
                site_id TEXT PRIMARY KEY,
                initialized_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def is_site_initialized(self, site_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM site_state WHERE site_id = ?",
            (site_id,),
        ).fetchone()
        return row is not None

    def mark_site_initialized(self, site_id: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT INTO site_state(site_id, initialized_at)
            VALUES (?, ?)
            ON CONFLICT(site_id) DO UPDATE SET initialized_at = excluded.initialized_at
            """,
            (site_id, timestamp),
        )
        self.connection.commit()

    def has_post(self, site_id: str, post_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM sent_posts WHERE site_id = ? AND post_id = ?",
            (site_id, post_id),
        ).fetchone()
        return row is not None

    def record_post(
        self,
        site_id: str,
        post_id: str,
        article_url: str,
        title: str,
        discord_message_id: str | None = None,
        status: str = "sent",
    ) -> None:
        if status not in {"sent", "skipped"}:
            raise ValueError("status harus berupa 'sent' atau 'skipped'.")
        timestamp = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT OR IGNORE INTO sent_posts(
                site_id, post_id, article_url, title, sent_at,
                discord_message_id, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site_id,
                post_id,
                article_url,
                title,
                timestamp,
                discord_message_id,
                status,
            ),
        )
        self.connection.commit()

    def record_baseline(self, site_id: str, entries: Iterable[object]) -> int:
        """Record current feed entries without sending them on first sync."""

        count = 0
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.connection:
            for entry in entries:
                self.connection.execute(
                    """
                    INSERT OR IGNORE INTO sent_posts(
                        site_id, post_id, article_url, title, sent_at,
                        discord_message_id, status
                    ) VALUES (?, ?, ?, ?, ?, NULL, 'skipped')
                    """,
                    (
                        site_id,
                        entry.post_id,
                        entry.link,
                        entry.title,
                        timestamp,
                    ),
                )
                count += 1
        return count

    def migrate_json(
        self,
        json_path: str | Path,
        legacy_site_id: str = "legacy",
    ) -> int:
        """Import the old list/dict JSON state when the database is empty."""

        path = Path(json_path)
        if not path.exists():
            return 0
        if self.connection.execute("SELECT 1 FROM sent_posts LIMIT 1").fetchone():
            return 0

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0

        imported = 0
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.connection:
            if isinstance(data, list):
                data = {legacy_site_id: data}
            if not isinstance(data, dict):
                return 0
            for site_id, post_ids in data.items():
                if not isinstance(site_id, str) or not isinstance(post_ids, list):
                    continue
                for post_id in post_ids:
                    if not isinstance(post_id, str) or not post_id:
                        continue
                    self.connection.execute(
                        """
                        INSERT OR IGNORE INTO sent_posts(
                            site_id, post_id, article_url, title, sent_at,
                            discord_message_id, status
                        ) VALUES (?, ?, NULL, NULL, ?, NULL, 'sent')
                        """,
                        (site_id, post_id, timestamp),
                    )
                    imported += 1
        return imported

    def close(self) -> None:
        self.connection.close()
