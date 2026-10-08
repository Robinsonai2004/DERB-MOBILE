"""
Design layout builder for DERB MOBILE - standard library only.

Turns a design payload (category + field values + images + theme) into a
deterministic, block-based *layout spec*. The HTML preview and the client-side
canvas export (PNG/JPG) both consume this SAME spec, so what the operator sees
is what prints / downloads.

This is deliberately NOT an AI image generator: it is a real, local layout
engine that arranges the operator's own content into a professional poster -
the honest equivalent of the CV/letter renderers. A clean seam for a real
image/AI provider lives in core/design_generation.py.
"""

from __future__ import annotations

from typing import Any

from core import design_catalog as catalog

# A poster is authored at a fixed pixel width for export; the HTML preview
# scales it with container-query units, so both stay proportional.
EXPORT_WIDTH = 1240
MAX_GALLERY = 6


def _rows(category: catalog.DesignCategory, fields: dict[str, str]) -> list[dict[str, str]]:
    """Label/value rows for every filled field, in the category's order."""
    out = []
    for key in category.fields:
        value = (fields.get(key) or "").strip()
        if not value:
            continue
        label = catalog.FIELD_DEFS.get(key, {}).get("label", key.replace("_", " ").title())
        out.append({"label": label, "value": value})
    return out


def _subtitle(category: catalog.DesignCategory, fields: dict[str, str]) -> str:
    """A short line under the title, drawn from the category's own fields."""
    for key in ("anniversary_type", "business_type", "degree", "position",
                "event_name", "certificate_title", "theme"):
        value = (fields.get(key) or "").strip()
        if value:
            return value
    return category.name


def build_layout(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the poster layout spec for a normalized design payload."""
    category = catalog.get_category(payload.get("category")) or catalog.CATEGORIES[0]
    theme = catalog.get_theme(payload.get("theme") or category.theme)
    aspect = catalog.ASPECTS.get(category.aspect, 0.7071)

    from core import design_model  # local import avoids a cycle at import time

    title = design_model.display_title(payload)
    fields = payload.get("fields") or {}
    rows = _rows(category, fields)
    images = [img for img in (payload.get("images") or []) if img.get("filename")][:MAX_GALLERY]
    instructions = (payload.get("instructions") or "").strip()

    blocks: list[dict[str, Any]] = []
    blocks.append({
        "kind": "header", "flex": 2.0,
        "title": title, "subtitle": _subtitle(category, fields),
        "fill": theme["accent"], "ink": theme["band_ink"],
    })

    if rows:
        blocks.append({
            "kind": "info", "flex": 1.1 + 0.42 * len(rows),
            "rows": rows, "ink": theme["ink"], "muted": theme["muted"],
        })

    if instructions:
        blocks.append({
            "kind": "paragraph", "flex": 1.4, "heading": "Details",
            "text": instructions, "ink": theme["ink"], "muted": theme["muted"],
        })

    if images:
        blocks.append({
            "kind": "gallery", "flex": 2.0, "images": images,
            "columns": min(len(images), 3),
        })

    blocks.append({
        "kind": "footer", "flex": 0.9,
        "lines": ["Designed at DERB FINANCE CONCEPTS"],
        "fill": theme["accent"], "ink": theme["band_ink"],
    })

    return {
        "aspect": aspect,
        "width": EXPORT_WIDTH,
        "height": int(round(EXPORT_WIDTH / aspect)),
        "palette": theme,
        "category": {"slug": category.slug, "name": category.name},
        "blocks": blocks,
    }


def render_design(payload: dict[str, Any]) -> dict[str, Any]:
    """Public entry point used by the route, the generation service and tests."""
    return build_layout(payload)
