import tempfile
import unittest
from pathlib import Path

from feed import FeedEntry
from storage import SQLiteStorage


class StorageTests(unittest.TestCase):
    def test_deduplication_is_scoped_to_site(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "bot.sqlite3")
            try:
                self.assertFalse(storage.has_post("site-a", "same-id"))
                storage.record_post("site-a", "same-id", "url-a", "A")
                self.assertTrue(storage.has_post("site-a", "same-id"))
                self.assertFalse(storage.has_post("site-b", "same-id"))
            finally:
                storage.close()

    def test_baseline_entries_are_marked_as_known(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteStorage(Path(directory) / "bot.sqlite3")
            try:
                entries = [
                    FeedEntry(
                        post_id="post-1",
                        title="Post 1",
                        link="https://example.test/1",
                        summary="Summary",
                        published_timestamp=None,
                    )
                ]
                self.assertEqual(storage.record_baseline("site-a", entries), 1)
                self.assertTrue(storage.has_post("site-a", "post-1"))
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
