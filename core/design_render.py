"""
Design layout engine for DERB MOBILE - standard library only.

Turns a design payload into an *element composition* (background, photos,
decorative shapes and measured text) that the HTML preview, the print dialog
and the canvas exporter all render identically.

Design rules baked into this engine:

* Role-based content. Fields are assembled into headline / name / sub-head /
  info lines / body / contact - never dumped as a "LABEL: value" table, and
  never more of them than the design type actually needs.
* Measured text. Every line is wrapped and fitted with real font metrics
  (core/cv_pdf._width), so the browser and the canvas draw the SAME lines and
  nothing can overlap or run into the next section. Text shrinks to fit its
  box, then truncates - it never overflows it.
* Real compositions, not a colour swap. Five structurally different templates
  (hero, split, ornate, strip, grid) place photos and text differently.
* Photos are part of the composition: full-bleed with a scrim, framed panels,
  or circular portraits - always cropped to fill, never pasted on as an after
  thought.
* The composition is content-driven: block heights come from measured text and
  photos grow into the space that is left, so the canvas stays full.
"""

from __future__ import annotations

from datetime import date, datetime

from core import design_catalog as catalog
from core.cv_pdf import _width

EXPORT_WIDTH = 1240

# Helvetica metrics vs the system sans on a phone - wrap conservatively so the
# rendered line is always shorter than its box.
FONT_SAFETY = 1.12
LINE_HEIGHT = 1.16
MAX_IMAGES = 4

# How much of the theme background is laid over accepted AI artwork. The image
# model is asked for artwork with no text at all, so the engine keeps drawing
# every piece of customer text on top; this tint keeps that text readable.
AI_SCRIM = 0.72


# ---------------------------------------------------------------------------
# Text metrics / fitting
# ---------------------------------------------------------------------------
def _font(weight: str) -> str:
    return "helvetica-bold" if str(weight) in ("700", "800", "bold") else "helvetica"


def _wrap(text: str, weight: str, size: float, max_w: float) -> list[str]:
    """Wrap to a conservative width; honours hard newlines."""
    if not text:
        return [""]
    font = _font(weight)
    limit = max_w / FONT_SAFETY if max_w > 0 else max_w
    lines: list[str] = []
    for para in str(text).split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if _width(trial, font, size) <= limit:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines or [""]


