import pandas as pd
import streamlit as st

from seo_lab import backlinks as bl
from seo_lab import site_state
from seo_lab.config import DEVTO_API_KEY
from seo_lab.live_site import get_pages

SITE_URL, LABEL = site_state.get_site_url(), site_state.label()
K = lambda name: f"bl_{name}_{LABEL}"  # widget/session keys are per site

st.title("6. Create backlinks")
st.caption(f"Reviewing **{SITE_URL}**")
st.info("**What to expect.** Links on blogging and community sites are usually *nofollow*, so they pass little or no direct ranking credit. "
        "What you gain is referral traffic, brand mentions and discovery, and only if the article is genuinely useful and discloses who wrote it. "
        "Nothing here posts by itself: every publish needs your click, and the default is a **private draft**.")

pages = get_pages()
if not pages:
    st.warning(f"No crawled pages for {SITE_URL} yet. Run **1. Crawl & audit** first.")
    st.page_link("views/1_Crawl_Audit.py", label="Go to Crawl & audit →")
    st.stop()
site_text = " ".join(f"{p['title']} {p['h1']} {p['metaDescription']}" for p in pages[:30])
keywords = site_state.get_keywords()

# ============================================================================== 1. write the article
st.header("1. Write one article about your website")
labels = {f"{p['path']} — {p['title'][:70]}": p for p in pages}
home_index = next((i for i, p in enumerate(pages) if p["path"] == "/"), 0)
c1, c2 = st.columns(2)
choice = c1.selectbox("Base the article on this page", list(labels), index=home_index)
page = labels[choice]
kw_pick = c2.selectbox("Topic keyword", keywords or [page["h1"] or page["title"]])
kw_typed = c2.text_input("...or type your own keyword", max_chars=100)
keyword = kw_typed.strip() or kw_pick

if st.button("✍️ Write the article with the local model", type="primary"):
    try:
        with st.spinner("The local model is writing the article (about 1 to 3 minutes)..."):
            art = bl.generate_article(page, keyword, pages, SITE_URL)
        st.session_state[K("removed")] = art.get("removed", [])
        st.session_state[K("meta")] = {"link": art["link"], "financial": art["financial"], "source_text": art["source_text"], "keyword": keyword, "brand": art["brand"]}
        st.session_state[K("title")], st.session_state[K("desc")] = art["title"], art["description"]
        st.session_state[K("tags")], st.session_state[K("body")] = ", ".join(art["tags"]), art["body"]
    except Exception as exc:
        st.error(str(exc))

meta = st.session_state.get(K("meta"))
if not meta:
    st.caption("The article is built only from the facts on the page you pick, includes a link to it, and is yours to edit before anything is published.")
else:
    if st.session_state.get(K("removed")):
        st.info("Removed an advert-style section the model added: " + ", ".join(f"“{h}”" for h in st.session_state[K("removed")]) + ". Platforms treat sign-up calls to action as ads.")
    title = st.text_input("Title", key=K("title"), max_chars=120)
    desc = st.text_input("Short description (max 150 characters)", key=K("desc"), max_chars=150)
    tags = st.text_input("Tags (up to 4, comma separated)", key=K("tags"))
    body = st.text_area("Article (Markdown)", key=K("body"), height=420)
    st.markdown("**Checks on the text as it is now**")
    for c in bl.article_checks(body, meta["link"], meta["financial"], meta["source_text"], meta["keyword"]):
        st.markdown(f"{'✅' if c['ok'] else '⚠️'} **{c['label']}**: {c['detail']}")
    with st.expander("Preview"):
        st.markdown(f"## {title}\n\n{body}")

    # ======================================================================== 2. publish to dev.to
    st.header("2. Publish to dev.to")
    if meta["financial"]:
        st.warning("This article is about a financial product (forex/CFDs/crypto). Promoting such products is regulated in many countries and platforms often "
                   "restrict it. Keep it educational, keep the risk warning, and check dev.to's rules and the financial-promotion rules that apply to you "
                   "before publishing publicly. I could not verify dev.to's current self-promotion rules, so starting with a private draft is the safe choice.")
    override = st.text_input("dev.to API key (optional: overrides the one in python/.env for this session)", type="password")
    api_key = override.strip() or DEVTO_API_KEY
    st.caption("API key: ✅ loaded from python/.env" if DEVTO_API_KEY and not override.strip() else "API key: using the one you pasted" if override.strip()
               else "API key: ❌ not set (add DEVTO_API_KEY to python/.env or paste it above)")
    if st.button("Test the key (read-only)"):
        try:
            st.success(f"The key works. It belongs to dev.to user @{bl.check_devto_key(api_key)}.")
        except bl.PublishError as exc:
            st.error(str(exc))

    def publish(public: bool):
        # If a draft already exists (made earlier here, or an unpublished article of yours with this title) it is UPDATED, not duplicated:
        # dev.to refuses a second new article with the same title within five minutes.
        try:
            with st.spinner("Sending to dev.to..."):
                result = bl.save_to_devto(api_key, title, body, [t for t in tags.split(",")], desc, published=public,
                                          known_id=st.session_state.get(K("devto_id")))
            st.session_state[K("devto_id")] = result["id"]
            bl.log_publication("dev.to", title, result["url"], result["published"], result["id"])
            verb = ("Published publicly" if result["published"] else "Private draft saved") + (" (updated your existing draft)" if result["updated"] else "")
            st.success(f"{verb}: {result['url']}")
            st.link_button("Open on dev.to", result["url"])
        except bl.PublishError as exc:
            st.error(str(exc))

    can_send = bool(title.strip() and body.strip() and api_key)
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Safe option**")
        if st.button("Create or update the private draft on dev.to", disabled=not can_send, type="primary"):
            publish(False)
        st.caption("Only you can see a draft. Open it on dev.to, read it, and publish from there if you are happy. Clicking again updates the same draft.")
    with d2:
        st.markdown("**Goes live immediately**")
        ok = st.checkbox("I have read this article. It is accurate, discloses who wrote it, and I am allowed to publish it under dev.to's rules and the financial-promotion rules that apply to us.")
        st.caption("If a draft with this title already exists on dev.to, this publishes that draft instead of creating a duplicate.")
        if st.button("Publish publicly on dev.to", disabled=not (can_send and ok)):
            publish(True)

# ============================================================================== 3. five more places
st.header("3. Five more places to post")
st.caption("Chosen from your site's keywords and page text. These come from my general knowledge: check each community's current rules before posting, and "
           "never post the same promotional text everywhere. (TradingView is left out on purpose: its house rules ban links and website references in ideas.)")
for site in bl.recommend_sites(keywords, site_text, 5):
    with st.container(border=True):
        left, right = st.columns([4, 1])
        left.markdown(f"**{site['name']}** · fits: {', '.join(site['fits'])}")
        left.write(f"**What to post:** {site['post']}")
        left.caption(f"Links: {site['link']}")
        left.caption(f"Rules: {site['rules']}")
        right.link_button("Open site", site["url"], width="stretch")

# ============================================================================== 4. history
log = bl.load_log()
if log:
    st.header("What you have created")
    st.dataframe(pd.DataFrame(log).iloc[::-1], hide_index=True, width="stretch",
                 column_config={"url": st.column_config.LinkColumn("url", display_text="open")})
