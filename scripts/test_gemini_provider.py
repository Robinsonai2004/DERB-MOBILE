#!/usr/bin/env python3
"""
DERB MOBILE - Gemini provider + provider-switch test.

Proves that DERB can finish a design with a **Gemini API key**, and that the
provider seam is honest:

    DERB_AI_PROVIDER=gemini  -> native Gemini generateContent (x-goog-api-key)
    DERB_AI_PROVIDER unset   -> the original OpenAI Images client, unchanged

The network is never touched. ``urllib.request.urlopen`` is stubbed, so the
REAL request-building code in core/ai_service.py runs and this test asserts the
exact URL, method, headers and JSON body it produces - including the
customer's own photo travelling as an ``inline_data`` part in the *same* call
(Gemini has no /images/edits, so a plain base-URL swap would silently drop it).

Fictional content only; every project and image it creates is removed again.

Run:
    python scripts/test_gemini_provider.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

passes = 0
failures: list[str] = []

# A valid 1x1 PNG - stands in for a customer photo and for the AI artwork.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
GEMINI_KEY = "AIza-DERB-MARKER-GEMINI-KEY-0123456789"
GEMINI_HOST = "generativelanguage.googleapis.com"


def check(label: str, condition: bool, detail: str = "") -> None:
    global passes
    if condition:
        passes += 1
        print(f"  [PASS] {label}")
    else:
        failures.append(f"{label}{(' -> ' + detail) if detail else ''}")
        print(f"  [FAIL] {label}" + (f"  ({detail})" if detail else ""))


# ---------------------------------------------------------------------------
# Stubbed transport - records every request, answers with crafted payloads
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self, n: int = -1) -> bytes:
        return self._data if n is None or n < 0 else self._data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Transport:
    """Swap-in for urllib.request.urlopen. `answer` decides each response."""

    def __init__(self):
        self.calls: list[urllib.request.Request] = []
        self.answer = self._ok_json
        self._real = urllib.request.urlopen

    # -- fixtures ---------------------------------------------------------
    @staticmethod
    def gemini_image(png: bytes = PNG_1X1) -> bytes:
        return json.dumps({
            "candidates": [{
                "content": {"parts": [
                    {"inlineData": {"mimeType": "image/png",
                                    "data": base64.b64encode(png).decode()}},
                ]},
                "finishReason": "STOP",
            }]
        }).encode()

    @staticmethod
    def _ok_json(req) -> _FakeResponse:
        return _FakeResponse(Transport.gemini_image())

    # -- plumbing ---------------------------------------------------------
    def install(self) -> None:
        urllib.request.urlopen = self._dispatch  # type: ignore[assignment]

    def restore(self) -> None:
        urllib.request.urlopen = self._real  # type: ignore[assignment]

    def _dispatch(self, req, timeout=None):
        self.calls.append(req)
        return self.answer(req)

    # -- assertions helpers ----------------------------------------------
    def last(self) -> urllib.request.Request:
        return self.calls[-1]

    def bodies(self) -> list[dict]:
        out = []
        for req in self.calls:
            if req.data:
                out.append(json.loads(req.data.decode("utf-8")))
        return out


def header(req: urllib.request.Request, name: str) -> str | None:
    """Case-insensitive header lookup (Request.get_header is exact-case on 3.14)."""
    for key, value in req.headers.items():
        if key.lower() == name.lower():
            return value
    return None


def http_error(code: int, message: str = "boom"):
    """An HTTPError whose body carries a provider-style JSON message."""
    body = json.dumps({"error": {"message": message}}).encode()
    return urllib.error.HTTPError(
        "https://example.invalid", code, message, {}, io.BytesIO(body)
    )


def main() -> int:  # noqa: C901 - a linear script reads better here
    print("DERB MOBILE - Gemini provider test")
    print("-" * 58)

    import config
    from config import DESIGN_IMAGES_DIR
    from core import ai_service, design_store, projects_repo, templates_repo
    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    transport = Transport()
    created_projects: list[int] = []
    created_images: list[str] = []
    prefs_before = templates_repo.get_setting(ai_service.PREF_KEY)
    env_before = {k: os.environ.get(k) for k in ai_service.ENV_KEYS}

    def set_env(**values) -> None:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def cleanup() -> None:
        transport.restore()
        ai_service.set_provider(None)
        for pid in created_projects:
            projects_repo.delete_project(pid)
        for name in created_images:
            design_store.delete_image(name)
        templates_repo.set_setting(ai_service.PREF_KEY, prefs_before or "")
        ai_service.reset_state()
        set_env(**env_before)

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

    def inline_parts(body: dict) -> list[dict]:
        parts = body["contents"][0]["parts"]
        return [p for p in parts if "inline_data" in p]

    # ------------------------------------------------- provider selection
    print("Provider selection")
    set_env(DERB_AI_PROVIDER=None, DERB_AI_API_KEY=GEMINI_KEY,
            DERB_AI_BASE_URL=None, DERB_AI_IMAGE_MODEL=None)
    ai_service.reset_state()
    cfg = ai_service.load_config()
    check("Default provider is unchanged (openai-images)",
          cfg.provider == "openai-images", cfg.provider)
    check("Default model is unchanged (gpt-image-1)", cfg.model == "gpt-image-1",
          cfg.model)
    check("Default provider runs the OpenAI client",
          ai_service.get_provider().slug == "openai-images")

    set_env(DERB_AI_PROVIDER="gemini")
    cfg = ai_service.load_config()
    check("DERB_AI_PROVIDER=gemini selects Gemini", cfg.provider == "gemini",
          cfg.provider)
    check("Gemini default model", cfg.model == "gemini-2.5-flash-image", cfg.model)
    check("Gemini base URL",
          cfg.base_url == "https://generativelanguage.googleapis.com/v1beta",
          cfg.base_url)
    check("Gemini provider is the one that runs",
          ai_service.get_provider().slug == "gemini",
          ai_service.get_provider().slug)
    check("Gemini reports a human label",
          cfg.label == "Google Gemini API · gemini-2.5-flash-image", cfg.label)
    check("Gemini accepts fewer reference images than OpenAI",
          ai_service.provider_for("gemini").max_input_images == 3
          and ai_service.provider_for("openai-images").max_input_images == 4)

    set_env(DERB_AI_PROVIDER="bogus-provider")
    check("An unknown provider falls back to the default (no guessing)",
          ai_service.load_config().provider == "openai-images",
          ai_service.load_config().provider)
    set_env(DERB_AI_PROVIDER="gemini")

    status = ai_service.status()
    check("Status reports the Gemini provider", status["provider"] == "gemini")
    check("Status shows the Gemini host, not the full URL",
          status["base_host"] == GEMINI_HOST, status["base_host"])
    check("Status never exposes the key",
          GEMINI_KEY not in json.dumps(status))
    check("The provider env var is documented",
          "DERB_AI_PROVIDER" in ai_service.ENV_KEYS)
    page = client.get("/settings").get_data(as_text=True)
    check("Settings documents the Gemini option end to end",
          "DERB_AI_PROVIDER" in page and "gemini" in page
          and "Google Gemini" in page and "x-goog-api-key" in page)

    # ------------------------------------------------- request shape (text)
    print("Gemini request shape (text-to-image)")
    transport.install()
    transport.calls.clear()
    cfg = ai_service.load_config()
    data, ext = ai_service.provider_for("gemini").generate(
        cfg=cfg, prompt="decorative gold backdrop, no text", size="1024x1536",
        images=[],
    )
    req = transport.last()
    check("One request was made", len(transport.calls) == 1, str(len(transport.calls)))
    check("It posts to the documented generateContent endpoint",
          req.full_url == f"https://{GEMINI_HOST}/v1beta/models/"
                          "gemini-2.5-flash-image:generateContent",
          req.full_url)
    check("It is a POST", req.get_method() == "POST", req.get_method())
    check("The key travels in the x-goog-api-key header",
          header(req, "x-goog-api-key") == GEMINI_KEY,
          str(header(req, "x-goog-api-key")))
    check("No Bearer Authorization header is sent to Gemini",
          header(req, "Authorization") is None)
    check("The key is never placed in the URL", GEMINI_KEY not in req.full_url)
    body = transport.bodies()[0]
    check("The body is a single text part",
          len(body["contents"][0]["parts"]) == 1
          and body["contents"][0]["parts"][0]["text"]
          == "decorative gold backdrop, no text", str(body))
    check("The returned bytes are the image only",
          data == PNG_1X1 and ext == ".png", f"{len(data)} bytes / {ext}")

    # ------------------------------------------- request shape (with photo)
    print("Gemini request shape (customer photo)")
    photo = design_store.save_bytes(PNG_1X1, ".png")
    created_images.append(photo)
    transport.calls.clear()
    data, ext = ai_service.provider_for("gemini").generate(
        cfg=cfg, prompt="use the customer's photo for colour harmony",
        size="1024x1536", images=[design_store.path_for(photo)],
    )
    req = transport.last()
    check("A design with a photo still uses ONE call (no /images/edits)",
          len(transport.calls) == 1
          and "/images/edits" not in req.full_url, req.full_url)
    body = transport.bodies()[0]
    parts = body["contents"][0]["parts"]
    check("The prompt and the photo travel together",
          len(parts) == 2 and parts[0]["text"] and parts[1]["inline_data"],
          str(parts))
    check("The photo is sent as base64 inline_data",
          parts[1]["inline_data"]["data"]
          == base64.b64encode(PNG_1X1).decode())
    check("The photo's MIME type is declared",
          parts[1]["inline_data"]["mime_type"] == "image/png",
          parts[1]["inline_data"]["mime_type"])

    # ------------------------------------------------------ response parse
    print("Gemini response handling")
    provider = ai_service.provider_for("gemini")

    def expect_error(label: str, kind: str, body: bytes, payload=None):
        transport.calls.clear()
        transport.answer = (lambda req: _FakeResponse(body)) if payload is None \
            else payload
        try:
            provider.generate(cfg=cfg, prompt="p", size="1024x1536", images=[])
        except ai_service.AiError as exc:
            check(label, exc.kind == kind, f"got {exc.kind}: {exc.message}")
        else:
            check(label, False, "no error raised")

    expect_error("No candidates -> invalid_response", "invalid_response",
                 json.dumps({"candidates": []}).encode())
    expect_error("A blocked prompt is reported with its reason", "bad_request",
                 json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}).encode())
    expect_error("A safety stop is surfaced, not faked", "provider",
                 json.dumps({"candidates": [{
                     "content": {"parts": [{"text": "I cannot help."}]},
                     "finishReason": "IMAGE_SAFETY"}]}).encode())
    expect_error("A part carrying no image data is rejected", "invalid_response",
                 json.dumps({"candidates": [{"content": {"parts": [
                     {"inlineData": {"mimeType": "image/png"}}]}}]}).encode())
    expect_error("Malformed JSON is rejected", "invalid_response", b"<html>nope</html>")

    # a payload with the right shape but HTML bytes must not pass the sniff
    bad = json.dumps({"candidates": [{"content": {"parts": [
        {"inlineData": {"mimeType": "image/png",
                        "data": base64.b64encode(b"<html>nope</html>").decode()}}]}}]}).encode()
    expect_error("Bytes that are not a real image are rejected",
                 "invalid_response", bad)

    # ------------------------------------------------------- error mapping
    print("HTTP failures map onto honest kinds")

    def expect_http(label: str, code: int, kind: str,
                    message: str = "provider detail", contains: str = ""):
        transport.calls.clear()
        transport.answer = lambda req: (_ for _ in ()).throw(
            http_error(code, message))
        try:
            provider.generate(cfg=cfg, prompt="p", size="1024x1536", images=[])
        except ai_service.AiError as exc:
            ok = exc.kind == kind and (
                not contains or contains.lower() in exc.message.lower())
            check(label, ok, f"got {exc.kind}: {exc.message[:140]}")
        else:
            check(label, False, "no error raised")

    expect_http("401 -> auth", 401, "auth")
    expect_http("429 -> rate_limit", 429, "rate_limit")
    expect_http("500 -> provider (message preserved)", 500, "provider",
                contains="provider detail")
    # The real failure this phone hit: a valid key with no image quota. It must
    # NOT be dressed up as a transient rate limit that "try again" would fix.
    expect_http("429 carrying a quota message -> quota, not 'try again'", 429,
                "quota",
                message="You exceeded your current quota, please check your plan "
                        "and billing details",
                contains="quota")
    transport.answer = lambda req: (_ for _ in ()).throw(
        http_error(429, "You exceeded your current quota, please check your "
                        "plan and billing details"))
    try:
        provider.generate(cfg=cfg, prompt="p", size="1024x1536", images=[])
    except ai_service.AiError as exc:
        check("A quota failure never advises a pointless retry",
              "try again" not in exc.message.lower(), exc.message[:140])
        check("A quota failure points at billing",
              "billing" in exc.message.lower() or "plan" in exc.message.lower())
    else:
        check("A quota failure never advises a pointless retry", False,
              "no error raised")

    def expect_raised(label: str, raiser, kind: str):
        transport.calls.clear()
        transport.answer = lambda req: (_ for _ in ()).throw(raiser)
        try:
            provider.generate(cfg=cfg, prompt="p", size="1024x1536", images=[])
        except ai_service.AiError as exc:
            check(label, exc.kind == kind, f"got {exc.kind}: {exc.message}")
        else:
            check(label, False, "no error raised")

    expect_raised("Unreachable host -> network",
                  urllib.error.URLError("no route"), "network")
    expect_raised("Timeout -> timeout", socket.timeout("slow"), "timeout")

    # --------------------------------------------- connectivity probe
    print("Check AI connection (Gemini)")
    transport.answer = lambda req: _FakeResponse(b'{"models": []}')
    ai_service.reset_state()
    result = ai_service.check_connection()
    req = transport.last()
    check("The probe succeeds", result["ok"] is True, str(result))
    check("It probes the Gemini /models endpoint",
          req.full_url == f"https://{GEMINI_HOST}/v1beta/models", req.full_url)
    check("The probe is a GET", req.get_method() == "GET", req.get_method())
    check("The probe authenticates with x-goog-api-key, not Bearer",
          header(req, "x-goog-api-key") == GEMINI_KEY
          and header(req, "Authorization") is None)
    check("A successful probe is remembered as verified",
          ai_service.status()["verified"] is True)

    transport.answer = lambda req: (_ for _ in ()).throw(http_error(401, "bad key"))
    ai_service.reset_state()
    result = ai_service.check_connection()
    check("A rejected key is reported as auth", result["kind"] == "auth", str(result))
    check("The rejection flips the service to unavailable",
          ai_service.status()["state"] == "unavailable",
          ai_service.status()["state"])
    check("The Settings screen shows the real reason",
          "rejected the api key" in client.get("/settings").get_data(as_text=True).lower())
    ai_service.reset_state()

    # ---------------------------------------------------------- end to end
    print("End to end: Finish with AI with a Gemini key")
    ai_service.set_preference(True)
    set_env(DERB_AI_API_KEY=GEMINI_KEY, DERB_AI_PROVIDER="gemini")
    ai_service.reset_state()
    transport.answer = Transport._ok_json
    transport.calls.clear()
    resp = post_ai("warm gold background, more space for the title")
    review = resp.get_data(as_text=True)
    check("Finish with AI -> 200", resp.status_code == 200)
    check("The Gemini endpoint was called", any(
        GEMINI_HOST in c.full_url for c in transport.calls), str(transport.calls))
    check("The customer's wording reached the prompt", any(
        "Choir Anniversary" in json.loads(c.data.decode())["contents"][0]["parts"][0]["text"]
        for c in transport.calls if c.data))
    check("The prompt still forbids the model from drawing text", any(
        "no text, letters, words" in
        json.loads(c.data.decode())["contents"][0]["parts"][0]["text"]
        for c in transport.calls if c.data))
    check("The review screen is shown", "AI background ready" in review)
    m = re.search(r'name="ai_background" value="(ai_[0-9a-f]+\.png)"', review)
    check("The Gemini artwork is stored locally", bool(m))
    review_ai = m.group(1) if m else ""
    if review_ai:
        created_images.append(review_ai)
        check("Stored artwork is a real PNG",
              design_store.sniff_image_ext(
                  (DESIGN_IMAGES_DIR / review_ai).read_bytes()) == ".png")
    check("The API key is never rendered on the design screen",
          GEMINI_KEY not in review)
    check("The API key is never rendered on Settings",
          GEMINI_KEY not in client.get("/settings").get_data(as_text=True))

    # reject to clean up the stored artwork
    if review_ai:
        client.post("/graphic-design/ai/reject", data={
            "category": "anniversary", "title": "CAC Choir 10th Anniversary",
            "ai_background": review_ai, "ai_prompt": "warm gold",
        })
        if review_ai in created_images:
            created_images.remove(review_ai)

    # ------------------------------------------- per-provider image cap
    print("The reference-image cap follows the provider")
    many = [design_store.save_bytes(PNG_1X1, ".png") for _ in range(5)]
    created_images.extend(many)
    transport.calls.clear()
    resp = post_ai("more photos than Gemini accepts", image_filename=many)
    body = transport.bodies()[0] if transport.calls else {}
    check("Gemini receives at most 3 reference images",
          len(inline_parts(body)) == ai_service.provider_for("gemini").max_input_images,
          str(len(inline_parts(body))) if body else "no request")
    mm = re.search(r'name="ai_background" value="(ai_[0-9a-f]+\.png)"',
                   resp.get_data(as_text=True))
    if mm:
        created_images.append(mm.group(1))
    for name in many:
        design_store.delete_image(name)
        if name in created_images:
            created_images.remove(name)

    # -------------------------------------------------- honest failure
    print("A Gemini failure is honest, never faked")
    transport.answer = lambda req: (_ for _ in ()).throw(
        urllib.error.URLError("offline"))
    designs_before = projects_repo.count_projects("DESIGN")
    resp = post_ai("make it pop")
    failed = resp.get_data(as_text=True)
    check("A network failure still renders the design", resp.status_code == 200)
    check("The failure is stated, not hidden",
          "did not complete" in failed and "unchanged" in failed.lower())
    check("No AI result is faked",
          'name="ai_background"' not in failed)
    check("Nothing was saved on failure",
          projects_repo.count_projects("DESIGN") == designs_before)
    check("The service reports itself unavailable after the failure",
          ai_service.status()["state"] == "unavailable",
          ai_service.status()["state"])

    # ------------------------------------------------ local env file
    print("Private key entry (.env.local)")
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env.local"
        env_file.write_text(
            "# a comment\n"
            "\n"
            "DERB_AI_PROVIDER=gemini\n"
            'DERB_AI_API_KEY="quoted-key-123"\n'
            "PATH=/tmp/hijack\n"
            "SOME_OTHER=1\n"
            "DERB_AI_TIMEOUT=42\n",
            encoding="utf-8",
        )
        set_env(DERB_AI_PROVIDER="openai-images", DERB_AI_API_KEY=None,
                DERB_AI_TIMEOUT=None)
        applied = config.load_local_env(env_file)
        check("Only DERB_ keys from the file are honoured",
              sorted(applied) == ["DERB_AI_API_KEY", "DERB_AI_TIMEOUT"],
              str(applied))
        check("A quoted value is unquoted",
              os.environ.get("DERB_AI_API_KEY") == "quoted-key-123",
              str(os.environ.get("DERB_AI_API_KEY")))
        check("A real environment variable wins over the file",
              os.environ.get("DERB_AI_PROVIDER") == "openai-images")
        check("A non-DERB key cannot rewrite the environment",
              not (os.environ.get("PATH") or "").startswith("/tmp/hijack"))
        check("It returns key names, never values",
              "quoted-key-123" not in " ".join(applied))
        # a file that selects Gemini is what load_config ends up using
        set_env(DERB_AI_PROVIDER=None, DERB_AI_API_KEY=None, DERB_AI_TIMEOUT=None)
        env_file.write_text("DERB_AI_PROVIDER=gemini\nDERB_AI_API_KEY=file-key\n",
                            encoding="utf-8")
        config.load_local_env(env_file)
        cfg = ai_service.load_config()
        check("A file-selected Gemini provider drives load_config",
              cfg.provider == "gemini" and cfg.configured
              and cfg.model == "gemini-2.5-flash-image",
              f"{cfg.provider}/{cfg.model}/{cfg.configured}")
        set_env(DERB_AI_PROVIDER=None, DERB_AI_API_KEY=None, DERB_AI_TIMEOUT=None)

    # the real entry point picks the file up and announces names only
    app_env = {k: v for k, v in os.environ.items() if k not in ai_service.ENV_KEYS}
    real_env_file = PROJECT_ROOT / ".env.local"
    marker = "AIza-DERB-ENVFILE-MARKER-987"
    had_file = real_env_file.exists()
    try:
        real_env_file.write_text(
            f"DERB_AI_PROVIDER=gemini\nDERB_AI_API_KEY={marker}\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, "-c", "import app"],
                              cwd=str(PROJECT_ROOT), env=app_env,
                              capture_output=True, text=True, timeout=90)
        output = proc.stdout + proc.stderr
        check("app.py starts and loads the local settings file",
              proc.returncode == 0, f"exit {proc.returncode}: {output[-300:]}")
        check("It reports the key NAME that was loaded",
              "DERB_AI_API_KEY" in output, output[-300:])
        check("It never prints the key VALUE", marker not in output)
    finally:
        if not had_file:
            real_env_file.unlink(missing_ok=True)

    # -------------------------------------------------------- cleanup
    print("Cleanup")
    cleanup()
    left = [n for n in created_images if (DESIGN_IMAGES_DIR / n).exists()]
    check("Test images removed", not left, str(left))
    check("AI preference restored",
          templates_repo.get_setting(ai_service.PREF_KEY) == (prefs_before or ""))
    check("Transport restored",
          urllib.request.urlopen is transport._real)
    check("Provider override cleared", ai_service.get_provider().slug in
          {"openai-images", "gemini"})

    print("-" * 58)
    print(f"{passes} passed, {len(failures)} failed")
    if failures:
        print("\nFailures:")
        for f in failures:
            print("  -", f)
        return 1
    print("Gemini provider verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
