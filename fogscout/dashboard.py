"""Dashboard of the statistics page (since 1.58, user's wish): what the filters selected, as tiles and two charts.

Pure logic (no Qt): ``build()`` turns the selected rounds and their official matches into the data the window draws
(qt_window.DashboardView): key figures, maps by rounds with their results, and killer × map (average kills).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import math

from . import bloodpoints, history, official
from .catalog import shown
from .i18n import N_, _, current as _language
from .textnorm import fmt_duration

MAPS_SHOWN = 10            # map bars: the most played
MATRIX_KILLERS = 8         # heatmap columns: the most played killers (with official data)
MATRIX_MAPS = 10           # heatmap rows: the maps most played as killer
MATRIX_MIN = 2             # a cell needs this many rounds with a result, else it stays empty (one round says little)


@dataclass
class Tile:
    title: str
    value: str = "–"
    sub: str = ""
    frac: float | None = None          # bar below the value (0..1), None = no bar
    colour: object = None              # value in this colour (None = text colour)
    open: str = ""                     # 1.38.54: a click shows what the tile counts (App._open_tile), "" = none


def rounds_target(ts) -> str:
    """1.38.54: the click target "rounds:<t>,<t>…" – these rounds (start times) marked under „Letzte Runden“."""
    return "rounds:" + ",".join(repr(float(t)) for t in ts) if ts else ""


@dataclass
class Dashboard:
    tiles: list = field(default_factory=list)
    maps: list = field(default_factory=list)          # [(map, rounds, result text)] most played first
    maps_max: int = 1
    rows: list = field(default_factory=list)          # heatmap rows (maps)
    columns: list = field(default_factory=list)       # heatmap columns (killers, display names)
    cells: dict = field(default_factory=dict)         # (map, killer) -> (average kills, rounds)
    empty: str = ""                                   # text instead of everything (no rounds)
    trend: list = field(default_factory=list)         # 1.57.77: [(rounds, label, tip)] per hour / day / week
    trend_title: str = ""
    times: object = None                              # 1.57.77: Grid of the rounds by weekday × time of day


def _bp(n) -> str:
    """Bloodpoints short: 215k, 3.45 Mio."""
    if n >= 1e6:
        return _("{n} Mio.", n=f"{n / 1e6:.2f}")
    return f"{n / 1000:.0f}k" if n >= 1000 else f"{n:.0f}"


def play_time(seconds: float) -> str:
    """Play time of many rounds: "29.5 h" from an hour on (h:mm:ss reads like a clock time there)."""
    if seconds < 3600:
        return fmt_duration(seconds)
    txt = f"{seconds / 3600:.1f}"
    return (txt.replace(".", ",") if _language() == "de" else txt) + " h"   # 1.24.7: "58,3 h" in German


@dataclass
class BpRate:
    """1.6.3 (user: farming evaluation): bloodpoints of the rounds tied to a match with BP."""
    rounds: int = 0
    bp: int = 0
    play_s: float = 0.0          # match length (the stats page's, else banner to end)
    wait_s: float = 0.0          # search time in the lobby (rounds without a known wait: the average of the others;
                                 # 1.55.5: a farming round without one is "sofort" = 0 s)

    @property
    def per_round(self):
        return self.bp / self.rounds if self.rounds else None

    @property
    def per_hour(self):
        return self.bp * 3600 / self.play_s if self.play_s > 0 else None

    @property
    def per_hour_waiting(self):
        """Per hour of playing and searching together – what an evening of farming really earns."""
        total = self.play_s + self.wait_s
        return self.bp * 3600 / total if total > 0 else None


def bp_rate(pairs) -> BpRate:
    """``pairs``: [(round, official match)]; only matches with bloodpoints count."""
    got = [(r, m) for r, m in pairs if m.bp > 0]
    out = BpRate(rounds=len(got), bp=sum(m.bp for _r, m in got))
    out.play_s = sum(m.seconds if m.seconds > 0 else r.seconds for r, m in got)
    waits = [r.wait for r, _m in got if r.wait is not None]
    avg_wait = sum(waits) / len(waits) if waits else 0.0
    # 1.55.5 (review F11): a farming round without a measured wait had no search (an instant lobby) – the tables say
    # "sofort" for it, so it counts 0 s here too instead of the average of the others
    out.wait_s = sum(r.wait if r.wait is not None else 0.0 if r.farming and not r.custom else avg_wait
                     for r, _m in got)
    return out


def bp_rows(pairs, killer_label=lambda k: k) -> list:
    """[(group, BpRate)]: all, survivor, killer, then each killer by rounds – the table "Bloodpoints"."""
    rows = [(_("Alle"), bp_rate(pairs))]
    for role, label in (("survivor", _("Survivor")), ("killer", _("Killer"))):
        sub = [(r, m) for r, m in pairs if r.role == role]
        if sub:
            rows.append((label, bp_rate(sub)))
    killers = {}
    for r, m in pairs:
        if r.role == "killer" and r.killer:
            killers.setdefault(r.killer, []).append((r, m))
    for k, sub in sorted(killers.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        rows.append(("   " + killer_label(k), bp_rate(sub)))
    return [(g, b) for g, b in rows if b.rounds]


def bp_tiles(pairs, role_label=lambda r: r) -> list:
    """1.7.1 (user: "a small dashboard for the bloodpoints too"): the tiles above the bloodpoints table – total,
    per round, per hour (match / with waiting), the best round, Ø per role (bars relative to the higher one)."""
    b = bp_rate(pairs)
    if not b.rounds:
        return []
    n_txt = _("{n} Runden", n=b.rounds)
    out = [Tile(_("Bloodpoints"), _bp(b.bp), n_txt + " · " + _("{time} gespielt", time=play_time(b.play_s))),
           Tile(_("Ø pro Runde"), _bp(b.per_round), n_txt),
           Tile(_("BP/h im Match"), _bp(b.per_hour) if b.per_hour else "–", _("Spielzeit laut Stats-Seite")),
           Tile(_("BP/h mit Wartezeit"), _bp(b.per_hour_waiting) if b.per_hour_waiting else "–",
                _("Match und Suche zusammen"))]
    best_r, best_m = max(((r, m) for r, m in pairs if m.bp > 0), key=lambda p: (p[1].bp, p[0].t))
    sub = shown(best_r.map) + " · " + time.strftime("%d.%m.%y", time.localtime(best_r.t))
    if best_r.role in ("killer", "survivor"):
        sub += " · " + role_label(best_r.role)
    out.append(Tile(_("Beste Runde"), _bp(best_m.bp), sub, open=rounds_target([best_r.t])))
    per = {role: bp_rate([(r, m) for r, m in pairs if r.role == role]) for role in ("killer", "survivor")}
    top = max((x.per_round or 0 for x in per.values()), default=0)
    for role, label in (("killer", _("Ø BP als Killer")), ("survivor", _("Ø BP als Survivor"))):
        x = per[role]
        if x.rounds:
            out.append(Tile(label, _bp(x.per_round), _("{n} Runden", n=x.rounds),
                            frac=x.per_round / top if top else None))
    return out


def bp_trend(pairs, unit: str) -> list:
    """Bloodpoints over time: [(bucket start, [bp …])] per hour / day / week from the first to the last round
    with bloodpoints, empty buckets included, the newest MAX_BUCKETS (like official.trend)."""
    groups = {}
    for r, m in pairs:
        if m.bp > 0:
            groups.setdefault(official.bucket_start(r.t, unit), []).append(m.bp)
    if not groups:
        return []
    return [(b, groups.get(b, [])) for b in official.bucket_span(min(groups), max(groups), unit)]     # CR-009


def balance_trend(rounds, unit: str) -> list:
    """1.38.48 (user's pick "Blutpunkte-Stand als Verlauf"): the bloodpoint balance read in the lobby after each
    round (Round.balance) over time – [(bucket start, the last balance of the bucket or None)] per hour / day / week
    from the first to the last bucket with a reading, the newest MAX_BUCKETS (like bp_trend)."""
    last = {}
    for r in rounds:
        if r.balance is None:
            continue
        b = official.bucket_start(r.t, unit)
        if b not in last or r.t >= last[b][0]:
            last[b] = (r.t, r.balance)
    if not last:
        return []
    return [(b, last[b][1] if b in last else None)                                   # CR-009
            for b in official.bucket_span(min(last), max(last), unit)]


def balance_tile(rounds, per_round, cap: int = bloodpoints.CAP):
    """1.38.48: the tile "BP-Stand" – the newest balance read (of ``rounds``: all of them, not the filtered ones –
    a balance is a state, not a sum) and how many rounds to the cap at ``per_round`` (Ø BP of the selection);
    None without a reading."""
    read = [r for r in rounds if r.balance is not None]
    if not read:
        return None
    newest = max(read, key=lambda r: r.t)
    bal = newest.balance
    if bal >= cap:
        sub = _("Cap erreicht")
    elif per_round:
        sub = _("Cap in ≈ {n} Runden", n=math.ceil((cap - bal) / per_round))
    else:
        sub = _("Cap: {cap}", cap=_bp(cap))
    return Tile(_("BP-Stand"), _bp(bal), sub + " · " + time.strftime("%d.%m. %H:%M", time.localtime(newest.t)),
                frac=min(1.0, bal / cap))


def tiles(rounds, pairs) -> list:
    s = history.summary(rounds)
    o = official.summary([m for _r, m in pairs])
    ws = history.wait_summary(rounds)
    out = [Tile(_("Runden"), str(s["count"]), _("{time} gespielt", time=play_time(s["total"])), open="tab:last")]
    # 1.24.2 (phase 2 audit: four of eight tiles said "–" without match data): a value the selection does not
    # have gets no tile – the statistics page says once what is missing and how to get it (App: stats_data_row)
    if o["killer"]:
        sub = _("4K: {n} von {total}", n=o["four"], total=o["killer"])
        if o["abandons"]:
            sub += " · " + _("{n}× Abandon", n=o["abandons"])
        out.append(Tile(_("Ø Kills"), f"{o['kills']:.2f}", sub, frac=o["kills"] / 4, open="tab:last:killer"))
    if o["survivor"]:
        out.append(Tile(_("Entkommen"), f"{o['escaped']:.0%}", _("{n} Survivor-Runden", n=o["survivor"]),
                        frac=o["escaped"], open="tab:last:survivor"))
    if s["count"]:
        out.append(Tile(_("Ø Rundendauer"), fmt_duration(s["avg"]), open="tab:last"))
    if ws["count"]:
        out.append(Tile(_("Ø Wartezeit"), fmt_duration(ws["avg"]),
                        _("Median {time}", time=fmt_duration(ws["median"])), open="tab:wait"))
    if o["bp_matches"]:
        out.append(Tile(_("Ø Bloodpoints"), _bp(o["bp"] / o["bp_matches"]), _("{n} Matches", n=o["bp_matches"]),
                        open="tab:bp"))
    rate = bp_rate(pairs)                                       # 1.6.3: what farming earns
    if rate.per_hour:
        out.append(Tile(_("Bloodpoints pro Stunde"), _bp(rate.per_hour),
                        _("mit Wartezeit {bp}", bp=_bp(rate.per_hour_waiting)) if rate.per_hour_waiting else "",
                        open="tab:bp"))
    return out


def map_rows(rounds, pairs, limit: int = MAPS_SHOWN) -> list:
    """[(map, rounds, results)] of the most played maps; results: Ø kills as killer · escaped as survivor."""
    res = official.results(pairs, lambda r: (r.map, r.role))
    rows = []
    for name, n, _avg, _longest in history.per_map(rounds)[:limit]:
        parts = []
        k = official.mean(res.get((name, "killer"), {}).get("kills"))
        e = official.mean(res.get((name, "survivor"), {}).get("escaped"))
        if k is not None:
            parts.append(_("Ø {kills} Kills", kills=f"{k:.1f}"))
        if e is not None:
            parts.append(_("{share} entkommen", share=f"{e:.0%}"))
        rows.append((name, n, " · ".join(parts)))
    return rows


def short_killer(name: str) -> str:
    """Column heading of the heatmap: "The Nurse" -> "Nurse" (the columns are narrow)."""
    return name[4:] if name.startswith("The ") else name


def matrix(pairs, label=lambda k: k):
    """Map × killer, average kills from the stats page: (maps, killers, {(map, killer): (avg, n)}). Only killer
    rounds with a known result; rows/columns = the most played, cells with fewer than MATRIX_MIN rounds left out."""
    res = official.results([(r, m) for r, m in pairs if r.role == "killer" and r.killer], lambda r: (r.map, r.killer))
    per_killer, per_map = {}, {}
    for (m, k), g in res.items():
        n = len(g["kills"])
        per_killer[k] = per_killer.get(k, 0) + n
        per_map[m] = per_map.get(m, 0) + n
    killers = [k for k, n in sorted(per_killer.items(), key=lambda kv: (-kv[1], kv[0]))[:MATRIX_KILLERS] if n]
    maps = [m for m, n in sorted(per_map.items(), key=lambda kv: (-kv[1], kv[0]))[:MATRIX_MAPS] if n]
    cells = {}
    for (m, k), g in res.items():
        if k in killers and m in maps and len(g["kills"]) >= MATRIX_MIN:
            cells[(m, label(k))] = (sum(g["kills"]) / len(g["kills"]), len(g["kills"]))
    rows = [m for m in maps if any((m, label(k)) in cells for k in killers)]          # no empty rows/columns
    cols = [label(k) for k in killers if any((m, label(k)) in cells for m in maps)]
    return rows, cols, cells


def play_trend(rounds, unit: str) -> list:
    """How much was played over time (1.57.77, the statistics' first page): [(rounds, label, tip)] per hour / day /
    week from the first to the last round of the selection, empty buckets included, the newest official.MAX_BUCKETS.
    From the rounds alone – it needs no match data."""
    import datetime
    import time
    counts = {}
    for r in rounds:
        b = official.bucket_start(r.t, unit)
        counts[b] = counts.get(b, 0) + 1
    if not counts:
        return []
    out = []
    for b in official.bucket_span(min(counts), max(counts), unit):
        if unit == "week":
            label = _("KW {n}", n=datetime.date.fromtimestamp(b).isocalendar()[1])
            when = f"{label} ({time.strftime('%d.%m.', time.localtime(b))}–" \
                   f"{time.strftime('%d.%m.', time.localtime(b + 6 * 86400))})"
        elif unit == "hour":
            label, when = time.strftime("%H:00", time.localtime(b)), time.strftime("%d.%m. %H:00", time.localtime(b))
        else:
            label = time.strftime("%d.%m.", time.localtime(b))
            when = _(WEEKDAY_NAMES[time.localtime(b).tm_wday])[:2] + " " + label
        n = counts.get(b, 0)
        out.append((n, label, _("{when}: {n} Runden", when=when, n=n)))
    return out


def play_grid(rounds):
    """When the user plays (1.57.77): a Grid of the number of rounds by weekday × time of day (blocks of
    history.HOUR_BLOCK hours, local time) – every weekday and every block with a round, a cell without one empty."""
    import datetime
    counts = {}
    for r in rounds:
        d = datetime.datetime.fromtimestamp(r.t)
        cell = (d.weekday(), d.hour // history.HOUR_BLOCK * history.HOUR_BLOCK)
        counts[cell] = counts.get(cell, 0) + 1
    day = {w: _(WEEKDAY_NAMES[w]) for w in sorted({c[0] for c in counts})}
    col = {b: f"{b:02d}–{(b + history.HOUR_BLOCK) % 24:02d}" for b in sorted({c[1] for c in counts})}
    top = max(counts.values(), default=1)
    return Grid(rows=list(day.values()), columns=list(col.values()),
                cells={(day[w], col[b]): (float(n), n) for (w, b), n in counts.items()}, top=float(top), count=True,
                legend=_("{n} Runden", n=top), n=sum(counts.values()))


def build(rounds, pairs, killer_label=lambda k: k, unit: str = "week") -> Dashboard:
    """``rounds``: the rounds the filters selected; ``pairs``: [(round, official match)] of those; ``unit``: the
    trend's buckets (hour / day / week)."""
    if not rounds:
        return Dashboard(empty=_("Keine Runden in dieser Auswahl – „Filter zurücksetzen“ zeigt wieder alle."))
    d = Dashboard(tiles=tiles(rounds, pairs), maps=map_rows(rounds, pairs))
    d.maps_max = max((n for _m, n, _r in d.maps), default=1)
    d.rows, d.columns, d.cells = matrix(pairs, killer_label)
    if unit == "week" and max(r.t for r in rounds) - min(r.t for r in rounds) < 28 * 86400:
        unit = "day"                                   # under four weeks of rounds: weeks would be a column or two
    d.trend = play_trend(rounds, unit)
    d.trend_title = {"hour": _("Verlauf – Runden pro Stunde"), "day": _("Verlauf – Runden pro Tag")}.get(
        unit, _("Verlauf – Runden pro Woche"))
    d.times = play_grid(rounds)
    return d


# ------------------------------------------------------------------ more statistics from the data already stored
@dataclass
class Result:
    """Ø kills (killer rounds), share escaped (survivor rounds) and Ø bloodpoints of a group, with their counts."""
    kills_sum: int = 0
    kills_n: int = 0
    escaped: int = 0
    survivor_n: int = 0
    bp_sum: int = 0
    bp_n: int = 0

    def add(self, k, e, bp=0) -> None:
        if k is not None:
            self.kills_sum += k
            self.kills_n += 1
        if e is not None:
            self.escaped += int(e)
            self.survivor_n += 1
        if bp > 0:
            self.bp_sum += bp
            self.bp_n += 1

    @property
    def kills(self):
        return self.kills_sum / self.kills_n if self.kills_n else None

    @property
    def escape_share(self):
        return self.escaped / self.survivor_n if self.survivor_n else None

    @property
    def bp(self):
        return self.bp_sum / self.bp_n if self.bp_n else None


def survival(pairs, killer_label=lambda k: k) -> dict:
    """How much of the match a survivor lived through: own time in the match (Match.seconds) / the whole match
    (Match.duration, userscript 3 and newer) – only survivor matches that know both. {"all": (n, Ø share or None),
    "maps": [(map, n, Ø share)], "killers": [(opposing killer, n, Ø share)]}, the most played first; one pass."""
    maps, killers = {}, {}
    n, total = 0, 0.0
    for r, m in pairs:
        if m.role != "survivor" or m.seconds <= 0 or m.duration <= 0:
            continue
        share = min(1.0, m.seconds / m.duration)       # the page's two clocks may differ by a second
        n += 1
        total += share
        g = maps.setdefault(r.map, [0, 0.0])
        g[0] += 1
        g[1] += share
        k = next((p.character for p in m.opp if p.role == "killer" and p.character), "")
        if k:
            g = killers.setdefault(killer_label(k), [0, 0.0])
            g[0] += 1
            g[1] += share

    def rows(groups):
        return sorted(((name, c, s / c) for name, (c, s) in groups.items()), key=lambda x: (-x[1], x[0].lower()))
    return {"all": (n, total / n if n else None), "maps": rows(maps), "killers": rows(killers)}


@dataclass
class Grid:
    """A heatmap other than killer × map (qt_views.Heatmap): rows × columns of (Ø value, rounds), the value 0..top;
    ``share`` writes it as a percentage, ``legend`` names the top of the colour ramp. Rows/columns: texts shown."""
    rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    cells: dict = field(default_factory=dict)          # (row, column) -> (mean, n)
    top: float = 4.0
    share: bool = False
    count: bool = False                                # 1.57.77: the value is a number of rounds (play_grid)
    legend: str = ""
    n: int = 0                                         # rounds with a result in all (also those in no cell)


WEEKDAY_NAMES = (N_("Montag"), N_("Dienstag"), N_("Mittwoch"), N_("Donnerstag"), N_("Freitag"), N_("Samstag"),
                 N_("Sonntag"))


def time_grids(pairs) -> dict:
    """Result by weekday × time of day (blocks of history.HOUR_BLOCK hours, local time): {"killer": Grid of Ø kills,
    "survivor": Grid of the share escaped}. A cell needs MATRIX_MIN rounds with a result (like ``matrix``); rows and
    columns without a cell are left out. One pass over the pairs."""
    import datetime
    sums = {"killer": {}, "survivor": {}}
    for r, m in pairs:
        k, e = official.kills(m), official.escaped(m)
        if k is None and e is None:
            continue
        d = datetime.datetime.fromtimestamp(r.t)
        cell = (d.weekday(), d.hour // history.HOUR_BLOCK * history.HOUR_BLOCK)
        g = sums["killer" if k is not None else "survivor"].setdefault(cell, [0, 0])
        g[0] += k if k is not None else int(e)
        g[1] += 1
    out = {}
    for role, groups in sums.items():
        kept = {c: (s / n, n) for c, (s, n) in groups.items() if n >= MATRIX_MIN}
        day = {w: _(WEEKDAY_NAMES[w]) for w in sorted({c[0] for c in kept})}
        col = {b: f"{b:02d}–{(b + history.HOUR_BLOCK) % 24:02d}" for b in sorted({c[1] for c in kept})}
        legend = (_("4 Kills · leer = weniger als {n} Runden", n=MATRIX_MIN) if role == "killer" else
                  _("100 % entkommen · leer = weniger als {n} Runden", n=MATRIX_MIN))
        out[role] = Grid(rows=list(day.values()), columns=list(col.values()),
                         cells={(day[w], col[b]): v for (w, b), v in kept.items()},
                         top=4.0 if role == "killer" else 1.0, share=role == "survivor", legend=legend,
                         n=sum(n for _s, n in groups.values()))
    return out


PING_BANDS = (40, 80)        # ms: under 40, 40–80, over 80 (Round.ping = median ping to the server region)


def connection(pairs) -> list:
    """Connection against the result: [(key, Result)] for the ping bands "<40", "40-80", ">80" (rounds with a
    measured ping) and for rounds with and without receive gaps "stalls" / "no_stalls" (rounds where they were
    measured, Round.stalls not None); groups without a result left out. One pass."""
    keys = ("<40", "40-80", ">80", "stalls", "no_stalls")
    groups = {k: Result() for k in keys}
    lo, hi = PING_BANDS
    for r, m in pairs:
        k, e = official.kills(m), official.escaped(m)
        if k is None and e is None:
            continue
        if r.ping is not None:
            groups["<40" if r.ping < lo else "40-80" if r.ping <= hi else ">80"].add(k, e)
        if r.stalls is not None:
            groups["stalls" if r.stalls > 0 else "no_stalls"].add(k, e)
    return [(k, groups[k]) for k in keys if groups[k].kills_n or groups[k].survivor_n]


def wait_trend(rounds, unit: str) -> list:
    """The median waiting time in the lobby over time per role: [(bucket start, {role: (median s, rounds)})] per
    hour / day / week from the first to the last bucket with a waiting time, empty buckets included ({}), the newest
    official.MAX_BUCKETS (like bp_trend). Only normal killer/survivor rounds with a measured wait count (as in
    history.wait_summary)."""
    groups = {}
    for r in rounds:
        if r.wait is None or r.role not in ("killer", "survivor") or not history.normal(r):
            continue
        groups.setdefault(official.bucket_start(r.t, unit), {}).setdefault(r.role, []).append(r.wait)
    if not groups:
        return []
    return [(b, {role: (history.median(w), len(w)) for role, w in groups.get(b, {}).items()})   # CR-009
            for b in official.bucket_span(min(groups), max(groups), unit)]
