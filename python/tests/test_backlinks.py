import unittest
from unittest import mock

import httpx

from seo_lab import backlinks as bl

RAW = """TITLE: How MetaTrader 5 works for newcomers
DESCRIPTION: A plain guide to the MetaTrader 5 platform.
TAGS: #Trading, fin-tech, MetaTrader 5, beginners, extra
BODY:
## What it is
MetaTrader 5 is a trading platform with many tools.

## Why it matters
Beginners can learn the layout first. """ + "More words here. " * 30


def response(status, payload=None, text=""):
    return httpx.Response(status, json=payload if payload is not None else {}, request=httpx.Request("POST", "https://dev.to/api/articles"), text=text or None)


class ArticleTests(unittest.TestCase):
    def test_parse_article_reads_layout_and_cleans_tags(self):
        a = bl.parse_article(RAW)
        self.assertEqual(a["title"], "How MetaTrader 5 works for newcomers")
        self.assertEqual(a["tags"], ["trading", "fintech", "metatrader", "5"])  # lowercase alphanumeric, at most 4
        self.assertTrue(a["body"].startswith("## What it is"))

    def test_parse_article_falls_back_to_a_heading_when_markers_are_missing(self):
        a = bl.parse_article("# A heading title\n\nSome body text. " * 3)
        self.assertEqual(a["title"], "A heading title")

    def test_finalize_adds_link_disclosure_and_risk_warning_once(self):
        body = bl.finalize_body("Intro text.", "ABET", "https://abetglobal.com/", True)
        self.assertIn("https://abetglobal.com/", body)
        self.assertIn("Risk warning", body)
        self.assertIn("Disclosure", body)
        self.assertEqual(bl.finalize_body(body, "ABET", "https://abetglobal.com/", True), body)  # idempotent

    def test_no_risk_warning_for_non_financial_topics(self):
        self.assertNotIn("Risk warning", bl.finalize_body("Intro text.", "Acme", "https://acme.dev/", False))

    def test_checks_flag_missing_link_and_profit_promises(self):
        checks = bl.article_checks("This is risk-free and guaranteed. " * 80, "https://abetglobal.com/", True, "some page text", "forex broker")
        by = {c["label"]: c for c in checks}
        self.assertFalse(by["Links to your website"]["ok"])
        self.assertFalse(by["No profit promises"]["ok"])
        self.assertFalse(by["Risk warning (financial topic)"]["ok"])

    def test_parse_article_accepts_markdown_dressed_labels_and_trims_cut_off_text(self):
        raw = ("### Title: MetaTrader 5 for beginners\n\n### Description: A short guide.\n\n### Tags: mt5, trading\n\n### Body:\n\n"
               "#### What is it\n\nA platform with tools for charting and analysis that newcomers can learn step by step over time.\n\n"
               "#### Key benefits\n\n- Charts\n- Indicators\n\n#### What Is")
        a = bl.parse_article(raw)
        self.assertEqual(a["title"], "MetaTrader 5 for beginners")
        self.assertEqual(a["tags"], ["mt5", "trading"])
        self.assertTrue(a["body"].startswith("## What is it"))  # headings shifted to dev.to-friendly level
        self.assertNotIn("What Is", a["body"].split("Key benefits")[-1])  # the dangling heading is gone
        self.assertTrue(a["body"].rstrip().endswith("- Indicators"))

    def test_calls_to_action_are_flagged(self):
        body = "A fine guide. To get started, sign up today and start trading. " * 20
        checks = {c["label"]: c for c in bl.article_checks(body, "https://x.com/", True, "text", "kw")}
        self.assertFalse(checks["Reads as education, not an advert"]["ok"])

    def test_advert_style_sections_are_removed(self):
        body = "Intro paragraph here.\n\n## What it is\n\nUseful text.\n\n## How to Get Started with X on ABET?\n\n1. Sign up\n2. Deposit\n\n## Final thoughts\n\nWrap up."
        cleaned, removed = bl.drop_cta_sections(body)
        self.assertEqual(removed, ["How to Get Started with X on ABET?"])
        self.assertIn("Final thoughts", cleaned)
        self.assertNotIn("Deposit", cleaned)

    def test_generate_article_fills_in_a_missing_title_and_description(self):
        text = "TAGS: mt5\nBODY:\n## What it is\n\n" + "A platform with many tools for charting and analysis. " * 20
        page = {"title": "MT5 | ABET", "h1": "MetaTrader 5", "metaDescription": "d", "body_text": "MetaTrader 5 trading platform tools", "url": "https://abetglobal.com/meta-trader-5/"}
        with mock.patch.object(bl.local_llm, "chat_text", side_effect=[text, "MetaTrader 5 explained for beginners"]):
            art = bl.generate_article(page, "MetaTrader 5", [{"title": "Home | ABET"}], "https://abetglobal.com")
        self.assertEqual(art["title"], "MetaTrader 5 explained for beginners")
        self.assertTrue(art["description"])
        self.assertIn("https://abetglobal.com/meta-trader-5/", art["body"])
        self.assertIn("Disclosure", art["body"])

    def test_plain_title_lines_become_headings_and_repeated_title_is_dropped(self):
        raw = ("TITLE: Property Search in Pakistan\nBODY:\nProperty Search in Pakistan\n"
               "This portal lets people search for homes and plots by city, type and price range across the country every day.\n"
               "Search Property for Sale and Rent\n"
               "You can filter results by location, type and price range to find the homes and plots that match your own needs.\n")
        a = bl.parse_article(raw)
        self.assertNotIn("Property Search in Pakistan\nThis portal", a["body"])  # repeated title line removed
        self.assertIn("## Search Property for Sale and Rent", a["body"])

    def test_unverified_superlatives_are_flagged(self):
        checks = {c["label"]: c for c in bl.article_checks("Pakistan's largest real estate portal. " * 30, "https://x.com/", False, "text", "kw")}
        self.assertFalse(checks["No unverified superlatives"]["ok"])
        self.assertIn("largest", checks["No unverified superlatives"]["detail"])

    def test_placeholder_text_from_the_template_is_not_used_as_a_title(self):
        raw = ("TITLE: <a clear, honest title under 70 characters>\nDESCRIPTION: <one sentence summary under 150 characters>\n"
               "TAGS: <up to 4 single-word lowercase tags, comma separated>\nBODY:\n## What it is\n\nA useful body paragraph here.")
        a = bl.parse_article(raw)
        self.assertEqual((a["title"], a["description"], a["tags"]), ("", "", []))

    def test_missing_placeholder_title_is_replaced_by_a_real_one(self):
        text = ("TITLE: <a clear, honest title under 70 characters>\nDESCRIPTION: (your one-sentence summary here)\nTAGS: mt5\nBODY:\n## What it is\n\n"
                + "A platform with many tools for charting and analysis. " * 20)
        page = {"title": "MT5 | ABET", "h1": "MetaTrader 5", "metaDescription": "d", "body_text": "MetaTrader 5 trading platform tools", "url": "https://abetglobal.com/meta-trader-5/"}
        with mock.patch.object(bl.local_llm, "chat_text", side_effect=[text, "MetaTrader 5 explained for beginners"]):
            art = bl.generate_article(page, "MetaTrader 5", [{"title": "Home | ABET"}], "https://abetglobal.com")
        self.assertEqual(art["title"], "MetaTrader 5 explained for beginners")
        self.assertNotIn("(your", art["description"])
        self.assertNotIn("<", art["description"])


