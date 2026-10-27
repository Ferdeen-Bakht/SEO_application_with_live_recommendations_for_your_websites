"""Read-only access to the live site under review, built from the last crawl (data/last_crawl.json).

There is no publishing path in this project: every result is a suggestion for a human to apply in their own repo/CMS.
"""
import json
from urllib.parse import urlparse

from seo_lab import site_state
from seo_lab.config import DATA_DIR
from seo_lab.site_checks import slugify

CRAWL_FILE = DATA_DIR / "last_crawl.json"


def save_crawl(pages: list[dict]) -> None:
    CRAWL_FILE.write_text(json.dumps(pages, indent=2, ensure_ascii=False), encoding="utf-8")


def load_crawl() -> list[dict]:
    try:
        return json.loads(CRAWL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _to_page(p: dict) -> dict:
    """Shape a crawled page like the editor expects: title, metaDescription, h1, a few intro paragraphs, path, slug."""
    path = urlparse(p["url"]).path or "/"
    paragraphs = p.get("paragraphs", [])
    return {
        "url": p["url"], "path": path, "slug": slugify(path), "version": 1,
        "title": p.get("title", ""), "metaDescription": p.get("description", ""), "h1": p.get("h1", ""),
        "h2": p.get("metrics", {}).get("h2_list", []), "paragraphs": paragraphs[:3], "body_text": "\n".join(paragraphs) or p.get("text", ""),
    }


def get_pages(base_url: str | None = None) -> list[dict]:
    base_url = base_url or site_state.get_site_url()
    host = urlparse(base_url).netloc
    return [_to_page(p) for p in load_crawl() if p.get("status_code") == 200 and p.get("metrics") and urlparse(p["url"]).netloc == host]


def get_page(slug: str, base_url: str | None = None) -> dict:
    for page in get_pages(base_url):
        if page["slug"] == slug:
            return page
    raise KeyError(f"No crawled page '{slug}'. Run 1. Crawl & audit first.")
