import pandas as pd
import streamlit as st

from seo_lab import benchmark as bm
from seo_lab import site_state
from seo_lab.crawler import crawl_site
from seo_lab.discovery import LAST_SKIPPED, discover_competitors, ensure_keywords
from seo_lab.live_site import CRAWL_FILE, load_crawl, save_crawl

SITE_URL = site_state.get_site_url()
LABEL = site_state.label()
LOCAL_CSV, COMP_CSV = bm.local_csv(), bm.comp_csv()
NL = chr(10)


def shown(df):
    """Spreadsheet view without the on-page SEO score (the score now lives on the Rankings page, from search results)."""
    return df.drop(columns=["score"], errors="ignore")

st.title("2. Competitor benchmark")
st.caption(f"Reviewing **{SITE_URL}** (change it on the Home page or in 1. Crawl & audit).")
st.write(
    "Compare the live site with its competitors, side by side. Competitors are found automatically from search results for keywords "
    "generated from your site, and you can edit the list. The results feed the **Suggestions** agent, which uses the gaps "
    "(page depth, headings, keywords, structured data) to recommend changes."
)

# ------------------------------------------------------------------ Step 1
st.header("Step 1 · Our site's data")
site_pages = [p for p in load_crawl() if p.get("metrics") and site_state.site_label(p["url"]) == LABEL]
csv_path = bm.EXPORT_DIR / LOCAL_CSV
if site_pages and (not csv_path.exists() or csv_path.stat().st_mtime < CRAWL_FILE.stat().st_mtime):
    frame = bm.pages_to_frame(LABEL, site_pages)  # no new requests: the numbers were already measured by Crawl & audit
    if not frame.empty:
        bm.save_csv(frame, LOCAL_CSV)
if site_pages:
    st.success(f"Using the {len(site_pages)} pages you already crawled in **1. Crawl & audit**. No new crawl needed.")
else:
    st.info("No crawl of this site yet. Run **1. Crawl & audit**, or crawl here.")
crawl_cols = st.columns(2)
unl_ours = crawl_cols[0].checkbox("Unlimited pages for our site", value=True, key="unl_ours")
minutes = crawl_cols[1].number_input("Stop after (minutes; 0 = no limit)", min_value=0, max_value=480, value=15, step=5, key="minutes_ours")
if st.button("Crawl our site again"):
    try:
        with st.spinner("Crawling our site..."):
            status = st.empty()
            pages = crawl_site(f"{SITE_URL}/", max_pages=None if unl_ours else 15, delay_seconds=0.2, max_seconds=minutes * 60 or None,
                               progress=lambda n, u: status.info(f"Crawled {n} pages... latest: {u}"))
            status.empty()
            save_crawl(pages)  # keep Crawl & audit and this page on the same data
            local = bm.pages_to_frame(LABEL, pages)
        if local.empty:
            st.error("No HTML pages were crawled. Is the site reachable?")
        else:
            path = bm.save_csv(local, LOCAL_CSV)
            st.success(f"Exported {len(local)} pages to {path}")
    except Exception as exc:
        st.error(str(exc))
local_df = bm.load_frame(LOCAL_CSV)
if not local_df.empty:
    st.dataframe(bm.friendly(shown(local_df)), hide_index=True, width="stretch")
    st.download_button("Download our CSV", bm.to_csv_bytes(shown(local_df)), LOCAL_CSV, "text/csv")

# ------------------------------------------------------------------ Step 2
st.header("Step 2 · Crawl competitor sites")
st.write("Competitors are suggested automatically: the local model generates 5 search keywords for your site, those are searched, "
         "and sites that keep appearing (minus directories, media and social networks) are listed. Edit the list freely, one URL per line. "
         "The crawler respects each site's robots.txt, stays on that site, waits between requests and is capped to a few pages per site.")
comp_key, fail_key, info_key = f"comp_urls_{LABEL}", f"disc_failed_{LABEL}", f"disc_info_{LABEL}"


