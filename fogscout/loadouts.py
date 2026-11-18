"""The survivors' loadouts from Dead by Daylight's pause menu (user: "Man sieht seit paar Monaten neu, was jeder
Survivor mitnimmt, wenn man ins Menü geht" – shown only to survivors, of the other survivors): the four perks, the
item and its two add-ons of each row, read from the screen picture only (hard rule – nothing from the game, no
network). Pure: numpy + OpenCV, the pictures of fogscout/perkicons (Dead by Daylight Wiki, THIRD_PARTY.md).

How a row is found without knowing where the menu sits or how large DBD draws it (the UI scale can be set):
1. ``_diamonds``: places shaped like a bright diamond on the dark menu (a slot = rarity fill + white drawing, the
   backdrop darker than ``FILL_VAL``) at several sizes on a small copy of the picture.
2. ``Reader._perk_hits``: a place is a perk only where a perk's drawing fits it clearly (``_glyph`` +
   ``Templates.best``: the white drawing – the minimum of the three colours – against the wiki pictures,
   normalised cross-correlation, ``MIN_SCORE``/``MIN_MARGIN``). The offering, the item and the portraits are no
   perks, so the step between two perks (``pitch``) and the left edge of the rows (``x0``) come from perks only.
3. Each row: the four slots on that grid, the item and add-ons at fixed steps (``ITEM_AT``, ``ADDONS_AT``), the
   character's portrait left of it (``PORTRAIT_AT``/``PORTRAIT_UP``) – all measured on the user's 3440×1440 menu.
   An unknown or unsure slot stays ``None``, never a guess. The killer's row (red) is left out.

Which survivor is which (1.57.1, user's pictures: the menu's order is not the HUD's, and the own row is not always
first): never by the names (any script, never read) but by the character's portrait – each survivor character is
in a match once. ``Votes`` keeps one entry per portrait over the looks (a slot counts after two equal readings);
``HudFinder`` finds each portrait in the HUD's survivor list after the menu closed – the perks are drawn beside
it. The own row: the menu's gold highlight (``_gold``), else the top portrait of the HUD's list."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES_FILE = os.path.join(HERE, "loadoutnames.json")
ICONS = os.path.join(HERE, "perkicons")

GLYPH = 32                    # side of the compared drawings
LOCATE_H = 720                # the picture is searched for diamonds at this height
FILL_VAL = 90                 # a slot (rarity fill + white drawing) is brighter than this; the menu's backdrop and the
                              # own row's gold are darker (user's 3440×1440 menu: 45–80, diamonds ≥ 100)
SIZES = range(14, 64, 2)      # diamond sizes tried at LOCATE_H (≈ 2–9 % of the height)
MIN_FIT = 0.5                 # the best diamond: its share of bright pixels where they should be
PEAK_FIT = 0.3                # any other place looked at: at least this fit (the perk's drawing decides)
MAX_PEAKS = 60
PITCH = (1.05, 1.45)          # perk pitch / diamond size: the steps between two slots of a row
ROW_TOL = 0.3                 # perks on one row: heights within this share of their size
GRID_TOL = 0.25               # a perk's place on the grid: within this share of a step
ROW_GAP = 1.5                 # menu rows: at least this many steps apart (user's menu: 2.1)
MIN_SCORE = 0.78              # a slot's best picture must fit at least this well …
MIN_MARGIN = 0.05             # … and this much better than the second best
SQUARE = 0.80                 # item / add-on square: its side in perk pitches
ITEM_AT = 2.19                # centre of the item right of the fourth perk, in perk pitches (user's menu)
ADDONS_AT = (3.43, 4.33)      # … and of the two add-ons
DIAMOND = 0.88                # a perk diamond's width in perk pitches (user's menu: 37 of 42 px)
PORTRAIT_AT = 1.74            # the character's portrait: its centre left of the first perk, in perk pitches …
PORTRAIT_UP = 0.33            # … and above the row's centre
PORTRAIT = 1.0                # … the square cut out of it (inside the round picture)
FACE = 24                     # portraits are compared at this size (grey)
SAME_FACE = 0.8               # two portraits of the menu are the same survivor from this correlation on
HUD_FIT = 0.7                 # a portrait found in the HUD's list from this correlation on
HUD_SCALES = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6)   # HUD portrait / menu portrait (both scales can be set)
HUD_BOX = (0.0, 0.2, 0.3, 0.88)   # where DBD's survivor list can be: share of the 16:9 picture (x0, y0, x1, y1)
CORNER = 0.28                 # an add-on's top right corner (DBD's white "+") is left out of the comparison
MAX_ROWS = 5                  # four survivors and the killer (left out)


@dataclass(frozen=True)
class Row:
    perks: tuple = (None, None, None, None)    # names (English, as on the wiki) or None
    item: str | None = None
    addons: tuple = (None, None)
    own: bool = False
    who: int = -1                               # Votes: the survivor (one per portrait)
    face: np.ndarray | None = field(default=None, compare=False, repr=False)    # FACE × FACE grey portrait
    hud: tuple | None = None                    # HudFinder: (x, y, side) of the portrait, shares of the picture

    @property
    def empty(self) -> bool:
        return not any(self.perks) and self.item is None and not any(self.addons)


@dataclass(frozen=True)
class Board:
    rows: tuple = ()
    size: float = 0.0                           # the diamonds' size in the picture (px) – for the diagnosis
    pitch: float = 0.0                          # the step between two perks (px): the portraits' size follows

    @property
    def others(self) -> tuple:
        """The other survivors' rows (the own row left out)."""
        return tuple(r for r in self.rows if not r.own)

    def key(self) -> tuple:
        """What is shown: the rows with at least one name, with their place in the HUD."""
        return tuple((r.who, r.perks, r.item, r.addons, r.own, r.hud) for r in self.rows if not r.empty)


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

    def best(self, glyphs: np.ndarray, at: list | None = None):
        """(name, score, margin) of the best picture for any of ``glyphs`` (n × GLYPH²), or (None, score, margin)
        when it is not clearly the best; ``at`` gets the index of the cut that fitted best."""
        if not len(self.names) or not len(glyphs):
            return None, 0.0, 0.0
        glyphs = glyphs.reshape(len(glyphs), GLYPH, GLYPH)
        if self.corner:
            glyphs = np.stack([_no_corner(g) for g in glyphs])
        scores = _norm(glyphs.reshape(len(glyphs), -1).astype(np.float32)) @ self.matrix.T     # n × templates
        per = scores.max(axis=0)                                    # each picture at its best cut
        order = np.argsort(per)[::-1]
        if at is not None:
            at.append(int(np.argmax(scores[:, order[0]])))
        top = float(per[order[0]])
        second = float(per[order[1]]) if len(order) > 1 else 0.0
        name = self.names[order[0]] if top >= MIN_SCORE and top - second >= MIN_MARGIN else None
        return name, top, top - second


