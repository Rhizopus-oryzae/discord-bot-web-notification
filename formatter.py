"""Discord message formatting helpers."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


DISCORD_MESSAGE_LIMIT = 2_000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_tags = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_tags += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_tags:
            self._ignored_tags -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_tags:
            self.parts.append(data)


def clean_html_text(value: str) -> str:
    """Strip HTML and normalize whitespace from RSS text."""

    parser = _TextExtractor()
    try:
        parser.feed(value or "")
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        # Malformed HTML should not stop the polling loop.
        text = re.sub(r"<[^>]*>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


def build_message(
    title: str,
    summary: str,
    link: str,
    max_length: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Build a bounded Discord message from one article."""

    title_text = clean_html_text(title) or "Artikel baru"
    hook_text = clean_html_text(summary)
    link_text = link.strip() or "URL artikel tidak tersedia."

    title_text = _truncate(title_text, max_length)
    link_text = _truncate(link_text, max_length)
    prefix = f"**{title_text}**\n\n"
    suffix = f"\n\n{link_text}"
    hook_limit = max_length - len(prefix) - len(suffix)
    hook_text = _truncate(hook_text, hook_limit)

    message = prefix + hook_text + suffix
    if len(message) <= max_length:
        return message

    # This only applies when the title and URL themselves nearly fill the
    # Discord limit. Keep the URL visible as long as possible.
    available_title = max_length - len("**" + suffix) - 2
    title_text = _truncate(title_text, max(1, available_title))
    message = f"**{title_text}**{suffix}"
    return _truncate(message, max_length)
