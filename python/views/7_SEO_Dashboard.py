import pandas as pd
import streamlit as st

from seo_lab import benchmark as bm
from seo_lab import integrations as ig

REAL, MEASURED, DERIVED, MISSING = ":green[REAL · Google]", ":blue[MEASURED · our crawler]", ":orange[DERIVED · rules on real data]", ":gray[UNAVAILABLE]"

st.title("7. SEO dashboard")
st.write("Every section is labelled by where its numbers come from, so real Google data is never mixed up with estimates.")
st.markdown(f"Labels: {REAL} reported by Google · {MEASURED} measured by this app on a page · {DERIVED} simple rules applied to real data (not forecasts) · {MISSING} not available")

try:
    connected = ig.google_credentials() is not None
except Exception:
    connected = False
site = ig.get_setting("GSC_SITE_URL")

# --------------------------------------------------------------------------- Google Search Console
st.header("Google Search performance")
if not connected or not site:
    st.info("Google Search Console is not connected, so there are no clicks, impressions, CTR or positions to show. Nothing is estimated in its place.")
    st.page_link("pages/6_Connections.py", label="Connect Google →")
else:
    days = st.radio("Period", [7, 28, 90], index=1, horizontal=True, format_func=lambda d: f"Last {d} days")
    start, end = ig.default_range(days)
    st.caption(f"{REAL} Property: `{site}` · {start} to {end} (Search Console data lags about 2 days).")
    key = (site, start, end)
    if st.button("Load / refresh Google data", type="primary"):
        try:
            with st.spinner("Asking Search Console..."):
                st.session_state["gsc"] = {
                    "totals": ig.gsc_totals(site, start, end),
                    "daily": ig.gsc_query(site, start, end, ["date"], 1000),
                    "queries": ig.gsc_query(site, start, end, ["query"], 250),
                    "pages": ig.gsc_query(site, start, end, ["page"], 100),
                }
                st.session_state["gsc_key"] = key
        except Exception as exc:
            st.error(f"Search Console request failed: {exc}")
    data = st.session_state.get("gsc") if st.session_state.get("gsc_key") == key else None
    if data:
        t = data["totals"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Clicks", f"{t['clicks']:,}", border=True)
        m2.metric("Impressions", f"{t['impressions']:,}", border=True)
        m3.metric("CTR", f"{t['ctr']}%", border=True)
        m4.metric("Average position", t["position"], border=True)
        if t["impressions"] == 0:
            st.warning("Google reports no impressions in this period. The site may be new, not yet indexed, or not verified under this property.")
        else:
            daily = pd.DataFrame(data["daily"]).set_index("date")
            st.line_chart(daily[["clicks", "impressions"]])
            left, right = st.columns(2)
            with left:
                st.subheader("Top queries")
                st.dataframe(pd.DataFrame(data["queries"]).head(25), hide_index=True, width="stretch")
            with right:
                st.subheader("Top pages")
                st.dataframe(pd.DataFrame(data["pages"]).head(25), hide_index=True, width="stretch")
            st.subheader("Keyword opportunities")
            st.caption(f"{DERIVED} Queries Google already shows your site for that look improvable. This is not a prediction of ranking or traffic.")
            opps = ig.keyword_opportunities(data["queries"])
            if opps:
                st.dataframe(pd.DataFrame(opps), hide_index=True, width="stretch")
            else:
                st.write("No query meets the opportunity rules yet (needs at least 20 impressions and a position of 8-20, or a low CTR near the top).")

    st.subheader("Indexing status")
    st.caption(f"{REAL} Google's own URL Inspection API. It checks one URL at a time and has a daily quota per property.")
    urls = st.text_area("URLs to inspect (one per line, full URLs on the monitored property)", placeholder=f"{site if site.startswith('http') else 'https://example.com/'}")
    if st.button("Inspect indexing"):
        rows = []
        for url in [u.strip() for u in urls.splitlines() if u.strip()][:10]:
            try:
                rows.append(ig.gsc_inspect(site, url))
            except Exception as exc:
                rows.append({"url": url, "verdict": f"error: {exc}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch") if rows else st.info("Enter at least one URL.")

# --------------------------------------------------------------------------- Analytics
st.header("Website traffic (Google Analytics)")
ga_id = ig.get_setting("GA4_PROPERTY_ID")
if not connected or not ga_id:
    st.info("Google Analytics is not connected (needs Google connected plus a GA4 property ID on the Connections page).")
else:
    start, end = ig.default_range(28)
    try:
        ga = ig.ga4_summary(ga_id, start, end)
        a1, a2, a3 = st.columns(3)
        a1.metric("Sessions", f"{ga['sessions']:,}", border=True)
        a2.metric("Users", f"{ga['users']:,}", border=True)
        a3.metric("Page views", f"{ga['views']:,}", border=True)
        st.caption(f"{REAL} Last 28 days from Google Analytics property {ga_id}.")
    except Exception as exc:
        st.error(f"Analytics request failed: {exc}")

# --------------------------------------------------------------------------- Local audit
st.header("Site audit score")
st.caption(f"{MEASURED} Our own 0-100 learning score from the crawler (title, description, headings, depth, images, technical basics). It is not a Google score and says nothing about rankings.")
history = bm.load_history()
if history:
    last = history[-1]
    first = history[0]
    s1, s2, s3 = st.columns(3)
    s1.metric("Our latest average score", f"{last['local_score']:.0f}/100", delta=f"{last['local_score'] - first['local_score']:+.1f} since first snapshot" if len(history) > 1 else None, border=True)
    s2.metric("Competitor average", "n/a" if last.get("competitor_score") is None else f"{last['competitor_score']:.0f}/100", border=True)
    s3.metric("Snapshots stored", len(history), border=True)
else:
    st.info("No audit snapshots yet. Run **5. Competitor benchmark** to create one.")

# --------------------------------------------------------------------------- Data quality table
st.header("What is real, derived or unavailable")
st.dataframe(pd.DataFrame([
    {"Metric": "Clicks, impressions, CTR, average position, queries, pages", "Source": "Google Search Console API", "Status": "Real when connected and the site has data"},
    {"Metric": "Indexing status of a URL", "Source": "Google URL Inspection API", "Status": "Real, per URL, quota-limited"},
    {"Metric": "Sessions, users, page views", "Source": "Google Analytics Data API", "Status": "Real when connected"},
    {"Metric": "Keyword opportunities", "Source": "Rules applied to real Search Console queries", "Status": "Derived (not a forecast)"},
    {"Metric": "SEO audit score, technical checks, competitor page comparison", "Source": "This app's crawler", "Status": "Measured on pages, not a Google score"},
    {"Metric": "Search volume for keywords", "Source": "None (Google exposes it only through Google Ads)", "Status": "Unavailable"},
    {"Metric": "Ranking position for keywords you do not yet appear for", "Source": "None", "Status": "Unavailable; never estimated"},
    {"Metric": "Predicted traffic or ranking gains", "Source": "None", "Status": "Not provided; no guarantees"},
]), hide_index=True, width="stretch")
