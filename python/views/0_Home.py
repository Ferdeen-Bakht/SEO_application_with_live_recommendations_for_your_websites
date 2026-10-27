import httpx
import streamlit as st

from seo_lab import site_state
from seo_lab.config import BROWSER_CHANNEL, OLLAMA_BASE_URL, OLLAMA_MODEL

st.title("AI SEO Lab · live site review")
site = site_state.get_site_url()
st.write("Audits a live website and suggests improvements. It only **reads** the site (public pages, robots.txt, sitemap): it cannot and does not change anything.")
st.info("Workflow: crawl & audit → competitor benchmark (competitors are found automatically) → rankings for 5 generated keywords → AI suggestions per page → save the ones you like.")

left, right = st.columns(2)
with left:
    st.subheader("Website under review")
    new_site = st.text_input("Website address", value=site, help="Used by every page. Changing it clears the old competitors and keywords; results are stored per site.")
    if st.button("Use this website", width="stretch"):
        try:
            saved = site_state.set_site(new_site)
            st.success(f"Now reviewing {saved}. Go to **1. Crawl & audit**.")
        except ValueError as exc:
            st.error(str(exc))
    st.caption(f"Browser for JS rendering: {BROWSER_CHANNEL} (BROWSER_CHANNEL in python/.env). JavaScript sites are rendered so the audit sees what visitors and Google see.")
with right:
    st.subheader("Local AI model")
    st.code(f"{OLLAMA_BASE_URL}\nModel: {OLLAMA_MODEL}")
    if st.button("Test Ollama connection", width="stretch"):
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{OLLAMA_BASE_URL}/api/tags")
                response.raise_for_status()
                models = [m["name"] for m in response.json().get("models", [])]
            st.success("Ollama is reachable.")
            st.write("Installed models:", ", ".join(models) if models else "No models found; pull the model from the terminal.")
        except Exception as exc:
            st.error(f"Cannot reach Ollama: {exc}. Open Ollama and pull the configured model.")

st.subheader("What each page does")
st.markdown("""
- **Crawl & audit:** crawls the live site (rendering JavaScript), runs page checks and site-wide checks (robots.txt, sitemap, soft 404s, duplicate titles).
- **Competitor benchmark:** finds competitors automatically from search results, crawls them and compares page-level SEO signals.
- **Rankings vs competitors:** the local model generates 5 keywords for the site, then shows who ranks for them in a search engine you can check yourself.
- **Suggestions:** the local model proposes title, description, H1 and intro rewrites per page using the competitor data.
- **Saved suggestions:** your accepted suggestions as a to-do list you can download.

Keyword positions come from SearXNG/Mojeek, not Google. Real Google positions need Search Console or a rank-tracking service.
""")
