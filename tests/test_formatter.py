import unittest

from formatter import build_message, clean_html_text


class FormatterTests(unittest.TestCase):
    def test_clean_html_text_removes_markup_and_script(self):
        result = clean_html_text("<p>Hello <strong>world</strong></p><script>bad()</script>")
        self.assertEqual(result, "Hello world")

    def test_message_stays_within_discord_limit(self):
        message = build_message("Title", "x" * 5000, "https://example.test/article")
        self.assertLessEqual(len(message), 2000)
        self.assertIn("https://example.test/article", message)


if __name__ == "__main__":
    unittest.main()
