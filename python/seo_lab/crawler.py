"""Small same-origin crawler for learning and authorized site audits."""
from collections import deque
import os
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from seo_lab.page_metrics import extract_metrics, extract_paragraphs
from seo_lab.renderer import Renderer, looks_like_js_shell

USER_AGENT = "BeginnerAISEOLab/0.1 (+local learning tool)"

# "Unlimited" still needs a ceiling: big sites (listings, search filters, calendars) have effectively endless URLs.
HARD_LIMIT = int(os.getenv("CRAWL_HARD_LIMIT", "2000"))
ASSET_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".zip", ".rar", ".7z", ".mp4", ".mp3", ".mov", ".avi",
                    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".exe", ".dmg", ".apk")


class CrawlList(list):
    """The crawled pages. `stopped_by` says why the crawl ended early: 'limit' (page limit/ceiling), 'time' (time limit) or None (done)."""
    stopped_by: str | None = None


def _key(url: str) -> str:
    """Identity of a page for de-duplication: trailing slash and host case do not make a new page."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/') or '/'}" + (f"?{p.query}" if p.query else "")


def _is_asset(url: str) -> bool:
    return urlparse(url).path.lower().endswith(ASSET_EXTENSIONS)


def _validate_start_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a complete http:// or https:// URL.")
    if parsed.username or parsed.password:
        raise ValueError("Do not include credentials in the URL.")
    host = parsed.hostname.lower()
    # Localhost is allowed for local development sites.
    if host not in {"localhost", "127.0.0.1", "::1"}:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
        except (socket.gaierror, ValueError) as exc:
            raise ValueError(f"Could not resolve host {host}: {exc}") from exc
        if any(not addr.is_global for addr in addresses):
            raise ValueError("For safety, this learning crawler only allows public hosts or localhost. Private/internal IP targets are blocked.")
    return url


def _robots_parser(origin: str, client: httpx.Client) -> RobotFileParser:
    robots_url = origin.rstrip("/") + "/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = client.get(robots_url, timeout=5)
        # Single-page apps often answer /robots.txt with their HTML shell; that is "no robots.txt", not rules.
        if response.status_code == 200 and "html" not in response.headers.get("content-type", "").lower():
            parser.parse(response.text.splitlines())
        else:
            # If robots.txt is unavailable, this small learning tool proceeds.
            parser.parse(["User-agent: *", "Allow: /"])
    except httpx.HTTPError:
        parser.parse(["User-agent: *", "Allow: /"])
    return parser


def _extract_page(url: str, html: str, status_code: int, content_type: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    description_tag = soup.find("meta", attrs={"name": lambda v: isinstance(v, str) and v.lower() == "description"})
    robots_tags = soup.find_all("meta", attrs={"name": lambda v: isinstance(v, str) and v.lower() in {"robots", "googlebot"}})
    canonical_tag = soup.find("link", rel=lambda v: v and "canonical" in ([x.lower() for x in v] if isinstance(v, list) else str(v).lower().split()))
    h1_tags = soup.find_all("h1")
    anchors = []
    for a in soup.find_all("a", href=True):
        dest = urldefrag(urljoin(url, a["href"].strip()))[0]
        if dest:
            anchors.append(dest)
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    text = " ".join(soup.stripped_strings)
    robots = ", ".join(tag.get("content", "") for tag in robots_tags)
    canonical = urljoin(url, canonical_tag.get("href", "")) if canonical_tag and canonical_tag.get("href") else ""
    return {
        "url": url,
        "status_code": status_code,
        "content_type": content_type,
        "title": title_tag.get_text(" ", strip=True) if title_tag else "",
        "description": description_tag.get("content", "").strip() if description_tag else "",
        "h1": h1_tags[0].get_text(" ", strip=True) if h1_tags else "",
        "h1_list": [x.get_text(" ", strip=True) for x in h1_tags],
        "canonical": canonical,
        "robots": robots,
        "text": text[:12000],
        "paragraphs": extract_paragraphs(html),
        "links": anchors,
    }


def crawl_site(start_url: str, max_pages: int | None = 15, delay_seconds: float = 0.15, render: str = "auto",
               max_seconds: float | None = None, progress=None) -> CrawlList:
    """max_pages=None means unlimited: follow every reachable link on the host (bounded only by CRAWL_HARD_LIMIT).
    max_seconds stops gracefully and returns what was found. progress(count, url) is called as pages are crawled.
    render: 'auto' (open a real browser only for pages whose raw HTML is an empty JavaScript shell), 'always', or 'never'.
    Rendered pages are marked with page['rendered'] = True and keep raw_word_count."""
    with Renderer() as renderer:
        return _crawl(start_url, max_pages, delay_seconds, render, renderer, max_seconds, progress)


def _crawl(start_url: str, max_pages: int | None, delay_seconds: float, render: str, renderer: "Renderer | None",
           max_seconds: float | None = None, progress=None) -> CrawlList:
    start_url = _validate_start_url(start_url)
    parsed_start = urlparse(start_url)
    origin = f"{parsed_start.scheme}://{parsed_start.netloc}"
    start_url = urldefrag(start_url)[0]
    queue = deque([start_url])
    seen, queued = set(), {_key(start_url)}
    pages = CrawlList()
    limit = HARD_LIMIT if not max_pages else max(1, min(int(max_pages), HARD_LIMIT))
    deadline = time.time() + max_seconds if max_seconds else None

    with httpx.Client(
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    ) as client:
        robots = _robots_parser(origin, client)
        while queue:
            if len(pages) >= limit:
                pages.stopped_by = "limit"
                break
            if deadline and time.time() > deadline:
                pages.stopped_by = "time"
                break
            url = queue.popleft()
            if _key(url) in seen:
                continue
            seen.add(_key(url))
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != parsed_start.netloc:
                continue
            if not robots.can_fetch(USER_AGENT, url):
                pages.append({"url": url, "status_code": 0, "title": "", "description": "", "h1": "", "canonical": "", "robots": "", "text": "", "h1_list": [], "links": [], "findings": [{"severity": "info", "issue": "Blocked by robots.txt", "why": "The crawler respected the site's robots.txt rule.", "suggestion": "Do not bypass this rule; check it manually if you own this site."}]})
                continue
            try:
                response = client.get(url)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if location:
                        next_url = urldefrag(urljoin(url, location))[0]
                        if urlparse(next_url).netloc == parsed_start.netloc and _key(next_url) not in seen and not _is_asset(next_url):
                            queued.add(_key(next_url))
                            queue.appendleft(next_url)
                    pages.append({"url": url, "status_code": response.status_code, "title": "", "description": "", "h1": "", "canonical": "", "robots": "", "text": "", "h1_list": [], "links": [], "findings": [{"severity": "review", "issue": "Redirect response", "why": "Redirects can be expected, but chains and loops should be avoided.", "suggestion": "Audit the final destination and verify that the redirect is intentional."}]})
                    continue
                ctype = response.headers.get("content-type", "").lower()
                if "text/html" not in ctype:
                    pages.append({"url": url, "status_code": response.status_code, "title": "", "description": "", "h1": "", "canonical": "", "robots": "", "text": "", "h1_list": [], "links": [], "findings": [{"severity": "info", "issue": f"Not an HTML page ({ctype or 'unknown content type'})", "why": "The crawler only parses HTML in this starter.", "suggestion": "Check PDF, image, or other resources with suitable tools if needed."}]})
                    continue
                if len(response.content) > 2_000_000:
                    pages.append({"url": url, "status_code": response.status_code, "title": "", "description": "", "h1": "", "canonical": "", "robots": "", "text": "", "h1_list": [], "links": [], "findings": [{"severity": "review", "issue": "Response larger than 2 MB", "why": "The starter crawler limits response size to avoid excessive memory usage.", "suggestion": "Inspect the page manually or configure a safe size limit."}]})
                    continue
                html = response.text
                raw_words = extract_metrics(html, url, response.status_code)["word_count"]
                rendered, raw_note = False, ""
                if render == "always" or (render == "auto" and looks_like_js_shell(html, raw_words)):
                    try:
                        html = renderer.render(url)["html"]
                        rendered = True
                    except Exception as exc:  # fall back to the raw HTML, but say so
                        raw_note = f"Browser rendering failed ({type(exc).__name__}); only the raw HTML was audited."
                page = _extract_page(url, html, response.status_code, ctype)
                page["metrics"] = extract_metrics(html, url, response.status_code)
                page["rendered"], page["raw_word_count"] = rendered, raw_words
                if raw_note:
                    page["render_error"] = raw_note
                page["findings"] = []
                # Audit only pages with an HTML response.
                from seo_lab.audit_rules import audit_page
                page["findings"] = audit_page(page)
                pages.append(page)
                for link in page.get("links", []):
                    target = urlparse(link)
                    k = _key(link)
                    if target.netloc == parsed_start.netloc and target.scheme in {"http", "https"} and k not in seen and k not in queued and not _is_asset(link):
                        queued.add(k)
                        queue.append(link)
                page["links"] = page["links"][:40]  # saved crawls stay small on big sites
                page["text"] = page["text"][:4000]
            except httpx.HTTPError as exc:
                pages.append({"url": url, "status_code": 0, "title": "", "description": "", "h1": "", "canonical": "", "robots": "", "text": "", "h1_list": [], "links": [], "findings": [{"severity": "high", "issue": f"Fetch failed: {type(exc).__name__}", "why": "The crawler could not fetch this URL.", "suggestion": "Check server availability, TLS, and the URL."}]})
            if progress:
                progress(len(pages), url)
            time.sleep(max(0, min(delay_seconds, 2.0)))
    return pages
