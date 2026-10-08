# DERB MOBILE - Technical Decisions

Short record of the choices made while building, and why. Kept so future
phases stay consistent.

## 1. Framework: Flask (as requested) - confirmed working

Installed with binary wheels only, so nothing compiles on the phone:

```
python -m pip install --only-binary=:all: flask
Successfully installed flask-3.1.3 werkzeug-3.1.9 jinja2-3.1.6
                     markupsafe-3.0.4 itsdangerous-2.2.0 click-8.5.0 blinker-1.9.0
```

`markupsafe` resolved to an Android `cp314` wheel - good. No build step needed.

## 2. PDF export: standard library writer + browser print (decided)

**Attempted:** `fpdf2`, the usual lightweight PDF library.

**Result:** it failed to install because it depends on **Pillow**, which tried to
compile and crashed on this mixed Termux/glibc toolchain:

```
/usr/include/features-time64.h:20:10: fatal error: 'bits/wordsize.h' file not found
ERROR: Failed building wheel for Pillow
```

The same class of failure affects `lxml` (used by `python-docx`), `cairo`
(`weasyprint`) and `ReportLab`. Requiring any of them would mean DERB MOBILE
cannot be installed offline without a build toolchain.

**Decision (Phase 6):** generate A4 PDFs with a small, self-contained PDF writer
built on the standard library only:

* Built-in PDF fonts (Helvetica / Times / Courier) - no font files to embed,
  no Pillow needed.
* Real A4 page box, print-ready, openable by any Android PDF viewer.
* Text is limited to the built-in font character set; unusual characters are
  transliterated, and this is stated in the UI.

**Plus** a second, always-available path: the live A4 preview is HTML/CSS, so
the phone browser's own **Print → Save as PDF** produces a pixel-perfect PDF for
free. That is the closest practical offline solution, and it is offered
alongside the generated file rather than instead of it.

## 3. DOCX export: hand-written OOXML (decided)

`python-docx` needs `lxml`, which hits the same compile wall as Pillow.

A `.docx` file is a ZIP of XML parts. Phase 7 will build a real Word document
with the standard library's `zipfile` + `xml` modules and the correct
`[Content_Types].xml`, `word/document.xml`, styles and relationships.

This produces a **genuinely editable Word file** (not an HTML file renamed),
which is exactly what was requested, with zero dependencies.

## 4. Database: standard-library `sqlite3`

No ORM. Three small tables (`projects`, `templates`, `settings`) and thin
repository functions in `core/`. Keeps memory use low on a budget phone and
means new services only need new columns/rows, not migrations tooling.

## 5. Frontend: no CDNs, no web fonts, no build step

* System font stack only - nothing to download, renders instantly offline.
* Icons are inline SVG (one Jinja macro) - no icon font, no image requests.
* One stylesheet, one small JS file. Cache-busted by version query string.
* `color-mix()` is used for accent tints with a `@supports` fallback for older
  Android WebViews.

## 6. Official Services: real links only, no CDN avatars (decided)

The `/official-services` screen lists government and Nigeria Police services
DERB assists with. Two rules shaped it.

**Links must be verified.** An earlier draft pointed every card at a
`https://example.gov.ng/services/<slug>` placeholder. That is a guessed
government address, so it was removed. The catalog in `core/official_services.py`
now allows only hosts we have opened and seen the service on
(`www.npf.gov.ng`, `cmris.npf.gov.ng`, `possap.gov.ng`), and the test suite
fails if a card points anywhere else. Where a service has no dedicated page the
card links the official index **and** says so in `portal_note`, and a service
with no verified link at all shows "link pending verification" instead of a
button. `VERIFIED_ON` records when the links were last checked and is shown to
the customer.

The page also states plainly that DERB does not apply, submit or pay on the
customer's behalf - the application is completed on the official portal.

**Avatars must work offline.** The draft loaded card icons from
`ui-avatars.com`, which is a CDN: on a phone with no data the cards would show
broken images, and it leaks the customer's browsing to a third party. Avatars
are now two initials rendered from the service name in the service accent
colour - pure CSS text, zero network. The smoke test's "no CDN references"
check covers the new stylesheet too.

The live search filter is ~30 lines of dependency-free JS in the page's
`{% block scripts %}`. While searching it hides the "Featured" copy of the
cards so matches are not listed twice.

## 7. Free-format Documents reuse the shared project table & export engines

**The need:** besides tiled CV and catalogue letters, customers bring text to
be typed verbatim - a speech, essay, assignment, report or minutes. That is not
the template-driven Letters flow, so it became its own **Documents** service
(Phase 7).

**Decision:** a Document is stored in the very same `projects` table under
`doc_type='DOCUMENT'` with `template_slug='free-format'`. There is no second
storage path, migration or backup story - **Saved Work** lists CVs and documents
together (newest first), and the PDF/DOCX exports go through the same Phase 4
engines (`core/cv_pdf._Doc`, the OOXML helpers in `core/cv_docx.py`), writing to
`DERB/Documents/`. `core/doc_model.py` is the single producer of the payload;
`normalize()`/`plain()` reduce anything pasted from a web page to safe text (no
scripts, remote images or event handlers), which keeps the no-CDN guarantee by
construction.

Letters deliberately stay separate: they are structured templates with their
own preview and `Saved Letters` screen, so folding them into this table would
have flattened a meaningful distinction. A save posted against a foreign
`doc_type` id never overwrites that row - it creates a new document instead
(covered by the test).

## 8. Graphic Design reuses the empty Passport Photo slot (Phase 8)

**The need:** an operator tool to turn a customer's flyer/anniversary/
certificate request into a finished design fast - not a customer-facing Canva.

**Where it lives.** The dashboard's **Passport Photo** tile was inspected and
found to be an empty placeholder (no template, no route logic, no model - it
rendered the generic "Coming Soon" screen). So that slot was repurposed into
the **Graphic Design** workspace: the registry entry, tile and the `/passport`
route were reused, and `/passport` now **redirects** to `/graphic-design` so
no old link breaks. There is deliberately only ONE design workspace - no
duplicate tile or route. The `DERB/Passport/` folder key is kept for
compatibility; designs write to `DERB/Designs/`.

**First screen is a category grid, not a blank editor.** 15 design types live
in `core/design_catalog.py`; each category owns its own field list (an
Anniversary asks for a theme and anniversary number, a Certificate for an
awardee and signatory). A new type is one catalog entry. Categories are
marked with initials-free inline icons - no CDN, matching the rest of the app.

**Generation is honest.** `core/design_generation.py` exposes a provider
seam. The active provider is a real, deterministic **layout engine**
(`core/design_render.py`) that produces a poster from the operator's input -
there is NO AI provider connected, and the UI says so on every design screen
rather than presenting a static image as AI output. Connecting a real service
means implementing `AiDesignProvider` and flipping one flag; nothing else
changes.

**Exports under the no-image-library rule.** Design uploads are stored
locally (`data/design_images/`, same private-store pattern as CV photos).
Because this toolchain cannot build Pillow, the server cannot rasterize PNG/
JPG - so JPG/PNG download is drawn on a `<canvas>` in the browser from the
layout JSON (offline, no CDN), and PDF comes from the browser's
Print → Save as PDF, exactly like the Document preview. The layout spec is
shared, so preview, print and the canvas export all match.

**Saved Work.** Designs persist in the same `projects` table
(doc_type='DESIGN'), so they list beside CVs, letters and documents with no
new storage system.

## 9. Accessibility from the start

Minimum 48px touch targets, `:focus-visible` outlines, `prefers-reduced-motion`
support and safe-area insets for notched phones.
