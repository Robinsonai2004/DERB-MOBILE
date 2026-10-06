"""
Template repository.

Wraps the `templates` table so the rest of the app never writes SQL directly.
This is the seam that the Template Manager (Phase 10) will grow into.
"""

from __future__ import annotations

import json
from typing import Any

from core import db, paths

DEFAULT_TEMPLATE_KEY = "default_cv_template"


def list_templates(category: str = "CV") -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM templates WHERE category = ? ORDER BY sort_order, name",
        (category,),
    )
    return [_row_to_dict(r) for r in rows]


def get_template(slug: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM templates WHERE slug = ?", (slug,))
    return _row_to_dict(row) if row else None


def get_default_template(category: str = "CV") -> dict[str, Any]:
    slug = get_setting(DEFAULT_TEMPLATE_KEY)
    if slug:
        found = get_template(slug)
        if found:
            return found
    row = db.query_one(
        "SELECT * FROM templates WHERE category = ? ORDER BY is_default DESC, sort_order LIMIT 1",
        (category,),
    )
    if row:
        return _row_to_dict(row)
    # Should never happen after seeding, but stay defensive.
    return {
        "slug": "professional-cv",
        "name": "Professional CV",
        "accent": "#123a72",
        "layout": "professional",
        "config": {},
    }


def set_default_template(slug: str) -> None:
    set_setting(DEFAULT_TEMPLATE_KEY, slug)


def count_templates(category: str = "CV") -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS c FROM templates WHERE category = ?", (category,)
    )
    return int(row["c"]) if row else 0


# --------------------------------------------------------------------------
# Settings helpers
# --------------------------------------------------------------------------
def get_setting(key: str, default: str | None = None) -> str | None:
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    db.execute(
        """
        INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, paths.stamp()),
    )


def ensure_default_setting() -> None:
    if not get_setting(DEFAULT_TEMPLATE_KEY):
        set_setting(DEFAULT_TEMPLATE_KEY, "professional-cv")


def _row_to_dict(row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["config"] = json.loads(item.get("config") or "{}")
    except (TypeError, ValueError):
        item["config"] = {}
    item["is_builtin"] = bool(item.get("is_builtin"))
    item["is_default"] = bool(item.get("is_default"))
    return item
