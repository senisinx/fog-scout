"""The overlay element "Diagramme" (1.57.73, user: "in overlay funktionen entfernen und mit diagrammen etc evtl versehen.
evtl so einbauen das ich diese diagramme selber aussuchen kann welche man ansehen will"): small charts in the black
bar – the user picks which (setting ``overlay.charts``, in the order of ``CATALOGUE``).

Pure: the catalogue, the series built from what the program already keeps (pings of the open round, the system
values' readings, the rounds of today joined with the stats page's matches, the points counted top right, the
bloodpoint balance of the lobby) and the drawing (PIL only, no window). Nothing new is read from the game and
nothing goes anywhere. The App mixin is app_charts.ChartsCard.

Never breathe: every chart picked is drawn at the same size whatever its values – one without values yet shows "–"
and an empty plot, so the card keeps its size while a round fills it.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .i18n import N_, _

# id, title in the card (upper case like the system values), name in the settings
CATALOGUE = (("ping", N_("PING"), N_("Ping-Verlauf der Runde")),
             ("score", N_("PUNKTE"), N_("Punkte dieser Runde je Kategorie")),
             ("time", N_("RUNDENZEIT"), N_("Rundenzeit gegen den Schnitt der Map")),
             ("kills", N_("KILLS HEUTE"), N_("Kills heute je Runde (Killer)")),
             ("form", N_("LETZTE 10"), N_("Letzte 10 Runden (gut, mittel, schlecht)")),
             ("map", N_("DIESE MAP"), N_("Bilanz auf dieser Map")),
             ("wait", N_("SUCHE HEUTE"), N_("Suchzeit heute je Runde")),
             ("bp", N_("BLOODPOINTS"), N_("Bloodpoints bis zur Obergrenze")),
             ("fps", N_("FPS"), N_("FPS-Verlauf (HWiNFO)")),
             ("gpu", N_("GPU"), N_("GPU-Temperatur")),
             ("cpu", N_("CPU"), N_("CPU-Last")))
IDS = tuple(c[0] for c in CATALOGUE)
DEFAULT = ["ping", "score", "kills"]
SYSTEM = ("fps", "gpu", "cpu")             # need the system monitor running (app_charts asks for it)
MAX_PICKED = 6                             # more would not fit a bar at a sensible size

CHART_SCALE = (60, 200)                    # size slider, percent
CHART_WIDTH = 0.17                         # the card's width at 100 %, share of the game height (≈ 245 px at 1440)
POINTS = 40                                # a line chart shows at most this many points (averaged buckets)
KEEP_S = 600                               # … of the last ten minutes of system readings
FORM_N = 10
BP_CAP = 5_000_000                         # = bloodpoints.CAP (test_the_chart_caps_match_the_readers)
SCORE_CAP = 10_000                         # = scorecount.CAP: a full category
KILLER_CATS = ("brutality", "deviousness", "hunter", "sacrifice")      # = scoreevents.KILLER
SURVIVOR_CATS = ("objective", "survival", "altruism", "boldness")      # = scoreevents.SURVIVOR
CAT_NAMES = {"brutality": N_("Brutalität"), "deviousness": N_("Hinterlist"), "hunter": N_("Jäger"),
             "sacrifice": N_("Opferung"), "objective": N_("Ziel"), "survival": N_("Überleben"),
             "altruism": N_("Altruismus"), "boldness": N_("Kühnheit")}


def picked(o: dict) -> list:
    """The charts switched on (setting overlay.charts), known ids only, in catalogue order, at most MAX_PICKED."""
    want = o.get("charts")
    if not isinstance(want, (list, tuple)):
        want = DEFAULT
    want = {c for c in want if isinstance(c, str)}
    return [c for c in IDS if c in want][:MAX_PICKED]


def chart_scale(o: dict) -> float:
    """Size factor of the card (setting overlay.charts_scale)."""
    return min(CHART_SCALE[1], max(CHART_SCALE[0], float(o.get("charts_scale", 1.0)) * 100)) / 100


def needs_system(o: dict) -> bool:
    """Whether a chart of the system values is on (then the monitor runs even with the system values off)."""
    return bool(o.get("show_charts", False)) and any(c in SYSTEM for c in picked(o))


@dataclass(frozen=True)
class Chart:
    """One chart as drawn: ``kind`` line / bars / hbars / dots / progress / pair; ``data`` its values (None or an
    empty tuple: nothing yet); ``lo``/``hi`` the value axis; ``ticks`` labelled lines; ``labels`` under bars or
    beside the rows of hbars; ``value`` the figure top right."""
    id: str
    kind: str
    data: tuple = ()
    lo: float = 0.0
    hi: float = 1.0
    ticks: tuple = ()
    labels: tuple = ()
    value: str = "–"

    @property
    def title(self) -> str:
        return _(dict((c[0], c[1]) for c in CATALOGUE)[self.id])


# ------------------------------------------------------------------ series
def buckets(values, n: int = POINTS) -> tuple:
    """At most ``n`` points of ``values`` (the latest last): equal runs averaged; fewer values as they are."""
    vals = [float(v) for v in values if v is not None and math.isfinite(v)]
    if len(vals) <= n:
        return tuple(vals)
    out = []
    for i in range(n):
        part = vals[i * len(vals) // n:(i + 1) * len(vals) // n]
        out.append(sum(part) / len(part))
    return tuple(out)


def nice_top(v: float, step: float, floor: float) -> float:
    """The axis top: ``v`` rounded up to ``step``, never below ``floor``."""
    return max(floor, math.ceil(max(0.0, v) / step) * step)


def ping_chart(pings) -> Chart:
    pts = buckets(pings)
    if len(pts) < 2:
        return Chart("ping", "line", lo=0, hi=80, ticks=(0, 40, 80))
    hi = nice_top(max(pts), 40, 80)
    return Chart("ping", "line", pts, 0, hi, (0, hi / 2, hi), value=f"{pts[-1]:.0f} ms")


def system_chart(cid: str, values) -> Chart:
    pts = buckets(values)
    if cid == "fps":
        hi = nice_top(max(pts), 30, 60) if pts else 60
        c = Chart("fps", "line", pts, 0, hi, (0, hi / 2, hi), value=f"{pts[-1]:.0f}" if pts else "–")
    elif cid == "gpu":
        hi = nice_top(max(pts), 10, 90) if pts else 90
        c = Chart("gpu", "line", pts, 30, hi, (30, hi), value=f"{pts[-1]:.0f} °C" if pts else "–")
    else:
        c = Chart("cpu", "line", pts, 0, 100, (0, 50, 100), value=f"{pts[-1]:.0f} %" if pts else "–")
    return c if len(pts) >= 2 else Chart(c.id, "line", (), c.lo, c.hi, c.ticks)


def score_chart(totals: dict, role: str) -> Chart:
    """The points of the round per category of its role (the role unknown: the side with points)."""
    totals = {k: v for k, v in (totals or {}).items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    cats = KILLER_CATS if role == "killer" or (role != "survivor" and any(c in totals for c in KILLER_CATS)) \
        else SURVIVOR_CATS
    data = tuple(min(SCORE_CAP, max(0, int(totals.get(c, 0)))) for c in cats)
    value = f"{sum(data):,}".replace(",", " ") if any(data) else "–"
    return Chart("score", "hbars", data if any(data) else (), 0, SCORE_CAP, labels=tuple(_(CAT_NAMES[c]) for c in cats),
                 value=value)


def time_chart(seconds: float | None, average: float | None) -> Chart:
    """This round's time against the average round on this map (``pair``: now, average)."""
    if not seconds or seconds < 0:
        seconds = 0.0
    if not average:
        return Chart("time", "pair", (seconds, 0.0) if seconds else (), 0, max(60.0, seconds * 1.15),
                     value=clock(seconds) if seconds else "–")
    return Chart("time", "pair", (seconds, average), 0, max(seconds, average) * 1.15, value=clock(seconds))


