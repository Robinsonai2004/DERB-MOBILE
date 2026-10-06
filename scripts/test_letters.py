#!/usr/bin/env python3
"""
DERB MOBILE - Phase 5 Letters & Documents test.

Walks the exact workflow an operator would follow, for the six required
document types:

    Application Letter, Motorcycle Sale & Transfer Agreement,
    Change of Ownership, Payment Agreement, Resignation Letter,
    Authorization Letter

each one through:

    select -> fill form -> preview -> save -> reopen -> edit -> export PDF/DOCX

Also checks landing search, disclaimers, Saved Letters isolation from CV
Saved Work, duplicate and delete. Fictional data only; every project and file
it creates is removed again.

Run:
    python scripts/test_letters.py
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


WORKFLOWS = {
    "application-letter": {
        "applicant_full_name": "Ngozi Ada", "applicant_phone": "0803 000 1111",
        "applicant_email": "ngozi@example.com", "applicant_address": "9 Allen Ave, Ikeja",
        "company_name": "Zenith Bank Plc", "position": "Graduate Trainee",
        "qualifications": "B.Sc Accounting, 2:1", "experience": "3 years NYSC + internship",
        "message": "I am available for interview at any time.",
    },
    "motorcycle-sale-transfer-agreement": {
        "seller_full_name": "Ada Obi", "seller_address": "12 Awolowo Road",
        "seller_phone": "0803 111 2222", "seller_id_details": "NIN 12345678901",
        "buyer_full_name": "Ben Eze", "buyer_address": "5 Market Road",
        "buyer_phone": "0805 333 4444", "buyer_id_details": "PVC 9876543",
        "motorcycle_make": "Bajaj", "motorcycle_model": "Boxer 100",
        "motorcycle_year": "2019", "motorcycle_colour": "Red",
        "motorcycle_reg_number": "LAG-123-ABC", "motorcycle_chassis_number": "CHS-998877",
        "motorcycle_engine_number": "ENG-556677", "sale_price": "N450,000",
        "amount_paid": "N400,000", "balance": "N50,000",
        "payment_method": "Bank transfer", "document_date": "2026-10-06",
        "witness_1": "Chidi Nwa", "witness_2": "Bola Ade",
    },
    "motorcycle-change-of-ownership": {
        "seller_full_name": "Uche Kalu", "buyer_full_name": "Nnamdi Oka",
        "motorcycle_make": "Jincheng", "motorcycle_reg_number": "ABJ-777-XY",
        "current_owner": "Uche Kalu", "new_owner": "Nnamdi Oka",
        "reason_for_transfer": "Outright sale", "transfer_date": "2026-10-01",
    },
    "payment-agreement": {
        "creditor_full_name": "Grace Ayo", "creditor_phone": "0803 555 0000",
        "debtor_full_name": "Peter Musa", "debtor_phone": "0806 222 1111",
        "total_amount": "N200,000", "amount_paid": "N50,000",
        "balance": "N150,000", "installment_amount": "N25,000",
        "installment_dates": "Last Friday of every month",
        "final_payment_date": "2027-04-30", "document_date": "2026-10-06",
    },
    "resignation-letter": {
        "employee_full_name": "Tunde Bakare", "employee_phone": "0807 000 9999",
        "employee_email": "tunde@example.com", "company_name": "DERB Finance Concepts",
        "position": "Account Officer", "resignation_date": "2026-10-06",
        "last_working_day": "2026-11-06", "reason": "Relocation",
        "message": "Thank you for the opportunities given to me.",
    },
    "authorization-letter": {
        "authorizing_person_full_name": "Mary Ije", "authorizing_person_phone": "0809 123 4567",
        "authorizing_person_address": "3 Broad Street, Lagos",
        "authorized_person": "John Okon", "authorized_person_id": "NIN 55566677788",
        "purpose": "Collecting my vehicle papers",
        "specific_action": "Collect the original vehicle documents from the licensing office",
        "valid_until": "2026-12-31", "additional_terms": "Original ID must be presented.",
    },
}


def main() -> int:
    print("DERB MOBILE - Phase 5 Letters & Documents test")
    print("-" * 58)

    from config import DERB_ROOT
    from core import letters_catalog, projects_repo

    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    created_ids: list[int] = []
    exported_files: list[Path] = []

    # ---------------------------------------------------------- landing
    print("Landing page")
    resp = client.get("/letters/")
    home = resp.get_data(as_text=True)
    check("GET /letters/ -> 200", resp.status_code == 200, f"status {resp.status_code}")
    check("Page title", "Create a Letter or Document" in home)
    check("Page subtitle", "Choose the type of document you want to create." in home)
    check("Prominent search bar", 'id="letter-search"' in home
          and "Search letters and documents..." in home)
    for cat_name in ("Business &amp; Official", "Agreements &amp; Contracts",
                     "Ownership &amp; Transfer", "Employment &amp; Workplace",
                     "Legal / Declaration / Authorization", "School &amp; Academic",
                     "Personal &amp; General"):
        check(f"Category shown: {cat_name}", cat_name in home)
    card_count = home.count('class="lt-card"')
    check("All 86 document cards rendered", card_count >= 86, f"{card_count} cards")
    check("Cards carry instant-search data", 'data-search=' in home)
    check("Create buttons on cards", ">Create</a>" in home)
    check("View-all control for large categories", "View all" in home)
    check("Saved Letters link", "/letters/saved" in home)

    # ---------------------------------------------------------- search
    print("Search")
    for q, expect in (("bike", "Motorcycle Sale &amp; Transfer Agreement"),
                      ("ownership", "Motorcycle Change of Ownership"),
                      ("job", "Application Letter"),
                      ("payment", "Payment Agreement")):
        resp = client.get(f"/letters/?q={q}")
        body = resp.get_data(as_text=True)
        check(f"search '{q}' finds: {expect}",
              resp.status_code == 200 and expect in body,
              f"status {resp.status_code}")
    resp = client.get("/letters/?q=zzzznothing")
    check("No-results state shown", "No documents match your search" in
          resp.get_data(as_text=True))
    js = (PROJECT_ROOT / "static" / "js" / "letters.js").read_text()
    check("Instant search wired client-side", "data-search" in js and "input" in js)

    # ------------------------------------------------------ workflows
    pdf_dir = DERB_ROOT / "Letters"
    for slug, fields in WORKFLOWS.items():
        doc = letters_catalog.get_doc(slug)
        print(f"Workflow: {doc['name']}")
        form = dict(fields)
        form["doc"] = slug
        form["template_slug"] = "professional"

        # select -> form
        resp = client.get(f"/letters/new?doc={slug}")
        check("  form opens", resp.status_code == 200, f"status {resp.status_code}")
        form_html = resp.get_data(as_text=True)
        first_field = next(iter(fields))
        check("  form shows document-specific fields", f'name="{first_field}"' in form_html)
        if doc["legal"]:
            check("  legal disclaimer on form", "not legal advice" in form_html)

        # fill -> preview (not saved)
        resp = client.post("/letters/preview", data=form)
        preview = resp.get_data(as_text=True)
        check("  preview renders", resp.status_code == 200, f"status {resp.status_code}")
        sample_value = list(fields.values())[0]
        check("  preview uses real entered data", sample_value in preview)
        check("  preview keeps entries on back", 'name="doc"' in preview
              and sample_value in preview)
        check("  print button present", "data-print" in preview)

        # save
        resp = client.post("/letters/save", data=form, follow_redirects=False)
        check("  save redirects to editor", resp.status_code == 302,
              f"status {resp.status_code}")
        location = resp.headers.get("Location", "")
        m = re.search(r"/letters/(\d+)/edit", location)
        check("  saved project id returned", bool(m), location)
        if not m:
            continue
        letter_id = int(m.group(1))
        created_ids.append(letter_id)

        # reopen
        resp = client.get(f"/letters/{letter_id}/edit")
        edit_html = resp.get_data(as_text=True)
        check("  reopen shows saved values", sample_value in edit_html)

        # edit + save again
        updated = dict(form)
        updated["project_id"] = str(letter_id)
        if "message" in updated:
            updated["message"] = "Updated message text 12345"
        resp = client.post("/letters/save", data=updated, follow_redirects=False)
        check("  edit + save again", resp.status_code == 302, f"status {resp.status_code}")

        # saved preview
        resp = client.get(f"/letters/{letter_id}/preview")
        saved_preview = resp.get_data(as_text=True)
        check("  saved preview renders", resp.status_code == 200)

        # export PDF
        resp = client.post(f"/letters/{letter_id}/export/pdf")
        check("  export PDF -> 200", resp.status_code == 200, f"status {resp.status_code}")
        pdf_bytes = resp.data
        check("  PDF magic bytes", pdf_bytes.startswith(b"%PDF-"))
        text = ""
        for s in re.findall(rb"stream\n(.*?)\nendstream", pdf_bytes, re.S):
            text += zlib.decompress(s).decode("latin-1")
        check("  PDF contains customer data", sample_value in text)
        if doc["legal"]:
            check("  PDF carries disclaimer", "not legal advice" in text)
        written = list(pdf_dir.glob("*.pdf"))
        if written:
            exported_files.extend(written)

        # export DOCX
        resp = client.post(f"/letters/{letter_id}/export/docx")
        check("  export DOCX -> 200", resp.status_code == 200, f"status {resp.status_code}")
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        check("  DOCX archive intact", zf.testzip() is None)
        doc_xml = zf.read("word/document.xml").decode()
        check("  DOCX contains customer data", sample_value in doc_xml)
        written = list(pdf_dir.glob("*.docx"))
        if written:
            exported_files.extend(written)

    # ---------------------------------------------- saved letters list
    print("Saved Letters")
    resp = client.get("/letters/saved")
    saved_html = resp.get_data(as_text=True)
    check("Saved Letters -> 200", resp.status_code == 200)
    check("Shows saved document names", "Application Letter" in saved_html)
    check("Shows category", "Employment &amp; Workplace" in saved_html
          or "Business &amp; Official" in saved_html)
    check("Shows parties", "Ada Obi" in saved_html or "Ngozi Ada" in saved_html)
    check("Shows template name", "Professional" in saved_html)
    check("Shows created/modified dates", "Created" in saved_html and "Modified" in saved_html)
    for action in ("Open / Edit", "Preview", "Duplicate", "Export PDF", "Export DOCX", "Delete"):
        check(f"Action available: {action}", action in saved_html)
    check("Delete asks for confirmation", "confirm(" in saved_html)
    check("Search on saved letters", 'name="q"' in saved_html)

    # isolation from CV Saved Work
    resp = client.get("/saved")
    cv_saved = resp.get_data(as_text=True)
    check("CV Saved Work does not list letters", "Ngozi Ada" not in cv_saved)

    # duplicate + delete
    target = created_ids[0]
    resp = client.post(f"/letters/{target}/duplicate", follow_redirects=False)
    check("Duplicate -> redirect", resp.status_code == 302)
    dupes = projects_repo.list_projects(doc_type="LETTER")
    dup_names = [p["customer_name"] for p in dupes if p["customer_name"].endswith("(Copy)")]
    check("Duplicated letter exists", bool(dup_names), str(dup_names))
    for p in dupes:
        if p["customer_name"].endswith("(Copy)"):
            created_ids.append(p["id"])

    resp = client.post(f"/letters/{target}/delete", follow_redirects=False)
    check("Delete -> redirect", resp.status_code == 302)
    check("Deleted letter gone", client.get(f"/letters/{target}/edit").status_code == 404)

    # guard: letters routes refuse CV projects
    from core import cv_model
    cv_id = projects_repo.create_project(cv_model.sample_cv(), "professional-cv")
    created_ids.append(cv_id)
    check("Letters route refuses a CV project",
          client.get(f"/letters/{cv_id}/edit").status_code == 404)
    check("Letters export refuses a CV project",
          client.post(f"/letters/{cv_id}/export/pdf").status_code == 404)

    # ------------------------------------------------------------ cleanup
    print("Cleanup")
    for pid in created_ids:
        projects_repo.delete_project(pid)
    for f in set(exported_files):
        try:
            f.unlink()
        except OSError:
            pass
    leftover = [f for f in pdf_dir.glob("*")
                if f.suffix in (".pdf", ".docx") and f.stat().st_size > 0]
    check("Test projects and files removed", not leftover, str(leftover))

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("Phase 5 Letters & Documents verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
