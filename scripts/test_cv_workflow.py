#!/usr/bin/env python3
"""
DERB MOBILE - Phase 3 end-to-end workflow test.

Walks the exact workflow a customer would:

    dashboard -> CV templates -> choose template -> editor -> preview
              -> save project -> Saved Work (search) -> preview -> duplicate
              -> delete

Fictional sample data only. Every project it creates is deleted again, so the
real Saved Work list is left exactly as it was found.

Run:
    python scripts/test_cv_workflow.py
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
    print("DERB MOBILE - Phase 3 CV workflow test")
    print("-" * 58)

    from core import cv_model, db, projects_repo

    db.init_db()
    from web import create_app

    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    starting_count = projects_repo.count_projects()
    created_ids: list[int] = []

    sample = cv_model.sample_cv()
    form = cv_model.to_form_data(sample)

    # ---------------------------------------------------------------- step 1
    print("Step 1-4  CV / Resume -> template list")
    page = client.get("/cv").get_data(as_text=True)
    check("Template page loads", "Choose a CV Template" in page)
    for name in ("Professional CV", "Modern CV", "Simple CV"):
        check(f"Template card shown: {name}", name in page)
    check("Use Template button present", page.count("Use Template") >= 3)
    check("Live thumbnails rendered", page.count("sheet sheet--") >= 3)

    dash = client.get("/").get_data(as_text=True)
    check("Dashboard links to CV templates", 'href="/cv/"' in dash or 'href="/cv"' in dash)

    # -------------------------------------------------- step 5-8: each template
    print("Step 5-8  Every template opens the editor and previews the data")
    layouts = {
        "professional-cv": "sheet--professional",
        "modern-cv": "sheet--modern",
        "simple-cv": "sheet--simple",
    }
    previews: dict[str, str] = {}
    for slug, sheet_class in layouts.items():
        editor = client.get(f"/cv/new?template={slug}")
        body = editor.get_data(as_text=True)
        check(f"Editor opens for {slug}", editor.status_code == 200)
        check(f"  editor shows selected template", f'value="{slug}" selected' in body
              or f"{slug}\" selected" in body)

        payload = dict(form)
        payload["template_slug"] = slug
        resp = client.post("/cv/preview", data=payload)
        html = resp.get_data(as_text=True)
        previews[slug] = html
        check(f"Preview renders for {slug}", resp.status_code == 200 and sheet_class in html)
        check(f"  preview shows customer name", "Chinedu A. Okafor" in html)
        check(f"  preview shows experience", "Zenith Bank Plc" in html)
        check(f"  preview shows education", "University of Port Harcourt" in html)
        check(f"  preview shows skills", "Financial Reporting" in html)
        check(f"  preview shows certifications", "ICAN Skills Certification" in html)
        check(f"  preview shows languages", "Igbo (Native)" in html)
        check(f"  preview shows references", "Dr. Grace Okoro" in html)
        check(f"  preview shows objective", "reputable organisation" in html)

    check("Templates produce different layouts",
          len({previews[s] for s in layouts}) == 3)

    # ---------------------------------------------------------------- saving
    print("Step 9  Save the project")
    payload = dict(form)
    payload["template_slug"] = "modern-cv"
    saved = client.post("/cv/save", data=payload, follow_redirects=False)
    check("Save redirects to the editor", saved.status_code in (302, 303),
          f"status {saved.status_code}")

    match = [p for p in projects_repo.list_projects("Chinedu") if p["customer_name"] == sample["personal"]["full_name"]]
    check("Project persisted in SQLite", bool(match))
    if match:
        project = match[0]
        created_ids.append(project["id"])
        check("Customer name stored", project["customer_name"] == "Chinedu A. Okafor",
              project["customer_name"])
        check("Template stored", project["template_slug"] == "modern-cv")
        check("CV JSON reloads with all sections",
              len(project["cv"]["education"]) == 2
              and len(project["cv"]["experience"]) == 2
              and len(project["cv"]["skills"]) == 5
              and len(project["cv"]["references"]) == 2)
        check("Responsibilities preserved",
              "Reconcile bank" in project["cv"]["experience"][0]["responsibilities"])

        pid = project["id"]
        editor = client.get(f"/cv/{pid}/edit").get_data(as_text=True)
        check("Saved project reopens in editor", "Chinedu A. Okafor" in editor)
        check("Saved project shows repeatable rows",
              editor.count('name="education[') >= 5 and editor.count('name="experience[') >= 5)

        # ---------------------------------------------------- step 10: saved work
        print("Step 10  Saved Work and search")
        listing = client.get("/saved").get_data(as_text=True)
        check("Project appears in Saved Work", "Chinedu A. Okafor" in listing)
        check("Listing shows document type", "CV" in listing)
        check("Listing shows template used", "Modern CV" in listing)
        check("Listing shows created date", "Created" in listing)
        check("Listing shows modified date", "Modified" in listing)

        found = client.get("/saved?q=Chinedu").get_data(as_text=True)
        check("Search by name finds the project", "Chinedu A. Okafor" in found)
        missing = client.get("/saved?q=Zzzzznomatch").get_data(as_text=True)
        check("Search hides non-matches", "Chinedu A. Okafor" not in missing)
        check("Empty search message shown", "No saved projects match" in missing)

        # ------------------------------------------------------------ preview
        resp = client.get(f"/cv/{pid}/preview")
        prev = resp.get_data(as_text=True)
        check("Saved project preview works",
              resp.status_code == 200 and "Chinedu A. Okafor" in prev)

        # ---------------------------------------------------------- duplicate
        client.post(f"/cv/{pid}/duplicate")
        copies = [p for p in projects_repo.list_projects("(Copy)")]
        check("Duplicate creates a copy", any("(Copy)" in c["customer_name"] for c in copies))
        created_ids.extend(c["id"] for c in copies if "Chinedu" in c["customer_name"])

    # ------------------------------------------------------------- validation
    print("Validation")
    blank = client.post("/cv/save", data={"template_slug": "professional-cv"},
                        follow_redirects=True)
    check("Saving without a name is rejected",
          "full name" in blank.get_data(as_text=True).lower())
    check("Rejected save creates no project",
          not any(p["customer_name"] == "Untitled Customer"
                  for p in projects_repo.list_projects()))
    check("Missing project preview -> 404", client.get("/cv/999999/preview").status_code == 404)
    check("Missing project edit -> 404", client.get("/cv/999999/edit").status_code == 404)

    # ---------------------------------------------------------------- cleanup
    print("Cleanup")
    for pid in set(created_ids):
        client.post(f"/cv/{pid}/delete")
    final_count = projects_repo.count_projects()
    check("Test projects removed", final_count == starting_count,
          f"started {starting_count}, now {final_count}")

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("Phase 3 CV workflow verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
