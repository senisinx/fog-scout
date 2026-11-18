"""The survivors' loadouts from Dead by Daylight's pause menu (user: "Man sieht seit paar Monaten neu, was jeder
Survivor mitnimmt, wenn man ins Menü geht" – shown only to survivors, of the other survivors): the four perks, the
item and its two add-ons of each row, read from the screen picture only (hard rule – nothing from the game, no
network). Pure: numpy + OpenCV, the pictures of fogscout/perkicons (Dead by Daylight Wiki, THIRD_PARTY.md).

How a row is found without knowing where the menu sits or how large DBD draws it (the HUD scale can be set):
1. ``_diamonds``: the perk diamonds are the only diamond-shaped areas of one strong colour (the rarity) – a
   diamond-shaped mask is matched against "strongly coloured" pixels at several sizes on a small copy of the
   picture; the best size is the menu's size.
2. ``_rows``: diamonds on one height in steps of about 1.2 × their size are one row; the rows share their left
   edge (``x0``), so an empty first slot still counts right.
3. ``_glyph`` + ``Templates.best``: each slot is cut out at full size and its white drawing (the minimum of the
   three colours is high only for white and grey) compared with the drawings of the known pictures (normalised
   cross-correlation, a few shifts and sizes). A slot is named only when the best picture is clearly the best
   (``MIN_SCORE``, ``MIN_MARGIN``) – an unknown or unsure slot stays ``None``, never a guess.
4. Item and add-ons sit right of the perks at fixed steps of the perk pitch (``ITEM_AT``, ``ADDONS_AT``),
   measured on the user's picture.

The own row is the first one (DBD lists the player first, highlighted); ``Board.others`` are the rows of the
other survivors in the order of the menu, which is the order of the HUD's list. A slot counts only
after it was read twice the same way (``Votes``)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES_FILE = os.path.join(HERE, "loadoutnames.json")
ICONS = os.path.join(HERE, "perkicons")

GLYPH = 32                    # side of the compared drawings
LOCATE_H = 720                # the picture is searched for diamonds at this height
SIZES = range(14, 64, 2)      # diamond sizes tried at LOCATE_H (≈ 2–9 % of the height)
MIN_FIT = 0.62                # the best diamond: its share of strongly coloured pixels where they should be
PEAK_FIT = (0.45, 0.55)       # any other: at least this fit and this share of the best (the drawing covers a part)
PITCH = (1.05, 1.45)          # perk pitch / diamond size: the steps between two slots of a row
ROW_TOL = 0.25                # diamonds on one row: heights within this share of their size
MIN_SCORE = 0.78              # a slot's best picture must fit at least this well …
MIN_MARGIN = 0.05             # … and this much better than the second best
SQUARE = 0.80                 # item / add-on square: its side in perk pitches
ITEM_AT = 2.24                # centre of the item right of the fourth perk, in perk pitches
ADDONS_AT = (3.44, 4.44)      # … and of the two add-ons
DIAMOND = 0.84                # a perk diamond's width in perk pitches
CORNER = 0.28                 # an add-on's top right corner (DBD's white "+") is left out of the comparison
MAX_ROWS = 4


@dataclass(frozen=True)
class Row:
    perks: tuple = (None, None, None, None)    # names (English, as on the wiki) or None
    item: str | None = None
    addons: tuple = (None, None)
    own: bool = False

    @property
    def empty(self) -> bool:
        return not any(self.perks) and self.item is None and not any(self.addons)


@dataclass(frozen=True)
class Board:
    rows: tuple = ()
    size: float = 0.0                           # the diamonds' size in the picture (px) – for the diagnosis

    @property
    def others(self) -> tuple:
        """The other survivors' rows, in the menu's order (the own row is left out)."""
        return tuple(r for r in self.rows if not r.own)

    def key(self) -> tuple:
        """What is shown: the rows with at least one name."""
        return tuple((i, r.perks, r.item, r.addons, r.own) for i, r in enumerate(self.rows) if not r.empty)


def load_names(path: str = NAMES_FILE) -> dict:
    """{"perks"|"items"|"addons": {file: name}} – the pictures the reader knows."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: dict(data.get(k, {})) for k in ("perks", "items", "addons")}


def icon_file(name: str, kind: str, names: dict | None = None) -> str | None:
    """The picture file (full path) for a name read by the reader, for drawing it."""
    for f, n in (names or _names()).get(kind, {}).items():
        if n == name:
            path = os.path.join(ICONS, f)
            return path if os.path.isfile(path) else None
    return None


_NAMES = None


def _names() -> dict:
    global _NAMES
    if _NAMES is None:
        _NAMES = load_names()
    return _NAMES


def _norm(a: np.ndarray) -> np.ndarray:
    """Rows of ``a`` (n × k) minus their mean, divided by their length (0 rows stay 0)."""
    a = a - a.mean(axis=1, keepdims=True)
    n = np.linalg.norm(a, axis=1, keepdims=True)
    return np.divide(a, n, out=np.zeros_like(a), where=n > 1e-6)


