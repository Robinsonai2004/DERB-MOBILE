"""
PDF export for DERB MOBILE - standard library only.

Why not fpdf2 / ReportLab? See docs/DECISIONS.md: they pull in Pillow, which
cannot compile on this Termux toolchain. This writer emits a real PDF 1.4 file
(A4 page box, built-in fonts, flowable blocks, automatic page breaks) with zero
dependencies, so export works offline on the phone.

Templates keep their identity through a style profile:

    professional  navy rules + accent section titles, Helvetica
    modern        teal sidebar strip on page 1, Helvetica
    simple        black & white, Times, single column

Text is limited to the built-in font character set (WinAnsi); anything outside
it is transliterated and the preview screen already tells the operator this.
"""

from __future__ import annotations

import unicodedata
import zlib
from datetime import date
from pathlib import Path
from typing import Any

from core import cv_model, paths

# ---------------------------------------------------------------------------
# Page geometry (A4, points)
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = 595.28, 841.89
MARGIN = 46.0
TOP_MARGIN = 50.0
BOTTOM_MARGIN = 54.0
CONTENT_W = PAGE_W - 2 * MARGIN

# Built-in PDF fonts: (name, widths-file). Metrics are Adobe AFM standard.
FONTS = {
    "helvetica": "Helvetica",
    "helvetica-bold": "Helvetica-Bold",
    "helvetica-oblique": "Helvetica-Oblique",
    "times": "Times-Roman",
    "times-bold": "Times-Bold",
    "times-italic": "Times-Italic",
    "courier": "Courier",
}

# WinAnsiEncoding widths (per 1000 units) for the characters we emit.
_W = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, "0": 556, "1": 556, "2": 556, "3": 556, "4": 556,
    "5": 556, "6": 556, "7": 556, "8": 556, "9": 556, ":": 278, ";": 278,
    "<": 584, "=": 584, ">": 584, "?": 556, "@": 1015, "A": 667, "B": 667,
    "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722, "I": 278,
    "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778, "P": 667,
    "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, "[": 278, "\\": 278, "]": 278, "^": 469,
    "_": 556, "`": 333, "a": 556, "b": 556, "c": 500, "d": 556, "e": 556,
    "f": 278, "g": 556, "h": 556, "i": 222, "j": 222, "k": 500, "l": 222,
    "m": 833, "n": 556, "o": 556, "p": 556, "q": 556, "r": 333, "s": 500,
    "t": 278, "u": 556, "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
    "{": 334, "|": 260, "}": 334, "~": 584,
}
# Helvetica-Bold differs for these glyphs only.
_W_BOLD_OVERRIDES = {
    " ": 278, "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333,
    "g": 611, "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889,
    "n": 611, "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333,
    "u": 611, "v": 556, "w": 778, "x": 556, "y": 556, "z": 500,
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 389, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556,
    "7": 556, "8": 556, "9": 556, ".": 278, ",": 278, "-": 333, ":": 333,
    "(": 333, ")": 333, "/": 278, "&": 722, "'": 238, "!": 333, "?": 611,
    "|": 280, "•": 350,
}

_TRANS = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u2022": "-",
    "\u00a0": " ", "\u2212": "-", "\u00b7": "-",
}


def _winansi(text: str) -> str:
    """Map anything outside the built-in character set to a safe glyph."""
    out = []
    for ch in text:
        if ch in _TRANS:
            out.append(_TRANS[ch])
        elif 32 <= ord(ch) <= 126 or ch in ("\u2018", "\u2019", "\u201c",
                                            "\u201d", "\u2013", "\u2014",
                                            "\u2022", "\u00b7"):
            out.append(ch)
        else:
            decomposed = unicodedata.normalize("NFKD", ch)
            stripped = "".join(c for c in decomposed if 32 <= ord(c) <= 126)
            out.append(stripped or "")
    return "".join(out)


def _width(text: str, font: str, size: float) -> float:
    table = _W_BOLD_OVERRIDES if "bold" in font or "Bold" in font else _W
    return sum(table.get(c, 556) for c in text) * size / 1000.0