def _glyph(bgr: np.ndarray) -> np.ndarray:
    """The white drawing of a cut-out slot as GLYPH × GLYPH floats: high where all three colours are high."""
    import cv2
    small = cv2.resize(bgr, (GLYPH, GLYPH), interpolation=cv2.INTER_AREA)
    low = np.minimum(np.minimum(small[..., 0], small[..., 1]), small[..., 2]).astype(np.float32) / 255
    return np.clip((low - 0.35) / 0.5, 0, 1)


def _cuts(frame, cx: float, cy: float, side: float, reach: int = 1, places: list | None = None,
          step: float | None = None, sizes: bool = True) -> np.ndarray:
    """The drawings of the square around (cx, cy) with a few shifts and sizes (the found place is ± a pixel or
    two off; ``reach`` 2 for a place from the coarse diamond search, ± side/10) – n × GLYPH²."""
    h, w = frame.shape[:2]
    step = step or max(1.0, side / 20)
    shifts = [k * step for k in range(-reach, reach + 1)]
    out = []
    for s in ((side - step, side, side + step) if sizes else (side,)):
        for dx in shifts:
            for dy in shifts:
                x0, y0 = int(round(cx + dx - s / 2)), int(round(cy + dy - s / 2))
                x1, y1 = int(round(x0 + s)), int(round(y0 + s))
                if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 - x0 < 8:
                    continue
                out.append(_glyph(frame[y0:y1, x0:x1]).ravel())
                if places is not None:
                    places.append((cx + dx, cy + dy))
    return np.array(out, dtype=np.float32) if out else np.zeros((0, GLYPH * GLYPH), np.float32)


