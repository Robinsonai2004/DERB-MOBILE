"""
Local image store for the Graphic Design workspace.

Images are saved next to the database (config.DESIGN_IMAGES_DIR) under an
unguessable name, exactly like the CV passport-photo flow in web/cv.py - but
this one accepts several images per job, which a design needs (logo, guest
minister, product...). Everything stays local: no upload leaves the phone.

Only PNG/JPEG/WebP are accepted (config.ALLOWED_PHOTO_EXT) and the stored name
is generated, never taken from the client, so a hostile filename cannot escape
the folder.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

import config

_SAFE_FILE = re.compile(r"^[A-Za-z0-9._-]+$")

# Magic bytes, so an image can be validated without Pillow (which cannot build
# on this Termux toolchain - see docs/DECISIONS.md). Used to check provider
# responses before they are stored or shown to the operator.
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)
# Formats the app is willing to store and serve.
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def ensure_dir() -> Path:
    config.DESIGN_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return config.DESIGN_IMAGES_DIR


def sniff_image_ext(data: bytes) -> str | None:
    """Return the real image extension from the bytes, or None if not an image."""
    if not data or len(data) < 12:
        return None
    for magic, ext in _MAGIC:
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def save_bytes(data: bytes, ext: str, *, prefix: str = "design") -> str:
    """Store raw image bytes under a generated name; return the filename (or '').

    Used for AI-generated artwork, which arrives as bytes rather than an
    upload. The name is always generated, never taken from the client.
    """
    if not data:
        return ""
    ext = ext if ext in IMAGE_EXT else (sniff_image_ext(data) or ".png")
    ensure_dir()
    name = f"{prefix}_{secrets.token_hex(8)}{ext}"
    (config.DESIGN_IMAGES_DIR / name).write_bytes(data)
    return name


def size_of(filename: str) -> int | None:
    """Stored size in bytes, or None when the file is missing/unsafe."""
    try:
        path = path_for(filename)
    except ValueError:
        return None
    return path.stat().st_size if path.is_file() else None


def save_upload(upload) -> str:
    """Store one uploaded image; return its stored filename (or '')."""
    if upload is None or not getattr(upload, "filename", ""):
        return ""
    ext = Path(upload.filename).suffix.lower()
    if ext not in config.ALLOWED_PHOTO_EXT:
        return ""
    ensure_dir()
    name = f"design_{secrets.token_hex(8)}{ext}"
    upload.save(config.DESIGN_IMAGES_DIR / name)
    return name


def save_uploads(files, roles: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Store several uploads (one per FileStorage); return image records.

    ``roles`` maps the stored filename to an optional role/caption.
    """
    roles = roles or {}
    out: list[dict[str, str]] = []
    for upload in files:
        name = save_upload(upload)
        if name:
            out.append({"filename": name, "role": (roles.get(name) or "").strip()[:60]})
    return out


def is_safe_name(filename: str) -> bool:
    return bool(filename) and bool(_SAFE_FILE.match(filename))


def path_for(filename: str) -> Path:
    """Absolute path for a stored image, or None-ish if the name is unsafe."""
    if not is_safe_name(filename):
        raise ValueError("unsafe filename")
    return config.DESIGN_IMAGES_DIR / filename


def delete_image(filename: str) -> None:
    try:
        path = path_for(filename)
    except ValueError:
        return
    try:
        path.unlink()
    except OSError:
        pass


def delete_images(filenames: list[str]) -> None:
    for name in filenames:
        delete_image(name)


def image_records(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Existing images referenced by a payload (filenames only)."""
    out = []
    for item in payload.get("images") or []:
        name = item.get("filename", "")
        if name:
            out.append({"filename": name, "role": item.get("role", "")})
    return out
