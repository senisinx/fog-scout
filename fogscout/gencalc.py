"""Calculator (pure; generators 1.51, every other area 1.52): how long Survivors with chosen perks need for a
Generator and what a Killer build does to that – and, for healing, movement, vaults, totems, chests, gates, hooks
and the Killer's own actions, the speed after diminishing returns with every modifier listed (``area_lines``), the
best next perk (``suggest``) – for the page "Rechner".

The numbers come from ``perkdata.json`` (Dead by Daylight Wiki, see THIRD_PARTY.md); nothing is read from the game.
A Generator is simulated from event to event instead of one formula, because the effects depend on the moment:
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
from dataclasses import dataclass, field, replace

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perkdata.json")
DT = 0.05                     # s per step while a kicked Generator regresses (its rate changes with the time)
LIMIT_S = 3600.0              # a Generator that is not done after this is reported as never done
MIN_CHARGES = 10.0            # the requirement never goes below this (stacked reductions)
MAX_SURVIVORS = 4
WEIGHTS = (1.0, 0.5, 0.25, 0.125)     # diminishing returns: the largest modifier, the 2nd, 3rd, 4th …
LAST_WEIGHT = 0.05                    # … and every further one


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
    areas: dict = field(default_factory=dict)        # id -> {"id", "side", "kind", "rows"}
    perks: dict = field(default_factory=dict)        # name -> entry with "effects" (every area but repair)
    medkits: dict = field(default_factory=dict)
    not_modelled_areas: list = field(default_factory=list)
    killers: dict = field(default_factory=dict)      # "The Trapper" -> {"speed", "mode", "alt"}
    killer_addons: dict = field(default_factory=dict)    # name -> {"killer", "effects"} (those that can be calculated)
    item_addons: dict = field(default_factory=dict)      # name -> {"item": "toolbox"/"medkit", "repair", "charges", …}


def load(path: str = FILE) -> Data:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return Data(raw["mechanics"], {e["name"]: e for e in raw["survivor"]}, {e["name"]: e for e in raw["killer"]},
                {e["name"]: e for e in raw["toolboxes"]}, {e["name"]: e for e in raw.get("addons", [])},
                list(raw.get("not_modelled", [])), raw.get("retrieved", ""), raw.get("source_state", ""),
                {a["id"]: a for a in raw.get("areas", [])}, {e["name"]: e for e in raw.get("perks", [])},
                {e["name"]: e for e in raw.get("medkits", [])}, list(raw.get("not_modelled_areas", [])),
                {e["name"]: e for e in raw.get("killers", [])}, {e["name"]: e for e in raw.get("killer_addons", [])},
                {e["name"]: e for e in raw.get("item_addons", [])})


@dataclass
class Survivor:
    perks: tuple = ()                 # perk names from Data.survivor / Data.perks (unknown names are ignored)
    toolbox: str = ""                 # a name from Data.toolboxes, "" = none
    part: bool = False                # Brand New Part on the toolbox (used on the Generator)
    medkit: str = ""                  # a name from Data.medkits, "" = none (healing others)
    addons: tuple = ()                # names from Data.item_addons (only those of the item in hand count)


@dataclass
class Killer:
    perks: tuple = ()
    counts: dict = field(default_factory=dict)   # perk name -> how often / how many (default: the entry's "default")
    name: str = ""                    # a name from Data.killers ("" = any Killer: the three usual speeds)
    addons: tuple = ()                # names from Data.killer_addons (only those of this Killer count)


@dataclass
class Scenario:
    great: float = 0.5                # share of Skill Checks hit Great (the rest Good)
    miss: float = 0.0                 # share missed
    diminishing: bool = True
    kicks: int = 1                    # kicks on this Generator (0 = the Killer never comes)
    kick_at: float = 0.5              # the Killer comes when the Generator has this share of its progress
    away: float = 20.0                # s the Survivors stay away after a kick
    walk: float = 0.0                 # s between two Generators (five Generators)
    stacks: float = 1.0               # share of a Survivor perk's Tokens/stacks that count (at least one)


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
    return [v * (WEIGHTS[i] if i < len(WEIGHTS) else LAST_WEIGHT) for i, v in enumerate(vals)]


def weights(values, diminishing: bool = True) -> list:
    """For each value (same order as given, sign ignored) the share of it that counts: the largest fully, …"""
    order = sorted(range(len(values)), key=lambda i: -abs(values[i]))
    out = [1.0] * len(values)
    if diminishing:
        for rank, i in enumerate(order):
            out[i] = WEIGHTS[rank] if rank < len(WEIGHTS) else LAST_WEIGHT
    return out


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


def slowdown_parts(data: Data, killer: Killer) -> list:
    """[(perk name, share)]: the Killer's repair-speed penalties (as positive shares), before diminishing returns."""
    out = []
    for e in _known(data, killer.perks, data.killer):
        n = _count(data, killer, e["name"])
        if e["kind"] == "slow" and n:
            v = min(e["per"] * n, e["max"])
            if e.get("full_at") and n >= e["full_at"]:
                v = e["full"]
            out.append((e["name"], v))
        elif e["kind"] == "slow_first" and n:
            out.append((e["name"], min(e["first"] + e["per"] * (n - 1), e["max"])))
    return out