def clock(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 60}:{s % 60:02d}"


def kills_chart(kills) -> Chart:
    """Today's killer rounds in order (kills each, unknown left out)."""
    ks = tuple(int(k) for k in kills if k is not None)
    if not ks:
        return Chart("kills", "bars", lo=0, hi=4, ticks=(0, 2, 4))
    avg = sum(ks) / len(ks)
    return Chart("kills", "bars", ks[-12:], 0, 4, (0, 2, 4), value=_("Ø {n}", n=f"{avg:.1f}".replace(".", ",")))


def outcome(role: str, kills=None, escaped=None) -> str:
    """"W" (killer 3+ kills, survivor escaped), "D" (killer 2), "L" (killer 0–1, survivor died) or "?" (no match
    data)."""
    if role == "killer" and kills is not None:
        return "W" if kills >= 3 else "D" if kills == 2 else "L"
    if role == "survivor" and escaped is not None:
        return "W" if escaped else "L"
    return "?"


def form_chart(outcomes) -> Chart:
    seq = tuple(o for o in outcomes if o in ("W", "D", "L", "?"))[-FORM_N:]
    if not seq:
        return Chart("form", "dots")
    known = [o for o in seq if o != "?"]
    value = _("{w} von {n}", w=sum(1 for o in known if o == "W"), n=len(known)) if known else "–"
    return Chart("form", "dots", seq, value=value)


