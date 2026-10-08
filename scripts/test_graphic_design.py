#!/usr/bin/env python3
"""
DERB MOBILE - Graphic Design (repurposed Passport Photo slot) test.

Walks the exact workflow an operator follows for a customer:

    dashboard tile -> choose design type -> category form -> add images
                   -> generate -> preview/export -> save -> reopen -> delete

Also verifies the honest generation story (built-in layout engine is real, the
AI provider is reported as NOT connected), the reuse of the Saved Work table,
the legacy /passport redirect, and that the other services are untouched.

Fictional content only; every project and image it creates is removed again.

Run:
    python scripts/test_graphic_design.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

passes = 0
failures: list[str] = []

# A valid 1x1 PNG - stands in for a customer photo/logo.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def check(label: str, condition: bool, detail: str = "") -> None:
    global passes
    if condition:
        passes += 1
        print(f"  [PASS] {label}")
    else:
        failures.append(f"{label}{(' -> ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    print("DERB MOBILE - Graphic Design test")
    print("-" * 58)

    from config import DESIGN_IMAGES_DIR
    from core import design_catalog as catalog
    from core import design_generation, design_model, design_render, design_store
    from core import projects_repo

    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    created_ids: list[int] = []
    created_images: list[str] = []

    # ------------------------------------------------------------- catalog
    print("Catalog")
    check("Has 15 design categories", len(catalog.CATEGORIES) == 15,
          f"found {len(catalog.CATEGORIES)}")
    check("Category slugs unique",
          len({c.slug for c in catalog.CATEGORIES}) == len(catalog.CATEGORIES))
    for required in ("birthday", "anniversary", "wedding", "retirement",
                     "church-programme", "funeral", "graduation",
                     "business-advert", "product-advert", "event",
                     "social-media", "invitation", "certificate", "banner",
                     "custom"):
        check(f"Category present: {required}", required in catalog.CATEGORIES_BY_SLUG)
    for c in catalog.CATEGORIES:
        check(f"Category has fields: {c.slug}", len(c.fields) >= 3, str(len(c.fields)))
        check(f"Category theme valid: {c.slug}", c.theme in catalog.THEMES, c.theme)
        check(f"Category aspect valid: {c.slug}", c.aspect in catalog.ASPECTS, c.aspect)
    # categories must NOT share one generic form
    check("Categories have different field sets",
          len({c.fields for c in catalog.CATEGORIES}) >= 12,
          f"{len({c.fields for c in catalog.CATEGORIES})} distinct")

    # --------------------------------------------------------------- model
    print("Data model")
    blank = design_model.blank_payload("birthday")
    check("Blank payload keys",
          set(blank) == {"category", "title", "fields", "instructions", "theme", "images"})
    check("Blank category applied", blank["category"] == "birthday")
    check("Blank has only the category's fields",
          set(blank["fields"]) == set(catalog.get_category("birthday").fields))
    check("Empty detected", design_model.is_empty(blank))

    dirty = {"category": "custom", "title": "  Test  ",
             "fields": {"custom_title": "<script>alert(1)</script>Hello",
                        "custom_body": "<b>Bold</b>\nSecond"},
             "instructions": "<img src='http://x/y'>notes"}
    clean = design_model.normalize(dirty)
    check("Title trimmed", clean["title"] == "Test")
    check("Script stripped from fields",
          "<script" not in clean["fields"]["custom_title"]
          and "alert(1)" not in clean["fields"]["custom_title"])
    check("Rich text reduced to text",
          clean["fields"]["custom_body"].startswith("Bold")
          and "Second" in clean["fields"]["custom_body"])
    check("Remote image stripped from instructions",
          "http://" not in clean["instructions"])
    check("Bad category falls back", design_model.normalize({"category": "nope"})["category"]
          == catalog.CATEGORIES[0].slug)
    check("Display title uses given title", design_model.display_title(clean) == "Test")
    untitled = design_model.normalize({"category": "event", "fields": {"event_name": "Grand Show"}})
    check("Display title falls back to a field",
          design_model.display_title(untitled) == "Grand Show")
    check("Images capped",
          len(design_model.normalize({"images": [{"filename": f"x{i}.png"} for i in range(20)]})["images"])
          == design_model.MAX_IMAGES)

    # ----------------------------------------------------------- generation
    print("Generation architecture")
    status = design_generation.provider_status()
    check("Active provider is configured", status["configured"] is True, str(status))
    check("AI provider reported as NOT configured",
          design_generation.AI_PROVIDER_CONFIGURED is False)
    check("Provider note tells the operator AI is not connected",
          "not connected" in status["note"].lower() or "not connected" in status["note"])
    payload = design_model.normalize({
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "theme": "gold-white",
        "fields": {"anniversary_type": "Choir Anniversary", "organisation": "CAC",
                   "date_event": "2026-11-01", "venue": "Main Auditorium"},
        "instructions": "Gold and white, bold choir name.",
    })
    layout = design_generation.generate_design(payload)
    kinds = [b["kind"] for b in layout["blocks"]]
    check("Layout has a header", "header" in kinds, str(kinds))
    check("Layout has info rows", "info" in kinds, str(kinds))
    check("Layout has a footer", "footer" in kinds, str(kinds))
    check("Layout carries the theme palette", layout["palette"]["accent"] == "#b8860b",
          layout["palette"]["accent"])
    check("Layout aspect is portrait", abs(layout["aspect"] - 0.7071) < 0.001)
    withimg = design_generation.generate_design(
        design_model.normalize({**payload, "images": [{"filename": "a.png"}]}))
    check("Images add a gallery block",
          any(b["kind"] == "gallery" for b in withimg["blocks"]))

    # --------------------------------------------------------------- store
    print("Image store")
    check("Rejects a bad extension",
          design_store.save_upload(type("U", (), {"filename": "evil.svg", "save": lambda *a: None})()) == "")
    stored = design_store.save_upload(type("U", (), {
        "filename": "logo.png",
        "save": lambda self, dest: Path(dest).write_bytes(PNG_1X1),
    })())
    check("Stores an allowed image", stored.startswith("design_") and stored.endswith(".png"), stored)
    if stored:
        created_images.append(stored)
        check("Stored file exists", (DESIGN_IMAGES_DIR / stored).is_file())
        check("Unsafe name rejected", design_store.is_safe_name("../etc/passwd") is False)

    # ------------------------------------------------------------ chooser
    print("Category chooser (HTTP)")
    resp = client.get("/graphic-design")
    home = resp.get_data(as_text=True)
    check("GET /graphic-design -> 200", resp.status_code == 200, f"status {resp.status_code}")
    check("Chooser lists every category",
          all(c.name in home for c in catalog.CATEGORIES))
    check("Chooser links to each category form",
          all(f'category={c.slug}' in home for c in catalog.CATEGORIES))
    check("Chooser is NOT a blank editor", 'contenteditable' not in home)
    check("Design CSS served", client.get("/static/css/design.css").status_code == 200)
    check("Design JS served", client.get("/static/js/design.js").status_code == 200)
    css = (PROJECT_ROOT / "static" / "css" / "design.css").read_text()
    check("Print CSS hides chrome", "@media print" in css and ".no-print" in css)
    check("Offline CSS (no CDN)", "http://" not in css and "https://" not in css)
    js = (PROJECT_ROOT / "static" / "js" / "design.js").read_text()
    check("Offline JS (no network)", "http://" not in js and "https://" not in js)
    check("Canvas export supported", "toDataURL" in js and "design-canvas" in js)

    resp = client.get("/graphic-design/new")
    check("new without a category redirects",
          resp.status_code in (301, 302) and "/graphic-design" in resp.headers.get("Location", ""))

    # ------------------------------------------------- category-specific form
    print("Category-specific forms")
    resp = client.get("/graphic-design/new?category=anniversary")
    form = resp.get_data(as_text=True)
    check("Anniversary form -> 200", resp.status_code == 200)
    check("Anniversary asks for its own fields",
          "Type of Anniversary" in form and "Anniversary Number" in form
          and "Guest Minister" in form)
    check("Anniversary does NOT ask for Birthday fields", "Age</label>" not in form)
    check("Form has title field", 'name="title"' in form)
    check("Form has colour theme select", 'name="theme"' in form and "Gold &amp; White" in form)
    check("Form has multiple image upload", 'name="images"' in form and "multiple" in form)
    check("Form has Add Image affordance", "Add Image" in form)
    check("Form has instructions box", 'name="instructions"' in form)
    check("Form has Generate + Save", "Generate Design" in form and "Save" in form)
    check("Form keeps category", 'name="category" value="anniversary"' in form)

    resp = client.get("/graphic-design/new?category=birthday")
    bform = resp.get_data(as_text=True)
    check("Birthday form asks for its own fields", "Age" in bform and "Birthday" in bform)
    check("Birthday does NOT ask for anniversary fields",
          "Anniversary Number" not in bform)

    # every category must render its own form and generate without error
    for c in catalog.CATEGORIES:
        form_resp = client.get(f"/graphic-design/new?category={c.slug}")
        check(f"Form renders: {c.slug}", form_resp.status_code == 200,
              f"status {form_resp.status_code}")
        gen_resp = client.post(
            "/graphic-design/generate",
            data={"category": c.slug, "title": f"{c.name} demo"},
            content_type="multipart/form-data",
        )
        check(f"Generate renders: {c.slug}", gen_resp.status_code == 200,
              f"status {gen_resp.status_code}")
        check(f"Result has a poster: {c.slug}", 'id="design-poster"' in gen_resp.get_data(as_text=True))

    # ------------------------------------------------------------- generate
    print("Generate workflow (with image upload)")
    data = {
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "theme": "gold-white", "anniversary_type": "Choir Anniversary",
        "organisation": "Christ Apostolic Church", "anniversary_number": "10th",
        "theme_field": "Grace", "date_event": "2026-11-01", "venue": "Main Auditorium",
        "instructions": "Gold and white, leave space for three guest photos.",
        "images": (io.BytesIO(PNG_1X1), "guest.png"),
    }
    resp = client.post("/graphic-design/generate", data=data,
                       content_type="multipart/form-data")
    result = resp.get_data(as_text=True)
    check("Generate -> 200", resp.status_code == 200, f"status {resp.status_code}")
    check("Result shows the poster", 'id="design-poster"' in result)
    check("Result shows the title", "CAC Choir 10th Anniversary" in result)
    check("Result shows entered field", "Christ Apostolic Church" in result)
    check("Result shows the instruction text", "leave space for three guest photos" in result)
    check("Result has a print control", 'data-role="print"' in result)
    check("Result has PNG + JPG export", 'data-export="png"' in result and 'data-export="jpg"' in result)
    check("Result embeds layout JSON for export", 'id="design-layout-json"' in result)
    check("Result has Regenerate + Save", "Regenerate" in result and "Save" in result)
    check("Result notes AI provider honestly",
          "not connected" in result.lower())

    m = re.search(r'name="image_filename" value="(design_[0-9a-f]+\.png)"', result)
    check("Uploaded image kept in the result", bool(m))
    if m:
        created_images.append(m.group(1))
        check("Uploaded image served",
              client.get(f"/graphic-design/image/{m.group(1)}").status_code == 200)
    check("Unsafe image path 404s",
          client.get("/graphic-design/image/..%2fconfig.py").status_code == 404)
    # layout JSON parses and carries image urls
    jm = re.search(r'id="design-layout-json">(.*?)</script>', result, re.S)
    parsed = json.loads(jm.group(1)) if jm else {}
    gal = [b for b in parsed.get("blocks", []) if b["kind"] == "gallery"]
    check("Layout JSON has the gallery with a url",
          bool(gal) and gal[0]["images"][0]["url"].startswith("/graphic-design/image/"))

    # ------------------------------------------------------------- save/edit
    print("Save / reopen")
    save_data = {
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "theme": "gold-white", "anniversary_type": "Choir Anniversary",
        "organisation": "Christ Apostolic Church", "anniversary_number": "10th",
        "instructions": "Gold and white.",
    }
    for name in re.findall(r'name="image_filename" value="(design_[0-9a-f]+\.png)"', result):
        save_data.setdefault("image_filename", []).append(name)
    resp = client.post("/graphic-design/save", data=save_data, follow_redirects=False)
    check("Save -> redirect", resp.status_code == 302, f"status {resp.status_code}")
    loc = resp.headers.get("Location", "")
    m = re.search(r"/graphic-design/(\d+)/edit", loc)
    check("Saved design id returned", bool(m), loc)
    if not m:
        print("-" * 58)
        print(f"{passes} passed, {len(failures)} failed")
        return 1
    design_id = int(m.group(1))
    created_ids.append(design_id)

    project = projects_repo.get_project(design_id)
    check("Stored as doc_type DESIGN", project["doc_type"] == "DESIGN")
    check("Stored in the shared projects table", project["template_slug"] == "design-anniversary")
    check("Stored payload keeps the title", project["raw"]["title"] == "CAC Choir 10th Anniversary")
    check("Stored payload keeps images", bool(project["raw"]["images"]))

    resp = client.get(f"/graphic-design/{design_id}/edit")
    edit_html = resp.get_data(as_text=True)
    check("Reopen editor -> 200", resp.status_code == 200)
    check("Reopen shows the title", "CAC Choir 10th Anniversary" in edit_html)
    check("Reopen shows saved image thumbnail", "/graphic-design/image/" in edit_html)
    check("Reopen offers Preview", f"/graphic-design/{design_id}/preview" in edit_html)

    resp = client.get(f"/graphic-design/{design_id}/preview")
    preview = resp.get_data(as_text=True)
    check("Preview -> 200", resp.status_code == 200)
    check("Preview shows the poster", 'id="design-poster"' in preview)
    check("Preview shows content", "Christ Apostolic Church" in preview)

    # -------------------------------------------------------- Saved Work
    print("Saved Work integration")
    saved = client.get("/saved").get_data(as_text=True)
    check("Design appears in Saved Work", "CAC Choir 10th Anniversary" in saved)
    check("Saved Work can reopen the design",
          f"/graphic-design/{design_id}/edit" in saved)
    check("Design shows its category", "Anniversary" in saved)
    letters_saved = client.get("/letters/saved").get_data(as_text=True)
    check("Design does NOT appear in Saved Letters",
          "CAC Choir 10th Anniversary" not in letters_saved)

    # ------------------------------------------------------------- legacy
    print("Passport Photo slot reuse")
    legacy = client.get("/passport", follow_redirects=False)
    check("Legacy /passport redirects to the workspace",
          legacy.status_code in (301, 302)
          and "/graphic-design" in legacy.headers.get("Location", ""),
          f"status {legacy.status_code}")
    home = client.get("/").get_data(as_text=True)
    check("Dashboard shows the Graphic Design tile", "Graphic Design" in home)
    check("Dashboard no longer shows a Passport Photos tile",
          "Passport Photo" not in home)
    check("Only one design workspace route exists",
          client.get("/graphic-design/").status_code == 200)

    # ------------------------------------------------------ other services
    print("Other services untouched")
    check("Letters landing works", "Request Letter" in client.get("/letters/?q=request").get_data(as_text=True))
    check("Documents editor works",
          'id="doc-area"' in client.get("/documents/").get_data(as_text=True))
    check("CV templates work",
          client.get("/cv").status_code == 200 and "Professional CV" in client.get("/cv").get_data(as_text=True))
    check("Official Services works", "Official Services" in client.get("/official-services").get_data(as_text=True))

    # ------------------------------------------------------------- delete
    print("Delete")
    resp = client.post(f"/graphic-design/{design_id}/delete", follow_redirects=False)
    check("Delete -> redirect", resp.status_code == 302)
    check("Deleted editor now 404", client.get(f"/graphic-design/{design_id}/edit").status_code == 404)
    check("Deleted design gone from Saved Work",
          "CAC Choir 10th Anniversary" not in client.get("/saved").get_data(as_text=True))

    # ------------------------------------------------------------ cleanup
    print("Cleanup")
    for pid in created_ids:
        projects_repo.delete_project(pid)
    for name in created_images:
        design_store.delete_image(name)
    deleted_files = [n for n in created_images if (DESIGN_IMAGES_DIR / n).exists()]
    check("Test images removed", not deleted_files, str(deleted_files))
    check("No test projects left", projects_repo.get_project(design_id) is None)

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("Graphic Design verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
