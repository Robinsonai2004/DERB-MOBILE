"""
Design data model for DERB MOBILE.

Single source of truth for "what a Graphic Design job is": a category plus the
category's own field values, an optional instruction note, a colour theme and
the uploaded image filenames. The model is serialised into the same
``projects`` table (doc_type='DESIGN') as CVs, letters and documents, so Saved
Work lists design jobs beside the rest with no new storage.

Text is sanitised through ``core.doc_model.plain`` so anything pasted into a
field is reduced to safe text - the layout renderer never emits markup from
operator input, which keeps the offline, no-CDN guarantee intact.
"""

from __future__ import annotations

from typing import Any

from core import design_catalog as catalog
from core import design_store, doc_model, paths

MAX_IMAGES = 8


def blank_payload(category_slug: str | None = None) -> dict[str, Any]:
    return normalize({"category": category_slug or (catalog.CATEGORIES[0].slug)})


def _clean_single(value: Any) -> str:
    """One-line text (collapses newlines)."""
    return " ".join(doc_model.plain(value if isinstance(value, str) else "").split())


def _clean_multi(value: Any) -> str:
    """Multi-line text (keeps intentional blank lines)."""
    return doc_model.plain(value if isinstance(value, str) else "")


def normalize(data: Any) -> dict[str, Any]:
    """Fill in anything missing so renderers and templates never KeyError."""
    if not isinstance(data, dict):
        data = {}

    category = catalog.get_category(str(data.get("category") or ""))
    if category is None:
        category = catalog.CATEGORIES[0]

    raw_fields = data.get("fields")
    if not isinstance(raw_fields, dict):
        raw_fields = {}
    fields: dict[str, str] = {}
    for key in category.fields:
        meta = catalog.FIELD_DEFS.get(key, {})
        value = raw_fields.get(key, "")
        if meta.get("type") == "textarea":
            fields[key] = _clean_multi(value)
        else:
            fields[key] = _clean_single(value)

    theme = str(data.get("theme") or "").strip()
    if theme not in catalog.THEMES:
        theme = category.theme

    style = str(data.get("style") or "").strip()
    if style not in dict(catalog.STYLES):
        style = ""

    images: list[dict[str, str]] = []
    raw_images = data.get("images")
    if isinstance(raw_images, list):
        for item in raw_images:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "").strip()
            if not filename:
                continue
            images.append({
                "filename": filename,
                "role": _clean_single(item.get("role", ""))[:60],
            })
    images = images[:MAX_IMAGES]

    # An accepted AI background is part of the design from now on: it survives
    # save, reopen, regenerate and export. The original uploads are untouched,
    # so "remove AI background" can always restore the plain composition.
    raw_ai = data.get("ai")
    if not isinstance(raw_ai, dict):
        raw_ai = {}
    background = str(raw_ai.get("background") or "").strip()
    ai: dict[str, str] = {}
    if background and design_store.is_safe_name(background):
        ai = {
            "background": background,
            "prompt": _clean_multi(raw_ai.get("prompt", ""))[:600],
            "provider": _clean_single(raw_ai.get("provider", ""))[:60],
            "model": _clean_single(raw_ai.get("model", ""))[:60],
            "created_at": _clean_single(raw_ai.get("created_at", ""))[:32],
        }

    return {
        "category": category.slug,
        "title": _clean_single(data.get("title", ""))[:120],
        "fields": fields,
        "instructions": _clean_multi(data.get("instructions", ""))[:2000],
        "theme": theme,
        "style": style,
        "images": images,
        "ai": ai,
    }


def parse_form(form, images: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Build the payload from an editor form submission.

    ``images`` is the already-stored image list (the form only carries the
    filenames as hidden fields, since the files were uploaded on Generate).
    Every design screen re-posts the accepted AI background through hidden
    fields, so regenerating or editing never silently drops it.
    """
    category = catalog.get_category(form.get("category")) or catalog.CATEGORIES[0]
    fields = {key: form.get(key, "") for key in category.fields}
    return normalize(
        {
            "category": category.slug,
            "title": form.get("title", ""),
            "fields": fields,
            "instructions": form.get("instructions", ""),
            "theme": form.get("theme", category.theme),
            "style": form.get("style", ""),
            "images": images or [],
            "ai": {
                "background": form.get("ai_background", ""),
                "prompt": form.get("ai_prompt", ""),
                "provider": form.get("ai_provider", ""),
                "model": form.get("ai_model", ""),
                "created_at": form.get("ai_created_at", ""),
            },
        }
    )


def ai_background(payload: dict[str, Any]) -> str:
    """Accepted AI background filename, or '' when the design has none."""
    ai = payload.get("ai")
    if not isinstance(ai, dict):
        return ""
    return str(ai.get("background") or "")


def has_ai(payload: dict[str, Any]) -> bool:
    return bool(ai_background(payload))


# ---------------------------------------------------------------------------
# Display helpers (shared by editor, preview, exports and the Saved list)
# ---------------------------------------------------------------------------
def display_title(payload: dict[str, Any], fallback: str | None = None) -> str:
    """Operator's job title, else the most telling field, else a label."""
    title = (payload.get("title") or "").strip()
    if title:
        return title
    category = catalog.get_category(payload.get("category"))
    fields = payload.get("fields") or {}
    for key in ("main_title", "custom_title", "event_name", "business_name",
                "headline", "couple_names", "deceased_name", "graduate_name",
                "honoree", "name", "awardee", "certificate_title",
                "anniversary_type"):
        value = (fields.get(key) or "").strip()
        if value:
            return value[:80]
    if category:
        return fallback or f"{category.name} Design"
    return fallback or "Untitled Design"


def is_empty(payload: dict[str, Any]) -> bool:
    """True when there is nothing worth generating or saving."""
    fields = payload.get("fields") or {}
    has_field = any((v or "").strip() for v in fields.values())
    return not (has_field or (payload.get("instructions") or "").strip()
                or payload.get("images"))


def filled_summary(payload: dict[str, Any]) -> dict[str, int]:
    fields = payload.get("fields") or {}
    filled = sum(1 for v in fields.values() if (v or "").strip())
    return {
        "fields": filled,
        "images": len(payload.get("images") or []),
        "details": len((payload.get("instructions") or "").split()),
    }


def summary_line(payload: dict[str, Any], limit: int = 110) -> str:
    category = catalog.get_category(payload.get("category"))
    label = category.name if category else "Design"
    return f"{label} - {display_title(payload)}"[:limit]


def safe_stem(payload: dict[str, Any]) -> str:
    return paths.safe_stem(display_title(payload), "Design")
