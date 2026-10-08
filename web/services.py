"""
Service routes.

Every dashboard tile resolves to a route here. Services that are built render
their real screen; the rest render a branded "Coming Soon" placeholder that
states which phase will deliver them. Nothing is faked: a placeholder clearly
says so.
"""

from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, url_for

# Imported under an alias: the route below is also called official_services(),
# so a plain import would be shadowed by the view function.
from core import official_services as official_catalog
from core import registry

# NOTE: /cv, /saved and /letters are implemented by their own blueprints.
# /documents lives in web/documents.py (free-format editor, Phase 7).

bp = Blueprint("services", __name__)


def _render(slug: str):
    service = registry.get_service(slug)
    if service is None:
        abort(404)
    if not service.is_ready:
        return render_template("pages/coming_soon.html", service=service)
    return render_template("pages/service_ready.html", service=service)


# ---------------------------------------------------------------------------
# Placeholder services (Coming Soon until their phase)
# ---------------------------------------------------------------------------
@bp.route("/school")
def school():
    return _render("school")


@bp.route("/business")
def business():
    return _render("business")


# The old Passport Photo placeholder is now the Graphic Design workspace.
# Keep the old URL working (nothing links to a dead route), but there is only
# ONE workspace: /graphic-design. See docs/DECISIONS.md.
@bp.route("/passport")
def passport():
    return redirect(url_for("design.index"), code=302)


@bp.route("/templates")
def templates():
    return _render("templates")


@bp.route("/settings")
def settings():
    return _render("settings")


@bp.route("/official-services")
def official_services():
    """Government / Nigeria Police services DERB assists customers with.

    The catalog (names, descriptions and verified portal links) lives in
    core/official_services.py so the page, the cards and the tests share
    one source of truth.
    """
    return render_template(
        "pages/official_services.html",
        featured_services=official_catalog.FEATURED_OFFICIAL_SERVICES,
        all_services=official_catalog.OFFICIAL_SERVICES,
        verified_on=official_catalog.VERIFIED_ON,
        source_note=official_catalog.SOURCE_NOTE,
    )
