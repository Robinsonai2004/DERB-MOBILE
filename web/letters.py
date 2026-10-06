"""
Letters / Documents workflow.

    /letters                    -> document type selection (search + categories)
    /letters/saved              -> Saved Letters list
    /letters/new?doc=<slug>     -> document-specific form
    POST /letters/preview       -> preview unsaved form data
    POST /letters/save          -> save letter, returns to the editor
    /letters/<id>/edit          -> edit a saved letter
    /letters/<id>/preview       -> preview a saved letter
    POST /letters/<id>/duplicate | /delete -> list actions
    POST /letters/<id>/export/pdf | /export/docx -> Phase 4 export engines

The document type catalog lives in core/letters_catalog.py; the composed
document structure in core/letter_model.py; the renderers in
core/letter_render.py, core/letter_pdf.py and core/letter_docx.py.
Storage reuses the existing `projects` table with doc_type='LETTER'.
"""

from __future__ import annotations

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    send_file, url_for,
)

from core import (
    letter_docx, letter_model, letter_pdf, letters_catalog, projects_repo,
    registry,
)

bp = Blueprint("letters", __name__, url_prefix="/letters")

LETTER_TEMPLATES = [
    {"slug": "professional", "name": "Professional", "accent": "#123a72",
     "layout": "professional",
     "desc": "Formal business appearance with navy accents."},
    {"slug": "modern", "name": "Modern", "accent": "#0f766e",
     "layout": "modern",
     "desc": "Contemporary design with subtle teal accents."},
    {"slug": "simple", "name": "Simple", "accent": "#111827",
     "layout": "simple",
     "desc": "Black and white, printer-friendly, minimal."},
]
LETTER_TEMPLATES_BY_SLUG = {t["slug"]: t for t in LETTER_TEMPLATES}


def _template(slug: str | None) -> dict:
    return LETTER_TEMPLATES_BY_SLUG.get(slug or "", LETTER_TEMPLATES[0])


def _doc_or_404() -> dict:
    doc = letters_catalog.get_doc(request.values.get("doc", ""))
    if doc is None:
        abort(404)
    return doc


def _letter_project(project_id: int) -> dict | None:
    project = projects_repo.get_project(project_id)
    if not project or project.get("doc_type") != "LETTER":
        return None
    return project


def _compose(fields: dict, doc: dict, template_slug: str) -> dict:
    template = _template(template_slug)
    return letter_model.build_document(doc, fields, template)


# ---------------------------------------------------------------------------
# Landing: document type selection
# ---------------------------------------------------------------------------
@bp.route("/", strict_slashes=False)
def index():
    query = (request.args.get("q") or "").strip()
    service = registry.get_service("letters")
    letters_count = projects_repo.count_projects("LETTER")

    if query:
        matches = letters_catalog.search_docs(query)
        categories = []
        for cat in letters_catalog.CATEGORIES:
            docs = [d for d in matches if d["category"] == cat["slug"]]
            if docs:
                categories.append({"cat": cat, "docs": docs, "expanded": True})
    else:
        categories = [
            {"cat": cat, "docs": letters_catalog.DOCS_BY_CATEGORY.get(cat["slug"], []),
             "expanded": False}
            for cat in letters_catalog.CATEGORIES
        ]
    return render_template(
        "letters/landing.html",
        service=service,
        categories=categories,
        query=query,
        total_types=len(letters_catalog.DOC_TYPES),
        letters_count=letters_count,
    )


@bp.route("/saved", strict_slashes=False)
def saved():
    query = (request.args.get("q") or "").strip()
    projects = projects_repo.list_projects(query or None, doc_type="LETTER")
    items = []
    for project in projects:
        payload = project.get("raw") or {}
        doc = letters_catalog.get_doc(payload.get("doc_slug", ""))
        fields = payload.get("fields") or {}
        items.append({
            "project": project,
            "doc": doc,
            "doc_name": doc["name"] if doc else (project.get("title") or "Letter"),
            "category": (letters_catalog.CATEGORIES_BY_SLUG.get(doc["category"], {})
                         if doc else {}).get("name", ""),
            "parties": letter_model.parties_summary(doc, fields) if doc else "",
            "template": _template(payload.get("template_slug")),
        })
    return render_template(
        "letters/saved.html",
        items=items,
        query=query,
        total=projects_repo.count_projects("LETTER"),
    )


# ---------------------------------------------------------------------------
# Document-specific form
# ---------------------------------------------------------------------------
@bp.route("/new", methods=["GET", "POST"])
def new():
    doc = _doc_or_404()
    template_slug = request.values.get("template") or "professional"
    instances = letters_catalog.field_instances(doc)
    fields = letter_model.normalize(doc, request.values.to_dict())
    return render_template(
        "letters/form.html",
        doc=doc,
        category=letters_catalog.CATEGORIES_BY_SLUG[doc["category"]],
        instances=instances,
        fields=fields,
        templates=LETTER_TEMPLATES,
        template_slug=template_slug,
        legal=doc["legal"],
        back_url=url_for("letters.index"),
    )


@bp.route("/preview", methods=["POST"])
def preview_form():
    """Preview the data currently in the form, saved or not."""
    doc = _doc_or_404()
    fields = letter_model.parse_form(doc, request.form)
    template_slug = request.form.get("template_slug") or "professional"
    doc_struct = _compose(fields, doc, template_slug)
    html = letter_render_letter_sheet(doc_struct)
    return render_template(
        "letters/preview.html",
        doc=doc,
        doc_struct=doc_struct,
        sheet=html,
        project_id=None,
        template_slug=template_slug,
        fields=fields,
        templates=LETTER_TEMPLATES,
        heading="Preview - not saved yet",
    )


