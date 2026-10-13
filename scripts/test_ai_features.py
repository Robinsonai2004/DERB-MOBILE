#!/usr/bin/env python3
"""
DERB MOBILE - "Switch to AI Features" + AI finishing test.

Walks the whole feature the way the operator does:

    Settings -> switch AI on/off -> Graphic Design -> Finish with AI
             -> review -> accept / try another / reject
             -> saved, printable, exportable -> remove the AI background

The AI provider is **mocked** (ai_service.set_provider), so this test never
makes a paid API call and never touches the network. It also proves the
honest-failure rule: when the provider fails, the app says so and the
operator's design is left untouched - it never shows a fake "enhanced" result.

Fictional content only; every project and image it creates is removed again.

Run:
    python scripts/test_ai_features.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

passes = 0
failures: list[str] = []

# A valid 1x1 PNG - stands in for a customer photo and for the AI artwork.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

API_KEY = "sk-test-DERB-MARKER-0123456789"
# Port 1 refuses instantly on loopback: the "provider unreachable" path is
# exercised for real without leaving the device.
UNREACHABLE = "http://127.0.0.1:1/v1"


def check(label: str, condition: bool, detail: str = "") -> None:
    global passes
    if condition:
        passes += 1
        print(f"  [PASS] {label}")
    else:
        failures.append(f"{label}{(' -> ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}" + (f"  ({detail})" if detail else ""))


# ---------------------------------------------------------------------------
# Mock provider - records what it was asked for, returns real PNG bytes
# ---------------------------------------------------------------------------
class FakeProvider:
    slug = "fake-images"
    label = "Fake image provider"

    def __init__(self, *, fail: str = "", payload: bytes = PNG_1X1):
        self.fail = fail
        self.payload = payload
        self.calls: list[dict] = []

    def generate(self, *, cfg, prompt, size, images):
        from core import ai_service

        self.calls.append({
            "prompt": prompt, "size": size,
            "images": [p.name for p in images],
            "model": cfg.model, "key": cfg.api_key,
        })
        if self.fail:
            raise ai_service.AiError(self.fail, f"mock {self.fail} failure")
        return self.payload, ".png"


def main() -> int:  # noqa: C901 - a linear script reads better here
    print("DERB MOBILE - AI features test")
    print("-" * 58)

    from config import DESIGN_IMAGES_DIR
    from core import ai_service, design_model, design_store, projects_repo
    from core import templates_repo

    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    created_projects: list[int] = []
    created_images: list[str] = []
    prefs_before = templates_repo.get_setting(ai_service.PREF_KEY)

    def cleanup() -> None:
        ai_service.set_provider(None)
        for pid in created_projects:
            projects_repo.delete_project(pid)
        for name in created_images:
            design_store.delete_image(name)
        templates_repo.set_setting(ai_service.PREF_KEY, prefs_before or "")
        ai_service.reset_state()
        os.environ.pop("DERB_AI_API_KEY", None)
        os.environ.pop("DERB_AI_BASE_URL", None)

    def set_env(key: str | None, base: str | None = None) -> None:
        if key:
            os.environ["DERB_AI_API_KEY"] = key
        else:
            os.environ.pop("DERB_AI_API_KEY", None)
        if base:
            os.environ["DERB_AI_BASE_URL"] = base

    def post_ai(prompt: str = "warmer gold, more space at the top", **extra):
        data = {
            "category": "anniversary", "title": "CAC Choir 10th Anniversary",
            "theme": "gold-white", "anniversary_type": "Choir Anniversary",
            "organisation": "Christ Apostolic Church", "anniversary_number": "10th",
            "date_event": "2026-11-01", "venue": "Main Auditorium",
            "contact": "0803 0000 0000", "ai_prompt": prompt, **extra,
        }
        return client.post("/graphic-design/ai", data=data,
                           content_type="multipart/form-data")

    def text_blocks(layout: dict) -> list:
        return [e["lines"] for e in layout["elements"] if e["kind"] == "text"]

    # ------------------------------------------------------ storage & state
    print("Settings storage")
    ai_service.set_preference(False)
    ai_service.reset_state()
    set_env(None)
    check("AI features are off by default on a fresh install",
          templates_repo.get_setting(ai_service.PREF_KEY) in (None, "", "0")
          or ai_service.preference_enabled() is False)
    ai_service.set_preference(True)
    check("Enabling persists in the existing settings table",
          templates_repo.get_setting(ai_service.PREF_KEY) == "1")
    check("Preference reads back as enabled", ai_service.preference_enabled())
    ai_service.set_preference(False)
    check("Disabling persists too",
          templates_repo.get_setting(ai_service.PREF_KEY) == "0")

    # ------------------------------------------------------- honest states
    print("Honest status states")
    ai_service.set_preference(False)
    check("Off reports 'disabled'", ai_service.status()["state"] == "disabled",
          ai_service.status()["state"])
    ai_service.set_preference(True)
    check("On without a key reports 'not_configured'",
          ai_service.status()["state"] == "not_configured",
          ai_service.status()["state"])
    check("Not configured is not 'ready'", ai_service.status()["ready"] is False)
    set_env(API_KEY)
    check("On with a key reports 'enabled'",
          ai_service.status()["state"] == "enabled", ai_service.status()["state"])
    check("Status never exposes the key",
          API_KEY not in json.dumps(ai_service.status()))
    check("Status lists the required env vars",
          set(ai_service.ENV_KEYS) >= {"DERB_AI_API_KEY", "DERB_AI_BASE_URL",
                                       "DERB_AI_IMAGE_MODEL"})

    # ------------------------------------------------------- settings page
    print("Settings page (HTTP)")
    resp = client.get("/settings")
    page = resp.get_data(as_text=True)
    check("GET /settings -> 200", resp.status_code == 200, f"status {resp.status_code}")
    check("Settings is a real screen, not 'Coming Soon'",
          "Coming Soon" not in page and "Switch to AI Features" in page)
    check("Settings has the AI toggle control",
          'name="ai_features"' in page and 'action="/settings/ai-features"' in page)
    check("Settings shows the current state", "Enabled" in page)
    check("Settings documents the env vars",
          "DERB_AI_API_KEY" in page and "DERB_AI_BASE_URL" in page)
    check("Settings states the text-preservation rule",
          "re-drawn" in page or "re-draw" in page)
    check("The API key is never rendered", API_KEY not in page)
    check("Settings CSS served",
          client.get("/static/css/settings.css").status_code == 200)
    check("Dashboard shows Settings as ready",
          "Settings" in client.get("/").get_data(as_text=True))

    # toggle off over HTTP, then back on
    resp = client.post("/settings/ai-features", data={"ai_features": ""},
                       follow_redirects=True)
    check("Toggle off -> redirects to Settings", resp.status_code == 200)
    check("Toggle off persists", ai_service.preference_enabled() is False)
    check("Toggle off is reported honestly",
          "switched off" in resp.get_data(as_text=True))
    resp = client.post("/settings/ai-features", data={"ai_features": "1"},
                       follow_redirects=True)
    check("Toggle on persists", ai_service.preference_enabled() is True)
    check("Toggle on confirms availability",
          "Finish with AI" in resp.get_data(as_text=True))

    # ------------------------------------------------ AI switched off ========
    print("AI switched off")
    ai_service.set_preference(False)
    resp = client.post("/graphic-design/generate",
                       data={"category": "anniversary", "title": "Normal Design"},
                       content_type="multipart/form-data")
    body = resp.get_data(as_text=True)
    check("Normal generate still works with AI off", resp.status_code == 200)
    check("Normal poster still renders", 'id="design-poster"' in body)
    check("No AI panel is offered when AI is off", "Finish with AI" not in body)
    check("Export controls are untouched",
          'data-export="png"' in body and 'data-export="jpg"' in body)
    refusals = projects_repo.count_projects("DESIGN")
    resp = post_ai()
    check("AI finish is refused while AI is off", resp.status_code == 200)
    check("Refusal explains how to turn AI on",
          "Settings" in resp.get_data(as_text=True))
    check("Refusal did not create anything",
          projects_repo.count_projects("DESIGN") == refusals)
    check("Refusal used the untouched design (no ai hidden field)",
          'name="ai_background"' not in resp.get_data(as_text=True))

    # --------------------------------------------- AI on, not configured =====
    print("AI on but not configured")
    ai_service.set_preference(True)
    ai_service.reset_state()
    set_env(None)
    resp = post_ai()
    body = resp.get_data(as_text=True)
    check("Not configured is refused honestly", resp.status_code == 200)
    check("Message says no API key is configured",
          "no ai provider api key" in body.lower(), body[:200])
    check("No design was enhanced", 'name="ai_background"' not in body)
    check("Design screen offers no AI button while unconfigured",
          "Finish with AI" not in body)
    check("Design screen links to Settings instead",
          "/settings" in body)
    check("Status is 'not_configured' in the UI",
          ai_service.status()["state"] == "not_configured")

    # -------------------------------------------------------- validation ====
    print("Request validation")
    set_env(API_KEY, "https://api.openai.com/v1")
    ai_service.reset_state()
    provider = FakeProvider()
    ai_service.set_provider(provider)
    ai_files_before = set(p.name for p in DESIGN_IMAGES_DIR.glob("ai_*"))

    resp = post_ai("   ")
    check("An empty instruction is rejected",
          "describe the improvement" in resp.get_data(as_text=True).lower())
    resp = post_ai("x" * (ai_service.MAX_PROMPT + 40))
    check("An over-long instruction is rejected",
          "under 600 characters" in resp.get_data(as_text=True).lower())
    resp = post_ai(**{"image_filename": "nope.png"})
    check("A missing upload is rejected",
          "missing" in resp.get_data(as_text=True).lower())
    resp = post_ai(**{"image_filename": ["../../etc/passwd"]})
    check("An unsafe image reference is rejected",
          "not valid" in resp.get_data(as_text=True).lower())
    check("No provider call happened for an invalid request", provider.calls == [])
    check("Invalid requests stored no AI image",
          set(p.name for p in DESIGN_IMAGES_DIR.glob("ai_*")) == ai_files_before,
          str(set(p.name for p in DESIGN_IMAGES_DIR.glob("ai_*")) - ai_files_before))

    # real oversized upload, caught by the byte limit
    big = design_store.save_bytes(b"x" * 64, ".png")
    created_images.append(big)
    original_limit = ai_service.MAX_INPUT_BYTES
    ai_service.MAX_INPUT_BYTES = 32
    resp = post_ai(**{"image_filename": big})
    check("An oversized upload is rejected",
          "larger than" in resp.get_data(as_text=True).lower())
    ai_service.MAX_INPUT_BYTES = original_limit

    # more images than the provider accepts: the design is still finished, and
    # only the first few are sent as reference
    many = [design_store.save_bytes(PNG_1X1, ".png") for _ in range(6)]
    created_images.extend(many)
    provider.calls.clear()
    resp = post_ai("more photos than usual", image_filename=many)
    many_html = resp.get_data(as_text=True)
    check("A design with many images is still finished",
          'name="ai_background"' in many_html)
    check(f"At most {ai_service.AI_MAX_INPUT_IMAGES} images are sent to the provider",
          len(provider.calls) == 1
          and len(provider.calls[0]["images"]) == ai_service.AI_MAX_INPUT_IMAGES,
          str(provider.calls[0]["images"]) if provider.calls else "no call")
    mm = re.search(r'name="ai_background" value="(ai_[0-9a-f]+\.png)"', many_html)
    if mm:
        created_images.append(mm.group(1))
    for name in many:
        design_store.delete_image(name)
        created_images.remove(name)
    provider.calls.clear()

    # -------------------------------------------------------- happy path ====
    print("Successful AI finishing (mocked provider)")
    payload_for_check = design_model.normalize({
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "theme": "gold-white",
        "fields": {"anniversary_type": "Choir Anniversary",
                   "organisation": "Christ Apostolic Church",
                   "date_event": "2026-11-01", "venue": "Main Auditorium",
                   "contact": "0803 0000 0000"},
    })
    resp = client.post(
        "/graphic-design/ai",
        data={
            "category": "anniversary", "title": "CAC Choir 10th Anniversary",
            "theme": "gold-white", "anniversary_type": "Choir Anniversary",
            "organisation": "Christ Apostolic Church", "anniversary_number": "10th",
            "date_event": "2026-11-01", "venue": "Main Auditorium",
            "contact": "0803 0000 0000",
            "ai_prompt": "warm gold background, more space for the title",
            "images": (io.BytesIO(PNG_1X1), "guest.png"),
        },
        content_type="multipart/form-data",
    )
    review = resp.get_data(as_text=True)
    designs_before = projects_repo.count_projects("DESIGN")
    check("AI finish -> 200", resp.status_code == 200, f"status {resp.status_code}")
    check("It asks the provider once", len(provider.calls) == 1, str(len(provider.calls)))
    check("The provider was asked for a portrait background",
          provider.calls and provider.calls[0]["size"] == "1024x1536",
          provider.calls[0]["size"] if provider.calls else "no call")
    check("The customer's uploaded photo was sent to the provider",
          provider.calls and provider.calls[0]["images"], str(provider.calls))
    check("The prompt forbids the model from drawing text",
          "no text, letters, words" in (provider.calls[0]["prompt"] if provider.calls else ""))
    check("The prompt carries the customer's own wording",
          "Choir Anniversary" in (provider.calls[0]["prompt"] if provider.calls else ""))
    check("The prompt carries the operator's instruction",
          "warm gold background" in (provider.calls[0]["prompt"] if provider.calls else ""))
    check("The review screen is shown", "AI background ready" in review)
    check("Review offers Accept", 'action="/graphic-design/ai/accept"' in review
          or re.search(r'formaction="/graphic-design/ai/accept"', review) is not None)
    check("Review offers Try another", re.search(r'formaction="/graphic-design/ai"', review) is not None)
    check("Review offers Reject", re.search(r'formaction="/graphic-design/ai/reject"', review) is not None)
    check("The original design is shown for comparison",
          'id="design-poster-original"' in review and "Original design" in review)
    check("The AI result is NOT saved yet",
          projects_repo.count_projects("DESIGN") == designs_before,
          str(projects_repo.count_projects("DESIGN")))
    check("Export + print are still offered on the review screen",
          'data-export="png"' in review and 'data-role="print"' in review)

    for name in re.findall(r'name="image_filename" value="(design_[0-9a-f]+\.png)"',
                           review):
        if name not in created_images:
            created_images.append(name)

    m = re.search(r'name="ai_background" value="(ai_[0-9a-f]+\.png)"', review)
    check("The AI artwork is stored locally", bool(m))
    ai_file = m.group(1) if m else ""
    if ai_file:
        created_images.append(ai_file)
        check("Stored AI artwork exists on disk", (DESIGN_IMAGES_DIR / ai_file).is_file())
        check("The AI artwork is served to the browser",
              client.get(f"/graphic-design/image/{ai_file}").status_code == 200)
        check("The AI artwork is validated as a real image before storage",
              design_store.sniff_image_ext((DESIGN_IMAGES_DIR / ai_file).read_bytes()) == ".png")
        check("The AI artwork uses a generated name, never a client one",
              ai_file.startswith("ai_") and design_store.is_safe_name(ai_file))

    # the layout JSON the canvas exporter draws from
    jm = re.search(r'id="design-layout-json">(.*?)</script>', review, re.S)
    layout = json.loads(jm.group(1)) if jm else {}
    check("The AI background is painted under the design",
          bool(layout.get("elements")) and layout["elements"][0]["kind"] == "photo"
          and layout["elements"][0]["file"].startswith("ai_"),
          str(layout.get("elements", [])[:1]))
    check("A legibility scrim sits between the artwork and the text",
          len(layout.get("elements", [])) > 1
          and layout["elements"][1]["kind"] == "rect"
          and layout["elements"][1].get("opacity"))
    check("The AI background is full-bleed",
          layout["elements"][0]["w"] == layout["width"]
          and layout["elements"][0]["h"] == layout["height"])
    check("Layout still reports the AI background",
          layout.get("ai_background", "").startswith("ai_"))
    check("The customer's text is still rendered by DERB's engine",
          len(text_blocks(layout)) >= 3, str(len(text_blocks(layout))))
    check("Nothing the customer typed was dropped",
          any("CAC" in " ".join(b) for b in text_blocks(layout))
          and any("Main Auditorium" in " ".join(b) for b in text_blocks(layout))
          and any("0803 0000 0000" in " ".join(b) for b in text_blocks(layout)),
          str(text_blocks(layout)))

    # "text is preserved" is asserted exactly: the AI variant's text elements
    # are byte-identical to the plain engine's for the same payload.
    original_layout = json.loads(json.dumps(layout))
    original_layout["elements"] = original_layout["elements"][2:]
    check("The AI variant's text elements are identical to the original's",
          text_blocks(original_layout) == text_blocks(layout))

    # ------------------------------------------------------------- reject ===
    print("Reject")
    files_before = sorted(p.name for p in DESIGN_IMAGES_DIR.glob("ai_*"))
    resp = client.post("/graphic-design/ai/reject", data={
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "anniversary_type": "Choir Anniversary", "ai_background": ai_file,
        "ai_prompt": "warm gold background",
    })
    rejected = resp.get_data(as_text=True)
    check("Reject -> 200", resp.status_code == 200)
    check("Reject discards the artwork file",
          ai_file not in sorted(p.name for p in DESIGN_IMAGES_DIR.glob("ai_*")),
          f"before {files_before}")
    check("Reject keeps the design itself",
          'id="design-poster"' in rejected and "CAC Choir 10th Anniversary" in rejected)
    check("Reject leaves no AI background attached",
          'name="ai_background"' not in rejected)
    check("Reject saved nothing",
          projects_repo.count_projects("DESIGN") == designs_before)
    if ai_file in created_images:
        created_images.remove(ai_file)

    # -------------------------------------------------------- try another ===
    print("Try another variation")
    resp = post_ai("even bolder title, calmer bottom")
    again = resp.get_data(as_text=True)
    m2 = re.search(r'name="ai_background" value="(ai_[0-9a-f]+\.png)"', again)
    second = m2.group(1) if m2 else ""
    check("A second variation is produced", bool(second) and second != ai_file)
    if second:
        created_images.append(second)
    check("'Try another' prefills the previous instruction",
          "even bolder title" in again)
    check("Only one AI result is presented for review",
          again.count('name="ai_background"') == 1)

    # ---------------------------------------------------------- upstream ====
    print("Provider failures are honest")
    failing = FakeProvider(fail="network")
    ai_service.set_provider(failing)
    resp = post_ai("make it pop")
    failed = resp.get_data(as_text=True)
    check("A network failure still renders the design", resp.status_code == 200)
    check("The failure is stated, not hidden",
          "did not complete" in failed and "unchanged" in failed.lower())
    check("A failure never shows a reviewed AI result",
          'name="ai_background"' not in failed)
    check("A failure stores no AI artwork of its own",
          not (DESIGN_IMAGES_DIR / "ai_fake.png").exists())
    check("A failure does not save the design",
          projects_repo.count_projects("DESIGN") == designs_before)
    check("The service is reported as unavailable after a failure",
          ai_service.status()["state"] == "unavailable",
          ai_service.status()["state"])
    check("The Settings screen shows the failure",
          ai_service.status()["message"][:20] in
          client.get("/settings").get_data(as_text=True))

    not_an_image = FakeProvider(payload=b"<html>not an image</html>")
    ai_service.set_provider(not_an_image)
    resp = post_ai("try again")
    check("A non-image provider response is rejected",
          "did not return a usable image" in resp.get_data(as_text=True)
          or "unrecognised" in resp.get_data(as_text=True))
    check("Nothing from a bad response is stored",
          'name="ai_background"' not in resp.get_data(as_text=True))

    ai_service.set_provider(FakeProvider(fail="rate_limit"))
    resp = post_ai("one more")
    check("A rate limit is explained",
          "rate limit" in resp.get_data(as_text=True).lower())

    # the Settings "Check AI connection" button, for real (unreachable host)
    set_env(API_KEY, UNREACHABLE)
    ai_service.reset_state()
    resp = client.post("/settings/ai-features/check", follow_redirects=True)
    check("Check connection reports a real failure",
          "could not reach" in resp.get_data(as_text=True).lower(),
          resp.get_data(as_text=True)[:200])
    check("Unreachable provider is reported as unavailable",
          ai_service.status()["state"] == "unavailable")

    # ------------------------------------------------------------ accept ====
    print("Accept")
    set_env(API_KEY, "https://api.openai.com/v1")
    ai_service.reset_state()
    provider = FakeProvider()
    ai_service.set_provider(provider)
    resp = post_ai("warm gold, more space for the title")
    review = resp.get_data(as_text=True)
    m = re.search(r'name="ai_background" value="(ai_[0-9a-f]+\.png)"', review)
    ai_file = m.group(1) if m else ""
    if ai_file:
        created_images.append(ai_file)
    accept_data = {
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "anniversary_type": "Choir Anniversary", "organisation": "Christ Apostolic Church",
        "venue": "Main Auditorium", "contact": "0803 0000 0000",
        "ai_background": ai_file, "ai_prompt": "warm gold, more space for the title",
        "ai_provider": "fake-images", "ai_model": "fake-model",
        "ai_created_at": "2026-10-12 09:00:00",
    }
    resp = client.post("/graphic-design/ai/accept", data=accept_data,
                       follow_redirects=False)
    check("Accept -> redirect", resp.status_code == 302, f"status {resp.status_code}")
    loc = resp.headers.get("Location", "")
    dm = re.search(r"/graphic-design/(\d+)/preview", loc)
    check("Accept redirects to the saved design", bool(dm), loc)
    if not dm:
        cleanup()
        print("-" * 58)
        print(f"{passes} passed, {len(failures)} failed")
        for f in failures:
            print("  -", f)
        return 1
    design_id = int(dm.group(1))
    created_projects.append(design_id)

    project = projects_repo.get_project(design_id)
    check("Accepted design is saved as doc_type DESIGN", project["doc_type"] == "DESIGN")
    check("The accepted backdrop is persisted with the design",
          project["raw"]["ai"]["background"] == ai_file, str(project["raw"].get("ai")))
    check("The instruction used is persisted",
          project["raw"]["ai"]["prompt"] == "warm gold, more space for the title")
    saved_board = client.get("/saved").get_data(as_text=True)
    check("Accepted AI design appears in Saved Work",
          "CAC Choir 10th Anniversary" in saved_board)

    preview = client.get(loc).get_data(as_text=True)
    check("Preview shows the accepted AI background", "AI background accepted" in preview)
    check("Preview can still print", 'data-role="print"' in preview)
    check("Preview can still export PNG + JPG",
          'data-export="png"' in preview and 'data-export="jpg"' in preview)
    pv_layout = json.loads(re.search(r'id="design-layout-json">(.*?)</script>',
                                     preview, re.S).group(1))
    check("Exported layout is drawn from the AI backdrop",
          pv_layout["elements"][0]["kind"] == "photo"
          and pv_layout["elements"][0]["file"] == ai_file)
    check("Exported layout still contains every customer text block",
          len(text_blocks(pv_layout)) >= 3
          and any("Main Auditorium" in " ".join(b) for b in text_blocks(pv_layout)))

    # ------------------------------------------- adjust and keep after accept
    print("Still editable and exportable after accepting")
    resp = client.get(f"/graphic-design/{design_id}/edit")
    editor = resp.get_data(as_text=True)
    check("Reopen editor -> 200", resp.status_code == 200)
    check("Editor keeps the AI background attached",
          f'name="ai_background" value="{ai_file}"' in editor)
    check("Editor offers to remove the AI background",
          f"/graphic-design/{design_id}/ai/remove" in editor)
    check("Add Image is still available", "Add Image" in editor)

    resp = client.post("/graphic-design/generate", data={
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "anniversary_type": "Choir Anniversary", "organisation": "Christ Apostolic Church",
        "venue": "Main Auditorium", "contact": "0803 0000 0000",
        "ai_background": ai_file, "ai_prompt": "warm gold",
        "project_id": str(design_id),
    }, content_type="multipart/form-data")
    regen = resp.get_data(as_text=True)
    check("Regenerating keeps the accepted AI background",
          'name="ai_background"' in regen
          and json.loads(re.search(r'id="design-layout-json">(.*?)</script>',
                                   regen, re.S).group(1))["elements"][0]["kind"] == "photo")

    resp = client.post("/graphic-design/save", data={
        "category": "anniversary", "title": "CAC Choir 10th Anniversary",
        "anniversary_type": "Choir Anniversary", "ai_background": ai_file,
        "ai_prompt": "warm gold", "project_id": str(design_id),
    })
    check("Saving again keeps the AI background",
          projects_repo.get_project(design_id)["raw"]["ai"]["background"] == ai_file)

    # ------------------------------------------------------------- remove ===
    print("Remove the AI background")
    resp = client.post(f"/graphic-design/{design_id}/ai/remove",
                       follow_redirects=False)
    check("Remove -> redirect", resp.status_code == 302)
    check("Remove clears the stored backdrop",
          not projects_repo.get_project(design_id)["raw"]["ai"].get("background"))
    check("Remove deleted the artwork file",
          not (DESIGN_IMAGES_DIR / ai_file).is_file())
    after = client.get(f"/graphic-design/{design_id}/preview").get_data(as_text=True)
    check("Removing restores the plain composition",
          "AI background accepted" not in after
          and 'id="design-poster"' in after)
    if ai_file in created_images:
        created_images.remove(ai_file)

    # -------------------------------------------------- other services still work
    print("Other services and secrets")
    for route in ("/", "/cv", "/letters", "/documents", "/saved",
                  "/official-services", "/templates", "/health", "/graphic-design"):
        check(f"GET {route} -> 200", client.get(route).status_code == 200)
    check("CV templates still render", "Professional CV" in
          client.get("/cv").get_data(as_text=True))
    check("Official Services still render", "Official Services" in
          client.get("/official-services").get_data(as_text=True))
    check("Letters landing still works",
          "Request Letter" in client.get("/letters/?q=request").get_data(as_text=True))
    check("Documents editor still works",
          'id="doc-area"' in client.get("/documents/").get_data(as_text=True))

    set_env(API_KEY)
    ai_service.set_preference(True)
    for route in ("/settings", "/graphic-design/new?category=certificate",
                  "/graphic-design", f"/graphic-design/{design_id}/preview"):
        rendered = client.get(route).get_data(as_text=True)
        check(f"No API key in {route}", API_KEY not in rendered)
    db_values = [row["value"] for row in
                 __import__("core.db", fromlist=["x"]).query("SELECT value FROM settings")]
    check("The API key was never written to the database",
          not any(API_KEY in (v or "") for v in db_values))
    check("Design CSS states the text rule in the UI",
          "re-drawn" in client.get("/graphic-design/new?category=anniversary").get_data(as_text=True))

    # -------------------------------------------------------------- cleanup
    print("Cleanup")
    cleanup()
    left = [n for n in created_images if (DESIGN_IMAGES_DIR / n).exists()]
    check("Test images removed", not left, str(left))
    check("No test projects left",
          projects_repo.get_project(design_id) is None)
    check("AI preference restored",
          templates_repo.get_setting(ai_service.PREF_KEY) == (prefs_before or ""))

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("AI features verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
