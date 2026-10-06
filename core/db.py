"""
SQLite storage for DERB MOBILE.

Kept deliberately small and dependency-free (standard-library sqlite3) so it
runs comfortably on a low-spec Android phone.

Tables
------
projects   saved customer documents (CVs today, other services later)
templates  CV/document templates (built-in + user copies)
settings   simple key/value store (e.g. default template)
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from config import DB_PATH
from core import paths

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT    NOT NULL DEFAULT '',
    doc_type      TEXT    NOT NULL DEFAULT 'CV',
    template_slug TEXT    NOT NULL DEFAULT 'professional-cv',
    title         TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'draft',
    data          TEXT    NOT NULL DEFAULT '{}',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_customer
    ON projects (customer_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_projects_doc_type ON projects (doc_type);

CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'CV',
    description TEXT    NOT NULL DEFAULT '',
    accent      TEXT    NOT NULL DEFAULT '#123a72',
    layout      TEXT    NOT NULL DEFAULT 'professional',
    is_builtin  INTEGER NOT NULL DEFAULT 0,
    is_default  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 100,
    config      TEXT    NOT NULL DEFAULT '{}',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# The three starter CV templates required for VERSION 1.
BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": "professional-cv",
        "name": "Professional CV",
        "category": "CV",
        "description": "Classic navy header with clear section rules. Trusted look for "
                       "banks, oil & gas and government applications.",
        "accent": "#123a72",
        "layout": "professional",
        "is_default": 1,
        "sort_order": 10,
        "config": {
            "header_style": "bar",
            "photo": "optional",
            "show_references": True,
            "font": "helvetica",
        },
    },
    {
        "slug": "modern-cv",
        "name": "Modern CV",
        "category": "CV",
        "description": "Two-tone accent sidebar with bold name treatment. Suited to "
                       "tech, media and private-sector roles.",
        "accent": "#0f766e",
        "layout": "modern",
        "is_default": 0,
        "sort_order": 20,
        "config": {
            "header_style": "sidebar",
            "photo": "optional",
            "show_references": True,
            "font": "helvetica",
        },
    },
    {
        "slug": "simple-cv",
        "name": "Simple CV",
        "category": "CV",
        "description": "Clean black-and-white single column. Prints perfectly on any "
                       "printer and reads well when photocopied.",
        "accent": "#111827",
        "layout": "simple",
        "is_default": 0,
        "sort_order": 30,
        "config": {
            "header_style": "plain",
            "photo": "hidden",
            "show_references": True,
            "font": "times",
        },
    },
]


def connect() -> sqlite3.Connection:
    """Open a connection tuned for small local use."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    """Create tables, document tree and starter templates."""
    paths.ensure_tree()
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        if seed:
            _seed_templates(conn)
    if seed:
        from core.templates_repo import ensure_default_setting

        ensure_default_setting()


def _seed_templates(conn: sqlite3.Connection) -> None:
    now = paths.stamp()
    for item in BUILTIN_TEMPLATES:
        conn.execute(
            """
            INSERT INTO templates
                (slug, name, category, description, accent, layout,
                 is_builtin, is_default, sort_order, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                accent=excluded.accent,
                layout=excluded.layout,
                sort_order=excluded.sort_order,
                config=excluded.config,
                updated_at=excluded.updated_at
            """,
            (
                item["slug"],
                item["name"],
                item["category"],
                item["description"],
                item["accent"],
                item["layout"],
                item["is_default"],
                item["sort_order"],
                json.dumps(item["config"]),
                now,
                now,
            ),
        )


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    """Run a write statement and return lastrowid."""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def stats() -> dict[str, int]:
    """Small counters used by the dashboard."""
    out: dict[str, int] = {}
    with get_conn() as conn:
        out["projects"] = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        out["templates"] = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    return out
