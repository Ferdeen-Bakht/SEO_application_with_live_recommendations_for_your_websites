"""Read-only domain statistics from public sources, for display only (nothing here feeds the suggestions agent).

- Internet Archive CDX API: how old a site is, how many URLs it has had archived, how its homepage changed over time.
- FreeSerp: a domain rating (DR 0-100), category, launch date and summary, when the site is in its index.
Results are cached per domain for a week in data/stats_cache/, because the archive can take 30+ seconds for a big site.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import time
from urllib.parse import urlparse

import httpx

from seo_lab.config import DATA_DIR
from seo_lab.crawler import USER_AGENT, _validate_start_url

CACHE_DIR = DATA_DIR / "stats_cache"
CACHE_SECONDS = 7 * 24 * 3600
CDX_URL = "https://web.archive.org/cdx/search/cdx"
FREESERP_URL = "https://freeserp.ai/api.php"
URL_LIMIT = 5000
HEADERS = {"User-Agent": USER_AGENT}


def _cached(name: str, loader, refresh: bool = False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.json"
    if not refresh:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - blob["saved"] < CACHE_SECONDS:
                return blob["data"]
        except (OSError, ValueError, KeyError):
            pass
    data = loader()
    if not data.get("error"):
        path.write_text(json.dumps({"saved": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")
    return data


def _cdx(**params) -> list[dict]:
    for attempt in range(3):  # the archive answers 429/503 now and then when busy
        r = httpx.get(CDX_URL, params={"output": "json", **params}, headers=HEADERS, timeout=120)
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(3 * (attempt + 1))
    r.raise_for_status()
    rows = r.json() if r.text.strip() else []
    return [dict(zip(rows[0], row)) for row in rows[1:]] if rows else []


# ------------------------------------------------------------------------------------------------ Internet Archive
def _wayback(domain: str) -> dict:
    try:
        home = _cdx(url=domain, fl="timestamp,statuscode,digest", collapse="timestamp:6")  # one capture per month
        urls = _cdx(url=domain, matchType="domain", fl="timestamp,original,statuscode,mimetype", collapse="urlkey", limit=URL_LIMIT)
    except (httpx.HTTPError, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", "")
        return {"error": f"Internet Archive request failed ({type(exc).__name__} {status}). Try again in a minute.".replace("  ", " ")}
    return {"home": home, "urls": urls, "truncated": len(urls) >= URL_LIMIT}


def wayback_raw(domain: str, refresh: bool = False) -> dict:
    return _cached(f"wayback__{domain}", lambda: _wayback(domain), refresh)


def _year(ts: str) -> int:
    return int(ts[:4])


def summarize_wayback(raw: dict) -> dict:
    """Plain numbers and small tables from the raw capture lists. Empty dict values mean 'no captures'."""
    if raw.get("error"):
        return {"error": raw["error"]}
    home, urls = raw["home"], raw["urls"]
    out: dict = {"months_captured": len(home), "unique_urls": len(urls), "truncated": raw["truncated"]}
    if home:
        out["first_capture"] = home[0]["timestamp"]
        out["last_capture"] = home[-1]["timestamp"]
        out["age_years"] = round((time.time() - time.mktime(time.strptime(home[0]["timestamp"][:8], "%Y%m%d"))) / (365.25 * 86400), 1)
        out["home_by_year"] = dict(sorted(Counter(_year(h["timestamp"]) for h in home).items()))
        changes, last = Counter(), None
        for h in home:  # a new content hash between two monthly captures = the homepage changed
            if last is not None and h["digest"] != last:
                changes[_year(h["timestamp"])] += 1
            last = h["digest"]
        out["home_changes_by_year"] = dict(sorted(changes.items()))
        out["home_status"] = dict(Counter(h["statuscode"] for h in home))
        out["home_distinct_versions"] = len({h["digest"] for h in home})
    if urls:
        out["urls_by_first_year"] = dict(sorted(Counter(_year(u["timestamp"]) for u in urls).items()))
        out["status_mix"] = dict(Counter(u["statuscode"] for u in urls).most_common())
        out["mime_mix"] = dict(Counter(u["mimetype"] for u in urls).most_common(8))
        html = [u for u in urls if "html" in u["mimetype"]]
        out["html_urls"] = len(html)
        sections, hosts = Counter(), Counter()
        for u in html:
            p = urlparse(u["original"])
            hosts[p.netloc.lower().split(":")[0]] += 1
            parts = [x for x in p.path.split("/") if x]
            sections["/" + parts[0] if len(parts) > 1 else "(top level)"] += 1
        out["top_sections"] = dict(sections.most_common(10))
        out["hosts"] = dict(hosts.most_common(8))
        out["with_query"] = sum(1 for u in urls if "?" in u["original"])
        out["oldest_urls"] = [{"first_seen": u["timestamp"][:8], "url": u["original"]} for u in sorted(urls, key=lambda u: u["timestamp"]) if "html" in u["mimetype"]][:10]
    return out


def archived_html_urls(raw: dict, limit: int) -> list[str]:
    seen, out = set(), []
    for u in raw.get("urls", []):
        if "html" in u["mimetype"] and u["statuscode"] == "200":
            clean = u["original"].split("#")[0].replace(":80/", "/").replace(":443/", "/")
            host = urlparse(clean).netloc.lower().removeprefix("www.")
            key = (host, urlparse(clean).path.rstrip("/"), urlparse(clean).query)
            if key not in seen:
                seen.add(key)
                out.append(clean)
    return out[:limit]


def live_status(urls: list[str], workers: int = 6) -> list[dict]:
    """Read-only HEAD/GET check of archived URLs on the live site: which still answer, which are gone or redirect away."""
    def one(url):
        try:
            _validate_start_url(url)
            r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=False)
            return {"url": url, "status": r.status_code, "redirects_to": r.headers.get("location", "") if 300 <= r.status_code < 400 else ""}
        except (ValueError, httpx.HTTPError) as exc:
            return {"url": url, "status": 0, "redirects_to": type(exc).__name__}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, urls))


# ------------------------------------------------------------------------------------------------ FreeSerp authority
def _freeserp(domain: str) -> dict:
    try:
        r = httpx.get(FREESERP_URL, params={"index": "web", "q": domain, "size": 10}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        results = r.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"FreeSerp request failed ({type(exc).__name__})."}
    for hit in results:
        host = (hit.get("domain") or "").lower().removeprefix("www.")
        if host == domain or host.endswith("." + domain):
            site = hit.get("site") or {}
            return {"found": True, "dr": site.get("dr"), "category": site.get("category"), "ai_categories": site.get("ai_categories") or [],
                    "went_live": site.get("went_live"), "summary": site.get("summary"), "sample_page": hit.get("url")}
    return {"found": False}


def freeserp_authority(domain: str, refresh: bool = False) -> dict:
    return _cached(f"freeserp__{domain}", lambda: _freeserp(domain), refresh)


def load_all(domains: list[str], refresh: bool = False) -> dict[str, dict]:
    """Authority + archive summary for each domain, fetched in parallel."""
    def one(d):
        return d, {"authority": freeserp_authority(d, refresh), "wayback": summarize_wayback(wayback_raw(d, refresh))}
    with ThreadPoolExecutor(max_workers=min(4, len(domains) or 1)) as pool:
        return dict(pool.map(one, domains))