class RecommendTests(unittest.TestCase):
    def test_trading_site_gets_trading_places_and_five_results(self):
        names = [e["name"] for e in bl.recommend_sites(["forex broker", "crypto trading platform"], "MetaTrader 5 CFD trading")]
        self.assertEqual(len(names), 5)
        self.assertIn("Reddit r/Forex", names)
        self.assertNotIn("TradingView", names)  # its house rules ban links in ideas

    def test_software_site_gets_developer_places(self):
        names = [e["name"] for e in bl.recommend_sites(["web app development company"], "We build web and mobile apps for developers")]
        self.assertIn("Hashnode", names)

    def test_every_recommendation_has_a_link_and_a_rules_note(self):
        for e in bl.recommend_sites(["anything"], ""):
            self.assertTrue(e["url"].startswith("https://"))
            self.assertTrue(e["rules"])


class PublishTests(unittest.TestCase):
    def test_draft_is_the_default_and_payload_is_correct(self):
        sent = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            sent.update(url=url, json=json, headers=headers)
            return response(201, {"id": 7, "url": "https://dev.to/u/post-123", "published": False})
        with mock.patch.object(bl.httpx, "post", side_effect=fake_post):
            out = bl.publish_to_devto("KEY", "Title", "Body", ["Trading", "fin-tech"], "desc")
        self.assertEqual(sent["url"], "https://dev.to/api/articles")
        self.assertEqual(sent["headers"]["api-key"], "KEY")
        self.assertIs(sent["json"]["article"]["published"], False)
        self.assertEqual(sent["json"]["article"]["tags"], ["trading", "fintech"])
        self.assertEqual(out, {"id": 7, "url": "https://dev.to/u/post-123", "published": False, "updated": False})

    def test_public_publish_sets_the_flag(self):
        with mock.patch.object(bl.httpx, "post", return_value=response(201, {"id": 1, "url": "u", "published": True})) as post:
            bl.publish_to_devto("KEY", "T", "B", [], published=True)
        self.assertIs(post.call_args.kwargs["json"]["article"]["published"], True)

    def test_errors_are_readable_and_never_contain_the_key(self):
        for status, payload, expect in [(401, {}, "rejected"), (429, {}, "rate limit"), (422, {"error": "Title is too long"}, "Title is too long")]:
            with mock.patch.object(bl.httpx, "post", return_value=response(status, payload)):
                with self.assertRaises(bl.PublishError) as ctx:
                    bl.publish_to_devto("SECRETKEY", "T", "B", [])
            self.assertIn(expect, str(ctx.exception))
            self.assertNotIn("SECRETKEY", str(ctx.exception))

    def test_missing_key_is_reported_without_a_request(self):
        with mock.patch.object(bl.httpx, "post") as post:
            with self.assertRaises(bl.PublishError):
                bl.publish_to_devto("", "T", "B", [])
        post.assert_not_called()


