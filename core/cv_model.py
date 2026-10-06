"""
CV data model for DERB MOBILE.

This module is the single source of truth for "what is a CV". Templates only
consume this structure - they never define their own fields - so a new template
can be added later without touching any customer's saved information.

    CV DATA  ->  TEMPLATE ENGINE  ->  SELECTED TEMPLATE  ->  PREVIEW

Everything here is plain dicts/lists, so it serialises straight to the JSON
column already present in the `projects` table (no new database).
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------
# Nigerian states (used by the "State of Origin" field)
# --------------------------------------------------------------------------
NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue",
    "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu",
    "FCT - Abuja", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina",
    "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo",
    "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
]

GENDERS = ["", "Male", "Female"]

# --------------------------------------------------------------------------
# Section / field definitions
#
# The editor UI and the form parser are both generated from these lists.
# To add a section later: append a dict here. Nothing else changes.
# --------------------------------------------------------------------------
SCALAR_SECTIONS: list[dict[str, Any]] = [
    {
        "key": "personal",
        "title": "Personal Information",
        "icon": "cv",
        "fields": [
            {"name": "full_name", "label": "Full Name", "type": "text",
             "placeholder": "e.g. Chinedu Okafor", "required": True},
            {"name": "professional_title", "label": "Professional Title", "type": "text",
             "placeholder": "e.g. Accounting Officer"},
            {"name": "phone", "label": "Phone Number", "type": "tel",
             "inputmode": "tel", "placeholder": "e.g. 0803 123 4567"},
            {"name": "email", "label": "Email", "type": "email",
             "inputmode": "email", "placeholder": "e.g. name@email.com"},
            {"name": "address", "label": "Address", "type": "text",
             "placeholder": "e.g. 12 Aba Road, Port Harcourt"},
            {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
            {"name": "gender", "label": "Gender", "type": "select", "options": GENDERS},
            {"name": "nationality", "label": "Nationality", "type": "text",
             "default": "Nigerian", "placeholder": "e.g. Nigerian"},
            {"name": "state_of_origin", "label": "State of Origin", "type": "select",
             "options": [""] + NIGERIAN_STATES},
            {"name": "lga", "label": "Local Government Area", "type": "text",
             "placeholder": "e.g. Obi/Akpor"},
        ],
    },
    {
        "key": "profile",
        "title": "Profile / Objective",
        "icon": "document",
        "fields": [
            {"name": "profile", "label": "Professional Profile", "type": "textarea",
             "placeholder": "Two or three sentences describing experience, strengths and value."},
            {"name": "objective", "label": "Career Objective", "type": "textarea",
             "placeholder": "What the applicant is seeking next."},
        ],
    },
]

REPEATABLE_SECTIONS: list[dict[str, Any]] = [
    {
        "key": "education",
        "title": "Education",
        "icon": "school",
        "add_label": "Add another education",
        "blank": {"institution": "", "qualification": "", "course": "",
                  "start_year": "", "end_year": ""},
        "fields": [
            {"name": "institution", "label": "Institution", "type": "text",
             "placeholder": "e.g. University of Port Harcourt"},
            {"name": "qualification", "label": "Qualification", "type": "text",
             "placeholder": "e.g. B.Sc"},
            {"name": "course", "label": "Course / Field", "type": "text",
             "placeholder": "e.g. Accounting"},
            {"name": "start_year", "label": "Start Year", "type": "text",
             "inputmode": "numeric", "placeholder": "2015"},
            {"name": "end_year", "label": "End Year", "type": "text",
             "inputmode": "numeric", "placeholder": "2019"},
        ],
    },
    {
        "key": "experience",
        "title": "Work Experience",
        "icon": "business",
        "add_label": "Add another job",
        "blank": {"company": "", "position": "", "start_date": "",
                  "end_date": "", "responsibilities": ""},
        "fields": [
            {"name": "company", "label": "Company", "type": "text",
             "placeholder": "e.g. Zenith Bank Plc"},
            {"name": "position", "label": "Position", "type": "text",
             "placeholder": "e.g. Customer Service Officer"},
            {"name": "start_date", "label": "Start Date", "type": "text",
             "placeholder": "e.g. Jan 2020"},
            {"name": "end_date", "label": "End Date", "type": "text",
             "placeholder": "e.g. Dec 2022 or Present"},
            {"name": "responsibilities", "label": "Responsibilities", "type": "textarea",
             "placeholder": "One responsibility per line.\nThey appear as bullet points."},
        ],
    },
    {
        "key": "skills",
        "title": "Skills",
        "icon": "check",
        "add_label": "Add another skill",
        "blank": {"name": ""},
        "fields": [
            {"name": "name", "label": "Skill", "type": "text",
             "placeholder": "e.g. Microsoft Excel"},
        ],
    },
    {
        "key": "certifications",
        "title": "Certifications",
        "icon": "document",
        "add_label": "Add another certification",
        "blank": {"name": "", "issuer": "", "year": ""},
        "fields": [
            {"name": "name", "label": "Certification", "type": "text",
             "placeholder": "e.g. ICAN Skills Certification"},
            {"name": "issuer", "label": "Issuing Body", "type": "text",
             "placeholder": "e.g. ICAN"},
            {"name": "year", "label": "Year", "type": "text",
             "inputmode": "numeric", "placeholder": "2022"},
        ],
    },
    {
        "key": "languages",
        "title": "Languages",
        "icon": "letter",
        "add_label": "Add another language",
        "blank": {"name": ""},
        "fields": [
            {"name": "name", "label": "Language", "type": "text",
             "placeholder": "e.g. English (Fluent)"},
        ],
    },
    {
        "key": "references",
        "title": "References",
        "icon": "saved",
        "add_label": "Add another reference",
        "blank": {"name": "", "title": "", "organisation": "",
                  "phone": "", "email": ""},
        "fields": [
            {"name": "name", "label": "Name", "type": "text",
             "placeholder": "e.g. Dr. Grace Okoro"},
            {"name": "title", "label": "Title / Position", "type": "text",
             "placeholder": "e.g. Head of Department"},
            {"name": "organisation", "label": "Organisation", "type": "text",
             "placeholder": "e.g. University of Port Harcourt"},
            {"name": "phone", "label": "Phone", "type": "tel",
             "inputmode": "tel", "placeholder": "e.g. 0803 000 0000"},
            {"name": "email", "label": "Email", "type": "email",
             "inputmode": "email", "placeholder": "e.g. ref@email.com"},
        ],
    },
]

SCALAR_FIELDS = [
    (s["key"], f["name"])
    for s in SCALAR_SECTIONS
    for f in s["fields"]
]

INDEXED_KEY = re.compile(r"^(\w+)\[(\d+)\]\[(\w+)\]$")

SECTION_BY_KEY = {s["key"]: s for s in REPEATABLE_SECTIONS}


# --------------------------------------------------------------------------
# Construction / normalisation
# --------------------------------------------------------------------------
def blank_cv() -> dict[str, Any]:
    """A complete, empty CV with every key present."""
    cv: dict[str, Any] = {"photo": "", "version": 1}
    for section in SCALAR_SECTIONS:
        cv[section["key"]] = {
            f["name"]: f.get("default", "") for f in section["fields"]
        }
    for section in REPEATABLE_SECTIONS:
        cv[section["key"]] = []
    return cv


def normalize(data: Any) -> dict[str, Any]:
    """Fill in anything missing so templates never hit KeyError."""
    cv = blank_cv()
    if not isinstance(data, dict):
        return cv

    cv["version"] = data.get("version", 1)
    cv["photo"] = data.get("photo", "") or ""

    for section in SCALAR_SECTIONS:
        key = section["key"]
        source = data.get(key) or {}
        if isinstance(source, dict):
            for f in section["fields"]:
                cv[key][f["name"]] = _clean(source.get(f["name"], ""))

    for section in REPEATABLE_SECTIONS:
        key = section["key"]
        rows = data.get(key) or []
        out: list[dict[str, str]] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = {f["name"]: _clean(row.get(f["name"], "")) for f in section["fields"]}
                if any(item.values()):
                    out.append(item)
        cv[key] = out
    return cv


def parse_form(form) -> dict[str, Any]:
    """
    Build a CV from a submitted editor form.

    Scalar fields use plain names ('full_name'); repeatable rows use indexed
    names ('education[0][institution]'), which keeps rows aligned even when a
    field is left blank.
    """
    cv = blank_cv()
    for section_key, field_name in SCALAR_FIELDS:
        cv[section_key][field_name] = _clean(form.get(field_name, ""))

    rows: dict[str, dict[int, dict[str, str]]] = {}
    for raw_key in form.keys():
        match = INDEXED_KEY.match(raw_key)
        if not match:
            continue
        section_key, index, field_name = match.group(1), int(match.group(2)), match.group(3)
        if section_key not in SECTION_BY_KEY:
            continue
        rows.setdefault(section_key, {}).setdefault(index, {})[field_name] = _clean(
            form.get(raw_key, "")
        )

    for section in REPEATABLE_SECTIONS:
        key = section["key"]
        found = rows.get(key, {})
        cv[key] = [
            found[i] for i in sorted(found) if any(found[i].values())
        ]
    return normalize(cv)


def to_form_data(cv: dict[str, Any]) -> dict[str, str]:
    """
    Serialise a CV into the exact form-field names the editor posts.
    Kept next to parse_form() so the two stay in step, and used by the tests.
    """
    cv = normalize(cv)
    data: dict[str, str] = {
        "existing_photo": cv.get("photo", "") or "",
    }
    for section_key, field_name in SCALAR_FIELDS:
        data[field_name] = cv[section_key].get(field_name, "")
    for section in REPEATABLE_SECTIONS:
        for index, row in enumerate(cv.get(section["key"], [])):
            for f in section["fields"]:
                data[f'{section["key"]}[{index}][{f["name"]}]'] = row.get(f["name"], "")
    return data


# --------------------------------------------------------------------------
# Display helpers
# --------------------------------------------------------------------------
def display_name(cv: dict[str, Any]) -> str:
    name = (cv.get("personal", {}) or {}).get("full_name", "").strip()
    return name or "Untitled Customer"


def professional_title(cv: dict[str, Any]) -> str:
    return (cv.get("personal", {}) or {}).get("professional_title", "").strip()


def project_title(cv: dict[str, Any]) -> str:
    title = professional_title(cv)
    name = display_name(cv)
    return f"{name} - {title}" if title else f"{name} - CV"


def contact_items(cv: dict[str, Any]) -> list[str]:
    """Ordered contact lines used by every template header."""
    p = cv.get("personal", {}) or {}
    order = ["phone", "email", "address"]
    items = [p.get(k, "").strip() for k in order]
    return [i for i in items if i]


def bio_items(cv: dict[str, Any]) -> list[str]:
    """Nationality / state / LGA / DOB / gender summary chips."""
    p = cv.get("personal", {}) or {}
    items = []
    if p.get("nationality"):
        items.append(f"Nationality: {p['nationality']}")
    origin = " / ".join(x for x in [p.get("state_of_origin"), p.get("lga")] if x)
    if origin:
        items.append(f"Origin: {origin}")
    if p.get("date_of_birth"):
        items.append(f"Date of Birth: {p['date_of_birth']}")
    if p.get("gender"):
        items.append(f"Gender: {p['gender']}")
    return items


def initials(name: str) -> str:
    """'Chinedu Okafor' -> 'CO'. Used by the Modern template monogram."""
    parts = [p for p in (name or "").split() if p and p[0].isalpha()]
    if not parts:
        return "CV"
    letters = [parts[0][0]]
    if len(parts) > 1:
        letters.append(parts[-1][0])
    return "".join(letters).upper()


def responsibilities_list(text: str) -> list[str]:
    return [line.strip(" -•\t") for line in (text or "").splitlines() if line.strip()]


def is_empty(cv: dict[str, Any]) -> bool:
    """True when nothing meaningful has been entered yet."""
    if cv.get("photo"):
        return False
    for section in SCALAR_SECTIONS:
        if any(str(v).strip() for v in cv.get(section["key"], {}).values()):
            return False
    for section in REPEATABLE_SECTIONS:
        if cv.get(section["key"]):
            return False
    return True


def filled_summary(cv: dict[str, Any]) -> dict[str, int]:
    """Counts used on the Saved Work screen."""
    return {
        "education": len(cv.get("education", [])),
        "experience": len(cv.get("experience", [])),
        "skills": len(cv.get("skills", [])),
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").strip()


# --------------------------------------------------------------------------
# Sample data (used for template thumbnails and automated tests).
# Clearly fictional - never real customer information.
# --------------------------------------------------------------------------
def sample_cv() -> dict[str, Any]:
    cv = blank_cv()
    cv["personal"].update({
        "full_name": "Chinedu A. Okafor",
        "professional_title": "Accounting Officer",
        "phone": "0803 123 4567",
        "email": "chinedu.okafor@email.com",
        "address": "12 Aba Road, Port Harcourt, Rivers State",
        "date_of_birth": "1995-04-12",
        "gender": "Male",
        "nationality": "Nigerian",
        "state_of_origin": "Imo",
        "lga": "Owerri West",
    })
    cv["profile"] = {
        "profile": "Detail-oriented accounting officer with 5 years of experience in "
                   "financial reporting, reconciliation and internal controls. Known for "
                   "accuracy under deadline and for improving month-end close times.",
        "objective": "To join a reputable organisation where I can apply strong "
                     "analytical and accounting skills while growing into a senior "
                     "finance role.",
    }
    cv["education"] = [
        {"institution": "University of Port Harcourt", "qualification": "B.Sc",
         "course": "Accounting", "start_year": "2013", "end_year": "2017"},
        {"institution": "Government Secondary School, Owerri", "qualification": "WASSCE",
         "course": "Science", "start_year": "2006", "end_year": "2012"},
    ]
    cv["experience"] = [
        {"company": "Zenith Bank Plc", "position": "Accounting Officer",
         "start_date": "Jan 2020", "end_date": "Present",
         "responsibilities": "Prepare monthly financial statements and reports\n"
                             "Reconcile bank and ledger accounts daily\n"
                             "Support internal and external audit exercises\n"
                             "Train two junior staff on the reporting process"},
        {"company": "Rockfield Oil Services Ltd", "position": "Accounts Assistant",
         "start_date": "Feb 2018", "end_date": "Dec 2019",
         "responsibilities": "Processed supplier invoices and payment schedules\n"
                             "Maintained petty cash and expense records\n"
                             "Assisted in monthly payroll preparation"},
    ]
    cv["skills"] = [
        {"name": "Microsoft Excel (Advanced)"},
        {"name": "Financial Reporting"},
        {"name": "QuickBooks"},
        {"name": "Account Reconciliation"},
        {"name": "Attention to Detail"},
    ]
    cv["certifications"] = [
        {"name": "ICAN Skills Certification", "issuer": "ICAN", "year": "2022"},
        {"name": "Excel for Finance", "issuer": "Coursera", "year": "2021"},
    ]
    cv["languages"] = [
        {"name": "English (Fluent)"},
        {"name": "Igbo (Native)"},
    ]
    cv["references"] = [
        {"name": "Dr. Grace Okoro", "title": "Head of Department",
         "organisation": "University of Port Harcourt",
         "phone": "0805 555 1212", "email": "grace.okoro@email.com"},
        {"name": "Mr. Ibrahim Bello", "title": "Branch Manager",
         "organisation": "Zenith Bank Plc",
         "phone": "0806 555 3434", "email": "ibrahim.bello@email.com"},
    ]
    return cv
