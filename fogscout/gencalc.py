"""Generator calculator (pure, 1.51): how long Survivors with chosen perks need for a Generator, and what a Killer
build does to that – for the page "Rechner".

The numbers come from ``perkdata.json`` (Dead by Daylight Wiki, see THIRD_PARTY.md); nothing is read from the game.
A Generator is simulated in small time steps instead of one formula, because the effects depend on the moment:
a toolbox runs empty, a kick sends the Survivors away while the Generator regresses, a block freezes it.

Rules used (all from the wiki, retrieved 2026-11-15):
- 90 Charges, 1 Charge/s per Survivor; every further Survivor on the same Generator costs each of them 15 % (co-op
  penalty: 2 → 85 % each, 3 → 70 %, 4 → 55 %).
- positive speed modifiers add up, negative ones multiply (1 + Σ bonus) · Π(1 − malus).
- diminishing returns (since patch 9.6.0): of several modifiers of one sign, the largest counts fully, the 2nd half,
  the 3rd a quarter, the 4th an eighth, every further 5 %. The wiki exempts only add-ons; the toolbox is counted
  (assumption, can be switched off together with the rule: ``Scenario.diminishing``).
- Skill Checks: 8 % chance per second (40 % with a toolbox), Great +1 % progress, a miss −10 % and 3 s without
  progress. Results use the expected value for the chosen share of Great/missed checks.
- Kick: −5 %, then −0.25 Charges/s until Survivors repaired +5 % again; at most 8 regression events (instant losses
  of ≥ 2.5 %) per Generator.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perkdata.json")
DT = 0.05                     # s per simulation step
LIMIT_S = 3600.0              # a Generator that is not done after this is reported as never done
MIN_CHARGES = 10.0            # the requirement never goes below this (stacked reductions)
MAX_SURVIVORS = 4


@dataclass
class Data:
    mech: dict
    survivor: dict            # name -> entry
    killer: dict
    toolboxes: dict
    addons: dict
    not_modelled: list
    retrieved: str = ""
    source_state: str = ""


def load(path: str = FILE) -> Data:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return Data(raw["mechanics"], {e["name"]: e for e in raw["survivor"]}, {e["name"]: e for e in raw["killer"]},
                {e["name"]: e for e in raw["toolboxes"]}, {e["name"]: e for e in raw.get("addons", [])},
                list(raw.get("not_modelled", [])), raw.get("retrieved", ""), raw.get("source_state", ""))


@dataclass
class Survivor:
    perks: tuple = ()                 # perk names from Data.survivor (unknown names are ignored)
    toolbox: str = ""                 # a name from Data.toolboxes, "" = none
    part: bool = False                # Brand New Part on the toolbox (used on the Generator)


@dataclass
class Killer:
    perks: tuple = ()
    counts: dict = field(default_factory=dict)   # perk name -> how often / how many (default: the entry's "default")


@dataclass
class Scenario:
    great: float = 0.5                # share of Skill Checks hit Great (the rest Good)
    miss: float = 0.0                 # share missed
    diminishing: bool = True
    kicks: int = 1                    # kicks on this Generator (0 = the Killer never comes)
    kick_at: float = 0.5              # the Killer comes when the Generator has this share of its progress
    away: float = 20.0                # s the Survivors stay away after a kick
    walk: float = 0.0                 # s between two Generators (five Generators)


@dataclass
class Result:
    seconds: float | None             # None = not done within LIMIT_S
    rates: list                       # c/s of each repairing Survivor at the start (with skill checks, no toolbox end)
    events: int = 0                   # regression events the Generator took
    lost: float = 0.0                 # Charges lost to the Killer
    notes: list = field(default_factory=list)


def ranked(values, diminishing: bool = True) -> list:
    """The values (all of one sign, as positive numbers) after diminishing returns: largest first, weighted."""
    vals = sorted((v for v in values if v > 0), reverse=True)
    if not diminishing:
        return vals
    weights = [1.0, 0.5, 0.25, 0.125]
    return [v * (weights[i] if i < len(weights) else 0.05) for i, v in enumerate(vals)]


def _count(data: Data, killer: Killer, name: str) -> int:
    e = data.killer[name]
    try:
        return max(0, min(int(killer.counts.get(name, e.get("default", 1))), int(e.get("count", 99))))
    except (TypeError, ValueError):
        return int(e.get("default", 1))


def _known(data: Data, perks, table) -> list:
    out, seen = [], set()
    for p in perks:
        e = table.get(p)
        if not e:
            continue
        key = e.get("group", p)
        if key in seen:                                   # the same perk twice (Overzealous Dull/Hex): the better
            prev = next(i for i, x in enumerate(out) if x.get("group", x["name"]) == key)
            if e.get("value", 0) > out[prev].get("value", 0):
                out[prev] = e
            continue
        seen.add(key)
        out.append(e)
    return out


def slowdowns(data: Data, killer: Killer) -> list:
    """The Killer's repair-speed penalties (as positive shares), before diminishing returns."""
    out = []
    for e in _known(data, killer.perks, data.killer):
        n = _count(data, killer, e["name"])
        if e["kind"] == "slow" and n:
            v = min(e["per"] * n, e["max"])
            if e.get("full_at") and n >= e["full_at"]:
                v = e["full"]
            out.append(v)
        elif e["kind"] == "slow_first" and n:
            out.append(min(e["first"] + e["per"] * (n - 1), e["max"]))
    return out


