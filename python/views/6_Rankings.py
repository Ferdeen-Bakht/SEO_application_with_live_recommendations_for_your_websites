import pandas as pd
import streamlit as st

from seo_lab import benchmark as bm
from seo_lab import site_state
from seo_lab.config import SERP_PROVIDER
from seo_lab.discovery import ensure_keywords, generate_keywords
from seo_lab.serp import check_rankings as serp_check_rankings, load_rankings, visibility_scores

NL = chr(10)
st.title("3. Rankings vs competitors")
SITE_URL, LABEL = site_state.get_site_url(), site_state.label()
st.caption(f"Reviewing **{SITE_URL}**")
st.write("Where does the site stand among its competitors, first on real search-engine results for 5 keywords, then on the on-page signals we can measure?")

# ----------------------------------------------------------------------------- search-engine rankings
st.header("Search-engine rankings for 5 keywords")
cfg = st.columns([1, 3])
cfg[0].metric("Provider", SERP_PROVIDER)
cfg[1].caption("Positions come from a real search engine you can check yourself: the **open search** links below run the same query in a browser. "
               "SearXNG = your own free local instance (started automatically); Mojeek = its official paid API. Results differ by engine and are not Google rankings.")
kw_key = f"kw_text_{LABEL}"
if not site_state.get_keywords():
    try:
        with st.spinner("Generating 5 keywords from your site with the local model..."):
            st.session_state[kw_key] = NL.join(ensure_keywords())
    except Exception as exc:
        st.error(f"Could not generate keywords automatically: {exc} Type 5 keywords below.")
if kw_key not in st.session_state:
    st.session_state[kw_key] = NL.join(site_state.get_keywords())
if st.button("Generate new keywords"):
    with st.spinner("Generating 5 keywords from your site with the local model..."):
        st.session_state[kw_key] = NL.join(generate_keywords())
    st.rerun()
kw_text = st.text_area("Keywords (generated for this site; edit freely, max 5, one per line)", key=kw_key, height=130)
competitors = site_state.get_competitors()
domains = [LABEL] + [site_state.site_label(u) for u in competitors]
if not competitors:
    st.info("No competitors yet: open **2. Competitor benchmark** first, so we know whose rankings to compare with yours.")
if st.button("Check search rankings", type="primary"):
    kws = [k.strip() for k in kw_text.splitlines() if k.strip()][:5]
    site_state.set_keywords(kws)
    try:
        with st.spinner(f"Searching {len(kws)} keywords on {SERP_PROVIDER} (starting the local search engine if needed)..."):
            serp_check_rankings(kws, domains)
    except Exception as exc:
        st.error(str(exc))
serp = load_rankings()
if serp:
    st.caption(f"Checked {serp['checked_at'][:16].replace('T', ' ')} UTC on {serp['provider']}; top {serp['depth']} results per keyword. 'not found' = not in those results.")
    table = []
    for row in serp["keywords"]:
        rec = {"Keyword": row["keyword"]}
        for d in serp["domains"]:
            pos = row["positions"].get(d)
            rec[d + (" (ours)" if d == serp["our_domain"] else "")] = str(pos) if pos else "not found"
        rec["Verify yourself"] = row["verify_url"]
        table.append(rec)
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch", column_config={"Verify yourself": st.column_config.LinkColumn("Verify yourself", display_text="open search")})
    found = sum(1 for r in serp["keywords"] if r["positions"].get(serp["our_domain"]))
    scores = visibility_scores(serp)
    board = pd.DataFrame([{"Site": d, "SEO score (SearXNG)": s, "Keywords ranked": f"{sum(1 for r in serp['keywords'] if r['positions'].get(d))} of {len(serp['keywords'])}",
                           "Best position": str(min([r["positions"][d] for r in serp["keywords"] if r["positions"].get(d)], default="-"))}
                          for d, s in scores.items()]).sort_values("SEO score (SearXNG)", ascending=False).reset_index(drop=True)
    board.insert(0, "Rank", range(1, len(board) + 1))
    ours_row = board[board["Site"] == serp["our_domain"]].iloc[0]
    st.subheader("SEO score from search rankings (SearXNG only)")
    m1, m2, m3 = st.columns(3)
    m1.metric("Our rank", f"#{int(ours_row['Rank'])} of {len(board)}", border=True)
    m2.metric("Our SEO score", f"{ours_row['SEO score (SearXNG)']:.0f}/100", border=True)
    m3.metric("Keywords where we appear", f"{found} of {len(serp['keywords'])}", border=True)
    st.dataframe(board.style.format({"SEO score (SearXNG)": "{:.1f}"}).apply(
        lambda r: ["font-weight: bold; background-color: rgba(46,160,67,.2)" if r["Site"] == serp["our_domain"] else "" for _ in r], axis=1),
        hide_index=True, width="stretch")
    st.bar_chart(board.set_index("Site")["SEO score (SearXNG)"])
    st.caption(f"How the score works: for each keyword a site earns (31 - position) / 30 points, so #1 = 1.0 and #30 = 0.03, and 0 if it is not in the top {serp['depth']}. "
               "The score is the average over the keywords x 100. It uses only the SearXNG results above, no page analysis, so you can recompute it yourself.")
    with st.expander("Top 10 results per keyword"):
        for row in serp["keywords"]:
            st.markdown(f"**{row['keyword']}**")
            st.dataframe(pd.DataFrame(row["top"]), hide_index=True, width="stretch")
else:
    st.info("Run **Check search rankings** to get each site's SEO score from the search results.")
st.divider()
st.header("On-page signals vs competitors")
st.caption("Measured on the crawled pages: content depth, headings, images, links and markup. The SEO score above comes from search rankings only.")

local_path, comp_path = bm.EXPORT_DIR / bm.local_csv(), bm.EXPORT_DIR / bm.comp_csv()
if not (local_path.exists() and comp_path.exists()):
    st.info("Run both crawls on **2. Competitor benchmark** first.")
    st.page_link("views/5_Competitor_Benchmark.py", label="Go to Competitor benchmark →")
    st.stop()


local_df, comp_df = bm.load_frame(bm.local_csv()), bm.load_frame(bm.comp_csv())
summary = bm.summarize(pd.concat([local_df, comp_df], ignore_index=True))
us = local_df["site"].iloc[0]
ranks = bm.rank_table(summary, us)

st.subheader("Strengths and gaps")
ahead, behind = ranks[ranks["Position"] == "ahead"], ranks[ranks["Position"] == "behind"]
a, b = st.columns(2)
with a:
    st.markdown("#### ✅ Where we are ahead")
    if ahead.empty:
        st.write("No metric is above the median yet.")
    for _, r in ahead.iterrows():
        st.success(f"**{r['Metric']}**: rank {r['Rank']} (ours {r['Ours']}, median {r['Median']})")
with b:
    st.markdown("#### ⚠️ Where we trail")
    if behind.empty:
        st.write("Nothing trails the median.")
    for _, r in behind.iterrows():
        st.warning(f"**{r['Metric']}**: rank {r['Rank']} (ours {r['Ours']}, best {r['Best']})")

st.subheader("Rank on every metric")
st.dataframe(ranks.drop(columns=["rank_n"]), hide_index=True, width="stretch")

st.caption("Only a few pages per site are crawled, so averages are indicative. Higher is not automatically better; keep content accurate and useful.")
