"""
Document data model for DERB MOBILE.

The Document screen is the free-format workspace for text a customer brings
in to be typed (speech, essay, assignment, report, minutes, messages...).
This module is the single source of truth for "what is a Document":

    * normalize() is the ONLY producer of the payload stored in the `projects`
      table (doc_type='DOCUMENT') - no schema changes are needed;
    * content is stored as plain-text lines plus the operator's chosen font
      size and alignment, and the same payload feeds the editor, the HTML
      preview, the PDF writer and the DOCX writer, so the outputs cannot
      drift apart;
    * sanitisation keeps the pipeline offline-safe: anything pasted from a
      web page is reduced to text (no scripts, no remote images, no event
      handlers), which preserves DERB's no-CDN guarantee by construction.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

from core import paths

# ---------------------------------------------------------------------------
# The single font-size scale used by the toolbar and both export engines.
# Keys follow the historical HTML font sizes; SIZE_PT maps them to points for
# the PDF engine (the DOCX engine converts points to Word half-points).
# ---------------------------------------------------------------------------
SIZES = (2, 3, 4, 5, 6, 7)
DEFAULT_SIZE = 3
SIZE_PT = {2: 10.5, 3: 12.0, 4: 14.0, 5: 18.0, 6: 22.0, 7: 28.0}

_ALIGN_ENUM = ("left", "center", "right")

_TR = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ",
    "\u2022": "- ", "\u00b7": "-", "\u2212": "-",
}
_SCRIPT_RE = re.compile(r"<script\b.*?</script\s*>", re.I | re.S)
_STYLE_RE = re.compile(r"<style\b.*?</style\s*>", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_EVENT_RE = re.compile(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_TAG_RE = re.compile(r"</?\w+[^>]*>")


def _plain(value: Any) -> str:
    """Reduce anything the browser/paste gave us to safe single-spaced text."""
    text = value if isinstance(value, str) else ""
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    text = _COMMENT_RE.sub("", text)
    # Block boundaries become line breaks before the tags are removed.
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|section|article|blockquote)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "\n- ", text)
    text = _TAG_RE.sub("", text)
    text = _EVENT_RE.sub("", text)
    text = _html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(_TR.get(ch, ch) for ch in text)
    # Printable characters only (control characters other than \n are noise).
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or 32 <= ord(ch) <= 0x2FFF)
    out: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if line == "-":
            line = "- "
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")  # a blank line is intentional paragraph spacing
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def plain(value: str) -> str:
    """Public wrapper of _plain, for save-time sanitisation of typed text."""
    return _plain(value)


def blank_payload() -> dict[str, str]:
    """The payload every new editor starts from."""
    return normalize({})


def normalize(data: Any) -> dict[str, str]:
    """Fill in anything missing so renderers never hit KeyError."""
    if not isinstance(data, dict):
        data = {}
    try:
        size = int(data.get("size", DEFAULT_SIZE))
    except (TypeError, ValueError):
        size = DEFAULT_SIZE
    if size not in SIZE_PT:
        size = DEFAULT_SIZE
    align = data.get("align", "left")
    align = align if align in _ALIGN_ENUM else "left"
    title = (str(data.get("title", "") or "")).strip()
    body = _plain(data.get("body_text", data.get("content", "")))
    return {
        "title": title,
        "body_text": body,
        "size": str(size),
        "align": align,
    }


def parse_form(form) -> dict[str, str]:
    """Build the payload from the editor form submission."""
    return normalize(
        {
            "title": form.get("title", ""),
            "body_text": form.get("body_text", ""),
            "size": form.get("size", DEFAULT_SIZE),
            "align": form.get("align", "left"),
        }
    )


def adjust(dst: dict[str, str], **changes: Any) -> dict[str, str]:
    """Return a copy of *dst* with size/align changes applied."""
    payload = dict(dst)
    payload.update({k: v for k, v in changes.items() if k in ("size", "align")})
    return normalize(payload)


# ---------------------------------------------------------------------------
# Display helpers (shared by editor, preview, exports and the Saved list)
# ---------------------------------------------------------------------------
def display_title(payload: dict[str, str], fallback: str = "Untitled Document") -> str:
    """Operator's title, else the first body line, else a neutral label."""
    title = (payload.get("title") or "").strip()
    if title:
        return title
    for raw_line in (payload.get("body_text") or "").split("\n"):
        line = raw_line.strip()
        if line:
            return line[:80]
    return fallback


def is_empty(payload: dict[str, str]) -> bool:
    """True when there is nothing worth saving yet."""
    return not (payload.get("body_text") or "").strip()


def filled_summary(payload: dict[str, str]) -> dict[str, int]:
    """Small counters for the Saved Work list rows."""
    lines = [ln for ln in (payload.get("body_text") or "").split("\n") if ln.strip()]
    return {
        "lines": len(lines),
        "words": sum(len(ln.split()) for ln in lines),
    }


def summary_line(payload: dict[str, str], limit: int = 120) -> str:
    """First body line for list rows / previews."""
    for raw_line in (payload.get("body_text") or "").split("\n"):
        line = raw_line.strip()
        if line:
            if len(line) > limit:
                line = line[: limit - 3].rstrip() + "..."
            return line
    return "Empty document"


def safe_filename(title: str) -> str:
    return paths.slugify(title, fallback="Document")


def formatted_preview_text(payload: dict[str, str]) -> str:
    """Body text the way the print/preview layout should show it."""
    return payload.get("body_text", "")
