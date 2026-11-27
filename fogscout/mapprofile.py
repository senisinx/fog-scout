"""Map profile (1.9.x, user: "Map-Profil"): what the own history says about one map – shown with the map big on the
maps page. Pure: rounds (history.Round) and their official matches in, texts and tiles out; nothing is read or written.

Counted are normal rounds only (no custom game, no farming round – like the tile's mark); results come from the
official match tied to a round, a round without one counts for rounds and length only."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import history, official
from .dashboard import Tile, rounds_target
from .i18n import _
from .textnorm import fmt_duration

KILLERS_KEPT = 4          # rows "Killer auf dieser Map"
RECENT_KEPT = 5           # rows "Letzte Runden"
OPEN_MAX = 200            # start times a click on "Runden" hands to the statistics (the newest)


@dataclass
class Profile:
    rounds: int = 0
    tiles: list = field(default_factory=list)       # [dashboard.Tile]
    killers: list = field(default_factory=list)     # [(killer, rounds text, result text)], most played first
    recent: list = field(default_factory=list)      # [(when, who, result, length)], newest first


def _when(t: float) -> str:
    return time.strftime("%d.%m. %H:%M", time.localtime(t))


def _avg(values) -> str:
    return f"{sum(values) / len(values):.1f}"


def build(rounds, off: dict, map_id: str, killer_name=str, result=None) -> Profile:
    """The profile of ``map_id`` from ``rounds`` and ``off`` ({id(round): official match}, as App._joined gives
    them). ``killer_name``: the shown name of a killer, ``result(match or None)``: the text of the column „Ergebnis“."""
    mine = sorted((r for r in rounds if r.map_id == map_id and history.normal(r)), key=lambda r: r.t)
    if not mine:
        return Profile()
    as_killer = [r for r in mine if r.role == "killer"]
    as_surv = [r for r in mine if r.role == "survivor"]
    kills = [(r, official.kills(off[id(r)])) for r in as_killer if id(r) in off]
    kills = [(r, k) for r, k in kills if k is not None]
    escapes = [official.escaped(off[id(r)]) for r in as_surv if id(r) in off]
    escapes = [e for e in escapes if e is not None]
    tiles = [Tile(_("Runden"), str(len(mine)),
                  _("{k} als Killer · {s} als Survivor", k=len(as_killer), s=len(as_surv)),
                  open=rounds_target([r.t for r in mine[-OPEN_MAX:]]))]
    if kills:
        ks = [k for _r, k in kills]
        four = sum(1 for k in ks if k == 4)
        tiles.append(Tile(_("Ø Kills"), _avg(ks), _("{n} Runden · {four}× 4K", n=len(ks), four=four),
                          frac=sum(ks) / len(ks) / 4))
    else:
        tiles.append(Tile(_("Ø Kills"), "–", _("noch kein Ergebnis")))
    if escapes:
        share = sum(1 for e in escapes if e) / len(escapes)
        tiles.append(Tile(_("Entkommen"), f"{share:.0%}", _("{n} Runden", n=len(escapes)), frac=share))
    else:
        tiles.append(Tile(_("Entkommen"), "–", _("noch kein Ergebnis")))
    lengths = [r.seconds for r in mine if r.seconds > 0]
    tiles.append(Tile(_("Ø Dauer"), fmt_duration(sum(lengths) / len(lengths)) if lengths else "–",
                      _("zuletzt {date}", date=time.strftime("%d.%m.%y", time.localtime(mine[-1].t)))))
    groups = {}
    for r in as_killer:
        if r.killer:
            groups.setdefault(r.killer, []).append(r)
    by_round = {id(r): k for r, k in kills}
    killers = []
    for name, rs in sorted(groups.items(), key=lambda g: (-len(g[1]), g[0])):
        ks = [by_round[id(r)] for r in rs if id(r) in by_round]
        killers.append((killer_name(name), _("{n} Runden", n=len(rs)),
                        _("Ø {kills} Kills", kills=_avg(ks)) if ks else "–"))
    recent = []
    for r in reversed(mine[-RECENT_KEPT:]):
        who = (killer_name(r.killer) if r.killer else _("Killer")) if r.role == "killer" else \
            _("Survivor") if r.role == "survivor" else "–"
        recent.append((_when(r.t), who, result(off.get(id(r))) if result else "–",
                       fmt_duration(r.seconds) if r.seconds > 0 else "–"))
    return Profile(len(mine), tiles, killers[:KILLERS_KEPT], recent)
