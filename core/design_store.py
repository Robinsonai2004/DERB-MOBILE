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


def ensure_dir() -> Path:
    config.DESIGN_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return config.DESIGN_IMAGES_DIR


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
