"""Stockage SQLite des recherches, de leur journal et des leads trouvés."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    profile TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS search_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL REFERENCES searches(id),
    created_at TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL REFERENCES searches(id),
    created_at TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    score INTEGER NOT NULL,
    data TEXT NOT NULL,
    UNIQUE (search_id, dedupe_key)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def create_search(profile: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO searches (created_at, profile, status) VALUES (?, ?, 'running')",
            (_now(), json.dumps(profile, ensure_ascii=False)),
        )
        return cur.lastrowid


def finish_search(search_id: int, status: str, summary: str = "", error: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE searches SET status = ?, summary = ?, error = ? WHERE id = ?",
            (status, summary, error, search_id),
        )


def log_event(search_id: int, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO search_events (search_id, created_at, message) VALUES (?, ?, ?)",
            (search_id, _now(), message),
        )


def dedupe_key(lead: dict) -> str:
    if lead.get("kind") == "tender":
        reference = " ".join((lead.get("reference") or "").lower().split())
        if reference:
            return f"ref:{reference}"
        url = (lead.get("url") or "").lower().rstrip("/")
        return f"url:{url}" if url else "title:" + " ".join((lead.get("title") or "").lower().split())
    siren = (lead.get("siren") or "").replace(" ", "")
    if siren:
        return f"siren:{siren}"
    website = (lead.get("website") or "").lower()
    for prefix in ("https://", "http://", "www."):
        website = website.removeprefix(prefix)
    website = website.rstrip("/")
    if website:
        return f"web:{website}"
    return "name:" + " ".join((lead.get("company_name") or "").lower().split())


def save_lead(search_id: int, lead: dict) -> bool:
    """Enregistre ou met à jour un lead. Renvoie True si c'est un nouveau lead."""
    key = dedupe_key(lead)
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE search_id = ? AND dedupe_key = ?", (search_id, key)
        ).fetchone()
        payload = json.dumps(lead, ensure_ascii=False)
        if existing:
            conn.execute(
                "UPDATE leads SET score = ?, data = ? WHERE id = ?",
                (lead["score"], payload, existing["id"]),
            )
            return False
        conn.execute(
            "INSERT INTO leads (search_id, created_at, dedupe_key, score, data) VALUES (?, ?, ?, ?, ?)",
            (search_id, _now(), key, lead["score"], payload),
        )
        return True


def count_leads(search_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM leads WHERE search_id = ?", (search_id,)
        ).fetchone()[0]


def list_searches() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM leads l WHERE l.search_id = s.id) AS lead_count
               FROM searches s ORDER BY s.id DESC"""
        ).fetchall()
    return [_search_row(r) for r in rows]


def get_search(search_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT s.*, (SELECT COUNT(*) FROM leads l WHERE l.search_id = s.id) AS lead_count
               FROM searches s WHERE s.id = ?""",
            (search_id,),
        ).fetchone()
        if row is None:
            return None
        events = conn.execute(
            "SELECT created_at, message FROM search_events WHERE search_id = ? ORDER BY id",
            (search_id,),
        ).fetchall()
    search = _search_row(row)
    search["events"] = [dict(e) for e in events]
    return search


def list_leads(search_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, score, data FROM leads WHERE search_id = ? ORDER BY score DESC, id",
            (search_id,),
        ).fetchall()
    return [{"id": r["id"], **json.loads(r["data"]), "score": r["score"]} for r in rows]


def _search_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["profile"] = json.loads(data["profile"])
    return data
