"""
Project repository.

Saved CVs live in the existing `projects` table - the CV dict is serialised
into the `data` column as JSON. No extra database, no schema changes.
"""

from __future__ import annotations

import json
from typing import Any

from core import cv_model, db, paths, templates_repo


def count_projects(doc_type: str | None = None) -> int:
    if doc_type:
        row = db.query_one(
            "SELECT COUNT(*) AS c FROM projects WHERE doc_type = ?", (doc_type,)
        )
    else:
        row = db.query_one("SELECT COUNT(*) AS c FROM projects")
    return int(row["c"]) if row else 0


def recent_projects(limit: int = 5) -> list[dict[str, Any]]:
    return list_projects(limit=limit)


def create_project(cv: dict[str, Any], template_slug: str,
                   doc_type: str = "CV", data: dict[str, Any] | None = None,
                   customer_name: str | None = None,
                   title: str | None = None) -> int:
    """Create a project row.

    CV projects pass the CV dict; other document types (letters) pass their
    own `data` payload and display fields, reusing the same table.
    """
    now = paths.stamp()
    if doc_type == "CV" and data is None:
        cv = cv_model.normalize(cv)
        payload = cv
        customer_name = customer_name or cv_model.display_name(cv)
        title = title or cv_model.project_title(cv)
    else:
        payload = data if data is not None else cv
    return db.execute(
        """
        INSERT INTO projects
            (customer_name, doc_type, template_slug, title, status, data,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, 'saved', ?, ?, ?)
        """,
        (
            customer_name or "Untitled",
            doc_type,
            template_slug,
            title or customer_name or "Untitled",
            json.dumps(payload),
            now,
            now,
        ),
    )


def update_project(project_id: int, cv: dict[str, Any], template_slug: str,
                   doc_type: str = "CV", data: dict[str, Any] | None = None,
                   customer_name: str | None = None,
                   title: str | None = None) -> None:
    if doc_type == "CV" and data is None:
        cv = cv_model.normalize(cv)
        payload = cv
        customer_name = customer_name or cv_model.display_name(cv)
        title = title or cv_model.project_title(cv)
    else:
        payload = data if data is not None else cv
    db.execute(
        """
        UPDATE projects
        SET customer_name = ?, template_slug = ?, title = ?, data = ?,
            status = 'saved', updated_at = ?
        WHERE id = ?
        """,
        (
            customer_name or "Untitled",
            template_slug,
            title or customer_name or "Untitled",
            json.dumps(payload),
            paths.stamp(),
            project_id,
        ),
    )


def save_project(project_id: int | None, cv: dict[str, Any], template_slug: str,
                 doc_type: str = "CV", data: dict[str, Any] | None = None,
                 customer_name: str | None = None,
                 title: str | None = None) -> int:
    """Create or update in one call; returns the project id."""
    if project_id:
        update_project(project_id, cv, template_slug, doc_type=doc_type,
                       data=data, customer_name=customer_name, title=title)
        return project_id
    return create_project(cv, template_slug, doc_type=doc_type, data=data,
                          customer_name=customer_name, title=title)


def get_project(project_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    return _decode(row) if row else None


def list_projects(query: str | None = None, limit: int = 100,
                  doc_type: str | None = None) -> list[dict[str, Any]]:
    """Newest first, optionally filtered by customer name and document type."""
    where, params = [], []
    if doc_type:
        where.append("doc_type = ?")
        params.append(doc_type)
    if query:
        where.append("(customer_name LIKE ? COLLATE NOCASE OR title LIKE ? COLLATE NOCASE)")
        params.extend((f"%{query}%", f"%{query}%"))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.query(
        f"""
        SELECT * FROM projects
        {clause}
        ORDER BY datetime(updated_at) DESC, id DESC
        LIMIT ?
        """,
        (*params, limit),
    )
    return [_decode(r) for r in rows]


def delete_project(project_id: int) -> None:
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def duplicate_project(project_id: int) -> int | None:
    original = get_project(project_id)
    if not original:
        return None
    if original.get("doc_type") == "CV":
        cv = original["cv"]
        cv["personal"]["full_name"] = (
            (cv["personal"].get("full_name") or "Untitled Customer") + " (Copy)"
        )
        return create_project(cv, original["template_slug"])
    # Letters and other document types: copy the raw payload and rename.
    name = (original.get("customer_name") or "Untitled") + " (Copy)"
    return create_project({}, original["template_slug"], doc_type=original["doc_type"],
                          data=original.get("raw") or {}, customer_name=name,
                          title=(original.get("title") or name) + " (Copy)")


def template_for(project: dict[str, Any]) -> dict[str, Any]:
    """Template row for a project, falling back to the default template."""
    found = templates_repo.get_template(project.get("template_slug") or "")
    return found or templates_repo.get_default_template("CV")


def _decode(row) -> dict[str, Any]:
    item = dict(row)
    try:
        raw = json.loads(item.get("data") or "{}")
    except (TypeError, ValueError):
        raw = {}
    item["raw"] = raw
    item["cv"] = cv_model.normalize(raw)
    item["template_slug"] = item.get("template_slug") or "professional-cv"
    return item
