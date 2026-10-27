"""The SEO agent: inspect a page, benchmark it, ask the local LLM for edits, test each edit, and let a human accept or reject.

The agent only builds *suggestions* for a live website. Nothing is ever written to the site; a human applies accepted changes.
"""
import re

from seo_lab import benchmark as bm
from seo_lab import local_llm, site_state
from seo_lab.page_metrics import apply_field_changes, score_metrics
from seo_lab.revision_tests import compare
from seo_lab import reference as ref_mod
from seo_lab.serp import serp_hints, top_competitor, top_competitor_hint
from seo_lab.technical_seo import run_technical_checks


def page_full_text(page: dict) -> str:
    parts = [page.get("title", ""), page.get("metaDescription", ""), page.get("h1", ""), page.get("tagline") or ""]
    parts += page.get("paragraphs", [])
    parts.append(page.get("body_text") or "")
    for s in page.get("sections", []):
        parts.append(s.get("heading", ""))
        parts += s.get("paragraphs", []) + s.get("items", [])
        for c in s.get("cards", []):
            parts += [c.get("title", ""), c.get("text", "")]
    return "\n".join(p for p in parts if p)


def derive_keyword(page: dict) -> str:
    head = re.split(r"[:|]", page.get("title", ""))[0].strip()
    if page.get("path", "/") != "/":  # inner pages often inherit the home title; their own H1 or URL says more
        if page.get("h1"):
            return page["h1"]
        if re.search(r"[:|]", page.get("title", "")) and len(head.split()) >= 2:  # a title that names this page, e.g. "Risk Disclosure: ..."
            return head
        stem = site_state.label().split(".")[0]
        return f"{stem} {page['path'].strip('/').split('/')[-1].replace('-', ' ')}".strip()
    return head if len(head.split()) >= 2 else page.get("h1", head)


def benchmark_hints(bench: dict | None) -> list[str]:
    if not bench:
        return []
    comp, local = bench["competitor_average"], bench["local_summary"]
    hints = [
        f"Competitor pages average {comp['word_count']:.0f} words and {comp['h2_count']:.1f} H2 headings; ours average "
        f"{local['word_count']:.0f} words and {local['h2_count']:.1f} H2s.",
        f"Competitor titles average {comp['title_len']:.0f} characters and descriptions {comp['desc_len']:.0f}.",
    ]
    gaps = [g["term"] for g in bench.get("keyword_gaps", [])[:8]]
    if gaps:
        hints.append("Words competitors use in titles/headings that we do not (use only if true for this page): " + ", ".join(gaps))
    return hints


def competitor_hints(page: dict, page_text: str, site: str | None = None) -> tuple[list[str], list[dict]]:
    """The closest competitor page (structure only; of one competitor if `site` is given) and topics it covers that this page does not mention."""
    try:
        matches = bm.match_competitor_pages(page, bm.load_frame(bm.comp_csv()), limit=1, site=site)
    except Exception:  # no competitor crawl yet, or an older CSV
        return [], []
    hints = []
    for m in matches:
        path = urlparse_path(m["url"])
        schema = f"; schema: {m['schema']}" if m["schema"] else ""
        hints.append(f"Closest competitor page {m['site']}{path}: title \"{m['title'][:90]}\"; description \"{m['description'][:150]}\"; "
                     f"H1 \"{m['h1'][:80]}\"; headings: {', '.join(m['h2'][:8]) or '(none)'}; {m['word_count']} words{schema}")
    if matches:
        ours = f"This page has {len(page_text.split())} words and headings: {', '.join(page.get('h2', [])[:8]) or '(none)'}."
        hints.append(ours)
        gaps = bm.topic_gaps(page_text, matches)
        if gaps:
            hints.append("Topics matched competitor pages cover that this page does not mention (add one only if it is true for this business): " + "; ".join(gaps))
    return hints, matches


def urlparse_path(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).path or "/"


