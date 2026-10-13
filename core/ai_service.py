"""
AI design service for DERB MOBILE.

This is the ONE place that talks to a remote AI/image provider. Everything
about it is deliberately conservative, because DERB is an offline-first
customer-service tool and a wrong answer here means a lost customer job:

* **No secrets in code.** The API key is read from the environment every time
  it is needed. It is never written to the database, never rendered into a
  page and never logged. ``load_config()`` is the only reader.

* **Honest states.** ``status()`` reports exactly one of: ``disabled`` (the
  operator switched AI off), ``not_configured`` (switched on but no key),
  ``unavailable`` (configured, but the last attempt failed) or ``enabled``.
  There is no state in which the app pretends an image was generated.

* **Text survives.** The image model is asked for *background artwork only* -
  no letters, words, numbers or logos. Every piece of customer text (names,
  dates, venues, phone numbers, logos) is re-rendered by the existing
  deterministic engine (core/design_render.py) on top of the AI layer, so
  nothing can be silently changed or dropped.

* **Provider-agnostic, stdlib only.** Two providers are built in behind one
  seam, and every request is made with ``urllib.request`` - no SDK, so the
  phone still installs with zero build steps (see docs/DECISIONS.md).
  Selecting one is a single environment variable; nothing else changes.

How a design is finished is the same either way (see `finish_design`), so the
app never confuses which provider ran:

* ``openai-images`` (default) - the documented OpenAI Images API
  (``/images/generations`` text-to-image and ``/images/edits`` when the
  customer's own photos are sent along).
* ``gemini`` - Google's Gemini API, spoken **natively**: one
  ``models/{model}:generateContent`` call handles text-to-image *and* the
  customer's photos together (``inline_data`` parts), authenticating with the
  ``x-goog-api-key`` header. Google's OpenAI-compatibility layer is
  deliberately not used here, because it has no ``/images/edits`` equivalent.

Environment variables (all optional except the key):

    DERB_AI_PROVIDER       openai-images (default) | gemini
    DERB_AI_API_KEY        secret; absent = "not configured"
    DERB_AI_BASE_URL       provider default; any compatible gateway works
    DERB_AI_IMAGE_MODEL    provider default model
    DERB_AI_QUALITY        default "high"  (low | medium | high | auto)
    DERB_AI_SIZE_OVERRIDE  e.g. 1536x1024, overrides the aspect mapping
    DERB_AI_TIMEOUT        seconds, default 90
"""

from __future__ import annotations

import base64
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core import design_catalog as catalog
from core import design_model, design_render, design_store, templates_repo

# ---------------------------------------------------------------------------
# Settings keys (the existing key/value `settings` table - no new storage)
# ---------------------------------------------------------------------------
PREF_KEY = "ai_features_enabled"          # "1" / "0"
LAST_CHECK_KEY = "ai_last_check"          # JSON {"ok":bool,"at":str,"message":str}
LAST_ERROR_KEY = "ai_last_error"          # last failure message (never a key)

# ---------------------------------------------------------------------------
# Limits - every one of these is validated before *and* after the API call.
# ---------------------------------------------------------------------------
MAX_PROMPT = 600
AI_MAX_INPUT_IMAGES = 4
MAX_INPUT_BYTES = 8 * 1024 * 1024          # per uploaded image
# Several images are sent in ONE edit request, so bound their sum too - a
# design can carry images stored across separate uploads, and a phone must not
# try to POST 4 x 8 MB to the provider.
MAX_INPUT_TOTAL_BYTES = 10 * 1024 * 1024   # all reference images together
MAX_RESPONSE_BYTES = 16 * 1024 * 1024      # provider response
REQUEST_TIMEOUT_DEFAULT = 90
CHECK_TIMEOUT = 15

DEFAULT_PROVIDER = "openai-images"

# Each provider owns its own base URL and default model, so switching provider
# is one environment variable and nothing else. The label is what the Settings
# screen shows the operator - never the raw key.
PROVIDER_DEFAULTS = {
    "openai-images": {
        "label": "OpenAI Images API",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-image-1",
    },
    "gemini": {
        "label": "Google Gemini API",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-2.5-flash-image",
    },
}