def run_discovery(fresh_keywords: bool = False):
    try:
        with st.spinner("Generating keywords, searching, and picking competitors (this can take a minute; the local search engine starts automatically)..."):
            if fresh_keywords:
                site_state.set_keywords([])
            kws = ensure_keywords()
            found = discover_competitors(kws)
        st.session_state[comp_key] = NL.join(c["url"] for c in found)
        st.session_state[info_key] = {"keywords": kws, "found": found, "skipped": list(LAST_SKIPPED)}
        st.session_state.pop(fail_key, None)
    except Exception as exc:
        st.session_state[fail_key] = str(exc)


if not site_state.get_competitors() and fail_key not in st.session_state:
    run_discovery()
if comp_key not in st.session_state:
    st.session_state[comp_key] = NL.join(site_state.get_competitors())
if st.session_state.get(fail_key):
    st.warning(f"Automatic competitor discovery did not work: {st.session_state[fail_key]} You can paste competitor URLs below instead.")
if st.button("Find competitors again (new keywords)"):
    run_discovery(fresh_keywords=True)
    st.rerun()
info = st.session_state.get(info_key)
if info:
    with st.expander("How these competitors were found"):
        st.write("**Keywords searched:** " + ", ".join(info["keywords"]))
        table = pd.DataFrame(info["found"]).rename(columns={"domain": "Domain", "keywords": "Keywords it ranks for", "title": "Example title"})
        st.dataframe(table[["Domain", "Keywords it ranks for", "Example title"]], hide_index=True, width="stretch")
        if info.get("skipped"):
            st.caption("Skipped because they refuse automated crawlers: " + ", ".join(f"{s['domain']} ({s['reason']})" for s in info["skipped"]))
urls_text = st.text_area("Competitor URLs (one per line)", key=comp_key, height=130)
comp_cols = st.columns([1, 2, 1])
unl_comp = comp_cols[0].checkbox("Unlimited pages", value=True, key="unl_comp")
max_pages = comp_cols[1].slider("Pages per competitor (used when not unlimited)", 1, 500, 5, disabled=unl_comp)
comp_minutes = comp_cols[2].number_input("Stop after (min; 0 = none)", min_value=0, max_value=480, value=15, step=5, key="minutes_comp",
                                         help="Per site. Competitors are crawled politely, up to 4 at a time, with a pause between requests.")
if unl_comp:
    st.caption("Unlimited follows every link on each competitor site, stopping at the time limit or a 2,000-page safety ceiling per site. "
               "Large sites can take a long time.")
if st.button("Crawl competitors and export CSV", type="primary"):
    urls = [u.strip() for u in urls_text.splitlines() if u.strip()][:8]
    if not urls:
        st.error("Enter at least one URL.")
    else:
        site_state.set_competitors(urls)
        progress_box = st.empty()
        with st.spinner(f"Crawling {len(urls)} site(s)..."):
            results = bm.crawl_many(urls, None if unl_comp else max_pages, comp_minutes * 60 or None,
                                    lambda counts: progress_box.info("Pages crawled so far: " + ", ".join(f"{s}: {n}" for s, n in counts.items())))
        progress_box.empty()
        frames = []
        for label, r in results.items():
            frame = bm.pages_to_frame(label, r["pages"])
            if r["error"]:
                st.warning(f"{label}: {r['error']}")
            elif frame.empty:
                st.warning(f"{label}: {bm.explain_no_pages(r['pages'])}")
            else:
                stopped = results[label].get("stopped_by")
                st.write(f"✅ {label}: {len(frame)} page(s)" + (" (stopped at the time limit)" if stopped == "time" else " (stopped at the page limit)" if stopped == "limit" else ""))
                frames.append(frame)
        if frames:
            comp = pd.concat(frames, ignore_index=True)
            path = bm.save_csv(comp, COMP_CSV)
            st.success(f"Exported {len(comp)} competitor pages to {path}")
            if not local_df.empty:
                bench = bm.build_benchmark(local_df, comp)
                bm.save_benchmark(bench)
                bm.record_snapshot(local_df, bench["competitor_average"]["score"])
                st.success("Benchmark saved. The Suggestions page will use it automatically.")
