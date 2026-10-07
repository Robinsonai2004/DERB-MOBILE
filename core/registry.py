"""
Service registry.

The dashboard renders itself from this single list. Adding a new service later
means adding one entry here plus a route - nothing else in the UI needs to
change. This is the "easy to expand" requirement, made concrete.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Service:
    slug: str
    title: str
    subtitle: str
    icon: str  # key into static/icons sprite
    accent: str  # hex colour used for the tile accent
    status: str = "soon"  # "ready" | "soon"
    phase: str = ""
    endpoint: str = ""  # Flask endpoint; empty means services.<slug>
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    @property
    def route(self) -> str:
        """Endpoint used by url_for() so templates never hard-code URLs."""
        return self.endpoint or f"services.{self.slug}"


SERVICES: tuple[Service, ...] = (
    Service(
        slug="cv",
        title="CV / Resume",
        subtitle="Build, preview & export professional CVs",
        icon="cv",
        accent="#123a72",
        status="ready",
        phase="Templates & editor live",
        endpoint="cv.templates",
        tags=("A4", "PDF", "DOCX"),
    ),
    Service(
        slug="letters",
        title="Letters",
        subtitle="Letters, agreements & official documents",
        icon="letter",
        accent="#7c3aed",
        status="ready",
        phase="Document types live",
        endpoint="letters.index",
        tags=("Search", "PDF", "DOCX"),
    ),
    Service(
        slug="documents",
        title="Documents",
        subtitle="Type, print & export any free-format document",
        icon="document",
        accent="#0ea5e9",
        status="ready",
        phase="Free-format editor live",
        endpoint="documents.new",
        tags=("Editor", "PDF", "DOCX"),
    ),
    Service(
        slug="school",
        title="School Documents",
        subtitle="Certificates, letters & school forms",
        icon="school",
        accent="#f59e0b",
        phase="Phase 13",
    ),
    Service(
        slug="business",
        title="Business Documents",
        subtitle="Invoices, receipts, quotes & letters",
        icon="business",
        accent="#16a34a",
        phase="Phase 14",
    ),
    Service(
        slug="passport",
        title="Passport Photos",
        subtitle="Crop & tile passport photographs",
        icon="passport",
        accent="#db2777",
        phase="Phase 15",
    ),
    Service(
        slug="saved",
        title="Saved Work",
        subtitle="Open, duplicate or export past work",
        icon="saved",
        accent="#0f766e",
        status="ready",
        phase="Search & PDF/DOCX exports live",
        endpoint="saved.index",
        tags=("Search", "PDF", "DOCX"),
    ),
    Service(
        slug="templates",
        title="Templates",
        subtitle="Manage your document templates",
        icon="templates",
        accent="#ca8a04",
        status="ready",
        phase="Phase 10",
    ),
    Service(
        slug="settings",
        title="Settings",
        subtitle="Business details, storage & defaults",
        icon="settings",
        accent="#475569",
        phase="Phase 16",
    ),
    Service(
        slug="official_services",
        title="Official Services",
        subtitle="Government & Nigeria Police services via DERB",
        icon="shield",
        accent="#0b2545",
        status="ready",
        phase="Verified portal links",
        endpoint="services.official_services",
        tags=("Assist", "External links"),
    ),
)

SERVICES_BY_SLUG = {s.slug: s for s in SERVICES}


def get_service(slug: str) -> Service | None:
    return SERVICES_BY_SLUG.get(slug)
