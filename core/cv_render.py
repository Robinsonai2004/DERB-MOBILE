"""
CV template engine.

Maps a template's `layout` key to a Jinja view that renders the shared CV data
into an A4 "sheet". Templates are pure presentation: they receive the same
`cv` dict and never define their own data.

Adding a template later means:
  1. add a row to the `templates` table (or the Template Manager), and
  2. add one file under templates/cv/layouts/ if it uses a brand-new layout.

Nothing else in the app changes.
"""

from __future__ import annotations

from typing import Any

from flask import render_template

from core import cv_model

LAYOUTS: dict[str, str] = {
    "professional": "cv/layouts/professional.html",
    "modern": "cv/layouts/modern.html",
    "simple": "cv/layouts/simple.html",
}
DEFAULT_LAYOUT = "professional"


def layout_template(layout: str) -> str:
    return LAYOUTS.get(layout, LAYOUTS[DEFAULT_LAYOUT])


def render_sheet(cv: dict[str, Any], template: dict[str, Any]) -> str:
    """Render one A4 sheet of HTML for the given CV and template."""
    cv = cv_model.normalize(cv)
    return render_template(
        layout_template(template.get("layout", DEFAULT_LAYOUT)),
        cv=cv,
        template=template,
        accent=template.get("accent") or "#123a72",
        helpers=_Helpers(),
    )


def available_layouts() -> list[str]:
    return sorted(LAYOUTS)


class _Helpers:
    """Small presentation helpers exposed to the layout templates."""

    @staticmethod
    def responsibilities(text: str) -> list[str]:
        return cv_model.responsibilities_list(text)

    @staticmethod
    def contact_items(cv: dict[str, Any]) -> list[str]:
        return cv_model.contact_items(cv)

    @staticmethod
    def bio_items(cv: dict[str, Any]) -> list[str]:
        return cv_model.bio_items(cv)

    @staticmethod
    def initials(name: str) -> str:
        return cv_model.initials(name)

    @staticmethod
    def year_range(*years: str) -> str:
        vals = [y for y in years if y]
        return " - ".join(vals)
