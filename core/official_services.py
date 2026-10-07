"""
Official Services catalog for DERB MOBILE.

Single source of truth for the "Official Services" screen (government and
Nigeria Police services that DERB assists customers with). The page, the cards
and the tests all read from here - adding a service later means adding ONE
entry below.

Every ``portal_url`` in this file is a real, verified official page:

    npf.gov.ng          Nigeria Police Force - official service pages
    cmris.npf.gov.ng    NPF Central Motor Registry Information System (e-CMR)
    possap.gov.ng       Police Specialized Services Automation Project

Verification rules (keep them when you edit this file):

* Only link a page you have actually opened and seen the service on.
* Prefer a dedicated service page; if none exists, link the official index
  AND say so in ``portal_note`` so the card never pretends a page exists.
* Never invent a URL pattern. An unverified service gets ``portal_url=""``
  and the card shows the "link pending verification" state instead of a
  guessed government address.
* Re-check the links and update ``VERIFIED_ON`` when you touch this file.

DERB does not submit applications or make payments on the customer's behalf
through these links - the customer (or DERB staff, with the customer) completes
the application on the official portal itself.
"""

from __future__ import annotations

from dataclasses import dataclass

# Month the portal links below were last opened and checked.
VERIFIED_ON = "October 2026"

# Shown under the card list so the customer knows who owns these portals.
SOURCE_NOTE = (
    "Links open official Nigeria Police Force and POSSAP portals. "
    "Applications and official fees are completed on those portals - "
    "DERB does not apply for, submit or pay on your behalf."
)


@dataclass(frozen=True)
class OfficialService:
    slug: str
    name: str
    description: str
    accent: str
    portal_url: str = ""
    portal_label: str = "Official Website"
    portal_note: str = ""
    featured: bool = False
    keywords: str = ""

    @property
    def initials(self) -> str:
        """Offline avatar text - no image service, no network request."""
        words = [w for w in self.name.replace("-", " ").split() if w[:1].isalnum()]
        return "".join(w[0] for w in words[:2]).upper() or "OS"

    @property
    def has_portal(self) -> bool:
        return bool(self.portal_url)

    @property
    def search_text(self) -> str:
        """Lower-cased haystack used by the page's live filter."""
        parts = [self.name, self.description, self.keywords, self.portal_note]
        return " ".join(p for p in parts if p).lower()


OFFICIAL_SERVICES: tuple[OfficialService, ...] = (
    OfficialService(
        slug="tinted-glass-permit",
        name="Tinted Glass Permit",
        description="Permit authorising a registered vehicle to use tinted windows.",
        accent="#0b2545",
        portal_url="https://possap.gov.ng/",
        portal_note="Applied for online on POSSAP; biometric capture follows at a police command.",
        featured=True,
        keywords="tint window vehicle car permit police tgp",
    ),
    OfficialService(
        slug="police-character-certificate",
        name="Police Character Certificate",
        description="Police character/clearance certificate for work, travel or study.",
        accent="#123a72",
        portal_url="https://possap.gov.ng/",
        portal_note="Applied for online on POSSAP; fingerprint capture follows at a police command.",
        featured=True,
        keywords="pcc clearance criminal record background travel visa",
    ),
    OfficialService(
        slug="police-e-cmr",
        name="Police e-CMR",
        description="Central Motor Registry registration and vehicle certificate.",
        accent="#0ea5e9",
        portal_url="https://possap.gov.ng/",
        portal_note="No dedicated page - vehicle e-CMR requests are raised on the POSSAP portal (registration is also handled by NPF CMRIS).",
        featured=True,
        keywords="cmr cmris vehicle registration motor registry car",
    ),
    OfficialService(
        slug="police-extract",
        name="Police Extract",
        description="Official police extract used for insurance, claims and records.",
        accent="#7c3aed",
        portal_url="https://possap.gov.ng/",
        portal_note="No dedicated page - the request is raised on the POSSAP portal.",
        keywords="extract report insurance claim record possap",
    ),
    OfficialService(
        slug="police-escort-guards",
        name="Police Escort & Guards",
        description="Escort and guard services for approved events and premises.",
        accent="#0f7a5a",
        portal_url="https://possap.gov.ng/",
        portal_note="No dedicated page - escort and guard requests are raised on POSSAP.",
        keywords="escort guard security event premises possap",
    ),
    OfficialService(
        slug="police-protection",
        name="Police Protection",
        description="Official police protection/security coverage for people and events.",
        accent="#db2777",
        portal_url="https://www.npf.gov.ng/services",
        portal_note="Listed on the NPF services index.",
        keywords="protection security coverage possap bodyguard",
    ),
    OfficialService(
        slug="police-investigation-report",
        name="Police Investigation Report",
        description="Report or record request from a police investigation file.",
        accent="#9a6b00",
        portal_url="https://www.npf.gov.ng/services",
        portal_note="No dedicated page - enquiries go through the NPF services index.",
        keywords="investigation report case enquiry cid record",
    ),
    OfficialService(
        slug="international-driving-permit",
        name="International Driving Permit",
        description="International driving permit guidance, fees and application.",
        accent="#16a34a",
        portal_url="https://www.npf.gov.ng/services/international-driving-permit",
        keywords="idp driving licence license travel abroad",
    ),
    OfficialService(
        slug="hotel-guest-information",
        name="Hotel & Guest Information System",
        description="HGIS registration and guest logging for hotels and lodges.",
        accent="#f59e0b",
        portal_url="https://www.npf.gov.ng/services/hgis",
        keywords="hgis hotel lodge guest registration hospitality",
    ),
)

OFFICIAL_SERVICES_BY_SLUG = {s.slug: s for s in OFFICIAL_SERVICES}

FEATURED_OFFICIAL_SERVICES: tuple[OfficialService, ...] = tuple(
    s for s in OFFICIAL_SERVICES if s.featured
)


def get_official_service(slug: str) -> OfficialService | None:
    return OFFICIAL_SERVICES_BY_SLUG.get(slug)
