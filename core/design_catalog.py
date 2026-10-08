"""
Graphic Design catalog for DERB MOBILE.

Single source of truth for the Graphic Design workspace (which reuses the
former Passport Photo placeholder page - see docs/DECISIONS.md). The category
picker, the per-category forms, the layout renderer and the tests all read
from here, so adding a design type later means adding ONE entry below.

    CATEGORY  ->  FORM FIELDS  ->  LAYOUT  ->  PREVIEW  ->  PRINT / PNG / JPG

A category owns:

* ``fields``  - the keys (from FIELD_DEFS) that make up its form. Categories
  deliberately do NOT share one generic form: an Anniversary asks for a theme
  and an anniversary number, a Certificate asks for an awardee and signatory.
* ``theme``   - the default colour theme (THEMES); the operator can override.
* ``aspect``  - the poster shape (portrait A4, landscape, square or banner).

DERB MOBILE is an operator tool for fast customer service, not a public
design canvas - so this catalog is about *ready professional layouts* the
operator fills in, never a blank editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Colour themes - applied by the HTML preview and the canvas export alike.
# ---------------------------------------------------------------------------
THEMES: dict[str, dict[str, str]] = {
    "gold-white": {"name": "Gold & White", "bg1": "#fffdf5", "bg2": "#fdf1cf",
                   "accent": "#b8860b", "ink": "#2b2b2b", "muted": "#6b5b2a",
                   "band_ink": "#ffffff"},
    "navy-gold": {"name": "Navy & Gold", "bg1": "#0b2545", "bg2": "#123a72",
                  "accent": "#f2c14e", "ink": "#ffffff", "muted": "#cdd8ec",
                  "band_ink": "#0b2545"},
    "royal-purple": {"name": "Royal Purple", "bg1": "#2e1065", "bg2": "#4c1d95",
                     "accent": "#fbbf24", "ink": "#ffffff", "muted": "#ddd0ff",
                     "band_ink": "#2e1065"},
    "teal-modern": {"name": "Teal Modern", "bg1": "#f0fdfa", "bg2": "#ccfbf1",
                    "accent": "#0f766e", "ink": "#0f2f2b", "muted": "#3f6b64",
                    "band_ink": "#ffffff"},
    "crimson": {"name": "Crimson", "bg1": "#fef2f2", "bg2": "#fee2e2",
                "accent": "#b91c1c", "ink": "#2b2b2b", "muted": "#7a3232",
                "band_ink": "#ffffff"},
    "emerald": {"name": "Emerald", "bg1": "#ecfdf5", "bg2": "#d1fae5",
                "accent": "#047857", "ink": "#0c2b22", "muted": "#33685a",
                "band_ink": "#ffffff"},
    "midnight": {"name": "Midnight Gold", "bg1": "#000000", "bg2": "#1f2937",
                 "accent": "#e0b64a", "ink": "#ffffff", "muted": "#c7cbd4",
                 "band_ink": "#000000"},
    "rose": {"name": "Rose", "bg1": "#fff1f2", "bg2": "#ffe4e6",
             "accent": "#be123c", "ink": "#3b0a1e", "muted": "#8a3d55",
             "band_ink": "#ffffff"},
}
DEFAULT_THEME = "navy-gold"


# ---------------------------------------------------------------------------
# Field definitions shared across categories (kept small on purpose).
# ---------------------------------------------------------------------------
FIELD_DEFS: dict[str, dict[str, str]] = {
    "name": {"label": "Name", "type": "text", "placeholder": "e.g. Chinedu Okafor"},
    "honoree": {"label": "Honoree / Celebrant", "type": "text"},
    "age": {"label": "Age", "type": "text", "inputmode": "numeric"},
    "date_event": {"label": "Date", "type": "date"},
    "time_event": {"label": "Time", "type": "time"},
    "venue": {"label": "Venue", "type": "text"},
    "message": {"label": "Message", "type": "textarea"},
    "contact": {"label": "Contact Information", "type": "text",
                "placeholder": "Phone, WhatsApp or email"},
    "anniversary_type": {"label": "Type of Anniversary", "type": "text",
                         "placeholder": "e.g. Choir Anniversary"},
    "anniversary_number": {"label": "Anniversary Number", "type": "text",
                           "placeholder": "e.g. 10th"},
    "organisation": {"label": "Organisation / Church / Group", "type": "text"},
    "main_title": {"label": "Main Title", "type": "text"},
    "theme": {"label": "Theme", "type": "text"},
    "guest_minister": {"label": "Guest Minister / Speaker", "type": "text"},
    "special_guests": {"label": "Special Guests", "type": "text"},
    "details": {"label": "Main Content / Details", "type": "textarea"},
    "position": {"label": "Position / Role", "type": "text"},
    "years_service": {"label": "Years of Service", "type": "text",
                      "inputmode": "numeric"},
    "retirement_date": {"label": "Retirement Date", "type": "date"},
    "appreciation": {"label": "Appreciation Message", "type": "textarea"},
    "couple_names": {"label": "Couple's Names", "type": "text"},
    "wedding_date": {"label": "Wedding Date", "type": "date"},
    "officiating": {"label": "Officiating Minister", "type": "text"},
    "colour_theme": {"label": "Colour Theme", "type": "text"},
    "programme": {"label": "Programme / Order of Service", "type": "textarea"},
    "deceased_name": {"label": "Name of the Deceased", "type": "text"},
    "born_date": {"label": "Date of Birth", "type": "date"},
    "died_date": {"label": "Date of Death", "type": "date"},
    "funeral_details": {"label": "Funeral Arrangements", "type": "textarea"},
    "graduate_name": {"label": "Graduate's Name", "type": "text"},
    "degree": {"label": "Degree / Qualification", "type": "text"},
    "institution": {"label": "Institution", "type": "text"},
    "graduation_date": {"label": "Graduation Date", "type": "date"},
    "business_name": {"label": "Business Name", "type": "text"},
    "business_type": {"label": "Business Type", "type": "text",
                      "placeholder": "e.g. Fashion, Restaurant, POS"},
    "offerings": {"label": "Products / Services", "type": "textarea"},
    "address": {"label": "Address", "type": "text"},
    "socials": {"label": "Social Media / Contact", "type": "text",
                "placeholder": "e.g. @derbfinance, 0803 000 0000"},
    "promo_message": {"label": "Promotional Message", "type": "textarea"},
    "product_name": {"label": "Product Name", "type": "text"},
    "price": {"label": "Price", "type": "text", "inputmode": "decimal"},
    "offer": {"label": "Offer / Discount", "type": "text"},
    "event_name": {"label": "Event Name", "type": "text"},
    "event_details": {"label": "Event Details", "type": "textarea"},
    "hosts": {"label": "Host(s)", "type": "text"},
    "social_handle": {"label": "Page / Handle", "type": "text"},
    "post_text": {"label": "Post Text", "type": "textarea"},
    "hashtags": {"label": "Hashtags", "type": "text"},
    "invitee": {"label": "Invitee / Guest", "type": "text"},
    "host_name": {"label": "Host Name", "type": "text"},
    "certificate_title": {"label": "Certificate Title", "type": "text",
                          "placeholder": "e.g. Certificate of Achievement"},
    "awardee": {"label": "Awardee / Recipient", "type": "text"},
    "certificate_body": {"label": "Certificate Body", "type": "textarea"},
    "signatory": {"label": "Signatory & Title", "type": "text"},
    "headline": {"label": "Headline", "type": "text"},
    "subtext": {"label": "Supporting Text", "type": "textarea"},
    "custom_title": {"label": "Title", "type": "text"},
    "custom_body": {"label": "Body / Content", "type": "textarea"},
    "style_notes": {"label": "Style Notes", "type": "text",
                    "placeholder": "e.g. gold and white, bold title"},
}


@dataclass(frozen=True)
class DesignCategory:
    slug: str
    name: str
    icon: str
    accent: str
    description: str
    fields: tuple[str, ...]
    theme: str = DEFAULT_THEME
    aspect: str = "portrait"      # portrait | landscape | square | banner
    photo_hint: str = ""
    keywords: str = ""
    featured: bool = False

    def field_defs(self) -> tuple[dict[str, str], ...]:
        """Resolve ``fields`` to their definitions, in order."""
        out = []
        for key in self.fields:
            meta = dict(FIELD_DEFS.get(key, {}))
            meta.setdefault("label", key.replace("_", " ").title())
            meta.setdefault("type", "text")
            meta["key"] = key
            out.append(meta)
        return tuple(out)

    @property
    def search_text(self) -> str:
        parts = [self.name, self.description, self.keywords]
        return " ".join(p for p in parts if p).lower()


# ---------------------------------------------------------------------------
# The design categories.
# ---------------------------------------------------------------------------
CATEGORIES: tuple[DesignCategory, ...] = (
    DesignCategory(
        slug="birthday", name="Birthday", icon="cake", accent="#db2777",
        description="Birthday flyer or card with name, age and message.",
        fields=("honoree", "age", "date_event", "time_event", "venue",
                "message", "contact"),
        theme="crimson", photo_hint="Photo of the celebrant",
        keywords="birthday bday party age celebrant flyer", featured=True,
    ),
    DesignCategory(
        slug="anniversary", name="Anniversary", icon="rings", accent="#b8860b",
        description="Choir, church or organisation anniversary programme.",
        fields=("anniversary_type", "organisation", "main_title",
                "anniversary_number", "theme", "date_event", "time_event",
                "venue", "guest_minister", "special_guests", "contact",
                "details"),
        theme="gold-white", photo_hint="Guest minister, choir or logo photos",
        keywords="anniversary choir church celebration years",
        featured=True,
    ),
    DesignCategory(
        slug="retirement", name="Retirement", icon="award", accent="#0f766e",
        description="Retirement celebration flyer with service history.",
        fields=("name", "organisation", "position", "years_service",
                "retirement_date", "venue", "appreciation", "contact"),
        theme="teal-modern", photo_hint="Photo of the retiree",
        keywords="retirement service send forth celebration",
    ),
    DesignCategory(
        slug="wedding", name="Wedding", icon="rings", accent="#be123c",
        description="Wedding invitation with couple, date and venue.",
        fields=("couple_names", "wedding_date", "time_event", "venue",
                "officiating", "colour_theme", "message", "contact"),
        theme="rose", photo_hint="Couple's photos",
        keywords="wedding marriage couple invitation", featured=True,
    ),
    DesignCategory(
        slug="church-programme", name="Church Programme", icon="church",
        accent="#4c1d95",
        description="Church service, crusade or convention programme.",
        fields=("organisation", "main_title", "theme", "date_event",
                "time_event", "venue", "guest_minister", "programme",
                "contact"),
        theme="royal-purple", photo_hint="Minister, choir or church photos",
        keywords="church programme crusade convention service",
    ),
    DesignCategory(
        slug="funeral", name="Funeral / Memorial", icon="ribbon",
        accent="#334155",
        description="Funeral or memorial service programme.",
        fields=("deceased_name", "born_date", "died_date", "funeral_details",
                "date_event", "time_event", "venue", "contact"),
        theme="midnight", photo_hint="Portrait of the deceased",
        keywords="funeral memorial burial service programme",
    ),
    DesignCategory(
        slug="graduation", name="Graduation", icon="cap", accent="#0ea5e9",
        description="Graduation celebration flyer.",
        fields=("graduate_name", "degree", "institution", "graduation_date",
                "message", "contact"),
        theme="teal-modern", photo_hint="Graduation photo",
        keywords="graduation convocation degree graduate",
    ),
    DesignCategory(
        slug="business-advert", name="Business Advert", icon="business",
        accent="#16a34a",
        description="Business advert with services and contact details.",
        fields=("business_name", "business_type", "offerings", "address",
                "contact", "socials", "promo_message"),
        theme="emerald", photo_hint="Business logo or product photos",
        keywords="business advert advertising promo company services",
        featured=True,
    ),
    DesignCategory(
        slug="product-advert", name="Product Advert", icon="tag",
        accent="#ea580c",
        description="Product promo with price and offer.",
        fields=("product_name", "price", "offer", "business_name",
                "promo_message", "contact", "socials"),
        theme="crimson", aspect="square", photo_hint="Product photograph",
        keywords="product promo sale price offer advert",
    ),
    DesignCategory(
        slug="event", name="Event", icon="calendar", accent="#7c3aed",
        description="Event flyer with name, date, venue and details.",
        fields=("event_name", "date_event", "time_event", "venue", "hosts",
                "event_details", "contact"),
        theme="royal-purple", photo_hint="Event or venue photos",
        keywords="event flyer concert show party",
    ),
    DesignCategory(
        slug="social-media", name="Social Media", icon="share", accent="#2563eb",
        description="Square post for WhatsApp, Facebook or Instagram.",
        fields=("social_handle", "main_title", "post_text", "hashtags",
                "contact"),
        theme="navy-gold", aspect="square", photo_hint="Profile or cover image",
        keywords="social media post whatsapp facebook instagram status",
    ),
    DesignCategory(
        slug="invitation", name="Invitation", icon="envelope", accent="#b8860b",
        description="General invitation card.",
        fields=("host_name", "invitee", "event_name", "date_event",
                "time_event", "venue", "message", "contact"),
        theme="gold-white", photo_hint="Host or event photo",
        keywords="invitation invite card guest",
    ),
    DesignCategory(
        slug="certificate", name="Certificate", icon="certificate",
        accent="#0f766e",
        description="Certificate of achievement, completion or recognition.",
        fields=("certificate_title", "awardee", "certificate_body",
                "date_event", "organisation", "signatory"),
        theme="teal-modern", aspect="landscape",
        photo_hint="Organisation logo (optional)",
        keywords="certificate award recognition achievement completion",
    ),
    DesignCategory(
        slug="banner", name="Banner", icon="banner", accent="#0b2545",
        description="Wide banner or backdrop for an event.",
        fields=("headline", "subtext", "organisation", "venue", "contact"),
        theme="navy-gold", aspect="banner", photo_hint="Logo or background photo",
        keywords="banner backdrop headline wide",
    ),
    DesignCategory(
        slug="custom", name="Custom Design", icon="design", accent="#475569",
        description="Free-format design when nothing else fits.",
        fields=("custom_title", "custom_body", "style_notes", "contact"),
        theme="midnight", photo_hint="Any images you want included",
        keywords="custom other free format design",
    ),
)

CATEGORIES_BY_SLUG: dict[str, DesignCategory] = {c.slug: c for c in CATEGORIES}

FEATURED_CATEGORIES: tuple[DesignCategory, ...] = tuple(
    c for c in CATEGORIES if c.featured
)

# Poster shapes: aspect = width / height.
ASPECTS: dict[str, float] = {
    "portrait": 0.7071,   # A4 portrait
    "landscape": 1.4142,  # A4 landscape
    "square": 1.0,
    "banner": 2.5,
}


def get_category(slug: str | None) -> DesignCategory | None:
    return CATEGORIES_BY_SLUG.get(slug or "")


def get_theme(slug: str | None) -> dict[str, str]:
    return THEMES.get(slug or "", THEMES[DEFAULT_THEME])
