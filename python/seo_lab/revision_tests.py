"""Compare an original text with an AI-proposed text: accuracy, clarity, keyword relevance, useful detail.

All checks are simple and explainable. They help a reviewer look in the right place; they do not replace reading the text.
"""
import re

from seo_lab.page_metrics import STOP, coverage, key_terms, tokens

HYPE = ["guaranteed", "guarantee", "best in the world", "#1", "number one", "cheapest", "top-rated", "unbeatable", "ultimate", "perfect"]
LIMITS = {"title": (30, 65), "metaDescription": (70, 165), "h1": (15, 90)}


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _proper_nouns(text: str) -> set[str]:
    found = set()
    for sentence in re.split(r"(?<=[.!?:])\s+", text):
        words = re.findall(r"[^\W\d_][\w'’\-]*", sentence)
        for w in words[1:]:  # the first word of a sentence is capitalized anyway
            if w[:1].isupper() and w.lower() not in STOP:
                found.add(w.lower())
    return found


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,.]*", text))


def _unsupported(proposed: str, source_text: str, check_names: bool = True) -> list[str]:
    source_tokens = set(tokens(source_text))
    source_numbers = _numbers(source_text)
    issues = [f"number '{n}'" for n in sorted(_numbers(proposed) - source_numbers)]
    if check_names:  # Title Case headings would make every capitalized word look like a new name
        for noun in sorted(_proper_nouns(proposed)):
            if all(part not in source_tokens for part in tokens(noun)):
                issues.append(f"name '{noun}'")
    return issues


def _overlap(a: str, b: str) -> float:
    ta = {t for t in tokens(a) if t not in STOP}
    tb = {t for t in tokens(b) if t not in STOP}
    return len(ta & tb) / max(1, len(ta | tb))


