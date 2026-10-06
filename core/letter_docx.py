"""
Letter / document DOCX export - standard library only.

Reuses the Phase 4 OOXML building blocks (core/cv_docx) so letters produce a
genuinely editable Word file with the same package layout, styles approach and
A4 section settings as the CV export.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from core import paths
from core.cv_docx import (W_NS, _accent, _el, _register_namespaces, _sub)
import io
import zipfile
import xml.etree.ElementTree as ET

from core.cv_docx import CONTENT_TYPES, ROOT_RELS, _DOC_RELS_NO_IMAGE, _styles_xml


class _LetterDocx:
    def __init__(self, accent: str, serif: bool):
        self.accent = accent
        self.body = ET.Element("w:body")

    # -- helpers ---------------------------------------------------------------
    def run(self, text: str, *, bold: bool = False, italic: bool = False,
            size: int = 21, color: str | None = None, caps: bool = False):
        r = _el("r")
        rpr = _sub(r, "rPr")
        if bold:
            _sub(rpr, "b")
        if italic:
            _sub(rpr, "i")
        if caps:
            _sub(rpr, "caps")
        _sub(rpr, "sz", val=str(size))
        _sub(rpr, "szCs", val=str(size))
        if color:
            _sub(rpr, "color", val=color)
        t = _sub(r, "t")
        t.text = text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return r

    def para(self, *runs, align: str | None = None,
             spacing_after: int = 80, keep_next: bool = False,
             top_border: bool = False):
        p = _el("p")
        ppr = _sub(p, "pPr")
        if keep_next:
            _sub(ppr, "keepNext")
        _sub(ppr, "spacing", after=str(spacing_after))
        if align:
            _sub(ppr, "jc", val=align)
        if top_border:
            border = ET.SubElement(ppr, f"{{{W_NS}}}pBdr")
            top = ET.SubElement(border, f"{{{W_NS}}}top")
            top.set(f"{{{W_NS}}}val", "single")
            top.set(f"{{{W_NS}}}sz", "8")
            top.set(f"{{{W_NS}}}space", "4")
            top.set(f"{{{W_NS}}}color", self.accent)
        for r in runs:
            p.append(r)
        self.body.append(p)
        return p

    def signature(self, name: str, role: str):
        self.para(self.run("________________________"), spacing_after=20)
        self.para(self.run(name, bold=True, size=20), spacing_after=10)
        if role:
            self.para(self.run(role, italic=True, size=18, color="5A6472"),
                      spacing_after=140)

    def sect_pr(self):
        sect = _sub(self.body, "sectPr")
        _sub(sect, "pgSz", w="11906", h="16838")
        _sub(sect, "pgMar", top="1134", right="1134", bottom="1134", left="1134",
             header="708", footer="708", gutter="0")

    def to_bytes(self, accent: str, serif: bool) -> bytes:
        _register_namespaces()
        body_xml = ET.tostring(self.body, encoding="unicode")
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}" '
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
            + body_xml + "</w:document>"
        )
        # Reuse the CV style-sheet builder so Word styles stay consistent.
        tpl = {"accent": "#" + accent.lower(), "layout": "simple" if serif
               else "professional"}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("word/document.xml", document.encode())
            z.writestr("word/styles.xml", _styles_xml(tpl))
            z.writestr("word/_rels/document.xml.rels", _DOC_RELS_NO_IMAGE)
        return buf.getvalue()


def render_letter_docx_bytes(doc_struct: dict[str, Any]) -> bytes:
    accent = _accent({"accent": doc_struct.get("accent") or "#123a72"})
    serif = bool(doc_struct.get("serif"))
    d = _LetterDocx(accent, serif)
    body_color = "1F2430"
    meta_color = "5A6472"

    # title + rule
    d.para(d.run(doc_struct["title"], bold=True, size=28, color=accent, caps=True),
           align="center", spacing_after=40, keep_next=True)
    d.para(d.run(" "), spacing_after=40, top_border=True)

    if doc_struct.get("date"):
        d.para(d.run(f"Date: {doc_struct['date']}", size=20, color=meta_color),
               align="right", spacing_after=120)

    recipient = doc_struct.get("recipient")
    if recipient:
        d.para(d.run("To:", bold=True, size=20), spacing_after=10, keep_next=True)
        for line in recipient:
            d.para(d.run(line, size=20), spacing_after=10)
        d.para(d.run(" "), spacing_after=120)

    if doc_struct.get("salutation"):
        d.para(d.run(doc_struct["salutation"] + ","), spacing_after=80)

    if doc_struct.get("opening"):
        d.para(d.run(doc_struct["opening"]), spacing_after=120)

    for idx, clause in enumerate(doc_struct.get("clauses", []), start=1):
        d.para(d.run(f"{idx}. {clause['heading']}", bold=True, size=21,
                     color=accent, caps=True),
               spacing_after=40, keep_next=True)
        for label, value in clause["items"]:
            d.para(d.run(f"{label}: ", bold=True, size=20),
                   d.run(value, size=20, color=body_color), spacing_after=60)

    if doc_struct.get("closing"):
        d.para(d.run(doc_struct["closing"]), spacing_after=160)
        if doc_struct.get("letter_signer"):
            d.signature(doc_struct["letter_signer"]["name"], "")

    for signer in doc_struct.get("signers", []):
        d.signature(signer["name"], signer["role"])

    witnesses = doc_struct.get("witnesses", [])
    if witnesses:
        d.para(d.run("WITNESSES", bold=True, size=21, color=accent, caps=True),
               spacing_after=40, keep_next=True)
        for i, wit in enumerate(witnesses, start=1):
            d.signature(wit["name"], f"Witness {i}")

    if doc_struct.get("disclaimer"):
        d.para(d.run("Note: " + doc_struct["disclaimer"], italic=True, size=16,
                     color=meta_color), spacing_after=0)

    d.sect_pr()
    return d.to_bytes(accent, serif)


def export_letter_docx(doc_struct: dict[str, Any], customer_name: str,
                       when: date | None = None) -> Path:
    stem = paths.safe_stem(customer_name, "Letter", when)
    out = paths.unique_path(paths.output_dir("letters"), stem, ".docx")
    out.write_bytes(render_letter_docx_bytes(doc_struct))
    return out
