#!/usr/bin/env python3
"""
DERB MOBILE - Official Services test.

Walks the real /official-services screen through the Flask app (the same thing
the phone browser hits) and checks the things that actually matter:

  * the page renders, with every catalog service on it
  * the "Official Website" behind each card is a REAL, allow-listed portal
    (npf.gov.ng / cmris.npf.gov.ng / possap.gov.ng) - never a guessed address
  * services with no dedicated page say so on the card
  * the page makes no network request of its own (no avatar CDN, no <img src>)
  * the live search markup the page filter depends on is present
  * "Get Assistance" leads to a real, working in-app flow

Run:
    python scripts/test_official_services.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import html as html_lib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

passes = 0
failures: list[str] = []

# Hosts we have opened and verified. A card must never point anywhere else.
ALLOWED_PORTAL_HOSTS = {"www.npf.gov.ng", "cmris.npf.gov.ng", "possap.gov.ng"}

# Portal paths that are a general index rather than a page about one service.
GENERIC_PORTAL_PATHS = {"/", "/services"}


def check(label: str, condition: bool, detail: str = "") -> None:
    global passes
    if condition:
        passes += 1
        print(f"  [PASS] {label}")
    else:
        failures.append(f"{label}{(' -> ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    print("DERB MOBILE - Official Services test")
    print("-" * 52)

    from core import db, official_services as catalog, registry

    db.init_db()

    # ------------------------------------------------------------- the catalog
    print("Catalog")
    services = catalog.OFFICIAL_SERVICES
    check("Catalog has services", len(services) >= 6, f"found {len(services)}")
    check("Service slugs are unique", len({s.slug for s in services}) == len(services))

    for service in services:
        parsed = urlparse(service.portal_url)
        check(
            f"Verified portal host: {service.slug}",
            parsed.scheme == "https" and parsed.netloc in ALLOWED_PORTAL_HOSTS,
            service.portal_url or "(no URL)",
        )
        check(
            f"Card states the link target: {service.slug}",
            parsed.path not in GENERIC_PORTAL_PATHS or bool(service.portal_note),
            f"generic link {parsed.path} without a portal_note",
        )
        check(
            f"Offline initials avatar: {service.slug}",
            re.fullmatch(r"[A-Z0-9]{1,2}", service.initials) is not None,
            service.initials,
        )
        check(
            f"Search text is lower-case: {service.slug}",
            service.search_text == service.search_text.lower() and bool(service.search_text),
        )

    check(
        "Featured services are a subset of all services",
        set(catalog.FEATURED_OFFICIAL_SERVICES) <= set(services),
    )
    check("Verified date recorded", bool(catalog.VERIFIED_ON), catalog.VERIFIED_ON)

    # ------------------------------------------------------------- the registry
    print("Dashboard integration")
    tile = registry.get_service("official_services")
    check("Registry has the Official Services service", tile is not None)
    check("Official Services tile is marked Ready", tile is not None and tile.is_ready)

    # ------------------------------------------------------------------- HTTP
    print("The screen itself (via Flask test client)")
    from web import create_app

    client = create_app().test_client()

    resp = client.get("/official-services")
    check("GET /official-services -> 200", resp.status_code == 200,
          f"status {resp.status_code}")
    html = resp.get_data(as_text=True)

    home = client.get("/").get_data(as_text=True)
    check("Dashboard shows the Official Services tile", "Official Services" in home)

    # Jinja escapes text and attributes, so compare against escaped names.
    for service in services:
        check(f"Service listed: {service.name}",
              html_lib.escape(service.name) in html)

    featured = catalog.FEATURED_OFFICIAL_SERVICES
    check("Featured services rendered in their own section",
          'data-service-section="featured"' in html
          and all(html_lib.escape(s.name) in html for s in featured))

    for service in services:
        check(f"Portal link present: {service.slug}",
              f'href="{service.portal_url}"' in html)
    check("External links open safely",
          html.count('rel="noopener noreferrer"') >= len(services))
    for service in services:
        if service.portal_note:
            check(f"Card explains the link target: {service.slug}",
                  service.portal_note in html)

    # --------------------------------------------------- offline / no CDN rule
    print("Offline safety")
    check("No external avatar service", "ui-avatars" not in html)
    check("No placeholder government URL", "example.gov.ng" not in html)
    check("No remote images on the page", 'src="http' not in html and "srcset=" not in html)
    check("No http:// links at all", "http://" not in html)
    check("Source note shown", catalog.SOURCE_NOTE.split(".")[0] in html)
    check("Verification date shown to the customer", catalog.VERIFIED_ON in html)

    css = (PROJECT_ROOT / "static" / "css" / "official_services.css").read_text()
    check("Official Services CSS is CDN-free",
          "http://" not in css and "https://" not in css)

    # ------------------------------------------------------------ search markup
    print("Live search markup")
    check("Search input present", 'id="os-search"' in html)
    check("Both lists are filter targets", html.count("data-service-list") >= 2)
    for service in services:
        check(f"Card carries filter text: {service.slug}",
              f'data-search="{html_lib.escape(service.search_text, quote=True)}"' in html)
    check("Empty-search state present", 'id="os-empty"' in html)

    # ------------------------------------------------------------- assistance
    print("Assistance flow")
    check("Cards link to the in-app assistance flow",
          'href="/letters/new?doc=request-letter"' in html)
    assist = client.get("/letters/new?doc=request-letter")
    check("Assistance target works", assist.status_code == 200,
          f"status {assist.status_code}")
    check("Assistance target is the request-letter form",
          "Request Letter" in assist.get_data(as_text=True))

    print("-" * 52)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print("  -", failure)
        return 1
    print("All Official Services checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
