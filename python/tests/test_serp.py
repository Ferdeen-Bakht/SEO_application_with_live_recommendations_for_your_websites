import unittest
from unittest import mock

from seo_lab import serp

FAKE = [
    {"url": "https://www.devsinc.com/", "title": "Devsinc", "snippet": ""},
    {"url": "https://example.org/x", "title": "Other", "snippet": ""},
    {"url": "https://blog.appcreatorz.com/post", "title": "Ours", "snippet": ""},
]


class SerpTests(unittest.TestCase):
    def test_rank_domains_matches_www_and_subdomains(self):
        pos = serp.rank_domains(FAKE, ["devsinc.com", "appcreatorz.com", "tkxel.com"])
        self.assertEqual(pos, {"devsinc.com": 1, "appcreatorz.com": 3, "tkxel.com": None})

    def test_check_rankings_caps_keywords_at_five_and_saves(self):
        with mock.patch.dict(serp.PROVIDERS, {"searxng": lambda q, d: FAKE}), mock.patch.object(serp, "_serp_file", mock.MagicMock()), mock.patch.object(serp, "ensure_searxng"):
            data = serp.check_rankings([f"k{i}" for i in range(8)], ["appcreatorz.com"], provider="searxng")
        self.assertEqual(len(data["keywords"]), 5)
        self.assertEqual(data["keywords"][0]["positions"]["appcreatorz.com"], 3)

    def test_searxng_json_parsing(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"results": [{"url": "https://a.com", "title": "A", "content": "c"}]}
        client = mock.MagicMock()
        client.__enter__.return_value.get.side_effect = [resp, mock.Mock(status_code=200, json=lambda: {"results": []})]
        with mock.patch.object(serp.httpx, "Client", return_value=client):
            self.assertEqual(serp._searxng("q", 10)[0]["url"], "https://a.com")

    def test_mojeek_parsing_and_missing_key(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"response": {"results": [{"url": "https://b.com", "title": "B", "desc": "d"}]}}
        with mock.patch.object(serp, "MOJEEK_API_KEY", "k"), mock.patch.object(serp.httpx, "get", return_value=resp):
            self.assertEqual(serp._mojeek("q", 10)[0]["snippet"], "d")
        with mock.patch.object(serp, "MOJEEK_API_KEY", ""):
            with self.assertRaises(RuntimeError):
                serp._mojeek("q", 10)

    def test_hints_say_when_we_are_missing(self):
        data = {"our_domain": "appcreatorz.com", "provider": "searxng", "depth": 30,
                "keywords": [{"keyword": "k", "positions": {"appcreatorz.com": None}, "top": [{"pos": 1, "url": "https://a.com", "title": "T"}]}]}
        self.assertIn("not in the top 30", serp.serp_hints(data)[0])

    def test_visibility_score_uses_search_positions_only(self):
        data = {"depth": 30, "domains": ["us.com", "a.com", "b.com"], "keywords": [
            {"keyword": "k1", "positions": {"us.com": None, "a.com": 1, "b.com": 30}},
            {"keyword": "k2", "positions": {"us.com": 15, "a.com": None, "b.com": None}}]}
        scores = serp.visibility_scores(data)
        self.assertEqual(scores["a.com"], 50.0)      # (1.0 + 0) / 2 * 100
        self.assertEqual(scores["us.com"], 26.7)     # (0 + 16/30) / 2 * 100
        self.assertEqual(scores["b.com"], 1.7)       # (1/30 + 0) / 2 * 100

    def test_top_competitor_prefers_the_closest_keyword_and_gives_the_exact_url(self):
        data = {"our_domain": "us.com", "keywords": [
            {"keyword": "crypto trading platform", "positions": {"us.com": None, "a.com": 3, "b.com": 1}, "urls": {"a.com": "https://a.com/c", "b.com": "https://b.com/c"}},
            {"keyword": "forex broker", "positions": {"us.com": 5, "a.com": 2, "b.com": 9}, "urls": {"a.com": "https://a.com/fx", "b.com": "https://b.com/fx"}}]}
        top = serp.top_competitor(data, "forex broker")
        self.assertEqual((top["domain"], top["url"], top["position"]), ("a.com", "https://a.com/fx", 2))
        overall = serp.top_competitor(data, "something unrelated")
        self.assertEqual((overall["domain"], overall["position"]), ("b.com", 1))
        self.assertIsNone(serp.top_competitor(None))


if __name__ == "__main__":
    unittest.main()
