"""1.57.67 (user: "ich will, dass wir 1:1 die DBD-Icons benutzen und nicht die eigenen"): the icons of the score
categories as the game itself shows them – taken from the user's own screen, never shipped.

The game's icon pictures belong to Behaviour; they do not go into this public repository or its releases. But the
tracker sees them anyway: beside every score event stands the icon of its category in a ring. ``Collector`` takes the
picture inside the ring (``scoreevents.icon_picture``: the pale drawing as a grey mask) of rows whose category and ring
were read for sure, and after ``KEEP`` sightings of a category picks the one most like their median – a single sharp
sighting, never an outlier (a row sliding in, a bright background). It is saved once as
``<data_dir>/cache/score_icons/<category>.png`` (the program's own cache, like every other picture there; deleting the
folder makes it learn again) and ``scoreview`` draws it instead of its own drawing. Until a category was seen in a
match, its drawn icon stands in.

Screen pixels only (CLAUDE.md), nothing sent, nothing read from the game's files. Pure but for the two file helpers.
"""
from __future__ import annotations

import io
import os

import numpy as np

from .scoreevents import CATEGORIES

FOLDER = os.path.join("cache", "score_icons")
SIZE = 96                  # side of a stored icon (scoreevents.ICON_PIC)
KEEP = 7                   # sightings of a category before one is picked
MIN_INK = 0.04             # share of bright pixels an icon needs – an empty ring is no icon
MAX_BYTES = 200_000        # a stored icon is a few kB; anything bigger is not ours


class Collector:
    """``add(category, mask)`` per sure sighting; returns the picked mask (uint8, SIZE×SIZE) once per category."""

    def __init__(self, done=(), keep: int = KEEP):
        self.keep = keep
        self.done = set(done)
        self._seen: dict = {}

    def add(self, category: str, mask):
        if category not in CATEGORIES or category in self.done or mask is None:
            return None
        m = np.asarray(mask)
        if m.shape != (SIZE, SIZE) or float((m > 128).mean()) < MIN_INK:
            return None
        seen = self._seen.setdefault(category, [])
        seen.append(m.astype(np.float32))
        if len(seen) < self.keep:
            return None
        median = np.median(seen, axis=0)
        mc = median - median.mean()

        def alike(a):
            ac = a - a.mean()
            n = float(np.linalg.norm(ac) * np.linalg.norm(mc))
            return float((ac * mc).sum() / n) if n > 0 else -1.0
        best = max(seen, key=alike)
        self.done.add(category)
        del self._seen[category]
        return np.clip(best, 0, 255).astype(np.uint8)


def path(data_dir: str, category: str) -> str:
    return os.path.join(data_dir, FOLDER, f"{category}.png")


def save(data_dir: str, category: str, mask) -> str:
    """Write the picked icon (complete or not at all – fsops.write_atomic); returns its path."""
    from PIL import Image
    from . import fsops
    if category not in CATEGORIES:
        raise ValueError(category)
    buf = io.BytesIO()
    Image.fromarray(np.asarray(mask, np.uint8), "L").save(buf, "PNG")
    target = path(data_dir, category)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fsops.write_atomic(target, buf.getvalue())
    return target


def load(data_dir: str) -> dict:
    """{category: PIL "L" picture} of the icons learned so far – only our own names, sizes and plain files."""
    from PIL import Image
    out = {}
    for c in CATEGORIES:
        p = path(data_dir, c)
        try:
            if os.path.islink(p) or not os.path.isfile(p) or os.path.getsize(p) > MAX_BYTES:
                continue
            with Image.open(p) as im:
                if im.format != "PNG" or im.size != (SIZE, SIZE):
                    continue
                out[c] = im.convert("L").copy()
        except (OSError, ValueError, SyntaxError):
            continue
    return out
