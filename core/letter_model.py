"""
Letter data model for DERB MOBILE.

Turns a catalog document definition plus the user's form data into a single
structured "document" (title, meta, intro, clause blocks, closing, signature
block). Every renderer - the HTML preview, the PDF writer and the DOCX writer
- consumes this same structure, so the three outputs can never drift apart.

No sample data is ever injected: every value comes from what the user typed.
Fields the user left blank print as fill-in lines, exactly like a paper form.
"""

from __future__ import annotations

from typing import Any

from core import letters_catalog as catalog

BLANK = "____"  # printed where the user has not filled a value


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").strip()


def blank_fields(doc: dict[str, Any]) -> dict[str, str]:
    """An empty field dict with every expected key present."""
    return {f["name"]: "" for f in catalog.flat_fields(doc)}


def normalize(doc: dict[str, Any], data: Any) -> dict[str, str]:
    """Fill in anything missing so renderers never hit KeyError."""
    fields = blank_fields(doc)
    if isinstance(data, dict):
        for key in fields:
            fields[key] = _clean(data.get(key, ""))
    return fields


def parse_form(doc: dict[str, Any], form) -> dict[str, str]:
    """Build the field dict from a submitted form."""
    fields = blank_fields(doc)
    for f in catalog.flat_fields(doc):
        fields[f["name"]] = _clean(form.get(f["name"], ""))
    return fields


def to_form_data(doc: dict[str, Any], fields: dict[str, str]) -> dict[str, str]:
    """Serialise back to the exact form names the editor posts (tests use this)."""
    fields = normalize(doc, fields)
    out: dict[str, str] = {"doc": doc["slug"]}
    out.update(fields)
    return out


def value_or_blank(fields: dict[str, str], name: str) -> str:
    return fields.get(name, "").strip() or BLANK


def _fmt(template: str, fields: dict[str, str]) -> str:
    """Interpolate {field_name} tokens; unfilled fields become fill-in lines."""
    out = template
    for token in _tokens(template):
        out = out.replace("{" + token + "}", value_or_blank(fields, token))
    return out


def _tokens(template: str) -> list[str]:
    import re

    return re.findall(r"{([a-z0-9_]+)}", template)


# ---------------------------------------------------------------------------
# Structured document
# ---------------------------------------------------------------------------
def display_title(doc: dict[str, Any], fields: dict[str, str]) -> str:
    """'Motorcycle Sale & Transfer Agreement - Chinedu Okafor'."""
    subject = ""
    for candidate in ("seller_full_name", "current_owner", "employee_name",
                      "new_owner", "applicant_full_name", "declarant_full_name",
                      "authorizing_person_full_name", "sender_full_name"):
        if fields.get(candidate):
            subject = fields[candidate]
            break
    return f"{doc['name']} - {subject}" if subject else doc["name"]


def parties_summary(doc: dict[str, Any], fields: dict[str, str]) -> str:
    """Short 'who is involved' line for the saved list."""
    names = []
    for inst in catalog.field_instances(doc):
        if inst["group"] != "person":
            continue
        for f in inst["fields"]:
            if f["name"].endswith("_full_name") and fields.get(f["name"]):
                names.append(fields[f["name"]])
                break
    if not names:
        for candidate in ("recipient_name", "organisation", "company_name"):
            if fields.get(candidate):
                names.append(fields[candidate])
                break
    return " - ".join(names) if names else ""


