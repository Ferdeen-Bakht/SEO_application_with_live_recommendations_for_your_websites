"""Extract measurable SEO signals from a page and turn them into an explainable 0-100 score.

The score is a learning aid: it adds up simple, visible checks (title, description, headings, depth, images,
technical basics). It is not a Google score and says nothing about rankings.
"""
import json
import re
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup

STOP = set("""a an the and or but of to in on at for from by with without about as is are was were be been being it its this that
these those your you our we they their his her not no yes more most less than then so if into out up down over under how what when
where which who why can will just also very all any each other some such only own same too s t""".split())


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", (text or "").lower())


def key_terms(text: str, limit: int = 4) -> list[str]:
    return [t for t in tokens(text) if t not in STOP and len(t) > 2][:limit]


def coverage(terms: list[str], text: str) -> float:
    if not terms:
        return 0.0
    seen = set(tokens(text))
    return sum(t in seen for t in terms) / len(terms)


def word_count(text: str) -> int:
    return len(tokens(text))


def _canonical(soup: BeautifulSoup, url: str) -> str:
    tag = soup.find("link", rel=lambda v: v and "canonical" in ([x.lower() for x in v] if isinstance(v, list) else str(v).lower().split()))
    return urljoin(url, tag["href"]) if tag and tag.get("href") else ""


def _jsonld_types(soup: BeautifulSoup) -> list[str]:
    found = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except ValueError:
            continue
        for node in (data if isinstance(data, list) else [data]):
            if isinstance(node, dict):
                kind = node.get("@type")
                found.extend(kind if isinstance(kind, list) else [kind or "unknown"])
    return [str(x) for x in found]


BLOCK_TAGS = ["p", "div", "li", "section", "article", "ul", "ol", "table", "h1", "h2", "h3", "h4", "form"]


