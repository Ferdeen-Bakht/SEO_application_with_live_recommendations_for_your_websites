import unittest
from seo_lab.audit_rules import audit_page


class AuditRulesTests(unittest.TestCase):
    def test_missing_title_is_flagged(self):
        page = {"status_code": 200, "title": "", "description": "Useful summary",
                "h1": "Main heading", "canonical": "https://example.test/",
                "robots": "index,follow", "h1_list": ["Main heading"]}
        self.assertIn("Missing title element", [f["issue"] for f in audit_page(page)])

    def test_multiple_h1s_are_info_not_a_penalty(self):
        page = {"status_code": 200, "title": "Good title", "description": "Good summary",
                "h1": "Main heading", "canonical": "https://example.test/",
                "robots": "index,follow", "h1_list": ["Main heading", "Another heading"]}
        findings = audit_page(page)
        issue = next(f for f in findings if f["issue"] == "Multiple H1 headings detected")
        self.assertEqual(issue["severity"], "info")

    def test_noindex_is_flagged(self):
        page = {"status_code": 200, "title": "Good title", "description": "Good summary",
                "h1": "Main heading", "canonical": "https://example.test/",
                "robots": "noindex,follow", "h1_list": ["Main heading"]}
        self.assertIn("A robots meta directive contains noindex", [f["issue"] for f in audit_page(page)])


if __name__ == "__main__":
    unittest.main()
