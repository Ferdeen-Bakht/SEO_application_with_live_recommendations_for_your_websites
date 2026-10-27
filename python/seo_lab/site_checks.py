"""Site-wide checks that no single page can show: robots.txt, sitemap, soft 404s, duplicate titles, HTTPS/www redirects.

Everything is a read-only GET. Findings are suggestions for a developer; this tool never changes the site.
Every finding carries `urls`: the full URLs it is about (the exact address tested, or the affected pages), so nothing is vague.
"""
import re
import secrets
import xml.etree.ElementTree as ET
from collections import Counter

import httpx

from seo_lab.crawl_checks import crawl_derived_checks
from seo_lab.crawler import USER_AGENT
from seo_lab.site_state import site_label


def _f(key, name, status, detail, fix="", severity="medium", urls=None):
    """status: pass | warn | fail. urls: full URLs the finding is about."""
    return {"key": key, "name": name, "status": status, "detail": detail, "fix": fix, "severity": severity, "urls": urls or []}


def _is_html(r: httpx.Response) -> bool:
    return "html" in r.headers.get("content-type", "").lower()


def run_site_checks(base_url: str, pages: list[dict] | None = None) -> list[dict]:
    base = base_url.rstrip("/")
    host = base.split("//", 1)[-1]
    out = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=False, timeout=30) as client:
        # robots.txt
        robots_url = base + "/robots.txt"
        try:
            r = client.get(robots_url)
            ctype = r.headers.get("content-type", "unknown")
            if r.status_code == 200 and not _is_html(r):
                has_sitemap = "sitemap:" in r.text.lower()
                out.append(_f("robots", "robots.txt", "pass" if has_sitemap else "warn",
                              f"{robots_url} exists" + (" and lists a sitemap." if has_sitemap else " but has no Sitemap: line."),
                              "" if has_sitemap else "Add a line such as Sitemap: " + base + "/sitemap.xml", urls=[robots_url]))
            else:
                got = f"HTTP 200 with content-type {ctype}, which is your HTML app shell" if r.status_code == 200 else f"HTTP {r.status_code}"
                out.append(_f("robots", "robots.txt", "fail", f"{robots_url} returned {got} instead of a robots file.",
                              "Serve a real text file at /robots.txt (User-agent: *, Allow: /, Sitemap: ...). In Create React App put it in public/robots.txt.",
                              "high", urls=[robots_url]))
        except httpx.HTTPError as exc:
            out.append(_f("robots", "robots.txt", "warn", f"Could not fetch {robots_url} ({type(exc).__name__}).", urls=[robots_url]))

        # XML sitemap
        sitemap_url = base + "/sitemap.xml"
        try:
            r = client.get(sitemap_url)
            urls = []
            if r.status_code == 200 and not _is_html(r):
                try:
                    urls = [e.text.strip() for e in ET.fromstring(r.content).iter() if e.tag.endswith("loc") and e.text]
                except ET.ParseError:
                    pass
            if urls:
                out.append(_f("sitemap", "XML sitemap", "pass", f"{sitemap_url} lists {len(urls)} URLs.", urls=[sitemap_url]))
            else:
                what = (f"{sitemap_url} returned HTTP 200 with content-type {r.headers.get('content-type', 'unknown')} (your HTML app shell), not XML."
                        if r.status_code == 200 else f"{sitemap_url} returned HTTP {r.status_code}.")
                out.append(_f("sitemap", "XML sitemap", "fail", what,
                              "Publish /sitemap.xml listing every indexable page and submit it in Google Search Console.", "high", urls=[sitemap_url]))
        except httpx.HTTPError as exc:
            out.append(_f("sitemap", "XML sitemap", "warn", f"Could not fetch {sitemap_url} ({type(exc).__name__}).", urls=[sitemap_url]))

        # Soft 404: a URL that cannot exist should not answer 200.
        probe = f"{base}/this-page-does-not-exist-{secrets.token_hex(4)}"
        try:
            r = client.get(probe, follow_redirects=True)
            if r.status_code == 200:
                out.append(_f("soft404", "Unknown URLs return 404", "fail",
                              f"Example: we requested the made-up address {probe} and it answered HTTP 200 with a normal page "
                              f"(a 'soft 404'). Search engines may index junk addresses like this as duplicates of a real page.",
                              "Return a real 404 status for unknown addresses (a server rule that only serves known routes) and show a 'page not found' view, "
                              "or add noindex to that view.", "high", urls=[probe]))
            else:
                out.append(_f("soft404", "Unknown URLs return 404", "pass",
                              f"Example: the made-up address {probe} correctly returned HTTP {r.status_code}.", urls=[probe]))
        except httpx.HTTPError:
            pass

        # HTTPS and www consolidation.
        if base.startswith("https://"):
            http_url = f"http://{host}/"
            try:
                r = client.get(http_url)
                ok = r.status_code in {301, 308} and r.headers.get("location", "").startswith("https://")
                out.append(_f("https", "HTTP redirects to HTTPS", "pass" if ok else "warn",
                              f"{http_url} permanently redirects to {r.headers.get('location')}." if ok
                              else f"{http_url} answered HTTP {r.status_code} without a permanent redirect to https://.",
                              "" if ok else "Add a 301 redirect from http to https.", urls=[http_url]))
            except httpx.HTTPError:
                pass
            bare = site_label(base)
            alt = bare[4:] if bare.startswith("www.") else "www." + bare
            alt_url = f"https://{alt}/"
            try:
                r = client.get(alt_url)
                ok = r.status_code in {301, 308} and site_label(r.headers.get("location", "")) == bare
                out.append(_f("www", f"{alt} consolidates to {bare}", "pass" if ok else "warn",
                              f"{alt_url} redirects to {r.headers.get('location')}." if ok
                              else f"{alt_url} answered HTTP {r.status_code}; two host names may split ranking signals.",
                              "" if ok else f"301-redirect {alt_url} to https://{bare}/ .", urls=[alt_url]))
            except httpx.HTTPError:
                pass

    # Cross-page checks from the crawl (full URLs everywhere).
    good = [p for p in (pages or []) if p.get("status_code") == 200 and p.get("metrics")]
    if len(good) >= 2:
        for field, label in (("title", "page titles"), ("description", "meta descriptions")):
            by_value: dict[str, list[str]] = {}
            for p in good:
                value = (p.get(field) or "").strip()
                if value:
                    by_value.setdefault(value, []).append(p["url"])
            if not by_value:
                continue
            value, urls = max(by_value.items(), key=lambda kv: len(kv[1]))
            if len(urls) >= 2:
                out.append(_f(f"dup_{field}", f"Unique {label}", "fail",
                              f"{len(urls)} of {len(good)} pages share the same {field}: “{value[:90]}”.",
                              f"Give every page its own {field} (for React: react-helmet-async or per-page <title>/<meta> tags, ideally pre-rendered).", "high", urls=urls))
            else:
                out.append(_f(f"dup_{field}", f"Unique {label}", "pass", f"All {label} are unique."))
        no_h1 = [p["url"] for p in good if not p.get("h1")]
        if no_h1:
            out.append(_f("h1s", "Every page has an H1", "fail", f"{len(no_h1)} of {len(good)} pages have no H1.",
                          "Add one descriptive H1 per page containing that page's main topic.", "medium", urls=no_h1))
        shells = [p["url"] for p in good if p.get("rendered") and not p.get("raw_word_count")]
        if shells:
            out.append(_f("csr", "Content visible without JavaScript", "warn",
                          f"{len(shells)} of {len(good)} pages ship an empty HTML shell; the content only appears after JavaScript runs. Google can render JavaScript, "
                          "but later and less reliably; Bing, social-link previews and AI crawlers often cannot.",
                          "Pre-render or server-render the public pages (Next.js, Remix, react-snap/prerender, or a prerender service) so the HTML already contains the content.",
                          "high", urls=shells))
        thin = [(p["url"], p["metrics"]["word_count"]) for p in good if p["metrics"]["word_count"] < 150]
        if thin:
            out.append(_f("thin", "Content depth", "warn", f"{len(thin)} pages have fewer than 150 words: " + ", ".join(f"{u} ({w} words)" for u, w in thin[:6]) + ".",
                          "Expand with specific, true detail: process, technologies, industries served, case-study results, FAQs.", "medium", urls=[u for u, _ in thin]))
    out += crawl_derived_checks(base, good, pages or [])
    return out


def slugify(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.strip("/").lower()).strip("-") or "home"
