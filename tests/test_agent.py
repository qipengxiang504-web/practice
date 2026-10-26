from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from agent import Article, BASE_DIR, canonical_url, main, parse_date, parse_feed, select_articles


class DigestTests(unittest.TestCase):
    def test_demo_filters_unrelated_items_and_duplicates(self):
        articles = parse_feed((BASE_DIR / "examples" / "sample.xml").read_bytes(), "demo")
        result = select_articles(articles, ["融资", "创投"], datetime.now(timezone.utc), None, 10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].url, "https://example.com/robotics-series-a")

    def test_time_window_excludes_old_future_and_unknown_dates(self):
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        articles = [Article("funding", f"https://example.com/{i}", "demo", "", date)
                    for i, date in enumerate([now - timedelta(hours=1),
                                              now - timedelta(hours=25),
                                              now + timedelta(hours=1), None])]
        result = select_articles(articles, ["funding"], now, 24, 10)
        self.assertEqual([item.url for item in result], ["https://example.com/0"])

    def test_atom_and_iso_timestamp(self):
        data = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Seed funding</title><link href="https://example.com/seed"/>
        <published>2026-01-01T08:00:00+08:00</published>
        <summary>New venture</summary></entry></feed>'''
        article = parse_feed(data, "atom")[0]
        self.assertEqual(article.published_at, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(parse_date("not a date"))
        self.assertIsNone(parse_date("2026-01-01T08:00:00"))

    def test_url_dedup_keeps_meaningful_query_parameters(self):
        self.assertEqual(canonical_url("https://example.com/post?id=2&utm_source=x#top"),
                         "https://example.com/post?id=2")

    def test_demo_runs_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "demo.md"
            with patch("agent.urlopen", side_effect=AssertionError("No network in demo")):
                self.assertEqual(main(["--demo", "--output", str(output)]), 0)
            report = output.read_text(encoding="utf-8")
            self.assertIn("虚构示例", report)
            self.assertIn("匹配资讯（2 条）", report)

    def test_all_sources_failing_does_not_write_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "digest.md"
            with patch("agent.urlopen", side_effect=URLError("offline")), patch("sys.stderr", io.StringIO()):
                self.assertEqual(main(["--output", str(output)]), 1)
            self.assertFalse(output.exists())

    def test_partial_failure_is_visible_in_report(self):
        data = (BASE_DIR / "examples" / "sample.xml").read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "digest.md"
            with patch("agent.urlopen", side_effect=[io.BytesIO(data), URLError("offline")]):
                self.assertEqual(main(["--output", str(output)]), 0)
            self.assertIn("Crunchbase News 读取失败", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