def slowdowns(data: Data, killer: Killer) -> list:
    """The Killer's repair-speed penalties (as positive shares), before diminishing returns."""
    return [v for _name, v in slowdown_parts(data, killer)]


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
            if s.toolbox and (s.part or any(a.get("part") for a in item_addons(data, s))):
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


def item_addons(data: Data, s: Survivor) -> list:
    """The add-on entries of ``s`` that fit the item in hand (a toolbox's on a toolbox, a med-kit's on a med-kit;
    each once, two at most – the game has two places)."""
    kind = "toolbox" if s.toolbox in data.toolboxes else "medkit" if s.medkit in data.medkits else ""
    out = []
    for name in dict.fromkeys(s.addons):
        e = data.item_addons.get(name)
        if e and e["item"] == kind and len(out) < 2:
            out.append(e)
    return out


def tool_charges(data: Data, s: Survivor) -> float:
    """The Charges of the toolbox in hand with its add-ons (Scraps, Wire Spool); 0 without a toolbox."""
    if s.toolbox not in data.toolboxes:
        return 0.0
    return float(data.toolboxes[s.toolbox]["charges"]) + sum(a.get("charges", 0) for a in item_addons(data, s))


def addon_bonus_parts(data: Data, s: Survivor, toolbox_on: bool = True) -> list:
    """[(add-on name, share)]: the repair-speed bonus of the toolbox's add-ons – never ranked (patch notes 9.6.0:
    modifiers from add-ons are excluded from diminishing returns)."""
    if not (toolbox_on and s.toolbox in data.toolboxes):
        return []
    return [(a["name"], a["repair"]) for a in item_addons(data, s) if a.get("repair")]


def bonus_parts(data: Data, s: Survivor, team, toolbox_on: bool = True, buff: bool = False) -> list:
    """[(name, share)]: the positive repair-speed modifiers of Survivor ``s`` while ``team`` repairs the Generator."""
    k = len(team)
    own = _known(data, s.perks, data.survivor)
    out = []
    for e in own:
        kind = e["kind"]
        if kind == "self":
            out.append((e["name"], e["value"]))
        elif kind == "self_with_others" and k >= 2:
            out.append((e["name"], e["value"]))
    team_perks = [e for m in team for e in _known(data, m.perks, data.survivor)]
    for kind in ("team_per_other", "team", "team_timed"):          # one instance each, for everyone there
        e = next((x for x in team_perks if x["kind"] == kind), None)
        if not e:
            continue
        if kind == "team_per_other" and k >= 2:
            out.append((e["name"], min(e["value"] * (k - 1), e["max"])))
        elif kind == "team":
            out.append((e["name"], e["value"]))
        elif kind == "team_timed" and buff:
            out.append((e["name"], e["value"]))
    if toolbox_on and s.toolbox in data.toolboxes:
        out.append((s.toolbox, data.toolboxes[s.toolbox]["bonus"]))
    return out


