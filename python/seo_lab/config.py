"""Central configuration. Keep secrets in .env, never commit them."""
import os
from pathlib import Path
from dotenv import load_dotenv

PYTHON_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PYTHON_DIR.parent
load_dotenv(PYTHON_DIR / ".env")

# The live website under review. This tool only reads it; it never writes to it.
SITE_URL = os.getenv("SITE_URL", "https://appcreatorz.com").rstrip("/")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
# Keyword-ranking provider: "searxng" (your own instance, free) or "mojeek" (official paid API).
SERP_PROVIDER = os.getenv("SERP_PROVIDER", "searxng").lower()
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://127.0.0.1:8080").rstrip("/")
MOJEEK_API_KEY = os.getenv("MOJEEK_API_KEY", "")
# dev.to key for the Create backlinks page (kept in .env, never in code)
DEVTO_API_KEY = os.getenv("DEVTO_API_KEY", "")
# Browser used to render JavaScript sites: "msedge" or "chrome" (already installed on Windows).
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "msedge")
DB_PATH_RAW = os.getenv("SEO_DB_PATH", "../data/seo_lab.db")
DB_PATH = (PYTHON_DIR / DB_PATH_RAW).resolve() if not Path(DB_PATH_RAW).is_absolute() else Path(DB_PATH_RAW)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
