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

**Five structural layouts, not a colour swap.** A theme only changes colour, so
`core/design_render.py` grew five genuinely different compositions - **hero**
(full-bleed photo + bottom type), **split** (photo panel + text column),
**ornate** (symmetrical framed programme/certificate), **strip** (headline band
+ photo strip + info band) and **grid** (airy collage + type stack). The
operator picks one, or leaves **Auto** to use the category default in
`DEFAULT_STYLE`. Each layout is emitted as an *element list* (background, rects,
ellipses, photos and measured text) rather than an HTML-only structure, so the
same spec drives the HTML preview, the print dialog and the canvas PNG/JPG
export identically. Adding a style is one `STYLES` entry plus one composition
function; adding a design type is still one `CATEGORIES` entry.

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

## 9. AI finishing: a background layer, never the text (Phase 9)

**The need:** a "Switch to AI Features" setting, and a "Finish with AI" action
inside the Graphic Design workspace that genuinely improves a customer's
existing flyer - without ever risking the customer's own wording.

**Settings became a real screen.** `/settings` was a "Coming Soon" placeholder
reusing the registry entry; the registry row now points at its own blueprint
(`web/settings.py`). The preference is stored in the **existing** `settings`
key/value table (`ai_features_enabled`), the same one that holds the default CV
template - no new storage and no migration. The switch is plain HTML + CSS
(a real `<input type="checkbox">` plus a styled track), so it works in an old
Android WebView with JavaScript unavailable.

**Four honest states, no guesswork.** `core/ai_service.status()` returns exactly
one of `disabled` (the operator switched it off), `not_configured` (on, but no
key in the environment), `unavailable` (configured, but the last attempt
failed) or `enabled`. The Settings page and every design screen render that
state verbatim, and enabling the switch without a key says so instead of
pretending to work. "Check AI connection" probes `GET {base}/models` - cheap,
and it deliberately does not generate an image just to answer a settings tap.

**Backdrop only - the text is never handed to the image model.** This is the
central decision. An image model cannot be trusted to reproduce a Nigerian
phone number, a venue or a date, so the prompt asks for *background artwork
explicitly without any letters, words, numbers or watermarks*, and the returned
image becomes a **base layer** in the existing engine: `_base()` in
`core/design_render.py` paints it full-bleed with a theme-tinted scrim
(`AI_SCRIM`), and then the composition draws its own text and photo elements on
top, unchanged. Hero already used its photo as the backdrop, so with an AI
backdrop the photo moves into a framed panel rather than disappearing. The
test asserts the strong form of this: for **all 15 categories x all 6 styles**
the AI variant's text elements are *byte-identical* to the plain engine's, and
the variant differs only by the backdrop + scrim.

**Nothing is saved until the operator accepts.** `POST /graphic-design/ai`
stores the generated image and re-renders the workspace in *review* mode, with
the AI version on the stage and the original shown underneath for comparison.
Accept persists it (same `projects` table, doc_type `DESIGN`), Try another asks
for a new variation, Reject deletes the temporary artwork and restores the
design. Once accepted, the backdrop travels with the design through every
hidden field - so editing, regenerating and re-saving keep it - and **Remove AI
background** deletes the file and restores the plain composition. PNG/JPG
export, printing and the canvas exporter are untouched, because the AI layer is
just another `photo` element in the same element spec.

**Failures are never disguised.** `finish_design()` raises a typed `AiError`
(`not_configured`, `bad_request`, `timeout`, `network`, `rate_limit`, `quota`,
`auth`, `provider`, `invalid_response`), each mapped to a plain-language message on the
design screen, and the operator's design is re-rendered untouched. A failure
records `ai_last_error`, which flips the status to `unavailable` so the next
visit to Settings tells the truth. A provider response is validated before it
is used: base64/URL image data is size-capped and its **magic bytes** are
sniffed (`design_store.sniff_image_ext`) because Pillow cannot be installed on
this toolchain - HTML or JSON dressed up as an image is rejected.

