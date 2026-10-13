"""
Settings screen for DERB MOBILE.

    GET  /settings                     -> this device's settings
    POST /settings/ai-features         -> switch AI features on / off
    POST /settings/ai-features/check   -> probe the AI provider (no image is
                                          generated, so it costs nothing)

The only "real" setting today is the **Switch to AI Features** preference,
which the Graphic Design workspace reads before offering its AI finishing
workflow. It is stored in the existing key/value `settings` table (the same
one that holds the default CV template) - no new storage, no migration.

Nothing here is allowed to guess: the screen reports exactly one of the honest
states in core/ai_service.status() (off, not configured, unavailable, ready).
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

import config
from core import ai_service, paths, registry

bp = Blueprint("settings", __name__)


def _context(**extra) -> dict:
    """Everything the settings page needs, including the honest AI state."""
    from core.db import DB_PATH

    return {
        "service": registry.get_service("settings"),
        "status": ai_service.status(),
        "ai_env_keys": ai_service.ENV_KEYS,
        "db_path": str(DB_PATH),
        "documents_root": str(paths.DERB_ROOT),
        "brand_version": config.BRAND_VERSION,
        **extra,
    }


@bp.route("/settings", strict_slashes=False)
def index():
    return render_template("pages/settings.html", **_context())


@bp.route("/settings/ai-features", methods=["POST"])
def ai_features():
    """Turn AI finishing on or off. The preference is what gets persisted."""
    enable = (request.form.get("ai_features") or "").strip().lower() in {
        "1", "on", "true", "yes", "enable",
    }
    ai_service.set_preference(enable)

    if not enable:
        flash("AI features switched off. Graphic Design works exactly as before.")
    elif not ai_service.load_config().configured:
        flash("AI features switched on, but no provider API key is configured "
              "on this device yet - so AI finishing cannot run until one is set.",
              "error")
    else:
        flash("AI features switched on. \"Finish with AI\" is now available in "
              "the Graphic Design workspace.")
    return redirect(url_for("settings.index"))


@bp.route("/settings/ai-features/check", methods=["POST"])
def ai_check():
    """Probe the provider so the operator sees a real, current answer."""
    result = ai_service.check_connection()
    if result["ok"]:
        flash(result["message"])
    else:
        flash(result["message"], "error")
    return redirect(url_for("settings.index"))
