"""Crawl our site and competitor sites, export CSVs, compare side by side, and turn the gaps into recommendations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import time
from urllib.parse import urlparse

import pandas as pd

from seo_lab import site_state
from seo_lab.config import DATA_DIR
from seo_lab.crawler import crawl_site
from seo_lab.page_metrics import STOP, score_metrics, tokens

EXPORT_DIR = DATA_DIR / "exports"


def _bench_file():
    return DATA_DIR / f"benchmark__{site_state.label()}.json"


def _history_file():
    return DATA_DIR / f"benchmark_history__{site_state.label()}.json"


def local_csv() -> str:
    return f"local__{site_state.label()}.csv"


def comp_csv() -> str:
    return f"competitors__{site_state.label()}.csv"

DEFAULT_COMPETITORS = [  # software houses selling web/mobile app development; edit freely in the UI
    "https://devsinc.com/",
    "https://10pearls.com/",
    "https://www.folio3.com/",
    "https://tkxel.com/",
    "https://www.netsolutions.com/",
]

COLUMNS = [
    ("url", "URL"), ("score", "SEO score"), ("title", "Title"), ("title_len", "Title length"),
    ("description", "Meta description"), ("desc_len", "Description length"), ("h1", "H1"), ("h2_count", "H2 count"),
    ("word_count", "Word count"), ("image_count", "Images"), ("alt_coverage", "Alt text %"),
    ("internal_links", "Internal links"), ("external_links", "External links"), ("canonical", "Canonical"),
    ("has_jsonld", "Structured data"), ("jsonld_types", "Schema types"), ("url_depth", "URL depth"), ("url_slug_len", "Slug length"),
]
NUMERIC = ["score", "title_len", "desc_len", "h2_count", "word_count", "image_count", "alt_coverage",
           "internal_links", "external_links", "url_depth"]


def site_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def pages_to_frame(site: str, pages: list[dict]) -> pd.DataFrame:
    rows = []
    for p in pages:
        m = p.get("metrics")
        if not m or p.get("status_code") != 200:
            continue
        rows.append({"site": site, "score": score_metrics(m)["total"], **{k: m.get(k, "") for k, _ in COLUMNS if k not in {"score", "jsonld_types"}},
                     "jsonld_types": " | ".join(dict.fromkeys(m.get("jsonld_types", []))), "h2_list": " | ".join(m.get("h2_list", []))})
    return pd.DataFrame(rows)


def explain_no_pages(pages: list[dict]) -> str:
    """Why a crawl produced no readable pages, from what the crawler actually saw."""
    if not pages:
        return "the crawler got no response at all."
    codes = {p.get("status_code") for p in pages}
    if codes <= {0} and any("robots.txt" in f.get("issue", "") for p in pages for f in p.get("findings", [])):
        return "robots.txt disallows crawling this page."
    if codes & {401, 403, 429}:
        return (f"the site answered HTTP {sorted(codes & {401, 403, 429})[0]}: it blocks automated crawlers (bot protection). "
                "This tool does not bypass that; use a competitor that allows crawling.")
    return f"no readable HTML (HTTP status {', '.join(str(c) for c in sorted(c for c in codes if c is not None))})."


def friendly(df: pd.DataFrame) -> pd.DataFrame:
    """Column names suitable for a spreadsheet."""
    out = df[["site"] + [k for k, _ in COLUMNS if k in df.columns] + (["h2_list"] if "h2_list" in df.columns else [])].copy()
    out = out.rename(columns={"site": "Site", "h2_list": "H2 headings", **dict(COLUMNS)})
    return out


def crawl_many(urls: list[str], max_pages_each: int | None = 3, max_seconds: float | None = None, on_progress=None) -> dict[str, dict]:
    """Crawl each site on its own thread (max_pages_each=None = unlimited). Every crawl respects robots.txt, stays on its host,
    waits between requests and is bounded by the time limit and the safety ceiling. on_progress({site: pages_so_far}) is called
    about once a second from the calling thread."""
    counts = {site_label(u): 0 for u in urls}

    def one(url):
        label = site_label(url)

        def tick(n, _url):
            counts[label] = n
        try:
            return label, crawl_site(url, max_pages=max_pages_each, delay_seconds=0.25, max_seconds=max_seconds, progress=tick), None
        except Exception as exc:  # report per site, keep the others
            return label, [], str(exc)
    with ThreadPoolExecutor(max_workers=min(4, len(urls) or 1)) as pool:
        futures = [pool.submit(one, u) for u in urls]
        while not all(f.done() for f in futures):
            if on_progress:
                on_progress(dict(counts))
            time.sleep(1)
        results = [f.result() for f in futures]
    return {label: {"pages": pages, "error": err, "stopped_by": getattr(pages, "stopped_by", None)} for label, pages, err in results}


def save_csv(df: pd.DataFrame, name: str) -> str:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / name
    friendly(df).to_csv(path, index=False, encoding="utf-8-sig")
    return str(path)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return friendly(df).to_csv(index=False).encode("utf-8-sig")


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """One row per site with averages; has_jsonld becomes a percentage of pages."""
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["has_jsonld"] = work["has_jsonld"].astype(float) * 100
    work["has_canonical"] = (work["canonical"].astype(str) != "").astype(float) * 100
    cols = NUMERIC + ["has_jsonld", "has_canonical"]
    summary = work.groupby("site")[cols].mean().round(1)
    summary.insert(0, "pages", work.groupby("site").size())
    return summary


# Navigation / boilerplate words that say nothing about the topic.
GENERIC = {"get", "see", "free", "official", "national", "organization", "home", "page", "search", "menu", "login", "sign", "join",
           "newsletter", "subscribe", "contact", "about", "privacy", "terms", "cookies", "experts", "expert", "tips"}


def _terms(text: str) -> set[str]:
    return {t for t in tokens(text) if t not in STOP and len(t) > 2}


def keyword_gaps(local_df: pd.DataFrame, comp_df: pd.DataFrame, limit: int = 12) -> list[dict]:
    """Words that appear in several competitor titles/H1/H2s but nowhere in ours."""
    ours = set()
    for _, r in local_df.iterrows():
        ours |= _terms(f"{r['title']} {r['h1']} {r.get('h2_list', '')}")
    brand_text = " ".join(comp_df["site"].unique()).replace(".", "").lower()  # e.g. "lonelyplanetcom roughguidescom"

    def useful(term: str) -> bool:
        return not term.isdigit() and term not in GENERIC and term not in brand_text

    sites_using: dict[str, set[str]] = {}
    for _, r in comp_df.iterrows():
        for t in filter(useful, _terms(f"{r['title']} {r['h1']} {r.get('h2_list', '')}")):
            sites_using.setdefault(t, set()).add(r["site"])
    # A term only counts when at least two different competitors use it, which filters out one site's own vocabulary.
    ranked = sorted(((t, len(s)) for t, s in sites_using.items() if len(s) >= 2 and t not in ours), key=lambda x: (-x[1], x[0]))
    return [{"term": t, "competitor_sites": c} for t, c in ranked[:limit]]


def make_insights(local_sum: pd.Series, comp_sum: pd.Series) -> list[dict]:
    """Compare our site averages with the competitor average and phrase each gap as a recommendation."""
    out = []

    def add(area, key, rec, priority, fmt="{:.0f}"):
        out.append({"area": area, "local": fmt.format(local_sum[key]), "competitors": fmt.format(comp_sum[key]),
                    "recommendation": rec, "priority": priority})

    if local_sum["word_count"] < 0.6 * comp_sum["word_count"]:
        add("Content depth (words)", "word_count",
            "Competitor pages are much longer. Add verifiable detail (practical tips, what to check, how to plan) in the page's own words; do not pad.", "high")
    if local_sum["h2_count"] < comp_sum["h2_count"] - 1:
        add("Subheadings (H2)", "h2_count", "Competitors break topics into more sections. Add descriptive subheadings.", "medium", "{:.1f}")
    if local_sum["has_jsonld"] < comp_sum["has_jsonld"]:
        add("Structured data (% pages)", "has_jsonld", "Competitors publish JSON-LD. Add schema.org markup to the site template (developer task).", "medium")
    if local_sum["alt_coverage"] < 100:
        add("Image alt text (%)", "alt_coverage", "Add descriptive alt text to every image.", "high")
    if local_sum["image_count"] < comp_sum["image_count"] * 0.5:
        add("Images per page", "image_count", "Competitors use more imagery. Add relevant images with alt text.", "low", "{:.1f}")
    if local_sum["internal_links"] < comp_sum["internal_links"] * 0.5:
        add("Internal links", "internal_links", "Link related guides together so visitors and crawlers can navigate between topics.", "low")
    if not 30 <= local_sum["title_len"] <= 65:
        add("Title length", "title_len", "Aim for roughly 30-65 characters with the main topic first.", "medium")
    if not 70 <= local_sum["desc_len"] <= 165:
        add("Meta description length", "desc_len", "Write page-specific descriptions of roughly 70-160 characters.", "medium")
    return out


def build_benchmark(local_df: pd.DataFrame, comp_df: pd.DataFrame) -> dict:
    summary = summarize(pd.concat([local_df, comp_df], ignore_index=True))
    local_label = local_df["site"].iloc[0]
    comp_sum = summary.drop(index=local_label).mean(numeric_only=True)
    local_sum = summary.loc[local_label]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "local_site": local_label,
        "competitors": sorted(comp_df["site"].unique().tolist()),
        "local_summary": local_sum.to_dict(),
        "competitor_average": comp_sum.to_dict(),
        "insights": make_insights(local_sum, comp_sum),
        "keyword_gaps": keyword_gaps(local_df, comp_df),
    }


def save_benchmark(bench: dict) -> None:
    _bench_file().write_text(json.dumps(bench, indent=2, ensure_ascii=False), encoding="utf-8")


def load_benchmark() -> dict | None:
    try:
        return json.loads(_bench_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def record_snapshot(local_df: pd.DataFrame, comp_avg_score: float | None) -> None:
    """Remember our average score over time so the dashboard can show how much it improved."""
    history = load_history()
    history.append({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "local_score": round(float(local_df["score"].mean()), 1),
        "local_words": round(float(local_df["word_count"].mean()), 1),
        "competitor_score": None if comp_avg_score is None else round(float(comp_avg_score), 1),
    })
    _history_file().write_text(json.dumps(history[-50:], indent=2), encoding="utf-8")


def load_history() -> list[dict]:
    try:
        return json.loads(_history_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


# Metrics where a higher value is better for a leaderboard (length metrics are excluded: "longer" is not "better").
RANKED = {"word_count": "Words per page", "h2_count": "H2 headings per page", "image_count": "Images per page",
          "alt_coverage": "Alt text coverage %", "internal_links": "Internal links per page", "has_jsonld": "Structured data % of pages",
          "has_canonical": "Canonical % of pages"}


def rank_table(summary: pd.DataFrame, local_label: str) -> pd.DataFrame:
    """Our rank (1 = best) among all crawled sites for each metric, with the best site and the median."""
    rows = []
    for key, label in RANKED.items():
        col = summary[key]
        rank = int((col > col[local_label]).sum()) + 1  # ties share the better rank
        rows.append({"Metric": label, "Ours": round(float(col[local_label]), 1), "Rank": f"{rank} of {len(col)}", "rank_n": rank,
                     "Best": f"{col.idxmax()} ({col.max():.0f})", "Median": round(float(col.median()), 1),
                     "Position": "ahead" if rank <= (len(col) + 1) // 2 and col[local_label] >= col.median() else "behind"})
    return pd.DataFrame(rows)


def load_frame(name: str) -> pd.DataFrame:
    """Reload an exported CSV back into the internal column names (so results survive a page refresh)."""
    path = EXPORT_DIR / name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig").fillna("")
    reverse = {v: k for k, v in COLUMNS}
    df = df.rename(columns={"Site": "site", "H2 headings": "h2_list", **reverse})
    df["has_jsonld"] = df["has_jsonld"].astype(str).str.lower().isin({"true", "1"})
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df



def match_competitor_pages(page: dict, comp_df: pd.DataFrame, limit: int = 3, site: str | None = None) -> list[dict]:
    """For one of our pages, the closest crawled page of each competitor (by title, H1, headings and URL words).

    Returns structure only (title, description, H1, headings, word count, schema types), never body text, so the model can learn
    how similar pages are organised without being handed text to copy."""
    if comp_df is None or comp_df.empty:
        return []
    if site:  # only this competitor's pages
        comp_df = comp_df[comp_df["site"] == site]
    brand = set(site_state.label().replace("-", "").split("."))
    clean = lambda text: {t for t in _terms(text) if t not in GENERIC and t not in brand}
    path = page.get("path", "/")
    ours = clean(" ".join([page.get("title", ""), page.get("h1", ""), path.replace("-", " ").replace("/", " "), " ".join(page.get("h2", []))]))
    best: dict[str, dict] = {}
    for _, r in comp_df.iterrows():
        their_path = urlparse(str(r["url"])).path
        theirs = clean(f"{r['title']} {r['h1']} {r.get('h2_list', '')} {their_path.replace('-', ' ').replace('/', ' ')}")
        shared = ours & theirs
        if not ours or not theirs:
            continue
        score = len(shared) / ((len(ours) * len(theirs)) ** 0.5)
        if path.strip("/") == "" and their_path.strip("/") == "":
            score += 0.25  # home page <-> home page
        if score < 0.2:  # weak overlaps (a couple of generic shared words) would mislead the model
            continue
        if r["site"] not in best or score > best[r["site"]]["score"]:
            best[r["site"]] = {"site": r["site"], "url": r["url"], "score": round(score, 2), "shared": sorted(shared)[:8],
                               "title": str(r["title"]), "description": str(r["description"]), "h1": str(r["h1"]),
                               "h2": [h for h in str(r.get("h2_list", "")).split(" | ") if h],
                               "word_count": int(r["word_count"]), "schema": str(r.get("jsonld_types", "") or "")}
    return sorted(best.values(), key=lambda m: -m["score"])[:limit]


def topic_gaps(page_text: str, matches: list[dict], limit: int = 6) -> list[str]:
    """Headings of matched competitor pages whose words mostly do not appear on our page."""
    ours = {t for t in tokens(page_text) if t not in STOP}
    gaps: list[str] = []
    for m in matches:
        for h in m["h2"]:
            words = {t for t in _terms(h) if t not in GENERIC}
            if len(words) >= 1 and len(words & ours) / len(words) < 0.5 and h not in gaps:
                gaps.append(h)
    return gaps[:limit]
