"""
Graphic Design workspace for DERB MOBILE.

    /graphic-design                     -> choose a design type (category grid)
    /graphic-design/new?category=<slug> -> the category's own form
    POST /graphic-design/generate       -> store images, build the layout
    POST /graphic-design/save           -> save into Saved Work (doc_type DESIGN)
    /graphic-design/<id>/edit           -> reopen a saved design
    /graphic-design/<id>/preview        -> read-only poster + print/export
    POST /graphic-design/<id>/delete    -> remove from Saved Work
    /graphic-design/image/<filename>    -> a locally stored uploaded image

This is the repurposed Passport Photo slot (the old placeholder page was empty
- see docs/DECISIONS.md). It is an operator tool for fast customer service: a
ready layout the operator fills in, NOT a blank design canvas.
"""

from __future__ import annotations

import json

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    send_from_directory, url_for,
)

from core import design_catalog as catalog
from core import design_generation, design_model, design_render, design_store
from core import projects_repo, registry

bp = Blueprint("design", __name__, url_prefix="/graphic-design")

DESIGN_DOC_TYPE = "DESIGN"


def _project(project_id: int) -> dict | None:
    project = projects_repo.get_project(project_id)
    if not project or project.get("doc_type") != DESIGN_DOC_TYPE:
        return None
    return project


def _payload_of(project: dict | None) -> dict:
    if not project:
        return design_model.blank_payload()
    return design_model.normalize(project.get("raw") or {})


def _layout_json(layout: dict) -> str:
    """Layout spec with image URLs resolved, for the canvas exporter."""
    safe = json.loads(json.dumps(layout))
    for block in safe.get("blocks", []):
        for img in block.get("images", []):
            img["url"] = url_for("design.image", filename=img["filename"])
    return json.dumps(safe)


# ---------------------------------------------------------------------------
# Category chooser
# ---------------------------------------------------------------------------
@bp.route("/", strict_slashes=False)
def index():
    designs = projects_repo.list_projects(doc_type=DESIGN_DOC_TYPE, limit=6)
    recent = [
        {"project": p, "title": design_model.display_title(
            design_model.normalize(p.get("raw") or {}))}
        for p in designs
    ]
    return render_template(
        "design/index.html",
        service=registry.get_service("graphic-design"),
        categories=catalog.CATEGORIES,
        recent=recent,
        total=projects_repo.count_projects(DESIGN_DOC_TYPE),
    )


@bp.route("/new")
def new():
    category = catalog.get_category(request.args.get("category"))
    if category is None:
        return redirect(url_for("design.index"))
    return render_template(
        "design/form.html",
        service=registry.get_service("graphic-design"),
        category=category,
        categories=catalog.CATEGORIES,
        themes=catalog.THEMES,
        payload=design_model.blank_payload(category.slug),
        images=[],
        document=None,
        saved=False,
        provider=design_generation.provider_status(),
    )


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
def _images_from_form() -> list[dict[str, str]]:
    """Existing (hidden) images minus any the operator ticked to remove,
    followed by freshly uploaded files."""
    removed = set(request.form.getlist("remove_image"))
    existing = [
        {"filename": name, "role": ""}
        for name in request.form.getlist("image_filename")
        if name and name not in removed
    ]
    uploads = request.files.getlist("images")
    stored = design_store.save_uploads([u for u in uploads if u and u.filename])
    images = existing + stored
    return images[: design_model.MAX_IMAGES]


@bp.route("/generate", methods=["POST"])
def generate():
    images = _images_from_form()
    payload = design_model.parse_form(request.form, images)
    project_id = request.form.get("project_id", type=int)
    if project_id and not _project(project_id):
        project_id = None
    layout = design_generation.generate_design(payload)
    return render_template(
        "design/result.html",
        service=registry.get_service("graphic-design"),
        category=catalog.get_category(payload["category"]),
        themes=catalog.THEMES,
        payload=payload,
        layout=layout,
        layout_json=_layout_json(layout),
        document=_project(project_id) if project_id else None,
        saved=False,
        provider=design_generation.provider_status(),
    )