def text_el(x: float, y: float, max_w: float, max_h: float, text: str,
            size: float, *, weight: str = "400", color: str = "#111111",
            align: str = "left", italic: bool = False, uppercase: bool = False,
            min_size: float | None = None, valign: str = "top",
            tracking: float = 0.0) -> dict | None:
    """Measure, wrap and fit text into the box. Never taller than max_h."""
    if not str(text or "").strip() or max_w <= 0 or max_h <= 0:
        return None
    source = str(text).upper() if uppercase else str(text)
    font = _font(weight)
    s = float(size)
    floor = float(min_size) if min_size else max(9.0, size * 0.52)

    while True:
        lines = _wrap(source, weight, s, max_w)
        height = len(lines) * s * LINE_HEIGHT
        if height <= max_h or s <= floor + 0.01:
            break
        s = max(floor, s * 0.94)

    height = len(lines) * s * LINE_HEIGHT
    if height > max_h:  # still too tall: truncate, never overflow
        max_lines = max(1, int(max_h // (s * LINE_HEIGHT)))
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _width(last + "...", font, s) > max_w / FONT_SAFETY:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
        height = len(lines) * s * LINE_HEIGHT

    top = y + (max_h - height) / 2 if valign == "middle" else y
    return {
        "kind": "text", "x": round(x, 1), "y": round(top, 1),
        "w": round(max_w, 1), "h": round(height, 1),
        "size": round(s, 1), "line_h": round(s * LINE_HEIGHT, 1),
        "lines": lines, "align": align, "weight": weight, "color": color,
        "italic": italic, "uppercase": uppercase, "tracking": round(tracking, 2),
        "font": font,
    }


def _text_height(text: str, size: float, max_w: float, weight: str = "400") -> float:
    """Height a fitted block will occupy (so the flow can advance safely)."""
    el = text_el(0, 0, max_w, 10_000, text, size, weight=weight)
    return el["h"] if el else 0.0


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------
def rect(x, y, w, h, fill, *, fill2=None, grad_dir="to bottom", radius=0.0,
         opacity=None, stroke=None, stroke_w=0.0) -> dict:
    el = {"kind": "rect", "x": round(x, 1), "y": round(y, 1),
          "w": round(w, 1), "h": round(h, 1), "fill": fill, "radius": round(radius, 1)}
    if fill2:
        el["fill2"] = fill2
        el["grad_dir"] = grad_dir
    if opacity is not None:
        el["opacity"] = opacity
    if stroke:
        el["stroke"] = stroke
        el["stroke_w"] = round(stroke_w, 1)
    return el


def ellipse(cx, cy, rx, ry, fill, *, opacity=None, stroke=None, stroke_w=0.0) -> dict:
    el = {"kind": "ellipse", "x": round(cx - rx, 1), "y": round(cy - ry, 1),
          "w": round(rx * 2, 1), "h": round(ry * 2, 1), "fill": fill}
    if opacity is not None:
        el["opacity"] = opacity
    if stroke:
        el["stroke"] = stroke
        el["stroke_w"] = round(stroke_w, 1)
    return el


def photo_el(x, y, w, h, filename, *, shape="rect", radius=0.0, border=None,
             border_w=0.0) -> dict:
    return {"kind": "photo", "x": round(x, 1), "y": round(y, 1),
            "w": round(w, 1), "h": round(h, 1), "file": filename,
            "shape": shape, "radius": round(radius, 1),
            "border": border, "border_w": round(border_w, 1)}


def _base(ctx: dict) -> list[dict]:
    """The composition's background layer.

    When the operator has accepted an AI backdrop it is drawn full-bleed with
    a theme-tinted scrim; otherwise the theme gradient is used, exactly as
    before. Everything the composition places afterwards (text, photos,
    decoration) is unaffected either way.
    """
    W, H, pal = ctx["W"], ctx["H"], ctx["pal"]
    bg = ctx.get("bg")
    if bg:
        return [photo_el(0, 0, W, H, bg),
                rect(0, 0, W, H, pal["bg1"], opacity=AI_SCRIM)]
    return [rect(0, 0, W, H, pal["bg1"], fill2=pal["bg2"])]


# ---------------------------------------------------------------------------
# Content assembly - roles, not a field table
# ---------------------------------------------------------------------------
def _pretty_date(value: str) -> str:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%a %d %b %Y").replace(" 0", " ")
        except ValueError:
            continue
    return value


def _pretty_time(value: str) -> str:
    try:
        t = datetime.strptime(value, "%H:%M")
        return t.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return value


def assemble(category: catalog.DesignCategory, payload: dict) -> dict:
    """Pick the fields that matter for THIS design type and shape them."""
    f = payload.get("fields") or {}

    def first(*keys: str) -> str:
        for k in keys:
            v = (f.get(k) or "").strip()
            if v:
                return v
        return ""

    title = (payload.get("title") or "").strip()

    # ---- headline: the operator's own title, else composed for the type ----
    headline = title
    if not headline:
        age = (f.get("age") or "").strip()
        number = (f.get("anniversary_number") or "").strip()
        kind = (f.get("anniversary_type") or "").strip()
        if category.slug == "birthday" and age:
            headline = f"{age}th Birthday Celebration" if age.isdigit() else f"{age} Birthday"
        elif category.slug == "anniversary" and number:
            headline = f"{number} {kind or 'Anniversary'}".strip()
        elif f.get("certificate_title"):
            headline = f["certificate_title"]
        else:
            headline = category.name

    # ---- the star line (celebrant / awardee / couple / business) ----------
    name = first("honoree", "name", "graduate_name", "awardee", "couple_names",
                 "deceased_name", "business_name", "product_name", "custom_title")
    if name and name == headline:
        name = ""

    sub = first("anniversary_type", "degree", "position", "theme", "business_type",
                "certificate_title", "event_name", "main_title", "colour_theme")
    if sub and sub in (headline, name, sub) and sub == headline:
        sub = ""

    org = first("organisation", "institution", "business_name", "host_name",
                "social_handle", "socials")

    # ---- info line: date / time / venue, only what exists ----------------
    info_bits = []
    if f.get("date_event"):
        info_bits.append(_pretty_date(f["date_event"].strip()))
    if f.get("time_event"):
        info_bits.append(_pretty_time(f["time_event"].strip()))
    if f.get("venue"):
        info_bits.append(f["venue"].strip())
    info_line = "  •  ".join(info_bits)

    extra: list[str] = []
    for key, label in (("guest_minister", "Guest Minister"),
                       ("special_guests", "Special Guests"),
                       ("officiating", "Officiating"),
                       ("years_service", "Years of Service"),
                       ("price", "Price"),
                       ("offer", "Offer"),
                       ("host_name", "Host"),
                       ("hosts", "Hosts"),
                       ("signatory", "")):
        v = (f.get(key) or "").strip()
        if not v:
            continue
        extra.append(f"{label}: {v}" if label else v)

    body = first("message", "details", "promo_message", "certificate_body",
                 "event_details", "programme", "funeral_details", "post_text",
                 "custom_body")
    if not body:
        body = (payload.get("instructions") or "").strip()

    contact = first("contact", "socials")

    return {
        "headline": headline, "name": name, "sub": sub, "org": org,
        "info": info_line, "extra": extra, "body": body, "contact": contact,
        "photos": [img.get("filename") for img in (payload.get("images") or [])
                   if img.get("filename")][:MAX_IMAGES],
    }


# ---------------------------------------------------------------------------
# Composition helpers
# ---------------------------------------------------------------------------
def _ornament_row(cx: float, y: float, w: float, color: str, count: int = 3) -> list[dict]:
    els = []
    r = w * 0.012
    start = cx - (count * r * 5) / 2
    for i in range(count):
        els.append(ellipse(start + i * r * 5 + r, y, r, r, color))
    return els


def _info_block(elements: list, c: dict, pal: dict, x: float, y: float,
                w: float, max_h: float, size: float, align: str) -> float:
    """Place info lines / extras / contact as plain readable text."""
    cur = y
    avail = max_h
    if c["info"]:
        el = text_el(x, cur, w, avail, c["info"], size, color=pal["ink"],
                     align=align, min_size=size * 0.7)
        if el:
            elements.append(el)
            cur += el["h"] + size * 0.45
            avail = max_h - (cur - y)
    for line in c["extra"][:3]:
        if avail < size * 1.2:
            break
        el = text_el(x, cur, w, avail, line, size * 0.92, color=pal["muted"],
                     align=align, min_size=size * 0.65)
        if el:
            elements.append(el)
            cur += el["h"] + size * 0.3
            avail = max_h - (cur - y)
    if c["contact"] and avail >= size * 1.2:
        el = text_el(x, cur, w, avail, c["contact"], size, weight="700",
                     color=pal["accent"], align=align, min_size=size * 0.65)
        if el:
            elements.append(el)
            cur += el["h"]
    return cur - y


# ---------------------------------------------------------------------------
# The five compositions
# ---------------------------------------------------------------------------
def _comp_hero(ctx: dict) -> list[dict]:
    """Full-bleed photo + bottom-anchored type. The flyer look."""
    W, H, pal, c = ctx["W"], ctx["H"], ctx["pal"], ctx["c"]
    els: list[dict] = []

    if ctx.get("bg"):
        # Accepted AI artwork becomes the full-bleed backdrop, and the
        # customer's own photo is framed on top of it rather than replaced.
        els.append(photo_el(0, 0, W, H, ctx["bg"]))
        els.append(rect(0, H * 0.30, W, H * 0.70, "#04101f", opacity=0.60))
        els.append(rect(0, 0, W, H * 0.34, "#04101f", fill2="#04101f", opacity=0.34))
    elif c["photos"]:
        els.append(photo_el(0, 0, W, H, c["photos"][0]))
        els.append(rect(0, H * 0.30, W, H * 0.70, "#04101f", opacity=0.55))
        els.append(rect(0, 0, W, H * 0.30, "#04101f", fill2="#04101f", opacity=0.30))
    else:
        els.append(rect(0, 0, W, H, pal["bg1"], fill2=pal["bg2"]))
        els.append(ellipse(W * 0.82, H * 0.16, W * 0.34, W * 0.34, pal["accent"], opacity=0.16))
        els.append(ellipse(W * 0.10, H * 0.78, W * 0.30, W * 0.30, pal["accent"], opacity=0.12))

    ink = "#ffffff"
    muted = "#e8edf6"
    accent = "#f2c14e" if pal["ink"].lower().startswith("#f") or pal["ink"] == "#ffffff" else pal["accent"]

    pad = W * 0.08
    max_w = W - pad * 2
    bottom = H - H * 0.06

    # Hero already uses its photo as the backdrop; with an AI backdrop that
    # photo is framed in the quiet upper band so it is still part of the job.
    framed = bool(ctx.get("bg")) and bool(c["photos"])
    if framed:
        d = W * 0.32
        els.append(photo_el(W - d - pad, H * 0.055, d, d * 1.12,
                            c["photos"][0], radius=W * 0.018, border=accent,
                            border_w=W * 0.005))

    # measure bottom-up so the stack never collides
    blocks: list[tuple[str, ...]] = []
    if c["sub"]:
        blocks.append(("sub", c["sub"]))
    if c["name"]:
        blocks.append(("name", c["name"]))
    blocks.append(("headline", c["headline"]))

    sizes = {"headline": W * 0.115, "name": W * 0.145, "sub": W * 0.052}
    # --- adaptive measurement: fit the whole stack inside the usable area ---
    bar_h = W * 0.012
    info_size = W * 0.045
    sizes = {"headline": W * 0.115, "name": W * 0.145, "sub": W * 0.052}
    min_sizes = {"headline": W * 0.05, "name": W * 0.058, "sub": W * 0.03}
    info_floor = W * 0.026
    top_limit = H * 0.44 if framed else H * 0.06
    avail = bottom - top_limit

    heights: dict[str, float] = {}
    for _ in range(14):
        heights = {}
        for key, val in blocks:
            el = text_el(0, 0, max_w, H * 0.5, val, sizes[key],
                         weight="700" if key != "sub" else "400",
                         uppercase=(key == "headline"), min_size=min_sizes[key])
            heights[key] = el["h"] if el else 0
        info_h = _text_height(c["info"], info_size, max_w, "400")
        extra_h = min(H * 0.14, sum(
            _text_height(x, info_size * 0.85, max_w) for x in c["extra"][:3]))
        contact_h = _text_height(c["contact"], info_size, max_w, "700")
        gaps = W * 0.028 + W * 0.05
        if c["headline"]:
            gaps += W * 0.02
        if c["name"]:
            gaps += W * 0.018
        if c["sub"]:
            gaps += W * 0.022
        total = (bar_h + gaps + heights["headline"] + heights.get("name", 0)
                 + heights.get("sub", 0) + info_h + extra_h + contact_h)
        if total <= avail:
            break
        # shrink the least important part first: the info block, then the type
        if info_size > info_floor:
            info_size = max(info_floor, info_size * 0.9)
        else:
            star = all(sizes[k] <= min_sizes[k] * 1.001 for k in sizes)
            if star:
                break
            for k in sizes:
                sizes[k] = max(min_sizes[k], sizes[k] * 0.94)

    start = max(top_limit, bottom - total)
    cur = start

    els.append(rect(pad, cur, W * 0.16, bar_h, accent))
    cur += bar_h + W * 0.028

    el = text_el(pad, cur, max_w, heights["headline"] + 1, c["headline"],
                 sizes["headline"], weight="700", color=ink, uppercase=True,
                 min_size=min_sizes["headline"])
    if el:
        els.append(el)
        cur += el["h"] + W * 0.02
    if c["name"]:
        el = text_el(pad, cur, max_w, heights.get("name", 0) + 1, c["name"],
                     sizes["name"], weight="700", color=accent,
                     min_size=min_sizes["name"])
        if el:
            els.append(el)
            cur += el["h"] + W * 0.018
    if c["sub"]:
        el = text_el(pad, cur, max_w, heights.get("sub", 0) + 1, c["sub"],
                     sizes["sub"], color=muted, min_size=min_sizes["sub"])
        if el:
            els.append(el)
            cur += el["h"] + W * 0.022
    els += _ornament_row(W / 2, cur, W, accent)
    cur += W * 0.05
    _info_block(els, c, {"ink": ink, "muted": muted, "accent": accent},
                pad, cur, max_w, max(0, bottom - cur), info_size, "left")
    return els


def _comp_split(ctx: dict) -> list[dict]:
    """Photo panel + text column with an accent rule."""
    W, H, pal, c = ctx["W"], ctx["H"], ctx["pal"], ctx["c"]
    els: list[dict] = []
    els += _base(ctx)

    wide = W > H
    pad = W * 0.07
    border = W * 0.012

    if c["photos"]:
        if wide:
            pw, ph = W * 0.44, H
            els.append(photo_el(0, 0, pw - border, ph, c["photos"][0]))
            if len(c["photos"]) > 1:
                d = W * 0.13
                els.append(photo_el(pw - d * 0.7, H * 0.5 - d, d, d,
                                    c["photos"][1], shape="circle",
                                    border=pal["accent"], border_w=W * 0.006))
            tx, tw = pw + pad * 0.7, W - pw - pad * 1.6
        else:
            pw, ph = W, H * 0.40
            els.append(photo_el(0, 0, pw, ph, c["photos"][0]))
            if len(c["photos"]) > 1:
                d = W * 0.30
                els.append(photo_el(W - d - pad, ph - d * 0.5, d, d,
                                    c["photos"][1], shape="circle",
                                    border=pal["accent"], border_w=W * 0.007))
            tx, tw = pad, W - pad * 2
            py = ph + pad * 0.8
        py = py if not wide else pad
    else:
        if wide:
            els.append(rect(0, 0, W * 0.05, H, pal["accent"]))
            tx, tw = W * 0.09, W * 0.84
            py = pad * 1.3
        else:
            els.append(rect(0, 0, W, H * 0.05, pal["accent"]))
            tx, tw = pad, W - pad * 2
            py = H * 0.05 + pad * 0.7

    max_h = H - py - pad
    cur = py
    # accent side rule
    els.append(rect(tx, cur, W * 0.008, max_h, pal["accent"]))
    tx2 = tx + W * 0.028
    tw2 = tw - W * 0.03

    if c["headline"]:
        el = text_el(tx2, cur, tw2, max_h * 0.30, c["headline"], W * 0.085,
                     weight="700", color=pal["ink"], uppercase=True,
                     min_size=W * 0.045)
        if el:
            els.append(el)
            cur += el["h"] + W * 0.018
    if c["name"]:
        el = text_el(tx2, cur, tw2, max_h * 0.24, c["name"], W * 0.105,
                     weight="700", color=pal["accent"], min_size=W * 0.055)
        if el:
            els.append(el)
            cur += el["h"] + W * 0.014
    if c["sub"]:
        el = text_el(tx2, cur, tw2, max_h * 0.12, c["sub"], W * 0.048,
                     color=pal["muted"], min_size=W * 0.03)
        if el:
            els.append(el)
            cur += el["h"] + W * 0.02
    if c["org"]:
        el = text_el(tx2, cur, tw2, max_h * 0.10, c["org"], W * 0.044,
                     weight="700", color=pal["muted"], min_size=W * 0.03)
        if el:
            els.append(el)
            cur += el["h"] + W * 0.02
    els.append(rect(tx2, cur, tw2 * 0.45, W * 0.004, pal["accent"]))
    cur += W * 0.028
    cur += _info_block(els, c, pal, tx2, cur, tw2, max_h - (cur - py), W * 0.045, "left")
    if c["body"]:
        avail = max_h - (cur - py) - pad * 0.4
        el = text_el(tx2, cur, tw2, avail, c["body"], W * 0.042, color=pal["ink"],
                     min_size=W * 0.028)
        if el:
            els.append(el)
    return els


def _comp_ornate(ctx: dict) -> list[dict]:
    """Symmetrical framed composition - programmes, certificates, invites."""
    W, H, pal, c = ctx["W"], ctx["H"], ctx["pal"], ctx["c"]
    els: list[dict] = []
    els += _base(ctx)
    accent = pal["accent"]

    m = W * 0.045
    els.append(rect(m, m, W - m * 2, H - m * 2, "transparent",
                    stroke=accent, stroke_w=W * 0.006))
    m2 = m + W * 0.016
    els.append(rect(m2, m2, W - m2 * 2, H - m2 * 2, "transparent",
                    stroke=accent, stroke_w=W * 0.002, opacity=0.7))

    pad = W * 0.10
    max_w = W - pad * 2
    inner_x = pad
    cur = H * 0.11

    els.append(rect(W * 0.5 - W * 0.10, cur, W * 0.20, W * 0.005, accent))
    cur += W * 0.035

    for text, size, weight, color, upper in (
        (c["sub"], W * 0.045, "400", pal["muted"], True),
        (c["headline"], W * 0.088, "700", pal["ink"], True),
        (c["name"], W * 0.115, "700", accent, False),
        (c["org"], W * 0.05, "700", pal["ink"], False),
    ):
        if not text:
            continue
        el = text_el(inner_x, cur, max_w, H * 0.30, text, size, weight=weight,
                     color=color, align="center", uppercase=upper,
                     min_size=size * 0.55)
        if el:
            els.append(el)
            cur += el["h"] + W * 0.02
        if cur > H * 0.72:
            break

    cur += W * 0.01
    els += _ornament_row(W / 2, cur, W, accent)
    cur += W * 0.045

    if cur < H * 0.70:
        cur += _info_block(els, c, pal, inner_x, cur, max_w, H * 0.70 - cur,
                           W * 0.044, "center")
        if c["body"]:
            avail = H * 0.84 - cur
            if avail > W * 0.05:
                el = text_el(inner_x, cur, max_w, avail, c["body"], W * 0.04,
                             color=pal["ink"], align="center", italic=True,
                             min_size=W * 0.026)
                if el:
                    els.append(el)

    # circular portraits along the bottom, inside the frame
    photos = c["photos"][:3]
    if photos:
        d = min(W * 0.24, H * 0.20)
        gap = W * 0.05
        total = len(photos) * d + (len(photos) - 1) * gap
        x = (W - total) / 2
        for fn in photos:
            els.append(photo_el(x, H - m2 - d - W * 0.045, d, d, fn,
                                shape="circle", border=accent,
                                border_w=W * 0.007))
            x += d + gap
    return els


def _comp_strip(ctx: dict) -> list[dict]:
    """Headline band, photo strip, then a tight information row."""
    W, H, pal, c = ctx["W"], ctx["H"], ctx["pal"], ctx["c"]
    els: list[dict] = []
    els += _base(ctx)
    accent = pal["accent"]
    pad = W * 0.075

    wide = W / H > 1.6
    cur = H * 0.07
    els.append(rect(0, 0, W, H * 0.015, accent))

    headline_h = H * 0.26 if wide else H * 0.20
    el = text_el(pad, cur, W - pad * 2, headline_h, c["headline"], W * 0.095,
                 weight="700", color=pal["ink"], uppercase=True, align="left",
                 min_size=W * 0.05, valign="middle")
    if el:
        els.append(el)
        cur = el["y"] + el["h"] + W * 0.02
    if c["name"]:
        el = text_el(pad, cur, W - pad * 2, H * 0.14, c["name"], W * 0.12,
                     weight="700", color=accent, align="left", min_size=W * 0.06)
        if el:
            els.append(el)
            cur = el["y"] + el["h"] + W * 0.02
    if c["sub"] or c["org"]:
        el = text_el(pad, cur, W - pad * 2, H * 0.09,
                     " — ".join([x for x in (c["sub"], c["org"]) if x]),
                     W * 0.048, color=pal["muted"], align="left",
                     min_size=W * 0.032)
        if el:
            els.append(el)
            cur = el["y"] + el["h"] + W * 0.03

    # photo strip fills the middle
    remaining_top = cur + W * 0.03
    remaining_bottom = H * 0.74
    strip_h = max(H * 0.20, remaining_bottom - remaining_top)
    if c["photos"]:
        n = len(c["photos"])
        gap = W * 0.02
        if n == 1:
            els.append(photo_el(pad, remaining_top, W - pad * 2, strip_h,
                                c["photos"][0]))
        else:
            cols = min(n, 3)
            cw = (W - pad * 2 - gap * (cols - 1)) / cols
            for i, fn in enumerate(c["photos"][:cols]):
                els.append(photo_el(pad + i * (cw + gap), remaining_top,
                                    cw, strip_h, fn, radius=W * 0.012))
    else:
        els.append(rect(pad, remaining_top, W - pad * 2, strip_h,
                        accent, fill2=accent, grad_dir="to right", opacity=0.14))
        els.append(rect(pad, remaining_top, W - pad * 2, strip_h, "transparent",
                        stroke=accent, stroke_w=W * 0.004, opacity=0.6))
    cur = remaining_top + strip_h + W * 0.03

    # bottom information band - placed with measured heights so it cannot overlap
    band_y = H * 0.80
    els.append(rect(0, band_y, W, H - band_y, pal["ink"], opacity=0.92))
    band_ink = pal["bg1"] if pal["ink"] != "#ffffff" else "#0b2545"
    inner = W - pad * 2
    if c["body"] and cur < band_y - W * 0.02:
        el = text_el(pad, cur, inner, band_y - cur - W * 0.03, c["body"],
                     W * 0.04, color=pal["ink"], min_size=W * 0.026)
        if el:
            els.append(el)

    band_top = band_y + H * 0.026
    band_avail = max(0, H - band_top - H * 0.03)
    info = "  •  ".join(x for x in [c["info"]] + c["extra"][:2] if x)
    info_el = None
    if info:
        info_el = text_el(pad, band_top, inner, band_avail * 0.60, info,
                          W * 0.042, weight="700", color=band_ink,
                          min_size=W * 0.026)
        if info_el:
            els.append(info_el)
    next_y = band_top + (info_el["h"] + H * 0.014 if info_el else 0)
    if c["contact"] and next_y < band_top + band_avail:
        el = text_el(pad, next_y, inner, band_top + band_avail - next_y,
                     c["contact"], W * 0.038, color=accent, min_size=W * 0.024)
        if el:
            els.append(el)
    return els


def _comp_grid(ctx: dict) -> list[dict]:
    """Airy light layout with a photo collage and a left-aligned type stack."""
    W, H, pal, c = ctx["W"], ctx["H"], ctx["pal"], ctx["c"]
    els: list[dict] = []
    accent = pal["accent"]
    els += _base(ctx)
    pad = W * 0.075
    inner = W - pad * 2

    cur = H * 0.07
    if c["headline"]:
        el = text_el(pad, cur, inner, H * 0.20, c["headline"], W * 0.10,
                     weight="800", color=pal["ink"], uppercase=True,
                     min_size=W * 0.055)
        if el:
            els.append(el)
            cur = el["y"] + el["h"] + W * 0.015
    if c["name"]:
        el = text_el(pad, cur, inner, H * 0.15, c["name"], W * 0.125,
                     weight="700", color=accent, min_size=W * 0.065)
        if el:
            els.append(el)
            cur = el["y"] + el["h"] + W * 0.012
    if c["sub"] or c["org"]:
        el = text_el(pad, cur, inner, H * 0.08,
                     " — ".join([x for x in (c["sub"], c["org"]) if x]),
                     W * 0.048, color=pal["muted"], min_size=W * 0.032)
        if el:
            els.append(el)
            cur = el["y"] + el["h"] + W * 0.02

    els.append(rect(pad, cur, W * 0.14, W * 0.008, accent))
    cur += W * 0.028

    # collage
    top = cur
    bottom_reserve = H * 0.30
    collage_h = max(H * 0.22, H - bottom_reserve - top)
    if c["photos"]:
        n = len(c["photos"])
        gap = W * 0.022
        if n == 1:
            els.append(photo_el(pad, top, inner, collage_h, c["photos"][0],
                                radius=W * 0.015, border=accent,
                                border_w=W * 0.005))
        else:
            big_w = inner * 0.60
            els.append(photo_el(pad, top, big_w, collage_h, c["photos"][0],
                                radius=W * 0.015))
            sx = pad + big_w + gap
            sw = inner - big_w - gap
            small = c["photos"][1:3]
            sh = (collage_h - gap * (len(small) - 1)) / max(1, len(small))
            for i, fn in enumerate(small):
                els.append(photo_el(sx, top + i * (sh + gap), sw, sh, fn,
                                    radius=W * 0.015, border=accent,
                                    border_w=W * 0.004))
        cur = top + collage_h + W * 0.035
    else:
        els.append(rect(pad, top, inner, collage_h * 0.7, accent,
                        fill2=accent, grad_dir="to right", opacity=0.12))
        cur = top + collage_h * 0.7 + W * 0.035

    info_top = cur
    info_max = H - info_top - H * 0.06
    cur += _info_block(els, c, pal, pad, info_top, inner, info_max * 0.62,
                       W * 0.044, "left")
    if c["body"]:
        el = text_el(pad, cur, inner, H - cur - H * 0.05, c["body"], W * 0.04,
                     color=pal["ink"], min_size=W * 0.026)
        if el:
            els.append(el)
    return els


COMPOSITIONS = {
    "hero": _comp_hero,
    "split": _comp_split,
    "ornate": _comp_ornate,
    "strip": _comp_strip,
    "grid": _comp_grid,
}

DEFAULT_STYLE = {
    "birthday": "hero", "anniversary": "ornate", "wedding": "hero",
    "retirement": "split", "church-programme": "ornate", "funeral": "hero",
    "graduation": "grid", "business-advert": "split", "product-advert": "grid",
    "event": "strip", "social-media": "hero", "invitation": "ornate",
    "certificate": "ornate", "banner": "strip", "custom": "grid",
}


def build_layout(payload: dict) -> dict:
    category = catalog.get_category(payload.get("category")) or catalog.CATEGORIES[0]
    pal = catalog.get_theme(payload.get("theme") or category.theme)
    aspect = catalog.ASPECTS.get(category.aspect, 0.7071)
    style = payload.get("style")
    if style not in COMPOSITIONS:
        style = DEFAULT_STYLE.get(category.slug, "grid")

    # An accepted AI backdrop (payload['ai']['background']) is painted under the
    # composition. It is a *backdrop only*: the engine still emits every text
    # and photo element, so no customer detail can be changed or dropped by the
    # image model. See docs/DECISIONS.md.
    ai = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
    bg = str((ai or {}).get("background") or "")

    W = EXPORT_WIDTH
    H = int(round(W / aspect))
    c = assemble(category, payload)
    ctx = {"W": W, "H": H, "pal": pal, "c": c, "category": category,
           "style": style, "bg": bg}
    elements = COMPOSITIONS[style](ctx)
    elements = [e for e in elements if e]

    return {
        "aspect": aspect, "width": W, "height": H, "template": style,
        "palette": pal, "elements": elements,
        "ai_background": bg,
        "category": {"slug": category.slug, "name": category.name},
    }


def render_design(payload: dict) -> dict:
    """Public entry point used by the route, the generation service and tests."""
    return build_layout(payload)
