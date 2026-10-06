"""
DOCX export for DERB MOBILE - standard library only.

python-docx needs lxml, which cannot compile on this Termux toolchain (see
docs/DECISIONS.md). A .docx file is a ZIP of XML parts, so this module writes
a genuinely editable Word document with zipfile + xml.etree only:

    [Content_Types].xml            part map (incl. png/jpeg photo support)
    _rels/.rels                    package relationships
    word/document.xml              the CV content, styled per template
    word/styles.xml                Word-native styles + template accent colour
    word/media/photo.<ext>         the customer's passport photo, when present
    word/_rels/document.xml.rels   document relationships (image)

The three template identities are preserved through style profiles that mirror
core/cv_pdf.py: professional (accent header band), modern (accent contact
block), simple (Times, black & white).

Photos: PNG and JPEG are embedded (Word cannot display WebP, so those are
skipped rather than producing a broken picture).
"""

from __future__ import annotations

import io
import struct
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any

import config
from core import cv_model, paths

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"

CONTENT_TYPES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CT_NS}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

ROOT_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_RELS_NO_IMAGE = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}">
</Relationships>"""


# ---------------------------------------------------------------------------
# Template style profiles (mirror cv_pdf.PROFILES)
# ---------------------------------------------------------------------------
PROFILES: dict[str, dict[str, Any]] = {
    "professional": {
        "serif": "Calibri", "header_bar": True, "sidebar": False,
        "name_size": 40, "body_size": 20,
    },
    "modern": {
        "serif": "Calibri", "header_bar": False, "sidebar": True,
        "name_size": 40, "body_size": 20,
    },
    "simple": {
        "serif": "Times New Roman", "header_bar": False, "sidebar": False,
        "name_size": 38, "body_size": 21,
    },
}
DEFAULT_PROFILE = "professional"


def _profile_for(template: dict[str, Any]) -> dict[str, Any]:
    return PROFILES.get(template.get("layout") or "", PROFILES[DEFAULT_PROFILE])


def _accent(template: dict[str, Any]) -> str:
    hexv = (template.get("accent") or "#123a72").lstrip("#")
    if len(hexv) != 6:
        hexv = "123a72"
    return hexv.upper()


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------
def _register_namespaces() -> None:
    ET.register_namespace("w", W_NS)
    ET.register_namespace("r", R_NS)
    ET.register_namespace("a", A_NS)
    ET.register_namespace("pic", PIC_NS)
    ET.register_namespace("wp", WP_NS)


def _el(tag: str, **attrs: str) -> ET.Element:
    """A w:-namespaced element. Attributes become w:-namespaced too."""
    e = ET.Element(f"w:{tag}")
    for k, v in attrs.items():
        e.set(f"w:{k}", v)
    return e


def _sub(parent: ET.Element, tag: str, **attrs: str) -> ET.Element:
    e = _el(tag, **attrs)
    parent.append(e)
    return e


def _wp(parent: ET.Element, tag: str) -> ET.Element:
    return ET.SubElement(parent, f"{{{WP_NS}}}{tag}")


# ---------------------------------------------------------------------------
# styles.xml - Word-native, editable styles carrying the template identity
# ---------------------------------------------------------------------------
def _styles_xml(template: dict[str, Any]) -> bytes:
    accent = _accent(template)
    serif = str(_profile_for(template)["serif"])
    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:docDefaults>
    <w:rPrDefault><w:rPr>
      <w:rFonts w:ascii="{serif}" w:hAnsi="{serif}"/>
      <w:sz w:val="21"/><w:szCs w:val="21"/>
      <w:color w:val="1F2430"/>
    </w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="80" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:styleId="CVSection">
    <w:name w:val="CV Section"/>
    <w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/>
      <w:pBdr><w:bottom w:val="single" w:sz="8" w:space="2" w:color="{accent}"/></w:pBdr></w:pPr>
    <w:rPr><w:b/><w:caps/><w:sz w:val="22"/><w:color w:val="{accent}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="CVEntry">
    <w:name w:val="CV Entry"/>
    <w:pPr><w:keepNext/><w:spacing w:after="20"/></w:pPr>
    <w:rPr><w:b/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="CVMeta">
    <w:name w:val="CV Meta"/>
    <w:pPr><w:spacing w:after="60"/></w:pPr>
    <w:rPr><w:i/><w:color w:val="5A6472"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="CVBody">
    <w:name w:val="CV Body"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="CVBullet">
    <w:name w:val="CV Bullet"/>
    <w:pPr><w:ind w:left="284" w:hanging="170"/></w:pPr>
    <w:rPr><w:color w:val="2A3140"/></w:rPr>
  </w:style>
</w:styles>"""
    return xml.encode()


