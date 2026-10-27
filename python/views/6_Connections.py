import json

import pandas as pd
import streamlit as st

from seo_lab import integrations as ig

st.title("6. Connections")
st.write(
    "Connect the SEO Supervisor to GitHub, Vercel and Google. Every connection here is **read-only**: the app can look at your repositories, "
    "deployments and Google search data, but it cannot deploy, merge or change anything. Secrets are stored only on this computer "
    "(`python/.env` and `data/google_*.json`, both outside version control) and are never displayed in full."
)

google_ok = False
try:
    google_ok = ig.google_credentials() is not None
except Exception:
    pass
c1, c2, c3 = st.columns(3)
c1.metric("GitHub", "Token saved" if ig.get_setting("GITHUB_TOKEN") else "Public data only", border=True)
c2.metric("Vercel", "Token saved" if ig.get_setting("VERCEL_TOKEN") else "Not connected", border=True)
c3.metric("Google", "Connected" if google_ok else "Not connected", border=True)

# --------------------------------------------------------------------------- GitHub
st.header("GitHub")
st.write("Shows your repositories, whether a CI workflow exists, recent workflow runs and open pull requests. Without a token only public repositories are visible.")
st.link_button("Create a GitHub token (choose fine-grained, read-only)", ig.LINKS["github_token"])
st.caption("Suggested permissions: Contents, Actions and Pull requests set to **Read-only**, limited to the repository that holds the website.")
with st.form("github_form"):
    user = st.text_input("GitHub username", value=ig.get_setting("GITHUB_USER", "Ferdeen-Bakht"))
    repo = st.text_input("Website repository (owner/name)", value=ig.get_setting("GITHUB_REPO"), placeholder="Ferdeen-Bakht/my-travel-site")
    token = st.text_input(f"Token (currently: {ig.mask(ig.get_setting('GITHUB_TOKEN'))})", type="password", help="Leave empty to keep the saved token.")
    submitted = st.form_submit_button("Save and test GitHub", type="primary")
if submitted:
    ig.save_setting("GITHUB_USER", user)
    ig.save_setting("GITHUB_REPO", repo)
    if token.strip():
        ig.save_setting("GITHUB_TOKEN", token.strip())
    st.session_state["gh"] = True
if st.session_state.get("gh") or ig.get_setting("GITHUB_TOKEN"):
    with st.spinner("Asking GitHub..."):
        gh = ig.github_overview(ig.get_setting("GITHUB_USER", "Ferdeen-Bakht"), ig.get_setting("GITHUB_REPO"), ig.get_setting("GITHUB_TOKEN"))
    if gh["error"]:
        st.error(gh["error"])
    else:
        st.success(f"Connected as **{gh['login']}** ({gh['mode']} access). {len(gh['repos'])} repositories visible.")
        st.dataframe(pd.DataFrame(gh["repos"]).rename(columns={"name": "Repository", "language": "Language", "private": "Private", "pushed_at": "Last push", "url": "Link"}),
                     hide_index=True, width="stretch", column_config={"Link": st.column_config.LinkColumn("Link")})
        if gh["repo"]:
            st.write(f"**{gh['repo']['full_name']}**: default branch `{gh['repo']['default_branch']}`.")
            if gh["workflows"]:
                st.write("CI workflows found: " + ", ".join(f"{w['name']} ({w['path']})" for w in gh["workflows"]))
            else:
                st.warning("No GitHub Actions workflow found in this repository. A starter template is below.")
            if gh["runs"]:
                st.dataframe(pd.DataFrame(gh["runs"]), hide_index=True, width="stretch", column_config={"url": st.column_config.LinkColumn("url")})
            if gh["pulls"]:
                st.write("Open pull requests: " + ", ".join(f"[#{p['number']} {p['title']}]({p['url']})" for p in gh["pulls"]))
        else:
            st.info("Enter the repository that holds the website (owner/name) to see its CI status.")
with st.expander("Starter CI workflow (copy to .github/workflows/ci.yml in the website repository)"):
    st.caption("Builds the React frontend, builds the .NET backend and runs the Python tests on every pull request. It is a template and has not been run against your repository. Deployment is deliberately not included.")
    template = ig.github_actions_template()
    st.code(template, language="yaml")
    st.download_button("Download ci.yml", template, "ci.yml", "text/yaml")

# --------------------------------------------------------------------------- Vercel
st.header("Vercel")
st.write("Lists your Vercel projects and recent deployments, including previews. Vercel can host the React frontend only; the .NET backend needs a separate host (for example Azure App Service or Render).")
b1, b2 = st.columns(2)
b1.link_button("Create a Vercel token", ig.LINKS["vercel_token"])
b2.link_button("Open your Vercel projects", "https://vercel.com/ferdeens-projects")
with st.form("vercel_form"):
    vtoken = st.text_input(f"Token (currently: {ig.mask(ig.get_setting('VERCEL_TOKEN'))})", type="password", help="Leave empty to keep the saved token.")
    team = st.text_input("Team ID (only if the projects belong to a team)", value=ig.get_setting("VERCEL_TEAM_ID"), placeholder="team_xxxxxxxx")
    vsubmitted = st.form_submit_button("Save and test Vercel", type="primary")
