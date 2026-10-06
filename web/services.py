"""
Service routes.

Every dashboard tile resolves to a route here. Services that are built render
their real screen; the rest render a branded "Coming Soon" placeholder that
states which phase will deliver them. Nothing is faked: a placeholder clearly
says so.
"""

from __future__ import annotations

from flask import Blueprint, abort, render_template

from core import registry

# NOTE: /cv, /saved and /letters are implemented by their own blueprints.

bp = Blueprint("services", __name__)


def _render(slug: str):
    service = registry.get_service(slug)
    if service is None:
        abort(404)
    if not service.is_ready:
        return render_template("pages/coming_soon.html", service=service)
    return render_template("pages/service_ready.html", service=service)


@bp.route("/documents")
def documents():
    return _render("documents")


@bp.route("/school")
def school():
    return _render("school")


@bp.route("/business")
def business():
    return _render("business")


@bp.route("/passport")
def passport():
    return _render("passport")


@bp.route("/templates")
def templates():
    return _render("templates")


@bp.route("/settings")
def settings():
    return _render("settings")
