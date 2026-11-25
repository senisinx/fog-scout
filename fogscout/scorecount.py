"""Score event tracker, step 4 (1.57.55): count each score event once over several looks.

A look gives the rows ``scoreevents.read_rows`` read (top to bottom). DBD shows an event for about 2.5–3 s; a new
one comes in at the top and pushes the others down by a row; while it slides in, its name is cut ("OVERY" for
RECOVERY); a lasting action (repairs, healing, a chase) shows one row whose points grow. So every row is given to
a *track*: an event seen before with the same category (when both are known), a fitting name (equal, one part of
the other, or alike) and a place at or below where it was last – rows never move up. A track not seen for
``GAP_S`` is one event: its category the most frequent one read, its points the most frequent reading of its last
part (a growing counter ends on its final value), "MAX" when most readings said so (the category is full; the
event gives nothing). A track seen only once or never read is dropped.

The ring around each event's icon shows how full its category is (``scoreevents.ring_progress``, 1.57.55). So a
category's total follows its events in time: an event's ring sets the total (absolute – a missed or doubled event
does not stay wrong), an event without one adds its points. A ring far below what was counted so far
(``RING_DROP_ABS`` + ``RING_DROP_REL``) is a misreading – a ring never empties – and only its points count. Measured
on 13 own rounds against the official per-category points: sum of the events 7.3 % off, newest ring blindly 5.9 %,
this 2.4 %.

Pure; no clock of its own – the caller passes the time of each look.
"""
from __future__ import annotations

import collections
import difflib
from dataclasses import dataclass, field

from .scoreevents import CATEGORIES, KILLER, SURVIVOR
from .textnorm import fold

CAP = 10000                # points a category can reach in a match (official data 11/2026: every full one is 10000)
GAP_S = 0.9                # a track not seen this long has ended (events stay 2.5–3 s; reading gaps ~0.5 s)
MIN_LOOKS = 2              # sightings an event needs (one look can be a mistaken row)
LAST_SHARE = 0.5           # the points of an event: the most frequent reading of this last part of its readings
UP_TOLERANCE = 0.6         # a row may seem up to this many name heights higher than before (it drifts while it fades)
NAME_ALIKE = 0.6           # difflib ratio for names that are not one part of the other
RING_LAST = 0.5            # an event's ring: the median of this last part of its readings (it may still fill)
RING_DROP_ABS = 500        # a ring this many points …
RING_DROP_REL = 0.1        # … plus this share below the running total is not believed
RING_FULL = 0.97           # a ring from here on says "full"
RING_JUMP_ABS = 1500       # 1.57.66: a ring this far above the total plus the event's own points is believed only when
                           # the category's next ring agrees (live: one ring misread as full on reddish wood set a
                           # category to 10 000 for the rest of the round)


@dataclass
class ScoreEvent:
    """One counted event: when it was first seen, its name, points (0 when "MAX"), category, capped."""
    t: float
    name: str
    points: int
    category: str
    capped: bool = False
    ring: float | None = None      # how full its category was (0..1), None: no ring read


@dataclass
class _Track:
    first: float
    last: float
    y: float
    h: float
    names: list = field(default_factory=list)
    cats: list = field(default_factory=list)
    readings: list = field(default_factory=list)     # (t, points, capped) of readable looks
    rings: list = field(default_factory=list)        # ring readings (0..1)
    looks: int = 0

    def name(self) -> str:
        if not self.names:
            return ""
        counts = collections.Counter(self.names)
        return max(counts, key=lambda n: (len(n), counts[n]))       # the longest: names are cut while sliding in

    def category(self):
        known = [c for c in self.cats if c]
        return collections.Counter(known).most_common(1)[0][0] if known else None


SHORT = {"brutality": "BRU", "deviousness": "DEV", "hunter": "HUN", "sacrifice": "SAC",
         "objective": "OBJ", "survival": "SUR", "altruism": "ALT", "boldness": "BOL"}


def line(totals: dict, full=()) -> tuple:
    """1.57.56: the overlay's line "Punkte" – (text, widest text) as ``PictureOverlay.set_score`` takes it:
    "BRU 4.3k · DEV 1.5k · HUN 8.3k · SAC MAX" (thousands, one decimal; a full category MAX), and the same with
    every number at its widest, so the line never changes its size. () without any category."""
    cats = [c for c in CATEGORIES if c in totals]
    if not cats:
        return ()

    def value(c):
        return "MAX" if c in full or totals[c] >= CAP else f"{totals[c] / 1000:.1f}k"
    text = " · ".join(f"{SHORT[c]} {value(c)}" for c in cats)
    widest = " · ".join(f"{SHORT[c]} 00.0k" for c in cats)
    return text, widest


def names_fit(a: str, b: str) -> bool:
    if not a or not b:
        return True
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= NAME_ALIKE


