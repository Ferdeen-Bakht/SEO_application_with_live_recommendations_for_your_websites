# AI SEO Lab: live-site review 

A **read-only** SEO review tool. It crawls a live website, finds problems, asks a local AI model (Ollama) for suggested rewrites, and compares the site against competitors. It **never changes the website**: accepted suggestions are saved as a hand-off list for a developer.

## What it does

- **Crawl & audit**: crawls the live site (unlimited pages by default: it follows every reachable link, shows live progress, and stops at a time limit you set (default 15 min) or a safety ceiling of 2,000 pages, `CRAWL_HARD_LIMIT` in `.env`; PDFs, images and other downloads are skipped). JavaScript (React) sites are rendered in your installed Edge/Chrome via Playwright, so the audit sees what visitors and Google see. Adds site-wide checks: robots.txt, XML sitemap, soft-404s, HTTP→HTTPS redirect, duplicate titles/descriptions, missing H1s, content visible without JS, thin pages.
- **Competitor benchmark** and **Rankings vs competitors** come *before* suggestions. Rankings has two parts: keyword positions for 5 keywords from a search engine you can check yourself, with an SEO score computed from those SearXNG positions only, and an on-page signals comparison (no score).
- **Suggestions** (needs the benchmark first; uses search rankings if available): per page, the local model proposes title / description / H1 in one call and rewrites each intro paragraph in its own call (so text cannot shift between paragraphs). Optionally it adds one extra paragraph built only from facts already on the page. Only ONE competitor's data goes to the model: the best-ranked competitor for the page's keyword (from the search rankings), whose page is used as a reference for topics and clarity; suggestions are checked against **your** page's facts and flagged if they copy its wording or lean on its vocabulary (if its page cannot be fetched, the search engine's own title and snippet are used). It is also shown the closest matching competitor page's title, description, H1, headings, word count and schema types (structure only, never body text) plus the topics those pages cover that yours doesn't. Each is tested for accuracy (no invented facts), clarity, keyword relevance and detail, with an estimated score impact. Accept or reject; save accepted ones.
- **Saved suggestions**: download as Markdown for your developer.
- **Create backlinks**: the local model writes one educational article from a page of your site (link, disclosure and a risk warning for financial topics are added; checks run on your edits), with a button to create a **private draft** (or publish publicly after a confirmation tick) on dev.to via its API, plus 5 recommended sites to post on. The dev.to key lives in `python/.env` as `DEVTO_API_KEY`. Links on such platforms are usually nofollow, so expect referral traffic and brand mentions, not direct ranking credit.

> Keyword positions come from SearXNG or Mojeek, not Google. The on-page leaderboard ranks measured page signals, not search positions.

## Keyword rankings: pick one provider

Mojeek's public search page forbids automated queries (robots.txt + 403), so this tool does **not** scrape it.

1. **SearXNG (free, self-hosted) - set up and working on this PC**: installed in `tools/searxng` (own venv) with a small Windows shim for the Unix-only `pwd` module (`tools/shims/pwd.py`) and local-only settings (`tools/searxng-settings.yml`: JSON on, bound to 127.0.0.1). Start it with `powershell -File tools\start_searxng.ps1` and leave it running; you can open http://127.0.0.1:8080 in a browser to run the same queries yourself. `.env` already has `SERP_PROVIDER=searxng`. SearXNG is a metasearch engine, so positions are SearXNG's merged ordering (currently mostly its Google-CSE source; Brave/DuckDuckGo may be rate-limited), not Google's. On Linux/macOS Docker is the easier route.
2. **Mojeek API (paid, about £1 per 1,000 queries)**: get a key at mojeek.com/services/api.html, set `SERP_PROVIDER=mojeek` and `MOJEEK_API_KEY=...` in `python/.env`.

Each result row has an "open search" link so you can run the same query yourself. See `UNUSED_FILES.md` for files that are no longer used.

## Setup (Windows PowerShell)

```powershell
cd python
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
ollama pull qwen2.5:3b
```

Playwright uses the Edge or Chrome already installed (`BROWSER_CHANNEL` in `.env`); no browser download is needed.

## Run

```powershell
cd python
.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open http://localhost:8501 and go through pages 1 → 6. To review a different site, change `SITE_URL` in `python/.env`.

## Safety

- Only GET requests to the target; the crawler respects robots.txt, stays on one host and is rate-limited. Review only sites you are authorized to test.
- Competitor sites are fetched politely (a few pages each) for comparison only.
- AI drafts can be wrong. Check facts before using any suggestion.
- The SEO score is a learning aid made of simple visible checks, not a Google score.

## Layout

```text
data/                 crawl results, CSV exports, SQLite suggestions (created at run time)
docs/SEO_CONCEPTS.md
python/
  streamlit_app.py    navigation
  views/              0_Home, 1_Crawl_Audit, 2_Content_Optimizer, 3_Saved_Suggestions, 4_SEO_Concepts, 5_Competitor_Benchmark, 6_Rankings
  seo_lab/            crawler, renderer (Playwright), site_checks, technical_seo, page_metrics, agent, local_llm, benchmark, repository, live_site
```