@bp.route("/edit", methods=["POST"])
def edit_form():
    """Return to the editor with the current (unsaved) data pre-filled."""
    images = [
        {"filename": name, "role": ""}
        for name in request.form.getlist("image_filename")
        if name
    ]
    payload = design_model.parse_form(request.form, images)
    category = catalog.get_category(payload["category"]) or catalog.CATEGORIES[0]
    project_id = request.form.get("project_id", type=int)
    return render_template(
        "design/form.html",
        service=registry.get_service("graphic-design"),
        category=category,
        categories=catalog.CATEGORIES,
        themes=catalog.THEMES,
        payload=payload,
        images=design_store.image_records(payload),
        document=_project(project_id) if project_id else None,
        saved=False,
        provider=design_generation.provider_status(),
    )


@bp.route("/save", methods=["POST"])
def save():
    images = [
        {"filename": name, "role": ""}
        for name in request.form.getlist("image_filename")
        if name
    ]
    payload = design_model.parse_form(request.form, images)
    if design_model.is_empty(payload):
        flash("Add some information before saving.", "error")
        return redirect(url_for("design.index"))
    title = design_model.display_title(payload)
    category = catalog.get_category(payload["category"])
    project_id = request.form.get("project_id", type=int)
    if project_id and not _project(project_id):
        project_id = None
    try:
        new_id = projects_repo.save_project(
            project_id, {}, f"design-{payload['category']}",
            doc_type=DESIGN_DOC_TYPE, data=payload, customer_name=title,
            title=title,
        )
    except Exception:
        current_app.logger.exception("Saving design %s failed", category)
        abort(500)
    # Image files the operator ticked to remove are deleted only once the save
    # succeeds, so a cancellation never orphans a still-referenced image.
    removed = set(request.form.getlist("remove_image"))
    if removed:
        design_store.delete_images(sorted(removed))
    flash("Design updated." if project_id else "Design saved to Saved Work.")
    return redirect(url_for("design.edit", design_id=new_id, saved=1))


# ---------------------------------------------------------------------------
# Existing designs
# ---------------------------------------------------------------------------
@bp.route("/<int:design_id>/edit")
def edit(design_id: int):
    project = _project(design_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    category = catalog.get_category(payload["category"]) or catalog.CATEGORIES[0]
    return render_template(
        "design/form.html",
        service=registry.get_service("graphic-design"),
        category=category,
        categories=catalog.CATEGORIES,
        themes=catalog.THEMES,
        payload=payload,
        images=design_store.image_records(payload),
        document=project,
        saved=request.args.get("saved") == "1",
        provider=design_generation.provider_status(),
    )


@bp.route("/<int:design_id>/preview")
def preview(design_id: int):
    project = _project(design_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    layout = design_generation.generate_design(payload)
    return render_template(
        "design/result.html",
        service=registry.get_service("graphic-design"),
        category=catalog.get_category(payload["category"]),
        themes=catalog.THEMES,
        payload=payload,
        layout=layout,
        layout_json=_layout_json(layout),
        document=project,
        saved=True,
        provider=design_generation.provider_status(),
    )


@bp.route("/<int:design_id>/delete", methods=["POST"])
def delete(design_id: int):
    project = _project(design_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    design_store.delete_images([img["filename"] for img in payload.get("images") or []])
    projects_repo.delete_project(design_id)
    flash("Design deleted.")
    return redirect(url_for("saved.index"))


# ---------------------------------------------------------------------------
# Uploaded images
# ---------------------------------------------------------------------------
@bp.route("/image/<path:filename>")
def image(filename: str):
    if not design_store.is_safe_name(filename):
        abort(404)
    return send_from_directory(design_store.ensure_dir(), filename)
