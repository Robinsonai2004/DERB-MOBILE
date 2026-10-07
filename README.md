# DERB MOBILE

**DERB FINANCE CONCEPTS** &middot; Offline Document Studio for Android (Termux)

Builds customer documents - CVs first - entirely offline on your phone and saves
them to a local folder you can transfer to a PC for printing.

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
| 7 | Template Manager + remaining services (Documents, School, Business, Passport) | Next |

> Version 1 targets the CV / Resume workflow. Letters, Documents, School,
> Business and Passport Photos are visible on the dashboard and clearly marked
> **Coming Soon** - they are placeholders, not broken links.

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
python scripts/smoke_test.py             # 41 checks - foundation & dashboard
python scripts/test_cv_workflow.py       # 64 checks - template picker/editor/save
python scripts/test_exports.py           # 29 checks - CV PDF & DOCX export
python scripts/test_letters.py           # 154 checks - letters & documents module
python scripts/test_official_services.py # 91 checks - official services page
```

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
│   ├── templates_repo.py   # template queries + default-template setting
│   └── projects_repo.py    # saved-project queries
├── web/
│   ├── __init__.py         # Flask app factory, error pages
│   ├── dashboard.py        # home screen, /about, /health
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
│   ├── Letters/ Documents/ School/ Business/ Passport/ Templates/
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

## Design notes

See [`docs/DECISIONS.md`](docs/DECISIONS.md) - notably why PDF/DOCX use the
standard library instead of `fpdf2`/`python-docx` (those pull in Pillow/lxml,
which fail to build on this Termux toolchain).