class SaveToDevtoTests(unittest.TestCase):
    def test_publishing_an_existing_draft_updates_it_instead_of_creating_a_duplicate(self):
        calls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append(("GET", url))
            return response(200, [{"id": 5, "title": "Other"}, {"id": 42, "title": "My Article ", "url": "https://dev.to/u/my-article-temp-slug"}])

        def fake_put(url, json=None, headers=None, timeout=None):
            calls.append(("PUT", url, json["article"]["published"]))
            return response(200, {"id": 42, "url": "https://dev.to/u/my-article", "published": True})
        with mock.patch.object(bl.httpx, "get", side_effect=fake_get), mock.patch.object(bl.httpx, "put", side_effect=fake_put), \
                mock.patch.object(bl.httpx, "post") as post:
            out = bl.save_to_devto("KEY", "my article", "Body", ["a"], "d", published=True)
        post.assert_not_called()  # no second "create" request: that is what dev.to answered with "Title has already been used"
        self.assertIn(("PUT", "https://dev.to/api/articles/42", True), calls)
        self.assertEqual((out["id"], out["updated"], out["published"]), (42, True, True))

    def test_known_id_skips_the_lookup(self):
        with mock.patch.object(bl.httpx, "get") as get, mock.patch.object(bl.httpx, "put", return_value=response(200, {"id": 9, "url": "u", "published": False})):
            out = bl.save_to_devto("KEY", "T", "B", [], published=False, known_id=9)
        get.assert_not_called()
        self.assertTrue(out["updated"])

    def test_creates_when_no_draft_exists(self):
        with mock.patch.object(bl.httpx, "get", return_value=response(200, [])), \
                mock.patch.object(bl.httpx, "post", return_value=response(201, {"id": 1, "url": "u", "published": False})) as post:
            out = bl.save_to_devto("KEY", "Brand new title", "B", [], published=False)
        post.assert_called_once()
        self.assertFalse(out["updated"])


if __name__ == "__main__":
    unittest.main()