def _bonuses(data: Data, s: Survivor, team, toolbox_on: bool, buff: bool) -> list:
    return [v for _name, v in bonus_parts(data, s, team, toolbox_on, buff)]


def speed(data: Data, s: Survivor, team, killer: Killer, scen: Scenario, toolbox_on: bool = True,
          buff: bool = False) -> float:
    """Charges per second Survivor ``s`` adds by repairing (without skill checks)."""
    k = len(team)
    pos = sum(ranked(_bonuses(data, s, team, toolbox_on, buff), scen.diminishing)) + \
        sum(v for _name, v in addon_bonus_parts(data, s, toolbox_on))
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
    tool = [tool_charges(data, s) for s in team]
    quiet = [any(a.get("no_checks") for a in item_addons(data, s)) for s in team]     # Instructions: no checks

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
            if tool[i] > 0 and quiet[i]:                   # with the toolbox in use no regular Skill Check comes
                chance = 0.0
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
        # 1.52: repairing runs at one rate until something changes – the Generator is done, the Killer comes, a
        # toolbox is empty, a timed bonus ends – so the time jumps to the nearest of these instead of taking
        # thousands of DT steps (measured: a render of the page 4–5 times faster, the same seconds)
        gain, drain = rates(buff_s > 0)
        ahead = []                                     # (seconds until it happens, what, which toolbox)
        if gain > 0:
            ahead.append(((need - prog) / gain, "done", 0))
            goal = scen.kick_at * need
            if kicks_done < scen.kicks and events < m["regression_events"] and prog < goal:
                ahead.append(((goal - prog) / gain, "kick", 0))
        for i, d in enumerate(drain):
            if tool[i] > 0 and d > 0:
                ahead.append((tool[i] / d, "tool", i))
        if buff_s > 0:
            ahead.append((buff_s, "buff", 0))
        if not ahead:                                  # no progress and nothing that would change that
            return Result(None, start_rates, events, lost, notes)
        dt, what, which = min(ahead)
        t += dt
        if what == "done":
            break
        prog = scen.kick_at * need if what == "kick" else max(0.0, prog + gain * dt)
        for i, d in enumerate(drain):
            if tool[i] > 0:
                tool[i] = 0.0 if what == "tool" and i == which else max(0.0, tool[i] - d * dt)
        buff_s = 0.0 if what == "buff" else max(0.0, buff_s - dt)
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


# ---------------------------------------------------------------------------------------------------------------
# Every other area (1.52): healing, movement, vaults, totems, chests, gates, hooks, the Killer's own actions.
# One rule for all of them (wiki "Dead by Daylight Maths", patch notes 9.6.0): speed = (1 + Σ bonus) · Π(1 − malus),
# each sign after diminishing returns – status effects (Haste, Hindered) included, negative modifiers ranked only
# among those of one role. For Haste together with Hindered the wiki gives no formula of its own; the action-speed
# rule is used (assumption, the page says so).
# ---------------------------------------------------------------------------------------------------------------
KILLER = -1                          # the subject "the Killer" (Survivors are 0 … 3)
REPAIR = "repair"


