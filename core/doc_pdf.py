"""
Document PDF export - standard library only.

Reuses the Phase 4 PDF engine (core/cv_pdf._Doc) exactly like the letters
module does, so free-format documents inherit the same A4 page box, built-in
fonts, word wrapping, automatic page breaks and footer. There is no second
export system to keep in sync.

This renderer is deliberately plainer than the letter writer: a Document is
the customer's own speech / essay / minutes, so it gets a centred title, an
optional rule, and body paragraphs laid out with the operator's chosen font
size (core.doc_model.SIZE_PT) and paragraph alignment.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core import doc_model, paths
from core.cv_pdf import _Doc, CONTENT_W, MARGIN, PAGE_W, _esc, _width


def _rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = (hex_color or "#123a72").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "123a72"
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _align_x(align: str, width: float) -> float:
    """Left margin for one line of *width* inside CONTENT_W."""
    if align == "center":
        return MARGIN + max(0.0, (CONTENT_W - width) / 2)
    if align == "right":
        return MARGIN + max(0.0, CONTENT_W - width)
    return MARGIN


def render_document_pdf_bytes(payload: dict[str, Any]) -> bytes:
    payload = doc_model.normalize(payload)
    accent = _rgb("#123a72")
    title = doc_model.display_title(payload)
    size = doc_model.SIZE_PT[int(payload.get("size") or doc_model.DEFAULT_SIZE)]
    align = payload.get("align", "left")

    d = _Doc("#123a72",
             {"serif": False, "sidebar": False, "header_bar": False,
              "title_size": 13, "body_size": size,
              "rule_above_title": False, "title_in_accent": False},
             "Document")

    head_font = "helvetica-bold"
    body_font = "helvetica"
    gray = (0.32, 0.35, 0.4)

    # ---- title (centred, wrapped) ------------------------------------------
    d.ensure(40)
    for line in d.wrap(title.upper(), head_font, 13, CONTENT_W):
        w = _width(line, head_font, 13)
        d.text(_align_x("center", w), d.y - 13, line, head_font, 13, accent)
        d.y -= 16
    d.y -= 2
    d.line(MARGIN, d.y, MARGIN + CONTENT_W, d.y, accent, 1.2)
    d.y -= 16

    # ---- body ---------------------------------------------------------------
    leading = size + 3.6
    blocks = _flow_blocks(payload)
    for block in blocks:
        text = block["text"]
        b_align = block.get("align") or align
        font = block.get("font") or body_font
        b_size = block.get("size") or size
        b_leading = b_size + 3.6
        if block["type"] == "bullet":
            for i, wl in enumerate(d.wrap(text, font, b_size, CONTENT_W - 14)):
                d.ensure(b_leading)
                if i == 0:
                    dot = "\u2022"
                    d.text(MARGIN + 2, d.y - b_size, dot, font, b_size,
                           gray if font == body_font else accent)
                d.text(MARGIN + 14, d.y - b_size, wl, font, b_size)
                d.y -= b_leading
            d.y -= 1.2
            continue
        # paragraph: line-by-line so we can honour left/center/right
        for wl in d.wrap(text, font, b_size, CONTENT_W):
            d.ensure(b_leading)
            w = _width(wl, font, b_size)
            x = MARGIN if b_align == "left" else _align_x(b_align, w)
            d.text(x, d.y - b_size, wl, font, b_size)
            d.y -= b_leading
        d.y -= 2.2

    # ---- light brand line ----------------------------------------------------
    d.y -= 8
    d.ensure(12)
    d.text(MARGIN, d.y - 8, "Typed at DERB FINANCE CONCEPTS", body_font, 7.5, gray)
    d.y -= 12

    return d.build()


def _flow_blocks(payload: dict[str, str]) -> list[dict[str, str]]:
    """Body text -> flowable blocks. Line-level overrides use '  @center:' etc."""
    align = payload.get("align", "left")
    size = doc_model.SIZE_PT[int(payload.get("size") or doc_model.DEFAULT_SIZE)]
    blocks: list[dict[str, str]] = []
    for raw in (payload.get("body_text") or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            blocks.append({"type": "gap", "text": ""})
            continue
        stripped = line.strip()
        if stripped.startswith("- ") or stripped == "-":
            blocks.append({"type": "bullet", "text": stripped[2:].strip(),
                           "align": align, "font": "helvetica", "size": size})
            continue
        blocks.append({"type": "para", "text": stripped,
                       "align": align, "font": "helvetica", "size": size})
    return blocks


def export_document_pdf(payload: dict[str, str], title: str,
                        when: date | None = None) -> Path:
    stem = paths.safe_stem(title, "Document", when)
    out = paths.unique_path(paths.output_dir("documents"), stem, ".pdf")
    out.write_bytes(render_document_pdf_bytes(payload))
    return out
