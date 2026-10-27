"""Simple, explainable checks. Findings are hints for a human, not ranking verdicts."""
from urllib.parse import urlparse


def audit_page(page: dict) -> list[dict]:
    findings = []
    title = (page.get("title") or "").strip()
    description = (page.get("description") or "").strip()
    h1 = (page.get("h1") or "").strip()
    canonical = (page.get("canonical") or "").strip()
    robots = (page.get("robots") or "").lower()
    status = int(page.get("status_code") or 0)

    if status != 200:
        findings.append({"severity": "high", "issue": f"HTTP status is {status}",
                         "why": "Search engines and users need the intended page to be accessible.",
                         "suggestion": "Check the URL, redirects, server logs, and whether this status is intentional."})
    if not title:
        findings.append({"severity": "high", "issue": "Missing title element",
                         "why": "The title helps users and search engines understand the page.",
                         "suggestion": "Write a unique, accurate title that describes this page."})
    elif len(title) > 65:
        findings.append({"severity": "review", "issue": "Title is relatively long",
                         "why": "Search engines may shorten displayed title links; there is no universal character limit that guarantees display.",
                         "suggestion": "Review whether the most useful words appear early; do not shorten mechanically."})
    if not description:
        findings.append({"severity": "medium", "issue": "Missing meta description",
                         "why": "Google may use the page text or meta description for the search snippet.",
                         "suggestion": "Consider writing a page-specific, accurate summary that helps a searcher decide whether to visit."})
    elif len(description) > 180:
        findings.append({"severity": "review", "issue": "Meta description is relatively long",
                         "why": "Search snippets vary by query and device; a fixed character count does not guarantee display.",
                         "suggestion": "Review for repetition and put the main benefit early. Do not treat length alone as an error."})
    if not h1:
        findings.append({"severity": "medium", "issue": "No H1 heading found",
                         "why": "A clear main heading can help people understand the page structure.",
                         "suggestion": "Check whether the page needs a visible, descriptive main heading."})
    if not canonical:
        findings.append({"severity": "review", "issue": "No canonical link found",
                         "why": "Canonical links can help when duplicate or similar URLs need a preferred URL; they are not mandatory for every page.",
                         "suggestion": "Check URL variants and duplicate content before adding a canonical."})
    if "noindex" in robots:
        findings.append({"severity": "high", "issue": "A robots meta directive contains noindex",
                         "why": "If Google can crawl the page and sees noindex, it can exclude the page from Search.",
                         "suggestion": "Verify this is intentional. Do not automatically remove it; robots.txt blocking can prevent Google from seeing noindex."})
    if canonical:
        try:
            if urlparse(canonical).scheme not in {"http", "https"}:
                findings.append({"severity": "review", "issue": "Unusual canonical URL scheme",
                                 "why": "Canonical URLs should point to the intended page URL.",
                                 "suggestion": "Verify that the canonical is a valid absolute HTTP(S) URL."})
        except ValueError:
            pass
    if len(page.get("h1_list", [])) > 1:
        findings.append({"severity": "info", "issue": "Multiple H1 headings detected",
                         "why": "This is not automatically a Google penalty; inspect the page's heading structure in context.",
                         "suggestion": "Make the document structure clear for readers, without changing headings solely to satisfy a count."})
    findings += _extra_checks(page)
    return findings


def _extra_checks(page: dict) -> list[dict]:
    """More on-page checks, read from the page's measured metrics. Pages crawled before these metrics existed are skipped."""
    m = page.get("metrics") or {}
    if not m:
        return []
    out = []

    def add(severity, issue, why, suggestion):
        out.append({"severity": severity, "issue": issue, "why": why, "suggestion": suggestion})

    title = (page.get("title") or "").strip()
    if title and len(title) < 10:
        add("review", "Title is very short", "A very short title says little about the page.", "Describe the page in more specific words.")
    if m.get("word_count", 999) < 200 and int(page.get("status_code") or 0) == 200:
        add("review", f"Low word count ({m['word_count']} words)", "Pages with very little text give search engines little to understand; some pages (contact, login) are fine this way.",
            "If the page should rank for something, add specific, useful content.")
    if "text_ratio" in m and m["text_ratio"] < 10 and int(page.get("status_code") or 0) == 200:
        add("review", f"Low text-to-HTML ratio ({m['text_ratio']}%)", "Most of this page's HTML is code, not readable text. It can mean heavy markup or little content, and may slow crawling.",
            "Remove unused markup, scripts or inline styles, or add useful text content.")
    if m.get("images_missing_alt", 0):
        add("review", f"{m['images_missing_alt']} image(s) without alt text", "Alt text describes images for people using screen readers and for image search.",
            "Add a short, accurate alt to meaningful images; decorative images can use an empty alt.")
    if m.get("is_https") and m.get("mixed_content"):
        add("high", f"Mixed content: {len(m['mixed_content'])} insecure resource(s) on an HTTPS page", "Browsers may block or warn about http:// files loaded by an https:// page.",
            "Load these resources over https://: " + ", ".join(m["mixed_content"][:3]))
    if m.get("has_viewport") is False:
        add("review", "No viewport meta tag", "Without it, mobile browsers show the desktop layout shrunk down.", "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.")
    if m.get("has_lang") is False:
        add("info", "No lang attribute on <html>", "The language helps screen readers and search engines pick the right audience.", "Add lang=\"en\" (or the right language) to the html tag.")
    if len(page.get("url", "")) > 200:
        add("info", "Very long URL", "Long URLs are harder to read and share.", "Use a shorter, descriptive path if you can change it safely with a redirect.")
    return out
