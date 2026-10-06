"""
Filesystem helpers for DERB MOBILE.

Responsibilities:
  * create and verify the local document tree (the DERB/ folder),
  * build safe, human-friendly filenames such as:
        Chinedu_Okafor_CV_2026-10-05.pdf
  * keep every write inside DERB_ROOT (no path traversal).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

from config import DERB_ROOT

# The document tree. Adding a new service later only means adding a key here.
DOC_TREE = {
    "cv": ("CV", "Projects"),
    "cv_pdf": ("CV", "PDF"),
    "cv_docx": ("CV", "DOCX"),
    "letters": ("Letters",),
    "documents": ("Documents",),
    "school": ("School",),
    "business": ("Business",),
    "passport": ("Passport",),
    "templates": ("Templates",),
}

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MULTI_US = re.compile(r"_+")
_MULTI_DASH = re.compile(r"-+")


def ensure_tree() -> Path:
    """Create the DERB document tree if it does not exist. Idempotent."""
    for parts in DOC_TREE.values():
        (DERB_ROOT.joinpath(*parts)).mkdir(parents=True, exist_ok=True)
    return DERB_ROOT


def output_dir(key: str) -> Path:
    """Return the output directory for a service key, creating it if needed."""
    parts = DOC_TREE.get(key)
    if parts is None:
        raise KeyError(f"Unknown document location: {key!r}")
    path = DERB_ROOT.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str, *, fallback: str = "Untitled") -> str:
    """Turn arbitrary text into an underscore-safe filename component."""
    if not value:
        return fallback
    # Normalise accents so 'Chukwuemeka' style names survive, then strip.
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    value = value.strip().replace(" ", "_")
    value = _SAFE_CHARS.sub("_", value)
    value = _MULTI_US.sub("_", value).strip("._-")
    return value or fallback


def safe_stem(customer_name: str, doc_type: str = "CV", when: date | None = None) -> str:
    """
    Build the readable filename stem used across PDF/DOCX/project files.

    Example: 'Chinedu Okafor', 'CV', 2026-10-05
             -> 'Chinedu_Okafor_CV_2026-10-05'
    """
    when = when or date.today()
    name = slugify(customer_name, fallback="Customer")
    kind = slugify(doc_type, fallback="Doc")
    return f"{name}_{kind}_{when.isoformat()}"


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """
    Return a path inside *directory* that does not yet exist.

    Collisions get an incrementing counter: Name_CV_2026-10-05_2.pdf
    """
    directory = Path(directory)
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def stamp() -> str:
    """Local timestamp used for 'created'/'modified' bookkeeping."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