def _esc(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


# ---------------------------------------------------------------------------
# Style profiles - keep each template's identity in the exported file
# ---------------------------------------------------------------------------
def _rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = (hex_color or "#123a72").lstrip("#")
    if len(hex_color) != 6:
        hex_color = "123a72"
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


PROFILES: dict[str, dict[str, Any]] = {
    "professional": {
        "serif": False, "sidebar": False, "header_bar": True,
        "name_size": 22, "title_size": 9.5, "body_size": 9.5,
        "rule_above_title": True, "title_in_accent": True,
    },
    "modern": {
        "serif": False, "sidebar": True, "header_bar": False,
        "name_size": 22, "title_size": 9.5, "body_size": 9.5,
        "rule_above_title": False, "title_in_accent": False,
    },
    "simple": {
        "serif": True, "sidebar": False, "header_bar": False,
        "name_size": 19, "title_size": 11, "body_size": 10.5,
        "rule_above_title": True, "title_in_accent": False,
    },
}
DEFAULT_PROFILE = "professional"


def _profile_for(template: dict[str, Any]) -> dict[str, Any]:
    return PROFILES.get(template.get("layout") or "", PROFILES[DEFAULT_PROFILE])


# ---------------------------------------------------------------------------
# Block model: the CV is reduced to flowable blocks, then laid out into pages
# ---------------------------------------------------------------------------
class _Doc:
    """Collects text operations and splits them into A4 pages."""

    def __init__(self, accent: str, profile: dict[str, Any], template_name: str):
        self.accent = _rgb(accent)
        self.profile = profile
        self.template_name = template_name
        self.pages: list[list[str]] = [[]]
        self.y = PAGE_H - TOP_MARGIN
        self.page_no = 1
        self.total_pages = 1

    # -- low level -----------------------------------------------------------
    def _ops(self) -> list[str]:
        return self.pages[-1]

    def _new_page(self) -> None:
        self.pages.append([])
        self.page_no += 1
        self.total_pages = self.page_no
        self.y = PAGE_H - TOP_MARGIN

    def space_needed(self, height: float) -> bool:
        return self.y - height >= BOTTOM_MARGIN

    def ensure(self, height: float) -> None:
        if not self.space_needed(height):
            self._new_page()

    def text(self, x: float, y: float, s: str, font: str, size: float,
             color: tuple[float, float, float] | None = None) -> None:
        color = color or (0.1, 0.1, 0.12)
        r, g, b = color
        self._ops().append(
            f"BT /{font} {size:.1f} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"{x:.2f} {y:.2f} Td ({_esc(_winansi(s))}) Tj ET"
        )

    def rect_fill(self, x: float, y: float, w: float, h: float,
                  color: tuple[float, float, float]) -> None:
        r, g, b = color
        self._ops().append(
            f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f"
        )

    def line(self, x1: float, y1: float, x2: float, y2: float,
             color: tuple[float, float, float], width: float = 0.8) -> None:
        r, g, b = color
        self._ops().append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w "
            f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

    def wrap(self, s: str, font: str, size: float, width: float) -> list[str]:
        words = _winansi(s).split()
        if not words:
            return [""]
        lines, current = [], words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if _width(trial, font, size) <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def paragraph(self, s: str, font: str, size: float, leading: float,
                  width: float = CONTENT_W, indent: float = 0.0,
                  color: tuple[float, float, float] | None = None) -> None:
        for line in self.wrap(s, font, size, width - indent):
            self.ensure(leading)
            self.text(MARGIN + indent, self.y - size, line, font, size, color)
            self.y -= leading

    def bullets(self, items: list[str], font: str, size: float,
                leading: float, color: tuple[float, float, float] | None = None,
                dot: str = "\u2022") -> None:
        for item in items:
            lines = self.wrap(item, font, size, CONTENT_W - 14)
            for i, line in enumerate(lines):
                self.ensure(leading)
                if i == 0:
                    self.text(MARGIN + 2, self.y - size, dot, font, size, color)
                self.text(MARGIN + 14, self.y - size, line, font, size)
                self.y -= leading

    def section_title(self, s: str) -> None:
        p = self.profile
        gap_before = 10 if self.page_no > 1 or self.y < PAGE_H - TOP_MARGIN - 2 else 4
        self.y -= gap_before
        self.ensure(20)
        if p["serif"]:
            font = "times-bold"
        else:
            font = "helvetica-bold"
        color = self.accent if p["title_in_accent"] else (0.08, 0.08, 0.1)
        if p["rule_above_title"]:
            self.line(MARGIN, self.y + 3, MARGIN + CONTENT_W, self.y + 3,
                      self.accent, 1.1)
            self.y -= 4
        self.text(MARGIN, self.y - p["title_size"], s.upper(), font,
                  p["title_size"], color)
        self.y -= p["title_size"] + 6

    def footer(self) -> None:
        """Page numbers + a light brand line on every page."""
        for idx, ops in enumerate(self.pages, start=1):
            y = 30
            ops.append(
                f"BT /helvetica 7.5 Tf 0.45 0.45 0.5 rg {MARGIN:.2f} {y} Td "
                f"({_esc(_winansi(f'DERB FINANCE CONCEPTS  -  {self.template_name}'))}) Tj ET"
            )
            label = f"Page {idx} of {len(self.pages)}"
            w = _width(label, "helvetica", 7.5)
            ops.append(
                f"BT /helvetica 7.5 Tf 0.45 0.45 0.5 rg "
                f"{PAGE_W - MARGIN - w:.2f} {y} Td ({_esc(label)}) Tj ET"
            )

    # -- output --------------------------------------------------------------
    def build(self) -> bytes:
        """Serialise pages into a valid PDF 1.4 byte string."""
        self.footer()
        n_pages = len(self.pages)

        # Object numbering: 1 = catalog, then one per font, then per page a
        # content-stream object followed by its page object, then Pages.
        catalog_num = 1
        first_font_num = 2
        first_page_num = first_font_num + len(FONTS)
        pages_num = first_page_num + n_pages

        page_objects: list[int] = []
        content_nums: list[int] = []
        for i in range(n_pages):
            content_num = pages_num + 1 + i * 2
            content_nums.append(content_num)
            page_objects.append(content_num + 1)

        final: dict[int, bytes] = {
            catalog_num: f"<< /Type /Catalog /Pages {pages_num} 0 R >>".encode()
        }
        num = first_font_num
        for alias in FONTS:
            final[num] = (
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{FONTS[alias]} "
                f"/Encoding /WinAnsiEncoding >>"
            ).encode()
            num += 1
        for i, ops in enumerate(self.pages):
            stream = "\n".join(ops).encode("latin-1", "replace")
            comp = zlib.compress(stream)
            content_obj = (
                f"<< /Length {len(comp)} /Filter /FlateDecode >>\nstream\n".encode()
                + comp + b"\nendstream"
            )
            final[content_nums[i]] = content_obj
            page_obj = (
                f"<< /Type /Page /Parent {pages_num} 0 R "
                f"/MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] /Resources << /Font << "
                + " ".join(f"/{a} {first_font_num + j} 0 R" for j, a in enumerate(FONTS))
                + " >> >> /Contents " + f"{content_nums[i]} 0 R >>"
            ).encode()
            final[content_nums[i] + 1] = page_obj
        kids = " ".join(f"{n} 0 R" for n in page_objects)
        final[pages_num] = (
            f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>"
        ).encode()

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: dict[int, int] = {}
        max_num = max(final)
        for obj_num in range(1, max_num + 1):
            offsets[obj_num] = len(out)
            body = final.get(obj_num, b"<< >>")
            out += f"{obj_num} 0 obj\n".encode() + body + b"\nendobj\n"
        xref_at = len(out)
        out += f"xref\n0 {max_num + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for obj_num in range(1, max_num + 1):
            out += f"{offsets[obj_num]:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {max_num + 1} /Root {catalog_num} 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF"
        ).encode()
        return bytes(out)


