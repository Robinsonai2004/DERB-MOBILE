#!/usr/bin/env python3
"""
DERB MOBILE - Document (free-format editor) test.

Walks the exact workflow an operator would follow for the Document screen:

    dashboard tile -> open blank editor -> type -> save -> reopen
                   -> previews -> export PDF & DOCX -> update -> delete

Also verifies the boundary against the Letters module (no duplication: a
Document is a free-format text, a Letter is a catalog template document),
file placement in DERB/Documents/, sanitisation and clean-up.

Fictional content only; every project and file it creates is removed again.

Run:
    python scripts/test_doc_workflow.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
import zlib
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


SPEECH_TITLE = "Welcome Speech - DERB Community Event"
SPEECH_BODY = (
    "Good morning, distinguished guests.\n"
    "Today we celebrate five years of service to this community.\n"
    "- Thank you to our customers and partners\n"
    "- Thank you to the DERB team\n"
    "\n"
    "We look forward to the next five years."
)


def main() -> int:
    print("DERB MOBILE - Document editor test")
    print("-" * 58)

    from config import DERB_ROOT
    from core import doc_model, projects_repo

    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    created_ids: list[int] = []
    exported_files: list[Path] = []
    documents_dir = DERB_ROOT / "Documents"

    # ------------------------------------------------------------- model
    print("Data model")
    blank = doc_model.blank_payload()
    check("Blank payload keys", set(blank) == {"title", "body_text", "size", "align"})
    check("Default size", blank["size"] == "3")
    check("Default align", blank["align"] == "left")
    check("Empty state detected", doc_model.is_empty(blank))

    dirty = "<script>alert(1)</script><img src='http://x/y'><b>Bold</b> story\r\n<p>Second line</p>"
    clean = doc_model.normalize({"body_text": dirty, "title": " Test "})
    check("Script tags stripped", "<script" not in clean["body_text"] and "alert(1)" not in clean["body_text"])
    check("Remote image stripped", "http://" not in clean["body_text"])
    check("Rich text reduced to lines", clean["body_text"].startswith("Bold story")
          and "Second line" in clean["body_text"])
    check("Title clean", clean["title"] == "Test")
    check("Display title uses given title", doc_model.display_title(clean) == "Test")

    untitled = doc_model.normalize({"body_text": "First paragraph\nmore"})
    check("Display title falls back to body", doc_model.display_title(untitled) == "First paragraph")
    check("Size clamped to allowed set", doc_model.normalize({"size": "99"})["size"] == "3")
    check("Align clamped to left/center/right", doc_model.normalize({"align": "middle"})["align"] == "left")

    # --------------------------------------------------------- open page
    print("Editor page")
    resp = client.get("/")
    dashboard = resp.get_data(as_text=True)
    check("Dashboard Documents tile is Ready (not Soon)", "Documents</span>" in dashboard
          and "Type, print &amp; export any free-format document" in dashboard)
    check("No duplicate placeholder route for /documents",
          client.get("/documents/").status_code == 200)

    resp = client.get("/documents/")
    page = resp.get_data(as_text=True)
    check("GET /documents/ -> 200", resp.status_code == 200, f"status {resp.status_code}")
    check("Page title 'Document'", "<h1 class=\"doc-hero__title\">Document</h1>" in page)
    check("Subtitle present", "Create, edit, print and export any document." in page)
    check("Contenteditable workspace", 'id="doc-area" contenteditable="true"' in page)
    check("Placeholder text", "Start typing your document here..." in page)
    check("Title field placeholder", 'placeholder="Untitled Document"' in page)
    check("Formatting toolbar present", 'id="doc-toolbar"' in page
          and 'data-cmd="bold"' in page and 'data-cmd="italic"' in page
          and 'data-cmd="underline"' in page)
    check("Alignment controls", 'data-align="left"' in page
          and 'data-align="center"' in page and 'data-align="right"' in page)
    check("Font size control", 'id="doc-size-select"' in page)
    check("List controls", 'data-cmd="insertUnorderedList"' in page
          and 'data-cmd="insertOrderedList"' in page)
    check("Undo/redo/clear formatting controls", 'data-cmd="undo"' in page
          and 'data-cmd="redo"' in page and 'data-cmd="removeFormat"' in page)
    check("Print button", 'id="doc-print-btn"' in page)
    check("Save button", "Save Document" in page)
    check("New / Clear button", "New / Clear" in page)
    check("No export buttons on a unsaved document", "/export/pdf" not in page)
    check("Editor JS served", client.get("/static/js/document-editor.js").status_code == 200)
    check("Editor CSS served", client.get("/static/css/documents.css").status_code == 200)

    css = (PROJECT_ROOT / "static" / "css" / "documents.css").read_text()
    check("Print CSS hides app chrome", "@media print" in css
          and ".appbar, .appfooter" in css)
    check("A4 paper styles", "doc-paper" in css and ("210mm" in css or "doc-paper {" in css))
    check("Offline CSS (no CDN/fonts)", "http://" not in css and "https://" not in css)
    js = (PROJECT_ROOT / "static" / "js" / "document-editor.js").read_text()
    check("Offline JS (no network calls)", "http" not in js.replace("use strict", ""))

    # ------------------------------------------------------------- save
    print("Save workflow")
    form = {"title": SPEECH_TITLE, "body_text": SPEECH_BODY,
            "size": "3", "align": "left"}
    resp = client.post("/documents/save", data=form, follow_redirects=False)
    check("POST /documents/save -> redirect", resp.status_code == 302,
          f"status {resp.status_code}")
    m = re.search(r"/documents/(\d+)/edit", resp.headers.get("Location", ""))
    check("Saved project id returned", bool(m), resp.headers.get("Location", ""))
    if not m:
        print("-" * 58)
        print(f"{passes} passed, {len(failures)} failed")
        return 1
    doc_id = int(m.group(1))
    created_ids.append(doc_id)

    project = projects_repo.get_project(doc_id)
    check("Stored as doc_type DOCUMENT", project["doc_type"] == "DOCUMENT")
    payload = project["raw"]
    check("Stored plain-text body", payload["body_text"] == SPEECH_BODY.strip())
    check("Stored title", payload["title"] == SPEECH_TITLE)
    check("Stored in same projects table as CV/letters", project["template_slug"] == "free-format")

    # ---------------------------------------------------------- reopen
    resp = client.get(f"/documents/{doc_id}/edit")
    edit_html = resp.get_data(as_text=True)
    check("Reopen editor -> 200", resp.status_code == 200)
    check("Reopen shows the saved title", SPEECH_TITLE in edit_html)
    check("Reopen shows saved content", "distinguished guests" in edit_html)
    check("Saved editor offers exports", f"/documents/{doc_id}/export/pdf" in edit_html
          and f"/documents/{doc_id}/export/docx" in edit_html)
    check("Saved editor shows Update button", "Update Document" in edit_html)

    # --------------------------------------------------------- preview
    resp = client.get(f"/documents/{doc_id}/preview")
    preview_html = resp.get_data(as_text=True)
    check("Preview -> 200", resp.status_code == 200)
    check("Preview shows title", SPEECH_TITLE in preview_html)
    check("Preview renders body lines", "distinguished guests" in preview_html)
    check("Preview renders bullet line", "Thank you to our customers and partners" in preview_html)
    check("Preview print button", "data-role=\"print\"" in preview_html
          or "data-print" in preview_html.replace("\'", "\""))
    check("Preview export buttons", "Export" not in preview_html or "export/docx" in preview_html)

    # --------------------------------------------------- exports
    print("Exports (shared Phase 4 engines)")
    resp = client.post(f"/documents/{doc_id}/export/pdf")
    check("Export PDF -> 200", resp.status_code == 200, f"status {resp.status_code}")
    pdf_bytes = resp.data
    check("PDF magic bytes", pdf_bytes.startswith(b"%PDF-"))
    check("PDF download attachment header", "attachment" in resp.headers.get("Content-Disposition", ""))
    text = ""
    for s in re.findall(rb"stream\n(.*?)\nendstream", pdf_bytes, re.S):
        text += zlib.decompress(s).decode("latin-1")
    check("PDF carries the title", "WELCOME SPEECH" in text.upper())
    check("PDF carries the content", "distinguished guests" in text)
    check("PDF carries bullet line", "Thank you to our customers and partners" in text)
    written = sorted(documents_dir.glob("Welcome_Speech_*.pdf"), key=lambda p: p.stat().st_mtime)
    check("PDF stored in DERB/Documents/", bool(written), str(documents_dir))
    if written:
        exported_files.append(written[-1])

    resp = client.post(f"/documents/{doc_id}/export/docx")
    check("Export DOCX -> 200", resp.status_code == 200, f"status {resp.status_code}")
    docx_bytes = resp.data
    check("DOCX is a ZIP container", docx_bytes[:2] == b"PK")
    zf = zipfile.ZipFile(io.BytesIO(docx_bytes))
    check("DOCX archive intact", zf.testzip() is None)
    doc_xml = zf.read("word/document.xml").decode()
    check("DOCX carries the title", "WELCOME SPEECH" in doc_xml.upper()
          and "WELCOME SPEECH - DERB COMMUNITY EVENT" in doc_xml.upper())
    check("DOCX carries the content", "distinguished guests" in doc_xml)
    written = sorted(documents_dir.glob("Welcome_Speech_*.docx"), key=lambda p: p.stat().st_mtime)
    check("DOCX stored in DERB/Documents/", bool(written))
    if written:
        exported_files.append(written[-1])

    # ------------------------------------------------ update + size/align
    print("Update workflow")
    updated = {"title": SPEECH_TITLE, "body_text": SPEECH_BODY + "\nUpdated closing line.",
               "size": "5", "align": "center"}
    resp = client.post("/documents/save", data={**updated, "project_id": str(doc_id)},
                       follow_redirects=False)
    check("Update -> redirect", resp.status_code == 302)
    check("Update kept the same row", int(resp.headers.get("Location").split("/")[-2]) == doc_id)
    payload = projects_repo.get_project(doc_id)["raw"]
    check("Update saved new content", "Updated closing line." in payload["body_text"])
    check("Update applied size", payload["size"] == "5")
    check("Update applied align", payload["align"] == "center")

    # corrupted-form guard: a save posted with a foreign doc_type's id must
    # not overwrite that row - it silently creates a NEW document instead.
    foreign = {"fields": {}, "doc_slug": "request-letter"}
    cv_id = projects_repo.create_project({}, "professional", doc_type="LETTER",
                                         data=foreign, customer_name="Someone",
                                         title="A letter")
    created_ids.append(cv_id)
    before = projects_repo.get_project(cv_id)["raw"]
    resp = client.post("/documents/save",
                       data={"title": "hijack", "body_text": "x", "project_id": str(cv_id)},
                       follow_redirects=False)
    m2 = re.search(r"/documents/(\d+)/edit", resp.headers.get("Location", ""))
    check("Save refuses a foreign doc_type project", resp.status_code == 302 and bool(m2),
          resp.headers.get("Location", ""))
    if m2:
        created_ids.append(int(m2.group(1)))
    check("Foreign row untouched", projects_repo.get_project(cv_id)["raw"] == before)

    # empty-save guard
    resp = client.post("/documents/save", data={"title": "Empty", "body_text": "   "},
                       follow_redirects=False)
    check("Empty document is not saved", resp.status_code == 302
          and "/documents/" in resp.headers.get("Location", "")
          and "/edit" not in resp.headers.get("Location", ""))

    # ------------------------------------------------- isolation checks
    print("Isolation from other workflows")
    resp = client.get("/saved")
    saved_html = resp.get_data(as_text=True)
    check("Document shows in Saved Work", SPEECH_TITLE in saved_html)
    check("Saved Work can reopen the document", f"/documents/{doc_id}/edit" in saved_html)
    resp = client.get("/letters/saved")
    check("Document does NOT appear in Saved Letters", SPEECH_TITLE not in resp.get_data(as_text=True))

    # letters workflow must be untouched
    resp = client.get("/letters/?q=request")
    letters_html = resp.get_data(as_text=True)
    check("Letters landing still works", resp.status_code == 200
          and "Request Letter" in letters_html)
    check("Letter create flow intact", client.get("/letters/new?doc=request-letter").status_code == 200)
    check("Official Services still fine", "Official Services" in client.get("/official-services").get_data(as_text=True))

    # ---------------------------------------------------------- delete
    print("Delete")
    resp = client.post(f"/documents/{doc_id}/delete", follow_redirects=False)
    check("Delete -> redirect", resp.status_code == 302)
    check("Deleted editor now 404", client.get(f"/documents/{doc_id}/edit").status_code == 404)
    check("Also 404s on exports", client.post(f"/documents/{doc_id}/export/pdf").status_code == 404)
    check("Foreign id 404s too", client.get("/documents/999999/edit").status_code == 404)

    # ------------------------------------------------------------ cleanup
    print("Cleanup")
    for pid in created_ids:
        projects_repo.delete_project(pid)
    # Sweep every export this test's fictional customer could have produced
    # in any run (earlier crashed runs may have left files behind), including
    # collision-suffixed copies from repeated exports.
    for f in documents_dir.glob("Welcome_Speech*"):
        exported_files.append(f)
    for f in exported_files:
        try:
            f.unlink()
        except OSError:
            pass
    leftover = [f for f in documents_dir.glob("Welcome_Speech*")]
    check("Test projects and files removed", not leftover, str(leftover))

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("Document editor verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
