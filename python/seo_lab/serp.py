"""Keyword rankings from a search engine you can also check yourself.

Providers (no scraping of search result pages, no bypassing of bot blocks):
- searxng: YOUR OWN SearXNG instance (free). It must have `json` under `search: formats:` in settings.yml.
  If it is the local one from tools/, it is started automatically when it is not running.
- mojeek:  Mojeek's official Search API (paid per query, needs MOJEEK_API_KEY).

Position = rank of the first result from that domain in the engine's results (1 = top). None = not in the results fetched.
"""
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import time
from urllib.parse import quote_plus, urlparse

import httpx

from seo_lab import site_state
from seo_lab.config import DATA_DIR, MOJEEK_API_KEY, PROJECT_ROOT, SEARXNG_URL, SERP_PROVIDER

RESULTS_DEPTH = 30
TOOLS_DIR = PROJECT_ROOT / "tools"


def _serp_file():
    return DATA_DIR / f"serp_ranks__{site_state.label()}.json"


def host_of(url: str) -> str:
    host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# ----------------------------------------------------------------------------- local SearXNG lifecycle
def _searxng_up() -> bool:
    try:
        return httpx.get(SEARXNG_URL + "/", timeout=3).status_code < 500
    except httpx.HTTPError:
        return False


def ensure_searxng(wait_seconds: int = 90) -> None:
    """Make sure SearXNG answers. Starts the local copy in tools/ (detached, hidden window) if needed."""
    if SERP_PROVIDER != "searxng" or _searxng_up():
        return
    host = urlparse(SEARXNG_URL).hostname
    python = TOOLS_DIR / "searxng" / "venv" / "Scripts" / "python.exe"
    if host not in {"127.0.0.1", "localhost"} or not python.exists():
        raise RuntimeError(f"SearXNG is not reachable at {SEARXNG_URL}. Start your SearXNG instance (see README) and try again.")
    env = dict(os.environ, SEARXNG_SETTINGS_PATH=str(TOOLS_DIR / "searxng-settings.yml"),
               PYTHONPATH=f"{TOOLS_DIR / 'shims'}{os.pathsep}{TOOLS_DIR / 'searxng'}")
    log = open(TOOLS_DIR / "searxng.log", "ab")
    subprocess.Popen([str(python), "-m", "searx.webapp"], cwd=TOOLS_DIR / "searxng", env=env, stdout=log, stderr=log,
                     creationflags=0x00000008 | 0x00000200 | 0x08000000, close_fds=True)  # DETACHED | NEW_GROUP | NO_WINDOW
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _searxng_up():
            return
        time.sleep(2)
    raise RuntimeError(f"Started the local SearXNG but it did not answer within {wait_seconds}s. See tools/searxng.log.")


# ----------------------------------------------------------------------------- providers
def _searxng(query: str, depth: int) -> list[dict]:
    out, page = [], 1
    with httpx.Client(timeout=40) as client:
        while len(out) < depth and page <= 5:
            r = client.get(f"{SEARXNG_URL.rstrip('/')}/search", params={"q": query, "format": "json", "pageno": page, "language": "en"})
            if r.status_code == 403:
                raise RuntimeError("SearXNG refused JSON (403). Add `json` under `search: formats:` in its settings.yml and restart it.")
            r.raise_for_status()
            batch = r.json().get("results", [])
            if not batch:
                break
            out += [{"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("content", "")} for x in batch]
            page += 1
    return out[:depth]


def _mojeek(query: str, depth: int) -> list[dict]:
    if not MOJEEK_API_KEY:
        raise RuntimeError("MOJEEK_API_KEY is not set in python/.env (the Mojeek API is paid; get a key at mojeek.com/services/api.html).")
    r = httpx.get("https://api.mojeek.com/search", params={"q": query, "api_key": MOJEEK_API_KEY, "fmt": "json", "t": depth}, timeout=30)
    if r.status_code in {401, 403}:
        raise RuntimeError(f"Mojeek rejected the API key (HTTP {r.status_code}).")
    r.raise_for_status()
    results = r.json().get("response", {}).get("results", [])
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "snippet": x.get("desc", "")} for x in results][:depth]


PROVIDERS = {"searxng": _searxng, "mojeek": _mojeek}


def search(query: str, depth: int = RESULTS_DEPTH, provider: str = SERP_PROVIDER) -> list[dict]:
    """One query on the configured engine (starting the local SearXNG first if needed)."""
    if provider == "searxng":
        ensure_searxng()
    return PROVIDERS[provider](query, depth)


def verify_link(query: str, provider: str = SERP_PROVIDER) -> str:
    """A normal search URL a person can open in a browser to check the same query."""
    if provider == "mojeek":
        return f"https://www.mojeek.com/search?q={quote_plus(query)}"
    return f"{SEARXNG_URL.rstrip('/')}/search?q={quote_plus(query)}"


def rank_domains(results: list[dict], domains: list[str]) -> dict[str, int | None]:
    positions: dict[str, int | None] = {d: None for d in domains}
    for i, r in enumerate(results, start=1):
        h = host_of(r["url"])
        for d in domains:
            if positions[d] is None and (h == d or h.endswith("." + d)):
                positions[d] = i
    return positions


