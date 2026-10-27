"""Site-wide checks that are built from the crawl results: TLS certificates, broken links, page weight, text ratio, mixed content.

Everything is read-only (TLS handshakes, HEAD/GET requests). Pages crawled before these measurements existed are simply skipped.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import socket
import ssl

import httpx

from seo_lab.crawler import USER_AGENT, _validate_start_url
from seo_lab.site_state import site_label

CERT_WARN_DAYS = 30
JS_CSS_LIMIT = 2 * 1024 * 1024  # total script + stylesheet bytes per page before it counts as heavy
LOW_TEXT_RATIO = 10.0  # percent of the HTML that is visible text
BLOCKED_STATUSES = {401, 403, 405, 429, 999}  # the site refuses automated requests, so we cannot tell if the link works
UNVERIFIABLE_HOSTS = {"x.com", "twitter.com", "facebook.com", "instagram.com", "linkedin.com", "t.me", "tiktok.com", "wa.me", "whatsapp.com", "api.whatsapp.com"}  # answer bots with errors even when the link works
PAGE_SAMPLE = 25  # pages whose scripts and styles are weighed


def _f(key, name, status, detail, fix="", severity="medium", urls=None):
    return {"key": key, "name": name, "status": status, "detail": detail, "fix": fix, "severity": severity, "urls": urls or []}


def certificate_check(host: str) -> dict:
    """TLS handshake: days until the certificate expires, or why it is not trusted."""
    try:
        with socket.create_connection((host, 443), timeout=10) as sock, ssl.create_default_context().wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    except ssl.SSLCertVerificationError as exc:
        return {"host": host, "ok": False, "problem": f"certificate not trusted ({exc.verify_message})"}
    except (OSError, ssl.SSLError) as exc:
        return {"host": host, "ok": None, "problem": f"could not connect on port 443 ({type(exc).__name__})"}
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
    return {"host": host, "ok": True, "expires": expires, "days": (expires - datetime.now(timezone.utc)).days}


def _link_status(url: str) -> int:
    """HTTP status of a link (0 = unreachable or not allowed). HEAD first, GET if the server dislikes HEAD."""
    try:
        _validate_start_url(url)
    except ValueError:
        return 0
    for method in ("HEAD", "GET"):  # HEAD first; GET is the second chance before the link is called dead
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=10) as c:
                r = c.request(method, url)
                if method == "HEAD" and r.status_code in {403, 404, 405, 501}:
                    continue
                return r.status_code
        except httpx.HTTPError:
            continue
    return 0


def _resource_size(url: str) -> int:
    try:
        _validate_start_url(url)
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20)
        return len(r.content) if r.status_code == 200 else 0
    except (ValueError, httpx.HTTPError):
        return 0


def _mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB"


def _certificates(base: str, all_pages: list[dict]) -> list[dict]:
    host = site_label(base)
    hosts = {host}
    for p in all_pages:
        for link in p.get("links", []) + p.get("metrics", {}).get("external_urls", []):
            h = site_label(link)
            if h.endswith("." + host) and len(hosts) < 8:
                hosts.add(h)
    with ThreadPoolExecutor(max_workers=4) as pool:
        certs = list(pool.map(certificate_check, sorted(hosts)))
    bad = [c for c in certs if c["ok"] is False or (c["ok"] and c["days"] < 0)]
    soon = [c for c in certs if c["ok"] and 0 <= c["days"] < CERT_WARN_DAYS]
    out = []
    urls = [f"https://{c['host']}/" for c in bad + soon]
    if bad:
        out.append(_f("cert", "SSL certificate", "fail",
                      "; ".join(f"{c['host']}: " + (c["problem"] if c["ok"] is False else f"expired {-c['days']} day(s) ago") for c in bad),
                      "Renew or replace the certificate right away; browsers show a full-page warning for expired or untrusted certificates.", "high", urls=urls))
    elif soon:
        out.append(_f("cert", "SSL certificate", "warn", "; ".join(f"{c['host']} expires in {c['days']} day(s) ({c['expires']:%Y-%m-%d})" for c in soon),
                      "Renew before it expires and check that automatic renewal (for example Let's Encrypt) works.", "medium", urls=urls))
    elif any(c["ok"] for c in certs):
        out.append(_f("cert", "SSL certificate", "pass", "; ".join(f"{c['host']} valid for {c['days']} more day(s)" for c in certs if c["ok"])))
    for c in certs:
        if c["ok"] is None:
            out.append(_f("cert_" + c["host"], f"SSL certificate ({c['host']})", "warn", f"{c['host']}: {c['problem']}.", "", "low"))
    return out


def _broken_internal(all_pages: list[dict]) -> list[dict]:
    broken = [p for p in all_pages if int(p.get("status_code") or 0) == 0 or int(p.get("status_code") or 0) >= 400]
    broken = [p for p in broken if not any(f.get("issue") == "Blocked by robots.txt" for f in p.get("findings", []))]
    if not broken:
        return [_f("broken_internal", "Broken internal links", "pass", "No crawled page returned an error status.")] if all_pages else []
    linked_from: dict[str, str] = {}
    for p in all_pages:
        for link in p.get("links", []):
            linked_from.setdefault(link.split("#")[0].rstrip("/"), p["url"])
    detail = [f"{p['url']} (HTTP {p.get('status_code') or 'no response'}" + (f", linked from {linked_from[p['url'].rstrip('/')]}" if p["url"].rstrip("/") in linked_from else "") + ")"
              for p in broken[:6]]
    return [_f("broken_internal", "Broken internal links", "fail", f"{len(broken)} crawled page(s) returned an error: " + "; ".join(detail) + ".",
               "Fix the link, restore the page, or 301-redirect the old address to a relevant page.", "high", urls=[p["url"] for p in broken])]


def _broken_external(good: list[dict]) -> list[dict]:
    ext: dict[str, str] = {}
    for p in good:
        for link in p.get("metrics", {}).get("external_urls", []):
            if site_label(link) not in UNVERIFIABLE_HOSTS:
                ext.setdefault(link, p["url"])
    if not ext:
        return []
    urls = list(ext)[:80]
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = dict(zip(urls, pool.map(_link_status, urls)))
    dead = [u for u, st in statuses.items() if st == 0 or st in {404, 410} or st >= 500]
    blocked = [u for u, st in statuses.items() if st in BLOCKED_STATUSES]
    if dead:
        return [_f("broken_external", "Broken external links", "warn",
                   f"{len(dead)} of {len(urls)} checked outside links do not work: "
                   + "; ".join(f"{u} (HTTP {statuses[u] or 'no response'}, on {ext[u]})" for u in dead[:5]) + ".",
                   "Update or remove these links; broken outbound links hurt visitors' trust.", "medium", urls=dead)]
    note = f" ({len(blocked)} others refuse automated checks)" if blocked else ""
    return [_f("broken_external", "Broken external links", "pass", f"All {len(urls) - len(blocked)} verifiable outside links answered{note}.")]


def _script_style_weight(good: list[dict]) -> list[dict]:
    sample = good[:PAGE_SAMPLE]
    wanted = list(dict.fromkeys(r for p in sample for r in p["metrics"].get("script_srcs", []) + p["metrics"].get("css_hrefs", []) if r.startswith(("http://", "https://"))))
    if not wanted:
        return []
    with ThreadPoolExecutor(max_workers=8) as pool:
        sizes = dict(zip(wanted, pool.map(_resource_size, wanted)))
    totals = [(p["url"], sum(sizes.get(r, 0) for r in set(p["metrics"].get("script_srcs", []) + p["metrics"].get("css_hrefs", [])))) for p in sample]
    heavy = [(u, t) for u, t in totals if t > JS_CSS_LIMIT]
    if heavy:
        return [_f("js_css_size", "JavaScript and CSS size", "warn",
                   f"{len(heavy)} page(s) load more than {_mb(JS_CSS_LIMIT)} of scripts and styles (uncompressed): " + ", ".join(f"{u} ({_mb(t)})" for u, t in heavy[:4]) + ".",
                   "Split bundles, remove unused code, minify and serve compressed files so pages load faster.", "medium", urls=[u for u, _ in heavy])]
    return [_f("js_css_size", "JavaScript and CSS size", "pass",
               f"No checked page loads more than {_mb(JS_CSS_LIMIT)} of scripts and styles (largest: {_mb(max(t for _, t in totals))}).")]


def crawl_derived_checks(base: str, good: list[dict], all_pages: list[dict]) -> list[dict]:
    out = []
    if base.startswith("https://"):
        out += _certificates(base, all_pages)
    out += _broken_internal(all_pages)
    out += _broken_external(good)
    out += _script_style_weight(good)

    def agg(key, name, pages, total, detail, fix, severity="medium", status="warn"):
        if pages:
            out.append(_f(key, name, status, f"{len(pages)} of {total} pages {detail}", fix, severity, urls=pages))

    measured = [p for p in good if "text_ratio" in p.get("metrics", {})]
    agg("text_ratio", "Text-to-HTML ratio", [p["url"] for p in measured if p["metrics"]["text_ratio"] < LOW_TEXT_RATIO], len(measured),
        f"have a text-to-HTML ratio below {LOW_TEXT_RATIO:.0f}% (the page is mostly code).", "Trim unused markup and inline code, or add useful text.", "low")
    agg("mixed", "Mixed content", [p["url"] for p in measured if p["metrics"].get("mixed_content")], len(measured),
        "load http:// resources on an https:// page.", "Serve every image, script and stylesheet over https.", "high", "fail")
    agg("alt", "Image alt text", [p["url"] for p in good if p["metrics"].get("images_missing_alt")], len(good),
        "have images without alt text.", "Add short, accurate alt text to meaningful images.", "low")
    agg("meta_missing", "Meta descriptions present", [p["url"] for p in good if not p.get("description")], len(good),
        "have no meta description.", "Write a page-specific summary of 70-160 characters.", "medium")
    agg("low_words", "Low word count", [p["url"] for p in good if p["metrics"]["word_count"] < 200], len(good),
        "have fewer than 200 words.", "Add specific, useful content where the page is meant to rank.", "low")
    return out
