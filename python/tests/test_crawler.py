import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from seo_lab import crawler

N_PAGES = 60
REQUESTED: list[str] = []
SLOW = {"seconds": 0.0}
BODY = " ".join(f"word{i}" for i in range(60))  # enough text that no browser rendering is attempted


class Site(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        REQUESTED.append(self.path)
        if SLOW["seconds"]:
            time.sleep(SLOW["seconds"])
        if self.path.startswith("/p/"):
            i = int(self.path.split("/")[2].rstrip("/"))
            links = "".join(f'<a href="/p/{j}">p{j}</a>' for j in (i + 1, i + 2) if j < N_PAGES)
            links += '<a href="/p/0/">dup of home</a><a href="/files/report.pdf">pdf</a><a href="https://other.example/x">external</a>'
            body = f"<html><head><title>Page {i}</title></head><body><h1>Page {i}</h1><p>{BODY}</p>{links}</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()


class CrawlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Site)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        REQUESTED.clear()
        SLOW["seconds"] = 0.0

    def test_unlimited_follows_every_page_once_and_skips_assets(self):
        pages = crawler.crawl_site(f"{self.base}/p/0", max_pages=None, delay_seconds=0, render="never")
        urls = [p["url"] for p in pages]
        self.assertEqual(len(urls), N_PAGES)
        self.assertEqual(len(set(urls)), N_PAGES)  # "/p/0/" is the same page as "/p/0"
        self.assertIsNone(pages.stopped_by)
        self.assertFalse([r for r in REQUESTED if r.endswith(".pdf")])  # assets are never downloaded

    def test_limited_crawl_reports_that_it_stopped_at_the_limit(self):
        pages = crawler.crawl_site(f"{self.base}/p/0", max_pages=10, delay_seconds=0, render="never")
        self.assertEqual(len(pages), 10)
        self.assertEqual(pages.stopped_by, "limit")

    def test_safety_ceiling_applies_to_unlimited(self):
        with mock.patch.object(crawler, "HARD_LIMIT", 25):
            pages = crawler.crawl_site(f"{self.base}/p/0", max_pages=None, delay_seconds=0, render="never")
        self.assertEqual(len(pages), 25)
        self.assertEqual(pages.stopped_by, "limit")

    def test_time_limit_returns_partial_results(self):
        SLOW["seconds"] = 0.05
        pages = crawler.crawl_site(f"{self.base}/p/0", max_pages=None, delay_seconds=0, render="never", max_seconds=0.5)
        self.assertEqual(pages.stopped_by, "time")
        self.assertTrue(0 < len(pages) < N_PAGES)

    def test_progress_callback_counts_pages(self):
        seen = []
        crawler.crawl_site(f"{self.base}/p/0", max_pages=5, delay_seconds=0, render="never", progress=lambda n, u: seen.append(n))
        self.assertEqual(seen[-1], 5)


if __name__ == "__main__":
    unittest.main()