def _longest_run(a: list[str], b: list[str]) -> int:
    """Longest run of consecutive identical words shared by two word lists."""
    best, prev = 0, [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def mixed_up(original: str, proposed: str, others: list[str]) -> bool:
    """True when a rewrite resembles another paragraph of the page more than the paragraph it was meant to rewrite."""
    own = _overlap(original, proposed)
    borrowed = max((_overlap(o, proposed) for o in others if o), default=0.0)
    return borrowed > own and borrowed >= 0.2


def compare(field: str, original: str, proposed: str, keyword: str, source_text: str, others: list[str] | None = None,
            reference_text: str = "") -> dict:
    """field: title | metaDescription | h1 | paragraph. Returns four 0-100 scores plus notes and a verdict."""
    notes = []
    terms = key_terms(keyword)

    # Accuracy: new facts (numbers, names) must already exist in the page; hype claims are flagged.
    unsupported = _unsupported(proposed, source_text + " " + original, check_names=field not in {"title", "h1"})
    hype = [h for h in HYPE if h in proposed.lower() and h not in original.lower()]
    accuracy = _clamp(100 - 25 * len(unsupported) - 25 * len(hype))
    ratio = len(proposed) / max(1, len(original)) if field == "paragraph" and original else 1.0
    if field == "paragraph" and original and others:
        if mixed_up(original, proposed, others):  # the rewrite resembles another paragraph of the page more than its own source
            accuracy = min(accuracy, 40)
            notes.append("Reads like a different paragraph of this page, not a rewrite of this one.")
    if unsupported:
        notes.append("Not found in the current page, verify: " + ", ".join(unsupported[:5]))
    if hype:
        notes.append("Unsupported superlative or promise: " + ", ".join(hype))

    # Clarity: sensible length, short sentences, no repeated-word stuffing.
    clarity = 100
    if field in LIMITS:
        low, high = LIMITS[field]
        if len(proposed) < low:
            clarity -= min(35, low - len(proposed))
            notes.append(f"Short for a {field} ({len(proposed)} chars; aim for {low}-{high}).")
        elif len(proposed) > high:
            clarity -= min(35, len(proposed) - high)
            notes.append(f"Long for a {field} ({len(proposed)} chars; aim for {low}-{high}).")
    sentences = [s for s in re.split(r"[.!?]+\s", proposed) if s.strip()]
    avg = sum(len(tokens(s)) for s in sentences) / max(1, len(sentences))
    if avg > 24:
        clarity -= min(30, int((avg - 24) * 3))
        notes.append(f"Long sentences (average {avg:.0f} words).")
    freq = {}
    for t in tokens(proposed):
        if t not in STOP and len(t) > 3:
            freq[t] = freq.get(t, 0) + 1
    repeats = [t for t, c in freq.items() if c >= 4]
    if repeats:
        clarity -= 15
        notes.append("Repeated word(s): " + ", ".join(repeats[:3]))
    clarity = _clamp(clarity)

    # Keyword relevance: key terms present where they matter, without stuffing.
    weight_fields = {"title", "metaDescription", "h1"}
    cov = coverage(terms, proposed) if terms else 0.0
    if field in weight_fields:
        keyword_score = 100 * cov
    else:
        keyword_score = 60 + 40 * cov  # body paragraphs only need natural, light use
    all_tokens = tokens(proposed)
    density = sum(all_tokens.count(t) for t in terms) / max(1, len(all_tokens)) if terms else 0
    if len(all_tokens) >= 30 and density > 0.08:  # density is meaningless for short titles and descriptions
        keyword_score -= 30
        notes.append("Key terms look overused (possible keyword stuffing).")
    if terms and cov < 0.5 and field in weight_fields:
        notes.append("Few of the target keyword's terms appear here.")
    keyword_score = _clamp(keyword_score)

    # Useful detail: keeps what was already there and adds meaningful new words.
    orig_terms = {t for t in tokens(original) if t not in STOP}
    new_terms = {t for t in tokens(proposed) if t not in STOP}
    kept = 1.0 if field == "paragraph_new" else len(orig_terms & new_terms) / max(1, len(orig_terms))
    added = len(new_terms - orig_terms)
    detail = 55 + min(30, added * 4) - (45 * (0.5 - kept) * 2 if kept < 0.5 else 0)
    if kept < 0.5:
        notes.append(f"Drops much of the original wording (keeps {round(100 * kept)}% of its key words).")
    if added == 0 and proposed.strip() != original.strip():
        notes.append("Rewords the text without adding new detail.")
    detail = _clamp(detail)

    if field == "paragraph" and original and ratio < 0.5:
        notes.append(f"Much shorter than the original ({round(100 * ratio)}% of its length); information may have been lost.")
    # Competitor reference: copied wording is rejected; leaning on the competitor's vocabulary instead of ours is flagged.
    lean_ref = 0.0
    if reference_text:
        run = _longest_run(tokens(proposed), tokens(reference_text))
        if run >= 8:
            accuracy = min(accuracy, 40)
            notes.append(f"Copies {run} consecutive words from the competitor page; rewrite it in our own words.")
        mine = {t for t in tokens(proposed) if t not in STOP and len(t) > 2}
        ours = set(tokens(source_text + " " + original))
        theirs_only = set(tokens(reference_text)) - ours
        lean_ref = len(mine & theirs_only) / max(1, len(mine))
        if lean_ref > 0.25:
            notes.append(f"{round(100 * lean_ref)}% of its key words appear only on the competitor page, not on ours; check it still describes our business.")
    overall = _clamp(0.35 * accuracy + 0.25 * clarity + 0.20 * keyword_score + 0.20 * detail)
    if accuracy < 75:
        verdict = "Check facts"
    elif overall >= 75:
        verdict = "Looks good"
    elif overall >= 55:
        verdict = "Review"
    else:
        verdict = "Risky"
    if lean_ref > 0.4 and verdict != "Check facts":
        verdict = "Risky"
    elif lean_ref > 0.25 and verdict == "Looks good":
        verdict = "Review"
    if field == "paragraph" and original:  # a rewrite that throws away the source text is never "good", whatever else scores well
        if kept < 0.15 and verdict != "Check facts":
            verdict = "Risky"
        elif (kept < 0.3 or ratio < 0.5) and verdict == "Looks good":
            verdict = "Review"
    return {"accuracy": accuracy, "clarity": clarity, "keyword": keyword_score, "detail": detail,
            "overall": overall, "verdict": verdict, "notes": notes}
