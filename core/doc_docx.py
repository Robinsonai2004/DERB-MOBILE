"""
Document DOCX export - standard library only.

Same pattern as core/letter_docx.py: word/document.xml is built from the
shared Phase 4 OOXML helpers in core/cv_docx.py (elements, namespacing,
content types, relationships, Word-native styles). Free-format documents get
a centred title, a rule, and body paragraphs carrying the operator's chosen
size (Word half-points) and alignment - genuinely editable in Word.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core import doc_model, paths
from core.cv_docx import _styles_xml, _register_namespaces, _sub, _el
from core.cv_docx import _DOC_RELS_NO_IMAGE, CONTENT_TYPES, ROOT_RELS, W_NS

import io
import zipfile
import xml.etree.ElementTree as ET

_ALIGN = {"left": None, "center": "center", "right": "right"}


def _half_points(size_key: int) -> int:
    """doc_model.SIZE_PT (pt) -> Word half-points (sz uses half-points)."""
    return int(round(doc_model.SIZE_PT[size_key] * 2))


class _DocxBuilder:
    def __init__(self, accent: str):
        self.accent = accent
        self.body = ET.Element("w:body")

    def run(self, text: str, *, bold: bool = False, size: int = 24,
            color: str | None = None):
        r = _el("r")
        rpr = _sub(r, "rPr")
        if bold:
            _sub(rpr, "b")
        _sub(rpr, "sz", val=str(size))
        _sub(rpr, "szCs", val=str(size))
        if color:
            _sub(rpr, "color", val=color)
        t = _sub(r, "t")
        t.text = text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return r

    def para(self, *runs, align: str | None = None, spacing_after: int = 120,
             bullet: bool = False):
        p = _el("p")
        ppr = _sub(p, "pPr")
        if bullet:
            ind = _sub(ppr, "ind", left="284", hanging="170")
        if align:
            _sub(ppr, "jc", val=align)
        _sub(ppr, "spacing", after=str(spacing_after))
        for r in runs:
            p.append(r)
        self.body.append(p)
        return p

    def top_rule(self):
        p = _el("p")
        ppr = _sub(p, "pPr")
        _sub(ppr, "spacing", after="160")
        border = ET.SubElement(ppr, f"{{{W_NS}}}pBdr")
        top = ET.SubElement(border, f"{{{W_NS}}}bottom")
        top.set(f"{{{W_NS}}}val", "single")
        top.set(f"{{{W_NS}}}sz", "8")
        top.set(f"{{{W_NS}}}space", "1")
        top.set(f"{{{W_NS}}}color", self.accent)
        self.body.append(p)

    def sect_pr(self):
        sect = _sub(self.body, "sectPr")
        _sub(sect, "pgSz", w="11906", h="16838")
        _sub(sect, "pgMar", top="1134", right="1134", bottom="1134", left="1134",
             header="708", footer="708", gutter="0")

    def to_bytes(self, accent: str) -> bytes:
        _register_namespaces()
        body_xml = ET.tostring(self.body, encoding="unicode")
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}" '
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
            + body_xml + "</w:document>"
        )
        # Reuse the CV style-sheet builder so Word styles stay consistent.
        tpl = {"accent": "#" + accent.lower(), "layout": "professional"}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("word/document.xml", document.encode())
            z.writestr("word/styles.xml", _styles_xml(tpl))
            z.writestr("word/_rels/document.xml.rels", _DOC_RELS_NO_IMAGE)
        return buf.getvalue()


def render_document_docx_bytes(payload: dict[str, Any]) -> bytes:
    payload = doc_model.normalize(payload)
    accent = "123A72"
    title = doc_model.display_title(payload)
    size_key = int(payload.get("size") or doc_model.DEFAULT_SIZE)
    hp = _half_points(size_key)
    align = payload.get("align", "left")

    d = _DocxBuilder(accent)

    # ---- title (red bold, centred) -------------------------------------------
    d.para(d.run(title, bold=True, size=32, color=accent, ), align="center",
           spacing_after=40)
    d.top_rule()

    # ---- body -----------------------------------------------------------------
    for block in _flow_blocks(payload, hp):
        if block["kind"] == "gap":
            d.para(d.run(" "), spacing_after=60)
            continue
        if block["kind"] == "bullet":
            d.para(d.run("\u2022  ", size=hp, color="5A6472"),
                   d.run(block["text"], size=hp),
                   align=_ALIGN.get(block["align"]), spacing_after=60,
                   bullet=True)
            continue
        d.para(d.run(block["text"], size=hp),
               align=_ALIGN.get(block["align"]), spacing_after=120)

    d.sect_pr()
    return d.to_bytes(accent)


def _flow_blocks(payload: dict[str, str], hp: int) -> list[dict[str, str]]:
    align = payload.get("align", "left")
    blocks: list[dict[str, str]] = []
    for raw in (payload.get("body_text") or "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            blocks.append({"kind": "gap", "text": "", "align": align})
            continue
        stripped = line.strip()
        if stripped.startswith("- ") or stripped == "-":
            blocks.append({"kind": "bullet", "text": stripped[2:].strip(),
                           "align": align})
            continue
        blocks.append({"kind": "para", "text": stripped, "align": align})
    return blocks


def export_document_docx(payload: dict[str, str], title: str,
                         when: date | None = None) -> Path:
    stem = paths.safe_stem(title, "Document", when)
    out = paths.unique_path(paths.output_dir("documents"), stem, ".docx")
    out.write_bytes(render_document_docx_bytes(payload))
    return out
