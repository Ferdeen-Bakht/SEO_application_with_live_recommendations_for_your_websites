import streamlit as st
from seo_lab import site_state
from seo_lab.repository import init_db

st.set_page_config(page_title="AI SEO Lab · Live site review", page_icon="🔎", layout="wide")
init_db()

pages = [
    st.Page("views/0_Home.py", title="Home & setup", icon="🏠", default=True),
    st.Page("views/1_Crawl_Audit.py", title="1. Crawl & audit", icon="🕷️"),
    st.Page("views/5_Competitor_Benchmark.py", title="2. Competitor benchmark", icon="📊"),
    st.Page("views/6_Rankings.py", title="3. Rankings vs competitors", icon="🏆"),
    st.Page("views/2_Content_Optimizer.py", title="4. Suggestions", icon="✍️"),
    st.Page("views/3_Saved_Suggestions.py", title="5. Saved suggestions", icon="📋"),
    st.Page("views/7_Create_Backlinks.py", title="6. Create backlinks", icon="🔗"),
    st.Page("views/8_Domain_Stats.py", title="7. Domain stats", icon="📈"),
    st.Page("views/4_SEO_Concepts.py", title="8. SEO concepts", icon="📚"),
]
selected = st.navigation(pages, position="sidebar")
with st.sidebar:
    st.markdown(f"**Reviewing:** {site_state.get_site_url()}")
    st.caption("Read-only • Local AI • Suggestions only, nothing is published")
selected.run()
