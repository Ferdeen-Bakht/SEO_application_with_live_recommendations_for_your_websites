import json

import pandas as pd
import streamlit as st

from seo_lab import live_site
from seo_lab import site_state
from seo_lab.crawler import crawl_site
from seo_lab.site_checks import run_site_checks

ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

st.title("1. Crawl & audit")
st.write("A crawler visits linked pages and writes down what it finds. It stays on one host, respects robots.txt, and only reads. "
         "JavaScript sites are opened in a real browser so the audit sees the finished page.")
with st.form("crawl_form"):
    start_url = st.text_input("Starting URL", value=f"{site_state.get_site_url()}/")
    mode = st.radio("How many pages?", ["Unlimited (every page we can reach)", "Limited"], horizontal=True,
                    help="Unlimited follows every link on the site. It stops at the time limit below or at a safety ceiling of "
                         "2,000 pages (CRAWL_HARD_LIMIT in .env), so very large sites cannot run forever.")
    max_pages = st.slider("Maximum pages (used only when Limited)", 1, 500, 10)
    minutes = st.number_input("Stop after (minutes; 0 = no time limit)", min_value=0, max_value=480, value=15, step=5,
                              help="When the time is up the crawl stops cleanly and keeps everything found so far.")
    render = st.radio("JavaScript rendering", ["auto", "always", "never"], horizontal=True,
                      help="auto = use a browser only when the raw HTML is an empty app shell")
    submitted = st.form_submit_button("Start crawl", type="primary")

if submitted:
    try:
        site_state.set_site(start_url)  # every other page now reviews this site
        with st.spinner("Fetching pages, rendering JavaScript and running site-wide checks..."):
            status = st.empty()
            pages = crawl_site(start_url, max_pages=None if mode.startswith("Unlimited") else max_pages, render=render,
                               max_seconds=minutes * 60 or None, progress=lambda n, u: status.info(f"Crawled {n} pages... latest: {u}"))
            status.empty()
            live_site.save_crawl(pages)
            st.session_state["site_checks"] = run_site_checks(start_url, pages)
        st.session_state["last_crawl_pages"] = pages
        st.session_state["crawl_for"] = site_state.label()
        st.success(f"Crawl finished. Visited {len(pages)} URL(s). Saved to data/last_crawl.json.")
        if pages.stopped_by == "time":
            st.warning(f"Stopped at the {minutes}-minute time limit; the site has more pages. Raise the limit to crawl further.")
        elif pages.stopped_by == "limit":
            st.warning("Stopped at the page limit; the site has more pages. Raise the limit (or choose Unlimited) to crawl further.")
    except Exception as exc:
        st.error(str(exc))

host = site_state.label()
if st.session_state.get("crawl_for") != host:  # session data belongs to the previously reviewed site
    st.session_state.pop("last_crawl_pages", None)
    st.session_state.pop("site_checks", None)
pages = [p for p in (st.session_state.get("last_crawl_pages") or live_site.load_crawl()) if site_state.site_label(p["url"]) == host]
if not pages:
    st.info("No crawl yet. Click **Start crawl**.")
    st.stop()

checks = st.session_state.get("site_checks")
if checks:
    st.subheader("Site-wide findings")
    order = {"fail": 0, "warn": 1, "pass": 2}
    for c in sorted(checks, key=lambda c: order[c["status"]]):
        with st.container(border=True):
            st.markdown(f"{ICON[c['status']]} **{c['name']}** · {c['detail']}")
            if c["fix"]:
                st.caption(f"Suggested fix: {c['fix']}")
            urls = c.get("urls", [])
            if urls:
                label = "Example URL" if c["key"] in {"soft404", "robots", "sitemap", "https", "www"} else "Affected URLs"
                st.markdown(f"**{label}{'s' if len(urls) > 1 and label == 'Example URL' else ''}:**")
                for u in urls[:12]:
                    st.markdown(f"- [{u}]({u})")
                if len(urls) > 12:
                    st.caption(f"...and {len(urls) - 12} more.")
else:
    st.caption("Run a crawl to see site-wide findings (robots.txt, sitemap, duplicate titles...).")

flat = []
for p in pages:
    findings = p.get("findings", [])
    m = p.get("metrics", {})
    flat.append({"URL": p.get("url", ""), "HTTP": p.get("status_code", 0), "Rendered by browser": p.get("rendered", False),
                 "Title": p.get("title", ""), "Title length": len(p.get("title", "")), "Meta description": p.get("description", ""),
                 "H1": p.get("h1", ""), "Words": m.get("word_count", 0), "Finding count": len(findings),
                 "Main finding": findings[0]["issue"] if findings else "No basic checks flagged an issue"})
st.subheader("Page inventory")
st.dataframe(pd.DataFrame(flat), width="stretch", hide_index=True)
st.download_button("Download crawl results (JSON)", json.dumps(pages, indent=2, ensure_ascii=False), "crawl_results.json", "application/json")
st.subheader("Inspect one page")
selected_url = st.selectbox("Choose a URL", [p["url"] for p in pages])
page = next(p for p in pages if p["url"] == selected_url)
a, b = st.columns(2)
with a:
    st.write("**Title**", page.get("title") or "(missing)")
    st.write("**Meta description**", page.get("description") or "(missing)")
    st.write("**H1**", page.get("h1") or "(missing)")
    st.write("**Canonical**", page.get("canonical") or "(not declared)")
    st.write("**Robots directive**", page.get("robots") or "(no meta robots directive found)")
    if page.get("render_error"):
        st.warning(page["render_error"])
with b:
    findings = page.get("findings", [])
    if not findings:
        st.success("No issue was flagged by this small set of checks. This does not mean the page is fully SEO-optimized.")
    for f in findings:
        with st.expander(f"{f.get('severity', 'info').upper()}: {f['issue']}"):
            st.write("**Why it matters:**", f.get("why", ""))
            st.write("**Possible next step:**", f.get("suggestion", ""))
