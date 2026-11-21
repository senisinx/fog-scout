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
   An unknown or unsure slot stays ``None``, never a guess. The killer's row (red) is left out. 1.57.36: as the
   killer, DBD's menu shows only the survivors' offerings – ``Reader._killer`` reads those (``Board.killer``).

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
# 1.57.4 (user: "Falls jemand was Verstecktes wirft, soll dies ebenfalls so angezeigt werden"): a hidden offering is a
# brown hexagon with a faint skull – the wiki has no picture of it; its drawing (GLYPH × GLYPH, grey) is the mean of
# eight bot rows of the user's menu pictures
# 1.57.8 (user: "Object of Obsession heisst es, wenn man den Myers-DLC hat, sonst Bound by Obsession. Dasselbe bei
# Sole Survivor"): one perk with two names and one picture – read as the first name
SAME_AS = {"Bound by Obsession": "Object of Obsession", "Down to the Last": "Sole Survivor"}
HIDDEN_OFFERING = "Hidden offering"
HIDDEN_FILE = os.path.join(HERE, "loadout_hidden_offering.png")

GLYPH = 32                    # side of the compared drawings
LOCATE_H = 720                # the picture is searched for diamonds at this height
FILL_VAL = 90                 # a slot (rarity fill + white drawing) is brighter than this; the menu's backdrop and the
                              # own row's gold are darker (user's 3440×1440 menu: 45–80, diamonds ≥ 100)
SIZES = range(14, 64, 2)      # diamond sizes tried at LOCATE_H (≈ 2–9 % of the height)
KNOWN_SPAN = 4                # 1.57.32: after a board, first only the sizes this close to its size (at LOCATE_H)
MIN_FIT = 0.5                 # the best diamond: its share of bright pixels where they should be
PEAK_FIT = 0.3                # any other place looked at: at least this fit (the perk's drawing decides)
MAX_PEAKS = 60
PROVEN_ROW = 2                    # 1.57.9: clear reads (MIN_SCORE/MIN_MARGIN) a row needs before LOOSE_*/CLOSE_* count
SIZE_TRIES, SIZE_SPAN = 3, 0.06   # 1.57.9: diamond sizes fitting within SIZE_SPAN of the best are tried (≤ SIZE_TRIES)
# 1.57.15 (user's menu of 19.11.: three bots with bright eyes – 52 px fitted 0.77, the right 68 px only 0.64, 56 px 0.71:
# no size within SIZE_SPAN found a perk): when those sizes find fewer than ENOUGH_HITS perks, up to SIZE_MORE further
# sizes (by fit, at least MIN_FIT) are tried as well – only then, so a menu read at once costs nothing more
SIZE_MORE, ENOUGH_HITS = 3, 4
# 1.57.16 (user's menu of 19.11., 16:57: two bots without a loadout, Jonah with three eyes and Plot Twist): a perk's
# fit swings with a few pixels (Jonah's eyes 0.46 at the diamond search's place, 0.76 four pixels left) – the coarse
# search around a found diamond goes ± size/5 in HIT_STEPS steps each way (before: 2 steps of size/10, every eye missed)
HIT_STEPS = 4
PITCH = (1.05, 1.45)          # perk pitch / diamond size: the steps between two slots of a row
ROW_TOL = 0.3                 # perks on one row: heights within this share of their size
GRID_TOL = 0.25               # a perk's place on the grid: within this share of a step
ROW_GAP = 1.5                 # menu rows: at least this many steps apart (user's menu: 2.1)
MIN_SCORE = 0.78              # a slot's best picture must fit at least this well …
MIN_MARGIN = 0.05             # … and this much better than the second best
# 1.57.5 (user: "Perks werden nicht alle sauber erkannt"): a slot of a found row may fit less well when it stands out
# clearly – fit + lead ≥ LOOSE_SUM, fit ≥ LOOSE_FLOOR, lead ≥ LOOSE_MARGIN. On the user's four menus every read in
# this range was right (the same bots' perks across matches); the close ones (Déjà Vu / Kindred, lead 0.04) stay open
LOOSE_FLOOR, LOOSE_SUM, LOOSE_MARGIN = 0.62, 0.87, 0.04
# 1.57.7: a perk close to others (within CLOSE_SPAN, ≤ CLOSE_MAX) compared with each again on the CLOSE_PART of the
# pixels where the two differ most – counts when it fits CLOSE_FIT and beats each by CLOSE_LEAD (only a slot of a
# found row whose best fit is at least CLOSE_FLOOR; user's menus: Déjà Vu beat Kindred/Obsession by 0.07–0.19)
CLOSE_FLOOR, CLOSE_SPAN, CLOSE_MAX, CLOSE_PART, CLOSE_FIT, CLOSE_LEAD = 0.72, 0.06, 5, 0.1, 0.6, 0.08
SQUARE = 0.80                 # item / add-on square: its side in perk pitches
ITEM_AT = 2.19                # centre of the item right of the fourth perk, in perk pitches (user's menu)
ADDONS_AT = (3.43, 4.33)      # … and of the two add-ons
OFFERING_AT = 1.1             # 1.57.4: the offering's hexagon right of the fourth perk …
OFFERING = 0.9                # … and its size, in perk pitches
DIAMOND = 0.88                # a perk diamond's width in perk pitches (user's menu: 37 of 42 px)
PORTRAIT_AT = 1.74            # the character's portrait: its centre left of the first perk, in perk pitches …
PORTRAIT_UP = 0.33            # … and above the row's centre
PORTRAIT = 1.0                # … the square cut out of it (inside the round picture)
FACE = 24                     # portraits are compared at this size (grey)
SAME_FACE = 0.8               # two portraits of the menu are the same survivor from this correlation on
HUD_FIT = 0.62                # a portrait found in the HUD's list from this correlation on (its round middle)
HUD_ROUND = 0.42              # 1.57.4: only the round middle of a portrait is compared (radius in portraits) – the
                              # corners show the menu's backdrop there and the game behind it in the HUD, and a
                              # framed portrait (obsession) has its brackets there
SURE_SCORE, SURE_MARGIN = MIN_SCORE, MIN_MARGIN   # 1.57.4: a slot read this clearly counts as two readings (menu
                                       # open shortly; 1.57.14: every strict read – on all of the user's real menus no
                                       # strict read ever differed between looks; one short look left 3 of 4 perks open;
                                       # 1.57.5: 0.88/0.12 left most of a short look open)
HUD_STEP = (1.2, 2.4)         # the list's rows: this many portraits apart …
HUD_ROW = 1.64                # … usually (user's HUD) – of two grids as good, the one nearer to it
HUD_GRID = 0.15               # a portrait's row on that grid: within this share of a step
HUD_SAME = 0.3                # two looks agree on a place within this share of a portrait
HUD_COL = 0.02                # the list is one column: centres within this share of the picture's width
HUD_LAST_FIT = 0.45           # 1.57.4: the last one missing, looked for only at the free row(s) of the list
HUD_SCALES = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6)   # HUD portrait / menu portrait (both scales can be set)
# 1.57.12 (user's real matches: hooked / downed / hurt teammates show an icon or red marks instead of the portrait,
# often three of four at once; the list never moves): DBD's survivor list at the usual HUD size – the own portrait's
# centre (x as share of the 16:9 picture's width, y of its height), the rows' step, a portrait's side (of the
# height); measured on all of the user's HUD pictures (own 608 px, others 726 / 844 / 962 px, 72 px, x 612 px)
HUD_LIST = (0.0672, 0.4222, 0.0819, 0.05)
TWIN_FACE = 0.9               # 1.57.13: two survivors with the same look (user's real menus: 0.97–1.00; others ≤ 0.55)
HUD_LIST_SIDE = 0.2           # a portrait found within this share of the list's side belongs to that list
HUD_BOX = (0.0, 0.2, 0.3, 0.88)   # where DBD's survivor list can be: share of the 16:9 picture (x0, y0, x1, y1)
CORNER = 0.28                 # an add-on's top right corner (DBD's white "+") is left out of the comparison
MAX_ROWS = 5                  # four survivors and the killer (left out)
# 1.57.36 (user: "Ich meine die Offerings der Survivor. Die sieht man als killer im spiel"): the killer's menu – the
# own red row with the killer's perks at the bottom (no survivor perk: found by its diamonds, not their drawings),
# above it the four survivors' rows with only their offering, on the same grid as a survivor's menu. Measured on the
# user's killer menu (2000×837, pitch 42.5 px): the rows 2.08 pitches apart (a survivor's menu: 2.08 too), the
# killer's row 2.21 pitches below the last survivor's
KILLER_STEP = 2.08
KILLER_GAP = 2.21
KILLER_ROWS = 4
# 1.57.18 (user: "Gelbe Taschenlampe von Jonah wird nicht erkannt", then "Seltenheitsfarbe auswerten"): the slot's
# fill colour (its corners, not the drawing) narrows an item or add-on to the rarity the wiki gives for that colour –
# measured on 115 item and add-on slots of the user's menus (OpenCV hue 0…180), every one as the wiki says: brown
# 11–15 Common, green 62–65 Uncommon, blue 106–111 Rare, purple 139–142 Very Rare, pink 170–171 Visceral (Ultra
# Rare), yellow 19–21 Event (Winter Party Starter, Masquerade items, Refined Serum, the Banquet Flashlight)
RARITY_COLOURS = (            # (hue from, hue to, saturation at least, value at least, rarities)
    (8, 17, 60, 30, frozenset({1, 11})),      # brown: Common (and Limited – bronze, not seen yet)
    (18, 26, 150, 100, frozenset({8})),       # yellow: Event
    (55, 72, 120, 35, frozenset({2})),        # green: Uncommon
    (100, 118, 70, 25, frozenset({3})),       # blue: Rare
    (132, 150, 90, 35, frozenset({4})),       # purple: Very Rare
    (162, 178, 150, 60, frozenset({5})),      # pink: Visceral (Ultra Rare)
)
RARITY_AT = ((-0.38, -0.38), (-0.38, 0.38), (0.38, 0.38), (0.0, 0.40), (-0.40, 0.0))   # corners (never the "+")