@dataclass
class Part:
    """One modifier of a line: where it comes from, what it says and what of it counts."""
    source: str                       # perk or item name
    value: float                      # nominal share, signed (+0.5, −0.2); 0 for a cap
    weight: float = 1.0               # share that counts after diminishing returns
    when: str = ""                    # condition code ("" = always): injured, gates, boon, hex, trigger, tokens …
    seconds: float = 0.0              # lasts this long (0 = as long as the condition holds)
    stacks: int = 0                   # Tokens/stacks counted in ``value`` (0 = none)
    side: str = "S"                   # whose perk it is
    cap: float | None = None          # the sum of all bonuses is limited to this (Hex: Under Your Thumb)
    exempt: bool = False              # from an add-on: counts fully, is not ranked (patch notes 9.6.0)

    @property
    def counted(self) -> float:
        return self.value * self.weight


@dataclass
class Line:
    """One row of an area for one subject: the base value, the speed factor and the result."""
    area: str
    row: str
    subject: int                      # Survivor index or KILLER
    kind: str                         # "time" (s, lower is faster) or "speed" (m/s)
    base: float | None                # None: only the factor is known
    mult: float
    result: float | None
    parts: list = field(default_factory=list)
    label: str = ""                   # the wiki's own name of the row (a Killer's mode: "Cloaked"), else ""


def acts_in(data: Data, entry: dict, area_id: str) -> bool:
    """The perk has an effect on at least one row of the area."""
    tags = {t for r in data.areas.get(area_id, {}).get("rows", ()) for t in r["tags"]}
    return any(tags & set(f["tags"]) for f in entry.get("effects", ()))


def perk_names(data: Data, side: str, area_id: str) -> list:
    """The perks of a side ("S"/"K") that do something in the area, sorted (repair: the generator lists)."""
    if area_id == REPAIR:
        names = data.survivor if side == "S" else data.killer
    else:
        names = [n for n, e in data.perks.items() if e["side"] == side and acts_in(data, e, area_id)]
    return sorted(names, key=str.lower)


def max_stacks(data: Data, name: str) -> int:
    """The most Tokens a perk's effects count (0 = it has none)."""
    return max((int(f.get("max_n", 0)) for f in data.perks.get(name, {}).get("effects", ())), default=0)


def _effect_value(f: dict, n: int) -> float:
    if "per" not in f:
        return float(f.get("value", 0.0))
    n = max(0, min(int(n), int(f.get("max_n", n))))
    if f.get("full_at") and n >= f["full_at"]:
        return float(f["full"])
    if "first" in f:                                   # the first Token counts differently (Hex: Pentimento)
        return float(f["first"] + f["per"] * (n - 1)) if n >= 1 else 0.0
    v = float(f.get("value", 0.0)) + f["per"] * n
    return max(v, -f["max"]) if "max" in f and v < 0 else min(v, f["max"]) if "max" in f else v


def _stack_count(data: Data, name: str, f: dict, side: str, killer: Killer, scen: Scenario) -> int:
    top = int(f.get("max_n", 0))
    if not top:
        return 0
    if side == "K":
        try:
            return max(0, min(int(killer.counts.get(name, top)), top))
        except (TypeError, ValueError):
            return top
    return max(1, min(top, int(round(top * scen.stacks))))


def _holds(data: Data, s: Survivor, item) -> bool:
    """The Survivor has an item of this kind in hand ("medkit"; True means the same, "toolbox")."""
    return s.toolbox in data.toolboxes if item == "toolbox" else s.medkit in data.medkits


def killer_addons(data: Data, killer: Killer) -> list:
    """The add-on entries that count: of the chosen Killer, each once, two at most."""
    out = []
    for name in dict.fromkeys(killer.addons):
        e = data.killer_addons.get(name)
        if e and e["killer"] == killer.name and len(out) < 2:
            out.append(e)
    return out


def killer_addon_names(data: Data, killer_name: str) -> list:
    """The add-ons of a Killer the calculator knows (those with a speed it can compute), sorted."""
    return sorted((n for n, e in data.killer_addons.items() if e["killer"] == killer_name), key=str.lower)


