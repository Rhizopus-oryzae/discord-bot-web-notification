import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from feed import fetch_feed


class FeedTests(unittest.TestCase):
    @patch("feed.feedparser.parse")
    @patch("feed.requests.get")
    def test_fetch_feed_returns_all_entries_in_chronological_order(
        self,
        mock_get,
        mock_parse,
    ):
        mock_get.return_value = SimpleNamespace(
            content=b"rss",
            raise_for_status=lambda: None,
        )
        mock_parse.return_value = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "id": "new",
                    "title": "New",
                    "link": "https://example.test/new",
                    "published_parsed": time.gmtime(200),
                },
                {
                    "id": "old",
                    "title": "Old",
                    "link": "https://example.test/old",
                    "published_parsed": time.gmtime(100),
                },
            ],
        )

        entries = fetch_feed("https://rss.test/feed", timeout_seconds=5)

        self.assertEqual([entry.post_id for entry in entries], ["old", "new"])
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
