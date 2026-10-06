"""
Saved Work screen.

Lists saved projects, supports search by customer name, and exposes the
open / duplicate / export / delete actions.
"""

from __future__ import annotations

from flask import Blueprint, render_template, request

from core import cv_model, projects_repo, registry, templates_repo

bp = Blueprint("saved", __name__, url_prefix="/saved")


@bp.route("/", strict_slashes=False)
def index():
    query = (request.args.get("q") or "").strip()
    # Saved Work lists CV projects; letters have their own Saved Letters screen.
    projects = projects_repo.list_projects(query or None, doc_type="CV")

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
            }
        )

    return render_template(
        "pages/saved.html",
        service=registry.get_service("saved"),
        items=items,
        query=query,
        total=projects_repo.count_projects("CV"),
    )