def map_chart(role: str, results) -> Chart:
    """The rounds on this map: as the killer how many ended with 0…4 kills, as a survivor died / escaped."""
    if role == "survivor":
        esc = [e for e in results if e is not None]
        data = (sum(1 for e in esc if not e), sum(1 for e in esc if e))
        labels = (_("tot"), _("entk."))
        value = _("{n} Runden", n=len(esc)) if esc else "–"
    else:
        ks = [int(k) for k in results if k is not None]
        data = tuple(sum(1 for k in ks if k == i) for i in range(5))
        labels = ("0", "1", "2", "3", "4")
        value = _("{n} Runden", n=len(ks)) if ks else "–"
    if not any(data):
        return Chart("map", "bars", (), 0, 4, (0,), labels)
    hi = nice_top(max(data), 2, 2)
    return Chart("map", "bars", data, 0, hi, (0, hi), labels, value)


def wait_chart(waits) -> Chart:
    ws = tuple(float(w) for w in waits if w is not None and w >= 0)[-12:]
    if not ws:
        return Chart("wait", "bars", lo=0, hi=180, ticks=(0, 90, 180))
    hi = nice_top(max(ws), 60, 120)
    return Chart("wait", "bars", ws, 0, hi, (0, hi), value=_("Ø {t}", t=clock(sum(ws) / len(ws))))


def bp_chart(balance) -> Chart:
    if balance is None or balance < 0:
        return Chart("bp", "progress", (), 0, BP_CAP)
    shown = f"{int(balance):,}".replace(",", " ")
    return Chart("bp", "progress", (min(float(balance), BP_CAP),), 0, BP_CAP, value=shown)


# ------------------------------------------------------------------ drawing
LOOKS = ("classic", "map", "glass", "line")      # setting overlay.charts_look (1.57.74, the user picked "alles wählbar")


@dataclass(frozen=True)
class Look:
    """How the card is drawn: ``accent`` (the window theme's colour), ``backdrop`` (the dark area – classic only),
    ``style`` one of LOOKS, ``dense`` = one row per chart (title, a small plot, the figure)."""
    accent: tuple = (201, 162, 39, 255)
    backdrop: bool = True
    style: str = "classic"
    dense: bool = False


@dataclass(frozen=True)
class Palette:
    fg: tuple
    dim: tuple
    grid: tuple
    accent: tuple
    good: tuple
    bad: tuple
    back: tuple | None          # the area behind the card (None: nothing)
    edge: tuple | None          # its outline
    radius: float               # … corner, share of the padding
    area: float                 # share of the accent in the area under a line (0: none)
    rules: bool                 # a hairline between the charts
    hollow: bool                # bars and dots as outlines (the newest bar / a good round filled)


FG = (232, 233, 235, 255)
DIM = (150, 156, 166, 255)
GRID = (62, 66, 74, 255)
BACK = (16, 17, 19, 214)
GOOD = (111, 207, 138, 255)
BAD = (224, 103, 95, 255)


