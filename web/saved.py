"""
Saved Work screen.

Lists saved CVs and free-format Documents side by side (newest first),
supports search by name/title, and exposes the open / duplicate / export /
delete actions. Letters keep their own Saved Letters screen on purpose:
they are template documents with their own preview and export flow.
"""

from __future__ import annotations

from flask import Blueprint, render_template, request

from core import cv_model, doc_model, projects_repo, registry, templates_repo

bp = Blueprint("saved", __name__, url_prefix="/saved")


@bp.route("/", strict_slashes=False)
def index():
    query = (request.args.get("q") or "").strip()
    projects = projects_repo.list_projects(query or None, doc_type="CV")
    documents = projects_repo.list_projects(query or None, doc_type="DOCUMENT")

    items = []
    for project in projects:
        template = projects_repo.template_for(project)
        cv = project["cv"]
        items.append(
            {
                "project": project,
                "template": template,
                "initials": cv_model.initials(cv_model.display_name(cv)),
                "counts": cv_model.filled_summary(cv),
                "has_photo": bool(cv.get("photo")),
                "is_document": False,
            }
        )

    # Free-format Documents: same storage table, doc_type='DOCUMENT'.
    for project in documents:
        payload = doc_model.normalize(project.get("raw") or {})
        title = doc_model.display_title(payload)
        items.append(
            {
                "project": project,
                "template": {"name": "Free-format", "accent": "#0ea5e9",
                             "layout": "document"},
                "initials": cv_model.initials(title),
                "counts": doc_model.filled_summary(payload),
                "has_photo": False,
                "is_document": True,
                "doc_payload": payload,
            }
        )

    items.sort(key=lambda it: (it["project"].get("updated_at") or ""), reverse=True)

    return render_template(
        "pages/saved.html",
        service=registry.get_service("saved"),
        items=items,
        query=query,
        total=projects_repo.count_projects("CV")
        + projects_repo.count_projects("DOCUMENT"),
    )
