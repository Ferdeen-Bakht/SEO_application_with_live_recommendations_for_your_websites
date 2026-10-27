from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from seo_lab import benchmark as bm
from seo_lab import domain_stats as ds
from seo_lab import site_state
from seo_lab.live_site import load_crawl
from seo_lab.serp import load_rankings, visibility_scores

SITE_URL, LABEL = site_state.get_site_url(), site_state.label()
domains = [LABEL] + [d for d in dict.fromkeys(site_state.site_label(u) for u in site_state.get_competitors()) if d != LABEL]
OURS = " (ours)"


def tag(d):
    return d + OURS if d == LABEL else d


def fmt_ts(ts):
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if ts else "-"


STATUS_NAMES = {"-": "- (duplicate capture)"}

st.title("7. Domain stats")
st.caption(f"Reviewing **{SITE_URL}**. Statistics only: nothing on this page feeds the suggestions, and nothing is estimated where the source has no data.")
st.write("Every number says where it comes from: **Internet Archive** (public capture history), **FreeSerp** (domain rating), "
         "**SearXNG** (search positions from your Rankings run), **our crawler** (measured on pages).")

picked = st.multiselect("Sites to include", domains, default=domains, format_func=tag)
c1, c2 = st.columns([1, 3])
refresh = c1.checkbox("Ignore cache", value=False, help="Archive and FreeSerp results are cached for 7 days. A large site can take 30+ seconds to fetch.")
c2.caption("Pulling the archive for several sites can take a minute. Requests are read-only and cached.")
if st.button("Load domain stats", type="primary"):
    if not picked:
        st.error("Pick at least one site.")
    else:
        with st.spinner(f"Asking the Internet Archive and FreeSerp about {len(picked)} site(s)..."):
            st.session_state["dstats"] = {"sites": picked, "data": ds.load_all(picked, refresh)}
state = st.session_state.get("dstats")

# ------------------------------------------------------------------------------------------------ data from earlier runs
serp = load_rankings()
serp_scores = visibility_scores(serp) if serp else {}
local_df, comp_df = bm.load_frame(bm.local_csv()), bm.load_frame(bm.comp_csv())
summary = bm.summarize(pd.concat([local_df, comp_df], ignore_index=True)) if not (local_df.empty and comp_df.empty) else pd.DataFrame()

# ------------------------------------------------------------------------------------------------ overview
st.header("Overview")
rows = []
for d in (state["sites"] if state else picked):
    row = {"Site": tag(d)}
    if state:
        auth, wb = state["data"][d]["authority"], state["data"][d]["wayback"]
        row["Domain rating (FreeSerp)"] = auth.get("dr") if auth.get("found") else None
        row["First archived"] = fmt_ts(wb.get("first_capture"))
        row["Age in archive (years)"] = wb.get("age_years")
        row["Archived URLs"] = wb.get("unique_urls")
        row["Archived HTML pages"] = wb.get("html_urls")
        row["Homepage versions seen"] = wb.get("home_distinct_versions")
    if serp and d in serp_scores:
        row["Search visibility (SearXNG)"] = serp_scores[d]
        row["Keywords ranked"] = sum(1 for r in serp["keywords"] if r["positions"].get(d))
        best = [r["positions"][d] for r in serp["keywords"] if r["positions"].get(d)]
        row["Best position"] = min(best) if best else None
    if not summary.empty and d in summary.index:
        row["Pages crawled"] = int(summary.loc[d, "pages"])
        row["Avg words"] = summary.loc[d, "word_count"]
        row["Avg H2"] = summary.loc[d, "h2_count"]
        row["Avg internal links"] = summary.loc[d, "internal_links"]
        row["Structured data %"] = summary.loc[d, "has_jsonld"]
    rows.append(row)
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
if not state:
    st.info("Click **Load domain stats** to add domain rating and Internet Archive numbers to this table. "
            "Search-visibility and on-page columns come from your earlier Rankings and Competitor benchmark runs.")
else:
    errs = [f"{d}: {v['wayback']['error']}" for d, v in state["data"].items() if v["wayback"].get("error")]
    errs += [f"{d}: {v['authority']['error']}" for d, v in state["data"].items() if v["authority"].get("error")]
    for e in errs:
        st.warning(e)
    ov = pd.DataFrame(rows).set_index("Site")
    left, right = st.columns(2)
    if "Domain rating (FreeSerp)" in ov and ov["Domain rating (FreeSerp)"].notna().any():
        left.subheader("Domain rating")
        left.bar_chart(ov["Domain rating (FreeSerp)"].dropna())
        left.caption("FreeSerp's 0-100 authority score. Sites missing from its index have no bar; that does not mean zero authority.")
    if "Archived URLs" in ov and ov["Archived URLs"].notna().any():
        right.subheader("URLs the Internet Archive has seen")
        right.bar_chart(ov["Archived URLs"].dropna())
        right.caption("Unique URLs (pages, images, scripts). A rough size and age signal, not a page count.")

