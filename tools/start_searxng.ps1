# Starts the local SearXNG used for keyword rankings (http://127.0.0.1:8080). Leave this window open; Ctrl+C to stop.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:SEARXNG_SETTINGS_PATH = Join-Path $here "searxng-settings.yml"
$env:PYTHONPATH = "$here\shims;$here\searxng"
Set-Location "$here\searxng"
& "$here\searxng\venv\Scripts\python.exe" -m searx.webapp
