"""1.57.64 (user: "Ansicht besser … den Kreis mit den Symbolen wie im Spiel" → "gefällt mir alles, nur die Logos näher
ans Spiel"): the counted points of the score events (scorecount) as a picture for the element Infos.

Three looks (setting ``overlay.score_style``): ``rings`` – one ring per category like the game's score events, its
icon inside, the arc red as far as the category is full (10 000 points), the value below; ``bars`` – a row per
category: icon in a small ring, a bar, the value; ``line`` – one line, a small ring before each value. A full category
is a closed ring in gold with "MAX".

The icons are drawn here (white, rough like the game's emblems: cracked skull, thorn knot, stag skull, hook – gear,
heart, open hand, flame); not the game's pictures, which belong to Behaviour and do not go into this public repo.
Every look is as big as its widest values ("00.0k"), so a new value never resizes the card. Pure (Pillow), cached.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .scorecount import CAP, SHORT, line
from .i18n import N_
from .scoreevents import CATEGORIES

STYLES = ("rings", "bars", "line")
STYLE_LABELS = (("rings", N_("Ringe mit Symbolen")), ("bars", N_("Balken")), ("line", N_("Eine Zeile")))
DEFAULT_STYLE = "rings"

RED = (214, 32, 38, 255)          # the game's arc
TRACK = (255, 255, 255, 46)       # the ring's empty part
PLATE = (14, 14, 17, 205)         # inside the ring (readable on any game picture)
WHITE = (240, 240, 240, 255)
GREY = (190, 190, 196, 255)
GOLD = (236, 176, 60, 255)        # a full category
SS = 4                            # supersampling of the drawings


# ------------------------------------------------------------------ icons (drawn on a 100×100 field)
def _skull(d):                     # brutality: a cracked skull
    d.ellipse((22, 10, 78, 66), fill=255)
    d.rounded_rectangle((33, 52, 67, 86), 6, fill=255)
    d.ellipse((31, 34, 47, 52), fill=0)
    d.ellipse((53, 34, 69, 52), fill=0)
    d.polygon([(50, 52), (45, 63), (55, 63)], fill=0)
    for x in (41, 50, 59):
        d.line((x, 72, x, 86), fill=0, width=3)
    d.line([(50, 10), (46, 20), (54, 27), (47, 34)], fill=0, width=4)


def _knot(d):                      # deviousness: a knot of thorns
    for a in (0, 120, 240):
        r = math.radians(a)
        cx, cy = 50 + 15 * math.cos(r), 50 + 15 * math.sin(r)
        d.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), outline=255, width=8)
    for a in range(0, 360, 40):
        r = math.radians(a)
        x0, y0 = 50 + 36 * math.cos(r), 50 + 36 * math.sin(r)
        x1, y1 = 50 + 46 * math.cos(r + 0.25), 50 + 46 * math.sin(r + 0.25)
        d.line((x0, y0, x1, y1), fill=255, width=5)


def _stag(d):                      # hunter: a stag skull with antlers
    d.polygon([(38, 34), (62, 34), (60, 62), (54, 90), (46, 90), (40, 62)], fill=255)
    d.ellipse((40, 44, 47, 52), fill=0)
    d.ellipse((53, 44, 60, 52), fill=0)
    for s in (-1, 1):
        x = 50 + s * 10
        d.line([(x, 36), (50 + s * 26, 18), (50 + s * 40, 8)], fill=255, width=6)
        d.line([(50 + s * 26, 18), (50 + s * 22, 4)], fill=255, width=5)
        d.line([(50 + s * 33, 13), (50 + s * 44, 22)], fill=255, width=5)
        d.polygon([(50 + s * 11, 38), (50 + s * 24, 34), (50 + s * 13, 46)], fill=255)


def _hook(d):                      # sacrifice: the meat hook
    d.ellipse((42, 4, 58, 20), outline=255, width=6)
    d.line((50, 19, 50, 56), fill=255, width=9)
    d.arc((24, 38, 72, 88), 0, 180, fill=255, width=10)
    d.arc((24, 38, 72, 88), 180, 200, fill=255, width=10)
    d.polygon([(19, 58), (31, 52), (26, 68)], fill=255)


def _gear(d):                      # objective: a gear
    for i in range(8):
        r = math.radians(i * 45)
        d.line((50, 50, 50 + 42 * math.cos(r), 50 + 42 * math.sin(r)), fill=255, width=14)
    d.ellipse((18, 18, 82, 82), fill=255)
    d.ellipse((38, 38, 62, 62), fill=0)


def _heart(d):                     # survival: a heart with a crack
    d.ellipse((16, 18, 52, 54), fill=255)
    d.ellipse((48, 18, 84, 54), fill=255)
    d.polygon([(19, 44), (81, 44), (50, 86)], fill=255)
    d.line([(52, 22), (45, 40), (55, 52), (48, 66)], fill=0, width=4)


def _hand(d):                      # altruism: an open hand
    d.rounded_rectangle((30, 46, 74, 90), 12, fill=255)
    for x, top in ((31, 20), (42, 12), (53, 14), (64, 22)):
        d.rounded_rectangle((x, top, x + 9, 56), 4, fill=255)
    d.polygon([(30, 62), (14, 44), (20, 38), (36, 54)], fill=255)


def _flame(d):                     # boldness: a flame
    d.polygon([(50, 6), (66, 30), (78, 52), (74, 74), (60, 90), (40, 90), (26, 74), (22, 52), (34, 34),
               (40, 50), (46, 30)], fill=255)
    d.polygon([(50, 50), (60, 64), (58, 80), (50, 86), (42, 80), (40, 66)], fill=0)


ICONS = {"brutality": _skull, "deviousness": _knot, "hunter": _stag, "sacrifice": _hook,
         "objective": _gear, "survival": _heart, "altruism": _hand, "boldness": _flame}


LEARNED: dict = {}                # 1.57.67: category -> "L" picture taken from the user's own screen (scoreicons)
REV = [0]                         # counts set_learned – part of for_overlay's value, so every cache sees a new icon
LEARNED_SHARE = 0.74              # a learned icon fills this share of its ring (the part inside the ring), a drawn
DRAWN_SHARE = 0.56                # one this


def set_learned(pictures: dict) -> None:
    """The game's own icons seen so far ({category: "L" picture}); the drawn ones stand in for the rest."""
    LEARNED.clear()
    LEARNED.update(pictures or {})
    REV[0] += 1
    icon.cache_clear()
    picture.cache_clear()