# ------------------------------------------------------------------------------------------------ authority
if state:
    st.header("Authority and profile (FreeSerp)")
    cols = st.columns(min(3, len(state["sites"])))
    for i, d in enumerate(state["sites"]):
        a = state["data"][d]["authority"]
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.markdown(f"**{tag(d)}**")
                if a.get("found"):
                    st.metric("Domain rating", a.get("dr") if a.get("dr") is not None else "n/a")
                    st.caption(f"Listed live since {a.get('went_live') or 'unknown'} · category {a.get('category') or ', '.join(a.get('ai_categories') or []) or 'unknown'}")
                    if a.get("summary"):
                        st.write(a["summary"][:300])
                else:
                    st.write("Not in FreeSerp's index.")
    st.caption("FreeSerp exposes a domain rating only. It does not provide backlink counts, referring domains or organic traffic; those need a paid source.")

# ------------------------------------------------------------------------------------------------ archive history
if state:
    st.header("Archive history (Internet Archive)")
    tabs = st.tabs([tag(d) for d in state["sites"]])
    for tab, d in zip(tabs, state["sites"]):
        wb = state["data"][d]["wayback"]
        with tab:
            if wb.get("error"):
                st.error(wb["error"])
                continue
            if not wb.get("months_captured") and not wb.get("unique_urls"):
                st.info("The Internet Archive has no captures for this domain.")
                continue
            m = st.columns(5)
            m[0].metric("First capture", fmt_ts(wb.get("first_capture")), border=True)
            m[1].metric("Latest capture", fmt_ts(wb.get("last_capture")), border=True)
            m[2].metric("Months with a homepage capture", wb.get("months_captured", 0), border=True)
            m[3].metric("Unique URLs", f"{wb.get('unique_urls', 0):,}" + ("+" if wb.get("truncated") else ""), border=True)
            m[4].metric("Homepage versions", wb.get("home_distinct_versions", 0), border=True)
            if wb.get("truncated"):
                st.caption(f"Only the first {ds.URL_LIMIT:,} URLs are listed, so URL statistics below are for that sample.")
            a, b = st.columns(2)
            if wb.get("urls_by_first_year"):
                a.subheader("New URLs by year first archived")
                a.bar_chart(pd.Series(wb["urls_by_first_year"]))
            if wb.get("home_by_year"):
                frame = pd.DataFrame({"Monthly captures": wb["home_by_year"], "Content changes": wb.get("home_changes_by_year", {})}).fillna(0)
                b.subheader("Homepage captures and changes by year")
                b.bar_chart(frame)
                b.caption("A change = the homepage's content hash differs from the previous monthly capture.")
            c, e = st.columns(2)
            if wb.get("status_mix"):
                c.subheader("HTTP status of archived URLs")
                c.bar_chart(pd.Series({STATUS_NAMES.get(k, k): v for k, v in wb["status_mix"].items()}))
                bad = sum(v for k, v in wb["status_mix"].items() if k.startswith(("4", "5")))
                c.caption(f"{bad:,} archived URLs answered with an error status when captured.")
            if wb.get("mime_mix"):
                e.subheader("File types")
                e.bar_chart(pd.Series(wb["mime_mix"]))
            f, g = st.columns(2)
            if wb.get("top_sections"):
                f.subheader("Where the HTML pages live")
                f.bar_chart(pd.Series(wb["top_sections"]))
            if wb.get("hosts"):
                g.subheader("Hostnames seen")
                g.dataframe(pd.DataFrame({"Host": list(wb["hosts"]), "HTML pages": list(wb["hosts"].values())}), hide_index=True, width="stretch")
            if wb.get("home_status"):
                st.write("**Homepage status codes when captured:** " + ", ".join(f"{k}: {v}" for k, v in wb["home_status"].items()))
            if wb.get("with_query"):
                st.write(f"**URLs with query strings:** {wb['with_query']:,} of {wb['unique_urls']:,}")
            if wb.get("oldest_urls"):
                with st.expander("Oldest archived pages"):
                    st.dataframe(pd.DataFrame(wb["oldest_urls"]).rename(columns={"first_seen": "First seen", "url": "URL"}), hide_index=True, width="stretch")

    st.subheader("Do the archived pages still exist?")
    st.caption("Checks a sample of archived pages on the live site (read-only, one request each). Pages that are gone or redirect elsewhere had a history that is now lost.")
    gone_site = st.selectbox("Site", state["sites"], format_func=tag, key="gone_site")
    gone_n = st.slider("Pages to check", 10, 150, 40, step=10)
    if st.button("Check archived pages on the live site"):
        raw = ds.wayback_raw(gone_site)
        urls = ds.archived_html_urls(raw, gone_n)
        if not urls:
            st.info("No archived HTML pages to check for this site.")
        else:
            with st.spinner(f"Requesting {len(urls)} pages..."):
                checked = pd.DataFrame(ds.live_status(urls))
            ok = int((checked["status"] == 200).sum())
            redirected = int(checked["status"].between(300, 399).sum())
            broken = len(checked) - ok - redirected
            k = st.columns(4)
            k[0].metric("Checked", len(checked), border=True)
            k[1].metric("Still 200", ok, border=True)
            k[2].metric("Redirect", redirected, border=True)
            k[3].metric("Gone / error", broken, border=True)
            st.dataframe(checked.sort_values("status", ascending=False).rename(columns={"url": "URL", "status": "Status now", "redirects_to": "Redirects to / error"}),
                         hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------------ search visibility
st.header("Search visibility (SearXNG)")
if not serp:
    st.info("No ranking check yet. Run **3. Rankings vs competitors** first.")
else:
    st.caption(f"Checked {serp['checked_at'][:16].replace('T', ' ')} UTC on {serp['provider']}; top {serp['depth']} results per keyword.")
    grid = pd.DataFrame([{"Keyword": r["keyword"], **{tag(d): str(r["positions"].get(d) or "not found") for d in serp["domains"]}} for r in serp["keywords"]])
    st.dataframe(grid, hide_index=True, width="stretch")
    v1, v2 = st.columns(2)
    v1.subheader("Visibility score")
    v1.bar_chart(pd.Series({tag(d): s for d, s in serp_scores.items()}))
    results_hosts = pd.Series([urlparse(t["url"]).netloc.removeprefix("www.") for r in serp["keywords"] for t in r["top"]]).value_counts().head(12)
    v2.subheader("Domains most often in the top 10")
    v2.bar_chart(results_hosts)
    v2.caption("Who actually occupies the first page for your keywords, whether or not they are tracked competitors.")

# ------------------------------------------------------------------------------------------------ on-page
st.header("On-page measurements (our crawler)")
if summary.empty:
    st.info("No crawl data yet. Run both crawls on **2. Competitor benchmark**.")
else:
    st.dataframe(summary.rename(index=tag).rename(columns={"pages": "Pages", "score": "On-page score", "title_len": "Title length", "desc_len": "Description length",
                                                           "h2_count": "H2 count", "word_count": "Words", "image_count": "Images", "alt_coverage": "Alt text %",
                                                           "internal_links": "Internal links", "external_links": "External links", "url_depth": "URL depth",
                                                           "has_jsonld": "Structured data %", "has_canonical": "Canonical %"}), width="stretch")
    metric = st.selectbox("Chart a metric", ["word_count", "h2_count", "image_count", "internal_links", "external_links", "alt_coverage", "has_jsonld", "title_len", "desc_len"],
                          format_func=lambda k: k.replace("_", " "))
    st.bar_chart(summary.rename(index=tag)[metric])

crawl = [p for p in load_crawl() if p.get("metrics") and site_state.site_label(p["url"]) == LABEL]
if crawl:
    st.subheader(f"Our crawled pages ({len(crawl)})")
    page_df = pd.DataFrame([{"URL": p["url"], "Status": p["status_code"], "Words": p["metrics"]["word_count"], "Title length": p["metrics"]["title_len"],
                             "Description length": p["metrics"]["desc_len"], "H2": p["metrics"]["h2_count"], "Images": p["metrics"]["image_count"],
                             "Alt text %": p["metrics"]["alt_coverage"], "Internal links": p["metrics"]["internal_links"],
                             "External links": p["metrics"]["external_links"], "Schema": " | ".join(dict.fromkeys(p["metrics"].get("jsonld_types", []))),
                             "Findings": len(p.get("findings", []))} for p in crawl])
    st.dataframe(page_df, hide_index=True, width="stretch")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total words", f"{int(page_df['Words'].sum()):,}", border=True)
    s2.metric("Images missing alt text", int(sum(p['metrics'].get('images_missing_alt', 0) for p in crawl)), border=True)
    s3.metric("Pages with structured data", f"{sum(1 for p in crawl if p['metrics'].get('has_jsonld'))} of {len(crawl)}", border=True)
    s4.metric("Pages with findings", f"{int((page_df['Findings'] > 0).sum())} of {len(crawl)}", border=True)

st.divider()
st.caption("Not available from free public sources: backlink counts, referring domains, organic traffic and search volume. "
           "Google Search Console and Analytics (page 7 · Connections) give real traffic for your own site once connected.")
