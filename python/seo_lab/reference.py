"""The top-ranking competitor page (as found by the search engine) used as a REFERENCE for suggestions.

The model may learn search intent, topics and clarity from it, but the suggestions must stay about OUR site:
- the prompt forbids the competitor's name, claims, numbers and wording,
- accuracy checks run against OUR page text only, so any competitor-only fact or number is flagged,
- revision_tests flags copied wording and proposals that lean on the competitor's vocabulary rather than ours.
The fetch respects robots.txt and is cached per URL.
"""
import json

from seo_lab import site_state
from seo_lab.config import DATA_DIR
from seo_lab.crawler import crawl_site


def _cache_file():
    return DATA_DIR / f"reference__{site_state.label()}.json"


def _load() -> dict:
    try:
        return json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch_reference(url: str, refresh: bool = False) -> dict:
    """Title, description, H1, headings and main text blocks of `url`; {'url', 'error'} when it cannot be read."""
    cache = _load()
    if url in cache and not refresh and not cache[url].get("error"):
        return cache[url]
    try:
        pages = crawl_site(url, max_pages=1, delay_seconds=0.2)
    except Exception as exc:  # unreachable, private address, bad URL...
        return {"url": url, "error": str(exc)}
    page = next((p for p in pages if p.get("metrics") and p.get("status_code") == 200), None)
    if page is None:
        why = next((f["issue"] for p in pages for f in p.get("findings", [])), "no readable HTML page")
        return {"url": url, "error": f"Could not read the competitor page ({why})."}
    m = page["metrics"]
    ref = {"url": url, "title": page["title"], "description": page["description"], "h1": page["h1"], "h2": m.get("h2_list", [])[:12],
           "paragraphs": page.get("paragraphs", [])[:14], "word_count": m.get("word_count", 0)}
    cache[url] = ref
    _cache_file().write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    return ref


def from_snippet(meta: dict, fetch_error: str) -> dict:
    """When the competitor page itself cannot be fetched (blocked network, robots.txt, 403), fall back to what the search engine shows."""
    text = (meta.get("snippet") or "").strip()
    return {"url": meta["url"], "title": meta.get("title", ""), "description": text, "h1": "", "h2": [], "paragraphs": [text] if text else [],
            "word_count": 0, "source": "search snippet", "fetch_error": fetch_error}


def reference_text(ref: dict | None, limit: int = 6000) -> str:
    """All of the reference's text (used for the checks, not shown to the model in full)."""
    if not ref or ref.get("error"):
        return ""
    parts = [ref.get("title", ""), ref.get("description", ""), ref.get("h1", ""), " ".join(ref.get("h2", []))] + ref.get("paragraphs", [])
    return "\n".join(p for p in parts if p)[:limit]


def prompt_block(ref: dict | None, meta: dict | None, excerpt_chars: int = 1300) -> str:
    """The reference section of the prompt, with the rules that keep the output about OUR site."""
    if not ref or ref.get("error"):
        return ""
    excerpt = "\n".join(
        [f"Title: {ref.get('title', '')}", f"Description: {ref.get('description', '')}", f"H1: {ref.get('h1', '')}",
         f"Headings: {'; '.join(ref.get('h2', [])[:10])}", "Text: " + " ".join(ref.get("paragraphs", []))])[:excerpt_chars]
    where = f"ranks #{meta['position']} on the search engine for \"{meta['keyword']}\", {meta['domain']}" if meta else ref["url"]
    return (f"REFERENCE: the competitor page that {where}. Use it ONLY to understand what searchers want, which topics a strong page covers, and how "
            f"clearly it is written.\nThis page is about OUR company, so: build every sentence from OUR page's own facts; never use the competitor's name, "
            f"products, prices, numbers, awards or claims; never copy its wording; if it conflicts with our page, ignore it. Our result must read as OUR "
            f"page, improved.\n\"\"\"\n{excerpt}\n\"\"\"\n")
