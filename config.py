"""
DERB MOBILE - configuration.

Central place for branding, filesystem layout and server settings.
Everything here is offline-safe: no network endpoints, no cloud config.
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "derb.db"
PHOTOS_DIR = DATA_DIR / "photos"
# Graphic Design uploads (multiple images per job) live beside the database.
DESIGN_IMAGES_DIR = DATA_DIR / "design_images"

# Passport photographs and design images are stored locally next to the DB.
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# Local document tree (the folder structure the operator transfers to a PC).
DERB_ROOT = Path(os.environ.get("DERB_OUTPUT_DIR", BASE_DIR / "DERB"))

# Optional, gitignored files the operator may create on the device to hold
# local settings - typically the AI provider key, so it never has to be typed
# into a shell command (which would land in the shell history). They are read
# only by load_local_env(), called from app.py - never imported by the modules
# the tests exercise, so the test suite stays hermetic.
LOCAL_ENV_FILES = (BASE_DIR / ".env", BASE_DIR / ".env.local")


def load_local_env(path: Path | None = None) -> list[str]:
    """Load ``DERB_*`` settings from a local, gitignored env file.

    Real environment variables always win: an explicitly exported value is
    never overwritten, so this is a convenience for on-device setup, not a
    second hidden configuration layer. Only keys prefixed ``DERB_`` are
    honoured, so a stray file can never rewrite ``PATH`` or anything else.

    Returns the names of the keys that were applied - never the values, so
    callers can report what was picked up without printing a secret.
    """
    candidates = (path,) if path else LOCAL_ENV_FILES
    applied: list[str] = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            value = value.strip().strip('"').strip("'")
            if not key.startswith("DERB_") or key in os.environ or not value:
                continue
            os.environ[key] = value
            applied.append(key)
    return applied

# --------------------------------------------------------------------------
# Branding
# --------------------------------------------------------------------------
BRAND_COMPANY = "DERB FINANCE CONCEPTS"
BRAND_PRODUCT = "DERB MOBILE"
BRAND_TAGLINE = "Offline Document Studio"
BRAND_VERSION = "1.0.0"
BRAND_PHASE = "Phase 6 - Official Services"

# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------
HOST = os.environ.get("DERB_HOST", "0.0.0.0")
PORT = int(os.environ.get("DERB_PORT", "8080"))
DEBUG = os.environ.get("DERB_DEBUG", "0") == "1"

# Android browsers sometimes keep stale assets; keep a cache-busting token.
ASSET_VERSION = os.environ.get("DERB_ASSET_VERSION", BRAND_VERSION)

# Maximum upload size for passport photographs (kept small for low-spec phones).
MAX_CONTENT_LENGTH = 6 * 1024 * 1024  # 6 MB

# NOTE: the Official Services catalog (names, descriptions and the verified
# police/government portal links) lives in core/official_services.py - not
# here - because it is content, not configuration. Card avatars are generated
# offline from the service name, so this app still makes no network request
# of its own.
