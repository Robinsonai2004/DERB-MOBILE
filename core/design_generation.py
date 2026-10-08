"""
Design generation service for DERB MOBILE.

This module is the ONE place that knows how a design is produced, so a real
image-generation / AI design service can be connected later without touching
the UI or the route layer.

Two providers exist:

* ``TemplateDesignProvider`` (active) - a real, offline, deterministic layout
  engine (core/design_render.py). It genuinely turns the operator's content
  into a finished poster. This is NOT presented as AI.
* ``AiDesignProvider`` (NOT configured) - a stub that documents exactly where a
  remote image/AI provider (and its API key) plugs in. It raises until wired,
  so the app never pretends an AI image was generated.

``provider_status()`` returns the honest state the UI shows the operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core import design_render


class GenerationNotConfigured(RuntimeError):
    """Raised when a provider is asked to run before it has been configured."""


class DesignProvider(Protocol):
    slug: str
    label: str
    configured: bool

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class TemplateDesignProvider:
    """Offline layout engine - always available, no network, no API key."""

    slug: str = "builtin-layout"
    label: str = "Built-in layout engine"
    configured: bool = True

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return design_render.build_layout(payload)


class AiDesignProvider:
    """Seam for a real remote image/AI design provider.

    To connect a provider:
      1. Add its HTTP client + API key here (read the key from config/env).
      2. Implement ``generate`` to POST the payload and either return image
         bytes to embed, or a layout spec this app can render.
      3. Flip ``configured`` to True and set a real ``label``.

    Until then the UI must keep telling the operator that AI generation is not
    connected - never substitute a static image and call it AI.
    """

    slug = "ai-remote"
    label = "AI image provider (not connected)"
    configured = False

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise GenerationNotConfigured(
            "No AI/image generation provider is configured. Set one up in "
            "core/design_generation.py and provide its API key."
        )


# The provider the app currently uses. Everything below reads from this.
_ACTIVE: DesignProvider = TemplateDesignProvider()


def get_provider() -> DesignProvider:
    return _ACTIVE


def generate_design(payload: dict[str, Any]) -> dict[str, Any]:
    """Produce a layout spec for the payload using the active provider."""
    return get_provider().generate(payload)


def provider_status() -> dict[str, Any]:
    """Honest, user-facing description of the active generation provider."""
    provider = get_provider()
    return {
        "configured": provider.configured,
        "provider": provider.slug,
        "label": provider.label,
        "note": (
            "Designs are produced by the built-in DERB layout engine from the "
            "information and images you enter. A real AI/image generation "
            "provider is not connected yet - it plugs in at "
            "core/design_generation.py when you have one."
        ),
    }


# Exposed so tests and the UI can assert the AI provider is honestly reported
# as unconfigured rather than faked.
AI_PROVIDER_CONFIGURED = AiDesignProvider.configured