def _diamond_mask(s: int) -> np.ndarray:
    """+1 on the bright ring of a diamond of side ``s``, −1 just outside it, 0 in its middle (the drawing)."""
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
    fill = (hsv[..., 2] > FILL_VAL).astype(np.float32)
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
    for _ in range(MAX_PEAKS):
        _, v, _, (px, py) = cv2.minMaxLoc(work)
        if v < PEAK_FIT:
            break
        peaks.append(((px + s / 2) / f, (py + s / 2) / f))
        x0, y0 = max(0, px - s // 2 - 1), max(0, py - s // 2 - 1)
        work[y0:py + s // 2 + 2, x0:px + s // 2 + 2] = -1
    return s / f, peaks


def _face(frame, cx: float, cy: float, side: float):
    """The grey FACE × FACE picture of the square around (cx, cy), None outside the picture."""
    import cv2
    h, w = frame.shape[:2]
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    x1, y1 = int(round(cx + side / 2)), int(round(cy + side / 2))
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 - x0 < 8:
        return None
    grey = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1]), cv2.COLOR_BGR2GRAY)
    return cv2.resize(grey, (FACE, FACE), interpolation=cv2.INTER_AREA)


def same_face(a, b) -> float:
    """Correlation of two FACE pictures (−1 … 1), 0 when one is missing."""
    if a is None or b is None:
        return 0.0
    m = _norm(np.stack([a.ravel(), b.ravel()]).astype(np.float32))
    return float(m[0] @ m[1])


def _strip(frame, x0: float, x1: float, y: float, half: float):
    """Mean HSV of the strip x0…x1 around the row's centre (the row's backdrop left of the perks)."""
    import cv2
    h, w = frame.shape[:2]
    a, b = max(0, int(x0)), min(w, int(x1))
    c, d = max(0, int(y - half)), min(h, int(y + half))
    if b - a < 2 or d - c < 2:
        return None
    return cv2.cvtColor(np.ascontiguousarray(frame[c:d, a:b]), cv2.COLOR_BGR2HSV).reshape(-1, 3).mean(axis=0)


def _gold(hsv) -> bool:
    """The own row's highlight: gold (user's menu: hue 25, saturation 116) – the others are blue-grey."""
    return hsv is not None and 10 <= hsv[0] <= 40 and hsv[1] >= 80


def _red(hsv) -> bool:
    """The killer's row: red."""
    return hsv is not None and (hsv[0] <= 8 or hsv[0] >= 170) and hsv[1] >= 120


