"""Which website is under review, plus the competitors and keywords chosen for it.

Stored in data/site_state.json so every page (and every restart) uses the same site. Changing the site resets the
competitors and keywords, because they belong to the old site. Results files are named per site, so nothing is mixed up.
"""
import json
from urllib.parse import urlparse

from seo_lab.config import DATA_DIR, SITE_URL

STATE_FILE = DATA_DIR / "site_state.json"


def normalize(url: str) -> str:
    """'abetglobal.com/x' -> 'https://abetglobal.com' (origin only)."""
    url = url.strip()
    if "//" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a website address such as https://example.com")
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def site_label(url: str) -> str:
    host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _load() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_site_url() -> str:
    return _load().get("site_url") or SITE_URL


def label() -> str:
    return site_label(get_site_url())


def set_site(url: str) -> str:
    """Remember the site. Competitors and keywords are cleared only when the site really changes."""
    new = normalize(url)
    state = _load()
    if site_label(state.get("site_url") or SITE_URL) != site_label(new):
        state = {}
    state["site_url"] = new
    _save(state)
    return new


def get_competitors() -> list[str]:
    return _load().get("competitors", [])


def set_competitors(urls: list[str]) -> None:
    state = _load()
    state["site_url"] = get_site_url()
    state["competitors"] = urls
    _save(state)


def get_keywords() -> list[str]:
    return _load().get("keywords", [])


def set_keywords(keywords: list[str]) -> None:
    state = _load()
    state["site_url"] = get_site_url()
    state["keywords"] = keywords[:5]
    _save(state)