comp_df = bm.load_frame(COMP_CSV)
if not comp_df.empty:
    st.dataframe(bm.friendly(shown(comp_df)), hide_index=True, width="stretch")
    st.download_button("Download competitor CSV", bm.to_csv_bytes(shown(comp_df)), COMP_CSV, "text/csv")

# ------------------------------------------------------------------ Step 3
st.header("Step 3 · Compare side by side")
if local_df.empty or comp_df.empty:
    st.info("Complete steps 1 and 2 to see the comparison.")
    st.stop()

bench = bm.build_benchmark(local_df, comp_df)
summary = bm.summarize(pd.concat([local_df, comp_df], ignore_index=True))
local_label = bench["local_site"]

st.subheader("Where do we stand?")
c1, c2, c3 = st.columns(3)
c1.metric("Words per page: ours vs competitors", f"{bench['local_summary']['word_count']:.0f} vs {bench['competitor_average']['word_count']:.0f}", border=True)
c2.metric("H2 headings per page", f"{bench['local_summary']['h2_count']:.1f} vs {bench['competitor_average']['h2_count']:.1f}", border=True)
c3.metric("Internal links per page", f"{bench['local_summary']['internal_links']:.0f} vs {bench['competitor_average']['internal_links']:.0f}", border=True)

st.subheader("Site averages")
names = {"pages": "Pages", "word_count": "Words", "title_len": "Title length", "desc_len": "Description length",
         "h2_count": "H2 count", "image_count": "Images", "alt_coverage": "Alt text %", "internal_links": "Internal links",
         "external_links": "External links", "has_jsonld": "Structured data %", "has_canonical": "Canonical %", "url_depth": "URL depth"}
table = summary[list(names)].rename(columns=names)
ordered = pd.concat([table.loc[[local_label]].rename(index=lambda s: f"{s} (ours)"), table.drop(index=local_label)])
st.dataframe(ordered, width="stretch")
st.download_button("Download comparison CSV", ordered.to_csv().encode("utf-8-sig"), "comparison.csv", "text/csv")
st.bar_chart(table[["Words"]])

st.subheader("What the agent will recommend")
st.dataframe(pd.DataFrame(bench["insights"]).rename(columns={"area": "Area", "local": "Ours", "competitors": "Competitors", "recommendation": "Recommendation", "priority": "Priority"}),
             hide_index=True, width="stretch")
if bench["keyword_gaps"]:
    st.write("**Keyword gaps** (used in titles/headings by 2+ competitors, absent from ours; number = competitors): " + ", ".join(f"{g['term']} ({g['competitor_sites']})" for g in bench["keyword_gaps"]))
else:
    st.caption("No keyword gaps found: no topic word is shared by two or more competitors that our site lacks.")
st.page_link("views/6_Rankings.py", label="3. See our SEO score and rankings vs competitors →")

st.subheader("Compare two pages")
a_col, b_col = st.columns(2)
ours_pick = a_col.selectbox("Our page", local_df["url"].tolist())
theirs_pick = b_col.selectbox("Competitor page", comp_df["url"].tolist())
ours, theirs = local_df[local_df["url"] == ours_pick].iloc[0], comp_df[comp_df["url"] == theirs_pick].iloc[0]
rows = []
for key, label in [("title", "Title"), ("description", "Meta description"), ("h1", "H1"), ("h2_list", "H2 headings"), ("word_count", "Words"),
                   ("title_len", "Title length"), ("desc_len", "Description length"), ("h2_count", "H2 count"), ("image_count", "Images"),
                   ("alt_coverage", "Alt text %"), ("internal_links", "Internal links"), ("has_jsonld", "Structured data"), ("url_depth", "URL depth")]:
    rows.append({"": label, "Ours": str(ours[key]), "Competitor": str(theirs[key])})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("Competitor data is collected from public pages for comparison only. A higher number is not automatically better; check that changes stay accurate and useful.")
