"""
Flask application factory for DERB MOBILE.
"""

from __future__ import annotations

from flask import Flask, render_template

import config
from core import db, paths


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.BASE_DIR / "templates"),
        static_folder=str(config.BASE_DIR / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["JSON_SORT_KEYS"] = False
    app.secret_key = "derb-mobile-offline-local-key"  # local-only; no remote sessions

    # Storage + document tree are ready before the first request.
    db.init_db()

    _register_blueprints(app)
    _register_context(app)
    _register_errors(app)
    return app


def _register_blueprints(app: Flask) -> None:
    from web.cv import bp as cv_bp
    from web.dashboard import bp as dashboard_bp
    from web.documents import bp as documents_bp
    from web.letters import bp as letters_bp
    from web.saved import bp as saved_bp
    from web.services import bp as services_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(cv_bp)
    app.register_blueprint(letters_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(saved_bp)


def _register_context(app: Flask) -> None:
    @app.context_processor
    def inject_branding():
        return {
            "brand_company": config.BRAND_COMPANY,
            "brand_product": config.BRAND_PRODUCT,
            "brand_tagline": config.BRAND_TAGLINE,
            "brand_version": config.BRAND_VERSION,
            "brand_phase": config.BRAND_PHASE,
            "asset_version": config.ASSET_VERSION,
            "derb_root": str(paths.DERB_ROOT),
        }


def _register_errors(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_err):
        return render_template("pages/message.html", code="404",
                               heading="Page not found",
                               message="That screen does not exist in DERB MOBILE."), 404

    @app.errorhandler(413)
    def too_large(_err):
        return render_template("pages/message.html", code="413",
                               heading="File too large",
                               message="Please choose a smaller image (under 6 MB)."), 413

    @app.errorhandler(500)
    def server_error(_err):  # pragma: no cover - defensive
        return render_template("pages/message.html", code="500",
                               heading="Something went wrong",
                               message="Please go back and try again."), 500