if vsubmitted:
    if vtoken.strip():
        ig.save_setting("VERCEL_TOKEN", vtoken.strip())
    ig.save_setting("VERCEL_TEAM_ID", team)
    st.session_state["vc"] = True
if ig.get_setting("VERCEL_TOKEN"):
    with st.spinner("Asking Vercel..."):
        vc = ig.vercel_overview(ig.get_setting("VERCEL_TOKEN"), ig.get_setting("VERCEL_TEAM_ID"))
    if vc["error"]:
        st.error(vc["error"])
    else:
        st.success(f"{len(vc['projects'])} project(s) found.")
        if vc["projects"]:
            st.dataframe(pd.DataFrame(vc["projects"]).drop(columns=["id"]), hide_index=True, width="stretch")
            names = {p["name"]: p["id"] for p in vc["projects"]}
            pick = st.selectbox("Show deployments for", list(names))
            try:
                deployments = ig.vercel_deployments(ig.get_setting("VERCEL_TOKEN"), names[pick], ig.get_setting("VERCEL_TEAM_ID"))
                st.dataframe(pd.DataFrame(deployments), hide_index=True, width="stretch")
                st.caption("Rollback: in Vercel open the project → Deployments → pick an earlier production deployment → *Promote to Production*. This app does not do it for you.")
            except Exception as exc:
                st.error(f"Could not load deployments: {exc}")
else:
    st.caption("Not connected yet.")

# --------------------------------------------------------------------------- Google
st.header("Google (Search Console and Analytics)")
st.write("Real clicks, impressions, CTR, average position, queries and indexing status come from Google itself through official APIs. This needs a one-time OAuth setup in your own Google Cloud project.")
with st.expander("One-time setup steps", expanded=not google_ok):
    st.markdown(
        "1. Open the Google Cloud console and create or choose a project.\n"
        "2. Enable the **Google Search Console API** (and the **Google Analytics Data API** if you want traffic).\n"
        "3. Under *APIs & Services → OAuth consent screen* set the app to *External* and add yourself as a **test user**.\n"
        "4. Under *Credentials* create an **OAuth client ID** of type **Desktop app** and download the JSON.\n"
        "5. Upload that JSON below and press **Connect Google**. A Google sign-in page opens in your browser; you approve read-only access."
    )
    l1, l2, l3 = st.columns(3)
    l1.link_button("Enable Search Console API", ig.LINKS["google_enable_gsc"])
    l2.link_button("Enable Analytics Data API", ig.LINKS["google_enable_ga"])
    l3.link_button("Create OAuth client", ig.LINKS["google_credentials"])
uploaded = st.file_uploader("OAuth client JSON (Desktop app)", type="json")
if uploaded is not None:
    try:
        data = json.loads(uploaded.getvalue())
        if "installed" not in data:
            st.error("This looks like the wrong credential type. Create an OAuth client of type **Desktop app**.")
        else:
            ig.DATA_DIR.mkdir(parents=True, exist_ok=True)
            ig.GOOGLE_CLIENT_FILE.write_bytes(uploaded.getvalue())
            st.success("Client file saved locally.")
    except ValueError:
        st.error("That file is not valid JSON.")
g1, g2 = st.columns(2)
if g1.button("Connect Google", type="primary", disabled=not ig.GOOGLE_CLIENT_FILE.exists()):
    try:
        with st.spinner("Complete the Google sign-in in the browser window that just opened (up to 4 minutes)..."):
            ig.google_connect()
        st.rerun()
    except Exception as exc:
        st.error(f"Google connection failed: {exc}")
if g2.button("Disconnect Google", disabled=not google_ok):
    ig.google_disconnect()
    st.rerun()

if google_ok:
    st.success("Google is connected (read-only).")
    try:
        sites = ig.gsc_sites()
        if not sites:
            st.warning("This Google account has no Search Console properties. Add and verify your website at search.google.com/search-console first.")
        else:
            options = [s["site"] for s in sites]
            current = ig.get_setting("GSC_SITE_URL")
            site = st.selectbox("Search Console property to monitor", options, index=options.index(current) if current in options else 0)
            if st.button("Use this property"):
                ig.save_setting("GSC_SITE_URL", site)
                st.success(f"Saved. Open **7. SEO dashboard** to see data for {site}.")
    except Exception as exc:
        st.error(f"Could not list Search Console properties: {exc}")
    ga = st.text_input("Google Analytics 4 property ID (optional, digits only)", value=ig.get_setting("GA4_PROPERTY_ID"))
    if st.button("Save Analytics property"):
        ig.save_setting("GA4_PROPERTY_ID", ga.strip())
        st.success("Saved.")
    st.page_link("pages/7_SEO_Dashboard.py", label="Open the SEO dashboard →")
st.link_button("Open Google Search Console", ig.LINKS["search_console"])
st.caption("A site running only on localhost has no Google data. Search Console reports only for a public, verified website that Google has crawled.")
