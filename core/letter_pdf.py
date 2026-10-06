"""
Letter / document PDF export - standard library only.

Reuses the Phase 4 PDF engine (core/cv_pdf._Doc) so letters inherit the same
A4 page box, built-in fonts, word wrapping, page breaks and footer as the CV
exports. The layout follows formal document conventions: centred title,
recipient block, numbered clauses and a signature block.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core import paths
from core.cv_pdf import _Doc, CONTENT_W, MARGIN, PAGE_W


def _rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = (hex_color or "#123a72").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "123a72"
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def render_letter_pdf_bytes(doc_struct: dict[str, Any]) -> bytes:
    serif = doc_struct.get("serif")
    accent = _rgb(doc_struct.get("accent") or "#123a72")
    d = _Doc(doc_struct.get("accent") or "#123a72",
             {"serif": serif, "sidebar": False, "header_bar": False,
              "title_size": 10, "body_size": 10, "rule_above_title": False,
              "title_in_accent": False},
             doc_struct.get("template_name") or "Document")

    body_font = "times" if serif else "helvetica"
    head_font = "times-bold" if serif else "helvetica-bold"
    size = 10
    leading = size + 3.4
    gray = (0.32, 0.35, 0.4)

    # ---- title -------------------------------------------------------------
    title = doc_struct["title"].upper()
    from core.cv_pdf import _width as _w
    from core.cv_pdf import _esc as _esc

    d.ensure(70)
    d.y -= 8
    if _w(title, head_font, 13) <= CONTENT_W:
        x = (PAGE_W - _w(title, head_font, 13)) / 2
        d.text(x, d.y - 13, title, head_font, 13, accent if not serif else (0, 0, 0))
    else:
        d.y -= 16
        d.paragraph(title, head_font, 13, 16)
    d.y -= 8
    d.line(MARGIN, d.y, MARGIN + CONTENT_W, d.y, accent if not serif else (0, 0, 0), 1.2)
    d.y -= 14

    # ---- date + recipient ---------------------------------------------------
    if doc_struct.get("date"):
        label = f"Date: {doc_struct['date']}"
        w = _w(label, body_font, size)
        d.text(MARGIN + CONTENT_W - w, d.y - size, label, body_font, size, gray)
        d.y -= leading + 2
    recipient = doc_struct.get("recipient")
    if recipient:
        d.text(MARGIN, d.y - size, "To:", head_font, size)
        d.y -= leading
        for line in recipient:
            d.ensure(leading)
            d.paragraph(line, body_font, size, leading)
        d.y -= 2
        d.line(MARGIN, d.y, MARGIN + 180, d.y, (0.75, 0.77, 0.8), 0.6)
        d.y -= 10

    # ---- salutation + opening ------------------------------------------------
    if doc_struct.get("salutation"):
        d.ensure(leading)
        d.paragraph(doc_struct["salutation"] + ",", body_font, size, leading)
    if doc_struct.get("opening"):
        d.ensure(leading * 2)
        d.paragraph(doc_struct["opening"], body_font, size, leading)
        d.y -= 3

    # ---- clauses -------------------------------------------------------------
    for idx, clause in enumerate(doc_struct.get("clauses", []), start=1):
        d.section_title(f"{idx}. {clause['heading']}")
        for label, value in clause["items"]:
            # label bold, wrapped value on the same flow with hanging indent
            lines = d.wrap(f"{label}: {value}", body_font, size, CONTENT_W - 10)
            for i, line in enumerate(lines):
                d.ensure(leading)
                if i == 0:
                    lw = _w(f"{label}:", head_font, size)
                    d.text(MARGIN + 2, d.y - size, f"{label}:", head_font, size)
                    rest = line[len(f"{label}:"):].strip()
                    d.text(MARGIN + 2 + lw + 4, d.y - size, rest, body_font, size)
                else:
                    d.text(MARGIN + 14, d.y - size, line, body_font, size)
                d.y -= leading
            d.y -= 1.5

    # ---- closing / signature ---------------------------------------------------
    if doc_struct.get("closing"):
        d.y -= 6
        d.ensure(leading * 2)
        d.paragraph(doc_struct["closing"], body_font, size, leading)
        if doc_struct.get("letter_signer"):
            d.ensure(58)
            d.y -= 6
            _signature_line(d, MARGIN, doc_struct["letter_signer"]["name"],
                            "", serif, gray)

    for signer in doc_struct.get("signers", []):
        d.ensure(62)
        d.y -= 6
        _signature_line(d, MARGIN, signer["name"], signer["role"], serif, gray)

    witnesses = doc_struct.get("witnesses", [])
    if witnesses:
        d.section_title("Witnesses")
        for i, wit in enumerate(witnesses, start=1):
            d.ensure(58)
            d.y -= 4
            _signature_line(d, MARGIN, wit["name"], f"Witness {i}", serif, gray)

    # ---- disclaimer ------------------------------------------------------------
    if doc_struct.get("disclaimer"):
        d.y -= 6
        d.ensure(40)
        d.line(MARGIN, d.y, MARGIN + CONTENT_W, d.y, (0.8, 0.82, 0.85), 0.6)
        d.y -= 4
        d.paragraph("Note: " + doc_struct["disclaimer"],
                    body_font, 7.5, 9.5, color=gray)

    return d.build()


def _signature_line(d: _Doc, x: float, name: str, role: str,
                    serif: bool, gray: tuple[float, float, float]) -> None:
    from core.cv_pdf import _width as _w

    body_font = "times" if serif else "helvetica"
    head_font = "times-bold" if serif else "helvetica-bold"
    d.line(x, d.y, x + 150, d.y, (0, 0, 0), 0.9)
    d.text(x, d.y - 11, name, head_font, 9.5)
    if role:
        d.text(x, d.y - 22, role, body_font, 8.5, gray)
    d.y -= 30


def export_letter_pdf(doc_struct: dict[str, Any], customer_name: str,
                      when: date | None = None) -> Path:
    stem = paths.safe_stem(customer_name, "Letter", when)
    out = paths.unique_path(paths.output_dir("letters"), stem, ".pdf")
    out.write_bytes(render_letter_pdf_bytes(doc_struct))
    return out