def requirement(data: Data, team, first: bool = True) -> tuple:
    """(Charges this Generator needs, notes). ``first``: the one-time reductions (Specialist, Fast Track, Brand New
    Part) are spent on this Generator."""
    need, notes = float(data.mech["charges"]), []
    perks = [e for s in team for e in _known(data, s.perks, data.survivor)]
    if any(e["kind"] == "requirement_all" for e in perks):
        e = next(e for e in perks if e["kind"] == "requirement_all")
        need -= e["value"]
        notes.append(f"{e['name']}: −{e['value']:g}")
    if first:
        for e in perks:
            if e["kind"] == "requirement_once":
                need -= e["value"]
                notes.append(f"{e['name']}: −{e['value']:g}")
        for s in team:
            if s.part and s.toolbox:
                v = data.addons["Brand New Part"]["value"]
                need -= v
                notes.append(f"Brand New Part: −{v:g}")
    return max(MIN_CHARGES, need), notes


def _hyper(data: Data, team, great: float) -> list:
    """Per Survivor: the expected factor on a Great check's bonus (Hyperfocus: +30 % per Token, Tokens kept only
    while every check is Great – stationary share of each Token count)."""
    out = []
    for s in team:
        e = next((x for x in _known(data, s.perks, data.survivor) if x["kind"] == "great_scale"), None)
        if not e or great <= 0:
            out.append(1.0)
            continue
        cap, g = int(e["tokens"]), min(max(great, 0.0), 1.0)
        share = [(1 - g) * g ** t for t in range(cap)] + [g ** cap]
        out.append(sum(p * (1 + e["value"] * t) for t, p in enumerate(share)))
    return out


def _bonuses(data: Data, s: Survivor, team, toolbox_on: bool, buff: bool) -> list:
    """The positive repair-speed modifiers of Survivor ``s`` while ``team`` repairs the Generator."""
    k = len(team)
    own = _known(data, s.perks, data.survivor)
    out = []
    for e in own:
        kind = e["kind"]
        if kind == "self":
            out.append(e["value"])
        elif kind == "self_with_others" and k >= 2:
            out.append(e["value"])
    team_perks = [e for m in team for e in _known(data, m.perks, data.survivor)]
    for kind in ("team_per_other", "team", "team_timed"):          # one instance each, for everyone there
        e = next((x for x in team_perks if x["kind"] == kind), None)
        if not e:
            continue
        if kind == "team_per_other" and k >= 2:
            out.append(min(e["value"] * (k - 1), e["max"]))
        elif kind == "team":
            out.append(e["value"])
        elif kind == "team_timed" and buff:
            out.append(e["value"])
    if toolbox_on and s.toolbox in data.toolboxes:
        out.append(data.toolboxes[s.toolbox]["bonus"])
    return out


