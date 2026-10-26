"""Discord entry point for the modular blog notification bot."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from pathlib import Path

import discord
from discord.ext import commands

from config import AppConfig, ConfigurationError, SiteConfig, load_config
from feed import FeedError, fetch_feed
from formatter import build_message
from storage import SQLiteStorage


LOGGER = logging.getLogger(__name__)


class NotificationBot(commands.Bot):
    """Discord bot with one guarded polling task."""

    def __init__(self, app_config: AppConfig, storage: SQLiteStorage):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.app_config = app_config
        self.storage = storage
        self.polling_task: asyncio.Task[None] | None = None
        self._storage_closed = False

    async def setup_hook(self) -> None:
        # setup_hook runs once per bot lifecycle, so reconnects cannot create
        # duplicate polling loops.
        self.polling_task = asyncio.create_task(self._poll_forever())

    async def on_ready(self) -> None:
        LOGGER.info("Bot berhasil login sebagai %s", self.user)

    async def _get_channel(self, channel_id: int):
        channel = self.get_channel(channel_id)
        if channel is not None:
            return channel
        return await self.fetch_channel(channel_id)

    async def _poll_site(self, site: SiteConfig) -> None:
        LOGGER.info("Memeriksa pembaruan dari %s", site.name)
        try:
            entries = await asyncio.to_thread(
                fetch_feed,
                site.rss_url,
                self.app_config.request_timeout_seconds,
            )
        except FeedError:
            LOGGER.exception("Gagal memproses RSS site %s", site.site_id)
            return

        initialized = self.storage.is_site_initialized(site.site_id)
        if not initialized and self.app_config.initial_sync == "skip_existing":
            baseline_count = self.storage.record_baseline(site.site_id, entries)
            self.storage.mark_site_initialized(site.site_id)
            LOGGER.info(
                "Sinkronisasi awal site %s selesai; %d artikel lama dilewati",
                site.site_id,
                baseline_count,
            )
            return

        pending_entries = [
            entry
            for entry in entries
            if not self.storage.has_post(site.site_id, entry.post_id)
        ]
        if not pending_entries:
            if not initialized:
                self.storage.mark_site_initialized(site.site_id)
            LOGGER.info("Tidak ada artikel baru dari %s", site.name)
            return

        channel_id = site.channel_id or self.app_config.default_channel_id
        if channel_id is None:
            LOGGER.error("Tidak ada channel Discord untuk site %s", site.site_id)
            return

        try:
            channel = await self._get_channel(channel_id)
        except discord.DiscordException:
            LOGGER.exception("Channel %s tidak dapat diakses", channel_id)
            return

        for entry in pending_entries:
            message = build_message(entry.title, entry.summary, entry.link)
            try:
                sent_message = await channel.send(
                    message,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.DiscordException:
                LOGGER.exception(
                    "Gagal mengirim artikel %s dari site %s",
                    entry.post_id,
                    site.site_id,
                )
                # Stop this site for the current cycle to preserve order and
                # retry the failed article on the next cycle.
                return

            self.storage.record_post(
                site_id=site.site_id,
                post_id=entry.post_id,
                article_url=entry.link,
                title=entry.title,
                discord_message_id=str(sent_message.id),
            )
            LOGGER.info("Artikel baru terkirim: %s", entry.title)

        if not initialized:
            self.storage.mark_site_initialized(site.site_id)

    async def _poll_once(self) -> None:
        for site in self.app_config.sites:
            if not site.enabled:
                continue
            try:
                await self._poll_site(site)
            except Exception:
                # A bug or unexpected provider response for one site must not
                # prevent the remaining sites from being checked.
                LOGGER.exception("Kesalahan tidak terduga pada site %s", site.site_id)

    async def _poll_forever(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            started_at = time.monotonic()
            await self._poll_once()
            elapsed = time.monotonic() - started_at
            wait_seconds = max(
                1,
                self.app_config.poll_interval_minutes * 60 - int(elapsed),
            )
            await asyncio.sleep(wait_seconds)

    async def close(self) -> None:
        if self.polling_task is not None:
            self.polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.polling_task
        if not self._storage_closed:
            self.storage.close()
            self._storage_closed = True
        await super().close()


def create_bot(app_config: AppConfig) -> NotificationBot:
    storage = SQLiteStorage(app_config.database_path)
    legacy_site_id = next(
        (site.site_id for site in app_config.sites if site.enabled),
        "legacy",
    )
    imported = storage.migrate_json(Path("sent_posts.json"), legacy_site_id)
    if imported:
        LOGGER.info("%d state artikel lama berhasil dimigrasikan", imported)
    return NotificationBot(app_config, storage)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        app_config = load_config()
    except ConfigurationError as exc:
        LOGGER.error("Konfigurasi tidak valid: %s", exc)
        return 2

    bot = create_bot(app_config)
    try:
        bot.run(app_config.token)
    except (discord.LoginFailure, discord.PrivilegedIntentsRequired) as exc:
        LOGGER.error("Gagal login ke Discord: %s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.info("Bot dihentikan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
