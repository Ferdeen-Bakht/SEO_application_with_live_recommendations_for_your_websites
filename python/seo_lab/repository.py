"""SQLite storage for accepted suggestions. Nothing here is ever published; it is a to-do list for a human."""
import json
import sqlite3
from datetime import datetime, timezone
from seo_lab.config import DB_PATH

STATUSES = ("open", "done", "dismissed")


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_url TEXT NOT NULL,
            page_path TEXT NOT NULL,
            original_json TEXT NOT NULL,
            suggested_json TEXT NOT NULL,
            rationale TEXT NOT NULL,
            target_query TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','dismissed')),
            created_at TEXT NOT NULL,
            updated_at TEXT
        )""")


def create_suggestion(site_url, page, suggested, rationale, target_query):
    original = {"title": page.get("title", ""), "metaDescription": page.get("metaDescription", ""),
                "h1": page.get("h1", ""), "paragraphs": page.get("paragraphs", [])}
    suggested_json = {"title": suggested["title"].strip(), "metaDescription": suggested["metaDescription"].strip(),
                      "h1": suggested["h1"].strip(), "paragraphs": suggested["paragraphs"]}
    with connect() as db:
        cur = db.execute("""INSERT INTO suggestions (site_url, page_path, original_json, suggested_json, rationale, target_query, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (site_url, page["path"], json.dumps(original, ensure_ascii=False),
                          json.dumps(suggested_json, ensure_ascii=False), rationale, target_query, now()))
        return cur.lastrowid


def list_suggestions(status=None):
    with connect() as db:
        rows = db.execute("SELECT * FROM suggestions WHERE status=? ORDER BY id DESC", (status,)).fetchall() if status \
            else db.execute("SELECT * FROM suggestions ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["original"] = json.loads(item.pop("original_json"))
        item["suggested"] = json.loads(item.pop("suggested_json"))
        result.append(item)
    return result


def set_status(suggestion_id, new_status):
    if new_status not in STATUSES:
        raise ValueError(new_status)
    with connect() as db:
        cur = db.execute("UPDATE suggestions SET status=?, updated_at=? WHERE id=?", (new_status, now(), int(suggestion_id)))
        return cur.rowcount == 1
