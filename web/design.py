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

from core import ai_service
from core import design_catalog as catalog
from core import design_generation, design_model, design_store
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
    for el in safe.get("elements", []):
        if el.get("kind") == "photo" and el.get("file"):
            el["url"] = url_for("design.image", filename=el["file"])
    return json.dumps(safe)


def _result(payload: dict, layout: dict, *, project: dict | None = None,
            saved: bool = False, review: dict | None = None,
            error: str = "", original_layout: dict | None = None) -> str:
    """Render the design workspace (result screen). One place, so the normal
    workflow, the AI review and a failed AI request all show the same UI."""
    return render_template(
        "design/result.html",
        service=registry.get_service("graphic-design"),
        category=catalog.get_category(payload["category"]),
        themes=catalog.THEMES,
        styles=catalog.STYLES,
        payload=payload,
        layout=layout,
        layout_json=_layout_json(layout),
        original_layout=original_layout,
        document=project,
        saved=saved,
        review=review,
        ai=design_generation.ai_status(),
        provider=design_generation.provider_status(),
        ai_error=error,
    )


def _posted_images() -> list[dict[str, str]]:
    """Already-stored images carried through hidden fields (never re-uploaded)."""
    return [
        {"filename": name, "role": ""}
        for name in request.form.getlist("image_filename")
        if name
    ]


def _review_payload(payload: dict, result: dict, stored: str) -> dict:
    """The payload for an AI variant: the operator's design with the freshly
    generated backdrop attached. The original payload is left untouched."""
    from core import paths

    return {
        **payload,
        "ai": {
            "background": stored,
            "prompt": result["prompt"],
            "provider": result["provider"],
            "model": result["model"],
            "created_at": paths.stamp(),
        },
    }


AI_ERROR_HINTS = {
    "disabled": "Turn AI features on in Settings.",
    "not_configured": "Add a provider API key in Settings.",
    "bad_request": "",
    "timeout": "The AI provider was slow to answer. Try again.",
    "network": "AI finishing needs an internet connection.",
    "rate_limit": "The AI provider is rate limiting this device. Try again shortly.",
    "quota": "This key's plan or quota is exhausted - check your provider's "
             "billing, not the design.",
    "auth": "The AI provider rejected the API key. Check Settings.",
    "provider": "The AI provider refused the request.",
    "invalid_response": "The AI provider did not return a usable image.",
}


def _message_for(exc: Exception) -> str:
    hint = AI_ERROR_HINTS.get(getattr(exc, "kind", ""), "")
    message = str(exc)
    return f"{message} {hint}".strip()


# ---------------------------------------------------------------------------
# Review bookkeeping
#
# While a result is on screen for review, the form's `ai_background` is the
# *pending* (unaccepted) image and `ai_original_background` carries whatever
# the design had accepted before - possibly nothing. The presence of that
# second field is how every route knows it is being posted from a review
# screen, so leaving review by any other door (Regenerate, Save, Edit) drops
# the unaccepted image instead of silently keeping it.
# ---------------------------------------------------------------------------
def _in_review() -> bool:
    return "ai_original_background" in request.form


def _previous_background() -> str:
    """The design's accepted AI background before this attempt ("" if none)."""
    kept = (request.form.get("ai_original_background") or "").strip()
    return kept if kept and design_store.is_safe_name(kept) else ""


def _without_pending(payload: dict) -> dict:
    """The payload as it was before the AI attempt: pending image dropped,
    any previously accepted background restored."""
    kept = _previous_background()
    if kept:
        return {**payload, "ai": {**payload.get("ai", {}), "background": kept}}
    return {**payload, "ai": {}}


def _discard_pending(payload: dict) -> dict:
    """Leave a review without accepting: restore the previous background and
    delete the pending image so it cannot pile up on the device."""
    pending = design_model.ai_background(payload)
    kept = _previous_background()
    if pending and pending != kept:
        design_store.delete_image(pending)
    return _without_pending(payload)


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
        styles=catalog.STYLES,
        payload=design_model.blank_payload(category.slug),
        images=[],
        document=None,
        saved=False,
        ai=design_generation.ai_status(),
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
    # Regenerating from a review screen means the operator moved on without
    # accepting, so the pending AI image is dropped, never silently kept.
    if _in_review():
        payload = _discard_pending(payload)
    project_id = request.form.get("project_id", type=int)
    if project_id and not _project(project_id):
        project_id = None
    layout = design_generation.generate_design(payload)
    return _result(payload, layout,
                   project=_project(project_id) if project_id else None)


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
    # Editing away from a review screen: keep whatever was accepted before,
    # not the unaccepted result that happened to be on screen.
    if _in_review():
        payload = _discard_pending(payload)
    return render_template(
        "design/form.html",
        service=registry.get_service("graphic-design"),
        category=category,
        categories=catalog.CATEGORIES,
        themes=catalog.THEMES,
        styles=catalog.STYLES,
        payload=payload,
        images=design_store.image_records(payload),
        document=_project(project_id) if project_id else None,
        saved=False,
        ai=design_generation.ai_status(),
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
    # Saving from a review screen without accepting must not persist the
    # unaccepted AI background.
    if _in_review():
        payload = _discard_pending(payload)
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
        styles=catalog.STYLES,
        payload=payload,
        images=design_store.image_records(payload),
        document=project,
        saved=request.args.get("saved") == "1",
        ai=design_generation.ai_status(),
        provider=design_generation.provider_status(),
    )