@dataclass(frozen=True)
class Row:
    perks: tuple = (None, None, None, None)    # names (English, as on the wiki) or None
    item: str | None = None
    addons: tuple = (None, None)
    offering: str | None = None                 # 1.57.4 (HIDDEN_OFFERING: burnt hidden)
    own: bool = False
    who: int = -1                               # Votes: the survivor (one per portrait)
    face: np.ndarray | None = field(default=None, compare=False, repr=False)    # FACE × FACE grey portrait
    hud: tuple | None = None                    # HudFinder: (x, y, side) of the portrait, shares of the picture
    sure: tuple = field(default=(), compare=False, repr=False)   # per slot (perks, item, add-ons): read very clearly
    # 1.57.25 (user: "einen Screenshot vom Menü nehmen, diesen verkleinern und dessen Survivor zuteilen"): the
    # slots as they look in the menu – perks 1–4, item, add-ons, offering (``TILE`` px BGRA, their shape cut free)
    pics: tuple = field(default=(), compare=False, repr=False)
    pics_n: int = 0                             # Votes: which look the pictures are from (a new one redraws)
    # 1.57.29 (user: "ja, setz das so um" – names only to tell alike portraits apart, only in memory): the menu
    # row's line of text (character, player name, ping) as read – only for rows whose portraits look alike
    line: str = field(default="", compare=False, repr=False)

    @property
    def empty(self) -> bool:
        return not any(self.perks) and self.item is None and not any(self.addons) and self.offering is None


@dataclass(frozen=True)
class Board:
    rows: tuple = ()
    size: float = 0.0                           # the diamonds' size in the picture (px) – for the diagnosis
    pitch: float = 0.0                          # the step between two perks (px): the portraits' size follows
    killer: bool = False                        # 1.57.36: the killer's menu – the survivors' offerings only

    @property
    def others(self) -> tuple:
        """The other survivors' rows (the own row left out)."""
        return tuple(r for r in self.rows if not r.own)

    def key(self) -> tuple:
        """What is shown: the rows with at least one name, with their place in the HUD."""
        return (self.killer,) + tuple((r.who, r.perks, r.item, r.addons, r.offering, r.own, r.hud, r.pics_n) for r in self.rows
                     if not r.empty or r.pics)


def load_names(path: str = NAMES_FILE) -> dict:
    """{"perks"|"items"|"addons"|"offerings": {file: name}} – the pictures the reader knows."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: dict(data.get(k, {})) for k in ("perks", "items", "addons", "offerings")}


def load_rarity(path: str = NAMES_FILE) -> dict:
    """1.57.18: {"items"|"addons": {name: rarity}} – the wiki's rarity of each item and add-on (same file)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: dict(v) for k, v in data.get("rarity", {}).items()}


def slot_rarities(frame, cx: float, cy: float, side: float):
    """1.57.18: the rarities the fill colour of the square slot around (cx, cy) allows (``RARITY_COLOURS``), or
    None when the colour says nothing (green, blue, grey, outside the picture)."""
    import cv2
    h, w = frame.shape[:2]
    patches = []
    for fx, fy in RARITY_AT:
        x, y = int(round(cx + fx * side)), int(round(cy + fy * side))
        if x < 2 or y < 2 or x + 3 > w or y + 3 > h:
            return None
        patches.append(frame[y - 2:y + 3, x - 2:x + 3].reshape(-1, 3))
    hsv = cv2.cvtColor(np.vstack(patches).astype(np.uint8)[None], cv2.COLOR_BGR2HSV)[0]
    hue, sat, val = (float(v) for v in np.median(hsv, axis=0))
    for lo, hi, s_min, v_min, allowed in RARITY_COLOURS:
        if lo <= hue <= hi and sat >= s_min and val >= v_min:
            return allowed
    return None


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


_RARITY = None


def _rarity() -> dict:
    global _RARITY
    if _RARITY is None:
        _RARITY = load_rarity()
    return _RARITY


def _hidden_offering() -> dict:
    """{HIDDEN_OFFERING: drawing} – empty when the file is missing."""
    import cv2
    pic = cv2.imread(HIDDEN_FILE, cv2.IMREAD_GRAYSCALE)
    if pic is None:
        return {}
    return {HIDDEN_OFFERING: cv2.resize(pic, (GLYPH, GLYPH), interpolation=cv2.INTER_AREA).astype(np.float32) / 255}


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

    def __init__(self, kind: str, names: dict | None = None, folder: str = ICONS, extra: dict | None = None):
        files = (names or _names()).get(kind, {})
        self.corner = kind == "addons"
        self.perks_kind = kind == "perks"
        self.names, rows = [], []
        seen = set()
        for f, name in sorted(files.items()):
            if name in SAME_AS:
                continue                                  # 1.57.8: the other name of one perk – read as that one
            t = _template(os.path.join(folder, f), self.corner)
            if t is not None and t.tobytes() not in seen:     # the same drawing twice can never be told apart
                seen.add(t.tobytes())
                self.names.append(name)
                rows.append(t.ravel())
        for name, glyph in (extra or {}).items():        # drawings that are no picture file (the hidden offering)
            self.names.append(name)
            rows.append(np.asarray(glyph, np.float32).ravel())
        known = _rarity().get(kind, {})
        self.rarity = np.array([known.get(n, 0) for n in self.names], dtype=np.int16)   # 0: not known
        self.matrix = _norm(np.array(rows, dtype=np.float32)) if rows else np.zeros((0, GLYPH * GLYPH), np.float32)

    def best(self, glyphs: np.ndarray, at: list | None = None, loose: bool = False, allowed=None):
        """(name, score, margin) of the best picture for any of ``glyphs`` (n × GLYPH²), or (None, score, margin)
        when it is not clearly the best; ``at`` gets the index of the cut that fitted best. ``loose`` (a slot of a row
        already found): a weaker fit counts when it leads clearly (``LOOSE_*``). ``allowed`` (1.57.18): only the
        pictures of these rarities (and those of no known rarity) compete – the slot's colour said so."""
        if not len(self.names) or not len(glyphs):
            return None, 0.0, 0.0
        glyphs = glyphs.reshape(len(glyphs), GLYPH, GLYPH)
        if self.corner:
            glyphs = np.stack([_no_corner(g) for g in glyphs])
        scores = _norm(glyphs.reshape(len(glyphs), -1).astype(np.float32)) @ self.matrix.T     # n × templates
        if allowed:
            other = (self.rarity != 0) & ~np.isin(self.rarity, list(allowed))
            if not other.all():
                scores[:, other] = -1.0
        per = scores.max(axis=0)                                    # each picture at its best cut
        order = np.argsort(per)[::-1]
        if at is not None:
            at.append(int(np.argmax(scores[:, order[0]])))
        top = float(per[order[0]])
        second = float(per[order[1]]) if len(order) > 1 else 0.0
        lead = top - second
        ok = top >= MIN_SCORE and lead >= MIN_MARGIN
        if loose and not ok:
            ok = top >= LOOSE_FLOOR and top + lead >= LOOSE_SUM and lead >= LOOSE_MARGIN
        if loose and not ok and top >= CLOSE_FLOOR:
            pick = self._apart(glyphs, scores, per, order)
            if pick is not None:
                return self.names[pick], top, lead
        return (self.names[order[0]] if ok else None), top, lead

    def _apart(self, glyphs, scores, per, order):
        """1.57.7 (user: "bei Lara fehlt immer das eine Perk" – Déjà Vu, Kindred and the two Obsession perks are
        one eye, only the pupil differs; on the whole drawing they are 0.03 apart): the best is compared with each
        drawing close to it (within ``CLOSE_SPAN``) again only where those two differ (``CLOSE_PART`` of the
        pixels, any cut) – it counts when it fits there at least ``CLOSE_FIT`` and beats every one of them by
        ``CLOSE_LEAD``. Perks only (the item kits stayed too close on the user's menus). Its index or None."""
        if not self.perks_kind:
            return None
        top = float(per[order[0]])
        best = int(order[0])
        near = [int(i) for i in order[1:CLOSE_MAX] if top - float(per[i]) <= CLOSE_SPAN]
        if not near:
            return None
        g = glyphs.reshape(len(glyphs), -1).astype(np.float32)
        for other in near:
            diff = np.abs(self.matrix[best] - self.matrix[other])
            mask = diff >= np.quantile(diff, 1 - CLOSE_PART)
            part = _norm(g[:, mask])
            fa = float((part @ _norm(self.matrix[best][mask][None])[0]).max())
            fb = float((part @ _norm(self.matrix[other][mask][None])[0]).max())
            if fa < CLOSE_FIT or fa - fb < CLOSE_LEAD:
                return None
        return best


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


def _fine_cuts(templates, frame, cx: float, cy: float, side: float) -> np.ndarray:
    """1.57.7 (user: Lara's Déjà Vu missing; the same menu, encoded a little differently, fitted 0.68 … 0.82 – the
    grid's place was a pixel off and the cuts' steps are side/20): the usual cuts plus finer ones (half the step,
    every size) around the one that fitted best."""
    places, at = [], []
    coarse = _cuts(frame, cx, cy, side, places=places)
    if not len(coarse):
        return coarse
    templates.best(coarse, at)
    fx, fy = places[at[0]] if at else (cx, cy)
    fine = _cuts(frame, fx, fy, side, step=max(0.5, side / 40))
    return np.vstack([coarse, fine]) if len(fine) else coarse