# ---------------------------------------------------------------------------
# Header renderers - one per template identity
# ---------------------------------------------------------------------------
def _header(d: _Doc, cv: dict[str, Any], template: dict[str, Any]) -> None:
    p = d.profile
    name_font = "times-bold" if p["serif"] else "helvetica-bold"
    body_font = "times" if p["serif"] else "helvetica"

    if p["header_bar"]:
        d.rect_fill(0, PAGE_H - TOP_MARGIN - 8, PAGE_W, TOP_MARGIN + 8, d.accent)
        d.y = PAGE_H - TOP_MARGIN + 14
        d.text(MARGIN, d.y, cv_model.display_name(cv), "helvetica-bold",
               p["name_size"], (1, 1, 1))
        d.y -= p["name_size"] + 4
        role = cv_model.professional_title(cv)
        if role:
            d.text(MARGIN, d.y, role, "helvetica-oblique", 10.5, (0.88, 0.91, 1))
            d.y -= 14
        contacts = "  |  ".join(cv_model.contact_items(cv))
        if contacts:
            for line in d.wrap(contacts, "helvetica", 8.5, CONTENT_W):
                d.text(MARGIN, d.y, line, "helvetica", 8.5, (0.9, 0.92, 1))
                d.y -= 11
        d.y -= 6
        return

    if p["sidebar"]:
        strip_w = 10
        d.rect_fill(0, PAGE_H - TOP_MARGIN - 6, strip_w, TOP_MARGIN + 6, d.accent)
        d.text(MARGIN + strip_w + 6, d.y - p["name_size"],
               cv_model.display_name(cv), name_font, p["name_size"], d.accent)
        d.y -= p["name_size"] + 5
        role = cv_model.professional_title(cv)
        if role:
            d.text(MARGIN + strip_w + 6, d.y, role, body_font + "-oblique"
                   if not p["serif"] else "times-italic", 11)
            d.y -= 14
        contacts = "  |  ".join(cv_model.contact_items(cv))
        if contacts:
            for line in d.wrap(contacts, body_font, 9, CONTENT_W - strip_w - 6):
                d.text(MARGIN + strip_w + 6, d.y, line, body_font, 9)
                d.y -= 12
        bio = "  |  ".join(cv_model.bio_items(cv))
        if bio:
            for line in d.wrap(bio, body_font, 8.5, CONTENT_W - strip_w - 6):
                d.text(MARGIN + strip_w + 6, d.y, line, body_font, 8.5,
                       (0.35, 0.38, 0.42))
                d.y -= 11
        d.y -= 8
        d.line(MARGIN + strip_w + 6, d.y, PAGE_W - MARGIN, d.y, d.accent, 1.4)
        d.y -= 10
        return

    # simple / plain
    d.text(MARGIN, d.y - p["name_size"], cv_model.display_name(cv),
           name_font, p["name_size"])
    d.y -= p["name_size"] + 4
    role = cv_model.professional_title(cv)
    if role:
        d.text(MARGIN, d.y, role, "times-italic" if p["serif"] else "helvetica-oblique", 11)
        d.y -= 14
    address = (cv["personal"].get("address") or "").strip()
    if address:
        d.paragraph(address, body_font, 9, 11)
    contacts = "  |  ".join(cv_model.contact_items(cv))
    if contacts:
        for line in d.wrap(contacts, body_font, 9, CONTENT_W):
            d.text(MARGIN, d.y, line, body_font, 9)
            d.y -= 12
    bio = "  |  ".join(cv_model.bio_items(cv))
    if bio:
        for line in d.wrap(bio, body_font, 8.5, CONTENT_W):
            d.text(MARGIN, d.y, line, body_font, 8.5, (0.35, 0.38, 0.42))
            d.y -= 11
    d.y -= 4
    d.line(MARGIN, d.y, MARGIN + CONTENT_W, d.y, (0, 0, 0), 1.2)
    d.y -= 8


