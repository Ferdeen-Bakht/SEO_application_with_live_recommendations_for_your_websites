"""Connections to GitHub, Vercel and Google (Search Console, URL Inspection, Analytics).

Rules this module follows:
- Secrets are typed by the user into this local app and stored in python/.env (git-ignored) or data/google_*.json.
  They are never printed, logged or sent anywhere except the official API of the service they belong to.
- Every function returns real API data or raises/returns an error. Nothing is estimated or invented here.
- Everything here is read-only. No deployments, merges or Search Console changes are made.
"""
from datetime import date, timedelta
import json
import os

import httpx
from dotenv import dotenv_values, set_key

from seo_lab.config import DATA_DIR, PYTHON_DIR

ENV_FILE = PYTHON_DIR / ".env"
GOOGLE_TOKEN_FILE = DATA_DIR / "google_token.json"
GOOGLE_CLIENT_FILE = DATA_DIR / "google_client_secret.json"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",   # Search Console (read-only)
    "https://www.googleapis.com/auth/analytics.readonly",    # Google Analytics (read-only)
]

LINKS = {
    "github_token": "https://github.com/settings/personal-access-tokens/new",
    "vercel_token": "https://vercel.com/account/tokens",
    "google_credentials": "https://console.cloud.google.com/apis/credentials",
    "google_enable_gsc": "https://console.cloud.google.com/apis/library/searchconsole.googleapis.com",
    "google_enable_ga": "https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com",
    "search_console": "https://search.google.com/search-console",
    "analytics": "https://analytics.google.com/",
}


# --------------------------------------------------------------------------- settings
def get_setting(key: str, default: str = "") -> str:
    return (dotenv_values(ENV_FILE).get(key) or os.getenv(key) or default).strip()


def save_setting(key: str, value: str) -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")
    set_key(str(ENV_FILE), key, value.strip(), quote_mode="never")


def mask(value: str) -> str:
    return "not set" if not value else (value[:4] + "…" + value[-4:] if len(value) > 12 else "set")


# --------------------------------------------------------------------------- GitHub
def _github(path: str, token: str = "") -> httpx.Response:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ai-seo-supervisor", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.get("https://api.github.com" + path, headers=headers, timeout=15)


def github_overview(user: str, repo: str = "", token: str = "") -> dict:
    """Public data works without a token; a token adds private repos, workflows and pull requests."""
    out = {"mode": "authenticated" if token else "public", "login": user, "repos": [], "repo": None, "workflows": [], "runs": [], "pulls": [], "error": ""}
    try:
        if token:
            me = _github("/user", token)
            if me.status_code == 401:
                out["error"] = "GitHub rejected the token (401). Check that it is correct and not expired."
                return out
            out["login"] = me.json().get("login", user)
            repos = _github("/user/repos?per_page=100&sort=pushed&affiliation=owner", token)
        else:
            repos = _github(f"/users/{user}/repos?per_page=100&sort=pushed")
        if repos.status_code != 200:
            out["error"] = f"GitHub returned HTTP {repos.status_code} while listing repositories."
            return out
        out["repos"] = [{"name": r["name"], "language": r.get("language") or "", "private": r["private"], "pushed_at": r["pushed_at"], "url": r["html_url"]} for r in repos.json()]
        if repo:
            r = _github(f"/repos/{repo}", token)
            if r.status_code != 200:
                out["error"] = f"Repository {repo} not found or not accessible (HTTP {r.status_code})."
                return out
            out["repo"] = {k: r.json().get(k) for k in ("full_name", "default_branch", "private", "html_url", "pushed_at")}
            wf = _github(f"/repos/{repo}/actions/workflows", token)
            if wf.status_code == 200:
                out["workflows"] = [{"name": w["name"], "path": w["path"], "state": w["state"]} for w in wf.json().get("workflows", [])]
            runs = _github(f"/repos/{repo}/actions/runs?per_page=5", token)
            if runs.status_code == 200:
                out["runs"] = [{"workflow": x["name"], "branch": x["head_branch"], "status": x["status"], "conclusion": x["conclusion"], "url": x["html_url"], "created": x["created_at"]} for x in runs.json().get("workflow_runs", [])]
            if token:
                pulls = _github(f"/repos/{repo}/pulls?state=open&per_page=10", token)
                if pulls.status_code == 200:
                    out["pulls"] = [{"number": p["number"], "title": p["title"], "url": p["html_url"]} for p in pulls.json()]
    except httpx.HTTPError as exc:
        out["error"] = f"Could not reach GitHub: {type(exc).__name__}"
    return out