def speed(data: Data, s: Survivor, team, killer: Killer, scen: Scenario, toolbox_on: bool = True,
          buff: bool = False) -> float:
    """Charges per second Survivor ``s`` adds by repairing (without skill checks)."""
    k = len(team)
    pos = sum(ranked(_bonuses(data, s, team, toolbox_on, buff), scen.diminishing))
    neg = 1.0
    for v in ranked(slowdowns(data, killer), scen.diminishing):
        neg *= max(0.0, 1.0 - v)
    coop = max(0.0, 1.0 - data.mech["coop_penalty"] * (k - 1))
    return data.mech["repair_rate"] * (1.0 + pos) * neg * coop


def _killer_effects(data: Data, killer: Killer) -> dict:
    perks = {e["name"]: e for e in _known(data, killer.perks, data.killer)}
    fx = {"pop": 0, "instant": [], "undone": 0, "blocks": 0.0, "start_block": 0.0, "brine": None,
          "overcharge": None, "ruin": 1.0}
    for name, e in perks.items():
        n = _count(data, killer, name)
        kind = e["kind"]
        if kind == "kick_loss":
            fx["pop"] = n
        elif kind == "instant":
            fx["instant"] += [e["value"]] * n
        elif kind == "undone":
            fx["undone"] = n
            fx["undone_e"] = e
        elif kind == "block" and n:
            if name.startswith("Corrupt"):
                fx["start_block"] = e["seconds"]
            else:
                fx["blocks"] += e["seconds"] * n
        elif kind == "regress_mult":
            fx["brine"] = e
        elif kind == "overcharge":
            fx["overcharge"] = e
        elif kind == "ruin":
            fx["ruin"] = e["value"]
    return fx


def one_generator(data: Data, team, killer: Killer | None = None, scen: Scenario | None = None,
                  first: bool = True, buff_s: float = 0.0) -> Result:
    """One Generator repaired by everyone in ``team`` together; the Killer kicks ``scen.kicks`` times when it reaches
    ``scen.kick_at``. ``buff_s``: seconds of Friendly Competition left from the Generator before."""
    killer = killer or Killer()
    scen = scen or Scenario()
    team = [s for s in team if isinstance(s, Survivor)][:MAX_SURVIVORS]
    if not team:
        return Result(None, [])
    m = data.mech
    need, notes = requirement(data, team, first)
    fx = _killer_effects(data, killer)
    steadfast = any(e["kind"] == "team" and e.get("regression") for s in team
                    for e in _known(data, s.perks, data.survivor))
    hyper = _hyper(data, team, scen.great)
    great_c, fail_c = m["great_bonus"] * need, m["fail_loss"] * need
    tool = [data.toolboxes[s.toolbox]["charges"] if s.toolbox in data.toolboxes else 0.0 for s in team]

    memo = {}

    def rates(buff: bool):
        """(progress per second, toolbox drain per Survivor) at this moment, skill checks included – the same for
        every step until a toolbox runs empty or a timed bonus ends (memo)."""
        key = (buff,) + tuple(c > 0 for c in tool)
        if key not in memo:
            memo[key] = _rates(buff)
        return memo[key]

    def _rates(buff: bool):
        total, drain, pause = 0.0, [], 0.0
        for i, s in enumerate(team):
            v = speed(data, s, team, killer, scen, tool[i] > 0, buff)
            chance = m["skill_check_chance_toolbox"] if tool[i] > 0 else m["skill_check_chance"]
            total += v + chance * (scen.great * great_c * hyper[i] - scen.miss * fail_c)
            pause += chance * scen.miss * m["fail_pause"]
            drain.append(v)
        return total * max(0.1, 1.0 - pause), drain

    start_rates = [round(speed(data, s, team, killer, scen, True, buff_s > 0), 4) for s in team]
    t, prog, events, lost, kicks_done = fx["start_block"], 0.0, 0, 0.0, 0
    if fx["start_block"]:
        notes.append(f"Corrupt Intervention: +{fx['start_block']:g} s")
    instant = list(fx["instant"])
    regression_mult = 0.25 / 0.25          # relative to the default rate

    def lose(share: float) -> float:
        nonlocal prog, events, lost
        if events >= m["regression_events"]:
            return 0.0
        c = min(prog, share * need)
        prog -= c
        lost += c
        if share >= m["event_min_loss"]:
            events += 1
        return c

    while prog < need:
        if t > LIMIT_S:
            return Result(None, start_rates, events, lost, notes)
        if kicks_done < scen.kicks and scen.kicks > 0 and prog >= scen.kick_at * need \
                and events < m["regression_events"]:
            # the Killer arrives: the Survivors leave, the Generator is kicked and may take perk effects
            kicks_done += 1
            loss = m["kick_loss"] + (0.15 if kicks_done <= fx["pop"] else 0.0)
            oc = fx["overcharge"]
            if oc:
                loss += oc["value"]
            block = 0.0
            if kicks_done == 1 and fx["undone"]:
                e = fx["undone_e"]
                loss += e["value"] * fx["undone"]
                block += e["block"] * fx["undone"]
            lose(loss)
            while instant and events < m["regression_events"]:
                lose(instant.pop(0))
            if kicks_done == 1:
                block += fx["blocks"]
            wait = max(scen.away, block)
            # blocked part: frozen; afterwards regression until the Survivors are back
            free = max(0.0, wait - block)
            step, done = DT, 0.0
            while done < free and prog > 0:
                mult = regression_mult
                if fx["brine"] and done + block < fx["brine"]["seconds"]:
                    mult *= fx["brine"]["value"]
                if oc and done + block < oc["seconds"]:
                    mult *= oc["from"] + (oc["to"] - oc["from"]) * (done + block) / oc["seconds"]
                mult = max(mult, fx["ruin"])
                if steadfast:
                    mult *= 0.5
                c = min(prog, m["regression_rate"] * mult * step)
                prog -= c
                lost += c
                done += step
            t += wait
            buff_s = max(0.0, buff_s - wait)
            continue
        gain, drain = rates(buff_s > 0)
        if gain > 0 and prog + gain * DT >= need:      # the last step: only the time it really takes
            t += (need - prog) / gain
            break
        prog += gain * DT
        for i, d in enumerate(drain):
            if tool[i] > 0:
                tool[i] = max(0.0, tool[i] - d * DT)
        buff_s = max(0.0, buff_s - DT)
        t += DT
    return Result(round(t, 2), start_rates, events, round(lost, 2), notes)