DEFAULT_BASE_URL = PROVIDER_DEFAULTS[DEFAULT_PROVIDER]["base_url"]
DEFAULT_MODEL = PROVIDER_DEFAULTS[DEFAULT_PROVIDER]["model"]
DEFAULT_QUALITY = "high"

# The composition is content-driven, so the image only has to be a backdrop.
# Sizes the GPT image models document as standard; banner picks the widest.
ASPECT_SIZES = {
    "portrait": "1024x1536",
    "landscape": "1536x1024",
    "square": "1024x1024",
    "banner": "1536x1024",
}

ENV_KEYS = (
    "DERB_AI_PROVIDER", "DERB_AI_API_KEY", "DERB_AI_BASE_URL",
    "DERB_AI_IMAGE_MODEL", "DERB_AI_QUALITY", "DERB_AI_SIZE_OVERRIDE",
    "DERB_AI_TIMEOUT",
)


# ---------------------------------------------------------------------------
# Errors - one taxonomy the routes can turn into honest messages
# ---------------------------------------------------------------------------
class AiError(Exception):
    """A provider/validation failure with a kind the UI maps to a message.

    ``kind`` is one of: disabled, not_configured, bad_request, timeout,
    network, rate_limit, quota, auth, provider, invalid_response.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


# ---------------------------------------------------------------------------
# Configuration (read from the environment on every call, never cached)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AiConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    quality: str
    size_override: str
    timeout: int

    @property
    def configured(self) -> bool:
        """True only when a key is present - the single definition of 'set up'."""
        return bool(self.api_key)

    @property
    def label(self) -> str:
        name = PROVIDER_DEFAULTS.get(self.provider, {}).get("label", self.provider)
        return f"{name} · {self.model}" if self.configured else name


def selected_provider() -> str:
    """The provider slug from DERB_AI_PROVIDER, or the built-in default.

    An unrecognised value falls back to the default rather than guessing at a
    provider that was never configured - the Settings screen then reports the
    provider that will actually run.
    """
    slug = (os.environ.get("DERB_AI_PROVIDER") or "").strip().lower()
    return slug if slug in PROVIDER_DEFAULTS else DEFAULT_PROVIDER


def load_config() -> AiConfig:
    provider = selected_provider()
    defaults = PROVIDER_DEFAULTS[provider]
    base = (os.environ.get("DERB_AI_BASE_URL") or defaults["base_url"]).strip().rstrip("/")
    try:
        timeout = int(os.environ.get("DERB_AI_TIMEOUT") or REQUEST_TIMEOUT_DEFAULT)
    except (TypeError, ValueError):
        timeout = REQUEST_TIMEOUT_DEFAULT
    return AiConfig(
        provider=provider,
        api_key=(os.environ.get("DERB_AI_API_KEY") or "").strip(),
        base_url=base or defaults["base_url"],
        model=(os.environ.get("DERB_AI_IMAGE_MODEL") or defaults["model"]).strip()
              or defaults["model"],
        quality=(os.environ.get("DERB_AI_QUALITY") or DEFAULT_QUALITY).strip() or DEFAULT_QUALITY,
        size_override=(os.environ.get("DERB_AI_SIZE_OVERRIDE") or "").strip(),
        timeout=max(5, min(300, timeout)),
    )


# ---------------------------------------------------------------------------
# Operator preference (persisted in the existing settings table)
# ---------------------------------------------------------------------------
def preference_enabled() -> bool:
    return templates_repo.get_setting(PREF_KEY) == "1"


def set_preference(enabled: bool) -> None:
    templates_repo.set_setting(PREF_KEY, "1" if enabled else "0")


def _last_check() -> dict[str, Any]:
    raw = templates_repo.get_setting(LAST_CHECK_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _last_error() -> str:
    return templates_repo.get_setting(LAST_ERROR_KEY) or ""


def _record_check(ok: bool, message: str) -> None:
    from core import paths

    templates_repo.set_setting(
        LAST_CHECK_KEY,
        json.dumps({"ok": bool(ok), "at": paths.stamp(), "message": message[:300]}),
    )


def _record_error(message: str | None) -> None:
    if message:
        templates_repo.set_setting(LAST_ERROR_KEY, message[:300])
    else:
        templates_repo.set_setting(LAST_ERROR_KEY, "")


def reset_state() -> None:
    """Forget the cached availability of the provider (used by tests/settings)."""
    templates_repo.set_setting(LAST_CHECK_KEY, "")
    templates_repo.set_setting(LAST_ERROR_KEY, "")


# ---------------------------------------------------------------------------
# Honest status - what the Settings page and the design screens show
# ---------------------------------------------------------------------------
def status() -> dict[str, Any]:
    """The single source of truth for "can AI finish a design right now?"."""
    cfg = load_config()
    enabled = preference_enabled()
    check = _last_check()
    error = _last_error()

    if not enabled:
        state = "disabled"
        message = ("AI features are switched off. The normal Graphic Design "
                   "editor keeps working exactly as before.")
    elif not cfg.configured:
        state = "not_configured"
        message = ("AI features are switched on, but no provider API key is "
                   "configured on this device yet.")
    elif error and not check.get("ok"):
        state = "unavailable"
        message = error
    else:
        state = "enabled"
        message = "AI finishing is available in the Graphic Design workspace."

    return {
        "state": state,
        "enabled": enabled,
        "configured": cfg.configured,
        # `ready` is the strict "reachable right now" flag (used for the
        # verification badge); `usable` means AI finishing can still be
        # *attempted* - on, with a key. A single transient failure records
        # `unavailable` and clears `ready`, but must NOT take the retry button
        # away from the operator.
        "ready": state == "enabled",
        "usable": enabled and cfg.configured,
        "provider": cfg.provider,
        "label": cfg.label,
        "model": cfg.model,
        # Never hand the full base URL (or anything derived from the key) to a
        # template: the host is all the operator needs to identify the provider.
        "base_host": urllib.parse.urlsplit(cfg.base_url).netloc or cfg.base_url,
        "verified": bool(check.get("ok")),
        "checked_at": check.get("at") or "",
        "last_error": error,
        "message": message,
        "env_keys": list(ENV_KEYS),
    }


def check_connection(cfg: AiConfig | None = None) -> dict[str, Any]:
    """Cheap reachability/credential probe for the *selected* provider.

    Each provider knows its own auth header and probe endpoint (both are
    ``GET {base}/models`` here, but Gemini authenticates with
    ``x-goog-api-key`` rather than a Bearer token). It deliberately does not
    generate an image: that would cost the operator money just to open a
    settings screen.

    The check always probes the *configured* provider, never a test override -
    it answers "will my key work against my provider?", which is the only
    question the operator is asking.
    """
    cfg = cfg or load_config()
    if not cfg.configured:
        return {"ok": False, "kind": "not_configured",
                "message": "No API key is configured."}
    try:
        provider_for(cfg.provider).check(cfg)
    except AiError as exc:
        _record_check(False, exc.message)
        _record_error(exc.message)
        return {"ok": False, "kind": exc.kind, "message": exc.message}
    except Exception as exc:  # pragma: no cover - defensive
        msg = f"Could not reach the provider ({type(exc).__name__})."
        _record_check(False, msg)
        _record_error(msg)
        return {"ok": False, "kind": "network", "message": msg}
    msg = "Provider reachable and the API key was accepted."
    _record_check(True, msg)
    _record_error(None)
    return {"ok": True, "kind": "ok", "message": msg}


# ---------------------------------------------------------------------------
# The provider seam - swappable so tests never call a paid API
# ---------------------------------------------------------------------------
class ImageProvider(Protocol):
    slug: str
    label: str

    def generate(self, *, cfg: AiConfig, prompt: str, size: str,
                 images: list[Path]) -> tuple[bytes, str]: ...


def _multipart(fields: dict[str, str],
               files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    """Encode a multipart/form-data body with the standard library only."""
    import secrets

    boundary = "----derbmobile" + secrets.token_hex(12)
    crlf = b"\r\n"
    out = bytearray()
    for name, value in fields.items():
        out += b"--" + boundary.encode() + crlf
        out += f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf
        out += str(value).encode("utf-8") + crlf
    for name, filename, ctype, data in files:
        out += b"--" + boundary.encode() + crlf
        out += (f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"').encode() + crlf
        out += f"Content-Type: {ctype}".encode() + crlf + crlf
        out += data + crlf
    out += b"--" + boundary.encode() + b"--" + crlf
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _raise_for(kind: str, message: str) -> None:
    raise AiError(kind, message)


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    """Pull the provider's message without ever leaking the request body."""
    try:
        raw = exc.read(4096)
    except Exception:  # pragma: no cover - defensive
        return ""
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return ""
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:300]
        if isinstance(err, str):
            return err[:300]
        if data.get("message"):
            return str(data["message"])[:300]
    return ""


IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp",
}


def _mime_for(path: Path) -> str:
    return IMAGE_MIME.get(path.suffix.lower(), "application/octet-stream")


def _probe_models(cfg: AiConfig, headers: dict[str, str]) -> None:
    """``GET {base}/models`` with the provider's own auth header.

    Cheap and non-billable: it proves the host is reachable and the key is
    accepted without generating (and paying for) an image. Raises
    :class:`AiError` on any failure.
    """
    req = urllib.request.Request(
        f"{cfg.base_url}/models",
        headers={**headers, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            resp.read(1024)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            _raise_for("auth", "The provider rejected the API key "
                               f"(HTTP {exc.code}). Check DERB_AI_API_KEY.")
        _raise_for("provider", f"The provider answered HTTP {exc.code}.")
    except (socket.timeout, TimeoutError):
        _raise_for("timeout", "The provider did not respond in time.")
    except urllib.error.URLError as exc:
        _raise_for("network", f"Could not reach the provider ({exc.reason}).")
    except OSError as exc:  # pragma: no cover - defensive
        _raise_for("network", f"Could not reach the provider ({exc}).")


def _raise_rate_limit(provider_name: str, detail: str) -> None:
    """Turn a 429 into an honest error.

    HTTP 429 covers two very different situations - transient throttling and an
    exhausted quota/plan - and the provider's own words are the only way to tell
    them apart. Saying "try again shortly" when the real fix is billing would
    send the operator in circles, so a quota hangs off its own ``quota`` kind.
    """
    if detail and "quota" in detail.lower():
        _raise_for("quota", f"The {provider_name} reports this key's quota or "
                            f"plan is exhausted: {detail}")
    _raise_for("rate_limit", f"The {provider_name} is rate limiting this device. "
                             "Wait a moment and try again.")


class OpenAiImagesProvider:
    """Documented OpenAI Images API over urllib (generations + edits)."""

    slug = "openai-images"
    label = "OpenAI Images API"
    # GPT image models accept several reference images on the edits endpoint.
    max_input_images = AI_MAX_INPUT_IMAGES

    def check(self, cfg: AiConfig) -> None:
        """Reachability/credential probe; raises :class:`AiError` on failure."""
        _probe_models(cfg, {"Authorization": f"Bearer {cfg.api_key}"})

    def generate(self, *, cfg: AiConfig, prompt: str, size: str,
                 images: list[Path]) -> tuple[bytes, str]:
        if images:
            return self._edit(cfg=cfg, prompt=prompt, size=size, images=images)
        return self._generations(cfg=cfg, prompt=prompt, size=size)

    # -- helpers ----------------------------------------------------------
    def _post(self, cfg: AiConfig, url: str, body: bytes, ctype: str) -> dict:
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": ctype,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            if exc.code in (401, 403):
                _raise_for("auth", "The AI provider rejected the API key "
                                   f"(HTTP {exc.code}). Check DERB_AI_API_KEY.")
            if exc.code == 429:
                _raise_rate_limit("AI provider", detail)
            _raise_for("provider", f"The AI provider returned HTTP {exc.code}"
                                   + (f": {detail}" if detail else "."))
        except (socket.timeout, TimeoutError):
            _raise_for("timeout", "The AI provider did not respond in time. "
                                  "Try again, or raise DERB_AI_TIMEOUT.")
        except urllib.error.URLError as exc:
            _raise_for("network", f"Could not reach the AI provider ({exc.reason}). "
                                  "Check this phone's internet connection.")
        except OSError as exc:  # pragma: no cover - defensive
            _raise_for("network", f"Could not reach the AI provider ({exc}).")
        if len(raw) > MAX_RESPONSE_BYTES:
            _raise_for("invalid_response", "The AI provider response was too large.")
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except (TypeError, ValueError):
            _raise_for("invalid_response", "The AI provider sent a response this "
                                           "app could not read.")
        if not isinstance(data, dict) or not data.get("data"):
            _raise_for("invalid_response", "The AI provider returned no image.")
        return data

    @staticmethod
    def _extract(data: dict, cfg: AiConfig) -> tuple[bytes, str]:
        first = (data.get("data") or [{}])[0]
        if not isinstance(first, dict):
            _raise_for("invalid_response", "The AI provider returned no image.")
        b64 = first.get("b64_json") or first.get("b64")
        if b64:
            try:
                raw = base64.b64decode(b64, validate=False)
            except (ValueError, TypeError):
                _raise_for("invalid_response", "The AI image could not be decoded.")
        elif first.get("url"):
            raw = OpenAiImagesProvider._download(cfg, str(first["url"]))
        else:
            _raise_for("invalid_response", "The AI provider returned no image data.")
        if not raw:
            _raise_for("invalid_response", "The AI provider returned an empty image.")
        if len(raw) > MAX_RESPONSE_BYTES:
            _raise_for("invalid_response", "The AI image was too large to store.")
        ext = design_store.sniff_image_ext(raw)
        if ext is None:
            _raise_for("invalid_response", "The AI provider did not return a real "
                                           "image (unrecognised file format).")
        return raw, ext

    @staticmethod
    def _download(cfg: AiConfig, url: str) -> bytes:
        if not url.startswith(("http://", "https://")):
            _raise_for("invalid_response", "The AI provider returned an unsafe URL.")
        try:
            with urllib.request.urlopen(url, timeout=cfg.timeout) as resp:  # noqa: S310
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            _raise_for("network", f"Could not download the AI image ({exc}).")
        if len(raw) > MAX_RESPONSE_BYTES:
            _raise_for("invalid_response", "The AI image was too large to store.")
        return raw

    def _generations(self, *, cfg: AiConfig, prompt: str, size: str) -> tuple[bytes, str]:
        body = json.dumps({
            "model": cfg.model, "prompt": prompt, "size": size, "n": 1,
            "quality": cfg.quality, "output_format": "png",
        }).encode("utf-8")
        data = self._post(cfg, f"{cfg.base_url}/images/generations", body,
                          "application/json")
        return self._extract(data, cfg)

    def _edit(self, *, cfg: AiConfig, prompt: str, size: str,
              images: list[Path]) -> tuple[bytes, str]:
        files: list[tuple[str, str, str, bytes]] = []
        for path in images:
            ctype = _mime_for(path)
            # GPT image models accept `image` (1 file) / `image[]` (many).
            name = "image" if len(images) == 1 else "image[]"
            files.append((name, path.name, ctype, path.read_bytes()))
        fields = {"model": cfg.model, "prompt": prompt, "size": size,
                  "n": "1", "quality": cfg.quality, "output_format": "png"}
        body, ctype = _multipart({k: v for k, v in fields.items()}, files)
        data = self._post(cfg, f"{cfg.base_url}/images/edits", body, ctype)
        return self._extract(data, cfg)


class GeminiImagesProvider:
    """Google Gemini API, spoken natively over urllib.

    One ``models/{model}:generateContent`` call covers both text-to-image and
    image-to-image: the customer's own photos become ``inline_data`` parts in
    the *same* request. That is why this app does not use Google's
    OpenAI-compatibility layer for Gemini - it has no ``/images/edits``
    equivalent, so a pure base-URL swap would silently drop the customer's
    photos. The key travels in the ``x-goog-api-key`` header exactly as the
    Gemini API documents - never in the URL, so it cannot end up in a log line.
    """

    slug = "gemini"
    label = "Google Gemini API"
    # gemini-2.5-flash-image documents a maximum of 3 reference images.
    max_input_images = 3

    def check(self, cfg: AiConfig) -> None:
        """Reachability/credential probe; raises :class:`AiError` on failure."""
        _probe_models(cfg, {"x-goog-api-key": cfg.api_key})

    def generate(self, *, cfg: AiConfig, prompt: str, size: str,
                 images: list[Path]) -> tuple[bytes, str]:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for path in images:
            parts.append({
                "inline_data": {
                    "mime_type": _mime_for(path),
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            })
        # The background's aspect/tone is described in the prompt that
        # compose_prompt() builds, so no model-specific generationConfig is
        # sent - the request stays valid across Gemini image models.
        body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
        url = f"{cfg.base_url}/models/{cfg.model}:generateContent"
        return self._extract(self._post(cfg, url, body))

    def _post(self, cfg: AiConfig, url: str, body: bytes) -> dict:
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "x-goog-api-key": cfg.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            if exc.code in (401, 403):
                _raise_for("auth", "The Gemini API rejected the API key "
                                   f"(HTTP {exc.code}). Check DERB_AI_API_KEY.")
            if exc.code == 429:
                _raise_rate_limit("Gemini API", detail)
            _raise_for("provider", f"The Gemini API returned HTTP {exc.code}"
                                   + (f": {detail}" if detail else "."))
        except (socket.timeout, TimeoutError):
            _raise_for("timeout", "The Gemini API did not respond in time. "
                                  "Try again, or raise DERB_AI_TIMEOUT.")
        except urllib.error.URLError as exc:
            _raise_for("network", f"Could not reach the Gemini API ({exc.reason}). "
                                  "Check this phone's internet connection.")
        except OSError as exc:  # pragma: no cover - defensive
            _raise_for("network", f"Could not reach the Gemini API ({exc}).")
        if len(raw) > MAX_RESPONSE_BYTES:
            _raise_for("invalid_response", "The Gemini API response was too large.")
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except (TypeError, ValueError):
            _raise_for("invalid_response", "The Gemini API sent a response this "
                                           "app could not read.")
        if not isinstance(data, dict):
            _raise_for("invalid_response", "The Gemini API sent a response this "
                                           "app could not read.")
        return data

    @staticmethod
    def _extract(data: dict) -> tuple[bytes, str]:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            # A prompt-level block (safety, recitation) arrives here with no
            # candidate at all - say so rather than failing generically.
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason") if isinstance(feedback, dict) else ""
            if reason:
                _raise_for("bad_request", f"The Gemini API refused the prompt "
                                           f"({reason}). Rework the description "
                                           "and try again.")
            _raise_for("invalid_response", "The Gemini API returned no image.")
        first = candidates[0] if isinstance(candidates[0], dict) else {}
        for part in (first.get("content") or {}).get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict) or not inline.get("data"):
                continue
            try:
                raw = base64.b64decode(inline["data"], validate=False)
            except (ValueError, TypeError):
                _raise_for("invalid_response", "The Gemini image could not be decoded.")
            if not raw:
                _raise_for("invalid_response", "The Gemini API returned an empty image.")
            if len(raw) > MAX_RESPONSE_BYTES:
                _raise_for("invalid_response", "The Gemini image was too large to store.")
            ext = design_store.sniff_image_ext(raw)
            if ext is None:
                _raise_for("invalid_response", "The Gemini API did not return a real "
                                               "image (unrecognised file format).")
            return raw, ext
        finish = first.get("finishReason") or ""
        if finish and finish not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            _raise_for("provider", f"The Gemini API stopped before producing an "
                                   f"image ({finish}).")
        _raise_for("invalid_response", "The Gemini API returned no image data.")


_OPENAI_PROVIDER = OpenAiImagesProvider()
_GEMINI_PROVIDER = GeminiImagesProvider()
_PROVIDERS: dict[str, ImageProvider] = {
    _OPENAI_PROVIDER.slug: _OPENAI_PROVIDER,
    _GEMINI_PROVIDER.slug: _GEMINI_PROVIDER,
}

# Override seam: when set it wins over the configured provider. Tests install a
# fake here; set_provider(None) goes back to following DERB_AI_PROVIDER.
_PROVIDER: ImageProvider | None = None


def provider_for(slug: str) -> ImageProvider:
    """The real implementation for a provider slug (config + UI use)."""
    return _PROVIDERS.get(slug) or _OPENAI_PROVIDER


def get_provider() -> ImageProvider:
    """The provider that will actually run: an override, else the selected one."""
    return _PROVIDER or provider_for(load_config().provider)


def set_provider(provider: ImageProvider | None) -> None:
    """Swap the provider (tests install a fake here; None restores selection)."""
    global _PROVIDER
    _PROVIDER = provider


# ---------------------------------------------------------------------------
# Prompt composition - the design's own content, plus the operator's words
# ---------------------------------------------------------------------------
def size_for(aspect: str) -> str:
    return ASPECT_SIZES.get(aspect, ASPECT_SIZES["portrait"])


def compose_prompt(payload: dict[str, Any], request: str) -> str:
    """Describe the design to the image model WITHOUT asking it to draw text."""
    category = catalog.get_category(payload.get("category")) or catalog.CATEGORIES[0]
    theme = catalog.get_theme(payload.get("theme") or category.theme)
    style = payload.get("style") or design_render.DEFAULT_STYLE.get(category.slug, "grid")
    content = design_render.assemble(category, payload)

    lines = [
        f"Create decorative BACKGROUND ARTWORK for a {category.name} poster "
        f"({category.aspect}, aspect ratio {catalog.ASPECTS.get(category.aspect, 0.7071):.3f}).",
        "This is only the backdrop: a real layout engine re-draws all of the "
        "text and the customer's photos on top of your image.",
    ]
    if content["headline"]:
        lines.append(f"Headline reading area (leave this space clear of clutter): "
                     f"{content['headline'][:80]}")
    if content["name"]:
        lines.append(f"Name / star line area: {content['name'][:60]}")
    if content["sub"]:
        lines.append(f"Sub-heading area: {content['sub'][:60]}")
    if content["info"]:
        lines.append(f"Date / venue line area: {content['info'][:80]}")
    if content["contact"]:
        lines.append("Contact details line area (keep the lower edge quiet): "
                     "text is added by the engine")
    lines.append(f"Colour direction: {theme['name']} "
                 f"(accent {theme['accent']}, background {theme['bg1']}, "
                 f"ink {theme['ink']}).")
    lines.append(f"Composition style: {style}.")
    if len(content["photos"]) > 0:
        lines.append("The attached image(s) are the customer's own photos/logo: use "
                     "them for colour harmony, tone and where the subject should sit.")
    if request:
        lines.append(f"Operator's requested improvements: {request}")

    lines.append(
        "HARD RULES: no text, letters, words, numbers, watermarks, signatures or "
        "logos anywhere in the image; no borders or frames around the whole edge; "
        "keep the design clean, professional and print-quality for a Nigerian "
        "print shop; leave calm, uncluttered areas where the engine drops its text."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation of the request (before spending the operator's API credit)
# ---------------------------------------------------------------------------
def validate_request(payload: dict[str, Any], request: str) -> str:
    """Return the cleaned operator instruction or raise AiError('bad_request')."""
    text = (request or "").strip()
    if not text:
        _raise_for("bad_request", "Describe the improvement you want first, "
                                  "for example 'warmer gold background, more "
                                  "space at the top'.")
    if len(text) > MAX_PROMPT:
        _raise_for("bad_request", f"Keep the description under {MAX_PROMPT} characters.")

    category = catalog.get_category(payload.get("category"))
    if category is None:
        _raise_for("bad_request", "Choose a design type first.")

    # design_model.normalize() already caps a design at MAX_IMAGES, so this is
    # a backstop against an unbounded list rather than the normal path: a design
    # with more images is fine, only the first AI_MAX_INPUT_IMAGES are sent.
    images = payload.get("images") or []
    if len(images) > design_model.MAX_IMAGES:
        _raise_for("bad_request",
                   f"A design can carry at most {design_model.MAX_IMAGES} images.")
    total = 0
    for item in images:
        name = (item or {}).get("filename") or ""
        if not name:
            continue
        if not design_store.is_safe_name(name):
            _raise_for("bad_request", "That image reference is not valid.")
        path = design_store.path_for(name)
        if not path.is_file():
            _raise_for("bad_request", f"The uploaded image {name} is missing.")
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            _raise_for("bad_request", f"{name} is not a PNG, JPG or WebP image.")
        size = path.stat().st_size
        if size > MAX_INPUT_BYTES:
            _raise_for("bad_request", f"{name} is larger than "
                                      f"{MAX_INPUT_BYTES // (1024 * 1024)} MB.")
        total += size
    if total > MAX_INPUT_TOTAL_BYTES:
        _raise_for("bad_request", "The images for one AI request add up to more "
                                  f"than {MAX_INPUT_TOTAL_BYTES // (1024 * 1024)} MB. "
                                  "Remove one and try again.")
    return text


def input_image_paths(payload: dict[str, Any],
                      limit: int = AI_MAX_INPUT_IMAGES) -> list[Path]:
    """Existing, validated upload paths to send as reference (capped by the
    caller to the selected provider's limit)."""
    out: list[Path] = []
    for item in (payload.get("images") or [])[:limit]:
        name = (item or {}).get("filename") or ""
        if name and design_store.is_safe_name(name):
            path = design_store.path_for(name)
            if path.is_file():
                out.append(path)
    return out


# ---------------------------------------------------------------------------
# The one entry point the Graphic Design route uses
# ---------------------------------------------------------------------------
def finish_design(payload: dict[str, Any], request: str,
                  provider: ImageProvider | None = None) -> dict[str, Any]:
    """Finish the design's background with AI, or raise :class:`AiError`.

    The returned dict carries the image *bytes*; the caller stores them. The
    original payload is never mutated - the operator decides when an AI result
    replaces their design. Every failure path records why, so the Settings
    screen and the design screen can both tell the truth about it.
    """
    try:
        state = status()
        if not state["enabled"]:
            _raise_for("disabled", "AI features are switched off. Turn them on in "
                                   "Settings first.")
        cfg = load_config()
        if not cfg.configured:
            _raise_for("not_configured",
                       "No AI provider API key is configured on this device. "
                       "Add one in Settings to use AI finishing.")

        text = validate_request(payload, request)
        category = catalog.get_category(payload.get("category")) or catalog.CATEGORIES[0]
        size = cfg.size_override or size_for(category.aspect)
        prompt = compose_prompt(payload, text)
        active = provider or get_provider()
        # Each provider accepts a different number of reference images, so the
        # cap is read from the provider that will actually run.
        limit = getattr(active, "max_input_images", AI_MAX_INPUT_IMAGES)
        images = input_image_paths(payload, limit)

        try:
            data, ext = active.generate(
                cfg=cfg, prompt=prompt, size=size, images=images
            )
        except AiError:
            raise
        except Exception as exc:  # the provider blew up in an unexpected way
            raise AiError("provider", "The AI provider failed "
                                       f"({type(exc).__name__}).") from exc

        if not data or design_store.sniff_image_ext(data) is None:
            _raise_for("invalid_response",
                       "The AI provider did not return a usable image. Nothing "
                       "was changed.")
    except AiError as exc:
        # 'disabled'/'not_configured'/'bad_request' are the operator's own doing,
        # not a provider outage, so they must not mark the service unavailable.
        if exc.kind not in ("disabled", "not_configured", "bad_request"):
            _record_error(exc.message)
        raise

    _record_error(None)
    return {
        "image_bytes": data,
        "ext": ext,
        "prompt": text,
        "composed_prompt": prompt,
        "provider": cfg.provider,
        "model": cfg.model,
        "size": size,
        "used_images": [p.name for p in images],
    }