@lru_cache(maxsize=64)
def icon(category: str, size: int, colour=WHITE) -> Image.Image:
    """The white icon of ``category``, ``size`` px square – the game's own once it was seen (``LEARNED``), else the
    drawing: rough edges and a few worn specks like the game's."""
    seen = LEARNED.get(category)
    if seen is not None:
        out = Image.new("RGBA", (size, size), colour[:3] + (0,))
        out.putalpha(seen.resize((size, size), Image.LANCZOS).point(lambda v: v * colour[3] // 255))
        return out
    big = 100 * SS
    mask = Image.new("L", (100, 100), 0)
    ICONS.get(category, _skull)(ImageDraw.Draw(mask))
    mask = mask.resize((big, big), Image.BILINEAR)
    rnd = random.Random(category)                         # the same specks every time (cached, tests)
    wear = Image.new("L", (big, big), 255)
    dw = ImageDraw.Draw(wear)
    for _ in range(22):                                   # worn specks and short scratches
        x, y, r = rnd.uniform(0, big), rnd.uniform(0, big), rnd.uniform(0.5 * SS, 1.4 * SS)
        dw.ellipse((x - r, y - r, x + r, y + r), fill=0)
    for _ in range(6):
        x, y, a = rnd.uniform(0, big), rnd.uniform(0, big), rnd.uniform(0, math.pi)
        n = rnd.uniform(6, 14) * SS
        dw.line((x, y, x + n * math.cos(a), y + n * math.sin(a)), fill=0, width=max(1, SS))
    mask = ImageChops.multiply(mask, wear.filter(ImageFilter.GaussianBlur(SS * 0.6)))
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), colour[:3] + (0,))
    out.putalpha(mask.point(lambda v: v * colour[3] // 255))
    return out


# ------------------------------------------------------------------ rings and the looks
def items(totals: dict, full=()) -> tuple:
    """(category, points, full) in the game's order, only categories counted."""
    return tuple((c, int(totals[c]), c in full or totals[c] >= CAP) for c in CATEGORIES if c in totals)


def for_overlay(totals: dict, full=(), style: str = DEFAULT_STYLE) -> tuple:
    """What the overlay's ``set_score`` gets: (text, widest text, items, look) – the texts as before (scorecount.line),
    the items and the look for ``picture``; () without points."""
    text = line(totals, full)
    if not text:
        return ()
    return tuple(text) + (items(totals, full), style if style in STYLES else DEFAULT_STYLE, REV[0])


def of(score) -> Image.Image | None:
    """The picture of a ``for_overlay`` value at unit 1 – None for the plain text form (text, widest) or nothing."""
    score = tuple(score or ())
    return picture(score[2], score[3], 1.0, rev(score)) if len(score) >= 4 and score[2] else None


def rev(score) -> int:
    """The icons' revision a ``for_overlay`` value was made with (0 for older, shorter values)."""
    return score[4] if len(score) > 4 else 0


def value(points: int, full: bool) -> str:
    return "MAX" if full else f"{points / 1000:.1f}k"


def _ring(size: int, share: float, full: bool, width: float, plate: bool = True, glyph: str = "") -> Image.Image:
    big = size * SS
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(SS, int(width * SS))
    box = (w // 2, w // 2, big - 1 - w // 2, big - 1 - w // 2)
    if plate:
        d.ellipse(box, fill=PLATE)
    d.ellipse(box, outline=TRACK, width=w)
    if full:
        d.ellipse(box, outline=GOLD, width=w)
    elif share > 0:
        d.arc(box, -90, -90 + 360 * min(1.0, share), fill=RED, width=w)
    im = im.resize((size, size), Image.LANCZOS)
    if glyph:
        share = LEARNED_SHARE if glyph in LEARNED else DRAWN_SHARE
        g = icon(glyph, max(4, int(size * share)), GOLD if full else WHITE)
        im.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
    return im


def _font(u: float, weight="SemiBold", px=14):
    from .skin import inter
    return inter(weight, max(8, int(px * u)))


def _text(im, xy, text, font, fill):
    d = ImageDraw.Draw(im)
    x, y = xy
    d.text((x + max(1, font.size // 14), y + max(1, font.size // 14)), text, font=font, fill=(0, 0, 0, 200))
    d.text((x, y), text, font=font, fill=fill)


def _w(font, text) -> int:
    return int(math.ceil(font.getlength(text)))


@lru_cache(maxsize=32)
def picture(entries: tuple, style: str = DEFAULT_STYLE, u: float = 1.0, rev: int = 0) -> Image.Image | None:
    """The look ``style`` of ``entries`` (``items``) at unit ``u`` (1.0 = the size of a 14-px text line). ``rev``:
    the icons' revision – only a part of the cache key."""
    if not entries:
        return None
    style = style if style in STYLES else DEFAULT_STYLE
    u = max(0.5, float(u))
    vf = _font(u, "SemiBold", 13)
    widest = max(_w(vf, "00.0k"), _w(vf, "MAX"))
    if style == "rings":
        d_ring, gap = int(46 * u), int(8 * u)
        col = max(d_ring, widest)
        th = vf.size + int(4 * u)
        im = Image.new("RGBA", (len(entries) * col + (len(entries) - 1) * gap, d_ring + int(4 * u) + th), (0, 0, 0, 0))
        for i, (cat, pts, full) in enumerate(entries):
            x = i * (col + gap)
            im.alpha_composite(_ring(d_ring, pts / CAP, full, 4.2 * u, glyph=cat), (x + (col - d_ring) // 2, 0))
            t = value(pts, full)
            _text(im, (x + (col - _w(vf, t)) // 2, d_ring + int(3 * u)), t, vf, GOLD if full else WHITE)
        return im
    if style == "bars":
        d_ring, bar_w, bar_h, row_gap = int(26 * u), int(110 * u), max(3, int(6 * u)), int(5 * u)
        gap = int(8 * u)
        w = d_ring + gap + bar_w + gap + widest
        im = Image.new("RGBA", (w, len(entries) * d_ring + (len(entries) - 1) * row_gap), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i, (cat, pts, full) in enumerate(entries):
            y = i * (d_ring + row_gap)
            im.alpha_composite(_ring(d_ring, pts / CAP, full, 2.4 * u, glyph=cat), (0, y))
            bx, by = d_ring + gap, y + (d_ring - bar_h) // 2
            d.rounded_rectangle((bx, by, bx + bar_w, by + bar_h), bar_h // 2, fill=(255, 255, 255, 40))
            fill_w = bar_w if full else int(bar_w * min(1.0, pts / CAP))
            if fill_w > bar_h:
                d.rounded_rectangle((bx, by, bx + fill_w, by + bar_h), bar_h // 2, fill=GOLD if full else RED)
            t = value(pts, full)
            _text(im, (w - _w(vf, t), y + (d_ring - vf.size) // 2 - int(2 * u)), t, vf, GOLD if full else WHITE)
        return im
    # line: a small ring before each "BRU 4.3k"
    lf = _font(u, "Medium", 13)
    d_ring, gap, sep = int(15 * u), int(5 * u), int(12 * u)
    cells = []
    for cat, pts, full in entries:
        label = f"{SHORT.get(cat, cat[:3].upper())} "
        cells.append((cat, pts, full, label, d_ring + gap + _w(lf, label) + widest))
    w = sum(c[4] for c in cells) + sep * (len(cells) - 1)
    h = max(d_ring, lf.size + int(4 * u))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for cat, pts, full, label, cw in cells:
        im.alpha_composite(_ring(d_ring, pts / CAP, full, 2.6 * u, plate=False), (x, (h - d_ring) // 2))
        _text(im, (x + d_ring + gap, (h - lf.size) // 2 - int(2 * u)), label + value(pts, full), lf,
              GOLD if full else WHITE)
        x += cw + sep
    return im
