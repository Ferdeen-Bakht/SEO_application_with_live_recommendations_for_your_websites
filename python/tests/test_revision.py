import unittest

import pandas as pd

from seo_lab import benchmark as bm
from seo_lab.revision_tests import compare

P1 = "ABET LLC provides trading services, owned by Abet LLC, whose company number is A000000977, and whose registered address is 9 Cassius Webster Building, Anguilla."
P2 = ("ABET LLC provides trading on contracts for difference (CFDs), which are complex financial instruments that are traded on leverage, "
      "and foreign exchange. Given that leverage can be used both favorably and unfavorably, they are very risky. These products might not be "
      "suitable for all investors due to the possibility of losing all invested funds. Seek outside legal assistance if necessary.")
P3 = ("ABET LLC does not offer advice, input, or recommendations regarding buying, holding, or selling of a CFD. ABET LLC offers only "
      "execution-based services and is not a financial counselor.")
SOURCE = " ".join([P1, P2, P3])


class RevisionTests(unittest.TestCase):
    def test_rewrite_borrowed_from_another_paragraph_is_flagged(self):
        # the real failure: "Paragraph 2" came back containing paragraph 3's content
        proposed = "ABET LLC does not offer advice, input, or recommendations regarding buying, holding, or selling CFDs. They offer only execution-based services."
        t = compare("paragraph", P2, proposed, "forex broker", SOURCE, others=[P1, P3])
        self.assertNotEqual(t["verdict"], "Looks good")
        self.assertTrue(any("different paragraph" in n for n in t["notes"]))

    def test_dropping_most_of_the_original_cannot_be_looks_good(self):
        t = compare("paragraph", P2, "ABET LLC offers CFD trading.", "forex broker", SOURCE, others=[P1, P3])
        self.assertIn(t["verdict"], {"Review", "Risky", "Check facts"})

    def test_faithful_rewrite_can_still_pass(self):
        proposed = P2.replace("Given that", "Because").replace("necessary", "needed")
        t = compare("paragraph", P2, proposed, "forex broker", SOURCE, others=[P1, P3])
        self.assertEqual(t["verdict"], "Looks good")

    def test_match_competitor_pages_by_topic_and_structure_only(self):
        comp = pd.DataFrame([
            {"site": "a.com", "url": "https://a.com/risk-disclosure", "title": "Risk Disclosure | A", "h1": "Risk disclosure", "description": "d",
             "h2_list": "Leverage risk | Margin calls", "word_count": 900, "jsonld_types": "WebPage"},
            {"site": "a.com", "url": "https://a.com/", "title": "A broker", "h1": "Trade now", "description": "d", "h2_list": "Platforms", "word_count": 500, "jsonld_types": ""},
            {"site": "b.com", "url": "https://b.com/about", "title": "About us", "h1": "Team", "description": "d", "h2_list": "People", "word_count": 300, "jsonld_types": ""},
        ])
        page = {"path": "/risk/", "title": "Risk Disclosure", "h1": "Risk warning", "h2": ["Leverage"]}
        matches = bm.match_competitor_pages(page, comp)
        self.assertEqual([m["url"] for m in matches], ["https://a.com/risk-disclosure"])
        self.assertNotIn("body", matches[0])
        self.assertIn("Margin calls", bm.topic_gaps("leverage only", matches)[0])

    def test_copied_competitor_wording_is_rejected(self):
        ref = "We provide award winning execution only trading on contracts for difference with tight spreads and no dealing desk interference ever."
        proposed = "Our broker offers award winning execution only trading on contracts for difference with tight spreads and no dealing desk."
        t = compare("paragraph", P3, proposed, "forex broker", SOURCE, others=[P1, P2], reference_text=ref)
        self.assertTrue(any("Copies" in n for n in t["notes"]))
        self.assertEqual(t["verdict"], "Check facts")

    def test_leaning_on_competitor_vocabulary_is_flagged(self):
        ref = "Zephyr platform offers copy trading, social signals, webinars, bonuses, cashback, referral rewards and tournaments."
        proposed = "ABET LLC offers copy trading, social signals, webinars, bonuses, cashback and tournaments."
        t = compare("paragraph", P3, proposed, "forex broker", SOURCE, others=[P1, P2], reference_text=ref)
        self.assertNotEqual(t["verdict"], "Looks good")
        self.assertTrue(any("only on the competitor page" in n for n in t["notes"]))

    def test_rewrite_in_our_own_words_with_reference_still_passes(self):
        ref = "Compare spreads, platforms and regulation before choosing a broker for forex and gold trading."
        proposed = P2.replace("Given that", "Because").replace("necessary", "needed")
        t = compare("paragraph", P2, proposed, "forex broker", SOURCE, others=[P1, P3], reference_text=ref)
        self.assertEqual(t["verdict"], "Looks good")

    def test_new_paragraph_is_not_penalised_for_not_keeping_old_wording(self):
        new = "Traders can reach support by email, phone or WhatsApp. Support runs Monday to Friday and the company offers only execution-based services."
        t = compare("paragraph_new", SOURCE, new, "forex broker", SOURCE)
        self.assertNotEqual(t["verdict"], "Risky")


if __name__ == "__main__":
    unittest.main()
