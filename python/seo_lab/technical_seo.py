"""Technical SEO checks for one page: crawlability, canonical URL, XML sitemap, image alt text, broken links."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from seo_lab.crawler import USER_AGENT, _validate_start_url
from seo_lab.page_metrics import extract_metrics
from seo_lab.renderer import Renderer, looks_like_js_shell

MAX_EXTERNAL_LINKS = 10


def _check(key, name, status, detail, fix="", editable=False):
    """status: pass | warn | fail. editable=True means the lab can publish the fix; otherwise a developer must."""
    return {"key": key, "name": name, "status": status, "detail": detail, "fix": fix, "editable": editable}


def _sitemap_urls(client: httpx.Client, base: str, robots_text: str) -> tuple[set[str], str]:
    candidates = [line.split(":", 1)[1].strip() for line in robots_text.splitlines() if line.lower().startswith("sitemap:")]
    declared = bool(candidates)
    if not candidates:
        candidates = [base + "/sitemap.xml"]
    urls: set[str] = set()
    for sitemap_url in candidates[:2]:
        try:
            r = client.get(sitemap_url, timeout=8)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                urls |= {el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text}
        except (httpx.HTTPError, ET.ParseError):
            continue
    return urls, "declared in robots.txt" if declared else "found at /sitemap.xml (not declared in robots.txt)"


def _link_status(client: httpx.Client, url: str) -> tuple[str, int | str]:
    try:
        r = client.head(url, timeout=6, follow_redirects=True)
        if r.status_code in {403, 405, 429, 501}:
            r = client.get(url, timeout=6, follow_redirects=True)
        return url, r.status_code
    except httpx.HTTPError as exc:
        return url, type(exc).__name__


def run_technical_checks(base_url: str, path: str, known_paths: set[str] | None = None) -> dict:
    """Fetch the live page and run the checks. Returns {'checks': [...], 'metrics': {...}, 'html': str}."""
    base = base_url.rstrip("/")
    page_url = base + path
    host = urlparse(base).netloc
    checks = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=False, timeout=30) as client:
        response = client.get(page_url)
        html = response.text if "text/html" in response.headers.get("content-type", "") else ""
        metrics = extract_metrics(html, page_url, response.status_code)
        if looks_like_js_shell(html, metrics["word_count"]):  # JavaScript site: audit what visitors and Google see
            with Renderer() as renderer:
                html = renderer.render(page_url)["html"]
            metrics = extract_metrics(html, page_url, response.status_code)

        # 1. Crawlability: HTTP status, robots.txt rules, noindex.
        robots_text = ""
        try:
            rr = client.get(base + "/robots.txt", timeout=5)
            is_html = "html" in rr.headers.get("content-type", "").lower()  # an app shell, not a real robots.txt
            robots_text = rr.text if rr.status_code == 200 and not is_html else ""
        except httpx.HTTPError:
            pass
        parser = RobotFileParser()
        parser.parse(robots_text.splitlines() if robots_text else ["User-agent: *", "Allow: /"])
        allowed = parser.can_fetch("*", page_url)
        noindex = "noindex" in metrics["robots_meta"].lower()
        if response.status_code != 200:
            checks.append(_check("crawl", "Crawlability", "fail", f"The page returned HTTP {response.status_code}.", "Make the page return HTTP 200."))
        elif not allowed:
            checks.append(_check("crawl", "Crawlability", "fail", "robots.txt blocks this URL.", "Remove the Disallow rule if the page should be crawled."))
        elif noindex:
            checks.append(_check("crawl", "Crawlability", "fail", "A robots meta tag contains noindex.", "Remove noindex if this page should appear in search."))
        else:
            checks.append(_check("crawl", "Crawlability", "pass", "HTTP 200, allowed by robots.txt, no noindex."))

        # 2. Canonical URL.
        canonical = metrics["canonical"]
        if not canonical:
            checks.append(_check("canonical", "Canonical URL", "warn", "No canonical link found.", "Add <link rel=\"canonical\"> pointing to this page's preferred URL."))
        elif urldefrag(canonical)[0].rstrip("/") != page_url.rstrip("/"):
            checks.append(_check("canonical", "Canonical URL", "warn", f"Canonical points elsewhere: {canonical}", "Make sure this is intentional; self-referencing canonicals are the usual default."))
        else:
            checks.append(_check("canonical", "Canonical URL", "pass", "Self-referencing absolute canonical is present."))

        # 3. XML sitemap.
        sitemap, how = _sitemap_urls(client, base, robots_text)
        if not sitemap:
            checks.append(_check("sitemap", "XML sitemap", "fail", "No readable XML sitemap was found.", "Publish /sitemap.xml and reference it in robots.txt."))
        elif page_url.rstrip("/") not in {u.rstrip("/") for u in sitemap}:
            checks.append(_check("sitemap", "XML sitemap", "fail", f"Sitemap has {len(sitemap)} URLs but not this page.", "Add this URL to the sitemap."))
        elif "not declared" in how:
            checks.append(_check("sitemap", "XML sitemap", "warn", f"This page is listed ({len(sitemap)} URLs); sitemap {how}.", "Add a Sitemap: line to robots.txt."))
        else:
            checks.append(_check("sitemap", "XML sitemap", "pass", f"This page is listed ({len(sitemap)} URLs); sitemap {how}."))

        # 4. Image alt text.
        if metrics["image_count"] == 0:
            checks.append(_check("alt", "Image alt text", "warn", "No images found on the page.", "Add relevant images with descriptive alt text."))
        elif metrics["images_missing_alt"]:
            checks.append(_check("alt", "Image alt text", "fail", f"{metrics['images_missing_alt']} of {metrics['image_count']} images have no alt text.", "Add short, descriptive alt text to each image."))
        else:
            checks.append(_check("alt", "Image alt text", "pass", f"All {metrics['image_count']} images have alt text."))

        # 5. Broken links (internal and a small sample of external links).
        soup = BeautifulSoup(html, "html.parser")
        internal, external = set(), set()
        for a in soup.find_all("a", href=True):
            dest = urldefrag(urljoin(page_url, a["href"].strip()))[0]
            if urlparse(dest).scheme not in {"http", "https"}:
                continue
            (internal if urlparse(dest).netloc == host else external).add(dest)
        broken, unverified = [], []
        for url in sorted(internal):
            if known_paths is not None and urlparse(url).path.rstrip("/") in known_paths:
                continue
            _, code = _link_status(client, url)
            if not isinstance(code, int) or code >= 400:
                broken.append(f"{url} ({code})")
        safe_external = []
        for url in sorted(external)[:MAX_EXTERNAL_LINKS]:
            try:
                _validate_start_url(url)
                safe_external.append(url)
            except ValueError:
                continue
        with ThreadPoolExecutor(max_workers=5) as pool:
            for url, code in pool.map(lambda u: _link_status(client, u), safe_external):
                if isinstance(code, int) and code in {401, 403, 429}:
                    unverified.append(f"{url} ({code})")
                elif not isinstance(code, int) or code >= 400:
                    broken.append(f"{url} ({code})")
        total = len(internal) + len(safe_external)
        if broken:
            checks.append(_check("links", "Broken links", "fail", f"{len(broken)} broken of {total} links checked: " + "; ".join(broken[:4]), "Fix or remove the broken links."))
        elif unverified:
            checks.append(_check("links", "Broken links", "warn", f"No broken links, but {len(unverified)} external site(s) blocked the check: " + "; ".join(unverified[:3]), "Open these manually to confirm they work."))
        else:
            checks.append(_check("links", "Broken links", "pass", f"All {total} checked links respond (external links: first {MAX_EXTERNAL_LINKS})."))

        # Extra: structured data (not requested, but a common gap).
        if not metrics["has_jsonld"]:
            checks.append(_check("jsonld", "Structured data", "warn", "No JSON-LD structured data found.", "Consider adding schema.org markup (e.g. Article or TouristDestination)."))
        else:
            checks.append(_check("jsonld", "Structured data", "pass", "JSON-LD found: " + ", ".join(metrics["jsonld_types"][:3])))
    return {"checks": checks, "metrics": metrics, "html": html}