def by_size(data: Data, team, killer: Killer | None = None, scen: Scenario | None = None) -> list:
    """[(number of Survivors, Result without the Killer, Result with the Killer)] for the first 1 … n Survivors."""
    scen = scen or Scenario()
    calm = Scenario(**{**scen.__dict__, "kicks": 0})
    out = []
    for k in range(1, min(len(team), MAX_SURVIVORS) + 1):
        out.append((k, one_generator(data, team[:k], Killer(), calm),
                    one_generator(data, team[:k], killer, scen)))
    return out


def five_together(data: Data, team, killer: Killer | None = None, scen: Scenario | None = None,
                  gens: int = 5) -> float | None:
    """Seconds until ``gens`` Generators are done when the whole team repairs one after the other (Friendly
    Competition carries over from one Generator to the next)."""
    scen = scen or Scenario()
    total, buff = 0.0, 0.0
    fc = next((e for s in team for e in _known(data, s.perks, data.survivor) if e["kind"] == "team_timed"), None)
    for g in range(gens):
        r = one_generator(data, team, killer, scen, first=(g == 0), buff_s=buff)
        if r.seconds is None:
            return None
        total += r.seconds + (scen.walk if g < gens - 1 else 0.0)
        buff = max(0.0, (fc["seconds"] if fc and len(team) >= 2 else 0.0) - scen.walk)
    return round(total, 1)


def five_split(data: Data, team, killer: Killer | None = None, scen: Scenario | None = None,
               gens: int = 5) -> float | None:
    """Seconds until ``gens`` Generators are done when every Survivor repairs alone and takes the next free
    Generator when done (list scheduling; the one-time reductions go to each Survivor's first Generator)."""
    scen = scen or Scenario()
    if not team:
        return None
    free = [0.0] * len(team)
    firsts = [True] * len(team)
    finish = 0.0
    for _g in range(gens):
        i = min(range(len(team)), key=lambda j: free[j])
        r = one_generator(data, [team[i]], killer, scen, first=firsts[i])
        if r.seconds is None:
            return None
        firsts[i] = False
        free[i] += r.seconds
        finish = max(finish, free[i])
        free[i] += scen.walk
    return round(finish, 1)


def fmt(seconds) -> str:
    """"1:23" for the table, "–" when never done."""
    if seconds is None:
        return "–"
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"