def build_document(doc: dict[str, Any], fields: dict[str, str],
                   template: dict[str, Any]) -> dict[str, Any]:
    """
    Compose the complete structured document from the user's actual data.

    Returns the block structure shared by the HTML preview, the PDF writer
    and the DOCX writer.
    """
    fields = normalize(doc, fields)
    instances = catalog.field_instances(doc)
    kind = doc["kind"]

    # ---- parties / person blocks ------------------------------------------
    clause_blocks: list[dict[str, Any]] = []
    person_instances = [i for i in instances
                        if i["group"] in ("person", "contact")]
    other_instances = [i for i in instances
                       if i["group"] not in ("person", "contact")]

    if kind == "agreement":
        # Clause 1: the parties, from every person group present.
        party_items = []
        for inst in person_instances:
            for f in inst["fields"]:
                party_items.append((f["label"], value_or_blank(fields, f["name"])))
        if party_items:
            clause_blocks.append({
                "heading": "THE PARTIES",
                "items": party_items,
            })
        # Remaining groups become numbered clauses (witnesses and the date
        # have their own places in the signature block and date line).
        for inst in other_instances:
            if inst["group"] in ("witnesses", "document_date"):
                continue
            items = [(f["label"], value_or_blank(fields, f["name"]))
                     for f in inst["fields"]]
            if items:
                clause_blocks.append({"heading": inst["heading"].upper(),
                                      "items": items})
    elif kind == "declaration":
        lead_name = ""
        for inst in person_instances:
            for f in inst["fields"]:
                if f["name"].endswith("_full_name") and fields.get(f["name"]):
                    lead_name = fields[f["name"]]
                    break
            if lead_name:
                break
        # The declarant's own details belong in the document too.
        for inst in person_instances:
            items = [(f["label"], value_or_blank(fields, f["name"]))
                     for f in inst["fields"]]
            if items:
                clause_blocks.append({"heading": (inst["role"] or "The Declarant").upper(),
                                      "items": items})
        for inst in other_instances:
            if inst["group"] in ("witnesses", "document_date"):
                continue
            items = [(f["label"], value_or_blank(fields, f["name"]))
                     for f in inst["fields"]]
            if items:
                clause_blocks.append({"heading": inst["heading"].upper(),
                                      "items": items})
    else:  # letter
        for inst in person_instances + other_instances:
            if inst["group"] in ("witnesses", "document_date"):
                continue
            items = [(f["label"], value_or_blank(fields, f["name"]))
                     for f in inst["fields"]]
            if items:
                clause_blocks.append({"heading": inst["heading"], "items": items})

    # ---- recipient block (letters print "To:") ----------------------------
    # Read through the instance's own field names so prefixed variants
    # (candidate_recipient_name, guest_recipient_name, ...) are found too.
    recipient = None
    for inst in instances:
        if inst["group"] == "recipient":
            lines = [fields.get(f["name"], "").strip() for f in inst["fields"]]
            lines = [line for line in lines if line]
            if lines:
                recipient = lines

    # ---- signature roles ---------------------------------------------------
    sign_roles = list(doc["sign_roles"])
    if not sign_roles:
        for inst in person_instances:
            if inst["role"]:
                sign_roles.append(inst["role"])
        if not sign_roles:
            first_contact = next((i for i in person_instances), None)
            if first_contact and first_contact["fields"]:
                sign_roles.append("Author")
    signers = []
    for role in sign_roles[:2]:
        matched = ""
        for inst in person_instances:
            if inst["role"] == role:
                for f in inst["fields"]:
                    if f["name"].endswith("_full_name") and fields.get(f["name"]):
                        matched = fields[f["name"]]
                        break
            if matched:
                break
        if not matched:
            for inst in person_instances:
                if not inst["role"]:
                    for f in inst["fields"]:
                        if f["name"].endswith("_full_name") and fields.get(f["name"]):
                            matched = fields[f["name"]]
                            break
                    if matched:
                        break
        signers.append({"role": role, "name": matched or BLANK})

    witnesses = []
    for fname in ("witness_1", "witness_2"):
        if fname in fields:
            witnesses.append({"name": fields.get(fname, "").strip() or BLANK})

    doc_date = ""
    if fields.get("document_date"):
        doc_date = fields["document_date"]
    elif fields.get("date_issued"):
        doc_date = fields["date_issued"]

    return {
        "title": doc["name"],
        "kind": kind,
        "accent": template.get("accent") or "#123a72",
        "template_name": template.get("name") or "Professional",
        "serif": (template.get("layout") == "simple"),
        "date": doc_date,
        "recipient": recipient,
        "salutation": doc["salutation"] if kind == "letter" else "",
        "opening": _fmt(doc["opening"], fields) if doc["opening"] else "",
        "closing": doc["closing"] if kind == "letter" else "",
        "signer_name": signers[0]["name"] if signers else "",
        "clauses": clause_blocks,
        "signers": signers if kind != "letter" else [],
        "letter_signer": {"name": signers[0]["name"] if signers else BLANK}
        if kind == "letter" else None,
        "witnesses": witnesses,
        "disclaimer": catalog.LEGAL_DISCLAIMER if doc["legal"] else "",
    }
