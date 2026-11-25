"""Score event tracker, step 2 (1.57.53): find and read the score events DBD shows top right in a match.

Each event is a row: the event's name in white italic capitals, the points in red below it ("+250" or "MAX"),
right-aligned, and the category icon in a ring right of both. The rows are found from the pixels alone
(``find_rows``: a white word with red glyphs right below it) and read with the program's own recognition model
(``read_rows``): the name as free text (perks and killers bring their own events – there is no closed list), the
points with an alphabet of digits only. One look may misread a row (events slide in and fade out, recordings
smear them); the counting step decides over several looks.

Step 3 (1.57.54): the category of each row from its icon (``icon_category``) – not from the name: the same event
counts for different categories (a heal of oneself is Survival, of another Altruism; a good skill check is
Objective, Survival or Altruism by what it is done for). Eight icons, compared with the templates in
``score_icons.png`` (made by ``tools/score_icons.py`` from own recordings); an icon that is not clearly one of
them (sliding in, smeared, a light background) gives None.

Works on ``worker.score_part`` – the box of the 16:9 picture, any size (lengths scale with its height).
Pure: numpy/cv2 and a ``Recognizer``; nothing is saved or sent.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

BOX_H = 634                # height of worker.SCORE_BOX in a 1440-high picture – the lengths below are for it
WORD_H = (14, 45)          # height of a name (dilated), px at BOX_H
WORD_MIN_W = 25
WORD_MIN_RATIO = 1.3       # names are wide; the white icon in its ring is not
MIN_GLYPHS = 2             # "+7" has two
POINTS_RE = re.compile(r"\+(\d{1,5})")
MAX_TEXT = "MAX"
NAME_MIN_LETTERS = 2
# italic: the points end about one name height left of the name's end (measured 1.1–1.2 h); the ring's red arc
# starts right of that
RIGHT_GAP = 0.6
LEFT_REACH = 2.5           # short names ("HIT") are narrower than their points: look left of the name too

# 1.57.54: the four categories with a cap of each role, in the order of the template picture
KILLER = ("brutality", "deviousness", "hunter", "sacrifice")
SURVIVOR = ("objective", "survival", "altruism", "boldness")
CATEGORIES = KILLER + SURVIVOR
ICONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "score_icons.png")
# the ring's middle from the name's box (x1, y0, height h; measured on own recordings) and the cut around it
ICON_DX, ICON_DY = 1.5, 0.8
ICON_HALF_W, ICON_HALF_H = 1.7, 1.3
ICON_CUT = (68, 52)        # the cut, scaled to this (w, h)
ICON_FEATURE = (34, 26)    # the compared picture (w, h)
ICON_SHIFT = 3             # tried shifts (px of the feature) – the icon slides in, the ring is tilted
ICON_MIN = 0.4             # correlation with the best template …
ICON_MARGIN = 0.1          # … and its lead over the second (held-out rounds: 97 % kept, 99.9 % of them right)


@dataclass
class Row:
    """One score event in one look. ``word``/``glyphs`` are boxes in the part (x0, y0, x1, y1) / (x, y, w, h);
    ``name`` the name as read (upper case, may be cut while it slides in), ``points`` the points (None: not
    readable), ``capped`` = "MAX" (the category is full – the event gives nothing)."""
    word: tuple
    glyphs: list = field(default_factory=list)
    name: str = ""
    points: int | None = None
    capped: bool = False
    raw: str = ""
    category: str | None = None

    @property
    def readable(self) -> bool:
        return sum(c.isalpha() for c in self.name) >= NAME_MIN_LETTERS and (self.capped or self.points is not None)


def _masks(part):
    b, g, r = (part[:, :, i].astype(np.int16) for i in range(3))
    white = (b > 170) & (g > 170) & (r > 170) & (np.abs(r - b) < 40)
    red = (r > 140) & (r - np.maximum(g, b) > 80)
    return white.astype(np.uint8), red.astype(np.uint8)


def _glyphs(red, x0, y0, x1, y1, h_word):
    """Red components in the box shaped like characters (x, y, w, h) – not the long thin streaks of the game's red
    lights; touching digits (one wide component) are kept when they are tall and filled enough."""
    if x1 <= x0 or y1 <= y0:
        return []
    n, _lab, st, _ = cv2.connectedComponentsWithStats(red[y0:y1, x0:x1], connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a < 6 or h > 1.1 * h_word or h < 0.25 * h_word or w > 4.5 * h_word:
            continue
        if w > 1.6 * h_word and (h < 0.45 * h_word or a < 0.18 * w * h):
            continue
        out.append((x0 + x, y0 + y, w, h))
    return out


def find_rows(part) -> list[Row]:
    """The score event rows in ``part`` (BGR), top to bottom – without reading them."""
    if part is None or part.ndim != 3 or not part.size:
        return []
    s = part.shape[0] / BOX_H
    white, red = _masks(part)
    kw, kh = max(3, round(15 * s)), max(1, round(3 * s))
    blob = cv2.dilate(white, cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh)))
    n, _lab, st, _ = cv2.connectedComponentsWithStats(blob)
    rows = []
    for i in range(1, n):
        x, y, w, h, _a = (int(v) for v in st[i])
        if not (WORD_H[0] * s <= h <= WORD_H[1] * s and w >= WORD_MIN_W * s and w / h >= WORD_MIN_RATIO):
            continue
        gl = _glyphs(red, max(0, x - int(LEFT_REACH * h)), y + h - max(1, round(3 * s)), min(red.shape[1], x + w + 4),
                     min(red.shape[0], y + 2 * h), h)
        if len(gl) < MIN_GLYPHS:
            continue
        mids = np.array([g[1] + g[3] / 2 for g in gl])
        m = float(np.median(mids))
        gl = sorted(g for g, mm in zip(gl, mids) if abs(mm - m) < 0.35 * h)      # one line
        # the red arc of the ring starts right of the points: nothing past the name's end, no glyph after a gap
        gl = [g for g in gl if g[0] + g[2] <= x + w - RIGHT_GAP * h]
        while len(gl) >= 2 and gl[-1][0] - (gl[-2][0] + gl[-2][2]) > 0.45 * h:
            gl.pop()
        if len(gl) < MIN_GLYPHS or max(g[0] + g[2] for g in gl) < x + w - 2.2 * h:
            continue                                     # points are right-aligned under the name
        rows.append(Row(word=(x, y, x + w, y + h), glyphs=gl))
    rows.sort(key=lambda r: r.word[1])
    return rows


def _keep(rec, chars):
    cache = rec.__dict__.setdefault("_score_keep", {})
    if chars not in cache:
        cache[chars] = np.array([i for i, c in enumerate(rec.chars) if i == 0 or c in chars])
    return cache[chars]


def _decode(rec, probs, chars) -> str:
    """Greedy CTC decoding restricted to ``chars`` (and blank)."""
    if len(probs) == 0:
        return ""
    keep = _keep(rec, chars)
    idx = probs[:, keep].argmax(1)
    res, prev = [], -1
    for i in idx:
        if i != prev and i != 0:
            res.append(rec.chars[keep[i]])
        prev = i
    return "".join(res)


def _ink(part, gl, s, pad=10):
    """The glyphs as dark ink on white, twice the size – the recognition model reads red on a busy picture badly."""
    m = max(1, round(2 * s))
    x0, y0 = max(0, min(g[0] for g in gl) - m), max(0, min(g[1] for g in gl) - m)
    x1, y1 = max(g[0] + g[2] for g in gl) + m, max(g[1] + g[3] for g in gl) + m
    sub = part[y0:y1, x0:x1].astype(np.int16)
    redness = np.clip(sub[:, :, 2] - np.maximum(sub[:, :, 1], sub[:, :, 0]), 0, 255).astype(np.float32)
    redness = np.clip(redness * 255.0 / max(60.0, float(redness.max())), 0, 255).astype(np.uint8)
    out = cv2.copyMakeBorder(255 - redness, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    f = 2.0 / s if s > 0 else 2.0
    out = cv2.resize(out, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def parse_points(text: str):
    """(points, capped) from a reading: "+250" → (250, False), "MAX" → (None, True), else (None, False)."""
    if text == MAX_TEXT:
        return None, True
    m = POINTS_RE.fullmatch(text)
    return (int(m.group(1)), False) if m else (None, False)


def _after_plus(rec, probs) -> int:
    """First frame after the "+": the best path of the grammar blank* "+"+ (digit | blank)* (Viterbi over three
    states). Points always start with a "+", which greedy decoding drops or takes for a 4 or a 1; cutting it off
    the picture took the left of the first digit with it (3 → 7)."""
    t_n = len(probs)
    if t_n == 0:
        return 0
    lp = np.log(np.clip(probs, 1e-12, 1.0))
    plus = rec.chars.index("+")
    digits = [rec.chars.index(c) for c in "0123456789"]
    after = np.maximum(lp[:, 0], lp[:, digits].max(1))
    v = np.full((t_n, 3), -np.inf)
    back = np.zeros((t_n, 3), np.int8)
    v[0, 0], v[0, 1] = lp[0, 0], lp[0, plus]
    for t in range(1, t_n):
        v[t, 0] = v[t - 1, 0] + lp[t, 0]
        j = 0 if v[t - 1, 0] >= v[t - 1, 1] else 1
        v[t, 1], back[t, 1] = v[t - 1, j] + lp[t, plus], j
        j = 1 if v[t - 1, 1] >= v[t - 1, 2] else 2
        v[t, 2], back[t, 2] = v[t - 1, j] + after[t], j
    state = 2 if v[-1, 2] >= v[-1, 1] else 1
    start = t_n
    for t in range(t_n - 1, -1, -1):
        if state == 2:
            start = t
        state = back[t, state] if t else 0
    return start


def read_points(rec, part, gl, s=1.0) -> str:
    """The points as text: "MAX", "+250", or "+" when no digit was read."""
    probs = rec.probs(_ink(part, gl, s))
    whole = _decode(rec, probs, "+0123456789MAX")
    if "M" in whole and "X" in whole:
        return MAX_TEXT
    return "+" + _decode(rec, probs[_after_plus(rec, probs):], "0123456789")


def read_name(rec, part, word, s=1.0) -> str:
    x0, y0, x1, y1 = word
    p = max(1, round(6 * s))
    sub = part[max(0, y0 - p):y1 + p, max(0, x0 - p):x1 + p]
    return rec.text(rec.probs(sub)).upper().strip()


def icon_cut(part, row):
    """The icon beside ``row`` scaled to ICON_CUT – None when it reaches out of the part (it slides in)."""
    x0, y0, x1, y1 = row.word
    h = y1 - y0
    cx, cy = x1 + ICON_DX * h, y0 + ICON_DY * h
    a, b = int(cx - ICON_HALF_W * h), int(cy - ICON_HALF_H * h)
    w, hh = int(2 * ICON_HALF_W * h), int(2 * ICON_HALF_H * h)
    if a < 0 or b < 0 or a + w > part.shape[1] or b + hh > part.shape[0] or w < 8 or hh < 8:
        return None
    return cv2.resize(part[b:b + hh, a:a + w], ICON_CUT, interpolation=cv2.INTER_AREA)


def icon_feature(cut):
    """Grey levels of the pale, unsaturated pixels (the drawing; not the red arc) inside the ring, minus their
    surroundings, blurred and normalised – compared by correlation."""
    hsv = cv2.cvtColor(cut, cv2.COLOR_BGR2HSV)
    h, w = cut.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inner = (((xx - w / 2) / (w * 0.30)) ** 2 + ((yy - h / 2) / (h * 0.36)) ** 2 <= 1).astype(np.float32)
    g = hsv[:, :, 2].astype(np.float32) * (hsv[:, :, 1] < 90)
    img = cv2.GaussianBlur((g - cv2.GaussianBlur(g, (0, 0), 4)) * inner, (0, 0), 1.2)
    v = cv2.resize(img, ICON_FEATURE, interpolation=cv2.INTER_AREA)
    v -= v.mean()
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


_TEMPLATES = []


def templates():
    """The eight templates (CATEGORIES order) from ICONS_FILE: one row of tiles, stored as 128 ± 127 · value / max."""
    if not _TEMPLATES:
        pic = cv2.imread(ICONS_FILE, cv2.IMREAD_GRAYSCALE)
        if pic is None:
            raise FileNotFoundError(ICONS_FILE)
        fw, fh = ICON_FEATURE
        out = []
        for i in range(len(CATEGORIES)):
            t = pic[:fh, i * fw:(i + 1) * fw].astype(np.float32) - 128.0
            t -= t.mean()
            out.append(t / max(1e-6, float(np.linalg.norm(t))))
        _TEMPLATES.append(np.array(out))
    return _TEMPLATES[0]


def save_templates(path, temps):
    """``templates`` written as ICONS_FILE (lossless PNG) – for tools/score_icons.py."""
    tiles = []
    for t in temps:
        m = float(np.abs(t).max()) or 1.0
        tiles.append(np.clip(np.round(128 + 127 * t / m), 0, 255).astype(np.uint8))
    cv2.imwrite(path, np.hstack(tiles))


def icon_scores(feature, temps=None):
    """Best correlation of ``feature`` with each template over shifts of up to ICON_SHIFT."""
    temps = templates() if temps is None else temps
    k = ICON_SHIFT
    padded = np.pad(feature, k)
    fh, fw = feature.shape
    best = np.full(len(temps), -1.0)
    for dy in range(2 * k + 1):
        for dx in range(2 * k + 1):
            best = np.maximum(best, temps.reshape(len(temps), -1) @ padded[dy:dy + fh, dx:dx + fw].ravel())
    return best


def icon_category(part, row, temps=None):
    """(category, score, lead) of the icon beside ``row`` – category None when unsure or not to be seen."""
    cut = icon_cut(part, row)
    if cut is None:
        return None, 0.0, 0.0
    s = icon_scores(icon_feature(cut), temps)
    order = np.argsort(s)
    top, lead = float(s[order[-1]]), float(s[order[-1]] - s[order[-2]])
    sure = top >= ICON_MIN and lead >= ICON_MARGIN
    return (CATEGORIES[int(order[-1])] if sure else None), top, lead


def read_rows(rec, part) -> list[Row]:
    """``find_rows`` with each row read: name, points, capped, category. Rows without a name are dropped – the white
    picture in a ring passes as a word, and the points beside it belong to the next row."""
    rows = find_rows(part)
    s = part.shape[0] / BOX_H if rows else 1.0
    out = []
    for r in rows:
        r.name = read_name(rec, part, r.word, s)
        if sum(c.isalpha() for c in r.name) < NAME_MIN_LETTERS:
            continue
        r.raw = read_points(rec, part, r.glyphs, s)
        r.points, r.capped = parse_points(r.raw)
        r.category = icon_category(part, r)[0]
        out.append(r)
    return out