class Reader:
    """Reads the loadout board from a picture of the pause menu (BGR)."""

    def __init__(self, names: dict | None = None, folder: str = ICONS):
        names = names or _names()
        self.perks = Templates("perks", names, folder)
        self.items = Templates("items", names, folder)
        self.addons = Templates("addons", names, folder)
        self.last = ""                                    # what the last look found – for the diagnosis

    def _perk_hits(self, frame, size: float, peaks: list) -> list:
        """[(x, y)] of the places where a perk's drawing clearly fits – moved to where it fits best (the coarse
        search is a few pixels off)."""
        out = []
        for x, y in peaks:
            places, at = [], []                          # coarse: ± size/5 in steps of size/10, one size …
            self.perks.best(_cuts(frame, x, y, size, reach=2, places=places, step=size / 10, sizes=False), at)
            if not at:
                continue
            fx, fy = places[at[0]]
            places, at = [], []                          # … then fine around the best place
            if self.perks.best(_cuts(frame, fx, fy, size, places=places), at)[0] is not None:
                out.append(places[at[0]])
        return out

    def read(self, frame) -> Board | None:
        size, peaks = _diamonds(frame)
        if not peaks:
            self.last = "keine Rauten"
            return None
        hits = self._perk_hits(frame, size, peaks)
        if not hits:
            self.last = f"{len(peaks)} Rauten, kein Perk"
            return None
        # the grid: every perk is x0 + n · pitch (n 0…3) – a straight line through all of them (one pair alone is
        # a pixel or two off, and the add-ons sit 7 steps further)
        x_min = min(x for x, _y in hits)
        guess = size * 1.15
        ns = np.array([round((x - x_min) / guess) for x, _y in hits], dtype=float)
        xs = np.array([x for x, _y in hits], dtype=float)
        pitch, x0 = guess, x_min
        if len(set(ns.tolist())) >= 2:
            p, x = (float(v) for v in np.polyfit(ns, xs, 1))
            if PITCH[0] * size <= p <= PITCH[1] * size:
                pitch, x0 = p, x
        # only perks on that grid (the HUD's own perks bottom right sit half a step apart: no menu)
        hits = [(x, y) for x, y in hits
                if abs((x - x0) / pitch - round((x - x0) / pitch)) <= GRID_TOL and 0 <= round((x - x0) / pitch) <= 3]
        lines = []
        for x, y in sorted(hits, key=lambda p: p[1]):
            for line in lines:
                if abs(np.mean([p[1] for p in line]) - y) <= ROW_TOL * size:
                    line.append((x, y))
                    break
            else:
                lines.append([(x, y)])
        # menu rows are far apart (≈ 2 steps); closer ones are no menu
        kept = []
        for line in sorted(lines, key=lambda ln: np.mean([p[1] for p in ln])):
            y = float(np.mean([p[1] for p in line]))
            if kept and y - kept[-1][0] < ROW_GAP * pitch:
                if len(line) > len(kept[-1][1]):
                    kept[-1] = (y, line)
                continue
            kept.append((y, line))
        if len(kept) < 2:                     # the menu lists four survivors; one row of perks is no menu (the HUD's own
            self.last = f"{len(peaks)} Rauten, kein Raster"     # perks) – and with only the own row nothing to show
            return None
        lines = [line for _y, line in kept]
        rows = []
        for line in sorted(lines, key=lambda ln: np.mean([p[1] for p in ln]))[:MAX_ROWS]:
            y = float(np.mean([p[1] for p in line]))
            back = _strip(frame, x0 - 1.2 * pitch, x0 - 0.7 * pitch, y, 0.25 * pitch)
            if _red(back):
                continue                                  # the killer's row
            perks = tuple(self.perks.best(_cuts(frame, x0 + k * pitch, y, pitch * DIAMOND))[0] for k in range(4))
            last = x0 + 3 * pitch
            item = self.items.best(_cuts(frame, last + ITEM_AT * pitch, y, pitch * SQUARE, reach=2))[0]
            addons = tuple(self.addons.best(_cuts(frame, last + a * pitch, y, pitch * SQUARE, reach=2))[0]
                           for a in ADDONS_AT)
            face = _face(frame, x0 - PORTRAIT_AT * pitch, y - PORTRAIT_UP * pitch, PORTRAIT * pitch)
            rows.append(Row(perks=perks, item=item, addons=addons, own=bool(_gold(back)), face=face))
        self.last = f"{len(rows)} Reihen, Raute {size:.0f} px"
        return Board(rows=tuple(rows), size=round(size, 1), pitch=round(pitch, 2)) if rows else None


class HudFinder:
    """Finds the menu's portraits in DBD's survivor list (the HUD left in the picture) – by the picture, never by
    a name. ``find`` gives {who: (x, y, side)} as shares of the picture for each portrait found clearly."""

    def find(self, frame, faces: dict, menu_side: float) -> dict:
        import cv2
        h, w = frame.shape[:2]
        vw, vh = min(w, h * 16 / 9), min(h, w * 9 / 16)
        vx, vy = (w - vw) / 2, (h - vh) / 2
        bx0, by0 = int(vx + HUD_BOX[0] * vw), int(vy + HUD_BOX[1] * vh)
        bx1, by1 = int(vx + HUD_BOX[2] * vw), int(vy + HUD_BOX[3] * vh)
        if bx1 - bx0 < 20 or by1 - by0 < 20 or not faces or menu_side <= 0:
            return {}
        half = 0.5                                       # searched at half size: four times faster
        box = cv2.cvtColor(np.ascontiguousarray(frame[by0:by1, bx0:bx1]), cv2.COLOR_BGR2GRAY)
        box = cv2.resize(box, None, fx=half, fy=half, interpolation=cv2.INTER_AREA)
        found = []
        for who, face in faces.items():
            if face is None:
                continue
            for sc in HUD_SCALES:
                side = max(8, int(round(menu_side * sc * half)))
                if side >= min(box.shape):
                    continue
                t = cv2.resize(face, (side, side), interpolation=cv2.INTER_AREA)
                r = cv2.matchTemplate(box, t, cv2.TM_CCOEFF_NORMED)
                _mn, v, _ml, (px, py) = cv2.minMaxLoc(r)
                found.append((float(v), who, (bx0 + (px + side / 2) / half) / w, (by0 + (py + side / 2) / half) / h,
                              side / half / h))
        found.sort(key=lambda f: -f[0])
        out, taken = {}, []
        for v, who, fx, fy, fs in found:
            if v < HUD_FIT or who in out or any(abs(fy - ty) < 0.6 * fs for ty in taken):
                continue
            out[who] = (round(fx, 4), round(fy, 4), round(fs, 4))
            taken.append(fy)
        return out


