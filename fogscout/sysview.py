"""Other looks of the overlay's system values (1.57.75, user picked three of five drafts: "die drei gefallen mir" –
Kurven, Messleisten, Zwei Zeilen): the same readings as the rows (sysinfo.Snapshot – nothing new is read), drawn as
a picture instead of text rows. Setting overlay.hud_view: "rows" (as before, sysinfo.hud_rows) or one of VIEWS.

Pure (PIL only). Never breathes: a view has one size for a width whatever the values – a value that is missing
(no HWiNFO: FPS, CPU temperature, hot spot) shows "–" in its place.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import charts, sysinfo
from .i18n import _

VIEWS = ("curves", "meters", "compact")
WIDTH = 0.165                # the card's width as a share of the system values' height setting (≈ 238 px at 1440)

FG = (232, 233, 235, 255)
DIM = (150, 156, 166, 255)
GRID = (62, 66, 74, 255)
BACK = (16, 17, 19, 214)
OK = (111, 207, 138, 255)
WARN = (230, 180, 80, 255)
BAD = (239, 111, 102, 255)
# where a value turns yellow / red: the temperatures as in the rows (sysinfo), the rest chosen with the user's draft
FPS_LOW, FPS_BAD = 110, 70
FULL_WARN, FULL_BAD = 0.85, 0.93             # share of VRAM / RAM in use
PING_WARN, PING_BAD = 45, 80
FPS_TOP = 165                                # the meters' and curves' full scale (higher readings raise the curves')


def level(kind: str, v) -> int:
    """0 fine, 1 yellow, 2 red (None: fine – nothing is known)."""
    if v is None:
        return 0
    if kind == "fps":
        return 2 if v < FPS_BAD else 1 if v < FPS_LOW else 0
    lo, hi = {"gpu": (sysinfo.GPU_WARM, sysinfo.GPU_HOT), "cpu": (sysinfo.CPU_WARM, sysinfo.CPU_HOT),
              "spot": (sysinfo.SPOT_WARM, sysinfo.SPOT_HOT), "full": (FULL_WARN, FULL_BAD),
              "ping": (PING_WARN, PING_BAD)}[kind]
    return 2 if v >= hi else 1 if v >= lo else 0


def colour(kind: str, v, base=FG) -> tuple:
    return (base, WARN, BAD)[level(kind, v)]


def _num(v, unit: str = "", digits: int = 0) -> str:
    if v is None:
        return "–"
    text = f"{v:.{digits}f}".replace(".", ",")
    return f"{text}{unit}"


def _share(used, total):
    return None if not used or not total else used / total


def size(view: str, width: int) -> tuple:
    """(w, h) of ``view`` at ``width`` px – for any readings."""
    w = max(120, int(width))
    u = w / 240
    return w, int({"curves": 262, "meters": 250, "compact": 64}.get(view, 64) * u)


def draw(view: str, snap, history=None, ping=None, width: int = 240, backdrop: bool = True,
         accent=(201, 162, 39, 255)) -> Image.Image:
    """The system values as ``view`` – ``snap`` a sysinfo.Snapshot, ``history`` a charts.SystemHistory (curves; None
    or too few readings: empty plots), ``ping`` ms or None."""
    w, h = size(view, width)
    pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(pic)
    u = w / 240
    if backdrop:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=max(3, int(8 * u)), fill=BACK)
    back = BACK if backdrop else (0, 0, 0, 0)
    {"curves": _curves, "meters": _meters}.get(view, _compact)(d, snap, history, ping, w, u, accent, back)
    return pic


def _curves(d, s, history, ping, w, u, accent, back) -> None:
    pad = int(12 * u)
    name_f, value_f, small = charts._font(int(10 * u), True), charts._font(int(14 * u), True), charts._font(int(8.5 * u))
    y = int(12 * u)
    hist = (lambda k: charts.buckets(history.values(k))) if history is not None else (lambda k: ())
    fps = hist("fps")
    top = charts.nice_top(max(fps), 15, FPS_TOP) if fps else FPS_TOP
    for name, value, col, data, lo, hi, ticks in (
            ("FPS", _num(s.fps), colour("fps", s.fps), fps, 0, top, (0, 60, top)),
            ("GPU", _num(s.gpu_temp, " °C"), colour("gpu", s.gpu_temp), hist("gpu"), 40, 95, (40, 95)),
            ("CPU", _num(s.cpu_load, " %"), colour("cpu", s.cpu_temp), hist("cpu"), 0, 100, (0, 50, 100))):
        d.text((pad, y + 6 * u), name, font=name_f, fill=DIM, anchor="lm")
        d.text((w - pad, y + 6 * u), value, font=value_f, fill=col, anchor="rm")
        y += int(18 * u)
        ph, left = int(46 * u), pad + int(22 * u)

        def yv(v, y=y, ph=ph, lo=lo, hi=hi):
            return y + ph - (min(max(v, lo), hi) - lo) / ((hi - lo) or 1) * (ph - 2) - 1
        for t in ticks:
            d.line((left, yv(t), w - pad, yv(t)), fill=GRID, width=1)
            d.text((left - 3, yv(t)), f"{t:.0f}", font=small, fill=DIM, anchor="rm")
        if len(data) >= 2:
            line_col = accent if col == FG else col
            pts = [(left + i * (w - pad - left) / (len(data) - 1), yv(v)) for i, v in enumerate(data)]
            under = tuple(int(a * 0.2 + b * 0.8) for a, b in zip(line_col[:3], back[:3])) + (max(back[3], 90),)
            d.polygon([(left, yv(lo))] + pts + [(pts[-1][0], yv(lo))], fill=under)
            d.line(pts, fill=line_col, width=max(1, int(1.6 * u)), joint="curve")
        y += ph + int(12 * u)
    d.line((pad, y - int(5 * u), w - pad, y - int(5 * u)), fill=GRID, width=1)
    row_f = charts._font(int(11 * u), True)
    cy = y + int(9 * u)
    x = pad
    for name, value, col in (("VRAM", _num(s.vram_used, " GB", 1), colour("full", _share(s.vram_used, s.vram_total))),
                             ("RAM", _num(s.ram_used, " GB", 1), colour("full", _share(s.ram_used, s.ram_total)))):
        d.text((x, cy), name, font=name_f, fill=DIM, anchor="lm")
        x += int(d.textlength(name, font=name_f) + 5 * u)
        d.text((x, cy), value, font=row_f, fill=col, anchor="lm")
        x += int(52 * u)
    d.text((w - pad, cy), _num(ping, " ms"), font=row_f, fill=colour("ping", ping), anchor="rm")


def _meters(d, s, history, ping, w, u, accent, back) -> None:
    pad = int(12 * u)
    name_f, value_f = charts._font(int(10 * u), True), charts._font(int(13 * u), True)
    y = int(14 * u)
    full = ((FULL_WARN, OK), (FULL_BAD - FULL_WARN, WARN), (1 - FULL_BAD, BAD))
    vram, ram = _share(s.vram_used, s.vram_total), _share(s.ram_used, s.ram_total)

    def temp_zones(warm, hot, lo=30, hi=100):
        a, b = (warm - lo) / (hi - lo), (hot - lo) / (hi - lo)
        return ((a, OK), (b - a, WARN), (1 - b, BAD))
    rows = (("FPS", _num(s.fps), None if s.fps is None else s.fps / FPS_TOP,
             ((FPS_BAD / FPS_TOP, BAD), ((FPS_LOW - FPS_BAD) / FPS_TOP, WARN), (1 - FPS_LOW / FPS_TOP, OK)),
             colour("fps", s.fps)),
            ("GPU °C", _num(s.gpu_temp), None if s.gpu_temp is None else (s.gpu_temp - 30) / 70,
             temp_zones(sysinfo.GPU_WARM, sysinfo.GPU_HOT), colour("gpu", s.gpu_temp)),
            ("GPU HOTSPOT", _num(s.gpu_hot), None if s.gpu_hot is None else (s.gpu_hot - 30) / 85,
             temp_zones(sysinfo.SPOT_WARM, sysinfo.SPOT_HOT, 30, 115), colour("spot", s.gpu_hot)),
            ("CPU °C", _num(s.cpu_temp), None if s.cpu_temp is None else (s.cpu_temp - 30) / 70,
             temp_zones(sysinfo.CPU_WARM, sysinfo.CPU_HOT), colour("cpu", s.cpu_temp)),
            ("VRAM", _num(s.vram_used, " GB", 1), vram, full, colour("full", vram)),
            ("RAM", _num(s.ram_used, " GB", 1), ram, full, colour("full", ram)))
    for name, value, share, zones, col in rows:
        d.text((pad, y + 6 * u), name, font=name_f, fill=DIM, anchor="lm")
        d.text((w - pad, y + 6 * u), value, font=value_f, fill=col, anchor="rm")
        y += int(17 * u)
        x, bar_w, bh = float(pad), w - 2 * pad, max(3, int(6 * u))
        for part, zc in zones:
            dim = tuple(int(c * 0.5 + b * 0.5) for c, b in zip(zc[:3], back[:3])) + (255,)
            d.rectangle((x, y, x + bar_w * part - max(1, 1.5 * u), y + bh), fill=dim)
            x += bar_w * part
        if share is not None:
            px = pad + bar_w * min(1.0, max(0.0, share))
            d.rectangle((px - 1.5 * u, y - 3 * u, px + 1.5 * u, y + bh + 3 * u), fill=FG)
        y += int(22 * u)


def _compact(d, s, history, ping, w, u, accent, back) -> None:
    pad = int(12 * u)
    big, cap = charts._font(int(34 * u), True), charts._font(int(9 * u), True)
    name_f, value_f, plain = charts._font(int(9.5 * u), True), charts._font(int(13 * u), True), charts._font(int(10.5 * u))
    d.text((pad, 28 * u), _num(s.fps), font=big, fill=colour("fps", s.fps), anchor="lm")
    d.text((pad + 2 * u, 54 * u), "FPS", font=cap, fill=DIM, anchor="lm")
    x = int(92 * u)
    for cy, name, temp, kind, load, mem, share in (
            (18 * u, "GPU", s.gpu_temp, "gpu", s.gpu_load, s.vram_used, _share(s.vram_used, s.vram_total)),
            (36 * u, "CPU", s.cpu_temp, "cpu", s.cpu_load, s.ram_used, _share(s.ram_used, s.ram_total))):
        d.text((x, cy), name, font=name_f, fill=DIM, anchor="lm")
        d.text((x + 28 * u, cy), _num(temp, "°"), font=value_f, fill=colour(kind, temp), anchor="lm")
        d.text((x + 57 * u, cy), _num(load, " %"), font=plain, fill=FG, anchor="lm")
        d.text((w - pad, cy), _num(mem, " GB", 1), font=plain, fill=colour("full", share), anchor="rm")
    d.text((x, 52 * u), "PING", font=name_f, fill=DIM, anchor="lm")
    d.text((x + 36 * u, 52 * u), _num(ping, " ms"), font=charts._font(int(11 * u), True), fill=colour("ping", ping),
           anchor="lm")
    if s.throttle or s.cpu_throttle:
        d.text((w - pad, 52 * u), _("gedrosselt"), font=charts._font(int(10 * u), True), fill=BAD, anchor="rm")


def sample_history():
    """Ten made-up minutes for the preview and "Overlay testen"."""
    from types import SimpleNamespace
    h = charts.SystemHistory()
    fps = (141, 143, 140, 138, 142, 139, 141, 144, 142, 140, 141, 143, 141, 140, 142, 141)
    gpu = (70, 71, 72, 73, 74, 75, 75, 76, 76, 77, 77, 77, 76, 77, 77, 77)
    cpu = (55, 58, 60, 66, 61, 59, 63, 70, 64, 62, 60, 61, 63, 65, 62, 63)
    for i in range(len(fps)):
        h.add(SimpleNamespace(t=float(i + 1), fps=float(fps[i]), gpu_temp=float(gpu[i]), cpu_load=float(cpu[i])))
    return h