def _no_corner(g: np.ndarray) -> np.ndarray:
    """The drawing without its top right corner (where DBD marks an add-on with a "+")."""
    c = int(GLYPH * CORNER)
    g = g.copy()
    g[:c, GLYPH - c:] = 0
    return g


def _template(path: str, corner: bool = False) -> np.ndarray | None:
    import cv2
    pic = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if pic is None or pic.ndim != 3 or pic.shape[2] != 4:
        return None
    pic = cv2.resize(pic, (GLYPH, GLYPH), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    g = pic[..., 3] * pic[..., :3].mean(axis=2)
    return _no_corner(g) if corner else g


class Templates:
    """The drawings of one kind of picture ("perks", "items", "addons"), normalised for the correlation."""

    def __init__(self, kind: str, names: dict | None = None, folder: str = ICONS):
        files = (names or _names()).get(kind, {})
        self.corner = kind == "addons"
        self.names, rows = [], []
        for f, name in sorted(files.items()):
            t = _template(os.path.join(folder, f), self.corner)
            if t is not None:
                self.names.append(name)
                rows.append(t.ravel())
        self.matrix = _norm(np.array(rows, dtype=np.float32)) if rows else np.zeros((0, GLYPH * GLYPH), np.float32)

    def best(self, glyphs: np.ndarray):
        """(name, score, margin) of the best picture for any of ``glyphs`` (n × GLYPH²), or (None, score, margin)
        when it is not clearly the best."""
        if not len(self.names) or not len(glyphs):
            return None, 0.0, 0.0
        glyphs = glyphs.reshape(len(glyphs), GLYPH, GLYPH)
        if self.corner:
            glyphs = np.stack([_no_corner(g) for g in glyphs])
        scores = _norm(glyphs.reshape(len(glyphs), -1).astype(np.float32)) @ self.matrix.T     # n × templates
        per = scores.max(axis=0)                                    # each picture at its best cut
        order = np.argsort(per)[::-1]
        top = float(per[order[0]])
        second = float(per[order[1]]) if len(order) > 1 else 0.0
        name = self.names[order[0]] if top >= MIN_SCORE and top - second >= MIN_MARGIN else None
        return name, top, top - second


def _glyph(bgr: np.ndarray) -> np.ndarray:
    """The white drawing of a cut-out slot as GLYPH × GLYPH floats: high where all three colours are high."""
    import cv2
    small = cv2.resize(bgr, (GLYPH, GLYPH), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    return np.clip((small.min(axis=2) - 0.35) / 0.5, 0, 1)


def _cuts(frame, cx: float, cy: float, side: float) -> np.ndarray:
    """The drawings of the square around (cx, cy) with a few shifts and sizes (the found place is ± a pixel or
    two off) – n × GLYPH²."""
    h, w = frame.shape[:2]
    step = max(1.0, side / 20)
    out = []
    for s in (side - step, side, side + step):
        for dx in (-step, 0, step):
            for dy in (-step, 0, step):
                x0, y0 = int(round(cx + dx - s / 2)), int(round(cy + dy - s / 2))
                x1, y1 = int(round(x0 + s)), int(round(y0 + s))
                if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 - x0 < 8:
                    continue
                out.append(_glyph(frame[y0:y1, x0:x1]).ravel())
    return np.array(out, dtype=np.float32) if out else np.zeros((0, GLYPH * GLYPH), np.float32)


def _diamond_mask(s: int) -> np.ndarray:
    """+1 on the coloured fill of a diamond of side ``s``, −1 just outside it, 0 on the drawing in its middle."""
    c = (s - 1) / 2
    yy, xx = np.mgrid[0:s, 0:s]
    d = (np.abs(xx - c) + np.abs(yy - c)) / max(c, 1)
    t = np.zeros((s, s), np.float32)
    t[(d <= 0.95) & (d >= 0.62)] = 1
    t[(d > 1.0) & (d <= 1.4)] = -1
    return t


def _diamonds(frame) -> tuple:
    """(size, [(x, y), …]) of the perk diamonds in the picture (full-size pixels), or (0, [])."""
    import cv2
    h, w = frame.shape[:2]
    f = LOCATE_H / h
    small = cv2.resize(frame, (max(1, int(w * f)), LOCATE_H), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    fill = ((hsv[..., 1] > 100) & (hsv[..., 2] > 70)).astype(np.float32)
    best = (0.0, 0, None)
    for s in SIZES:
        t = _diamond_mask(s)
        r = cv2.matchTemplate(fill, t, cv2.TM_CCORR) / float((t > 0).sum())
        top = float(r.max())
        if top > best[0]:
            best = (top, s, r)
    fit, s, r = best
    if r is None or fit < MIN_FIT:
        return 0, []
    peaks = []
    work = r.copy()
    for _ in range(MAX_ROWS * 4 + 8):
        _, v, _, (px, py) = cv2.minMaxLoc(work)
        if v < max(PEAK_FIT[0], fit * PEAK_FIT[1]):
            break
        peaks.append(((px + s / 2) / f, (py + s / 2) / f))
        x0, y0 = max(0, px - s // 2 - 1), max(0, py - s // 2 - 1)
        work[y0:py + s // 2 + 2, x0:px + s // 2 + 2] = -1
    return s / f, peaks


def _rows(size: float, peaks: list) -> tuple:
    """(pitch, x0, [y, …]): the rows of diamonds, the step between two slots and the first slot's centre."""
    lines = []
    for x, y in sorted(peaks, key=lambda p: p[1]):
        for line in lines:
            if abs(line[0][1] - y) <= ROW_TOL * size:
                line.append((x, y))
                break
        else:
            lines.append([(x, y)])
    steps = []
    for line in lines:
        xs = sorted(p[0] for p in line)
        steps += [b - a for a, b in zip(xs, xs[1:]) if PITCH[0] * size <= b - a <= PITCH[1] * size]
    if not steps:
        return 0.0, 0.0, []
    pitch = float(np.median(steps))
    good, starts = [], []
    for line in lines:
        xs = sorted(p[0] for p in line)
        # a row: diamonds on the grid of one step – each kept one has another 1–3 steps away (a lone coloured
        # spot on the row, a portrait, is not)
        kept = [a for a in xs if any(b != a and abs(abs(b - a) / pitch - round(abs(b - a) / pitch)) < 0.2
                                     and 1 <= round(abs(b - a) / pitch) <= 3 for b in xs)]
        if kept:
            good.append(float(np.mean([p[1] for p in line if p[0] in kept])))
            starts.append(min(kept))
    if not good:
        return 0.0, 0.0, []
    return pitch, min(starts), sorted(good)[:MAX_ROWS]


class Reader:
    """Reads the loadout board from a picture of the pause menu (BGR)."""

    def __init__(self, names: dict | None = None, folder: str = ICONS):
        names = names or _names()
        self.perks = Templates("perks", names, folder)
        self.items = Templates("items", names, folder)
        self.addons = Templates("addons", names, folder)
        self.last = ""                                    # what the last look found – for the diagnosis

    def read(self, frame) -> Board | None:
        size, peaks = _diamonds(frame)
        if not peaks:
            self.last = "keine Rauten"
            return None
        pitch, x0, ys = _rows(size, peaks)
        if not ys:
            self.last = f"{len(peaks)} Rauten, keine Reihe"
            return None
        rows = []
        for i, y in enumerate(ys):
            perks = tuple(self.perks.best(_cuts(frame, x0 + k * pitch, y, pitch * DIAMOND))[0] for k in range(4))
            last = x0 + 3 * pitch
            item = self.items.best(_cuts(frame, last + ITEM_AT * pitch, y, pitch * SQUARE))[0]
            addons = tuple(self.addons.best(_cuts(frame, last + a * pitch, y, pitch * SQUARE))[0] for a in ADDONS_AT)
            rows.append(Row(perks=perks, item=item, addons=addons, own=i == 0))     # a lone row is the own one
        self.last = f"{len(rows)} Reihen, Raute {size:.0f} px"
        return Board(rows=tuple(rows), size=round(size, 1))


class Votes:
    """The board of one round from several looks: a slot shows a name once it was read ``need`` times and more
    often than any other name there (one misread look never reaches the screen; a slot read differently stays
    open). Rows by their place in the menu."""

    def __init__(self, need: int = 2):
        self.need = need
        self.looks = 0
        self._counts: dict = {}           # (row, slot) -> {name: n}
        self._own: dict = {}              # row -> own?

    def note(self, board: Board | None) -> bool:
        """Count a look; True when the shown board changed."""
        if board is None:
            return False
        before = self.board().key()
        self.looks += 1
        for i, row in enumerate(board.rows):
            self._own[i] = row.own
            for slot, name in enumerate(row.perks + (row.item,) + row.addons):
                if name is not None:
                    c = self._counts.setdefault((i, slot), {})
                    c[name] = c.get(name, 0) + 1
        return self.board().key() != before

    def _slot(self, i: int, slot: int):
        c = self._counts.get((i, slot), {})
        if not c:
            return None
        ranked = sorted(c.items(), key=lambda kv: -kv[1])
        if ranked[0][1] < self.need or (len(ranked) > 1 and ranked[1][1] == ranked[0][1]):
            return None
        return ranked[0][0]

    def board(self) -> Board:
        rows = []
        for i in sorted(self._own):
            names = [self._slot(i, s) for s in range(7)]
            rows.append(Row(perks=tuple(names[:4]), item=names[4], addons=tuple(names[5:]), own=self._own[i]))
        return Board(rows=tuple(rows))

    def reset(self) -> None:
        self.looks = 0
        self._counts.clear()
        self._own.clear()