# --------------------------------------------------------------------------- Vercel
def vercel_overview(token: str, team_id: str = "") -> dict:
    out = {"projects": [], "error": ""}
    params = {"limit": 50}
    if team_id:
        params["teamId"] = team_id
    try:
        r = httpx.get("https://api.vercel.com/v9/projects", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if r.status_code in (401, 403):
            out["error"] = f"Vercel rejected the token (HTTP {r.status_code}). If your projects belong to a team, also enter the Team ID."
            return out
        r.raise_for_status()
        for p in r.json().get("projects", []):
            latest = (p.get("latestDeployments") or [{}])[0]
            out["projects"].append({
                "name": p["name"], "id": p["id"], "framework": p.get("framework") or "",
                "repo": (p.get("link") or {}).get("repo", ""), "latest_state": latest.get("readyState", ""),
                "latest_url": latest.get("url", ""), "updated": p.get("updatedAt"),
            })
    except httpx.HTTPError as exc:
        out["error"] = f"Could not reach Vercel: {type(exc).__name__}"
    return out


def vercel_deployments(token: str, project_id: str, team_id: str = "", limit: int = 10) -> list[dict]:
    params = {"projectId": project_id, "limit": limit}
    if team_id:
        params["teamId"] = team_id
    r = httpx.get("https://api.vercel.com/v6/deployments", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    return [{"url": d["url"], "state": d.get("readyState") or d.get("state"), "target": d.get("target") or "preview", "created": d["created"],
             "branch": (d.get("meta") or {}).get("githubCommitRef", ""), "commit": (d.get("meta") or {}).get("githubCommitMessage", "")}
            for d in r.json().get("deployments", [])]


# --------------------------------------------------------------------------- Google (OAuth, Search Console, Analytics)
def google_credentials():
    """Return valid credentials from the saved token, refreshing when needed; None if not connected."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not GOOGLE_TOKEN_FILE.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_FILE), GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        GOOGLE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds if creds.valid else None


def google_connect() -> None:
    """Open Google's consent screen in the user's browser (OAuth 'desktop app' flow) and save the token locally."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not GOOGLE_CLIENT_FILE.exists():
        raise RuntimeError("Upload your Google OAuth client JSON first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CLIENT_FILE), GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=240, authorization_prompt_message="", success_message="Connected. You can close this tab and return to the dashboard.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GOOGLE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")


def google_disconnect() -> None:
    GOOGLE_TOKEN_FILE.unlink(missing_ok=True)


def _service(name: str, version: str):
    from googleapiclient.discovery import build
    creds = google_credentials()
    if not creds:
        raise RuntimeError("Google is not connected.")
    return build(name, version, credentials=creds, cache_discovery=False)


def gsc_sites() -> list[dict]:
    entries = _service("searchconsole", "v1").sites().list().execute().get("siteEntry", [])
    return [{"site": e["siteUrl"], "permission": e["permissionLevel"]} for e in entries]


def default_range(days: int = 28) -> tuple[str, str]:
    """Search Console data lags by about 2 days, so the range ends 2 days ago."""
    end = date.today() - timedelta(days=2)
    return (end - timedelta(days=days - 1)).isoformat(), end.isoformat()


def parse_rows(response: dict, dimensions: list[str]) -> list[dict]:
    """Turn a Search Analytics response into flat rows. CTR is a percentage; position is Google's average position."""
    rows = []
    for r in response.get("rows", []):
        row = {d: k for d, k in zip(dimensions, r.get("keys", []))}
        row.update({"clicks": int(r["clicks"]), "impressions": int(r["impressions"]), "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1)})
        rows.append(row)
    return rows


def gsc_query(site: str, start: str, end: str, dimensions: list[str], row_limit: int = 250) -> list[dict]:
    body = {"startDate": start, "endDate": end, "dimensions": dimensions, "rowLimit": row_limit, "dataState": "final"}
    return parse_rows(_service("searchconsole", "v1").searchanalytics().query(siteUrl=site, body=body).execute(), dimensions)


def gsc_totals(site: str, start: str, end: str) -> dict:
    """Totals without dimensions, so they match what Search Console itself shows."""
    resp = _service("searchconsole", "v1").searchanalytics().query(siteUrl=site, body={"startDate": start, "endDate": end, "dataState": "final"}).execute()
    rows = parse_rows(resp, [])
    return rows[0] if rows else {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}


def gsc_inspect(site: str, url: str) -> dict:
    """Official URL Inspection API: Google's own index status for one URL (quota-limited per property)."""
    body = {"inspectionUrl": url, "siteUrl": site}
    result = _service("searchconsole", "v1").urlInspection().index().inspect(body=body).execute().get("inspectionResult", {})
    idx = result.get("indexStatusResult", {})
    return {"url": url, "verdict": idx.get("verdict", "UNKNOWN"), "coverage": idx.get("coverageState", ""), "last_crawl": idx.get("lastCrawlTime", ""),
            "robots": idx.get("robotsTxtState", ""), "indexing_allowed": idx.get("indexingState", ""), "google_canonical": idx.get("googleCanonical", ""),
            "user_canonical": idx.get("userCanonical", "")}


def ga4_summary(property_id: str, start: str, end: str) -> dict:
    """Sessions, users and views from the Google Analytics Data API (needs a GA4 property you can read)."""
    body = {"dateRanges": [{"startDate": start, "endDate": end}],
            "metrics": [{"name": "sessions"}, {"name": "totalUsers"}, {"name": "screenPageViews"}]}
    resp = _service("analyticsdata", "v1beta").properties().runReport(property=f"properties/{property_id}", body=body).execute()
    vals = [int(v["value"]) for v in (resp.get("rows") or [{"metricValues": [{"value": 0}] * 3}])[0]["metricValues"]]
    return {"sessions": vals[0], "users": vals[1], "views": vals[2]}


# --------------------------------------------------------------------------- derived from REAL Search Console rows
def keyword_opportunities(query_rows: list[dict], min_impressions: int = 20) -> list[dict]:
    """Label real queries that look improvable. These are rules applied to real data, not forecasts."""
    out = []
    for r in query_rows:
        if r["impressions"] < min_impressions:
            continue
        if 8 <= r["position"] <= 20:
            why = f"Average position {r['position']}: close to page 1 with {r['impressions']} impressions."
        elif r["position"] < 8 and r["ctr"] < 2:
            why = f"Ranks around {r['position']} but only {r['ctr']}% click-through: the title or description may not match what searchers want."
        else:
            continue
        out.append({"query": r["query"], "impressions": r["impressions"], "clicks": r["clicks"], "ctr": r["ctr"], "position": r["position"], "why": why})
    return sorted(out, key=lambda x: -x["impressions"])[:25]


# --------------------------------------------------------------------------- CI template
def github_actions_template(frontend_dir: str = "dotnet/SeoDemoSite/ClientApp", backend_dir: str = "dotnet/SeoDemoSite", python_dir: str = "python") -> str:
    """A starter CI workflow the user can copy into .github/workflows/ci.yml (tests only; deployment is a separate step)."""
    return f"""name: CI
on:
  pull_request:
  push:
    branches: [main]

jobs:
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {{ node-version: 22, cache: npm, cache-dependency-path: {frontend_dir}/package-lock.json }}
      - run: npm ci
        working-directory: {frontend_dir}
      - run: npm run build
        working-directory: {frontend_dir}

  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with: {{ dotnet-version: 10.0.x }}
      - run: dotnet build {backend_dir} --configuration Release

  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {{ python-version: "3.13", cache: pip, cache-dependency-path: {python_dir}/requirements.txt }}
      - run: pip install -r requirements.txt pytest
        working-directory: {python_dir}
      - run: python -m pytest -q
        working-directory: {python_dir}
"""