class Votes:
    """The board of one round from several looks, one entry per survivor (found again by the portrait – the
    menu's order changes): a slot shows a name once it was read ``need`` times and more often than any other name
    there (one misread look never reaches the screen; a slot read differently stays open)."""

    def __init__(self, need: int = 2):
        self.need = need
        self.looks = 0
        self.side = 0.0                   # the menu portraits' size (px) – HudFinder scales from it
        self._people: list = []           # {"face", "counts": {slot: {name: n}}, "own": n, "seen": n, "hud": …}

    def _who(self, face, index: int) -> int:
        """The survivor of a row: the one with the same portrait; a row without one (cut off) by its place."""
        best, at = 0.0, -1
        for i, p in enumerate(self._people):
            v = same_face(face, p["face"])
            if v > best:
                best, at = v, i
        if at >= 0 and best >= SAME_FACE:
            return at
        if face is None:
            for i, p in enumerate(self._people):
                if p["face"] is None and p["index"] == index:
                    return i
        self._people.append({"face": face, "index": index, "counts": {}, "own": 0, "seen": 0, "hud": None})
        return len(self._people) - 1

    def note(self, board: Board | None) -> bool:
        """Count a look; True when the shown board changed."""
        if board is None:
            return False
        before = self.board().key()
        self.looks += 1
        if board.pitch:
            self.side = board.pitch * PORTRAIT
        for index, row in enumerate(board.rows):
            p = self._people[self._who(row.face, index)]
            p["seen"] += 1
            p["own"] += 1 if row.own else 0
            for slot, name in enumerate(row.perks + (row.item,) + row.addons):
                if name is not None:
                    c = p["counts"].setdefault(slot, {})
                    c[name] = c.get(name, 0) + 1
        return self.board().key() != before

    def faces(self) -> dict:
        """{who: portrait} of the survivors not yet found in the HUD."""
        return {i: p["face"] for i, p in enumerate(self._people) if p["hud"] is None and p["face"] is not None}

    def place(self, found: dict) -> bool:
        """Places found by HudFinder; True when the shown board changed."""
        before = self.board().key()
        for who, at in found.items():
            if 0 <= who < len(self._people):
                self._people[who]["hud"] = at
        return self.board().key() != before

    @property
    def placed(self) -> bool:
        """Every survivor seen with a face has its place in the HUD."""
        return bool(self._people) and not self.faces()

    def _slot(self, p: dict, slot: int):
        c = p["counts"].get(slot, {})
        if not c:
            return None
        ranked = sorted(c.items(), key=lambda kv: -kv[1])
        if ranked[0][1] < self.need or (len(ranked) > 1 and ranked[1][1] == ranked[0][1]):
            return None
        return ranked[0][0]

    def _own(self) -> int:
        """The own survivor: the gold row of the menu (most looks), else the top portrait of the HUD's list once
        every survivor has its place there; -1 when not known."""
        gold = [(p["own"], i) for i, p in enumerate(self._people) if p["own"] * 2 > p["seen"]]
        if gold:
            return max(gold)[1]
        if self.placed and len(self._people) > 1:
            return min(range(len(self._people)), key=lambda i: self._people[i]["hud"][1])
        return -1

    def board(self) -> Board:
        own = self._own()
        rows = []
        for i, p in enumerate(self._people):
            names = [self._slot(p, s) for s in range(7)]
            rows.append(Row(perks=tuple(names[:4]), item=names[4], addons=tuple(names[5:]), own=i == own, who=i,
                            face=p["face"], hud=p["hud"]))
        return Board(rows=tuple(rows))

    def reset(self) -> None:
        self.looks = 0
        self.side = 0.0
        self._people.clear()
