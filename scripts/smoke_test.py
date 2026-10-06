#!/usr/bin/env python3
"""
DERB MOBILE - smoke test.

Checks every Phase 1 & 2 deliverable through the real Flask app (not by
importing internals), so it exercises exactly what the phone browser will hit.

Run:
    python scripts/smoke_test.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

passes = 0
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global passes
    if condition:
        passes += 1
        print(f"  [PASS] {label}")
    else:
        failures.append(f"{label}{(' -> ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    print("DERB MOBILE - smoke test")
    print("-" * 52)

    # ---------------------------------------------------------------- storage
    print("Storage")
    from config import DB_PATH
    from core import db, paths, templates_repo

    # Run the same bootstrap the app runs on startup.
    db.init_db()

    check("SQLite database file created", DB_PATH.exists(), str(DB_PATH))
    tree_ok = all(
        paths.output_dir(key).exists()
        for key in ("cv", "cv_pdf", "cv_docx", "letters", "documents",
                    "school", "business", "passport", "templates")
    )
    check("DERB document tree created", tree_ok, str(paths.DERB_ROOT))

    templates = templates_repo.list_templates("CV")
    slugs = sorted(t["slug"] for t in templates)
    check("3 built-in CV templates seeded", len(templates) >= 3,
          f"found {len(templates)}: {slugs}")
    for expected in ("professional-cv", "modern-cv", "simple-cv"):
        check(f"Template present: {expected}", expected in slugs)
    check("Default template is professional-cv",
          templates_repo.get_setting("default_cv_template") == "professional-cv")

    # ------------------------------------------------------------------ safety
    print("Filename safety")
    stem = paths.safe_stem("Chinedu Okafor", "CV")
    check("Safe filename stem format", stem.count("_") >= 2 and stem.startswith("Chinedu_Okafor_CV_"),
          stem)
    check("Dangerous characters stripped",
          paths.slugify("../../etc/pa ss wd!") == "etc_pa_ss_wd",
          paths.slugify("../../etc/pa ss wd!"))

    # ------------------------------------------------------------------- http
    print("HTTP routes (via Flask test client)")
    from web import create_app

    app = create_app()
    client = app.test_client()

    routes = ["/", "/about", "/health", "/cv", "/letters", "/documents",
              "/school", "/business", "/passport", "/saved", "/templates",
              "/settings"]
    for route in routes:
        resp = client.get(route)
        check(f"GET {route} -> 200", resp.status_code == 200,
              f"status {resp.status_code}")

    home = client.get("/").get_data(as_text=True)
    check("Dashboard shows company name", "DERB FINANCE CONCEPTS" in home)
    check("Dashboard shows product name", "DERB MOBILE" in home)
    for title in ("CV / Resume", "Letters", "Documents", "School Documents",
                  "Business Documents", "Passport Photos", "Saved Work",
                  "Templates", "Settings"):
        check(f"Dashboard tile: {title}", title in home)

    health = client.get("/health").get_json()
    check("/health reports offline mode", health.get("offline") is True)
    check("/health reports template count", health.get("templates", 0) >= 3)

    check("Unknown route -> 404", client.get("/does-not-exist").status_code == 404)

    # -------------------------------------------------------------- responsive
    print("Mobile presentation")
    css = (PROJECT_ROOT / "static" / "css" / "app.css").read_text()
    check("Viewport meta present", 'name="viewport"' in (PROJECT_ROOT / "templates" / "base.html").read_text())
    check("Touch targets defined (>=48px)", "--tap: 48px" in css)
    check("Small-screen breakpoint present", "min-width: 420px" in css)
    check("No external font/CDN references",
          "http://" not in css and "https://" not in css)

    print("-" * 52)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("All Phase 1 & 2 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