def item_addon_names(data: Data, item: str) -> list:
    """The add-ons that fit an item name (a toolbox or a med-kit), sorted; [] for no item."""
    kind = "toolbox" if item in data.toolboxes else "medkit" if item in data.medkits else ""
    return sorted((n for n, e in data.item_addons.items() if e["item"] == kind), key=str.lower)


def area_rows(data: Data, area_id: str, killer: Killer | None = None) -> list:
    """The rows of an area. The Killer's movement with a Killer chosen: that Killer's own speed (and the speeds
    of the power's modes as the wiki lists them – shown, no perk is applied to them) instead of the three usual."""
    area = data.areas.get(area_id) or {}
    rows = list(area.get("rows", ()))
    k = data.killers.get(killer.name) if killer else None
    if area_id != "k_move" or not k:
        return rows
    out = [{"id": "kbase", "base": k["speed"], "tags": ["kmove"], "label": k.get("mode", "")}]
    out += [{"id": f"kalt{i}", "base": v, "tags": ["kpower"], "label": label}
            for i, (v, label) in enumerate(k.get("alt", ()))]
    return out + [r for r in rows if "carry" in r["tags"]]


def modifiers(data: Data, area_id: str, row: dict, subject: int, team, killer: Killer | None = None,
              scen: Scenario | None = None) -> list:
    """The Parts acting on ``row`` for ``subject`` (a Survivor index or KILLER), weighted by diminishing returns."""
    killer, scen = killer or Killer(), scen or Scenario()
    tags = set(row["tags"])
    found = []                                            # (Part, group)

    def take(name: str, wanted: tuple, holder: Survivor | None = None):
        e = data.perks.get(name)
        if not e:
            return
        for f in e["effects"]:
            if f["to"] not in wanted or not tags & set(f["tags"]):
                continue
            if f.get("no_item") and holder is not None and _holds(data, holder, f["no_item"]):
                continue
            n = _stack_count(data, name, f, e["side"], killer, scen)
            v = _effect_value(f, n)
            if not v and "cap" not in f:
                continue
            found.append((Part(name, v, 1.0, f.get("when", ""), float(f.get("seconds", 0.0)), n, e["side"],
                               f.get("cap")), f.get("group", "")))

    def take_addons(wanted: str):
        """The Killer's add-ons: counted fully and never ranked; where an add-on only strengthens an effect of the
        power, the power's own value comes with it (ranked like any modifier, once)."""
        for e in killer_addons(data, killer):
            for f in e["effects"]:
                if f["to"] != wanted or not tags & set(f["tags"]):
                    continue
                power = f.get("power", "")
                found.append((Part(power or e["name"], float(f["value"]), 1.0, f.get("when", ""),
                                   float(f.get("seconds", 0.0)), 0, "K", None, not power),
                              "power:" + power if power else f.get("group", "")))

    if subject == KILLER:
        for name in dict.fromkeys(killer.perks):
            take(name, ("self",))
        take_addons("self")
        for name in dict.fromkeys(p for s in team for p in s.perks):          # a perk of two Survivors: once
            take(name, ("enemy",))
    else:
        me = team[subject]
        for name in dict.fromkeys(me.perks):
            take(name, ("self", "team"), me)
        mine = set(me.perks)
        others = dict.fromkeys(p for i, s in enumerate(team) if i != subject for p in s.perks)
        for name in others:
            take(name, ("others",) if name in mine else ("others", "team"), me)
        for name in dict.fromkeys(killer.perks):
            take(name, ("enemy",))
        take_addons("enemy")
        mine = item_addons(data, me)
        if me.medkit in data.medkits:
            if "altruistic" in tags:
                found.append((Part(me.medkit, data.medkits[me.medkit]["bonus"]), ""))
            if "heal" in tags:                             # with the kit in hand: healing others and oneself
                found += [(Part(a["name"], a["heal"], exempt=True), "") for a in mine if a.get("heal")]
        if "sabotage" in tags and me.toolbox in data.toolboxes:
            if data.toolboxes[me.toolbox].get("sabotage"):
                found.append((Part(me.toolbox, data.toolboxes[me.toolbox]["sabotage"]), ""))
            found += [(Part(a["name"], a["sabotage"], exempt=True), "") for a in mine if a.get("sabotage")]
    parts, groups = [], {}
    for part, group in found:                             # of one group (Exhaustion perks) only the strongest
        if group:
            best = groups.get(group)
            if best is None or abs(part.value) > abs(best.value):
                groups[group] = part
        else:
            parts.append(part)
    parts += list(groups.values())
    for sign, side in ((1, None), (-1, "S"), (-1, "K")):  # negative modifiers: ranked within their role
        same = [p for p in parts if p.cap is None and not p.exempt and
                (p.value > 0 if sign > 0 else p.value < 0 and p.side == side)]
        for p, w in zip(same, weights([p.value for p in same], scen.diminishing)):
            p.weight = w
    parts.sort(key=lambda p: (p.value < 0, -abs(p.value)))
    return parts


