"""One SQLite file for everything the app keeps: runs, safety events, the
faculty directory sample and a cache of public-API responses.

Created on first start from the files in data/, so a fresh clone needs no setup.
"""
from __future__ import annotations

import csv
import gzip
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DATA

DB_PATH = DATA / "warmpath.db"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    company     TEXT NOT NULL,
    goal        TEXT NOT NULL,
    web         INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL,
    result      TEXT NOT NULL DEFAULT '{}',
    trace       TEXT NOT NULL DEFAULT '[]',
    usage       TEXT NOT NULL DEFAULT '{}',
    cost_usd    REAL NOT NULL DEFAULT 0,
    duration_s  REAL NOT NULL DEFAULT 0,
    example     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS safety_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    created_at  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    detail      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS http_cache (
    key         TEXT PRIMARY KEY,
    body        TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS faculty (
    id TEXT PRIMARY KEY, name TEXT, title TEXT, departments TEXT,
    research TEXT, email TEXT, profile_url TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS faculty_fts USING fts5(
    name, title, departments, research, content='faculty', content_rowid='rowid'
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init() -> None:
    DATA.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0] == 0:
            with gzip.open(DATA / "faculty.csv.gz", "rt", encoding="utf-8") as f:
                rows = [(r["id"], r["name"], r["title"], r["departments"], r["research"],
                         r["email"], r["profile_url"]) for r in csv.DictReader(f)]
            conn.executemany("INSERT INTO faculty VALUES (?,?,?,?,?,?,?)", rows)
            conn.execute("INSERT INTO faculty_fts(faculty_fts) VALUES ('rebuild')")
        if conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0:
            examples = DATA / "example_runs.json"
            if examples.is_file():
                for run in json.loads(examples.read_text(encoding="utf-8")):
                    conn.execute(
                        "INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,1)",
                        (run["id"], run["created_at"], run["company"], run["goal"], run["web"],
                         run["status"], json.dumps(run["result"]), json.dumps(run["trace"]),
                         json.dumps(run["usage"]), run["cost_usd"], run["duration_s"]))


# --- Runs --------------------------------------------------------------------------

def save_run(run: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (run["id"], run["created_at"], run["company"], run["goal"], int(run["web"]),
             run["status"], json.dumps(run.get("result") or {}), json.dumps(run.get("trace") or []),
             json.dumps(run.get("usage") or {}), run.get("cost_usd", 0.0),
             run.get("duration_s", 0.0), int(run.get("example", 0))))


def _run_dict(row) -> dict:
    d = dict(row)
    for k in ("result", "trace", "usage"):
        d[k] = json.loads(d[k])
    d["web"] = bool(d["web"])
    d["example"] = bool(d["example"])
    return d


def get_run(run_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _run_dict(row) if row else None


def list_runs(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, company, goal, web, status, cost_usd, duration_s, example, usage "
            "FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["usage"] = json.loads(d["usage"])
        d["web"], d["example"] = bool(d["web"]), bool(d["example"])
        out.append(d)
    return out


def spent_today() -> float:
    """Dollars spent by live (non-example) runs since midnight UTC."""
    today = datetime.now(timezone.utc).date().isoformat()
    with connect() as conn:
        row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM runs "
                           "WHERE example = 0 AND created_at >= ?", (today,)).fetchone()
    return float(row[0])


# --- Safety events -------------------------------------------------------------------

def log_safety(run_id: str | None, kind: str, detail: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO safety_events (run_id, created_at, kind, detail) VALUES (?,?,?,?)",
                     (run_id, now(), kind, detail[:1000]))


def safety_events(limit: int = 100) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM safety_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


# --- Faculty directory ------------------------------------------------------------------

def faculty_search(query: str, limit: int = 8) -> list[dict]:
    words = [w for w in "".join(c if c.isalnum() else " " for c in query).split() if len(w) > 1]
    # "Formica RN", "Forrest JK": PubMed-style initials would never match a full name.
    words = [w for w in words if not (w.isupper() and len(w) <= 3)] or words
    if not words:
        return []
    match = " ".join(f'"{w}"' for w in words)
    with connect() as conn:
        rows = conn.execute(
            "SELECT f.* FROM faculty_fts JOIN faculty f ON f.rowid = faculty_fts.rowid "
            "WHERE faculty_fts MATCH ? ORDER BY bm25(faculty_fts, 10.0, 3.0, 1.0, 1.0) LIMIT ?",
            (match, limit)).fetchall()
    return [dict(r) for r in rows]


# --- HTTP cache -------------------------------------------------------------------------

def cache_get(key: str, max_age_days: int = 7) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT body, fetched_at FROM http_cache WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    age = datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])
    return row["body"] if age.days < max_age_days else None


def cache_put(key: str, body: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO http_cache VALUES (?,?,?)", (key, body, now()))