# ---------------------------------------------------------------------------
# Body renderers - the customer's real data, template-ordered
# ---------------------------------------------------------------------------
def _body(d: _Doc, cv: dict[str, Any]) -> None:
    p = d.profile
    head_font = "times-bold" if p["serif"] else "helvetica-bold"
    body_font = "times" if p["serif"] else "helvetica"
    size = p["body_size"]
    leading = size + 3.2

    if p["sidebar"]:
        _body_modern(d, cv)
        return

    # profile / objective
    if cv["profile"].get("profile"):
        d.section_title("Professional Profile")
        d.paragraph(cv["profile"]["profile"], body_font, size, leading)
    if cv["profile"].get("objective"):
        d.section_title("Career Objective")
        d.paragraph(cv["profile"]["objective"], body_font, size, leading)

    # experience
    if cv["experience"]:
        d.section_title("Work Experience")
        for e in cv["experience"]:
            title = f'{e.get("position") or "Position"}'
            meta = " - ".join(x for x in (e.get("start_date"), e.get("end_date")) if x)
            line = f"{title}  ({meta})" if meta else title
            d.ensure(leading * 2)
            d.text(MARGIN, d.y - size, line, head_font, size)
            d.y -= leading
            if e.get("company"):
                d.text(MARGIN, d.y - size, e["company"], body_font, size, (0.3, 0.32, 0.36))
                d.y -= leading
            resp = cv_model.responsibilities_list(e.get("responsibilities", ""))
            if resp:
                d.bullets(resp, body_font, size - 0.5, leading - 0.8)
            d.y -= 3

    # education
    if cv["education"]:
        d.section_title("Education")
        for ed in cv["education"]:
            lead_bits = [b for b in (ed.get("qualification"), ed.get("course")) if b]
            meta = " - ".join(x for x in (ed.get("start_year"), ed.get("end_year")) if x)
            line = " - ".join([(" in ".join(lead_bits))] if lead_bits else [])
            if meta:
                line = f"{line}  ({meta})" if line else meta
            d.ensure(leading * 2)
            if line:
                d.text(MARGIN, d.y - size, line, head_font, size)
                d.y -= leading
            if ed.get("institution"):
                d.text(MARGIN, d.y - size, ed["institution"], body_font, size,
                       (0.3, 0.32, 0.36))
                d.y -= leading
            d.y -= 1

    # skills / languages as dot-separated inline lists
    if cv["skills"]:
        d.section_title("Skills")
        d.paragraph("  |  ".join(s["name"] for s in cv["skills"] if s.get("name")),
                    body_font, size, leading)
    if cv["certifications"]:
        d.section_title("Certifications")
        for c in cv["certifications"]:
            bits = [c.get("name", "")]
            if c.get("issuer"):
                bits.append(c["issuer"])
            if c.get("year"):
                bits.append(f"({c['year']})")
            d.bullets([" - ".join(b for b in bits if b)], body_font, size, leading)
    if cv["languages"]:
        d.section_title("Languages")
        d.paragraph("  |  ".join(l["name"] for l in cv["languages"] if l.get("name")),
                    body_font, size, leading)
    if cv["references"]:
        d.section_title("References")
        for r in cv["references"]:
            line1 = ", ".join(b for b in (r.get("name"), r.get("title"),
                                          r.get("organisation")) if b)
            line2 = "  |  ".join(b for b in (r.get("phone"), r.get("email")) if b)
            d.ensure(leading * 2)
            d.text(MARGIN, d.y - size, line1, head_font, size - 0.5)
            d.y -= leading - 1
            if line2:
                d.text(MARGIN, d.y - size, line2, body_font, size - 0.5,
                       (0.3, 0.32, 0.36))
                d.y -= leading - 1
            d.y -= 2