def _diamond_mask(s: int) -> np.ndarray:
    """+1 on the bright ring of a diamond of side ``s``, −1 just outside it, 0 in its middle (the drawing)."""
    c = (s - 1) / 2
    yy, xx = np.mgrid[0:s, 0:s]
    d = (np.abs(xx - c) + np.abs(yy - c)) / max(c, 1)
    t = np.zeros((s, s), np.float32)
    t[(d <= 0.95) & (d >= 0.62)] = 1
    t[(d > 1.0) & (d <= 1.4)] = -1
    return t


def _diamonds(frame, sizes: int = 1, more: int = 0, only=None) -> list:
    """[(size, [(x, y), …], near), …] of the perk diamonds in the picture (full-size pixels) for the ``sizes`` diamond
    sizes that fit best (1.57.9: the fit is flat over a few sizes – a menu full of bright eyes fitted 26 best, 32 was
    right), best first, ``near`` = within SIZE_SPAN of the best; then up to ``more`` further sizes fitting at least
    MIN_FIT (``near`` False); [] when none fits. ``only`` (1.57.32): try just these sizes (at LOCATE_H)."""
    import cv2
    h, w = frame.shape[:2]
    f = LOCATE_H / h
    small = cv2.resize(frame, (max(1, int(w * f)), LOCATE_H), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    fill = (hsv[..., 2] > FILL_VAL).astype(np.float32)
    fits = []
    for s in (SIZES if only is None else only):
        t = _diamond_mask(s)
        r = cv2.matchTemplate(fill, t, cv2.TM_CCORR) / float((t > 0).sum())
        fits.append((float(r.max()), s, r))
    fits.sort(key=lambda x: -x[0])
    if not fits or fits[0][0] < MIN_FIT:
        return []
    out, taken = [], {True: 0, False: 0}
    for fit, s, r in fits:
        near = fit >= fits[0][0] - SIZE_SPAN
        if fit < MIN_FIT or (not near and taken[False] >= more):
            break
        if near and taken[True] >= sizes:
            continue                                  # enough near sizes: on to the further ones
        if any(abs(s - o) <= 2 for o, _p, _n in out):
            continue                                  # a neighbour of a size taken already
        taken[near] += 1
        peaks = []
        work = r.copy()
        for _ in range(MAX_PEAKS):
            _, v, _, (px, py) = cv2.minMaxLoc(work)
            if v < PEAK_FIT:
                break
            peaks.append(((px + s / 2) / f, (py + s / 2) / f))
            x0, y0 = max(0, px - s // 2 - 1), max(0, py - s // 2 - 1)
            work[y0:py + s // 2 + 2, x0:px + s // 2 + 2] = -1
        out.append((s, peaks, near))
    return [(s / f, peaks, near) for s, peaks, near in out]


PERK_COLOUR = 0.04            # 1.57.30: a perk hit's diamond has at least this share of coloured pixels (user's menus:
                              # perks 0.07–0.83; the grey person icon of the other rows' headers 0.00 – read as "This
                              # Is Not Happening" 0.82 at a smaller size, it won the size choice at every odd pixel
                              # offset; the own row's icon on gold reaches 0.16, but one row alone never wins it)


def _coloured(frame, cx: float, cy: float, side: float) -> float:
    """Share of coloured pixels (saturation > 70, value > 50) inside the diamond of ``side`` px around (cx, cy)."""
    import cv2
    n = int(side)
    x0, y0 = int(round(cx - n / 2)), int(round(cy - n / 2))
    h, w = frame.shape[:2]
    if n < 4 or x0 < 0 or y0 < 0 or x0 + n > w or y0 + n > h:
        return 0.0
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[y0:y0 + n, x0:x0 + n, :3]), cv2.COLOR_BGR2HSV)
    inside = _diamond_mask(n) > 0
    return float(((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 50))[inside].mean())


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


HUD_TWIN = 0.8                # 1.57.28: two portraits the HUD can't tell apart (their round middles, as HudFinder
                              # compares them) – user's menus: one Claudette with and without DBD's brackets 0.89–1.00,
                              # other survivors ≤ 0.54


def hud_alike(a, b) -> float:
    """1.57.28 (user's match with four Claudettes in one skin, one of them with DBD's brackets "( )" around her
    portrait: 0.70 by ``same_face``, so no twin – and her perks were drawn one row too low): the correlation of two
    portraits' round middles (radius ``HUD_ROUND``), the only part HudFinder compares – what decides whether the HUD
    can tell two survivors apart. 0 when one is missing."""
    import cv2
    if a is None or b is None or a.shape != b.shape:
        return 0.0
    n = a.shape[0]
    mask = np.zeros(a.shape[:2], np.uint8)
    cv2.circle(mask, (n // 2, n // 2), max(2, int(n * HUD_ROUND)), 1, -1)
    inside = mask.astype(bool)
    x, y = a[inside].astype(np.float32), b[inside].astype(np.float32)
    x -= x.mean()
    y -= y.mean()
    den = float(np.sqrt((x @ x) * (y @ y)))
    return float(x @ y / den) if den > 1e-6 else 0.0


def _strip(frame, x0: float, x1: float, y: float, half: float, colour: bool = False):
    """Mean HSV of the strip x0…x1 around the row's centre (the row's backdrop left of the perks). ``colour``
    (1.57.21, user's public match: The Pig's hidden offering was read as a fifth survivor "S5" and drawn over the
    own row): the HSV of the mean colour instead – red lies at both ends of the hue circle (0 and 179), the pixels'
    hues of the killer's row averaged to 10–46 and it was never red (dropped only while nothing was read on it); the
    own gold row keeps the pixels' mean (its saturation fell from 98 to 78 as one colour)."""
    import cv2
    h, w = frame.shape[:2]
    a, b = max(0, int(x0)), min(w, int(x1))
    c, d = max(0, int(y - half)), min(h, int(y + half))
    if b - a < 2 or d - c < 2:
        return None
    if colour:
        mean = frame[c:d, a:b].reshape(-1, 3).mean(axis=0)
        return cv2.cvtColor(np.clip(np.rint(mean), 0, 255).astype(np.uint8)[None, None],
                            cv2.COLOR_BGR2HSV)[0, 0].astype(float)
    return cv2.cvtColor(np.ascontiguousarray(frame[c:d, a:b]), cv2.COLOR_BGR2HSV).reshape(-1, 3).mean(axis=0)


def _gold(hsv) -> bool:
    """The own row's highlight: gold (user's menu: hue 25, saturation 116) – the others are blue-grey."""
    return hsv is not None and 10 <= hsv[0] <= 40 and hsv[1] >= 80


def _red(hsv) -> bool:
    """The killer's row: red (1.57.21: as one colour hue 0, saturation 240 on all of the user's menus, ``_strip``)."""
    return hsv is not None and (hsv[0] <= 8 or hsv[0] >= 170) and hsv[1] >= 120


def _menu_rows(ys: list, pitch: float, height: int) -> list:
    """1.57.4 (CI on Windows: a survivor with few perks, read a hair below the bar there, was missing): the menu's
    rows are evenly spaced – [(y, inferred?)] of the rows found by their perks and of the rows on their grid
    between and after them (up to ``MAX_ROWS``); a grid row is read like the others and kept only when something
    on it is read."""
    ys = sorted(ys)
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    if not gaps:
        return [(y, False) for y in ys]
    base = min(gaps)
    step = float(np.median([g / max(1, round(g / base)) for g in gaps]))
    if step < ROW_GAP * pitch:
        return [(y, False) for y in ys]
    out = [(y, False) for y in ys]
    for k in range(-2, MAX_ROWS + 1):                # two above the first found (the own row may lack a perk read)
        y = ys[0] + k * step
        if pitch <= y <= height - pitch and all(abs(y - o) > 0.5 * step for o, _i in out):
            out.append((y, True))
    return sorted(out)


def _diamond_rows(peaks: list, size: float) -> list:
    """1.57.36: [(x0, pitch, y, xs)] of rows of four diamonds evenly spaced (``PITCH`` × ``size`` apart) among the
    diamond search's ``peaks`` – the perks of a row whose drawings need not be known (the killer's own row)."""
    out = []
    for _x, y in sorted(peaks, key=lambda p: p[1]):
        line = sorted(p for p in peaks if abs(p[1] - y) <= ROW_TOL * size)
        for a in range(len(line)):
            for b in range(a + 1, len(line)):
                for n in (3, 2, 1):                       # the coarse places are a few pixels off: the widest
                    pitch = (line[b][0] - line[a][0]) / n  # pair that fits gives the step best
                    if PITCH[0] * size <= pitch <= PITCH[1] * size:
                        break
                else:
                    continue
                chain = []
                for k in range(4):
                    want = line[a][0] + k * pitch
                    nxt = [p for p in line if abs(p[0] - want) <= GRID_TOL * pitch]
                    if not nxt:
                        break
                    chain.append(min(nxt, key=lambda p: abs(p[0] - want)))
                if len(chain) == 4:
                    p, x0 = (float(v) for v in np.polyfit(range(4), [c[0] for c in chain], 1))
                    row = (x0, p, float(np.mean([c[1] for c in chain])), tuple(c[0] for c in chain))
                    if all(abs(row[0] - o[0]) > GRID_TOL * p or abs(row[2] - o[2]) > ROW_TOL * size for o in out):
                        out.append(row)
    return out


def _best_place(templates, frame, cx: float, cy: float, side: float):
    """1.57.40: (name, score, lead, (x, y)) of the best picture around (cx, cy) – ``_fine_cuts`` that also gives the
    place of the cut that fitted best (where the slot's picture is cut from)."""
    places, at = [], []
    coarse = _cuts(frame, cx, cy, side, places=places)
    if not len(coarse):
        return None, 0.0, 0.0, (cx, cy)
    templates.best(coarse, at)
    fx, fy = places[at[0]] if at else (cx, cy)
    fine_places = []
    fine = _cuts(frame, fx, fy, side, step=max(0.5, side / 40), places=fine_places)
    allc, allp = (np.vstack([coarse, fine]), places + fine_places) if len(fine) else (coarse, places)
    at = []
    name, score, lead = templates.best(allc, at, loose=True)
    return name, score, lead, (allp[at[0]] if at else (fx, fy))


class Reader:
    """Reads the loadout board from a picture of the pause menu (BGR)."""

    def __init__(self, names: dict | None = None, folder: str = ICONS):
        names = names or _names()
        self.perks = Templates("perks", names, folder)
        self.items = Templates("items", names, folder)
        self.addons = Templates("addons", names, folder)
        self.offerings = Templates("offerings", names, folder, extra=_hidden_offering())
        self.last = ""                                    # what the last look found – for the diagnosis

    def _perk_hits(self, frame, size: float, peaks: list) -> list:
        """[(x, y)] of the places where a perk's drawing clearly fits – moved to where it fits best (the coarse
        search is a few pixels off)."""
        out = []
        for x, y in peaks:
            places, at = [], []                          # coarse: ± size/5 in HIT_STEPS steps each way, one size …
            self.perks.best(_cuts(frame, x, y, size, reach=HIT_STEPS, places=places, step=size / (5 * HIT_STEPS),
                                  sizes=False), at)
            if not at:
                continue
            fx, fy = places[at[0]]
            places, at = [], []                          # … then fine around the best place
            if self.perks.best(_cuts(frame, fx, fy, size, places=places), at)[0] is not None:
                if _coloured(frame, *places[at[0]], size) >= PERK_COLOUR:
                    out.append(places[at[0]])
        return out

    def _first_column(self, frame, hits: list, x0: float, pitch: float, size: float) -> tuple:
        """1.57.30 (user: "untersuche den 1-Pixel-Raster-Fehler"): the coarse search (at ``LOCATE_H``) finds the
        first perk column 7–9 px too far right – on the user's menu one of four first perks was hit, one pixel more
        and none: the second column became "perk 1", every slot was read (and cut) one place too far right. While
        fewer than four columns are hit, a column left of the grid is looked at: a perk read there clearly (strict,
        like any other slot) moves the grid's start to it."""
        for _ in range(3):
            cols = {round((x - x0) / pitch) for x, _y in hits}
            if not cols or max(cols) >= 3:
                break
            rows = []
            for y in sorted(y for _x, y in hits):
                if rows and y - rows[-1][-1] <= ROW_TOL * size:
                    rows[-1].append(y)
                else:
                    rows.append([y])
            left = x0 - pitch
            found = [(left, float(np.mean(r))) for r in rows
                     if self.perks.best(_fine_cuts(self.perks, frame, left, float(np.mean(r)), pitch * DIAMOND))[0]]
            if not found:
                break
            x0, hits = left, hits + found
        return x0, hits

    def read(self, frame, text=None) -> Board | None:
        """``text`` (1.57.29): reads a line of text from a picture (the worker's OCR) – only the rows whose portraits
        look alike get their line read (``Row.line``), to tell them apart in the HUD; None: no names at all.
        1.57.32 (user: "Weiter mit Optimierungen"; diagnosis: a look 625 ms on average, half of it trying 25 diamond
        sizes): the size of the last board read is tried first with its neighbours (``KNOWN_SPAN``) – DBD's UI size
        stays put; only when that gives no board of two rows are all sizes tried."""
        board = self._again(frame, text)               # 1.57.33: the last grid, read directly
        if board is not None:
            self.last = f"{len(board.rows)} Reihen, Raute {board.size:.0f} px (Raster wie zuvor)"
            return board
        known = getattr(self, "_known", None)
        if known is not None:
            board = self._read(frame, text, [s for s in SIZES if abs(s - known) <= KNOWN_SPAN])
            if board is not None and (len(board.rows) < 2  # the size chosen at the window's edge: the UI size
                                      or abs(board.size * LOCATE_H / frame.shape[0] - known) >= KNOWN_SPAN - 0.5):
                board = None                               # changed, the right one may lie outside – all sizes
        if board is None:
            board = self._read(frame, text, None)
        if board is not None and board.size:
            self._known = round(board.size * LOCATE_H / frame.shape[0])
        return board

    def _read(self, frame, text, only) -> Board | None:
        found = [(s_, p_, n_) for s_, p_, n_ in _diamonds(frame, SIZE_TRIES, SIZE_MORE, only) if p_]
        if not found:
            self.last = "keine Rauten"
            return None
        size, peaks, hits = 0.0, [], []
        for s_, p_, near in found:                        # 1.57.9: the size whose perks are found most often
            if not near and len(hits) >= ENOUGH_HITS:
                break                                     # 1.57.15: further sizes only when the near ones found few
            h_ = self._perk_hits(frame, s_, p_)
            if len(h_) > len(hits):
                size, peaks, hits = s_, p_, h_
        if len(hits) < 2:                                 # 1.57.36: the killer's menu has one row of (killer) perks
            board = self._killer(frame, text, found)
            if board is not None:
                return board
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
        x0, hits = self._first_column(frame, hits, x0, pitch, size)
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
            board = self._killer(frame, text, found)            # perks) – and with only the own row nothing to show
            if board is not None:                               # 1.57.36: unless it is the killer's own row
                return board
            self.last = f"{len(peaks)} Rauten, kein Raster"
            return None
        found_ys = [y for y, _line in kept]
        grid_rows = list(_menu_rows(found_ys, pitch, frame.shape[0]))
        self._grid = (frame.shape[:2], x0, pitch, size, tuple(y for y, _i in grid_rows), tuple(found_ys))
        return self._rows_on(frame, text, x0, pitch, size, grid_rows, found_ys)

    def _killer(self, frame, text, found) -> Board | None:
        """1.57.36: the killer's pause menu – four diamonds in a row on a red backdrop (the killer's own perks;
        the program knows only the survivors' perks, so the diamonds' places count, not their drawings), the
        survivors' rows ``KILLER_STEP`` apart above it, ``KILLER_GAP`` from it, each with only its offering (the
        place of a survivor's menu). A Board(killer=True) of the survivors' rows – offering and portrait – or None."""
        h = frame.shape[0]
        for size, peaks, _near in found:
            for x0, pitch, yk, xs in _diamond_rows(peaks, size):
                if not _red(_strip(frame, x0 - 1.2 * pitch, x0 - 0.7 * pitch, yk, 0.25 * pitch, colour=True)):
                    continue
                cx = x0 + 3 * pitch + OFFERING_AT * pitch
                # 1.57.40 (user's killer menu at 3440×1440: every offering unread, the pictures cut off-centre – the
                # coarse diamonds gave x0 6 px and the step 2 % off): the killer's own offering on its row joins the
                # straight line through its perks, and the survivors' hexagons found in that column give its place
                own = [(px, py) for px, py in peaks if abs(px - cx) <= 0.5 * pitch and abs(py - yk) <= 0.4 * pitch]
                if own:
                    ks = [0, 1, 2, 3, 3 + OFFERING_AT]
                    pitch, x0 = (float(v) for v in np.polyfit(ks, list(xs) + [own[0][0]], 1))
                    cx = x0 + 3 * pitch + OFFERING_AT * pitch
                column = [px for px, py in peaks if abs(px - cx) <= 0.4 * pitch and py < yk - pitch]
                if column:
                    cx = float(np.median(column))
                rows = []
                for j in range(KILLER_ROWS):
                    y = yk - (KILLER_GAP + j * KILLER_STEP) * pitch
                    if y < pitch:
                        break
                    near = [(px, py) for px, py in peaks
                            if abs(px - cx) <= 0.4 * pitch and abs(py - y) <= 0.4 * pitch]
                    if near:                              # the offering's hexagon was found: its height
                        y = min(near, key=lambda p: abs(p[1] - y))[1]
                    name, score, lead, (tx, ty) = _best_place(self.offerings, frame, cx, y, pitch * OFFERING)
                    sure = name is not None and score >= SURE_SCORE and lead >= SURE_MARGIN
                    if name is None:                      # nothing read: the picture where the slot should be
                        tx, ty = cx, y
                    tile = None
                    if name is not None or _coloured(frame, tx, ty, pitch * OFFERING) >= PERK_COLOUR:
                        tile = _tile(frame, tx, ty, pitch * OFFERING, "hexagon")    # an empty slot: no picture
                    face = _face(frame, x0 - PORTRAIT_AT * pitch, y - PORTRAIT_UP * pitch, PORTRAIT * pitch)
                    rows.append(Row(offering=name, face=face, sure=(False,) * 7 + (sure,),
                                    pics=(None,) * 7 + (tile,), line=f"@{x0:.1f},{y:.1f}"))
                if len(rows) < 2 or yk >= h:
                    continue
                rows = self._lines(frame, rows[::-1], pitch, text)
                self.last = f"Killer-Menü: {len(rows)} Survivor, Raute {size:.0f} px"
                return Board(rows=tuple(rows), size=round(size, 1), pitch=round(pitch, 2), killer=True)
        return None

    def _again(self, frame, text) -> Board | None:
        """1.57.33 (user: "Loadout-Erkennung weiter optimieren"): DBD draws the menu at the same pixels every time –
        the grid of the last board read is read again directly (no diamond or perk search); a row counts as found
        (not inferred) where a perk diamond is coloured (``PERK_COLOUR``). None when that gives no board of two rows
        with a clear perk – then the search as before."""
        known = getattr(self, "_grid", None)
        if known is None or known[0] != frame.shape[:2]:
            return None
        _shape, x0, pitch, size, ys, found_ys = known
        grid_rows = [(y, not any(_coloured(frame, x0 + k * pitch, y, pitch * DIAMOND) >= PERK_COLOUR
                                 for k in range(4))) for y in ys]
        board = self._rows_on(frame, text, x0, pitch, size, grid_rows, list(found_ys))
        if board is None or len(board.rows) < 2 or not any(r.sure and any(r.sure[:4]) for r in board.rows):
            return None
        return board

    def _rows_on(self, frame, text, x0: float, pitch: float, size: float, grid_rows, found_ys) -> Board | None:
        rows = []
        for y, inferred in grid_rows:
            if len(rows) >= MAX_ROWS:
                break
            back = _strip(frame, x0 - 1.2 * pitch, x0 - 0.7 * pitch, y, 0.25 * pitch)
            if _red(_strip(frame, x0 - 1.2 * pitch, x0 - 0.7 * pitch, y, 0.25 * pitch, colour=True)):
                continue                                  # the killer's row
            reads = [self.perks.best(_fine_cuts(self.perks, frame, x0 + k * pitch, y, pitch * DIAMOND), loose=True)
                     for k in range(4)]
            last = x0 + 3 * pitch
            cx = last + ITEM_AT * pitch
            reads.append(self.items.best(_cuts(frame, cx, y, pitch * SQUARE, reach=2), loose=False,
                                         allowed=slot_rarities(frame, cx, y, pitch * SQUARE)))
            reads += [self.addons.best(_cuts(frame, last + a * pitch, y, pitch * SQUARE, reach=2), loose=True,
                                       allowed=slot_rarities(frame, last + a * pitch, y, pitch * SQUARE))
                      for a in ADDONS_AT]
            reads.append(self.offerings.best(_cuts(frame, last + OFFERING_AT * pitch, y, pitch * OFFERING, reach=2),
                                             loose=True))
            strict = [n is not None and sc >= MIN_SCORE and m >= MIN_MARGIN for n, sc, m in reads]
            if sum(strict) < PROVEN_ROW:              # 1.57.9: the looser rules only in a row proven by clear reads
                reads = [r if ok else (None, r[1], r[2]) for r, ok in zip(reads, strict)]
            names = [n for n, _s, _m in reads]
            sure = tuple(n is not None and s >= SURE_SCORE and m >= SURE_MARGIN for n, s, m in reads)
            perks, item, addons, offering = tuple(names[:4]), names[4], tuple(names[5:7]), names[7]
            if inferred and not any(names) and not (_gold(back) and y < found_ys[0]):
                continue                                  # a row of the grid with nothing read: none (1.57.6: the
                                                          # own gold row counts empty too – no perks equipped)
            face = _face(frame, x0 - PORTRAIT_AT * pitch, y - PORTRAIT_UP * pitch, PORTRAIT * pitch)
            rows.append(Row(perks=perks, item=item, addons=addons, offering=offering, own=bool(_gold(back)), face=face,
                            sure=sure, pics=slot_pictures(frame, x0, y, pitch), line=f"@{x0:.1f},{y:.1f}"))
        empty_own = [r for r in rows if r.own and r.empty]
        if empty_own and (len(empty_own) > 1 or any(r.own and not r.empty for r in rows)):
            rows = [r for r in rows if not (r.own and r.empty)]  # a gold patch above a read own row: no row
        rows = self._lines(frame, rows, pitch, text)
        self.last = f"{len(rows)} Reihen, Raute {size:.0f} px"
        return Board(rows=tuple(rows), size=round(size, 1), pitch=round(pitch, 2)) if rows else None

    @staticmethod
    def _lines(frame, rows: list, pitch: float, text) -> list:
        """1.57.29: the line of text of each row whose portrait looks like another row's (not the own one) – the
        rest get none (``line`` held only the row's place until here)."""
        import dataclasses
        alike = set()
        for i, a in enumerate(rows):
            for j, b in enumerate(rows):
                if i < j and not a.own and not b.own and hud_alike(a.face, b.face) >= HUD_TWIN:
                    alike |= {i, j}
        out = []
        for i, r in enumerate(rows):
            line = ""
            if text is not None and i in alike:
                x0, y = (float(v) for v in r.line[1:].split(","))
                cut = name_box(frame, menu_name_box(x0, y, pitch))
                if cut is not None:
                    try:
                        line = text(cut) or ""
                    except Exception:
                        line = ""
            out.append(dataclasses.replace(r, line=line))
        return out


TILE = 64                     # 1.57.25: a slot's picture cut from the menu (px, square)


def _tile(frame, cx: float, cy: float, side: float, shape: str = "square"):
    """1.57.25: the slot around (cx, cy), ``side`` px, as DBD draws it – ``TILE`` × ``TILE`` BGRA, outside its shape
    ("diamond" perk, "hexagon" offering, "square") transparent; None when it runs off the picture."""
    import cv2
    h, w = frame.shape[:2]
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    x1, y1 = int(round(cx + side / 2)), int(round(cy + side / 2))
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 - x0 < 4 or y1 - y0 < 4:
        return None
    cut = cv2.resize(np.ascontiguousarray(frame[y0:y1, x0:x1, :3]), (TILE, TILE), interpolation=cv2.INTER_AREA)
    mask = np.full((TILE, TILE), 255, np.uint8)
    c = (TILE - 1) / 2
    if shape == "diamond":
        pts = [(c, 0), (TILE - 1, c), (c, TILE - 1), (0, c)]
    elif shape == "hexagon":
        pts = [(c + c * np.cos(np.radians(a)), c + c * np.sin(np.radians(a))) for a in range(30, 390, 60)]
    else:
        pts = None
    if pts is not None:
        mask[:] = 0
        cv2.fillConvexPoly(mask, np.round(np.array(pts)).astype(np.int32), 255, lineType=cv2.LINE_AA)
    return np.dstack([cut, mask])


def slot_pictures(frame, x0: float, y: float, pitch: float) -> tuple:
    """1.57.25: the eight slots of a menu row whose first perk is at (x0, y): perks 1–4, item, two add-ons,
    offering – the order of ``Row``'s names."""
    last = x0 + 3 * pitch
    out = [_tile(frame, x0 + k * pitch, y, pitch * DIAMOND, "diamond") for k in range(4)]
    out.append(_tile(frame, last + ITEM_AT * pitch, y, pitch * SQUARE))
    out += [_tile(frame, last + a * pitch, y, pitch * SQUARE) for a in ADDONS_AT]
    out.append(_tile(frame, last + OFFERING_AT * pitch, y, pitch * OFFERING, "hexagon"))
    return tuple(out)


NAME_LINE = (0.3, -1.48, 11.0, -0.92)   # 1.57.29: the menu row's line of text – x0, y0, x1, y1 in perk pitches from
                                        # its first perk (user's menus: person icon, name, player name, ping, BOT)
HUD_NAME = (1.1, 0.02, 5.5, 0.42)       # … the player name right below a HUD portrait, in portraits from its centre
NAME_COST = 0.34                        # 1.57.31: a name fits a line with at most this share of its characters changed …
NAME_AHEAD = 1                          # … and the twins' best assignment by this many changes fewer than the next


def name_box(frame, box) -> object:
    """1.57.29: the picture inside ``box`` (x0, y0, x1, y1 px) with DBD's orange "BOT" tag darkened (it is no part
    of a name); None when it lies off the picture."""
    import cv2
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 8 or y1 - y0 < 6:
        return None
    cut = np.ascontiguousarray(frame[y0:y1, x0:x1, :3]).copy()
    hsv = cv2.cvtColor(cut, cv2.COLOR_BGR2HSV)
    cut[(hsv[:, :, 0] >= 5) & (hsv[:, :, 0] <= 28) & (hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 90)] = 0
    return cut


def menu_name_box(x0: float, y: float, pitch: float) -> tuple:
    a, b, c, d = NAME_LINE
    return x0 + a * pitch, y + b * pitch, x0 + c * pitch, y + d * pitch


def hud_name_box(at: tuple, width: int, height: int) -> tuple:
    """``at`` = (x, y, side) of a HUD portrait as shares of the picture (HudFinder, list_grid)."""
    x, y, side = at[0] * width, at[1] * height, at[2] * height
    a, b, c, d = HUD_NAME
    return x + a * side, y + b * side, x + c * side, y + d * side


_SAME_LOOK = str.maketrans({"O": "0", "I": "1", "L": "1", "|": "1"})


def fold_name(text: str) -> str:
    """Letters and digits upper case, the ones OCR mixes up made one (O/0, I/l/1)."""
    return "".join(ch for ch in (text or "").upper() if ch.isalnum()).translate(_SAME_LOOK)


def name_cost(hud_text: str, line: str) -> int:
    """1.57.31 (user's custom game with two "Thalita Lyra" bots: the menu's line was read "THAUTA LYRA…" – one
    misread letter broke 1.57.29's longest common run, nobody was placed): how many characters must change (insert,
    drop, replace) for the name read in the HUD to stand somewhere in a menu row's line – an edit distance that lets
    the line begin and end anywhere. DBD's "BOT" tag after the HUD name is left out."""
    a, b = fold_name(hud_text), fold_name(line)
    for tag in ("B0T", "BT", "B0"):                    # the tag, also read in part
        if a.endswith(tag):
            a = a[:-len(tag)]
            break
    if not a:
        return 99
    prev = [0] * (len(b) + 1)                          # free start anywhere in the line
    for ch in a:
        cur = [prev[0] + 1]
        for k, bc in enumerate(b, 1):
            cur.append(min(prev[k] + 1, cur[k - 1] + 1, prev[k - 1] + (ch != bc)))
        prev = cur
    return min(prev)                                   # free end anywhere


class HudFinder:
    """Finds the menu's portraits in DBD's survivor list (the HUD left in the picture) – by the picture, never by
    a name. ``find`` gives {who: (x, y, side)} as shares of the picture for each portrait found clearly."""

    def find(self, frame, faces: dict, menu_side: float, scales=HUD_SCALES, box=None) -> dict:
        """``box`` (1.57.32): only this part of the picture (x0, y0, x1, y1 as shares) – DBD's list column once it
        was seen there (``list_box``); otherwise the whole ``HUD_BOX``."""
        import cv2
        h, w = frame.shape[:2]
        vw, vh = min(w, h * 16 / 9), min(h, w * 9 / 16)
        vx, vy = (w - vw) / 2, (h - vh) / 2
        bx0, by0 = int(vx + HUD_BOX[0] * vw), int(vy + HUD_BOX[1] * vh)
        bx1, by1 = int(vx + HUD_BOX[2] * vw), int(vy + HUD_BOX[3] * vh)
        if box is not None:
            bx0, by0 = max(bx0, int(box[0] * w)), max(by0, int(box[1] * h))
            bx1, by1 = min(bx1, int(box[2] * w)), min(by1, int(box[3] * h))
        if bx1 - bx0 < 20 or by1 - by0 < 20 or not faces or menu_side <= 0:
            return {}
        half = 0.5                                       # searched at half size: four times faster
        box = cv2.cvtColor(np.ascontiguousarray(frame[by0:by1, bx0:bx1]), cv2.COLOR_BGR2GRAY)
        box = cv2.resize(box, None, fx=half, fy=half, interpolation=cv2.INTER_AREA)
        found = []
        for who, face in faces.items():
            if face is None:
                continue
            for sc in scales:
                side = max(8, int(round(menu_side * sc * half)))
                if side >= min(box.shape):
                    continue
                t = cv2.resize(face, (side, side), interpolation=cv2.INTER_AREA)
                mask = np.zeros((side, side), np.uint8)
                cv2.circle(mask, (side // 2, side // 2), max(2, int(side * HUD_ROUND)), 255, -1)
                r = cv2.matchTemplate(box, t, cv2.TM_CCOEFF_NORMED, mask=mask)
                r[~np.isfinite(r)] = -1
                for _peak in range(2):                   # 1.57.6: the two best places – the same character twice
                    _mn, v, _ml, (px, py) = cv2.minMaxLoc(r)     # (own Dwight and a bot Dwight) are two rows
                    found.append((float(v), who, (bx0 + (px + side / 2) / half) / w,
                                  (by0 + (py + side / 2) / half) / h, side / half / h))
                    r[max(0, py - side // 2):py + side // 2 + 1, max(0, px - side // 2):px + side // 2 + 1] = -1
        found.sort(key=lambda f: -f[0])
        self.scores = {}
        for v, who, *_rest in found:                    # each portrait's best fit of this look (diagnosis)
            self.scores[who] = max(v, self.scores.get(who, -1.0))
        out, taken = {}, []
        for v, who, fx, fy, fs in found:
            if v < HUD_FIT or who in out or any(abs(fy - ty) < 0.6 * fs for ty in taken):
                continue
            out[who] = (round(fx, 4), round(fy, 4), round(fs, 4))
            taken.append(fy)
        return out


def list_grid(width: int, height: int):
    """(x, y, step, side) of the own portrait in DBD's survivor list (shares of the picture) at the usual HUD size."""
    vw = min(width, height * 16 / 9)
    vx = (width - vw) / 2
    x, y, step, side = HUD_LIST
    return ((vx + x * vw) / width, y, step, side)


def list_box(grid, width: int, height: int) -> tuple:
    """1.57.32 (user: "Weiter mit Optimierungen"; a HUD look 106–141 ms, 56 looks in one round): the part of the
    picture DBD's list ``grid`` (list_grid) can hold – its column (``HUD_COL`` and a portrait each side) and its four
    rows (a portrait above and below) – as shares (x0, y0, x1, y1). Only places in it count once the list was seen
    (``Votes.place_on_list``)."""
    gx, gy, step, side = grid
    pad = 1.6 * side * height                        # a portrait and a half: bigger HUD sizes (Votes.scales) fit
    x0, x1 = gx * width - HUD_COL * width - pad, gx * width + HUD_COL * width + pad
    y0, y1 = (gy - 1.6 * side) * height, (gy + 3 * step + 1.6 * side) * height
    return max(0.0, x0 / width), max(0.0, y0 / height), min(1.0, x1 / width), min(1.0, y1 / height)


def on_grid(found: dict) -> dict:
    """The places of ``found`` ({who: (x, y, side)}) that fit DBD's survivor list: one column, rows a whole number
    of steps apart (``HUD_STEP`` × the portrait); at least two – a lone match says nothing."""
    if len(found) < 2:
        return {}
    side = sorted(a[2] for a in found.values())[len(found) // 2]
    xs = sorted(a[0] for a in found.values())
    mid = xs[len(xs) // 2]
    col = {w: a for w, a in found.items() if abs(a[0] - mid) <= HUD_COL}
    if len(col) < 2:
        return {}
    ys = sorted(a[1] for a in col.values())
    best, best_key = {}, None
    for i, base in enumerate(ys):                    # every pair may give the step; keep the largest set on a grid
        for other in ys[i + 1:]:                     # (of two as large: the one fitting best, the usual step)
            gap = other - base
            for n in (1, 2, 3):
                step = gap / n
                if not HUD_STEP[0] * side <= step <= HUD_STEP[1] * side:
                    continue
                off = {w: abs((a[1] - base) / step - round((a[1] - base) / step)) for w, a in col.items()}
                fit = {w: col[w] for w, e in off.items() if e <= HUD_GRID}
                key = (len(fit), -round(sum(off[w] for w in fit), 2), -abs(step / side - HUD_ROW))
                if best_key is None or key > best_key:
                    best, best_key = fit, key
    return best if len(best) >= 2 else {}


def score_at(frame, face, place) -> float:
    """1.57.4: how well ``face`` fits around ``place`` ((x, y, side) as shares of the picture) – the round middle
    only, a little search around it; −1 outside the picture."""
    import cv2
    h, w = frame.shape[:2]
    x, y, s = place[0] * w, place[1] * h, place[2] * h
    side = max(8, int(round(s)))
    pad = side // 3
    x0, y0 = int(x - side / 2 - pad), int(y - side / 2 - pad)
    x1, y1 = x0 + side + 2 * pad, y0 + side + 2 * pad
    if face is None or x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        return -1.0
    box = cv2.cvtColor(np.ascontiguousarray(frame[y0:y1, x0:x1]), cv2.COLOR_BGR2GRAY)
    t = cv2.resize(face, (side, side), interpolation=cv2.INTER_AREA)
    mask = np.zeros((side, side), np.uint8)
    cv2.circle(mask, (side // 2, side // 2), max(2, int(side * HUD_ROUND)), 255, -1)
    r = cv2.matchTemplate(box, t, cv2.TM_CCOEFF_NORMED, mask=mask)
    r[~np.isfinite(r)] = -1
    return float(r.max())


def _kit(row) -> tuple:
    """What a row shows: perks, item, add-ons, offering."""
    return row.perks, row.item, row.addons, row.offering


PICS_APART = 25.0             # 1.57.26: two rows' slot pictures of one look differ from this mean difference on
PICS_SIDE = 8                 # … compared at this size (user's menu with two Kates: other loadouts 58–93, the same
                              # loadout re-encoded ≤ 11 – the rows of one look share their grid, two looks may not)


def _pics_apart(a: tuple, b: tuple) -> bool:
    """1.57.26 (user: "Was wenn mehrere gleiche Survivor in der Runde sind"): whether two rows of **one** look show
    other loadouts by their slot pictures – the largest mean difference of a slot both have, inside its shape, at
    ``PICS_SIDE`` px. Without pictures: not known – False."""
    import cv2
    worst = -1.0
    for p, q in zip(a or (), b or ()):
        if p is None or q is None:
            continue
        ps = cv2.resize(p, (PICS_SIDE, PICS_SIDE), interpolation=cv2.INTER_AREA).astype(np.int16)
        qs = cv2.resize(q, (PICS_SIDE, PICS_SIDE), interpolation=cv2.INTER_AREA).astype(np.int16)
        inside = (ps[:, :, 3] > 200) & (qs[:, :, 3] > 200)
        if inside.any():
            worst = max(worst, float(np.abs(ps[:, :, :3] - qs[:, :, :3])[inside].mean()))
    return worst >= PICS_APART


class Votes:
    """The board of one round from several looks, one entry per survivor (found again by the portrait – the
    menu's order changes): a slot shows a name once it was read ``need`` times and more often than any other name
    there (one misread look never reaches the screen; a slot read differently stays open)."""

    def __init__(self, need: int = 2):
        self.need = need
        self.looks = 0
        self._pics_n = 0                  # 1.57.25: counts the looks whose slot pictures were taken
        self._apart: set = set()          # 1.57.26: {who, who} alike portraits whose pictures differed in one look
        self.side = 0.0                   # the menu portraits' size (px) – HudFinder scales from it
        self._hud_seen: dict = {}         # the places on the grid of the last look at the HUD
        self._last_seen = None            # (who, place) the last look chose for the only one missing (1.57.4)
        self._missed = 0                  # 1.57.7: HUD looks in a row that found nothing (at the remembered size)
        self._own_at = None               # 1.57.11: the own portrait's place in the HUD (kept across rounds)
        self._list_seen = False           # 1.57.12: portraits were found on DBD's usual list (kept across rounds)
        self._twin_rows: dict = {}        # 1.57.13: rows of the list where one of two alike survivors was seen (count)
        self._people: list = []           # {"face", "counts": {slot: {name: n}}, "own": n, "seen": n, "hud": …}
        self.killer = False               # 1.57.36: the killer's menu – no own survivor, the list's rows 0–3 theirs

    def _who(self, face, index: int, used: set = frozenset(), own: bool = False) -> int:
        """The survivor of a row: the one with the same portrait; a row without one (cut off) by its place.
        1.57.6 (user's match with the own Dwight and a bot Dwight): two rows of one look are never one survivor –
        of the same portrait the own row is the one seen gold before. 1.57.12 (user's debug pictures: the two
        Dwights swapped between looks): the gold row is always the survivor seen gold, a plain row never is."""
        gold = [i for i, p in enumerate(self._people) if p["own"] > 0 and i not in used]
        if own and gold:
            return gold[0]
        best, at = 0.0, -1
        for i, p in enumerate(self._people):
            if i in used:
                continue
            if not own and p["own"] * 2 > p["seen"] > 0:
                continue                                  # 1.57.12: the own one (gold) never takes a plain row
            v = same_face(face, p["face"])
            if v >= TWIN_FACE and p["index"] == index:
                v += 0.05                                 # 1.57.13: twins (two Kates) kept apart by their menu row
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
        self.killer = self.killer or board.killer
        if board.pitch:
            self.side = board.pitch * PORTRAIT
        used = set()
        seen = []                                 # (who, row) of this look
        for index, row in enumerate(board.rows):
            who = self._who(row.face, index, used, row.own)
            used.add(who)
            for other, prev in seen:              # 1.57.26: two alike portraits of one look, other pictures
                if (row.face is not None and prev.face is not None and hud_alike(row.face, prev.face) >= HUD_TWIN
                        and _pics_apart(row.pics, prev.pics)):
                    self._apart.add(frozenset((who, other)))
            seen.append((who, row))
            p = self._people[who]
            p["seen"] += 1
            p["own"] += 1 if row.own else 0
            if row.line:                          # 1.57.29: the menu line of an alike portrait (memory only)
                p["line"] = row.line
            read = sum(1 for n in row.perks + (row.item,) + row.addons + (row.offering,) if n is not None)
            if row.pics and read >= p.get("pics_read", -1):      # 1.57.25: the pictures of the clearest look
                self._pics_n += 1
                p["pics"], p["pics_read"], p["pics_n"] = row.pics, read, self._pics_n
            for slot, name in enumerate(row.perks + (row.item,) + row.addons + (row.offering,)):
                if name is not None:              # 1.57.4: a very clear reading counts twice (the menu may be shut
                    c = p["counts"].setdefault(slot, {})          # after one look)
                    sure = slot < len(row.sure) and row.sure[slot]
                    c[name] = c.get(name, 0) + (2 if sure else 1)
        return self.board().key() != before

    @property
    def list_seen(self) -> bool:
        """DBD's list was found at its usual place (``place_on_list``) – from then on only it counts."""
        return bool(self._list_seen)

    def faces(self) -> dict:
        """{who: portrait} of every survivor with a portrait – all are looked for in each look (one found at a wrong
        place must not take a free row from another)."""
        own = self._own(gold_only=True) if self._list_seen else -1     # 1.57.12: its row is known – not looked for
        return {i: p["face"] for i, p in enumerate(self._people) if p["face"] is not None and i != own}

    def twins(self) -> set:
        """1.57.13 (user's real match with two Kate Densons, one skin): survivors other than the own one whose
        portraits are the same (``TWIN_FACE``) and whose loadouts differ – the HUD can't tell which is which, so they
        are never placed by their portrait (with the same loadout either place is right). 1.57.26: "differ" also
        when their slot pictures differed in one look (``_apart``) – names read alike (none, or the same misreading)
        must not make two loadouts the same."""
        own = self._own(gold_only=True)
        board = self.board().rows
        out = set()
        for i, p in enumerate(self._people):
            for j, q in enumerate(self._people):
                if i < j and own not in (i, j) and p["face"] is not None and q["face"] is not None \
                        and hud_alike(p["face"], q["face"]) >= HUD_TWIN \
                        and (_kit(board[i]) != _kit(board[j]) or frozenset((i, j)) in self._apart):
                    out |= {i, j}
        return out

    def place_on_list(self, found: dict, grid) -> bool | None:
        """1.57.12 (user's real matches: three of four portraits an icon or marked red at once – two found in one
        look were seldom; the own one hooked): with DBD's list where it always is (``grid`` = list_grid), the own
        survivor (gold row) stands on its top row without being looked for, and every other portrait found counts
        on its own when it sits on one of the three rows below at the list's size – after two agreeing looks, one
        survivor a row. None when nothing found fits that list (another HUD size: the grid of the found ones,
        ``place``, decides)."""
        gx, gy, step, side = grid
        own = self._own(gold_only=True)
        twins = self.twins()
        fits = {}
        for who, (x, y, s) in found.items():
            if who == own or not 0 <= who < len(self._people):
                continue
            k = round((y - gy) / step)
            if (abs(s - side) <= HUD_LIST_SIDE * side and abs(x - gx) <= HUD_COL and self._first_row <= k <= 3
                    and abs(y - (gy + k * step)) <= HUD_GRID * step):
                if who in twins:                          # one of them is there – which one is unknown
                    self._twin_rows[k] = self._twin_rows.get(k, 0) + 1
                else:
                    fits[who] = (gx, gy + k * step, side)
        if not fits and not self._list_seen and not self._twin_rows:
            return None                                   # nothing fits it (yet): another HUD size, maybe
        self._list_seen = True                            # it fits: from now on only the list (kept across rounds)
        before = self.board().key()
        self._missed = 0 if found else self._missed + 1
        if own >= 0 and self._people[own]["hud"] is None:
            self._people[own]["hud"] = (gx, gy, side)     # its row is the top one – no need to find its portrait
            self._own_at = (gx, gy, side)
        prev, self._hud_seen = self._hud_seen, fits
        for who, at in fits.items():
            if prev.get(who) == at and self._people[who]["hud"] is None:
                if all(p["hud"] is None or abs(p["hud"][1] - at[1]) >= 0.5 * step for p in self._people):
                    self._people[who]["hud"] = at
        # the last one by elimination: four survivors, four rows – three placed (the own one among them), one row
        # left; its portrait need not be seen (hooked or downed all the time). 1.57.36: as the killer all four rows
        if (own >= 0 or self.killer) and len(self._people) == 4:
            left = [i for i, p in enumerate(self._people) if p["hud"] is None]
            rows = [k for k in range(self._first_row, 4) if all(p["hud"] is None or abs(p["hud"][1] - (gy + k * step)) >= 0.5 * step
                                                for p in self._people) and self._twin_rows.get(k, 0) < 2]
            left = [i for i in left if i not in twins]      # 1.57.13: the twins' rows (seen twice) are theirs
            if len(left) == 1 and len(rows) == 1:
                self._people[left[0]]["hud"] = (gx, gy + rows[0] * step, side)
        return self.board().key() != before

    @property
    def _first_row(self) -> int:
        """1.57.36: the first row of DBD's list another survivor can stand on – 1 below the own one, 0 as the
        killer (the list holds the four survivors only)."""
        return 0 if self.killer else 1

    def name_rows(self, grid) -> list:
        """1.57.29: the list's rows (1–3, DBD's list ``grid``) where an unplaced twin may stand – their names are
        read only there and only while twins are left; [] otherwise."""
        twins = [i for i in self.twins() if self._people[i]["hud"] is None and self._people[i].get("line")]
        if not twins:
            return []
        gx, gy, step, side = grid
        taken = [p["hud"][1] for p in self._people if p["hud"] is not None]
        return [k for k in range(self._first_row, 4) if all(abs(y - (gy + k * step)) >= 0.5 * step for y in taken)]

    def place_by_names(self, read: dict, grid) -> bool:
        """1.57.29 (user: four Claudettes in one skin; "Weshalb sollte das mit dem Namen ein Problem sein?" – "ja"):
        ``read`` = {row: name read below the HUD portrait there}. 1.57.31: the twins are given the free rows all at
        once – the assignment whose names stand best in the twins' menu lines compared with the other twins'
        (``name_cost`` minus the best other twin's at that row), each within ``NAME_COST`` of its name and
        ``NAME_AHEAD`` better than any other assignment – after two looks agreeing. Names are kept nowhere else."""
        import itertools
        gx, gy, step, side = grid
        twins = [i for i in self.twins() if self._people[i]["hud"] is None and self._people[i].get("line")]
        before = self.board().key()
        rows = [k for k, t in read.items() if t]
        choice = {}
        if twins and len(rows) >= len(twins):
            cost = {(i, k): name_cost(read[k], self._people[i]["line"]) for i in twins for k in rows}
            limit = {k: max(1, int(NAME_COST * len(fold_name(read[k])))) for k in rows}
            # how much better a row fits this twin than the best other twin (a row that fits all alike – another
            # alike bot's, an empty one's – says nothing; 1.57.31: the Claudettes' third row tied otherwise)
            rel = {(i, k): cost[i, k] - min(cost[j, k] for j in twins if j != i) for i in twins for k in rows}
            ranked = sorted((sum(rel[i, k] for i, k in zip(twins, ks)), ks)
                            for ks in itertools.permutations(rows, len(twins)))
            best, ks = ranked[0]
            if (len(ranked) == 1 or ranked[1][0] - best >= NAME_AHEAD) \
                    and all(cost[i, k] <= limit[k] for i, k in zip(twins, ks)):
                choice = dict(zip(twins, ks))
        prev, self._name_seen = getattr(self, "_name_seen", {}), choice
        for i, k in choice.items():
            if prev.get(i) == k and self._people[i]["hud"] is None:
                self._people[i]["hud"] = (gx, gy + k * step, side)
        return self.board().key() != before

    def place(self, found: dict, grid=None) -> bool:
        """Places found by HudFinder in one look; True when the shown board changed. 1.57.2 (user's picture: one
        perk diamond above the own portrait, none at a bot whose portrait was covered): a place counts only when it
        lies on the list's grid with the others of that look (same column, rows a whole number of steps apart) and
        the look before found it at the same place – one stray match never sticks for the round."""
        if grid is not None:                          # 1.57.12: DBD's list where it always is
            done = self.place_on_list(found, grid)
            if done is not None:
                return done
        before = self.board().key()
        self._missed = 0 if found else self._missed + 1           # 1.57.7: two empty looks: all sizes again
        good = self._own_on_top(on_grid({w: a for w, a in found.items() if 0 <= w < len(self._people)}))
        good = self._below_own(good)
        twins = self.twins()                          # 1.57.13: never by a portrait two survivors share
        good = {w: a for w, a in good.items() if w not in twins}
        prev = self._hud_seen
        self._hud_seen = good
        for who, at in good.items():
            last = prev.get(who)
            if last is not None and abs(last[1] - at[1]) <= HUD_SAME * at[2] and abs(last[0] - at[0]) <= HUD_COL:
                if self._people[who]["hud"] is None:
                    taken = [p["hud"][1] for p in self._people if p["hud"] is not None]
                    if all(abs(y - at[1]) >= 0.6 * at[2] for y in taken):
                        self._people[who]["hud"] = at
        return self.board().key() != before

    def _below_own(self, good: dict) -> dict:
        """1.57.11 (user's match with real players: the own portrait hurt, not found – another survivor's perks were
        drawn at the own, top row): with the own survivor known (gold row) the others count only below its place –
        found this look, placed before, or remembered from an earlier round (``_own_at``, the HUD stays put); with
        none of these known, nobody is placed this look."""
        own = self._own(gold_only=True)
        if own < 0:
            return good
        at = good.get(own) or self._people[own]["hud"] or self._own_at
        if at is None:
            return {}
        if own in good or self._people[own]["hud"] is not None:
            self._own_at = good.get(own) or self._people[own]["hud"]
        return {w: a for w, a in good.items() if w == own or a[1] > at[1] + 0.6 * at[2]}

    def _own_on_top(self, good: dict) -> dict:
        """1.57.6 (user's match with the own Dwight and a bot Dwight – alike portraits fit each other's place): the
        own survivor always stands on top of the HUD's list. When the own (gold row) was found below another one,
        it takes the top place and the other gets none this look (it is looked for at the freed row then)."""
        own = self._own(gold_only=True)
        if own not in good or len(good) < 2:
            return good
        top = min(good, key=lambda w: good[w][1])
        if top == own:
            return good
        out = dict(good)
        out[own] = out.pop(top)
        return out

    def missing(self):
        """1.57.4 (user's pictures: one survivor never placed, the others were): (who, [place, …]) of the only
        survivor not placed yet and the free rows of the list where it can stand – the list is N rows in steps
        of the placed ones' grid, the own one on top; None when not exactly one is missing."""
        faced = [(i, p) for i, p in enumerate(self._people) if p["face"] is not None]
        left = [i for i, p in faced if p["hud"] is None and i not in self.twins()]
        done = [p["hud"] for _i, p in faced if p["hud"] is not None]
        if len(left) != 1 or len(done) < 2:
            return None
        ys = sorted(a[1] for a in done)
        side = sorted(a[2] for a in done)[len(done) // 2]
        steps = [d / n for d in (b - a for a, b in zip(ys, ys[1:])) for n in (1, 2, 3)
                 if HUD_STEP[0] * side <= d / n <= HUD_STEP[1] * side]
        if not steps:
            return None
        step = min(steps, key=lambda st: abs(st / side - HUD_ROW))
        x = sorted(a[0] for a in done)[len(done) // 2]
        n = len(faced)
        free = set()
        for k in range(n):                               # where the list may start so that every placed row fits
            start = ys[0] - k * step
            rows = [start + j * step for j in range(n)]
            if all(any(abs(y - r) <= HUD_GRID * step for r in rows) for y in ys) and start > 0:
                free |= {round(r, 4) for r in rows if all(abs(r - y) > HUD_GRID * step for y in ys) and r < 1}
        return left[0], [(x, y, side) for y in sorted(free)]

    def place_last(self, who: int, scores: dict) -> bool:
        """``scores`` = {place: fit} of the missing survivor at the free rows of one look: the best one, when it fits
        at least ``HUD_LAST_FIT`` and the look before chose the same row; True when the board changed."""
        before = self.board().key()
        best = max(scores.items(), key=lambda kv: kv[1], default=(None, -1.0))
        last, self._last_seen = self._last_seen, (who, best[0]) if best[1] >= HUD_LAST_FIT else None
        if best[0] is not None and best[1] >= HUD_LAST_FIT and last == (who, best[0]):
            self._people[who]["hud"] = best[0]
        return self.board().key() != before

    def describe(self, scores: dict | None = None) -> str:
        """1.57.4: per survivor (no names: "S1" … in the order first seen) – own, place in the HUD found (with the
        last fit), slots read – for the diagnosis."""
        out = []
        board = self.board()
        for i, row in enumerate(board.rows):
            read = sum(1 for s in row.perks if s)
            extra = sum(1 for s in (row.item, row.offering) + row.addons if s)
            fit = f" {scores[i]:.2f}" if scores and i in scores else ""
            where = "HUD ja" if row.hud else "HUD nein"
            out.append(f"S{i + 1}{' (eigener)' if row.own else ''}: {where}{fit}, Perks {read}/4, sonst {extra}/4")
        return " · ".join(out) or "–"

    def scales(self, height: int) -> tuple:
        """1.57.7 (user: "geht viel zu lange bis es angezeigt wird"; one look at all nine sizes took 0.48 s): once a
        portrait is placed, the HUD's size is known – only its nearest size in ``HUD_SCALES`` and the two beside it
        are searched then."""
        sides = [p["hud"][2] * height for p in self._people if p["hud"] is not None]
        if sides and self.side > 0:
            self._ratio = float(np.median(sides)) / self.side       # kept for the next rounds (reset keeps it)
        ratio = getattr(self, "_ratio", None)
        self._scale_looks = getattr(self, "_scale_looks", 0) + 1
        if ratio is None and self.side > 0 and self._scale_looks % 4:
            ratio = HUD_LIST[3] * height / self.side     # 1.57.14: DBD's usual list first (every 4th look: all sizes)
        if ratio is None or self.side <= 0 or self._missed >= 2:
            return HUD_SCALES
        at = min(range(len(HUD_SCALES)), key=lambda i: abs(HUD_SCALES[i] - ratio))
        return HUD_SCALES[max(0, at - 1):at + 2]

    @property
    def placed(self) -> bool:
        """Every survivor seen with a portrait has its place in the HUD."""
        faced = [p for p in self._people if p["face"] is not None]
        return bool(faced) and all(p["hud"] is not None for p in faced)

    def _slot(self, p: dict, slot: int):
        c = p["counts"].get(slot, {})
        if not c:
            return None
        ranked = sorted(c.items(), key=lambda kv: -kv[1])
        if ranked[0][1] < self.need or (len(ranked) > 1 and ranked[1][1] == ranked[0][1]):
            return None
        return ranked[0][0]

    def _own(self, gold_only: bool = False) -> int:
        """The own survivor: the gold row of the menu (most looks), else the top portrait of the HUD's list once
        every survivor has its place there; -1 when not known."""
        gold = [(p["own"], i) for i, p in enumerate(self._people) if p["own"] * 2 > p["seen"]]
        if gold:
            return max(gold)[1]
        if gold_only or self.killer:                  # 1.57.36: the killer is none of the survivors
            return -1
        if self.placed and len(self._people) > 1:
            return min(range(len(self._people)), key=lambda i: self._people[i]["hud"][1])
        return -1

    def board(self) -> Board:
        own = self._own()
        rows = []
        for i, p in enumerate(self._people):
            names = [self._slot(p, s) for s in range(8)]
            rows.append(Row(perks=tuple(names[:4]), item=names[4], addons=tuple(names[5:7]), offering=names[7],
                            own=i == own, who=i,
                            face=p["face"], hud=p["hud"], pics=p.get("pics", ()), pics_n=p.get("pics_n", 0)))
        return Board(rows=tuple(rows), killer=self.killer)

    def reset(self) -> None:
        self.looks = 0
        self.side = 0.0
        self._hud_seen = {}
        self._last_seen = None
        self._missed = 0
        self._twin_rows = {}
        self._apart = set()
        self._name_seen = {}
        self.killer = False
        self._people.clear()                  # (the HUD's size, ``_ratio``, stays for the next round)
