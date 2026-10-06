"""
CV / Resume workflow.

    /cv                      -> choose a template
    /cv/new?template=<slug>  -> editor (new customer)
    /cv/<id>/edit            -> editor (existing project)
    POST /cv/preview         -> preview the form data without saving
    /cv/<id>/preview         -> preview a saved project
    POST /cv/save            -> save project, returns to the editor
    POST /cv/<id>/duplicate  -> copy a project
    POST /cv/<id>/delete     -> remove a project
    POST /cv/<id>/export/pdf -> export to PDF (DERB/CV/PDF + download)
    POST /cv/<id>/export/docx-> export to Word (DERB/CV/DOCX + download)
    /cv/photo/<filename>     -> locally stored passport photograph
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    send_file, send_from_directory, url_for,
)

import config
from core import cv_docx, cv_model, cv_pdf, cv_render, projects_repo, registry, templates_repo

bp = Blueprint("cv", __name__, url_prefix="/cv")

_SAFE_FILE = re.compile(r"^[A-Za-z0-9._-]+$")


@bp.route("/", strict_slashes=False)
def templates():
    """Phase 3: the CV template selection page."""
    service = registry.get_service("cv")
    cv_templates = templates_repo.list_templates("CV")
    default_slug = templates_repo.get_setting(templates_repo.DEFAULT_TEMPLATE_KEY)
    # A small, complete sample so each card shows the real layout.
    sample = cv_model.sample_cv()
    cards = [
        {
            "template": tpl,
            "sheet": cv_render.render_sheet(sample, tpl),
            "is_default": tpl["slug"] == default_slug,
        }
        for tpl in cv_templates
    ]
    return render_template(
        "cv/templates.html",
        service=service,
        cards=cards,
        project_count=projects_repo.count_projects("CV"),
    )


@bp.route("/new")
def new():
    slug = request.args.get("template") or templates_repo.get_setting(
        templates_repo.DEFAULT_TEMPLATE_KEY
    )
    template = templates_repo.get_template(slug) or templates_repo.get_default_template("CV")
    cv = cv_model.blank_cv()
    return render_template(
        "cv/editor.html",
        cv=cv,
        template=template,
        cv_templates=templates_repo.list_templates("CV"),
        scalar_sections=cv_model.SCALAR_SECTIONS,
        repeatable_sections=cv_model.REPEATABLE_SECTIONS,
        project=None,
        saved=False,
    )


@bp.route("/<int:project_id>/edit")
def edit(project_id: int):
    project = projects_repo.get_project(project_id)
    if not project:
        abort(404)
    template = projects_repo.template_for(project)
    return render_template(
        "cv/editor.html",
        cv=project["cv"],
        template=template,
        cv_templates=templates_repo.list_templates("CV"),
        scalar_sections=cv_model.SCALAR_SECTIONS,
        repeatable_sections=cv_model.REPEATABLE_SECTIONS,
        project=project,
        saved=request.args.get("saved") == "1",
    )


@bp.route("/save", methods=["POST"])
def save():
    cv = _cv_from_request()
    if not cv["personal"].get("full_name"):
        flash("Please enter the customer's full name before saving.", "error")
        return redirect(url_for("cv.new", template=request.form.get("template_slug")))

    template_slug = request.form.get("template_slug") or "professional-cv"
    project_id = request.form.get("project_id", type=int)
    new_id = projects_repo.save_project(project_id, cv, template_slug)
    flash("Project saved." if project_id else "Project saved to Saved Work.", "ok")
    return redirect(url_for("cv.edit", project_id=new_id, saved=1))


@bp.route("/preview", methods=["POST"])
def preview_form():
    """Preview the data currently in the editor, saved or not."""
    cv = _cv_from_request()
    template = templates_repo.get_template(
        request.form.get("template_slug") or ""
    ) or templates_repo.get_default_template("CV")
    sheet = cv_render.render_sheet(cv, template)
    return render_template(
        "cv/preview.html",
        cv=cv,
        template=template,
        sheet=sheet,
        project_id=request.form.get("project_id", type=int),
        back_url=url_for("cv.new", template=template["slug"]),
        heading="Preview - not saved yet",
    )


@bp.route("/<int:project_id>/preview")
def preview(project_id: int):
    project = projects_repo.get_project(project_id)
    if not project:
        abort(404)
    template = projects_repo.template_for(project)
    sheet = cv_render.render_sheet(project["cv"], template)
    return render_template(
        "cv/preview.html",
        cv=project["cv"],
        template=template,
        sheet=sheet,
        project_id=project_id,
        back_url=url_for("cv.edit", project_id=project_id),
        heading=project["title"],
    )


@bp.route("/<int:project_id>/duplicate", methods=["POST"])
def duplicate(project_id: int):
    new_id = projects_repo.duplicate_project(project_id)
    if not new_id:
        abort(404)
    flash("Project duplicated.", "ok")
    return redirect(url_for("saved.index"))


@bp.route("/<int:project_id>/delete", methods=["POST"])
def delete(project_id: int):
    projects_repo.delete_project(project_id)
    flash("Project deleted.", "ok")
    return redirect(url_for("saved.index"))


@bp.route("/<int:project_id>/export/pdf", methods=["POST"])
def export_pdf(project_id: int):
    """Phase 4: render the saved CV to PDF and hand it to the browser."""
    project = projects_repo.get_project(project_id)
    if not project:
        abort(404)
    try:
        path = cv_pdf.export_pdf(project["cv"], projects_repo.template_for(project))
    except Exception:
        current_app.logger.exception("PDF export failed for project %s", project_id)
        abort(500)
    flash(f"PDF saved to {path}.", "ok")
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=path.name,
    )


@bp.route("/<int:project_id>/export/docx", methods=["POST"])
def export_docx(project_id: int):
    """Phase 4: render the saved CV to an editable Word document."""
    project = projects_repo.get_project(project_id)
    if not project:
        abort(404)
    try:
        path = cv_docx.export_docx(project["cv"], projects_repo.template_for(project))
    except Exception:
        current_app.logger.exception("DOCX export failed for project %s", project_id)
        abort(500)
    flash(f"Word document saved to {path}.", "ok")
    return send_file(
        path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=path.name,
    )


@bp.route("/photo/<path:filename>")
def photo(filename: str):
    if not _SAFE_FILE.match(filename):
        abort(404)
    return send_from_directory(config.PHOTOS_DIR, filename)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _cv_from_request() -> dict:
    cv = cv_model.parse_form(request.form)
    cv["photo"] = _handle_photo(request) or request.form.get("existing_photo", "")
    return cv


def _handle_photo(req) -> str:
    """Store an uploaded passport photograph locally. Returns its filename."""
    upload = req.files.get("photo")
    if not upload or not upload.filename:
        return ""
    ext = Path(upload.filename).suffix.lower()
    if ext not in config.ALLOWED_PHOTO_EXT:
        return ""
    config.PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"photo_{secrets.token_hex(8)}{ext}"
    upload.save(config.PHOTOS_DIR / name)
    return name
