#!/usr/bin/env python3
"""
DERB MOBILE - Phase 4 export workflow test.

Walks the exact workflow an operator would follow:

    dashboard -> Saved Work -> Export PDF  -> verify the download
                            -> Export DOCX -> verify the download

and checks that the exported files contain the customer's real data (not
sample data), land in DERB/CV/PDF and DERB/CV/DOCX, and survive a long CV.

Fictional sample data only. Every project and file it creates is deleted
again, so the Saved Work list and the DERB folders are left as found.

Run:
    python scripts/test_exports.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
import zlib
import xml.etree.ElementTree as ET
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
    print("DERB MOBILE - Phase 4 export test")
    print("-" * 58)

    from config import DERB_ROOT
    from core import cv_model, db, projects_repo

    db.init_db()
    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    created_ids: list[int] = []
    exported_files: list[Path] = []

    # ------------------------------------------------------ seed a project
    print("Setup")
    cv = cv_model.sample_cv()
    project_id = projects_repo.create_project(cv, "professional-cv")
    created_ids.append(project_id)
    check("Test project created", project_id > 0, f"id={project_id}")

    # ----------------------------------------------- PDF export over HTTP
    print("PDF export (through the real routes)")
    resp = client.post(f"/cv/{project_id}/export/pdf")
    check("POST /cv/<id>/export/pdf -> 200", resp.status_code == 200,
          f"status {resp.status_code}")
    pdf_bytes = resp.data
    check("Response is a PDF", pdf_bytes.startswith(b"%PDF-"), pdf_bytes[:16].hex())
    disp = resp.headers.get("Content-Disposition", "")
    check("Download attachment header",
          "attachment" in disp and ".pdf" in disp, disp)
    check("MIME type application/pdf",
          resp.mimetype == "application/pdf", resp.mimetype)

    xref_at = int(pdf_bytes.rsplit(b"startxref", 1)[1].split()[0])
    check("PDF xref table reachable", pdf_bytes[xref_at:xref_at + 4] == b"xref")
    text = ""
    for stream in re.findall(rb"stream\n(.*?)\nendstream", pdf_bytes, re.S):
        text += zlib.decompress(stream).decode("latin-1")
    for needle in ("Chinedu A. Okafor", "Zenith Bank Plc", "ICAN Skills Certification",
                   "WORK EXPERIENCE", "REFERENCES"):
        check(f"PDF contains real data: {needle}", needle in text)

    # file landed in DERB/CV/PDF
    pdf_dir = DERB_ROOT / "CV" / "PDF"
    written = sorted(pdf_dir.glob("Chinedu_A._Okafor_CV_*.pdf"),
                     key=lambda p: p.stat().st_mtime)
    check("PDF stored in DERB/CV/PDF", bool(written), str(pdf_dir))
    if written:
        exported_files.append(written[-1])
        check("Stored PDF matches download size",
              written[-1].stat().st_size == len(pdf_bytes))

    # --------------------------------------------- DOCX export over HTTP
    print("DOCX export (through the real routes)")
    resp = client.post(f"/cv/{project_id}/export/docx")
    check("POST /cv/<id>/export/docx -> 200", resp.status_code == 200,
          f"status {resp.status_code}")
    docx_bytes = resp.data
    check("Response is a ZIP container", docx_bytes[:2] == b"PK", docx_bytes[:16].hex())
    check("MIME type wordprocessingml.document",
          resp.mimetype ==
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          resp.mimetype)

    zf = zipfile.ZipFile(io.BytesIO(docx_bytes))
    check("DOCX archive intact", zf.testzip() is None)
    xml_ok = True
    for part in zf.namelist():
        if part.endswith((".xml", ".rels")):
            try:
                ET.fromstring(zf.read(part))
            except ET.ParseError:
                xml_ok = False
    check("All DOCX XML parts well-formed", xml_ok)
    doc_xml = zf.read("word/document.xml").decode()
    for needle in ("Chinedu A. Okafor", "Zenith Bank Plc", "ICAN Skills Certification",
                   "Owerri West", "0805 555 1212"):
        check(f"DOCX contains real data: {needle}", needle in doc_xml)

    docx_dir = DERB_ROOT / "CV" / "DOCX"
    written_d = sorted(docx_dir.glob("Chinedu_A._Okafor_CV_*.docx"),
                       key=lambda p: p.stat().st_mtime)
    check("DOCX stored in DERB/CV/DOCX", bool(written_d), str(docx_dir))
    if written_d:
        exported_files.append(written_d[-1])

    # ------------------------------------------------- long CV pagination
    print("Long CV handling")
    big = cv_model.sample_cv()
    big["experience"] = (big["experience"] * 6)[:14]
    big["references"] = (big["references"] * 5)[:10]
    big_id = projects_repo.create_project(big, "professional-cv")
    created_ids.append(big_id)
    resp = client.post(f"/cv/{big_id}/export/pdf")
    big_pages = len(re.findall(rb"stream\n", resp.data))
    check("Long CV produces multiple PDF pages", big_pages >= 2, f"{big_pages} pages")
    resp = client.post(f"/cv/{big_id}/export/docx")
    check("Long CV DOCX exports cleanly",
          zipfile.ZipFile(io.BytesIO(resp.data)).testzip() is None)

    # -------------------------------------------------------- error paths
    print("Error handling")
    check("Export of missing project -> 404",
          client.post("/cv/999999/export/pdf").status_code == 404)
    check("DOCX export of missing project -> 404",
          client.post("/cv/999999/export/docx").status_code == 404)

    # ------------------------------------------------------------ cleanup
    print("Cleanup")
    for pid in created_ids:
        projects_repo.delete_project(pid)
    # Remove every file this test's fictional customer produced, including
    # collision-suffixed copies (Name_CV_date_2.pdf) from repeated exports.
    for pattern in ("Chinedu_A._Okafor_CV_*.pdf", "Chinedu_A._Okafor_CV_*.docx"):
        for f in pdf_dir.glob(pattern):
            exported_files.append(f)
        for f in docx_dir.glob(pattern):
            exported_files.append(f)
    for f in exported_files:
        try:
            f.unlink()
        except OSError:
            pass
    leftover = list(pdf_dir.glob("Chinedu_A._Okafor_CV_*.pdf")) + \
        list(docx_dir.glob("Chinedu_A._Okafor_CV_*.docx"))
    check("Test projects and files removed", not leftover, str(leftover))

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("Phase 4 export workflow verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
