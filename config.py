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
