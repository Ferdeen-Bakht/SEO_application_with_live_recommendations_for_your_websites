import streamlit as st

from seo_lab.repository import list_suggestions, set_status

st.title("5. Saved suggestions")
st.write("Suggestions you accepted on the previous page. This is a hand-off list: copy the wording into your own codebase or CMS. Nothing here touches the live site.")
flt = st.selectbox("Show", ["open", "done", "dismissed", "all"])
items = list_suggestions(None if flt == "all" else flt)
if not items:
    st.info("Nothing here yet. Create suggestions on page 4.")
    st.stop()


def as_markdown(s: dict) -> str:
    o, n = s["original"], s["suggested"]
    return (f"# Suggestion #{s['id']} for {s['site_url']}{s['page_path']}\n\nTarget keyword: {s['target_query']}\n\n"
            f"## Title\n- Current: {o['title']}\n- Suggested: {n['title']}\n\n"
            f"## Meta description\n- Current: {o['metaDescription']}\n- Suggested: {n['metaDescription']}\n\n"
            f"## H1\n- Current: {o['h1']}\n- Suggested: {n['h1']}\n\n"
            f"## Intro paragraphs (suggested)\n" + "\n\n".join(n["paragraphs"]) + f"\n\n## Notes\n{s['rationale']}\n")


all_md = "\n\n---\n\n".join(as_markdown(s) for s in items)
st.download_button("Download all shown as Markdown", all_md, "seo_suggestions.md", "text/markdown")
for s in items:
    with st.expander(f"#{s['id']} · {s['status'].upper()} · {s['page_path']} · {s['target_query']}"):
        left, right = st.columns(2)
        left.markdown("**Current**")
        left.write(f"**Title:** {s['original']['title']}")
        left.write(f"**Description:** {s['original']['metaDescription']}")
        left.write(f"**H1:** {s['original']['h1']}")
        right.markdown("**Suggested**")
        right.write(f"**Title:** {s['suggested']['title']}")
        right.write(f"**Description:** {s['suggested']['metaDescription']}")
        right.write(f"**H1:** {s['suggested']['h1']}")
        for p in s["suggested"]["paragraphs"]:
            st.write(p)
        st.caption(s["rationale"])
        c1, c2, c3 = st.columns([1, 1, 4])
        if c1.button("Mark done", key=f"done_{s['id']}", disabled=s["status"] == "done"):
            set_status(s["id"], "done")
            st.rerun()
        if c2.button("Dismiss", key=f"dis_{s['id']}", disabled=s["status"] == "dismissed"):
            set_status(s["id"], "dismissed")
            st.rerun()
