"""
Design generation service for DERB MOBILE.

This module is the ONE place that knows how a design is produced, so the UI and
the route layer never care which engine ran.

Two engines exist, and the app never confuses them:

* ``TemplateDesignProvider`` (active) - a real, offline, deterministic layout
  engine (core/design_render.py). It genuinely turns the operator's content
  into a finished poster. This is NOT presented as AI.
* The **AI finishing** path - core/ai_service.py. It talks to a real remote
  image provider, but only to produce *background artwork*; the layout engine
  above always re-draws the customer's text and photos on top of it, so an
  image model can never silently change a name, date or phone number.

``provider_status()`` returns the honest state the UI shows the operator,
including whether AI finishing is off, not configured, unavailable or ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core import ai_service, design_render


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


# The provider the app currently uses for layout. Everything below reads this.
_ACTIVE: DesignProvider = TemplateDesignProvider()


def get_provider() -> DesignProvider:
    return _ACTIVE


def generate_design(payload: dict[str, Any]) -> dict[str, Any]:
    """Produce a layout spec for the payload using the active provider."""
    return get_provider().generate(payload)


def ai_status() -> dict[str, Any]:
    """Honest AI-features status (see core/ai_service.status)."""
    return ai_service.status()


def ai_provider_configured() -> bool:
    """True only when an AI provider API key is actually available.

    Read from the environment on every call - never hard-coded - so the UI can
    never claim AI is connected when it is not, and never hides it when it is.
    """
    return ai_service.load_config().configured


def provider_status() -> dict[str, Any]:
    """Honest, user-facing description of design generation on this device."""
    state = ai_status()
    if state["state"] == "enabled":
        ai_note = ("AI finishing is switched on and a provider is configured. "
                   "In Graphic Design you can describe an improvement and let "
                   "the AI paint a new background; your text and photos are "
                   "always re-drawn by the built-in engine.")
    elif state["state"] == "not_configured":
        ai_note = ("AI finishing is switched on in Settings, but no provider "
                   "API key is configured on this device yet - so it cannot "
                   "run. The built-in layout engine is used instead.")
    elif state["state"] == "unavailable":
        ai_note = ("AI finishing is switched on but the provider could not be "
                   "reached on the last attempt. The built-in layout engine "
                   "still produces your design.")
    else:
        ai_note = ("AI finishing is switched off. Designs are produced by the "
                   "built-in DERB layout engine from the information and images "
                   "you enter. Turn AI on in Settings if you want it.")
    return {
        "configured": get_provider().configured,
        "provider": get_provider().slug,
        "label": get_provider().label,
        "note": ai_note,
        "ai": state,
    }