@bp.route("/<int:design_id>/preview")
def preview(design_id: int):
    project = _project(design_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    layout = design_generation.generate_design(payload)
    return _result(payload, layout, project=project, saved=True)


# ---------------------------------------------------------------------------
# AI finishing (see core/ai_service.py)
#
# The AI paints a BACKGROUND only. The customer's own text and photos are
# re-rendered by the built-in engine on top of it, so an image model can never
# silently change a name, date, venue or phone number. Nothing is saved until
# the operator explicitly accepts the result.
# ---------------------------------------------------------------------------
@bp.route("/ai", methods=["POST"])
def ai_finish():
    """Ask the AI provider for a new background and show it for review.

    Accepts the same post as Generate (fresh uploads included), so
    "Generate & Finish with AI" from the editor works in one step.
    """
    payload = design_model.parse_form(request.form, _images_from_form())
    prompt = request.form.get("ai_prompt", "")
    project_id = request.form.get("project_id", type=int)
    project = _project(project_id) if project_id else None

    # "Try another" carries the image it is replacing, so the old variation can
    # be deleted once the new one exists - it was never accepted.
    discard = (request.form.get("ai_discard") or "").strip()
    review = _in_review()

    # The design as it was before this attempt. On a review screen the form's
    # ai_background is the *pending* result, so both the fallback and the
    # comparison must use the previously accepted background instead.
    base = _without_pending(payload) if review else payload
    original = design_generation.generate_design(base)

    try:
        result = ai_service.finish_design(payload, prompt)
    except ai_service.AiError as exc:
        flash(_message_for(exc), "error")
        if review:
            # Leaving the review because the retry failed: discard the pending
            # image and fall back to what was accepted before it.
            design_store.delete_image(discard)
            base = _without_pending(payload)
            return _result(base, design_generation.generate_design(base),
                           project=project, error=str(exc))
        return _result(payload, original, project=project, error=str(exc))

    stored = design_store.save_bytes(result["image_bytes"], result["ext"],
                                     prefix="ai")
    if not stored:
        flash("The AI image could not be stored on this device. Nothing changed.",
              "error")
        if review:
            design_store.delete_image(discard)
            base = _without_pending(payload)
            return _result(base, design_generation.generate_design(base),
                           project=project)
        return _result(payload, original, project=project)

    # The new variation is on disk, so the image it replaced can go.
    if discard and design_store.is_safe_name(discard) and discard != stored:
        design_store.delete_image(discard)

    variant = design_model.normalize(_review_payload(payload, result, stored))
    # `base` (not the pending `payload`) goes to the template so
    # ai_original_background is the design's *previous* accepted background -
    # what Reject restores and Accept supersedes. The stage draws the variant.
    return _result(base, design_generation.generate_design(variant),
                   project=project,
                   review=variant["ai"], original_layout=original)


@bp.route("/ai/accept", methods=["POST"])
def ai_accept():
    """Accept the reviewed AI result: it becomes the design and is saved."""
    payload = design_model.parse_form(request.form, _posted_images())
    accepted = design_model.ai_background(payload)
    if not accepted:
        flash("There is no AI result to accept.", "error")
        return redirect(url_for("design.index"))
    # Never persist a design that points at an image this device no longer has.
    if not design_store.path_for(accepted).is_file():
        flash("The reviewed AI background is no longer on this device. "
              "Run Finish with AI again.", "error")
        return redirect(url_for("design.index"))
    project_id = request.form.get("project_id", type=int)
    if project_id and not _project(project_id):
        project_id = None
    title = design_model.display_title(payload)
    try:
        new_id = projects_repo.save_project(
            project_id, {}, f"design-{payload['category']}",
            doc_type=DESIGN_DOC_TYPE, data=payload, customer_name=title,
            title=title,
        )
    except Exception:
        current_app.logger.exception("Saving accepted AI design failed")
        abort(500)
    # The design now uses this result, so the background it superseded is no
    # longer referenced by anything and can be removed.
    previous = _previous_background()
    if previous and previous != accepted:
        design_store.delete_image(previous)
    flash("AI result accepted. Your text and images stay exactly as you entered "
          "them - export or print it from here.")
    return redirect(url_for("design.preview", design_id=new_id, saved=1))


@bp.route("/ai/reject", methods=["POST"])
def ai_reject():
    """Reject a reviewed AI result: delete its image, keep the original design."""
    payload = design_model.parse_form(request.form, _posted_images())
    # Delete the rejected image and restore whatever the design had before
    # this attempt (usually nothing).
    payload = _discard_pending(payload)
    project_id = request.form.get("project_id", type=int)
    project = _project(project_id) if project_id else None
    flash("AI result discarded. Your original design is unchanged.")
    return _result(payload, design_generation.generate_design(payload),
                   project=project)


@bp.route("/<int:design_id>/ai/remove", methods=["POST"])
def ai_remove(design_id: int):
    """Drop an accepted AI background and go back to the plain composition."""
    project = _project(design_id)
    if not project:
        abort(404)
    payload = _payload_of(project)
    name = design_model.ai_background(payload)
    if name:
        design_store.delete_image(name)
    payload["ai"] = {}
    title = design_model.display_title(payload)
    projects_repo.update_project(
        design_id, {}, f"design-{payload['category']}", doc_type=DESIGN_DOC_TYPE,
        data=payload, customer_name=title, title=title,
    )
    flash("AI background removed. The original design is back.")
    return redirect(url_for("design.preview", design_id=design_id))


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
