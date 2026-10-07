"""
Documents workflow - the free-format screen.

    /documents            -> editor, blank (Empty state on first open)
    /documents/<id>/edit  -> editor with a saved document
    POST /documents/save  -> save (new or update), reuse the projects table
    /documents/<id>/preview -> read-only A4 sheet + Print button
    POST /documents/<id>/delete -> remove from Saved Documents
    POST /documents/<id>/export/pdf | /export/docx -> same Phase 4 engines
                                  (letters and CVs use), files in DERB/Documents/

This is intentionally NOT part of the Letters workflow: Letters are
structured template documents; a Document here is whatever the customer
brought to be typed (speech, essay, minutes...). Sharing happens through
the same `projects` table (doc_type='DOCUMENT'), the same flash messages
and the same export engines - so Saved Work lists and exports all work the
same way without duplicating storage paths.
"""

from __future__ import annotations

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    send_file, url_for,
)

from core import doc_docx, doc_model, doc_pdf, projects_repo, registry

# Data-model module reused for sizes; import keeps the mapping in one place.
SIZE_PT = doc_model.SIZE_PT

bp = Blueprint("documents", __name__, url_prefix="/documents")


def _project(project_id: int) -> dict | None:
    project = projects_repo.get_project(project_id)
    if not project or project.get("doc_type") != "DOCUMENT":
        return None
    return project


def _payload_of(project: dict | None) -> dict:
    """Normalized payload from a saved row (or a blank one)."""
    if not project:
        return doc_model.blank_payload()
    return doc_model.normalize(project.get("raw") or {})


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------
@bp.route("/", strict_slashes=False)
def new():
    return render_template(
        "documents/editor.html",
        payload=doc_model.blank_payload(),
        document=None,
        saved=False,
        service=registry.get_service("documents"),
    )


@bp.route("/<int:document_id>/edit")
def edit(document_id: int):
    project = _project(document_id)
    if not project:
        abort(404)
    return render_template(
        "documents/editor.html",
        payload=_payload_of(project),
        document=project,
        saved=request.args.get("saved") == "1",
        service=registry.get_service("documents"),
    )


@bp.route("/save", methods=["POST"])
def save():
    payload = doc_model.parse_form(request.form)
    # Sanitise the typed text against stray markup (the editor normally
    # submits plain text; this guards copy-pasted HTML and stored replay).
    payload = doc_model.adjust(payload, **{
        "size": payload["size"],
        "align": payload["align"],
    })
    payload["body_text"] = doc_model.plain(payload["body_text"])
    if doc_model.is_empty(payload):
        flash("Type some content before saving.", "error")
        return redirect(url_for("documents.new"))
    title = doc_model.display_title(payload)
    project_id = request.form.get("project_id", type=int)
    if project_id and not _project(project_id):
        project_id = None  # never let the form rename another doc type's row
    new_id = projects_repo.save_project(
        project_id, {}, "free-format", doc_type="DOCUMENT",
        data=payload, customer_name=title, title=title,
    )
    flash("Document updated." if project_id else "Document saved to Saved Documents.")
    return redirect(url_for("documents.edit", document_id=new_id, saved=1))


@bp.route("/<int:document_id>/preview")
def preview(document_id: int):
    project = _project(document_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    size_pt = SIZE_PT[int(payload.get("size") or doc_model.DEFAULT_SIZE)]
    return render_template(
        "documents/preview.html",
        payload=payload,
        document=project,
        title_text=doc_model.display_title(payload),
        size_pt=size_pt,
    )


@bp.route("/<int:document_id>/delete", methods=["POST"])
def delete(document_id: int):
    project = _project(document_id)
    if not project:
        abort(404)
    projects_repo.delete_project(document_id)
    flash("Document deleted.")
    return redirect(url_for("saved.index"))


# ---------------------------------------------------------------------------
# Exports - reuse the Phase 4 engines, files under DERB/Documents/
# ---------------------------------------------------------------------------
@bp.route("/<int:document_id>/export/pdf", methods=["POST"])
def export_pdf(document_id: int):
    project = _project(document_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    title = doc_model.display_title(payload)
    try:
        path = doc_pdf.export_document_pdf(payload, title)
    except Exception:
        current_app.logger.exception("Document PDF export failed for %s", document_id)
        abort(500)
    flash(f"PDF saved to {path}.")
    return send_file(path, mimetype="application/pdf", as_attachment=True,
                     download_name=path.name)


@bp.route("/<int:document_id>/export/docx", methods=["POST"])
def export_docx(document_id: int):
    project = _project(document_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    title = doc_model.display_title(payload)
    try:
        path = doc_docx.export_document_docx(payload, title)
    except Exception:
        current_app.logger.exception("Document DOCX export failed for %s", document_id)
        abort(500)
    flash(f"Word document saved to {path}.")
    return send_file(
        path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=path.name,
    )