def factor(parts) -> float:
    """The speed factor of a list of Parts: (1 + Σ bonus, capped) · Π(1 − malus)."""
    pos = sum(p.counted for p in parts if p.value > 0)
    caps = [p.cap for p in parts if p.cap is not None]
    if caps:
        pos = min(pos, min(caps))
    out = 1.0 + pos
    for p in parts:
        if p.value < 0:
            out *= max(0.0, 1.0 + p.counted)
    return out


def area_lines(data: Data, area_id: str, team, killer: Killer | None = None, scen: Scenario | None = None) -> list:
    """Every row of the area for every subject (each Survivor of ``team``, or the Killer)."""
    area = data.areas.get(area_id)
    if not area or area.get("kind") == REPAIR:
        return []
    team = [s for s in team if isinstance(s, Survivor)][:MAX_SURVIVORS]
    subjects = [KILLER] if area["side"] == "K" else list(range(len(team)))
    out = []
    rows = area_rows(data, area_id, killer)
    for subject in subjects:
        for row in rows:
            parts = modifiers(data, area_id, row, subject, team, killer, scen)
            mult = factor(parts)
            base = row.get("base")
            if base is None or mult <= 0:
                result = None
            else:
                result = base * mult if area["kind"] == "speed" else base / mult
            out.append(Line(area_id, row["id"], subject, area["kind"], base, mult, result, parts,
                            row.get("label", "")))
    return out


def repair_parts(data: Data, team, index: int, killer: Killer | None = None, scen: Scenario | None = None) -> list:
    """The repair-speed modifiers of Survivor ``index`` while ``team`` repairs together, as Parts (toolbox on,
    no timed bonus) – the same numbers ``speed`` multiplies."""
    killer, scen = killer or Killer(), scen or Scenario()
    pos = [Part(n, v) for n, v in bonus_parts(data, team[index], team)]
    neg = [Part(n, -v, side="K") for n, v in slowdown_parts(data, killer)]
    for group in (pos, neg):
        for p, w in zip(group, weights([p.value for p in group], scen.diminishing)):
            p.weight = w
    pos += [Part(n, v, exempt=True) for n, v in addon_bonus_parts(data, team[index])]
    for group in (pos, neg):
        group.sort(key=lambda p: -abs(p.value))
    return pos + neg


@dataclass
class Tip:
    """A perk worth adding: who would take it, and what it changes."""
    name: str
    side: str                         # "S" or "K"
    who: int                          # the Survivor index it was tried on (KILLER for a Killer perk)
    gain: float                       # relative change of the metric (0.12 = 12 %)
    row: str                          # the row it changes most ("" = the Generator)
    before: float | None
    after: float | None
    subject: int = KILLER             # whose row ``row`` is (the taker's own when the perk changes one of theirs)


def _with_perk(team, i: int, name: str) -> list:
    out = list(team)
    s = team[i]
    out[i] = replace(s, perks=tuple(s.perks) + (name,))
    return out


