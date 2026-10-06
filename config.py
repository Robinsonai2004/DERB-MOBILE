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

# Passport photographs are stored locally next to the database.
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
BRAND_PHASE = "Phase 5 - Letters & Documents"

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