def _body_modern(d: _Doc, cv: dict[str, Any]) -> None:
    """Modern layout: experience/education/profile flow; skills etc. inline
    after a 'Sidebar details' block so nothing from the sidebar is lost."""
    size = d.profile["body_size"]
    body_font = "helvetica"
    leading = size + 3.2

    if cv["profile"].get("profile"):
        d.section_title("Profile")
        d.paragraph(cv["profile"]["profile"], body_font, size, leading)
    if cv["profile"].get("objective"):
        d.section_title("Career Objective")
        d.paragraph(cv["profile"]["objective"], body_font, size, leading)

    if cv["experience"]:
        d.section_title("Experience")
        for e in cv["experience"]:
            meta = " - ".join(x for x in (e.get("start_date"), e.get("end_date")) if x)
            line = f'{e.get("position") or "Position"}  -  {e.get("company", "")}'
            if meta:
                line = f"{line}  ({meta})"
            d.ensure(leading * 2)
            d.text(MARGIN, d.y - size, line.strip("  -"), "helvetica-bold", size)
            d.y -= leading
            resp = cv_model.responsibilities_list(e.get("responsibilities", ""))
            if resp:
                d.bullets(resp, body_font, size - 0.5, leading - 0.8)
            d.y -= 3

    if cv["education"]:
        d.section_title("Education")
        for ed in cv["education"]:
            course = f' in {ed["course"]}' if ed.get("course") else ""
            meta = " - ".join(x for x in (ed.get("start_year"), ed.get("end_year")) if x)
            line = f'{ed.get("qualification", "")}{course}  -  {ed.get("institution", "")}'
            if meta:
                line = f"{line}  ({meta})"
            d.ensure(leading)
            d.text(MARGIN, d.y - size, line.strip("  -"), "helvetica-bold", size)
            d.y -= leading
            d.y -= 1

    if cv["skills"]:
        d.section_title("Skills")
        d.paragraph("  |  ".join(s["name"] for s in cv["skills"] if s.get("name")),
                    body_font, size, leading)
    if cv["certifications"]:
        d.section_title("Certifications")
        for c in cv["certifications"]:
            bits = [c.get("name", "")]
            if c.get("year"):
                bits.append(f"({c['year']})")
            d.bullets([" ".join(b for b in bits if b)], body_font, size, leading)
    if cv["languages"]:
        d.section_title("Languages")
        d.paragraph("  |  ".join(l["name"] for l in cv["languages"] if l.get("name")),
                    body_font, size, leading)
    if cv["references"]:
        d.section_title("References")
        for r in cv["references"]:
            line1 = ", ".join(b for b in (r.get("name"), r.get("title"),
                                          r.get("organisation")) if b)
            line2 = "  |  ".join(b for b in (r.get("phone"), r.get("email")) if b)
            d.ensure(leading * 2)
            d.text(MARGIN, d.y - size, line1, "helvetica-bold", size - 0.5)
            d.y -= leading - 1
            if line2:
                d.text(MARGIN, d.y - size, line2, body_font, size - 0.5,
                       (0.3, 0.32, 0.36))
                d.y -= leading - 1
            d.y -= 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def render_pdf_bytes(cv: dict[str, Any], template: dict[str, Any]) -> bytes:
    """Render the customer's CV to PDF bytes using the template's style."""
    cv = cv_model.normalize(cv)
    profile_key = template.get("layout") or DEFAULT_PROFILE
    profile = PROFILES.get(profile_key, PROFILES[DEFAULT_PROFILE])
    d = _Doc(template.get("accent") or "#123a72", profile,
             template.get("name") or "CV")
    _header(d, cv, template)
    _body(d, cv)
    if d.page_no == 1 and not d.pages[-1]:
        pass  # header always emits ops, so this cannot happen in practice
    return d.build()


def export_pdf(cv: dict[str, Any], template: dict[str, Any],
               when: date | None = None) -> Path:
    """Write the PDF into DERB/CV/PDF and return its path."""
    stem = paths.safe_stem(cv_model.display_name(cv), "CV", when)
    out = paths.unique_path(paths.output_dir("cv_pdf"), stem, ".pdf")
    out.write_bytes(render_pdf_bytes(cv, template))
    return out