# ---------------------------------------------------------------------------
# document.xml builder
# ---------------------------------------------------------------------------
class _Docx:
    def __init__(self, template: dict[str, Any]):
        self.template = template
        self.profile = _profile_for(template)
        self.accent = _accent(template)
        self.body = ET.Element("w:body")
        self.has_image = False
        self.photo_bytes: tuple[bytes, str] | None = None

    # -- runs / paragraphs ----------------------------------------------------
    def run(self, text: str, *, bold: bool = False, italic: bool = False,
            size: int | None = None, color: str | None = None) -> ET.Element:
        r = _el("r")
        rpr = _sub(r, "rPr")
        if bold:
            _sub(rpr, "b")
        if italic:
            _sub(rpr, "i")
        if size:
            _sub(rpr, "sz", val=str(size))
            _sub(rpr, "szCs", val=str(size))
        if color:
            _sub(rpr, "color", val=color)
        t = _sub(r, "t")
        t.text = text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return r

    def para(self, *runs: ET.Element, style: str | None = None,
             shade: str | None = None) -> ET.Element:
        p = _el("p")
        ppr = _sub(p, "pPr")
        if style:
            _sub(ppr, "pStyle", val=style)
        if shade:
            shd = ET.SubElement(ppr, f"{{{W_NS}}}shd")
            shd.set(f"{{{W_NS}}}val", "clear")
            shd.set(f"{{{W_NS}}}color", "auto")
            shd.set(f"{{{W_NS}}}fill", shade)
        for r in runs:
            p.append(r)
        self.body.append(p)
        return p

    def bullet(self, text: str) -> None:
        p = _el("p")
        ppr = _sub(p, "pPr")
        _sub(ppr, "pStyle", val="CVBullet")
        p.append(self.run("\u2022  ", bold=True, color=self.accent))
        p.append(self.run(text))
        self.body.append(p)

    # -- photo ----------------------------------------------------------------
    def photo(self, cv: dict[str, Any]) -> None:
        filename = (cv.get("photo") or "").strip()
        if not filename:
            return
        path = config.PHOTOS_DIR / filename
        if not path.is_file():
            return
        ext = path.suffix.lower().lstrip(".")
        if ext not in ("png", "jpg", "jpeg"):
            return  # Word cannot render webp; skip rather than embed a broken image
        data = path.read_bytes()
        if not data:
            return
        try:
            width_px, height_px = _image_size(data, ext)
        except Exception:
            return
        if not width_px or not height_px:
            return

        target_emu_w = 1188720  # 3.3 cm
        target_emu_h = int(height_px * target_emu_w / width_px)

        p = _el("p")
        _sub(_sub(p, "pPr"), "spacing", after="160")
        r = _sub(p, "r")
        drawing = ET.SubElement(r, f"{{{WP_NS}}}drawing")
        inline = _wp(drawing, "inline")
        inline.set("distT", "0"); inline.set("distB", "0")
        inline.set("distL", "0"); inline.set("distR", "0")
        extent = _wp(inline, "extent")
        extent.set("cx", str(target_emu_w)); extent.set("cy", str(target_emu_h))
        docpr = _wp(inline, "docPr")
        docpr.set("id", "1"); docpr.set("name", "Passport Photo")
        graphic = ET.SubElement(inline, f"{{{A_NS}}}graphic")
        graphic_data = ET.SubElement(graphic, f"{{{A_NS}}}graphicData")
        graphic_data.set("uri", "http://schemas.openxmlformats.org/drawingml/2006/picture")
        pic = ET.SubElement(graphic_data, f"{{{PIC_NS}}}pic")
        nv = ET.SubElement(pic, f"{{{PIC_NS}}}nvPicPr")
        cnv = ET.SubElement(nv, f"{{{PIC_NS}}}cNvPr")
        cnv.set("id", "1"); cnv.set("name", "photo")
        ET.SubElement(nv, f"{{{PIC_NS}}}cNvPicPr")
        blip_fill = ET.SubElement(pic, f"{{{PIC_NS}}}blipFill")
        blip = ET.SubElement(blip_fill, f"{{{A_NS}}}blip")
        blip.set(f"{{{R_NS}}}embed", "rIdPhoto1")
        stretch = ET.SubElement(blip_fill, f"{{{A_NS}}}stretch")
        ET.SubElement(stretch, f"{{{A_NS}}}fillRect")
        sp_pr = ET.SubElement(pic, f"{{{PIC_NS}}}spPr")
        xfrm = ET.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
        off = ET.SubElement(xfrm, f"{{{A_NS}}}off")
        off.set("x", "0"); off.set("y", "0")
        ext2 = ET.SubElement(xfrm, f"{{{A_NS}}}ext")
        ext2.set("cx", str(target_emu_w)); ext2.set("cy", str(target_emu_h))
        prst = ET.SubElement(sp_pr, f"{{{A_NS}}}prstGeom")
        prst.set("prst", "rect")
        ET.SubElement(prst, f"{{{A_NS}}}avLst")
        self.body.append(p)
        self.has_image = True
        self.photo_bytes = (data, "jpeg" if ext == "jpg" else ext)

    # -- sections / page setup -------------------------------------------------
    def sect_pr(self) -> None:
        sect = _sub(self.body, "sectPr")
        _sub(sect, "pgSz", w="11906", h="16838")  # A4 in twips
        _sub(sect, "pgMar", top="1134", right="1134", bottom="1134", left="1134",
             header="708", footer="708", gutter="0")

    # -- finish ------------------------------------------------------------------
    def to_bytes(self) -> bytes:
        _register_namespaces()
        body_xml = ET.tostring(self.body, encoding="unicode")
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}" '
            f'xmlns:wp="{WP_NS}" xmlns:a="{A_NS}" xmlns:pic="{PIC_NS}" '
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
            + body_xml + "</w:document>"
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("word/document.xml", document.encode())
            z.writestr("word/styles.xml", _styles_xml(self.template))
            if self.has_image and self.photo_bytes:
                data, ext = self.photo_bytes
                z.writestr(f"word/media/photo.{ext}", data)
                z.writestr(
                    "word/_rels/document.xml.rels",
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<Relationships xmlns="{PKG_REL_NS}">'
                    '<Relationship Id="rIdPhoto1" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    f'Target="media/photo.{ext}"/>'
                    "</Relationships>",
                )
            else:
                z.writestr("word/_rels/document.xml.rels", _DOC_RELS_NO_IMAGE)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Image header sniffing (png / jpeg) - enough for a passport photo
