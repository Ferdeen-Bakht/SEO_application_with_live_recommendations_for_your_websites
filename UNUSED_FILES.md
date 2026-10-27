# Files that are no longer used

The project was changed from "publish to a local .NET demo site" to "read-only review of a live site". The files below are **not imported, linked or run** by the current app. Nothing has been deleted; remove them whenever you like. Paths are relative to this folder.

| Path | Why it is unused | Safe to delete? |
|---|---|---|
| `dotnet/` (whole folder, incl. `ClientApp/node_modules`) | Demo travel website. The app now reviews a live site and never publishes. | Yes |
| `python/views/6_Connections.py` | GitHub / Vercel / Google connections page; removed from navigation. | Yes |
| `python/views/7_SEO_Dashboard.py` | Old Google Search Console / Analytics dashboard; needed the Connections page. Replaced by `6_Rankings.py`. | Yes |
| `python/views/3_Approval_Queue.py` | Approve-and-publish workflow. Replaced by `3_Saved_Suggestions.py`. | Yes |
| `python/seo_lab/integrations.py` | Code behind the Connections page and old dashboard. | Yes |
| `python/seo_lab/dotnet_client.py` | HTTP client for the .NET demo API. Replaced by `live_site.py`. | Yes |
| `python/tests/test_integrations.py` | Tests `integrations.py`. | Yes (together with it) |
| `data/seo_lab.db` | Old SQLite file whose `proposals` table is demo data. The app now uses a separate `suggestions` table in the same file, which is created automatically. | Yes, if you do not need the old demo proposals |
| `data/benchmark_history.json` | Score history from the demo travel site; mixes with live-site history if kept. | Yes |
| `screenshots/` | Screenshots of the old demo. | Yes |
| `python/seo_lab/local_llm.py` -> `suggest_seo()` | Old single-shot draft function; only `suggest_changes()` is used. | Yes (delete that function only) |
| `python/requirements.txt` | Already updated; `google-auth-oauthlib` and `google-api-python-client` were removed. | n/a |

## Not implemented yet

- Keyword rankings now run against a local SearXNG (see README). Mojeek's paid API path is coded but untested (no key).
- Google positions and Search Console data (the connection was removed on request).
- Rank history over time for keywords (only the latest check is stored in `data/serp_ranks.json`).

## Old un-suffixed result files (appcreatorz.com era)

Results are now stored per site (`*__<site>.json/csv`). These older files are no longer read: `data/benchmark.json`, `data/benchmark_history.json`, `data/serp_ranks.json`, `data/exports/local_site.csv`, `data/exports/competitors.csv`. Safe to delete.

Note: the `pages/` folder was renamed to `views/` because Streamlit's automatic `pages/` discovery overrides the custom navigation when a page is opened by direct URL.
