# DERB MOBILE

**DERB FINANCE CONCEPTS** &middot; Offline Document Studio for Android (Termux)

Builds customer documents - CVs, letters and any free-format text - entirely
offline on your phone and saves them to a local folder you can transfer to a PC
for printing.

---

## Status

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 | Project structure (Flask + SQLite + document tree) | **Done** |
| 2 | Mobile dashboard with DERB branding and 10 services | **Done** |
| 3 | CV template system + CV editor + live A4 preview + Saved Work | **Done** |
| 4 | PDF & DOCX export (standard-library writers) | **Done** |
| 5 | Letters & Documents: 86 document types, 7 categories, dynamic forms, Saved Letters | **Done** |
| 6 | Official Services: verified police/government portal links + live search | **Done** |
| 7 | Free-format Document editor: type anything, print, PDF & DOCX export | **Done** |
| 8 | Graphic Design workspace: 15 design types, per-type forms, image upload, 5 layout styles, layout engine, print/PNG/JPG | **Done** |
| 9 | Settings + **Switch to AI Features**: AI finishing (background artwork) for Graphic Design | **Done** |
| 10 | Template Manager + remaining services (School, Business) | Next |

> CV / Resume, Letters, the free-format Document editor, Graphic Design,
> Official Services and **Settings** are live. School, Business and Templates
> are visible on the dashboard and clearly marked **Coming Soon** - they are
> placeholders, not broken links.
>
> **AI finishing ships switched off, and no AI provider is connected by
> default.** Turn it on in **Settings &rarr; Switch to AI Features** and see
> [Connecting an AI provider](#connecting-an-ai-provider). With it off, the
> Graphic Design editor behaves exactly as it always has.
>
> **Graphic Design** lives on the old **Passport Photo** tile (the placeholder
> was empty). The `/passport` URL still works - it redirects to the workspace.
> There is no separate Graphic Design tile.

---

## Start the app

```bash
cd ~/DERB-Mobile
bash start.sh
```

Or directly:

```bash
cd ~/DERB-Mobile
python app.py
```

First run installs Flask automatically if it is missing (needs internet **once**).
After that, everything runs offline.

You will see:

```
====================================================
  DERB FINANCE CONCEPTS
  DERB MOBILE  v1.0.0
====================================================
  Phone (this device):  http://localhost:8080
  Same Wi-Fi network:   http://192.168.x.x:8080
  Documents folder:     /data/data/com.termux/files/home/DERB-Mobile/DERB
  Database:             /data/data/com.termux/files/home/DERB-Mobile/data/derb.db
====================================================
```

## Open it on your Android phone

1. Start the server in Termux (above).
2. Open your phone browser (Chrome) and go to:

   **http://localhost:8080**

   (If a browser refuses `localhost`, use the `http://192.168.x.x:8080` address
   from the banner - that is the same phone on your Wi-Fi.)
3. Optional: menu &rarr; **Add to Home screen** for an app-like icon.

To reach it from a **PC on the same Wi-Fi**, type the `192.168.x.x:8080` address
into the PC browser.

Stop the server with `CTRL+C` in Termux.

---

## Test it

```bash
cd ~/DERB-Mobile
python scripts/smoke_test.py             # 42 checks - foundation & dashboard
python scripts/test_cv_workflow.py       # 64 checks - template picker/editor/save
python scripts/test_exports.py           # 29 checks - CV PDF & DOCX export
python scripts/test_letters.py           # 154 checks - letters & documents module
python scripts/test_official_services.py # 93 checks - official services page
python scripts/test_doc_workflow.py      # 84 checks - free-format Document editor
python scripts/test_graphic_design.py    # 233 checks - Graphic Design workflow
python scripts/test_ai_features.py       # 136 checks - AI switch + AI finishing
python scripts/test_gemini_provider.py   # 77 checks - Gemini provider + private key entry
```

`test_ai_features.py` installs a **fake image provider**, so the suite never
makes a paid API call and never needs the internet. It also proves the
honest-failure rule: when the provider fails, the app says so and leaves the
operator's design untouched rather than showing a fake result.

The export test walks the real workflow: create project, export PDF and DOCX
over HTTP, verify the files contain the customer's real data, store in
`DERB/CV/PDF` and `DERB/CV/DOCX`, handle a 14-job CV across multiple PDF pages,
and clean up after itself.

---

## Project layout

```
DERB-Mobile/
├── app.py                  # entry point / server
├── config.py               # branding, paths, port
├── start.sh                # one-command launcher
├── requirements.txt        # Flask only
├── core/
│   ├── paths.py            # document tree + safe filenames
│   ├── db.py               # SQLite schema + built-in templates
│   ├── registry.py         # the 10 services (dashboard is generated from this)
│   ├── official_services.py # verified police/gov portal catalog (Phase 6)
│   ├── doc_model.py        # free-format Document model + sanitisation
│   ├── doc_pdf.py          # Document PDF writer (shared Phase 4 engine)
│   ├── doc_docx.py         # Document DOCX writer (shared Phase 4 engine)
│   ├── design_catalog.py   # Graphic Design categories + per-type fields + themes
│   ├── design_model.py     # design payload model + sanitisation
│   ├── design_store.py     # multi-image upload store (local, offline)
│   ├── design_render.py    # deterministic layout engine (HTML + canvas)
│   ├── design_generation.py # generation provider seam + honest AI status
│   ├── ai_service.py       # AI finishing: provider client, validation, status
│   ├── templates_repo.py   # template queries + default-template setting
│   └── projects_repo.py    # saved-project queries
├── web/
│   ├── __init__.py         # Flask app factory, error pages
│   ├── dashboard.py        # home screen, /about, /health
│   ├── documents.py        # free-format Document editor/preview/export
│   ├── design.py           # Graphic Design workspace (the Passport Photo slot)
│   ├── settings.py         # Settings + the Switch to AI Features preference
│   └── services.py         # routes for all services, incl. /official-services
├── templates/              # Jinja screens
│   ├── base.html
│   ├── partials/icons.html # inline SVG icon macro
│   └── pages/…
├── static/
│   ├── css/app.css         # mobile-first stylesheet
│   ├── js/app.js           # tiny UI helpers
│   └── img/derb-logo.svg
├── data/derb.db            # SQLite database (created on first run)
├── DERB/                   # your documents
│   ├── CV/{Projects,PDF,DOCX}
│   ├── Letters/ Documents/ Designs/ School/ Business/ Passport/ Templates/
└── scripts/smoke_test.py
```

## Adding a new service later

1. Add one entry to `SERVICES` in `core/registry.py`.
2. Add a short route in `web/services.py`.

The dashboard, badges and About roadmap update themselves. No redesign needed.

## Adding a new official service later

1. Add one entry to `OFFICIAL_SERVICES` in `core/official_services.py`.

It appears on `/official-services`, in the search filter and in the tests. Two
rules apply, because these cards point at government websites:

* **Only link a page you have opened and seen the service on.** If a service has
  no dedicated page, link the official index and say so in `portal_note` - the
  card then tells the customer that instead of pretending a page exists.
* **Never invent a URL pattern.** A service with no verified link yet keeps
  `portal_url=""` and shows the "link pending verification" state.

Update `VERIFIED_ON` whenever you re-check the links.

## Adding a new letter / document type later

1. Add one entry to `DOC_TYPES` in `core/letters_catalog.py` (pick re-usable
   field groups, an opening line, and whether it is a letter, agreement or
   declaration).

It appears automatically in search, its category, the form, preview, PDF and
DOCX export. No template or route changes needed.

## Adding a new design type later

1. Add one entry to `CATEGORIES` in `core/design_catalog.py` (pick the field
   keys, a theme and a poster aspect).

It appears automatically on the Graphic Design chooser, with its own form,
layout, print, PNG and JPG export. No template or route changes needed.

## Adding a new layout style later

1. Add one entry to `STYLES` in `core/design_catalog.py` (a slug and a label).
2. Add its composition function to `COMPOSITIONS` in `core/design_render.py`.

A style is structural, not a colour swap: it decides where photos, type and
decoration sit. The operator picks one on the form and the result screen, or
leaves it on **Auto** to use the category's default in `DEFAULT_STYLE`.

## Connecting an AI provider

The AI features are written, but **no provider is connected out of the box** -
there is no built-in key, and the app never pretends there is one. Graphic
Design works fully without it, using the offline layout engine
(`core/design_render.py`).

Two providers are built in. `DERB_AI_PROVIDER` picks one; the default is
`openai-images`, so an existing setup keeps working unchanged.

### Keep the key off the command line (recommended)

Typing a key after `export` puts it in your shell history. Instead, let DERB
ask for it privately and save it to a local file that git ignores:

```bash
cd ~/DERB-Mobile
bash scripts/set_ai_key.sh        # hidden prompt; defaults to the gemini provider
bash start.sh
```

`set_ai_key.sh` reads the key with a hidden prompt (nothing echoed, nothing in
history, never passed as a command argument), writes `.env.local` with
permissions `600`, and refuses to run if that file is not gitignored.
`.env.example` is the committed template. At startup `app.py` loads
`.env` / `.env.local` and prints **only the names** of the keys it picked up -
never a value. Rules:

* a real environment variable always wins over the file, so `export` still
  overrides it for a one-off run;
* only keys beginning with `DERB_` are read - a stray file can never rewrite
  `PATH` or anything else;
* the file is never read into a page, a log or the database (section 9's rule
  is unchanged), and `git` ignores it.

If you would rather not use a file, the plain `export` form below still works.

**Option 1 - Google Gemini** (one key, handles plain text-to-image *and* the
customer's own photos in the same call). Get a key from Google AI Studio, then:

> **Image generation is not on the Gemini free tier.** With an unbilled key,
> `Check AI connection` succeeds (the key is valid) but every image model
> answers HTTP 429 with `free_tier_requests, limit: 0`. DERB reports that as
> **quota**, not as a rate limit - "wait and retry" would be a lie. Enable
> billing on the key's Google Cloud project to finish designs.

```bash
export DERB_AI_PROVIDER=gemini                 # required for Gemini
export DERB_AI_API_KEY=your-gemini-api-key     # required, secret
export DERB_AI_IMAGE_MODEL=gemini-2.5-flash-image   # optional (default)
export DERB_AI_TIMEOUT=90                      # seconds, optional
python app.py
```

**Option 2 - any OpenAI Images API gateway** (the default):

```bash
export DERB_AI_PROVIDER=openai-images          # default, may be omitted
export DERB_AI_API_KEY=your-provider-api-key   # required, secret
export DERB_AI_BASE_URL=https://api.openai.com/v1
export DERB_AI_IMAGE_MODEL=gpt-image-1
export DERB_AI_QUALITY=high                    # low | medium | high | auto
export DERB_AI_SIZE_OVERRIDE=                  # e.g. 1536x1024, optional
export DERB_AI_TIMEOUT=90                      # seconds
python app.py
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `DERB_AI_PROVIDER` | no | `gemini` or `openai-images` (default). Unknown values fall back to the default. |
| `DERB_AI_API_KEY` | yes | The provider key. Absent = "Not configured". |
| `DERB_AI_BASE_URL` | no | Any compatible gateway. Provider default otherwise. |
| `DERB_AI_IMAGE_MODEL` | no | Image model. Default `gpt-image-1` (OpenAI) / `gemini-2.5-flash-image` (Gemini). |
| `DERB_AI_QUALITY` | no | `low`, `medium`, `high` or `auto` (OpenAI only). |
| `DERB_AI_SIZE_OVERRIDE` | no | Force an output size instead of the one derived from the design's aspect. |
| `DERB_AI_TIMEOUT` | no | Request timeout in seconds (default 90). |

With `DERB_AI_PROVIDER=gemini`, the app calls the Gemini API **natively** - one
`models/{model}:generateContent` request covers text-to-image and the
customer's photos (`inline_data` parts), authenticating with the
`x-goog-api-key` header. Google's OpenAI-compatibility layer is deliberately
*not* used for Gemini because it has no `/images/edits` equivalent, so a plain
base-URL swap would silently drop the customer's photos. With
`openai-images`, the provider must speak the documented OpenAI Images API
(`POST /images/generations` for text-to-image, `POST /images/edits` when the
customer's own photos are sent along). Either way the provider returns
PNG/JPEG/WebP data and only `urllib` from the standard library is used -
**no SDK is installed**, so the phone still needs no build step.

**The API key never leaves the backend.** It is read from the environment in
`core/ai_service.py`, is never written to the database, never rendered into a
page and never logged. The test suite sets a marker key and asserts it appears
in no rendered screen and no stored setting.

### How AI finishing works (and why the text is safe)

The AI is asked for **background artwork only** - the prompt explicitly forbids
letters, words, numbers, watermarks and logos. The customer's design is sent as
context (category, aspect, the actual headline/name/date/venue/contact lines,
the colour direction, the layout style and the uploaded photos), and the
returned image is used as a **backdrop layer**: DERB's own engine re-draws
every text and photo element on top of it, exactly as it would without AI. So:

* an image model can never silently change a name, date, venue or phone number;
* the result is reviewable - **Accept**, **Try another** or **Reject**, and the
  original design is kept (and shown side by side) until you accept;
* after accepting, the design is saved to Saved Work as usual and can still be
  adjusted, printed and exported to PNG/JPG - **Remove AI background** puts the
  plain composition back at any time.

### If something goes wrong

There is no path that fakes a result. A missing key, a switched-off feature, a
bad request, an unreachable host, a timeout, a rate limit, a rejected key and a
non-image provider response are each reported in plain words on the design
screen and in Settings, and **the operator's design is left exactly as it was**.
Settings also has a **Check AI connection** button that probes the provider
without generating (and paying for) an image.

## Design notes

See [`docs/DECISIONS.md`](docs/DECISIONS.md) - notably why PDF/DOCX use the
standard library instead of `fpdf2`/`python-docx` (those pull in Pillow/lxml,
which fail to build on this Termux toolchain).