**Config is environment-only, and no SDK.** `DERB_AI_API_KEY`,
`DERB_AI_BASE_URL`, `DERB_AI_IMAGE_MODEL`, `DERB_AI_QUALITY`,
`DERB_AI_SIZE_OVERRIDE`, `DERB_AI_TIMEOUT`. The client speaks the documented
OpenAI Images API (`/images/generations` and `/images/edits`, the latter so the
customer's own photos and logos are actually sent along) over `urllib` with a
hand-rolled multipart encoder - so `requirements.txt` stays "Flask only" and
the phone still installs with zero build steps. Any OpenAI-compatible gateway
works by changing the base URL. The key is read on every call, never cached,
never stored in the database, never rendered and never logged; the tests set a
marker key and assert it appears in no page and no stored setting. Tests
therefore install a fake provider (`ai_service.set_provider`) - the suite never
makes a paid API call.

## 10. Accessibility from the start

Minimum 48px touch targets, `:focus-visible` outlines, `prefers-reduced-motion`
support and safe-area insets for notched phones.

## 11. Google Gemini as a second provider, spoken natively (Phase 9+)

**The need:** the operator wants to finish designs with a **Gemini API key**,
not only an OpenAI one. The provider seam from section 9 already exists, so the
work is a second implementation behind it - not a rewrite.

**Not the OpenAI-compatibility layer.** Google publishes an
OpenAI-compatible endpoint (`{base}/v1beta/openai`, `POST /images/generations`),
so it is tempting to support Gemini with nothing but a base-URL change. We
deliberately did not, for one concrete reason: that layer has **no
`/images/edits` equivalent**. DERB sends the customer's own photos to
`/images/edits` whenever a design has uploads, so a pure base-URL swap would
work for text-only designs and then silently drop the customer's photos - a
wrong result presented as a right one, which is exactly what the honest-failure
rule forbids. Gemini does image-to-image through the *same* call as
text-to-image, so the provider is written against the native API:
`POST {base}/models/{model}:generateContent` with the key in the
`x-goog-api-key` header (never a query parameter, so it cannot land in a log
line), the prompt as a `text` part and each photo as an `inline_data` part.

**Selection is explicit, never guessed.** `DERB_AI_PROVIDER` is either
`gemini` or `openai-images` (the default, so existing setups are untouched).
Each provider owns its own base URL and default model
(`gemini-2.5-flash-image`, `gpt-image-1`), and the reference-image cap
(`max_input_images`: 3 for Gemini, 4 for OpenAI) so the request stays valid for
the engine that will actually run. An unrecognised value falls back to the
default rather than inspecting the key's shape - guessing a provider from a key
is precisely the kind of pretence this project avoids.

**The probe follows the provider.** "Check AI connection" probes
`GET {base}/models`, but Gemini authenticates with `x-goog-api-key` rather than
`Authorization: Bearer`, so `check_connection()` delegates to the provider's own
`check()` instead of hard-coding one header. It deliberately probes the
*configured* provider (not a test override) because the operator's question is
"will my key work against my provider?". Failures map onto the same
`AiError` kinds as generation, so the UI wording is unchanged. A Gemini
safety/recitation block (a `promptFeedback.blockReason` with no candidate) is
reported as `bad_request` with the reason, and a non-image or unrecognised
payload is rejected by the same magic-byte sniffing as every other provider.

**429 is two different things.** A rate limit and an exhausted quota both
arrive as HTTP 429, and telling the operator to "try again shortly" when the
real fix is billing would send them in circles. The provider's own message is
the only reliable discriminator, so a 429 whose body says *quota* is raised as
the separate `quota` kind (with the provider's words attached and a
billing-shaped hint), and only a genuine throttle stays `rate_limit`. Both
providers share one `_raise_rate_limit()` helper so they cannot drift apart.

**Same guarantees.** The text rule (section 9) is unchanged: the Gemini prompt
is the same background-artwork-only prompt, and DERB's engine still re-draws
every name, date, venue and phone number on top. The key is still read from the
environment on every call and never stored, rendered or logged. Tests stub
`urllib.request.urlopen` and assert the real request shape (URL, header, body)
without a network call, plus an end-to-end run through `/graphic-design/ai`.

**On-device key entry.** Typing a key after `export` leaves it in the shell
history, so `scripts/set_ai_key.sh` reads it with a hidden prompt and writes the
gitignored `.env.local`, and `config.load_local_env()` (called **only** from the
entry point `app.py`, never from anything the tests import, which keeps the
suite hermetic) reads it back. It honours `DERB_*` keys only - a stray file
cannot rewrite `PATH` - and never overrides a real environment variable, so the
environment stays the single source of truth and wins on conflict. `app.py`
announces only the *names* it loaded, never a value, and the value still
reaches nothing but the provider request header. This is convenience for the
operator, not a second configuration layer.
