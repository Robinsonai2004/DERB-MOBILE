"""
Home screen (dashboard) routes.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template

import config
from core import db, paths, projects_repo, registry, templates_repo

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def home():
    counts = db.stats()
    return render_template(
        "pages/dashboard.html",
        services=registry.SERVICES,
        stats=counts,
        recent=projects_repo.recent_projects(limit=3),
        letters_count=projects_repo.count_projects("LETTER"),
    )


@bp.route("/about")
def about():
    return render_template("pages/about.html", services=registry.SERVICES)


@bp.route("/health")
def health():
    """Lightweight readiness probe used by the start script and tests."""
    counts = db.stats()
    return jsonify(
        {
            "app": config.BRAND_PRODUCT,
            "version": config.BRAND_VERSION,
            "phase": config.BRAND_PHASE,
            "database": str(config.DB_PATH),
            "database_ok": config.DB_PATH.exists(),
            "documents_root": str(paths.DERB_ROOT),
            "projects": counts["projects"],
            "templates": counts["templates"],
            "default_template": templates_repo.get_setting(
                templates_repo.DEFAULT_TEMPLATE_KEY
            ),
            "offline": True,
        }
    )