class ScoreCounter:
    """``feed(t, rows)`` once per look, ``flush()`` at the end of the match; ``events`` and ``totals()``."""

    def __init__(self, cap: int = CAP, gap_s: float = GAP_S, min_looks: int = MIN_LOOKS):
        self.cap = cap
        self.gap_s = gap_s
        self.min_looks = min_looks
        self.events: list[ScoreEvent] = []
        self.full: set = set()               # categories that showed "MAX"
        self.dropped = 0                     # tracks that were not counted (seen once, never read, no category)
        self._tracks: list[_Track] = []

    # -- looks ---------------------------------------------------------------------------------------------------
    def feed(self, t: float, rows) -> list[ScoreEvent]:
        """One look at time ``t`` (s) with its rows; returns the events that ended with it."""
        ended = self._end(t)
        live = [tr for tr in self._tracks]
        pairs = []
        for i, r in enumerate(rows):
            x0, y0, x1, y1 = r.word
            name, cat = fold(r.name), r.category
            for j, tr in enumerate(live):
                dy = y0 - tr.y
                if dy < -UP_TOLERANCE * tr.h:
                    continue
                known = tr.category()
                if cat and known and cat != known:
                    continue
                if not names_fit(name, fold(tr.name())):
                    continue
                pairs.append((dy / max(1.0, tr.h), i, j))
        pairs.sort()
        used_r, used_t = set(), set()
        for _cost, i, j in pairs:
            if i in used_r or j in used_t:
                continue
            used_r.add(i)
            used_t.add(j)
            self._add(live[j], t, rows[i])
        for i, r in enumerate(rows):
            if i not in used_r:
                x0, y0, x1, y1 = r.word
                tr = _Track(first=t, last=t, y=y0, h=max(1, y1 - y0))
                self._tracks.append(tr)
                self._add(tr, t, r)
        return ended

    def flush(self) -> list[ScoreEvent]:
        """End every track (the match is over)."""
        return self._end(float("inf"))

    # -- results -------------------------------------------------------------------------------------------------
    def totals(self) -> dict:
        """Points per category so far, its events in time: a believable ring sets the total, else the event's points
        add to it; at most ``cap``, a category that showed MAX is full."""
        out = {}
        for c in CATEGORIES:
            total = 0.0
            mine = sorted((e for e in self.events if e.category == c), key=lambda e: e.t)
            for i, e in enumerate(mine):
                ring = None if e.ring is None else e.ring * self.cap
                ok = ring is not None and ring >= total - (RING_DROP_ABS + RING_DROP_REL * total)
                if ok and ring > total + e.points + RING_JUMP_ABS and not e.capped:
                    # a jump the event's points do not explain: only when a later ring of the category is up there
                    # too; the newest ring (none after it yet) is believed unless it says "full" – the misreadings
                    # seen were red all round
                    later = [n.ring * self.cap for n in mine[i + 1:] if n.ring is not None]
                    ok = (any(v >= ring - (RING_DROP_ABS + RING_DROP_REL * ring) for v in later) if later
                          else e.ring < RING_FULL)
                if ok:
                    total = ring
                else:
                    total += e.points
            out[c] = self.cap if c in self.full else min(self.cap, round(total))
        return out

    def role(self):
        """"killer"/"survivor" by the categories seen, None before any event."""
        k = sum(e.category in KILLER for e in self.events)
        s = sum(e.category in SURVIVOR for e in self.events)
        return None if k == s == 0 else "killer" if k >= s else "survivor"

    # -- inside --------------------------------------------------------------------------------------------------
    @staticmethod
    def _add(tr: _Track, t, r):
        tr.last = t
        tr.y = r.word[1]
        tr.h = max(1, r.word[3] - r.word[1])
        tr.looks += 1
        if r.name:
            tr.names.append(fold(r.name))
        tr.cats.append(r.category)
        if r.capped or r.points is not None:
            tr.readings.append((t, r.points, r.capped))
        ring = getattr(r, "ring", None)
        if ring is not None:
            tr.rings.append(ring)

    def _end(self, t) -> list[ScoreEvent]:
        ended, keep = [], []
        for tr in self._tracks:
            if t - tr.last > self.gap_s:
                ev = self._event(tr)
                if ev is None:
                    self.dropped += 1
                else:
                    ended.append(ev)
            else:
                keep.append(tr)
        self._tracks = keep
        for ev in sorted(ended, key=lambda e: e.t):
            self.events.append(ev)
            if ev.capped:
                self.full.add(ev.category)
        return ended

    def _event(self, tr: _Track):
        cat = tr.category()
        if tr.looks < self.min_looks or not tr.readings or cat is None:
            return None
        capped = sum(c for _t, _p, c in tr.readings) * 2 > len(tr.readings)
        points = 0
        if not capped:
            values = [p for _t, p, c in tr.readings if not c and p is not None]
            if not values:
                return None
            tail = values[int(len(values) * (1 - LAST_SHARE)):] or values
            counts = collections.Counter(tail)
            points = max(counts, key=lambda v: (counts[v], v))
        ring = None
        if tr.rings:
            tail = sorted(tr.rings[int(len(tr.rings) * (1 - RING_LAST)):] or tr.rings)
            ring = tail[len(tail) // 2]
        return ScoreEvent(t=tr.first, name=tr.name(), points=points, category=cat, capped=capped, ring=ring)