def first_urls(results: list[dict], domains: list[str]) -> dict[str, str | None]:
    """The exact result URL of the first hit for each domain (so we know which page ranks, not just that the site does)."""
    urls: dict[str, str | None] = {d: None for d in domains}
    for r in results:
        h = host_of(r["url"])
        for d in domains:
            if urls[d] is None and (h == d or h.endswith("." + d)):
                urls[d] = r["url"]
    return urls


def first_hits(results: list[dict], domains: list[str]) -> dict[str, dict]:
    """URL, title and search snippet of the first hit per domain: what the engine itself shows for the ranking page."""
    hits: dict[str, dict] = {}
    for r in results:
        h = host_of(r["url"])
        for d in domains:
            if d not in hits and (h == d or h.endswith("." + d)):
                hits[d] = {"url": r["url"], "title": r.get("title", ""), "snippet": r.get("snippet", "")}
    return hits


def visibility_scores(data: dict) -> dict[str, float]:
    """0-100 'SEO score' from search results only: per keyword a site earns (depth+1-position)/depth (1.0 at #1, 0 if absent
    from the fetched results); the score is the average over the tracked keywords."""
    depth, rows = data["depth"], data["keywords"]
    out = {}
    for d in data["domains"]:
        pts = [((depth + 1 - r["positions"][d]) / depth) if r["positions"].get(d) else 0.0 for r in rows]
        out[d] = round(100 * sum(pts) / max(1, len(pts)), 1)
    return out


def _hit_text(row: dict, domain: str) -> dict:
    hit = row.get("hits", {}).get(domain, {})
    return {"title": hit.get("title", ""), "snippet": hit.get("snippet", "")}


def top_competitor_hint(top: dict, data: dict) -> str:
    """One line: where the top-ranking competitor stands for its keyword (with its title) and where we stand."""
    row = next((r for r in data["keywords"] if r["keyword"] == top["keyword"]), None)
    pos = row["positions"].get(data["our_domain"]) if row else None
    where = f"we rank #{pos}" if pos else f"we are not in the top {data['depth']}"
    title = f" with the title \"{top['title'][:90]}\"" if top.get("title") else ""
    return f"Search '{top['keyword']}' ({data['provider']}): {top['domain']} ranks #{top['position']}{title}; {where}."


def top_competitor(data: dict | None, keyword: str = "", context: str = "") -> dict | None:
    """The best-ranked competitor for the tracked keyword closest to `keyword`/`context`, with the exact URL that ranks.

    Falls back to the best-ranked competitor over all keywords. Returns {domain, url, position, keyword} or None."""
    if not data:
        return None
    ours = data["our_domain"]
    want = {w for w in re.findall(r"[a-z0-9]+", f"{keyword} {context}".lower()) if len(w) > 2}

    def best_in(row):
        ranked = [(pos, d) for d, pos in row["positions"].items() if pos and d != ours and row.get("urls", {}).get(d)]
        return min(ranked) if ranked else None

    rows = sorted(data["keywords"], key=lambda r: -len(want & set(re.findall(r"[a-z0-9]+", r["keyword"].lower()))))
    if rows and want & set(re.findall(r"[a-z0-9]+", rows[0]["keyword"].lower())) and best_in(rows[0]):
        pos, d = best_in(rows[0])
        return {"domain": d, "url": rows[0]["urls"][d], "position": pos, "keyword": rows[0]["keyword"], **_hit_text(rows[0], d)}
    found = [(best_in(r), r) for r in data["keywords"] if best_in(r)]
    if not found:
        return None
    (pos, d), row = min(found, key=lambda x: x[0][0])
    return {"domain": d, "url": row["urls"][d], "position": pos, "keyword": row["keyword"], **_hit_text(row, d)}


def check_rankings(keywords: list[str], domains: list[str], provider: str = SERP_PROVIDER, depth: int = RESULTS_DEPTH) -> dict:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Use one of: {', '.join(PROVIDERS)}")
    domains = [host_of(d) for d in domains]
    rows = []
    for kw in keywords[:5]:
        results = search(kw, depth, provider)
        rows.append({"keyword": kw, "positions": rank_domains(results, domains), "urls": first_urls(results, domains), "hits": first_hits(results, domains), "results_fetched": len(results),
                     "top": [{"pos": i, "url": r["url"], "title": r["title"]} for i, r in enumerate(results[:10], start=1)],
                     "verify_url": verify_link(kw, provider)})
    data = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provider": provider, "depth": depth,
            "our_domain": site_state.label(), "domains": domains, "keywords": rows}
    _serp_file().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def load_rankings() -> dict | None:
    try:
        return json.loads(_serp_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def serp_hints(data: dict | None, keyword: str = "") -> list[str]:
    """Plain-language facts for the suggestion agent: who ranks for the tracked keywords and what their titles look like.

    With a tracked keyword, only that keyword's results are used; with any other keyword, all tracked keywords are used."""
    if not data:
        return []
    ours, rows = data["our_domain"], data["keywords"]
    matching = [r for r in rows if keyword and keyword.lower() == r["keyword"].lower()]
    hints = []
    for row in matching or rows:
        pos = row["positions"].get(ours)
        where = f"we rank #{pos}" if pos else f"we are not in the top {data['depth']}"
        titles = "; ".join(f"#{t['pos']} {host_of(t['url'])}: \"{t['title'][:70]}\"" for t in row["top"][:3])
        hints.append(f"Search '{row['keyword']}' ({data['provider']}): {where}. Top results: {titles}")
    return hints