def analyze(page: dict, base_url: str, known_paths: set[str], bench: dict | None, keyword: str = "", extra_facts: str = "", serp: dict | None = None,
            use_reference: bool = True, extra_paragraph: bool = True) -> dict:
    """Run the full agent pass and return everything the UI needs."""
    tech = run_technical_checks(base_url, page["path"], known_paths)
    keyword = keyword.strip() or derive_keyword(page)
    source_text = page_full_text(page) + "\n" + extra_facts
    # ONE competitor: the best-ranked one for this page's keyword. Its page is the reference; nothing is averaged over other competitors.
    top = top_competitor(serp, keyword, page.get("title", "") + " " + page.get("h1", "")) if use_reference else None
    reference = None
    if top:
        reference = ref_mod.fetch_reference(top["url"])
        if reference.get("error") and (top.get("title") or top.get("snippet")):
            reference = ref_mod.from_snippet(top, reference["error"])
    full_page = bool(reference) and not reference.get("error") and reference.get("source") != "search snippet"
    # The fetched page already carries its title/description/headings, so a separate "closest page" line is only needed as a fallback.
    comp_hints, matches = ([], []) if full_page else competitor_hints(page, page_full_text(page), site=top["domain"] if top else None)
    competitor_lines = [top_competitor_hint(top, serp)] if top else benchmark_hints(bench) + serp_hints(serp, keyword)  # no ranking data: fall back to averages
    hints = competitor_lines + comp_hints + [f"{c['name']}: {c['detail']}" for c in tech["checks"] if c["status"] != "pass" and c["key"] in {"alt", "canonical"}]
    ref_text = ref_mod.reference_text(reference)
    suggestion = local_llm.suggest_changes(page, keyword, source_text, hints, extra_facts, ref_mod.prompt_block(reference, top, 1000), extra_paragraph,
                                           ref_mod.prompt_block(reference, top, 650))

    original = {"title": page["title"], "metaDescription": page["metaDescription"], "h1": page["h1"], "paragraphs": list(page["paragraphs"])}
    changes = []

    def add(cid, label, field, original_text, proposed_text, reason, index=None):
        if not proposed_text or " ".join(proposed_text.split()) == " ".join((original_text or "").split()):
            return
        changes.append({"id": cid, "kind": "content", "label": label, "field": field, "index": index,
                        "original": original_text, "proposed": proposed_text, "reason": reason or "Suggested by the agent.",
                        "tests": compare("paragraph" if field == "paragraph" else field, original_text, proposed_text, keyword, source_text,
                                         others=[x for j, x in enumerate(original["paragraphs"]) if j != index] if field == "paragraph" else None,
                                         reference_text=ref_text)})

    add("title", "HTML title", "title", original["title"], suggestion["title"], suggestion["title_reason"])
    add("meta", "Meta description", "metaDescription", original["metaDescription"], suggestion["metaDescription"], suggestion["meta_reason"])
    add("h1", "H1 heading", "h1", original["h1"], suggestion["h1"], suggestion["h1_reason"])
    for i, p in enumerate(suggestion["paragraphs"]):
        if i < len(original["paragraphs"]):
            add(f"p{i}", f"Paragraph {i + 1}", "paragraph", original["paragraphs"][i], p["text"], p["reason"], i)
        else:
            add(f"padd{i}", "New paragraph", "paragraph_new", "", p["text"], p["reason"], i)
    for c in changes:
        if c["field"] == "paragraph_new":  # nothing to compare with: judge it against the page it extends
            c["tests"] = compare("paragraph_new", " ".join(original["paragraphs"]), c["proposed"], keyword, source_text, reference_text=ref_text)

    # Score impact of each change on its own, and a note when the H1 just repeats the title.
    base_total = score_metrics(tech["metrics"], keyword)["total"]
    norm = lambda s: " ".join((s or "").lower().split())
    final_title = next((c["proposed"] for c in changes if c["id"] == "title"), original["title"])
    for c in changes:
        solo, _, _ = apply_decisions({"original": original, "changes": [c]}, {c["id"]: "accepted"})
        c["score_delta"] = score_metrics(apply_field_changes(tech["metrics"], original, solo), keyword)["total"] - base_total
        if c["id"] == "h1" and norm(c["proposed"]) == norm(final_title):
            c["tests"]["notes"].append("Identical to the title; a slightly different H1 can add context for readers.")
            if c["tests"]["verdict"] == "Looks good":
                c["tests"]["verdict"] = "Review"
        if c["score_delta"] < 0:
            c["tests"]["notes"].append(f"Lowers the estimated SEO score by {-c['score_delta']} point(s).")
            if c["tests"]["verdict"] == "Looks good":
                c["tests"]["verdict"] = "Review"

    for check in tech["checks"]:
        if check["status"] != "pass":
            changes.append({"id": f"tech_{check['key']}", "kind": "technical", "label": check["name"], "status": check["status"],
                            "detail": check["detail"], "fix": check["fix"], "reason": check["fix"]})

    base = tech["metrics"]
    return {"keyword": keyword, "original": original, "changes": changes, "technical": tech["checks"], "base_metrics": base,
            "score_before": score_metrics(base, keyword), "hints": hints, "skipped": suggestion.get("skipped", []), "matches": matches, "reference": ({"domain": top["domain"], "url": top["url"], "position": top["position"], "keyword": top["keyword"],
                       **{k: reference.get(k) for k in ("word_count", "error", "fetch_error", "source")}} if top and reference else None), "source_text": source_text}


def apply_decisions(analysis: dict, decisions: dict[str, str]) -> tuple[dict, list[str], list[dict]]:
    """Return (proposed fields, developer to-do list, accepted content changes) for the accepted changes."""
    proposed = {**analysis["original"], "paragraphs": list(analysis["original"]["paragraphs"])}
    todo, accepted = [], []
    additions = []
    for c in analysis["changes"]:
        if decisions.get(c["id"]) != "accepted":
            continue
        if c["kind"] == "technical":
            todo.append(f"{c['label']}: {c['fix']} ({c['detail']})")
            continue
        accepted.append(c)
        if c["field"] in {"title", "metaDescription", "h1"}:
            proposed[c["field"]] = c["proposed"]
        elif c["field"] == "paragraph":
            proposed["paragraphs"][c["index"]] = c["proposed"]
        else:
            additions.append(c["proposed"])
    proposed["paragraphs"] += additions
    return proposed, todo, accepted


def score_after(analysis: dict, proposed: dict) -> dict:
    return score_metrics(apply_field_changes(analysis["base_metrics"], analysis["original"], proposed), analysis["keyword"])