def palette(look: Look) -> Palette:
    """The colours of a look. "map": bone on nothing with ochre marks and hairlines (the window's Kartentisch
    theme); "glass": a light translucent area with a thin edge (the overlay style of that name); "line": strokes and
    figures only, one colour."""
    if look.style == "map":
        return Palette((221, 214, 195, 255), (143, 148, 138, 255), (58, 74, 71, 255), (201, 138, 46, 255),
                       (143, 183, 132, 255), (196, 102, 77, 255), None, None, 0.0, 0.0, True, False)
    if look.style == "glass":
        return Palette((242, 243, 245, 255), (176, 182, 191, 255), (96, 100, 108, 255), look.accent,
                       (127, 214, 154, 255), (238, 128, 121, 255), (44, 46, 52, 170), (120, 124, 132, 255), 1.6,
                       0.18, False, False)
    if look.style == "line":
        return Palette((215, 217, 220, 255), (125, 131, 140, 255), (48, 51, 58, 255), (215, 217, 220, 255),
                       (215, 217, 220, 255), (107, 112, 120, 255), None, None, 0.0, 0.0, False, True)
    return Palette(FG, DIM, GRID, look.accent, GOOD, BAD, BACK if look.backdrop else None, None, 1.0, 0.22, False,
                   False)


# heights as shares of the card's width (the width follows the bar, never the values)
TITLE_H = 0.085
GAP_H = 0.035
PLOT_H = {"line": 0.30, "bars": 0.30, "hbars": 0.36, "dots": 0.09, "progress": 0.07, "pair": 0.17}
PAD = 0.045
ROW_H = 0.105               # dense: one row per chart
DENSE_NAME, DENSE_VALUE = 0.42, 0.35     # … its name and figure columns (the small plot takes the rest)


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False):
    names = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else \
        ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, max(6, size))
        except OSError:
            continue
    return ImageFont.load_default()


def card_size(kinds, width: int, dense: bool = False) -> tuple:
    """(w, h) of a card with charts of these ``kinds`` at ``width`` – the same for any values."""
    w = max(60, int(width))
    pad = max(3, int(w * PAD))
    if dense:
        return w, 2 * pad + int(w * ROW_H) * len(kinds)
    parts = [int(w * TITLE_H) + int(w * PLOT_H.get(k, 0.3)) for k in kinds]
    return w, 2 * pad + sum(parts) + int(w * GAP_H) * max(0, len(parts) - 1)