def _line_change(old: Line, new: Line) -> float:
    return new.mult / old.mult - 1.0 if old.mult > 0 else 0.0


def suggest(data: Data, area_id: str, team, killer: Killer | None = None, scen: Scenario | None = None,
            slots: int = 4, top: int = 3) -> dict:
    """{"S": [Tip], "K": [Tip]}: for each side the perks (not chosen yet, a free slot given) that help it most in
    this area – Survivors: faster, the Killer: slower Survivors (or a faster Killer in the Killer's own areas)."""
    killer, scen = killer or Killer(), scen or Scenario()
    team = [s for s in team if isinstance(s, Survivor)][:MAX_SURVIVORS]
    out = {"S": [], "K": []}
    if not team or area_id not in data.areas:
        return out
    killer_area = data.areas[area_id]["side"] == "K"
    free, seen = [], set()
    for i, s in enumerate(team):                          # equal builds: the perk is tried on the first only
        build = (tuple(s.perks), s.toolbox, s.part, s.medkit, tuple(s.addons))
        if len(s.perks) < slots and build not in seen:
            seen.add(build)
            free.append(i)
    kill_free = len(killer.perks) < slots

    if area_id == REPAIR:
        base = one_generator(data, team, killer, scen).seconds
        if base is None:
            return out
        best = {}
        for name in data.survivor:
            group = data.survivor[name].get("group", name)
            for i in free:
                if any(data.survivor.get(p, {}).get("group", p) == group for p in team[i].perks):
                    continue
                t = one_generator(data, _with_perk(team, i, name), killer, scen).seconds
                if t is not None and t < base - 0.05 and (name not in best or t < best[name].after):
                    best[name] = Tip(name, "S", i, (base - t) / base, "", base, t, i)
        out["S"] = sorted(best.values(), key=lambda x: -x.gain)[:top]
        if kill_free:
            tips = []
            for name in data.killer:
                if name in killer.perks:
                    continue
                t = one_generator(data, team, replace(killer, perks=tuple(killer.perks) + (name,)),
                                  scen).seconds
                if t is not None and t > base + 0.05:
                    tips.append(Tip(name, "K", KILLER, (t - base) / base, "", base, t))
            out["K"] = sorted(tips, key=lambda x: -x.gain)[:top]
        return out

    lines = area_lines(data, area_id, team, killer, scen)

    def tip(name: str, side: str, who: int, new_lines, want_more: bool):
        changes = [(_line_change(a, b), a, b) for a, b in zip(lines, new_lines)]
        total = sum(c for c, _a, _b in changes)
        if (total if want_more else -total) < 1e-6:
            return None
        sign = 1 if want_more else -1
        own = [x for x in changes if x[1].subject == who and sign * x[0] > 1e-9]       # the taker's own rows first
        c, a, b = max(own or changes, key=lambda x: sign * x[0])
        return Tip(name, side, who, abs(total) / max(1, len({ln.subject for ln in lines})), a.row, a.result, b.result,
                   a.subject)

    best = {}
    for name in perk_names(data, "S", area_id):
        for i in free:
            if name in team[i].perks:
                continue
            t = tip(name, "S", i, area_lines(data, area_id, _with_perk(team, i, name), killer, scen),
                    want_more=not killer_area)
            if t and (name not in best or t.gain > best[name].gain):
                best[name] = t
    out["S"] = sorted(best.values(), key=lambda x: -x.gain)[:top]
    if kill_free:
        tips = []
        for name in perk_names(data, "K", area_id):
            if name in killer.perks:
                continue
            t = tip(name, "K", KILLER,
                    area_lines(data, area_id, team, replace(killer, perks=tuple(killer.perks) + (name,)), scen),
                    want_more=killer_area)
            if t:
                tips.append(t)
        out["K"] = sorted(tips, key=lambda x: -x.gain)[:top]
    return out
