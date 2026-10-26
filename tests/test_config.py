import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ConfigurationError, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_modular_sites_and_expands_rsshub_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_path = root / ".env"
            config_path = root / "config.yaml"
            env_path.write_text(
                "DISCORD_TOKEN=test-token\n"
                "DEFAULT_CHANNEL_ID=123456789\n"
                "RSSHUB_BASE_URL=http://rsshub.test:1200\n",
                encoding="utf-8",
            )
            config_path.write_text(
                "sites:\n"
                "  - id: first\n"
                "    name: First\n"
                "    enabled: true\n"
                "    rss_url: ${RSSHUB_BASE_URL}/first\n"
                "  - id: second\n"
                "    name: Second\n"
                "    enabled: false\n"
                "    rss_url: https://example.test/feed\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                config = load_config(config_path=config_path, env_path=env_path)

            self.assertEqual(config.sites[0].rss_url, "http://rsshub.test:1200/first")
            self.assertFalse(config.sites[1].enabled)

    def test_rejects_duplicate_site_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_path = root / ".env"
            config_path = root / "config.yaml"
            env_path.write_text(
                "DISCORD_TOKEN=test-token\nDEFAULT_CHANNEL_ID=123456789\n",
                encoding="utf-8",
            )
            config_path.write_text(
                "sites:\n"
                "  - id: duplicate\n"
                "    rss_url: https://example.test/one\n"
                "  - id: duplicate\n"
                "    rss_url: https://example.test/two\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_config(config_path=config_path, env_path=env_path)


if __name__ == "__main__":
    unittest.main()