def draw(charts, width: int, look: Look = Look()) -> Image.Image:
    """The card, ``width`` px wide: each chart a title row (name left, figure right) and its plot below – or,
    ``look.dense``, one row per chart with a small plot between name and figure."""
    w, h = card_size([c.kind for c in charts], width, look.dense)
    pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(pic)
    p = palette(look)
    pad = max(3, int(w * PAD))
    if p.back is not None:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=max(3, int(pad * p.radius)), fill=p.back, outline=p.edge)
    back = p.back or (0, 0, 0, 0)
    title_f = _font(int(w * TITLE_H * 0.72), True)
    small = _font(int(w * 0.05))
    y = pad
    if look.dense:
        rh = int(w * ROW_H)
        # three fixed columns: name, small plot, figure (the widest figures – "18 Runden", "812 340" – fit theirs)
        mid = (pad + int(w * DENSE_NAME), w - pad - int(w * DENSE_VALUE))
        row_f = _font(int(w * 0.047), True)
        value_f = _font(int(w * 0.054), True)
        for i, c in enumerate(charts):
            if p.rules and i:
                d.line((pad, y, w - pad, y), fill=p.grid, width=1)
            d.text((pad, y + rh / 2), c.title, font=row_f, fill=p.dim, anchor="lm")
            d.text((w - pad, y + rh / 2), c.value, font=value_f, fill=p.fg, anchor="rm")
            _mini(d, c, (mid[0], y + rh * 0.22, mid[1], y + rh * 0.78), p, back)
            y += rh
        return pic
    for i, c in enumerate(charts):
        if p.rules and i:
            d.line((pad, y - int(w * GAP_H) // 2, w - pad, y - int(w * GAP_H) // 2), fill=p.grid, width=1)
        th = int(w * TITLE_H)
        d.text((pad, y + th / 2), c.title, font=title_f, fill=p.dim, anchor="lm")
        d.text((w - pad, y + th / 2), c.value, font=title_f, fill=p.fg, anchor="rm")
        y += th
        ph = int(w * PLOT_H.get(c.kind, 0.3))
        _plot(d, c, (pad, y, w - pad, y + ph), small, p, back)
        y += ph + int(w * GAP_H)
    return pic


def _bar(d, box, colour, p: Palette, solid: bool = False) -> None:
    if p.hollow and not solid:
        d.rectangle(box, outline=colour, width=1)
    else:
        d.rectangle(box, fill=colour)


def _dot(d, box, o, p: Palette) -> None:
    """One round of the form: None = no round, "?" = no match data, else W / D / L."""
    if o is None:
        d.ellipse(box, outline=p.grid, width=1)
    elif o == "?":
        d.ellipse(box, outline=p.dim, width=1)
    elif p.hollow and o != "W":
        d.ellipse(box, outline={"D": p.dim, "L": p.bad}[o], width=1)
    else:
        d.ellipse(box, fill={"W": p.good, "D": p.dim, "L": p.bad}[o])


def _under(p: Palette, back) -> tuple | None:
    """The colour of the area under a line: the accent mixed into what is behind it (ImageDraw replaces pixels, it
    does not blend)."""
    if not p.area:
        return None
    return tuple(int(a * p.area + b * (1 - p.area)) for a, b in zip(p.accent[:3], back[:3])) + (max(back[3], 90),)


def _plot(d, c: Chart, box, font, p: Palette, back) -> None:
    x0, y0, x1, y1 = box
    if c.kind in ("line", "bars"):
        left = x0 + int((x1 - x0) * 0.13)
        bottom = y1 - (int((y1 - y0) * 0.2) if c.labels else 0)
        span = (c.hi - c.lo) or 1.0

        def yv(v):
            return bottom - (min(max(v, c.lo), c.hi) - c.lo) / span * (bottom - y0 - 2) - 1
        for t in c.ticks:
            d.line((left, yv(t), x1, yv(t)), fill=p.grid, width=1)
            d.text((left - 3, yv(t)), _tick(t), font=font, fill=p.dim, anchor="rm")
        if not c.data:
            return
        n = len(c.data)
        if c.kind == "line":
            xs = [left + i * (x1 - left) / max(1, n - 1) for i in range(n)]
            pts = [(x, yv(v)) for x, v in zip(xs, c.data)]
            fill = _under(p, back)
            if fill:
                d.polygon([(left, yv(c.lo))] + pts + [(xs[-1], yv(c.lo))], fill=fill)
            d.line(pts, fill=p.accent, width=max(1, int((x1 - x0) / 110)), joint="curve")
            r = max(2, int((x1 - x0) / 80))
            d.ellipse((pts[-1][0] - r, pts[-1][1] - r, pts[-1][0] + r, pts[-1][1] + r), fill=p.fg)
        else:
            bw = (x1 - left) / n
            for i, v in enumerate(c.data):
                bx = left + i * bw + bw * 0.18
                last = i == n - 1 and not c.labels
                if v > c.lo:
                    _bar(d, (bx, yv(v), bx + bw * 0.64, yv(c.lo)), p.fg if last else p.accent, p, solid=last)
                if c.labels and i < len(c.labels):
                    d.text((bx + bw * 0.32, y1), c.labels[i], font=font, fill=p.dim, anchor="md")
    elif c.kind == "hbars":
        rows = len(c.labels) or 1
        rh = (y1 - y0) / rows
        label_w = int((x1 - x0) * 0.34)
        num_w = int((x1 - x0) * 0.16)
        for i, name in enumerate(c.labels):
            cy = y0 + rh * (i + 0.5)
            d.text((x0, cy), name, font=font, fill=p.fg, anchor="lm")
            bx0, bx1 = x0 + label_w, x1 - num_w
            bh = max(2, rh * 0.45)
            d.rectangle((bx0, cy - bh / 2, bx1, cy + bh / 2), fill=p.grid)
            v = c.data[i] if i < len(c.data) else 0
            if v:
                d.rectangle((bx0, cy - bh / 2, bx0 + (bx1 - bx0) * min(1.0, v / (c.hi or 1)), cy + bh / 2),
                            fill=p.accent)
            text = "MAX" if v >= c.hi else (f"{v / 1000:.1f}k" if v else "–")
            d.text((x1, cy), text, font=font, fill=p.fg, anchor="rm")
    elif c.kind == "dots":
        _dots(d, c, box, p)
    elif c.kind == "progress":
        _progress(d, c, box, p)
    elif c.kind == "pair":
        label_w = int((x1 - x0) * 0.26)
        rh = (y1 - y0) / 2
        for i, (name, col) in enumerate(((_("jetzt"), p.accent), (_("Schnitt"), p.dim))):
            cy = y0 + rh * (i + 0.5)
            d.text((x0, cy), name, font=font, fill=p.dim, anchor="lm")
            v = c.data[i] if i < len(c.data) else 0
            bh = max(2, rh * 0.5)
            if v:
                d.rectangle((x0 + label_w, cy - bh / 2, x0 + label_w + (x1 - x0 - label_w) * min(1.0, v / c.hi),
                             cy + bh / 2), fill=col)


def _dots(d, c: Chart, box, p: Palette) -> None:
    x0, y0, x1, y1 = box
    step = (x1 - x0) / FORM_N
    r = max(2, min(step * 0.36, (y1 - y0) / 2))
    cy = (y0 + y1) / 2
    for i in range(FORM_N):
        cx = x0 + step * (i + 0.5)
        _dot(d, (cx - r, cy - r, cx + r, cy + r), c.data[i] if i < len(c.data) else None, p)


def _progress(d, c: Chart, box, p: Palette) -> None:
    x0, y0, x1, y1 = box
    r = int(y1 - y0) // 2
    d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=p.grid)
    if c.data:
        share = min(1.0, max(0.0, c.data[0] / (c.hi or 1)))
        if share > 0:
            d.rounded_rectangle((x0, y0, x0 + max(y1 - y0, (x1 - x0) * share), y1), radius=r, fill=p.accent)


def _mini(d, c: Chart, box, p: Palette, back) -> None:
    """The small plot of a dense row: a line without axis, small bars, four short bars (points), the dots, a thin
    bar (progress; pair: now against the average as a mark)."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    if c.kind == "line":
        if len(c.data) < 2:
            d.line((x0, y1, x1, y1), fill=p.grid, width=1)
            return
        span = (c.hi - c.lo) or 1.0
        pts = [(x0 + i * (x1 - x0) / (len(c.data) - 1), y1 - (min(max(v, c.lo), c.hi) - c.lo) / span * h)
               for i, v in enumerate(c.data)]
        d.line(pts, fill=p.accent, width=max(1, int((x1 - x0) / 70)), joint="curve")
        r = max(1.5, h / 9)
        d.ellipse((pts[-1][0] - r, pts[-1][1] - r, pts[-1][0] + r, pts[-1][1] + r), fill=p.fg)
    elif c.kind == "bars":
        d.line((x0, y1, x1, y1), fill=p.grid, width=1)
        n = len(c.data)
        for i, v in enumerate(c.data):
            bw = (x1 - x0) / n
            last = i == n - 1 and not c.labels
            if v > c.lo:
                _bar(d, (x0 + i * bw + 1, y1 - (v - c.lo) / ((c.hi - c.lo) or 1) * h, x0 + (i + 1) * bw - 1, y1),
                     p.fg if last else p.accent, p, solid=last)
    elif c.kind == "hbars":
        n = len(c.labels) or 1
        gap = max(2, (x1 - x0) * 0.03)
        bw = (x1 - x0 - gap * (n - 1)) / n
        for i in range(n):
            bx = x0 + i * (bw + gap)
            d.rectangle((bx, y0 + h * 0.3, bx + bw, y1 - h * 0.3), fill=p.grid)
            v = c.data[i] if i < len(c.data) else 0
            if v:
                d.rectangle((bx, y0 + h * 0.3, bx + bw * min(1.0, v / (c.hi or 1)), y1 - h * 0.3), fill=p.accent)
    elif c.kind == "dots":
        _dots(d, c, (x0, y0 + h * 0.1, x1, y1 - h * 0.1), p)
    elif c.kind == "progress":
        _progress(d, c, (x0, y0 + h * 0.3, x1, y1 - h * 0.3), p)
    elif c.kind == "pair":
        d.rectangle((x0, y0 + h * 0.3, x1, y1 - h * 0.3), fill=p.grid)
        if c.data and c.hi:
            d.rectangle((x0, y0 + h * 0.3, x0 + (x1 - x0) * min(1.0, c.data[0] / c.hi), y1 - h * 0.3), fill=p.accent)
            if len(c.data) > 1 and c.data[1]:
                mx = x0 + (x1 - x0) * min(1.0, c.data[1] / c.hi)
                d.line((mx, y0, mx, y1), fill=p.fg, width=max(1, int(h / 8)))


def _tick(v: float) -> str:
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


# ------------------------------------------------------------------ samples (preview, "Overlay testen")
def sample(cid: str) -> Chart:
    """Made-up values to see and place the card before a round filled it."""
    if cid == "ping":
        return ping_chart([29, 28, 30, 27, 28, 41, 63, 35, 29, 28, 28, 27, 29, 30, 28, 28])
    if cid == "score":
        return score_chart({"brutality": 4200, "deviousness": 1400, "hunter": 3100, "sacrifice": 2600}, "killer")
    if cid == "time":
        return time_chart(134, 612)
    if cid == "kills":
        return kills_chart([3, 4, 2, 3, 1, 4, 3])
    if cid == "form":
        return form_chart("WWLWDWWLWW")
    if cid == "map":
        return map_chart("killer", [0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4])
    if cid == "wait":
        return wait_chart([95, 130, 72, 160, 88, 102, 68])
    if cid == "bp":
        return bp_chart(812_340)
    if cid == "fps":
        return system_chart("fps", [141, 143, 140, 138, 142, 121, 98, 135, 141, 144, 142, 140])
    if cid == "gpu":
        return system_chart("gpu", [58, 59, 60, 61, 61, 62, 63, 63, 63, 64, 63, 63])
    return system_chart("cpu", [31, 33, 35, 38, 36, 52, 61, 44, 38, 36, 35, 37])


class SystemHistory:
    """The system values' readings of the last ``KEEP_S`` seconds (one per new snapshot) – fps, gpu_temp,
    cpu_load. Only filled while a chart of them is on."""

    def __init__(self, keep_s: float = KEEP_S):
        self.keep_s = keep_s
        self.rows: list = []           # (t, fps, gpu_temp, cpu_load)
        self._last_t = None

    def add(self, snap) -> bool:
        """True when a new reading was kept."""
        t = getattr(snap, "t", 0.0)
        if not t or t == self._last_t:
            return False
        self._last_t = t
        self.rows.append((t, snap.fps, snap.gpu_temp, snap.cpu_load))
        cut = t - self.keep_s
        while self.rows and self.rows[0][0] < cut:
            self.rows.pop(0)
        return True

    def values(self, cid: str) -> list:
        i = {"fps": 1, "gpu": 2, "cpu": 3}[cid]
        return [r[i] for r in self.rows if r[i] is not None]

    def clear(self) -> None:
        self.rows.clear()
        self._last_t = None


def today_outcomes(rounds, off: dict, now: float | None = None) -> list:
    """(role, kills, escaped) of today's normal rounds in time order – ``off`` = {id(round): match} of the joined
    stats-page data (kills/escaped None without one)."""
    from . import history, official
    since = history.period_start("day", time.time() if now is None else now)
    out = []
    for r in sorted((r for r in rounds if r.t >= since and history.normal(r)), key=lambda r: r.t):
        m = off.get(id(r))
        out.append((r.role, official.kills(m) if m is not None else None,
                    official.escaped(m) if m is not None else None))
    return out