@bp.route("/save", methods=["POST"])
def save():
    doc = _doc_or_404()
    fields = letter_model.parse_form(doc, request.form)
    template_slug = request.form.get("template_slug") or "professional"
    project_id = request.form.get("project_id", type=int)
    customer = _customer_for(doc, fields)
    title = letter_model.display_title(doc, fields)
    payload = {"doc_slug": doc["slug"], "fields": fields}
    new_id = projects_repo.save_project(
        project_id, {}, template_slug, doc_type="LETTER", data=payload,
        customer_name=customer, title=title,
    )
    flash("Document saved." if project_id else "Document saved to Saved Letters.",
          "ok")
    return redirect(url_for("letters.edit", letter_id=new_id, saved=1))


def _customer_for(doc: dict, fields: dict) -> str:
    """Storage display name: the person the document is about."""
    for name in ("seller_full_name", "current_owner", "employee_name",
                 "new_owner", "applicant_full_name", "declarant_full_name",
                 "authorizing_person_full_name", "sender_full_name",
                 "full_name"):
        if fields.get(name):
            return fields[name]
    return doc["name"]


# ---------------------------------------------------------------------------
# Saved document routes
# ---------------------------------------------------------------------------
@bp.route("/<int:letter_id>/edit")
def edit(letter_id: int):
    project = _letter_project(letter_id)
    if not project:
        abort(404)
    payload = project.get("raw") or {}
    doc = letters_catalog.get_doc(payload.get("doc_slug", ""))
    if doc is None:
        abort(404)
    fields = letter_model.normalize(doc, payload.get("fields") or {})
    return render_template(
        "letters/form.html",
        doc=doc,
        category=letters_catalog.CATEGORIES_BY_SLUG[doc["category"]],
        instances=letters_catalog.field_instances(doc),
        fields=fields,
        templates=LETTER_TEMPLATES,
        template_slug=payload.get("template_slug") or "professional",
        legal=doc["legal"],
        project=project,
        saved=request.args.get("saved") == "1",
        back_url=url_for("letters.saved"),
    )


@bp.route("/<int:letter_id>/preview")
def preview(letter_id: int):
    project = _letter_project(letter_id)
    if not project:
        abort(404)
    payload = project.get("raw") or {}
    doc = letters_catalog.get_doc(payload.get("doc_slug", ""))
    if doc is None:
        abort(404)
    fields = letter_model.normalize(doc, payload.get("fields") or {})
    doc_struct = _compose(fields, doc, payload.get("template_slug"))
    html = letter_render_letter_sheet(doc_struct)
    return render_template(
        "letters/preview.html",
        doc=doc,
        doc_struct=doc_struct,
        sheet=html,
        project_id=letter_id,
        template_slug=payload.get("template_slug") or "professional",
        fields=fields,
        templates=LETTER_TEMPLATES,
        heading=project["title"],
    )


@bp.route("/<int:letter_id>/duplicate", methods=["POST"])
def duplicate(letter_id: int):
    new_id = projects_repo.duplicate_project(letter_id)
    if not new_id:
        abort(404)
    flash("Document duplicated.", "ok")
    return redirect(url_for("letters.saved"))


@bp.route("/<int:letter_id>/delete", methods=["POST"])
def delete(letter_id: int):
    project = _letter_project(letter_id)
    if not project:
        abort(404)
    projects_repo.delete_project(letter_id)
    flash("Document deleted.", "ok")
    return redirect(url_for("letters.saved"))


# ---------------------------------------------------------------------------
# Exports (Phase 4 engines)
# ---------------------------------------------------------------------------
@bp.route("/<int:letter_id>/export/pdf", methods=["POST"])
def export_pdf(letter_id: int):
    project = _letter_project(letter_id)
    if not project:
        abort(404)
    payload = project.get("raw") or {}
    doc = letters_catalog.get_doc(payload.get("doc_slug", ""))
    if doc is None:
        abort(404)
    fields = letter_model.normalize(doc, payload.get("fields") or {})
    doc_struct = _compose(fields, doc, payload.get("template_slug"))
    try:
        path = letter_pdf.export_letter_pdf(doc_struct, project["customer_name"])
    except Exception:
        current_app.logger.exception("Letter PDF export failed for %s", letter_id)
        abort(500)
    flash(f"PDF saved to {path}.", "ok")
    return send_file(path, mimetype="application/pdf", as_attachment=True,
                     download_name=path.name)


@bp.route("/<int:letter_id>/export/docx", methods=["POST"])
def export_docx(letter_id: int):
    project = _letter_project(letter_id)
    if not project:
        abort(404)
    payload = project.get("raw") or {}
    doc = letters_catalog.get_doc(payload.get("doc_slug", ""))
    if doc is None:
        abort(404)
    fields = letter_model.normalize(doc, payload.get("fields") or {})
    doc_struct = _compose(fields, doc, payload.get("template_slug"))
    try:
        path = letter_docx.export_letter_docx(doc_struct, project["customer_name"])
    except Exception:
        current_app.logger.exception("Letter DOCX export failed for %s", letter_id)
        abort(500)
    flash(f"Word document saved to {path}.", "ok")
    return send_file(
        path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=path.name,
    )


# ---------------------------------------------------------------------------
# HTML sheet (shared by preview routes)
# ---------------------------------------------------------------------------
def letter_render_letter_sheet(doc_struct: dict) -> str:
    """Render the A4 sheet HTML for the composed document."""
    return render_template("letters/sheet.html", d=doc_struct)