def extract_paragraphs(html: str, min_words: int = 8, limit: int = 40) -> list[str]:
    """Readable text blocks of the main content: <p>, <li>, and div/span leaves (React sites often skip <p>)."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
        element.decompose()
    seen, blocks = set(), []
    for el in (soup.body or soup).find_all(["p", "li", "div", "span", "blockquote"]):
        if el.find(BLOCK_TAGS):  # only leaf blocks, so text is not repeated by its parents
            continue
        text = el.get_text(" ", strip=True)
        if word_count(text) >= min_words and text not in seen:
            seen.add(text)
            blocks.append(text)
    return blocks[:limit]


def extract_metrics(html: str, url: str, status_code: int = 200) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(url).netloc
    title_tag = soup.find("title")
    desc_tag = soup.find("meta", attrs={"name": lambda v: isinstance(v, str) and v.lower() == "description"})
    robots_tag = soup.find("meta", attrs={"name": lambda v: isinstance(v, str) and v.lower() == "robots"})
    viewport = soup.find("meta", attrs={"name": lambda v: isinstance(v, str) and v.lower() == "viewport"})
    html_tag = soup.find("html")
    jsonld = _jsonld_types(soup)

    images = soup.find_all("img")
    img_missing_alt = [i.get("src", "") for i in images if not (i.get("alt") or "").strip()]

    internal = external = empty_anchor = 0
    external_urls: list[str] = []
    for a in soup.find_all("a", href=True):
        dest = urldefrag(urljoin(url, a["href"].strip()))[0]
        if urlparse(dest).scheme not in {"http", "https"}:
            continue
        if urlparse(dest).netloc == host:
            internal += 1
        else:
            external += 1
            if dest not in external_urls and len(external_urls) < 40:
                external_urls.append(dest)
        if not a.get_text(strip=True) and not a.find("img"):
            empty_anchor += 1

    # Resources the page loads (for size and mixed-content checks) and the share of the HTML that is visible text.
    script_srcs = [urljoin(url, t["src"]) for t in soup.find_all("script", src=True)][:60]
    css_hrefs = [urljoin(url, t["href"]) for t in soup.find_all("link", href=True)
                 if "stylesheet" in ([x.lower() for x in t.get("rel", [])] if isinstance(t.get("rel"), list) else str(t.get("rel", "")).lower().split())][:40]
    insecure = []
    if urlparse(url).scheme == "https":
        for t in soup.find_all(["script", "img", "iframe", "audio", "video", "source", "link"]):
            ref = t.get("src") or (t.get("href") if t.name == "link" else "") or ""
            if ref.strip().lower().startswith("http://"):
                insecure.append(ref.strip())
    visible = sum(len(x.strip()) for x in soup.find_all(string=True)
                  if x.parent and x.parent.name not in {"script", "style", "noscript", "head", "title", "meta", "link", "svg"} and type(x).__name__ == "NavigableString")
    html_bytes = len(html.encode("utf-8", "ignore"))
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    region = soup.find("main") or soup.find("article") or soup.body or soup
    for element in region(["nav", "footer", "aside", "header"]):
        element.decompose()
    body_text = region.get_text(" ", strip=True)

    h1s = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")]
    h3s = [h.get_text(" ", strip=True) for h in soup.find_all("h3")]
    path = urlparse(url).path
    segments = [s for s in path.split("/") if s]
    title = title_tag.get_text(" ", strip=True) if title_tag else ""
    description = (desc_tag.get("content") or "").strip() if desc_tag else ""
    return {
        "url": url,
        "status_code": status_code,
        "title": title,
        "title_len": len(title),
        "description": description,
        "desc_len": len(description),
        "h1": h1s[0] if h1s else "",
        "h1_count": len(h1s),
        "h2_count": len(h2s),
        "h3_count": len(h3s),
        "h2_list": h2s[:15],
        "list_items": len(region.find_all("li")),
        "word_count": word_count(body_text),
        "image_count": len(images),
        "images_missing_alt": len(img_missing_alt),
        "missing_alt_srcs": img_missing_alt[:10],
        "alt_coverage": round(100 * (len(images) - len(img_missing_alt)) / len(images)) if images else 100,
        "internal_links": internal,
        "external_links": external,
        "empty_anchors": empty_anchor,
        "canonical": _canonical(soup, url),
        "robots_meta": (robots_tag.get("content") or "") if robots_tag else "",
        "has_viewport": bool(viewport),
        "has_lang": bool(html_tag and html_tag.get("lang")),
        "jsonld_types": jsonld,
        "has_jsonld": bool(jsonld),
        "url_depth": len(segments),
        "url_slug_len": len(segments[-1]) if segments else 0,
        "url_has_query": bool(urlparse(url).query),
        "is_https": urlparse(url).scheme == "https",
        "html_bytes": html_bytes,
        "text_ratio": round(100 * visible / html_bytes, 1) if html_bytes else 0.0,
        "script_srcs": script_srcs,
        "css_hrefs": css_hrefs,
        "external_urls": external_urls,
        "mixed_content": insecure[:10],
    }


def score_metrics(m: dict, keyword: str | None = None) -> dict:
    """Return {'total': 0-100, 'parts': [...]} with a plain-language note for every part."""
    terms = key_terms(keyword) if keyword else key_terms(m.get("title", ""))
    parts = []

    def add(name, points, maximum, note):
        parts.append({"name": name, "points": round(points, 1), "max": maximum, "note": note})

    tl, title = m.get("title_len", 0), m.get("title", "")
    pts = (5 if title else 0) + (5 if 30 <= tl <= 65 else 2 if title else 0) + 5 * coverage(terms, title)
    add("Title", pts, 15, f"{tl} characters; covers {round(100 * coverage(terms, title))}% of the key terms")

    dl, desc = m.get("desc_len", 0), m.get("description", "")
    pts = (5 if desc else 0) + (5 if 70 <= dl <= 165 else 2 if desc else 0) + 5 * coverage(terms, desc)
    add("Meta description", pts, 15, f"{dl} characters; covers {round(100 * coverage(terms, desc))}% of the key terms")

    h1 = m.get("h1", "")
    pts = (5 if m.get("h1_count", 0) == 1 else 2 if h1 else 0) + 5 * coverage(terms, h1)
    add("H1 heading", pts, 10, f"{m.get('h1_count', 0)} H1; covers {round(100 * coverage(terms, h1))}% of the key terms")

    wc = m.get("word_count", 0)
    pts = 20 if wc >= 1000 else 16 if wc >= 600 else 12 if wc >= 300 else 7 if wc >= 150 else 3
    add("Content depth", pts, 20, f"{wc} words of main content")

    h2 = m.get("h2_count", 0)
    pts = (6 if h2 >= 3 else 3 if h2 >= 1 else 0) + (4 if (m.get("h3_count", 0) or m.get("list_items", 0) >= 3) else 0)
    add("Structure", pts, 10, f"{h2} H2 headings, {m.get('h3_count', 0)} H3, {m.get('list_items', 0)} list items")

    imgs = m.get("image_count", 0)
    pts = (4 if imgs else 0) + 6 * (m.get("alt_coverage", 100) / 100 if imgs else 0)
    add("Images & alt text", pts, 10, f"{imgs} images, {m.get('alt_coverage', 100)}% have alt text")

    pts = (5 if m.get("canonical") else 0) + (2 if m.get("has_viewport") else 0) + (2 if m.get("has_lang") else 0) \
        + (3 if "noindex" not in m.get("robots_meta", "").lower() else 0) + (3 if m.get("has_jsonld") else 0)
    add("Technical basics", pts, 15, "canonical, viewport, lang, no noindex, structured data")

    il = m.get("internal_links", 0)
    add("Internal links", 5 if il >= 3 else il * 5 / 3, 5, f"{il} internal links")

    return {"total": round(sum(p["points"] for p in parts)), "parts": parts, "terms": terms}


def apply_field_changes(m: dict, original: dict, proposed: dict) -> dict:
    """Estimate metrics after replacing title / description / H1 / intro paragraphs (everything else unchanged)."""
    new = dict(m)
    new["title"], new["title_len"] = proposed["title"], len(proposed["title"])
    new["description"], new["desc_len"] = proposed["metaDescription"], len(proposed["metaDescription"])
    new["h1"] = proposed["h1"]
    old_words = word_count(original["h1"] + " " + " ".join(original["paragraphs"]))
    new_words = word_count(proposed["h1"] + " " + " ".join(proposed["paragraphs"]))
    new["word_count"] = max(0, m.get("word_count", 0) - old_words + new_words)
    return new