# ---------------------------------------------------------------------------
def _image_size(data: bytes, ext: str) -> tuple[int, int]:
    if ext == "png":
        # PNG: IHDR width/height start at byte 16.
        w = struct.unpack(">I", data[16:20])[0]
        h = struct.unpack(">I", data[20:24])[0]
        return w, h
    if ext in ("jpg", "jpeg"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = (data[i + 5] << 8) | data[i + 6]
                w = (data[i + 7] << 8) | data[i + 8]
                return w, h
            seg_len = (data[i + 2] << 8) | data[i + 3]
            if seg_len <= 0:
                break
            i += 2 + seg_len
        return 0, 0
    return 0, 0


# ---------------------------------------------------------------------------
# Content builders - the customer's real data, ordered per template
# ---------------------------------------------------------------------------
def _add_header(d: _Docx, cv: dict[str, Any]) -> None:
    p = d.profile
    contacts = "  |  ".join(cv_model.contact_items(cv))

    if p["header_bar"]:
        # Professional: accent band echoed as paragraph shading, white text.
        d.para(d.run(cv_model.display_name(cv), bold=True, size=40, color="FFFFFF"),
               shade=d.accent)
        role = cv_model.professional_title(cv)
        if role:
            d.para(d.run(role, italic=True, size=22, color="FFFFFF"), shade=d.accent)
        if contacts:
            d.para(d.run(contacts, size=18, color="E8EDF8"), shade=d.accent)
        bio = "  |  ".join(cv_model.bio_items(cv))
        if bio:
            d.para(d.run(bio, size=18, color="5A6472"))
        return

    d.para(d.run(cv_model.display_name(cv), bold=True, size=p["name_size"],
                 color="111827"))
    role = cv_model.professional_title(cv)
    if role:
        d.para(d.run(role, italic=True, size=22, color=d.accent))
    if not p["sidebar"]:
        address = (cv["personal"].get("address") or "").strip()
        if address:
            d.para(d.run(address, size=18, color="3A4150"))
    if contacts:
        d.para(d.run(contacts, size=18, color="3A4150"))
    if not p["sidebar"]:
        bio = "  |  ".join(cv_model.bio_items(cv))
        if bio:
            d.para(d.run(bio, size=18, color="5A6472"))
    if p["sidebar"]:
        # Modern: contact block carries the accent, like the HTML sidebar.
        bits = []
        if cv["personal"].get("state_of_origin"):
            bits.append(f'{cv["personal"]["state_of_origin"]} State')
        if cv["personal"].get("lga"):
            bits.append(f'{cv["personal"]["lga"]} LGA')
        if cv["personal"].get("nationality"):
            bits.append(cv["personal"]["nationality"])
        if cv["personal"].get("date_of_birth"):
            bits.append(f'Born: {cv["personal"]["date_of_birth"]}')
        if cv["personal"].get("gender"):
            bits.append(cv["personal"]["gender"])
        if bits:
            d.para(d.run("  |  ".join(bits), size=18, color=d.accent))


def _section(d: _Docx, title: str) -> None:
    d.para(d.run(title), style="CVSection")


def _entry_head(d: _Docx, lead: str, meta: str) -> None:
    d.para(d.run(lead), style="CVEntry")
    if meta:
        d.para(d.run(meta), style="CVMeta")


def _body(d: _Docx, cv: dict[str, Any]) -> None:
    p = d.profile

    if cv["profile"].get("profile"):
        _section(d, "Profile" if p["sidebar"] else "Professional Profile")
        d.para(d.run(cv["profile"]["profile"]), style="CVBody")
    if cv["profile"].get("objective"):
        _section(d, "Career Objective")
        d.para(d.run(cv["profile"]["objective"]), style="CVBody")

    if cv["experience"]:
        _section(d, "Experience" if p["sidebar"] else "Work Experience")
        for e in cv["experience"]:
            meta = " - ".join(x for x in (e.get("start_date"), e.get("end_date")) if x)
            if p["sidebar"]:
                lead = (f'{e.get("position") or "Position"}'
                        f'{" - " + e["company"] if e.get("company") else ""}')
                _entry_head(d, lead.strip(" -"), meta)
            else:
                _entry_head(d, e.get("position") or "Position", meta)
                if e.get("company"):
                    d.para(d.run(e["company"], size=20, color="3A4150"), style="CVBody")
            for line in cv_model.responsibilities_list(e.get("responsibilities", "")):
                d.bullet(line)

    if cv["education"]:
        _section(d, "Education")
        for ed in cv["education"]:
            course = f' in {ed.get("course")}' if ed.get("course") else ""
            meta = " - ".join(x for x in (ed.get("start_year"), ed.get("end_year")) if x)
            lead = (f'{ed.get("qualification", "")}{course}'
                    f'{" - " + ed["institution"] if ed.get("institution") else ""}')
            _entry_head(d, lead.strip(" -"), meta)

    if cv["skills"]:
        _section(d, "Skills")
        d.para(d.run("  |  ".join(s["name"] for s in cv["skills"] if s.get("name"))),
               style="CVBody")
    if cv["certifications"]:
        _section(d, "Certifications")
        for c in cv["certifications"]:
            bits = [c.get("name", "")]
            if c.get("issuer"):
                bits.append(c["issuer"])
            if c.get("year"):
                bits.append(f"({c['year']})")
            d.bullet(" - ".join(b for b in bits if b))
    if cv["languages"]:
        _section(d, "Languages")
        d.para(d.run("  |  ".join(l["name"] for l in cv["languages"] if l.get("name"))),
               style="CVBody")
    if cv["references"]:
        _section(d, "References")
        for r in cv["references"]:
            line1 = ", ".join(b for b in (r.get("name"), r.get("title"),
                                          r.get("organisation")) if b)
            line2 = "  |  ".join(b for b in (r.get("phone"), r.get("email")) if b)
            d.para(d.run(line1, bold=True, size=20))
            if line2:
                d.para(d.run(line2, size=18, color="5A6472"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_docx_bytes(cv: dict[str, Any], template: dict[str, Any]) -> bytes:
    """Render the customer's CV to .docx bytes using the template's style."""
    cv = cv_model.normalize(cv)
    d = _Docx(template)
    d.photo(cv)
    _add_header(d, cv)
    _body(d, cv)
    d.sect_pr()
    return d.to_bytes()


def export_docx(cv: dict[str, Any], template: dict[str, Any],
                when: date | None = None) -> Path:
    """Write the DOCX into DERB/CV/DOCX and return its path."""
    stem = paths.safe_stem(cv_model.display_name(cv), "CV", when)
    out = paths.unique_path(paths.output_dir("cv_docx"), stem, ".docx")
    out.write_bytes(render_docx_bytes(cv, template))
    return out
