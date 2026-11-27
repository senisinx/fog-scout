"""1.52 (Saru: "für alle Elemente von Diminishing Returns … Haste, Repair, Vault … nur eine Perkauswahl bei einem
Survivor … schlauer": breakdown, best next perk, two builds): the calculator's other areas (gencalc.area_lines),
its page and the perk pictures (perkicons)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fogscout import app_calc, perkicons  # noqa: E402
from fogscout import gencalc as g  # noqa: E402

D = g.load()
S, K, Sc = g.Survivor, g.Killer, g.Scenario


def line(area, row, team, killer=None, scen=None, subject=0):
    return next(ln for ln in g.area_lines(D, area, team, killer, scen) if ln.row == row and ln.subject == subject)


def test_the_base_values_are_the_wikis():
    """Health States (16 Charges, recovery 30.4 s), Med-Kits (self-heal 24 s), Vaulting, Pallets, Totems, Chests,
    Exit Gates, Hooks, Movement Speeds, Generators (damage), Breakable Walls, Lockers – without a perk."""
    want = {("heal", "heal_other"): 16.0, ("heal", "heal_self"): 24.0, ("heal", "recover"): 30.4,
            ("vault", "window_fast"): 0.5, ("vault", "window_medium"): 0.9, ("vault", "window_slow"): 1.5,
            ("vault", "pallet_fast"): 1.1, ("vault", "pallet_slow"): 2.0, ("objects", "cleanse"): 14.0,
            ("objects", "bless_hex"): 28.0, ("objects", "chest"): 8.0, ("objects", "gate"): 20.0,
            ("hook", "unhook"): 1.0, ("hook", "sabotage"): 3.0, ("move", "run"): 4.0, ("move", "walk"): 2.26,
            ("move", "crouch"): 1.13, ("move", "crawl"): 0.7}
    for (area, row), value in want.items():
        ln = line(area, row, [S()])
        assert ln.result == pytest.approx(value) and ln.mult == 1.0 and ln.parts == []
    want = {("k_move", "k460"): 4.6, ("k_move", "carry"): 3.68, ("k_action", "kvault"): 1.7,
            ("k_action", "break"): 2.34, ("k_action", "damage"): 1.8, ("k_action", "locker"): 2.333,
            ("k_attack", "hit"): 2.7, ("k_attack", "miss"): 1.5}
    for (area, row), value in want.items():
        assert line(area, row, [S()], subject=g.KILLER).result == pytest.approx(value)
    assert g.area_lines(D, "repair", [S()]) == [] and g.area_lines(D, "no such area", [S()]) == []


def test_diminishing_returns_rank_the_bonuses_of_every_area():
    """Patch 9.6.0: 100 / 50 / 25 / 12.5 / 5 % from the largest down – for healing as for repairing."""
    assert g.weights([0.3, -0.8, 0.5, 0.1, 0.2, 0.05]) == [0.25, 1.0, 0.5, 0.05, 0.125, 0.05]
    assert g.weights([0.3, 0.8], diminishing=False) == [1.0, 1.0]
    assert line("heal", "heal_other", [S(("Botany Knowledge",))]).result == pytest.approx(16 / 1.5)
    both = [S(("Botany Knowledge", "Empathic Connection"))]
    ln = line("heal", "heal_other", both)
    assert ln.mult == pytest.approx(1 + 0.5 + 0.4 * 0.5)
    assert [(p.source, p.weight) for p in ln.parts] == [("Botany Knowledge", 1.0), ("Empathic Connection", 0.5)]
    assert line("heal", "heal_other", both, scen=Sc(diminishing=False)).mult == pytest.approx(1.9)
    assert line("heal", "heal_self", both).result == pytest.approx(24 / 1.5)      # altruistic only: not for oneself
    assert line("heal", "recover", both).mult == 1.0                              # recovering is not healing


def test_a_med_kit_counts_as_a_bonus_and_circle_of_healing_needs_none():
    kit = [S(("Botany Knowledge",), medkit="Ranger Med-Kit"), S(("Boon: Circle of Healing",))]
    ln = line("heal", "heal_other", kit)
    assert ln.mult == pytest.approx(1 + 0.5 + 0.5 * 0.5)          # the Boon does not act with a Med-Kit in hand
    assert {p.source for p in ln.parts} == {"Botany Knowledge", "Ranger Med-Kit"}
    assert line("heal", "heal_self", kit).mult == pytest.approx(1.5)     # the kit's bonus is for healing others
    bare = [S(("Botany Knowledge",)), S(("Boon: Circle of Healing",))]
    assert line("heal", "heal_other", bare).mult == pytest.approx(1 + 1.0 + 0.5 * 0.5)
    assert line("heal", "heal_other", bare, subject=1).mult == pytest.approx(2.0)   # the Boon's owner too


def test_the_killers_penalties_multiply_and_rank_among_themselves():
    """Negative modifiers multiply; diminishing returns only within the role (here: the Killer's two)."""
    k = K(("Coulrophobia", "Hex: Pentimento"), {"Hex: Pentimento": 2})          # −30 %, −23 % (20 + 3)
    ln = line("heal", "heal_other", [S(("Botany Knowledge",))], k)
    assert ln.mult == pytest.approx(1.5 * (1 - 0.30) * (1 - 0.23 * 0.5))
    assert [p.weight for p in ln.parts] == [1.0, 1.0, 0.5]                      # the bonus is ranked on its own
    assert line("heal", "heal_other", [S()], K(("Hex: Pentimento",), {"Hex: Pentimento": 0})).mult == 1.0
    assert line("heal", "heal_other", [S()], K(("Hex: Pentimento",))).mult == pytest.approx(1 - 0.32)   # 5 Tokens
    # Thanatophobia: 2 % per Survivor, 20 % with all four (the wiki's secondary effect)
    assert line("objects", "cleanse", [S()], K(("Thanatophobia",), {"Thanatophobia": 2})).mult == \
        pytest.approx(0.96)
    assert line("objects", "cleanse", [S()], K(("Thanatophobia",), {"Thanatophobia": 4})).result == \
        pytest.approx(14 / 0.8)
    assert line("objects", "gate", [S()], K(("Thanatophobia",))).mult == 1.0     # not for the gates


def test_haste_of_one_exhaustion_perk_only_and_the_cap_of_under_your_thumb():
    runner = [S(("Sprint Burst", "Lithe", "Hope"))]
    ln = line("move", "run", runner)
    assert ln.result == pytest.approx(4.0 * (1 + 0.5 + 0.05 * 0.5))            # Sprint Burst or Lithe, never both
    # 1.54.1: the one that does not count stays in the breakdown and says beside which – before, a chosen perk
    # was simply gone
    assert [(p.source, p.beaten, p.counted) for p in ln.parts] == [
        ("Sprint Burst", "", 0.5), ("Lithe", "Sprint Burst", 0.0), ("Hope", "", 0.025)]
    assert g.factor(ln.parts) == pytest.approx(ln.mult)
    assert ln.parts[0].seconds == 2 and ln.parts[0].when == "trigger" and ln.parts[2].when == "gates"
    capped = line("move", "run", runner, K(("Hex: Under Your Thumb",)))
    assert capped.result == pytest.approx(4.0 * 1.15)
    assert line("move", "walk", runner, K(("Hex: Under Your Thumb",))).mult == pytest.approx(1.525)
    slowed = line("move", "run", [S()], K(("Forced Hesitation", "Hex: Nothing but Misery")))
    assert slowed.result == pytest.approx(4.0 * 0.8 * (1 - 0.05 * 0.5))
    assert line("move", "crouch", [S(("Urban Evasion",))]).result == pytest.approx(2.26)   # the wiki's table
    assert line("move", "walk", [S(("Urban Evasion", "Fixated"))]).result == pytest.approx(2.712)


def test_a_perk_acts_only_on_its_rows_and_on_the_right_survivors():
    v = [S(("Finesse", "Resilience"))]
    assert line("vault", "window_fast", v).mult == pytest.approx(1 + 0.2 + 0.09 * 0.5)
    assert line("vault", "window_medium", v).mult == pytest.approx(1.09)       # Finesse: fast vaults only
    assert line("vault", "pallet_fast", v).mult == pytest.approx(1.2)          # Resilience: windows only
    assert line("vault", "pallet_slow", v).mult == 1.0
    assert line("vault", "pallet_slow", v, K(("Hex: Nothing but Misery",))).mult == pytest.approx(0.9)
    team = [S(("Leader",)), S(), S(("Leader",))]
    assert line("objects", "gate", team, subject=0).mult == pytest.approx(1.3)  # from the other Leader
    assert line("objects", "gate", team, subject=1).mult == pytest.approx(1.3)  # two Leaders: once
    assert line("objects", "gate", [S(("Leader",)), S()], subject=0).mult == 1.0    # not for its owner
    # 1.55.2 (patch 10.3.0): others unhook you 65/70/75 % faster (was 90/95/100 %) – tier III: 1 s / 1.75
    assert line("hook", "unhook", [S(("Slippery Meat",)), S()], subject=1).result == pytest.approx(1 / 1.75)
    # Tokens of a Survivor perk: all, half, one
    flow = [S(("Flow State",))]
    assert line("objects", "bless", flow).mult == pytest.approx(1.75)
    assert line("objects", "bless", flow, scen=Sc(stacks=0.5)).mult == pytest.approx(1 + 0.15 * 2)
    assert line("objects", "bless", flow, scen=Sc(stacks=0.0)).mult == pytest.approx(1.15)
    assert line("objects", "gate", [S(("Wake Up!",))]).mult == pytest.approx(1.7)        # 10 % + 4 · 15 %
    # Counterforce: the wiki says it raises the default cleansing speed *to* 125 % (not by 125 %, as 1.52 had it),
    # and +25 % for every totem cleansed
    assert line("objects", "cleanse", [S(("Counterforce",))], scen=Sc(stacks=0.0)).result == pytest.approx(14 / 1.5)
    assert line("objects", "cleanse", [S(("Counterforce",))]).mult == pytest.approx(1 + 0.25 + 4 * 0.25)


def test_the_killers_own_actions_and_what_survivors_do_to_them():
    k = K(("Fire Up", "Brutal Strength", "Bamboozle"), {"Fire Up": 3})
    assert line("k_action", "break", [S()], k, subject=g.KILLER).result == pytest.approx(2.34 / (1 + 0.24 + 0.1))
    assert line("k_action", "kvault", [S()], k, subject=g.KILLER).result == pytest.approx(1.7 / (1 + 0.24 + 0.075))
    pick = line("k_action", "pickup", [S()], K(("Fire Up",)), subject=g.KILLER)
    assert pick.result is None and pick.base is None and pick.mult == pytest.approx(1.4)   # speed only
    assert line("k_attack", "miss", [S()], K(("Unrelenting",)), subject=g.KILLER).result == pytest.approx(1.5 / 1.4)
    assert line("k_attack", "hit", [S()], K(("Unrelenting",)), subject=g.KILLER).result == pytest.approx(2.7 / 1.1)
    blind = [S(("Champion of Light",)), S(("Champion of Light",))]
    ln = line("k_move", "k460", blind, K(("Batteries Included",)), subject=g.KILLER)
    assert ln.result == pytest.approx(4.6 * 1.05 * 0.8) and len(ln.parts) == 2          # the perk of two: once
    assert line("k_move", "carry", [S()], K(("Agitation",)), subject=g.KILLER).result == pytest.approx(4.3424)
    assert line("k_move", "k460", [S()], K(("Agitation",)), subject=g.KILLER).mult == 1.0


def test_the_values_changed_by_patch_10_3_0():
    """1.55.2 (tools/check_perkdata.py reported them): Calm Spirit 23/24/25 % (was 8/9/10 %), Dark Arrogance
    vaulting +15 % and hit recovery +13/14/15 %, but missed attacks recover 15 % slower (was +25 % / +10 % on both)."""
    calm = [S(("Calm Spirit",))]
    for row in ("cleanse", "bless", "chest"):
        assert line("objects", row, calm).mult == pytest.approx(1.25)              # 14 s → 11.2 s, 8 s → 6.4 s
    assert line("objects", "chest", calm).result == pytest.approx(6.4)
    assert line("objects", "gate", calm).mult == 1.0
    da = K(("Dark Arrogance",))
    assert line("k_action", "kvault", [S()], da, subject=g.KILLER).result == pytest.approx(1.7 / 1.15)
    assert line("k_attack", "hit", [S()], da, subject=g.KILLER).result == pytest.approx(2.7 / 1.15)
    assert line("k_attack", "miss", [S()], da, subject=g.KILLER).result == pytest.approx(1.5 / 0.85)
    # with Unrelenting (+40 % after a miss): bonuses add, the penalty multiplies – 1.5 / (1.4 · 0.85)
    both = K(("Dark Arrogance", "Unrelenting"))
    assert line("k_attack", "miss", [S()], both, subject=g.KILLER).result == pytest.approx(1.5 / (1.4 * 0.85))


def test_skill_check_perks_count_on_generators_and_are_named_where_they_cannot():
    """1.55.2: the heal rows have no Skill Checks (a fixed time per Health State), so what Deadline, One-Two-Three-
    Four!, Bardic Inspiration and Unnerving Presence do while healing – and the healing-only perks Autodidact, Bite
    the Bullet, Reactive Healing and Resurgence – is named as not calculated instead of invented."""
    checks = ("Deadline", "One-Two-Three-Four!", "Bardic Inspiration", "Technician")
    assert all(n in g.perk_names(D, "S", "repair") for n in checks)
    assert "Unnerving Presence" in g.perk_names(D, "K", "repair")
    for name in ("Deadline", "One-Two-Three-Four!", "Bardic Inspiration", "Unnerving Presence", "Autodidact",
                 "Bite the Bullet", "Reactive Healing", "Resurgence"):
        assert name in D.not_modelled_areas and name not in D.perks, name
    healer = [S(("Deadline", "One-Two-Three-Four!", "Bardic Inspiration")), S(("Bardic Inspiration",))]
    assert all(ln.mult == 1.0 for ln in g.area_lines(D, "heal", healer, K(("Unnerving Presence",))))


def test_the_repair_breakdown_gives_the_speed_the_generator_runs_at():
    team = [S(("Prove Thyself", "Resilience", "Déjà Vu"), "Commodious Toolbox"), S()]
    k = K(("Thanatophobia", "Distressing"), {"Thanatophobia": 4})
    for i in range(2):
        parts = g.repair_parts(D, team, i, k)
        assert g.factor(parts) * 0.85 == pytest.approx(g.speed(D, team[i], team, k, Sc()))
    first = g.repair_parts(D, team, 0, k)
    assert [(p.source, p.weight) for p in first] == [
        ("Commodious Toolbox", 1.0), ("Prove Thyself", 0.5), ("Resilience", 0.25), ("Déjà Vu", 0.125),
        ("Thanatophobia", 1.0), ("Distressing", 0.5)]
    assert all(p.weight == 1.0 for p in g.repair_parts(D, team, 0, k, Sc(diminishing=False)))


def test_the_best_next_perk_is_one_that_really_helps_most():
    team = [S(("Botany Knowledge",)), S(("A", "B", "C", "D"))]          # the second build is full
    tips = g.suggest(D, "heal", team, K())
    assert tips["S"] and all(t.who == 0 and t.name != "Botany Knowledge" for t in tips["S"])
    assert [t.gain for t in tips["S"]] == sorted((t.gain for t in tips["S"]), reverse=True)
    best = tips["S"][0]
    after = line("heal", best.row, [S(("Botany Knowledge", best.name)), team[1]])
    assert after.result == pytest.approx(best.after) and best.after < best.before and best.subject == 0
    # a perk that only helps the others: the row quoted is theirs
    lead = next(t for t in g.suggest(D, "objects", [S(), S()], K(), top=99)["S"] if t.name == "Leader")
    assert lead.subject != lead.who and lead.after < lead.before
    assert tips["K"] and all(t.after > t.before for t in tips["K"])    # the Killer: slower Survivors
    full = [S(("A", "B", "C", "D"))]
    assert g.suggest(D, "heal", full, K(("a", "b", "c", "d")))== {"S": [], "K": []}
    # the Killer's own area: the Killer gets faster, a Survivor perk makes the Killer slower
    tips = g.suggest(D, "k_move", [S()], K())
    assert tips["K"][0].after > tips["K"][0].before and tips["S"][0].after < tips["S"][0].before
    # Generators: Survivors faster, the Killer slower – measured on one Generator with everyone
    rep = g.suggest(D, "repair", [S(("Prove Thyself",)), S()], K())
    assert rep["S"][0].after < rep["S"][0].before and rep["K"][0].after > rep["K"][0].before
    base = g.one_generator(D, [S(("Prove Thyself",)), S()], K(), Sc()).seconds
    assert rep["S"][0].before == rep["K"][0].before == base
    assert g.suggest(D, "repair", [], K()) == {"S": [], "K": []}


def test_the_data_file_names_only_what_the_calculator_and_the_page_know():
    """Every area and row has a name on the page, every effect a row it can act on, a known receiver and a known
    condition; a perk in two lists (Generators and the other areas) is the same perk of the same side."""
    with open(g.FILE, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert [a["id"] for a in raw["areas"]] == list(app_calc.AREAS)
    tags = set()
    for a in raw["areas"]:
        assert a["side"] in ("S", "K") and a["kind"] in ("repair", "time", "speed")
        for r in a.get("rows", ()):
            assert r["id"] in app_calc.ROWS and (r["base"] is None or r["base"] > 0)
            tags.update(r["tags"])
    names = [e["name"] for e in raw["perks"]]
    assert len(names) == len(set(names)) and len(names) > 80
    for e in raw["perks"]:
        assert e["side"] in ("S", "K") and e["effects"], e["name"]
        other = D.killer if e["side"] == "S" else D.survivor
        assert e["name"] not in other, e["name"]
        for f in e["effects"]:
            assert set(f["tags"]) <= tags, e["name"]
            assert f["to"] in ("self", "others", "team", "enemy"), e["name"]
            assert f.get("when", "") in set(app_calc.WHEN) | {""}, e["name"]
            assert abs(f.get("value", 0)) <= 2.0 and ("per" in f) == ("max_n" in f), e["name"]
            assert f.get("value") or f.get("per") or f.get("cap") or f.get("first"), e["name"]
            if f["to"] == "enemy" and "cap" not in f:           # what one does to the other side slows it
                assert f.get("value", 0) <= 0 and f.get("per", 0) <= 0, e["name"]
    for area in app_calc.AREAS:
        assert g.perk_names(D, "S", area) or g.perk_names(D, "K", area)
    assert "Resilience" in g.perk_names(D, "S", "repair") and "Resilience" in g.perk_names(D, "S", "heal")
    assert "Botany Knowledge" not in g.perk_names(D, "S", "repair")
    assert g.max_stacks(D, "Fire Up") == 5 and g.max_stacks(D, "Bamboozle") == 0
    assert not set(D.not_modelled_areas) & set(D.perks)


def test_every_killer_has_its_own_speed_and_the_modes_of_its_power():
    """1.53 (Saru: "Jeder Killer soll drin sein mit seiner Base Speed und Addons"): wiki Module:Datatable –
    45 Killers, 4.6 m/s for most, 4.4 for some, 3.85 for The Nurse, 4.2 for The Shape while stalking; the speeds
    of the power's modes are shown as the wiki names them and take no perk."""
    assert len(D.killers) == 45
    speeds = {n: k["speed"] for n, k in D.killers.items()}
    assert speeds["The Trapper"] == 4.6 and speeds["The Huntress"] == 4.4 and speeds["The Nurse"] == 3.85
    assert speeds["The Shape"] == 4.2 and D.killers["The Shape"]["mode"] == "Stalker Mode"
    assert set(speeds.values()) <= {3.85, 4.2, 4.4, 4.6}
    rows = g.area_lines(D, "k_move", [S()], K(("Batteries Included",), name="The Wraith"))
    assert [(ln.row, ln.label, ln.base) for ln in rows] == [
        ("kbase", "Uncloaked", 4.6), ("kalt0", "Cloaked", 6.0), ("carry", "", 3.68)]
    assert rows[0].result == pytest.approx(4.6 * 1.05) and rows[1].result == 6.0 and rows[1].parts == []
    assert rows[2].result == pytest.approx(3.68 * 1.05)
    plain = g.area_lines(D, "k_move", [S()], K())                       # no Killer chosen: the three usual speeds
    assert [ln.row for ln in plain] == ["k460", "k440", "k385", "carry"]
    assert [ln.row for ln in g.area_lines(D, "k_move", [S()], K(name="No Such Killer"))] == [ln.row for ln in plain]


def test_a_killers_add_ons_count_fully_and_only_for_their_killer():
    """Patch notes 9.6.0: modifiers from add-ons are excluded from diminishing returns. Where an add-on only
    strengthens an effect of the power, the power's own value comes with it (once, ranked like a perk)."""
    clown = K(("Batteries Included",), name="The Clown", addons=("Cheap Gin Bottle", "Sticky Soda Bottle"))
    ln = line("k_move", "kbase", [S()], clown, subject=g.KILLER)
    assert ln.mult == pytest.approx(1 + 0.14 + 0.05 * 0.5 + 0.03 + 0.02)
    assert [(p.source, p.value, p.weight, p.exempt) for p in ln.parts] == [
        ("The Afterpiece Antidote", 0.14, 1.0, False), ("Batteries Included", 0.05, 0.5, False),
        ("Cheap Gin Bottle", 0.03, 1.0, True), ("Sticky Soda Bottle", 0.02, 1.0, True)]
    off = line("k_move", "kbase", [S()], clown, Sc(diminishing=False), subject=g.KILLER)
    assert off.mult == pytest.approx(1.24)
    # another Killer's add-on, a third add-on and the same one twice do nothing
    assert line("k_move", "kbase", [S()], K(name="The Trapper", addons=("Cheap Gin Bottle",)),
                subject=g.KILLER).mult == 1.0
    assert g.killer_addons(D, K(name="The Huntress", addons=("Infantry Belt", "Infantry Belt", "Leather Loop",
                                                              "Rusty Head"))) == \
        [D.killer_addons["Infantry Belt"], D.killer_addons["Leather Loop"]]
    assert g.killer_addons(D, K(addons=("Infantry Belt",))) == []
    # the Hag's shoe: her own speed up, Survivors near a trap down
    hag = K(name="The Hag", addons=("Waterlogged Shoe",))
    assert line("k_move", "kbase", [S()], hag, subject=g.KILLER).result == pytest.approx(4.73)
    assert line("move", "run", [S()], hag).result == pytest.approx(4.0 * 0.91)
    # Mangled is one status effect: from a perk and an add-on it counts once (−20 % healing speed)
    nurse = K(("Sloppy Butcher", "Coulrophobia"), name="The Nurse", addons=("Fragile Wheeze",))
    ln = line("heal", "heal_other", [S()], nurse)
    assert ln.mult == pytest.approx(0.7 * 0.8)                                      # the add-on's: not ranked
    assert [p.source for p in ln.parts if not p.beaten] == ["Coulrophobia", "Fragile Wheeze"]
    only = line("heal", "heal_other", [S()], K(name="The Nurse", addons=("Fragile Wheeze",)))
    assert only.result == pytest.approx(16 / 0.8) and only.parts[0].exempt and only.parts[0].seconds == 70
    # an add-on that helps both sides (The Animatronic's poster)
    party = K(name="The Animatronic", addons=("Celebrate! Poster",))
    assert line("k_action", "kvault", [S()], party, subject=g.KILLER).result == pytest.approx(1.7 / 1.2)
    assert line("vault", "window_fast", [S()], party).result == pytest.approx(0.5 / 1.2)
    assert line("move", "run", [S()], party).result == pytest.approx(4.48)
    # 1.54 (Saru: "Alle Addon sollen verfügbar sein für jeden Killer und Surv."): every add-on of the power is
    # offered, 20 for each of the 45 Killers; one the calculator cannot work out takes its place and adds nothing
    clown_all = g.killer_addon_names(D, "The Clown")
    assert len(clown_all) == 20 and clown_all == sorted(clown_all, key=str.lower)
    assert {"Cheap Gin Bottle", "Flask of Bleach", "Sticky Soda Bottle", "Sulphuric Acid Vial",
            "Robin Feather"} <= set(clown_all)
    assert all(len(g.killer_addon_names(D, name)) == 20 for name in D.killers) and g.killer_addon_names(D, "") == []
    assert '"Shadow Dance" - Blood' in g.killer_addon_names(D, "The Wraith")            # a name with quotes
    full = K(name="The Clown", addons=("Robin Feather", "Cheap Gin Bottle", "Sticky Soda Bottle"))
    assert g.killer_addons(D, full) == [D.killer_addons["Cheap Gin Bottle"]]            # the third has no place
    assert g.plain_addons(D, killer=full) == ["Robin Feather"]
    assert line("k_move", "kbase", [S()], full, subject=g.KILLER).mult == pytest.approx(1.17)
    cloaked = K(name="The Wraith", addons=('"Shadow Dance" - Blood',))
    assert line("k_action", "break", [S()], cloaked, subject=g.KILLER).result == pytest.approx(2.34 / 1.6)


def test_items_and_their_add_ons_for_healing_sabotage_and_repairing():
    """1.53 (Saru: "Surv: Items und Addons involvieren"): a med-kit's add-ons speed up healing with it (others and
    oneself), a toolbox's sabotage bonus and add-ons the sabotage, its repair add-ons the Generator – add-ons
    always fully."""
    medic = [S(("Botany Knowledge",), medkit="Ranger Med-Kit", addons=("Abdominal Dressing", "Medical Scissors"))]
    ln = line("heal", "heal_other", medic)
    assert ln.mult == pytest.approx(1 + 0.5 + 0.5 * 0.5 + 0.15 + 0.10)
    assert [p.exempt for p in ln.parts] == [False, False, True, True]
    assert line("heal", "heal_self", medic).result == pytest.approx(24 / (1 + 0.5 + 0.25))
    assert line("heal", "recover", medic).mult == 1.0
    # a toolbox add-on on a med-kit (and the other way round) does nothing; a third add-on neither
    wrong = [S(medkit="First Aid Kit", addons=("Socket Swivels", "Butterfly Tape", "Medical Scissors",
                                               "Abdominal Dressing"))]
    assert line("heal", "heal_other", wrong).mult == pytest.approx(1 + 0.4 + 0.05 + 0.10)
    assert g.item_addons(D, S(addons=("Butterfly Tape",))) == []                    # no item, no add-on
    # sabotage: the toolbox's own bonus is ranked with perks, the add-ons are not; Saboteur is for bare hands
    sab = [S(("Saboteur", "Resilience"), toolbox="Alex's Toolbox", addons=("Hacksaw", "Cutting Wire"))]
    ln = line("hook", "sabotage", sab)
    assert ln.mult == pytest.approx(1 + 1.0 + 0.09 * 0.5 + 0.3 + 0.2)
    assert "Saboteur" not in {p.source for p in ln.parts}
    assert line("hook", "sabotage", [S(("Saboteur",))]).result == pytest.approx(3 / 1.3)
    assert line("hook", "sabotage", [S(toolbox="Worn-Out Tools")]).mult == 1.0     # no sabotage bonus of its own
    assert line("hook", "unhook", sab).mult == pytest.approx(1.09)
    # repairing: Socket Swivels +30 % on top of the toolbox, Wire Spool +12 Charges, both while the box lasts
    box = S(toolbox="Toolbox", addons=("Socket Swivels", "Wire Spool"))
    calm = Sc(great=0, miss=0, kicks=0)
    assert g.tool_charges(D, box) == 32 and g.speed(D, box, [box], K(), calm) == pytest.approx(1.8)
    assert g.one_generator(D, [box], None, calm).seconds == pytest.approx(32 / 1.8 + 58, abs=0.01)
    with_perk = S(("Resilience",), "Toolbox", addons=("Socket Swivels",))
    assert g.speed(D, with_perk, [with_perk], K(), calm) == pytest.approx(1 + 0.5 + 0.09 * 0.5 + 0.3)
    parts = g.repair_parts(D, [with_perk], 0)
    assert [(p.source, p.weight, p.exempt) for p in parts] == [
        ("Toolbox", 1.0, False), ("Socket Swivels", 1.0, True), ("Resilience", 0.5, False)]
    assert g.factor(parts) == pytest.approx(g.speed(D, with_perk, [with_perk], K(), calm))
    # Brand New Part: 10 Charges less; Instructions: no regular Skill Check while the toolbox lasts
    part = S(toolbox="Toolbox", addons=("Brand New Part",))
    assert g.one_generator(D, [part], None, calm).seconds == pytest.approx(20 / 1.5 + 60, abs=0.01)
    great = Sc(great=1.0, miss=0, kicks=0)
    quiet = g.one_generator(D, [S(toolbox="Toolbox", addons=("Instructions",))], None, great).seconds
    loud = g.one_generator(D, [S(toolbox="Toolbox")], None, great).seconds
    assert quiet > loud and quiet == pytest.approx(20 / 1.5 + 70 / (1 + 0.08 * 0.9), abs=0.01)
    # the event toolboxes and med-kits have the values of their twins (wiki "Toolboxes", "Med-Kits")
    assert D.toolboxes["Festive Toolbox"] == {**D.toolboxes["Commodious Toolbox"], "name": "Festive Toolbox"}
    assert D.medkits["Anniversary Med-Kit"]["bonus"] == D.medkits["First Aid Kit"]["bonus"] == 0.40
    kit = g.item_addon_names(D, "Ranger Med-Kit")
    assert len(kit) == 13 and {"Abdominal Dressing", "Butterfly Tape", "Medical Scissors", "Self Adherent Wrap",
                               "Bandages", "Styptic Agent"} <= set(kit)
    assert len(g.item_addon_names(D, "Toolbox")) == 11 and g.item_addon_names(D, "") == []
    # 1.54: every item with its add-ons – those without a speed of their own are offered and change nothing
    assert g.item_kind(D, "Flashlight") == "flashlight" and len(g.item_addon_names(D, "Flashlight")) == 13
    assert [len(g.item_addon_names(D, n)) for n in ("Skeleton Key", "Cryptic Map", "Vigo's Fog Vial")] == [5, 5, 5]
    assert {"Flashlight", "Skeleton Key", "Cryptic Map", "Vigo's Fog Vial", "Toolbox", "Ranger Med-Kit",
            "Banquet Toolbox"} <= set(g.item_names(D)) and len(g.item_names(D)) == len(set(g.item_names(D)))
    wrapped = S(medkit="First Aid Kit", addons=("Bandages", "Medical Scissors", "Abdominal Dressing"))
    assert g.item_addons(D, wrapped) == [D.item_addons["Medical Scissors"]]         # Bandages takes a place
    assert g.plain_addons(D, "First Aid Kit", wrapped.addons) == ["Bandages"]
    assert g.plain_addons(D, "Flashlight", ("Battery", "Socket Swivels")) == ["Battery"]


def test_a_row_is_left_out_when_the_item_in_hand_cannot_do_it():
    """1.54 (review): healing oneself needs the med-kit, sabotage the toolbox or Saboteur – with another item in
    hand the row is not shown; with empty hands it stays (the item it needs is assumed)."""
    def rows(area, s):
        return [ln.row for ln in g.area_lines(D, area, [s])]
    assert "heal_self" in rows("heal", S()) and "heal_self" in rows("heal", S(medkit="First Aid Kit"))
    assert "heal_self" not in rows("heal", S(toolbox="Toolbox")) and "heal_self" not in rows("heal",
                                                                                           S(item="Flashlight"))
    assert rows("heal", S(toolbox="Toolbox")) == ["heal_other", "heal_dying", "recover"]
    assert "sabotage" in rows("hook", S()) and "sabotage" in rows("hook", S(toolbox="Toolbox"))
    assert rows("hook", S(medkit="First Aid Kit")) == ["unhook"] and rows("hook", S(item="Skeleton Key")) == ["unhook"]
    assert rows("hook", S(("Saboteur",), medkit="First Aid Kit")) == ["unhook", "sabotage"]
    two = g.area_lines(D, "heal", [S(toolbox="Toolbox"), S()])
    assert [(ln.subject, ln.row) for ln in two if ln.row == "heal_self"] == [(1, "heal_self")]


def test_mangled_from_a_perk_and_an_add_on_counts_the_same_in_either_order():
    """1.54 (review): the effect is there once; the add-on's is never lowered by diminishing returns – whichever
    of the two the build names first."""
    nurse = K(("Coulrophobia", "Sloppy Butcher"), name="The Nurse", addons=("Fragile Wheeze",))
    ln = line("heal", "heal_other", [S()], nurse)
    assert ln.mult == pytest.approx(0.7 * 0.8)
    assert [(p.source, p.exempt, p.beaten) for p in ln.parts] == [
        ("Coulrophobia", False, ""), ("Fragile Wheeze", True, ""), ("Sloppy Butcher", False, "Fragile Wheeze")]
    perk_only = line("heal", "heal_other", [S()], K(("Coulrophobia", "Sloppy Butcher")))
    assert perk_only.mult == pytest.approx(0.7 * (1 - 0.2 * 0.5))                  # a perk's is ranked


def test_weeping_wounds_slows_repairing_too():
    """1.54 (review; wiki: "Reduces their Action speeds for Healing and Repairing by 16 %"): it was in the
    healing area only."""
    s = S()
    assert g.speed(D, s, [s], K(("Scourge Hook: Weeping Wounds",)), Sc()) == pytest.approx(0.84)
    assert g.speed(D, s, [s], K(("Scourge Hook: Weeping Wounds",), {"Scourge Hook: Weeping Wounds": 0}),
                   Sc()) == pytest.approx(1.0)
    assert line("heal", "heal_other", [s], K(("Scourge Hook: Weeping Wounds",))).mult == pytest.approx(0.84)
    assert "Scourge Hook: Weeping Wounds" in g.perk_names(D, "K", "repair")


def test_the_add_on_lists_of_the_data_file_fit_the_calculator():
    with open(g.FILE, encoding="utf-8") as fh:
        raw = json.load(fh)
    tags = {t for a in raw["areas"] for r in a.get("rows", ()) for t in r["tags"]}
    names = [e["name"] for e in raw["killer_addons"]]
    assert len(names) == len(set(names)) and not set(names) & set(D.perks)
    for e in raw["killer_addons"]:
        assert e["killer"] in D.killers and e["effects"], e["name"]
        for f in e["effects"]:
            assert set(f["tags"]) <= tags and f["to"] in ("self", "enemy") and abs(f["value"]) <= 0.6, e["name"]
            assert f.get("when", "") in set(app_calc.WHEN) | {""}, e["name"]
    for e in raw["item_addons"]:
        assert e["item"] in ("toolbox", "medkit"), e["name"]
        assert sum(k in e for k in ("repair", "charges", "part", "no_checks", "sabotage", "heal")) == 1, e["name"]
    assert all({"name", "bonus", "charges", "sabotage"} <= set(t) for t in raw["toolboxes"])
    # the full lists: 20 add-ons for each Killer, every one with an effect is in its Killer's or item's list
    assert set(raw["killer_addon_lists"]) == set(D.killers)
    assert all(len(v) == len(set(v)) == 20 for v in raw["killer_addon_lists"].values())
    assert all(e["name"] in raw["killer_addon_lists"][e["killer"]] for e in raw["killer_addons"])
    assert all(e["name"] in raw["item_addon_lists"][e["item"]] for e in raw["item_addons"])
    every = [n for v in raw["killer_addon_lists"].values() for n in v] + \
        [n for v in raw["item_addon_lists"].values() for n in v]
    assert len(every) == len(set(every)) == 952                 # no name twice: one list never offers another's
    assert not set(D.not_modelled_areas) & (set(D.killer_addons) | set(D.item_addons))


def test_the_words_of_a_modifier():
    part = g.Part("x", 0.5, when="trigger", seconds=2)
    assert app_calc.when_text(part) == "nach Auslösung · 2 s lang"
    assert app_calc.when_text(g.Part("x", 0.75, when="tokens", stacks=5)) == "5 Tokens"
    assert app_calc.when_text(g.Part("x", 0.5)) == ""
    assert app_calc.signed_pct(0.5) == "+50 %" and app_calc.signed_pct(-0.115) == "−11.5 %"
    assert app_calc.value_text("time", 10.6667) == "10.67 s" and app_calc.value_text("speed", 4) == "4.00 m/s"
    assert app_calc.value_text("time", None) == "–"
    assert app_calc.delta_text("time", 10.0, 11.2) == "−1.20 s" and app_calc.delta_text("speed", 4.2, 4.0) == \
        "+0.20 m/s"
    assert app_calc.delta_text("time", 10.0, 10.001) == "=" and app_calc.delta_text("time", None, 1) == "–"


def test_perk_pictures_are_found_by_the_perks_name_or_the_packs_file_name(tmp_path):
    own, user = tmp_path / "own", tmp_path / "data" / perkicons.USER_FOLDER
    (user / "Perks" / "DLC").mkdir(parents=True)
    own.mkdir()
    (user / "Botany Knowledge.png").write_bytes(b"x")
    (user / "Perks" / "DLC" / "iconPerks_boonCircleOfHealing.PNG").write_bytes(b"x")
    (user / "Perks" / "iconPerks_noOneEscapesDeath.webp").write_bytes(b"x")       # the pack leaves "Hex" out
    (user / "iconPerks_dejaVu.png").write_bytes(b"x")
    (user / "cullTheWeak.png").write_bytes(b"x")
    (user / "notes.txt").write_bytes(b"x")
    (user / "Lithe.png").write_bytes(b"x" * (perkicons.MAX_BYTES + 1))             # no icon is that large
    (own / "Botany Knowledge.png").write_bytes(b"x")               # the user's picture of a perk comes first
    index = perkicons.Index([str(user), str(own)])
    assert index.any()
    assert index.find("Botany Knowledge").endswith("Botany Knowledge.png")
    assert index.find("Boon: Circle of Healing").endswith("iconPerks_boonCircleOfHealing.PNG")
    assert index.find("Hex: No One Escapes Death").endswith("iconPerks_noOneEscapesDeath.webp")
    assert index.find("Déjà Vu").endswith("iconPerks_dejaVu.png")
    assert index.find("Dying Light / Cull the Weak").endswith("cullTheWeak.png")
    assert index.find("Lithe") is None and index.find("notes") is None and index.find("Sprint Burst") is None
    assert os.path.dirname(index.find("Botany Knowledge")) == str(user)
    assert perkicons.key("iconPerks_We'reGonnaLiveForever") == perkicons.key("We're Gonna Live Forever")
    assert perkicons.key("T_UI_iconsPerks_Rampage") == perkicons.key("IconsPerks_Rampage") == "rampage"
    # the beginning goes only with its underscore: "IconAddon_scraps" must not lose the s of its name
    assert perkicons.key("IconAddon_scraps") == "scraps" and perkicons.key("IconItems_toolbox") == "toolbox"
    assert perkicons.key("Iconoclast") == "iconoclast"
    assert perkicons.key("Jump Rope (Dream Demon)") == "jumpropedreamdemon"
    assert perkicons.candidates("Jump Rope (Dream Demon)")[:2] == ["jumpropedreamdemon", "jumprope"]
    # 1.54: a perk and an add-on of one name never take each other's picture; a plainly named file serves both
    twins = tmp_path / "twins"
    twins.mkdir()
    for name in ("iconPerks_twin.png", "IconAddon_twin.png", "IconItems_lamp.png", "Plain Name.png"):
        (twins / name).write_bytes(b"x")
    both = perkicons.Index([str(twins)])
    assert both.find("Twin", "perks").endswith("iconPerks_twin.png")
    assert both.find("Twin", "addon").endswith("IconAddon_twin.png") and both.find("Twin", "items") is None
    assert both.find("Lamp", "items").endswith("IconItems_lamp.png") and both.find("Lamp", "perks") is None
    assert both.find("Lamp").endswith("IconItems_lamp.png")                       # any kind when none is asked
    assert both.finder("addon")("Plain Name").endswith("Plain Name.png") and both.find("Plain Name", "perks")
    assert [perkicons.kind_of(n) for n in ("T_UI_iconsPerks_x", "IconAddon_x", "iconItems_x", "Prove Thyself")] == \
        ["perks", "addon", "items", ""]
    # the user's own picture comes first, however it is named (the program's own folder is the second one)
    mine, shipped = tmp_path / "mine", tmp_path / "shipped"
    mine.mkdir()
    shipped.mkdir()
    (mine / "Twin.png").write_bytes(b"x")
    (shipped / "iconPerks_twin.png").write_bytes(b"x")
    (shipped / "iconPerks_other.png").write_bytes(b"x")
    order = perkicons.Index([str(mine), str(shipped)])
    assert order.find("Twin", "perks").endswith(os.path.join("mine", "Twin.png"))
    assert order.find("Other", "perks").endswith("iconPerks_other.png")
    empty = perkicons.Index([str(tmp_path / "nothing")])
    assert not empty.any() and empty.find("Botany Knowledge") is None
    assert perkicons.folders("D") == [os.path.join("D", perkicons.USER_FOLDER),
                                      os.path.join(perkicons.HERE, perkicons.FOLDER)]


# what the wiki has no picture for that can be told apart by its name (1.54) – these entries stand without one
NO_PICTURE = {("addon", "Anti-Exhaustion Syringe"), ("addon", "Misty Day, Remains of Judgement"),
              ("addon", "Mysterious Elixir"), ("addon", "Spattered Handkerchief"),
              ("addon", "Vorpal Sword")}    # 1.57: the two maps came with the loadout reader; 1.57.18: the
                                                # three Banquet items too


def test_every_perk_of_the_calculator_has_its_picture_in_the_program():
    """Saru: "Wiki ist in Ordnung" – the pictures come with the program (64 px PNG from the Dead by Daylight Wiki,
    THIRD_PARTY.md): one for every perk of perkdata.json and (1.53/1.54, "ja") for every item and every add-on,
    each of its own kind – but for the ten the wiki has none for; nothing else in the folder, each a small
    picture."""
    from PIL import Image
    folder = os.path.join(perkicons.HERE, perkicons.FOLDER)
    index = perkicons.Index([folder])
    want = [(n, "perks") for n in set(D.survivor) | set(D.killer) | set(D.perks)] + \
        [(n, "items") for n in g.item_names(D)] + \
        [(n, "addon") for v in list(D.killer_addon_lists.values()) + list(D.item_addon_lists.values()) for n in v]
    assert len(want) == len(set(want)) == 1106        # 1.56.5: + Hex: Huntress Lullaby
    assert {(kind, n) for n, kind in want if index.find(n, kind) is None} == NO_PICTURE
    for n, kind in want:                                      # a picture is of the kind asked for
        path = index.find(n, kind)
        assert path is None or perkicons.kind_of(os.path.basename(path)) == kind, n
    used = {index.find(part, kind) for n, kind in want for part in n.split(" / ")} - {None}
    from fogscout import loadouts                             # 1.57: and every survivor perk / item / add-on
    used = {os.path.basename(p) for p in used} | {f for kind in loadouts.load_names().values() for f in kind}
    files = sorted(os.listdir(folder))                        # … (the reader's own names file)
    assert sorted(used) == files and len(files) > 1000
    for name in files:
        path = os.path.join(folder, name)
        assert name.endswith(".png") and os.path.getsize(path) < 16 * 1024, name
        with Image.open(path) as im:
            assert im.size == (64, 64) and im.format == "PNG", name
    with open(os.path.join(os.path.dirname(perkicons.HERE), "THIRD_PARTY.md"), encoding="utf-8") as fh:
        assert "fogscout/perkicons" in fh.read()


def test_a_perk_picture_is_drawn_on_a_dark_tile_and_a_broken_file_gives_none(tmp_path):
    """The game's icons are white on nothing: the choice shows them on a dark tile (visible in the light theme);
    a file that is no picture leaves the entry without one instead of failing."""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from fogscout import qt_app, qt_pages
    qt_app.application()
    good = os.path.join(perkicons.HERE, perkicons.FOLDER, "IconPerks_proveThyself.png")
    icon = qt_pages._file_icon(good)
    assert not icon.isNull() and qt_pages._file_icon(good) is icon               # made once
    image = icon.pixmap(64, 64).toImage()
    corner, edge = image.pixelColor(0, 0), image.pixelColor(32, 1)
    assert corner.alpha() == 0 and edge.alpha() == 255 and edge.lightness() < 80   # rounded, dark
    bad = tmp_path / "x.png"
    bad.write_bytes(b"not a picture")
    assert qt_pages._file_icon(str(bad)).isNull()


@pytest.fixture
def app_root(tmp_path):
    """The whole program offscreen (like tests/test_gencalc.py)."""
    if sys.platform == "win32":
        pytest.skip("Linux: the Windows job tests the native parts; the app would touch the system there")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("maps", "models", "maps.json"):
        os.symlink(os.path.join(root, name), tmp_path / name)
    (tmp_path / "sim").mkdir()
    return tmp_path


def shown(app, w) -> bool:
    from fogscout import app_qt
    return app_qt.ui_shown(w)


def test_the_page_shows_one_area_and_only_the_builds_of_the_team(app_root):
    """One Survivor chosen → one build; the choices list the perks of the area; the result, the breakdown and
    the best next perk follow; Build A stands beside what is chosen later."""
    from fogscout.app import App
    from fogscout import app_qt
    (app_root / perkicons.USER_FOLDER).mkdir()
    (app_root / perkicons.USER_FOLDER / "Botany Knowledge.png").write_bytes(b"\x89PNG")
    calc = {"area": "heal", "n": 1, "survivors": [[["Botany Knowledge", "Prove Thyself"], "Ranger Med-Kit"],
                                                  [["Leader"], ""], [[], ""], [[], ""]],
            "killer": ["Coulrophobia"], "counts": {}}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        assert app.calc_area_var.get() == "Heilen und Erholen" and app.calc_n_var.get() == "1"
        assert [bool(b.winfo_manager()) for b in app.calc_surv_rows] == [True, False, False, False]
        box, var, side = app.calc_perk_boxes[0]
        values = list(box.cget("values"))
        assert "Botany Knowledge" in values and "Déjà Vu" not in values and side == "S"
        box2, var2, _side = app.calc_perk_boxes[1]
        assert var2.get() == "Prove Thyself" and "Prove Thyself" in box2.cget("values")   # chosen before: stays
        # 1.54.1: the box is narrower than many names – hovering shows the whole name, an empty place nothing
        assert app_qt.ui_state(box)["tip"] == "Botany Knowledge"
        assert app_qt.ui_state(app.calc_perk_boxes[2][0])["tip"] == ""
        assert "Prove Thyself" not in values
        kbox = app.calc_perk_boxes[16][0]
        assert "Coulrophobia" in kbox.cget("values") and "Pop Goes the Weasel" not in kbox.cget("values")
        # the assumptions of the Generators are away; 1.55: the Tokens are asked per build, and only for a build
        # with a perk that counts some
        assert not shown(app, app.calc_opt_rows["kicks"]) and "stacks" not in app.calc_opt_rows
        assert not shown(app, app.calc_tokens[0][0])
        assert not shown(app, app.calc_effects_frame)
        t = app.calc_tree
        assert list(t.cget("columns")) == ["base", "now", "speed"]
        assert list(t.get_children()) == ["0:heal_other", "0:heal_dying", "0:heal_self", "0:recover"]
        want = 16 / ((1 + 0.5 + 0.25) * 0.7)                      # Botany, the kit at half, Coulrophobia
        assert t.item("0:heal_other", "values") == ("16.00 s", f"{want:.2f} s", "122.5 %")
        assert t.item("0:heal_other", "text") == "Andere heilen"                  # one Survivor: no name before
        b = app.calc_parts_tree
        top = b.get_children()[0]
        assert b.item(top, "text") == "Andere heilen, Sterbende aufheben"
        rows = [(b.item(i, "text"),) + tuple(b.item(i, "values")) for i in b.get_children(top)]
        assert rows == [("Botany Knowledge", "+50 %", "100 %", "+50 %", ""),
                        ("Ranger Med-Kit", "+50 %", "50 %", "+25 %", ""),
                        ("Coulrophobia", "−30 %", "100 %", "−30 %", "im Terrorradius")]
        tips = "\n".join(app.calc_tip_lines())                 # 1.57.95: a row with "Einsetzen" per proposal
        assert tips.startswith("Survivor: ") and "Killer: " in tips and "→" in tips
        assert "Self-Care" in app.calc_source_var.get()
        # the picture of a perk goes to the page with the choice's state
        st = app_qt.ui_state(box)
        assert st["icons"][st["values"].index("Botany Knowledge")].endswith("Botany Knowledge.png")   # the user's own
        assert st["icons"][0] is None and all(st["icons"][1:])                    # every perk has its picture
        assert os.path.dirname(st["icons"][st["values"].index("Leader")]) == \
            os.path.join(perkicons.HERE, perkicons.FOLDER)
        # Build A, then a change: both stand in the table
        assert app.calc_drop_btn.instate(["disabled"])
        app._calc_keep()
        assert not app.calc_drop_btn.instate(["disabled"]) and "area" not in app.settings.get("calc")["compare"]
        var2.set("Empathic Connection")
        app._calc_changed()
        assert list(t.cget("columns")) == ["base", "now", "speed", "a", "delta"]
        now = 16 / ((1 + 0.5 + 0.25 + 0.4 * 0.25) * 0.7)
        cells = t.item("0:heal_other", "values")
        assert cells[1] == f"{now:.2f} s" and cells[3] == f"{want:.2f} s" and cells[4] == f"−{want - now:.2f} s"
        assert t.item("0:recover", "values")[4] == "="
        # a second Survivor: the second build appears and counts (Leader helps the first)
        app.calc_n_var.set("2")
        app._calc_changed()
        assert [bool(b.winfo_manager()) for b in app.calc_surv_rows] == [True, True, False, False]
        assert shown(app, app.calc_surv_rows[1]) and not shown(app, app.calc_surv_rows[2])
        assert t.item("0:heal_other", "text") == "Survivor 1 · Andere heilen" and "1:heal_other" in t.get_children()
        assert t.item("1:heal_other", "values")[3] == "–"                         # Build A had one Survivor
        app._calc_drop()
        assert list(t.cget("columns")) == ["base", "now", "speed"] and app.settings.get("calc")["compare"] is None
        # the Killer's own area: one line per action, the Tokens of Fire Up as the count
        app.calc_area_var.set("Killer: Aktionen")
        app.calc_kill[1][0].set("Fire Up")
        app._calc_killer_picked(1)
        assert app.calc_kill[1][1].get() == "5" and "Tokens des Perks" in app.calc_kill[1][2].get()
        assert t.item(f"{g.KILLER}:break", "values")[:3] == ("2.34 s", f"{2.34 / 1.4:.2f} s", "140 %")
        assert t.item(f"{g.KILLER}:pickup", "values")[:3] == ("–", "–", "140 %")
        assert "Fire Up" in app.calc_perk_boxes[17][0].cget("values")
        assert app.settings.get("calc")["area"] == "k_action"
        # back to the Generators: their assumptions and table are there again
        app.calc_area_var.set("Reparieren (Generatoren)")
        app._calc_changed()
        assert shown(app, app.calc_opt_rows["kicks"]) and not shown(app, app.calc_tokens[0][0])
        assert shown(app, app.calc_effects_frame)
        assert list(t.cget("columns")) == ["calm", "killer"] and list(t.get_children()) == ["k1", "k2", "all", "split"]
        assert "Prove Thyself" in app.calc_perk_boxes[0][0].cget("values")
        parts = app.calc_parts_tree
        assert parts.get_children() == ()                          # no perk of the builds acts on a Generator
        app.calc_surv[0][0][2].set("Prove Thyself")
        app._calc_changed()
        assert parts.item(parts.get_children()[0], "text").startswith("Survivor 1 · zu 2. am Generator")
        app._calc_keep()
        app.calc_surv[0][0][3].set("Resilience")
        app._calc_changed()
        assert list(t.cget("columns")) == ["calm", "killer", "a", "delta"]
        assert t.item("k1", "values")[2] != t.item("k1", "values")[1] and t.item("k1", "values")[2] != "–"
        assert t.item("k1", "values")[3].startswith("−")                          # Resilience: faster than Build A
        app._calc_reset()
        assert app.settings.get("calc")["compare"] is None and app.settings.get("calc")["area"] == "repair"
    finally:
        app.quit()


def test_tokens_count_per_survivor_and_a_timed_speed_says_its_metres():
    """1.55: every Survivor has their own number of Tokens (before: one choice for the whole team) – also where
    the perk acts on somebody else; and a speed modifier that lasts some seconds is worth base speed × its share
    of the factor × seconds in metres."""
    assert line("objects", "bless", [S(("Flow State",), stacks=0.0)]).mult == pytest.approx(1.15)
    assert line("objects", "bless", [S(("Flow State",), stacks=1.0)], scen=Sc(stacks=0.0)).mult == pytest.approx(1.75)
    assert line("objects", "bless", [S(("Flow State",))], scen=Sc(stacks=0.0)).mult == pytest.approx(1.15)   # as before
    team = [S(("Flow State",), stacks=1.0), S(("Flow State",), stacks=0.5)]
    assert [line("objects", "bless", team, subject=i).mult for i in (0, 1)] == [pytest.approx(1.75), pytest.approx(1.3)]
    for share, want in ((0.0, 1.1), (1.0, 1.6)):                      # the owner's Tokens, whoever opens the gate
        team = [S(("Down to the Last",), stacks=share), S(stacks=1.0 - share)]
        assert line("objects", "gate", team, subject=1).mult == pytest.approx(want)
    run = line("move", "run", [S(("Sprint Burst", "Hope"))])
    burst, hope = run.parts
    assert g.metres(run, burst) == pytest.approx(4.0 * 0.5 * 2) and g.metres(run, hope) is None    # 4 m in 2 s
    crawl = line("move", "crawl", [S(("Hope",))])
    assert all(g.metres(crawl, p) is None for p in crawl.parts)
    slowed = line("move", "run", [S(("Sprint Burst",))], K(("Forced Hesitation",)))
    burst, slow = slowed.parts
    assert g.metres(slowed, burst) == pytest.approx(4.0 * 0.5 * 0.8 * 2)                # with the Killer's −20 %
    assert g.metres(slowed, slow) == pytest.approx(-4.0 * 1.5 * 0.2 * slow.seconds)
    both = line("move", "run", [S(("Lithe", "Sprint Burst"))])
    assert [g.metres(both, p) for p in both.parts] == [pytest.approx(6.0), None]        # the one that counts
    assert g.metres(line("heal", "heal_other", [S(("Botany Knowledge",))]),
                    line("heal", "heal_other", [S(("Botany Knowledge",))]).parts[0]) is None    # a time, no speed


def test_the_page_asks_tokens_per_build_and_counts_only_where_a_perk_has_them(app_root):
    """1.55: the Token line of a build is there only while one of its perks counts Tokens (and says which); a
    Killer perk without a count has no "Anzahl" beside it; the breakdown gives a timed Haste in metres; an entry
    saved before 1.55 takes the one choice all Survivors shared."""
    from fogscout.app import App
    calc = {"area": "objects", "n": 2, "stacks": 50, "killer": ["Fire Up", "Brutal Strength"], "counts": {},
            "survivors": [[["Flow State", "Counterforce"], "", []], [["Resilience"], "", [], 0]]}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        (row0, var0, names0), (row1, var1, _n1) = app.calc_tokens[:2]
        assert shown(app, row0) and names0.get() == "Flow State, Counterforce" and not shown(app, row1)
        assert var0.get() == "die Hälfte" and var1.get() == "eine"            # the old shared choice / its own
        t = app.calc_tree
        assert t.item("0:bless", "values")[2] == "130 %"                       # 2 of 5 Tokens
        var0.set("alle")
        app._calc_changed()
        assert t.item("0:bless", "values")[2] == "175 %"
        assert app.settings.get("calc")["survivors"][0][3] == 100 and app.settings.get("calc")["survivors"][1][3] == 0
        assert "stacks" not in app.calc_opt_rows
        app.calc_n_var.set("1")
        app.calc_surv[0][0][0].set(app_calc.NONE)
        app.calc_surv[0][0][1].set(app_calc.NONE)
        app._calc_changed()
        assert not shown(app, row0)                                            # no perk with Tokens left
        # the Killer's counts: Fire Up has Tokens, Brutal Strength counts nothing, an empty place neither
        assert [shown(app, b) for b in app.calc_count_boxes] == [True, False, False, False]
        app.calc_area_var.set("Bewegung (Haste, Hindered)")
        app.calc_surv[0][0][0].set("Sprint Burst")
        app._calc_changed()
        b = app.calc_parts_tree
        top = next(i for i in b.get_children() if "Rennen" in b.item(i, "text"))
        assert [(b.item(i, "text"), b.item(i, "values")[3]) for i in b.get_children(top)] == [
            ("Sprint Burst", "nach Auslösung · 2 s lang · +4 m")]
        app._calc_reset()
        assert var0.get() == "alle" and var1.get() == "alle"
    finally:
        app.quit()


def test_the_result_stands_beside_the_choices_on_a_wide_page(app_root):
    """1.55 (user's yes to "Ergebnis neben die Eingaben" – it began 900 px down the page): two columns from
    BESIDE_FROM px on, what is chosen on the left, what comes of it on the right (at most BESIDE_MAX wide, so
    the rest goes to the choices, which grow up to PERK_MAX); below each other on a narrow page, as before."""
    from PySide6.QtWidgets import QApplication, QComboBox
    from fogscout.app import App
    from fogscout import qt_pages
    calc = {"area": "heal", "n": 2, "survivors": [[["Botany Knowledge"], "Ranger Med-Kit", []], [[], "", []]],
            "killer": [], "counts": {}}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        q = app.qt
        q.resize(2000, 1000)
        q.show()
        q.show_page("calc")
        app._poll()
        app._qt_refresh(force=True)
        for _i in range(6):
            QApplication.processEvents()
        page = q._page("calc")
        sb = page.findChild(qt_pages.SideBySide, "beside")
        left, right = sb.cards
        widget = lambda w: page.controls[str(w)][1]
        assert left.isAncestorOf(widget(app.calc_perk_boxes[0][0])) and left.isAncestorOf(widget(app.calc_dr_box))
        assert right.isAncestorOf(widget(app.calc_tree)) and right.isAncestorOf(widget(app.calc_parts_tree))
        sb.arrange(app_calc.BESIDE_FROM)
        assert sb.beside() and right.maximumWidth() == qt_pages.BESIDE_MAX
        sb.arrange(app_calc.BESIDE_FROM - 1)
        assert not sb.beside() and right.maximumWidth() > 10000                # below each other: the full width
        # the choices: a name's width at least, more where the row has room, never past the limit
        box = widget(app.calc_perk_boxes[0][0])
        assert isinstance(box, QComboBox)
        # 1.57.95 (draft B "Build-Karten"): a perk is a place of the build – a tile, wider where the row has room
        assert isinstance(box, qt_pages.SlotCombo) and box._what == "Perk 1"
        assert box.minimumWidth() == qt_pages.SLOT_W and box.maximumWidth() == qt_pages.SLOT_MAX == box._grow_to
        assert box.height() == qt_pages.SLOT_H
        addon = widget(app.calc_item_addons[0][0][0])                          # an add-on stays a plain choice
        assert not isinstance(addon, qt_pages.SlotCombo)
        assert addon.minimumWidth() == app_calc.PERK_PX and addon.maximumWidth() == app_calc.PERK_MAX == addon._grow_to
        sb.arrange(sb.width())
        for _i in range(6):
            QApplication.processEvents()
        # every card can still be moved within its column: a card per Survivor now, the Killer and the assumptions
        assert [len(c.cards) for c in page.columns] == [1, g.MAX_SURVIVORS, 2, 4]    # area · builds · Killer,
        #                                                                 assumptions · the result
    finally:
        app.quit()


def test_the_breakdown_names_a_chosen_perk_that_does_not_count(app_root):
    """1.54.1 (review): of two Exhaustion perks – or Mangled from a perk and an add-on – only one counts. The
    other was missing from the breakdown, as if the choice had been lost; now its row says beside which it
    does not count, and the result is the same as before."""
    from fogscout.app import App
    calc = {"area": "move", "n": 1, "survivors": [[["Lithe", "Sprint Burst"], "", []]], "killer": [], "counts": {}}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        assert app.calc_tree.item("0:run", "values") == ("4.00 m/s", "6.00 m/s", "150 %")
        b = app.calc_parts_tree
        top = next(i for i in b.get_children() if "Rennen" in b.item(i, "text"))
        rows = [(b.item(i, "text"),) + tuple(b.item(i, "values")) for i in b.get_children(top)]
        # both +50 %: the one named first counts (they never run at once – Exhausted)
        assert rows == [("Lithe", "+50 %", "100 %", "+50 %", "nach Auslösung · 3 s lang · +6 m"),   # 1.55: its metres
                        ("Sprint Burst", "+50 %", "0 %", "—", "nur Lithe zählt")]
    finally:
        app.quit()


def test_the_page_takes_a_killer_its_add_ons_and_the_items_add_ons(app_root):
    """1.53: the Killer is chosen by name (the row shows that Killer's speed), the add-on choices list what fits
    the Killer or the item in hand, an add-on that no longer fits is taken out, and everything is kept."""
    from fogscout.app import App
    calc = {"area": "k_move", "n": 1, "survivors": [[["Botany Knowledge"], "Ranger Med-Kit"]],     # an older entry
            "killer": [], "counts": {}, "killer_name": "The Clown",
            "killer_addons": ["Cheap Gin Bottle", "No Such Add-on"]}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        t = app.calc_tree
        assert app.calc_killer_var.get() == "The Clown"
        (box1, add1), (box2, add2) = app.calc_killer_addons
        assert add1.get() == "Cheap Gin Bottle" and add2.get() == app_calc.NONE
        from fogscout import app_qt
        st = app_qt.ui_state(box1)                                   # the add-ons' pictures go to the page
        named = [p for p in st["icons"][1:] if p]
        assert st["icons"][0] is None and len(named) >= 19 and all("addon_" in os.path.basename(p).lower()
                                                                  for p in named)
        assert list(box1.cget("values")) == [app_calc.NONE] + g.killer_addon_names(D, "The Clown")
        assert list(t.get_children()) == [f"{g.KILLER}:kbase", f"{g.KILLER}:kalt0", f"{g.KILLER}:carry"]
        assert t.item(f"{g.KILLER}:kbase", "text") == "Grundgeschwindigkeit"
        assert t.item(f"{g.KILLER}:kalt0", "text") == "Reloading"
        assert t.item(f"{g.KILLER}:kbase", "values") == ("4.60 m/s", f"{4.6 * 1.17:.2f} m/s", "117 %")
        b = app.calc_parts_tree
        rows = [(b.item(i, "text"),) + tuple(b.item(i, "values")) for i in b.get_children(b.get_children()[0])]
        assert rows == [("The Afterpiece Antidote", "+14 %", "100 %", "+14 %", "nach Auslösung"),
                        ("Cheap Gin Bottle", "+3 %", "Add-on: 100 %", "+3 %", "nach Auslösung")]
        # the same add-on twice is not possible; another Killer: the add-ons go, the lists follow
        add2.set("Cheap Gin Bottle")
        app._calc_changed()
        assert add2.get() == app_calc.NONE
        app.calc_killer_var.set("The Shape")
        app._calc_changed()
        assert add1.get() == app_calc.NONE and "Hair Brush" in box1.cget("values")
        assert t.item(f"{g.KILLER}:kbase", "text") == "Grundgeschwindigkeit (Stalker Mode)"
        assert t.item(f"{g.KILLER}:kbase", "values")[0] == "4.20 m/s"
        saved = app.settings.get("calc")
        assert saved["killer_name"] == "The Shape" and saved["killer_addons"] == []
        app.calc_killer_var.set("The Trapper")
        app._calc_changed()
        assert not box1.instate(["disabled"])
        app.calc_killer_var.set("The Cenobite")                         # 1.54: every Killer has all 20 add-ons
        app._calc_changed()
        assert not box1.instate(["disabled"]) and len(box1.cget("values")) == 21
        assert "Ohne berechenbare Wirkung" not in app.calc_killer_hint.get()
        add1.set(g.killer_addon_names(D, "The Cenobite")[0])           # none of them changes a speed
        app._calc_changed()
        assert add1.get() != app_calc.NONE and app.settings.get("calc")["killer_addons"] == [add1.get()]
        assert f"Ohne berechenbare Wirkung: {add1.get()}." in app.calc_killer_hint.get()
        app.calc_killer_var.set(app_calc.NONE)
        app._calc_changed()
        assert list(t.get_children())[0] == f"{g.KILLER}:k460" and app.settings.get("calc")["killer_name"] == ""
        # the item's add-ons: a med-kit's for the med-kit, gone with the item
        (ibox, iadd), (_ibox2, iadd2) = app.calc_item_addons[0]
        assert list(ibox.cget("values")) == [app_calc.NONE] + g.item_addon_names(D, "Ranger Med-Kit")
        app.calc_area_var.set("Heilen und Erholen")
        iadd.set("Abdominal Dressing")
        iadd2.set("Medical Scissors")
        app._calc_changed()
        want = 16 / (1 + 0.5 + 0.25 + 0.15 + 0.10)
        assert t.item("0:heal_other", "values")[1] == f"{want:.2f} s"
        assert app.settings.get("calc")["survivors"][0] == [["Botany Knowledge"], "Ranger Med-Kit",
                                                             ["Abdominal Dressing", "Medical Scissors"], 100]
        app.calc_surv[0][1].set("Toolbox")
        app._calc_changed()
        assert iadd.get() == app_calc.NONE and "Socket Swivels" in ibox.cget("values")
        assert app.settings.get("calc")["survivors"][0][2] == []
        # Generators: the add-ons are explained with the toolbox
        app.calc_area_var.set("Reparieren (Generatoren)")
        iadd.set("Socket Swivels")
        iadd2.set("Wire Spool")
        app._calc_changed()
        text = app.calc_effects_var.get()
        assert "Toolbox – +50 % Tempo, bis 32 Ladungen übertragen sind" in text
        assert "Socket Swivels – +30 % Tempo mit dem Werkzeugkasten" in text and "Wire Spool – +12 Ladungen" in text
        calm = g.one_generator(D, [S(("Botany Knowledge",), "Toolbox", addons=("Socket Swivels", "Wire Spool"))],
                               None, Sc(kicks=0)).seconds
        assert t.item("k1", "values")[0] == g.fmt(calm)
        app.calc_surv[0][1].set(app_calc.NONE)
        app._calc_changed()
        assert ibox.instate(["disabled"]) and iadd.get() == app_calc.NONE
        # 1.54: a flashlight and its add-ons can be chosen; the page says that they change nothing it works out
        app.calc_surv[0][1].set("Flashlight")
        app._calc_changed()
        assert not ibox.instate(["disabled"]) and list(ibox.cget("values"))[1:] == g.item_addon_names(D, "Flashlight")
        iadd.set("Battery")
        app._calc_changed()
        assert app.settings.get("calc")["survivors"][0][1:] == ["Flashlight", ["Battery"], 100]
        assert app.calc_plain_var.get() == "Ohne berechenbare Wirkung: Survivor 1: Flashlight, Battery."
        app.calc_surv[0][1].set("Toolbox")
        app._calc_changed()
        iadd.set("Spring Clamp")
        iadd2.set("Socket Swivels")
        app._calc_changed()
        assert app.calc_plain_var.get() == "Ohne berechenbare Wirkung: Survivor 1: Spring Clamp."
        iadd.set(app_calc.NONE)
        app._calc_changed()
        assert app.calc_plain_var.get() == ""
        app.calc_killer_var.set("The Clown")
        app._calc_reset()
        assert app.calc_killer_var.get() == app_calc.NONE and app.settings.get("calc")["killer_addons"] == []
    finally:
        app.quit()


def test_a_perk_is_in_a_build_only_once(app_root):
    """1.53.1 (Saru: "Beim Calculator kann ein Survivor 2x dasselbe Perk haben. Das macht keinen Sinn"): a perk
    chosen in a build is not offered in its other places, a second one (older settings) is taken out – for the
    Killer's build and the two kinds of Overzealous too; another Survivor may have the same perk."""
    from fogscout.app import App
    calc = {"area": "repair", "n": 2, "survivors": [[["Resilience", "Prove Thyself", "Resilience"], "", []],
                                                    [["Resilience"], "", []]],
            "killer": ["Thanatophobia", "Thanatophobia"], "counts": {"Thanatophobia": 3}}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        none = app_calc.NONE
        first, second = app.calc_surv[0][0], app.calc_surv[1][0]
        assert [v.get() for v in first] == ["Resilience", "Prove Thyself", none, none]      # the second one is out
        assert second[0].get() == "Resilience"                                           # another build: its own
        assert [v.get() for v, _n, _m in app.calc_kill] == ["Thanatophobia", none, none, none]
        boxes = [box for box, _var, _side in app.calc_perk_boxes]
        assert "Resilience" in boxes[0].cget("values") and "Prove Thyself" not in boxes[0].cget("values")
        assert "Resilience" not in boxes[2].cget("values") and "Déjà Vu" in boxes[2].cget("values")
        assert "Resilience" not in boxes[5].cget("values")                                # Survivor 2, second place
        assert "Thanatophobia" not in boxes[17].cget("values") and "Thanatophobia" in boxes[16].cget("values")
        # chosen twice all the same (by hand in the settings, or a list not yet refreshed): taken out, kept once
        first[3].set("Prove Thyself")
        app._calc_changed()
        assert first[3].get() == none and app.settings.get("calc")["survivors"][0][0] == ["Resilience",
                                                                                          "Prove Thyself"]
        # the two kinds of Overzealous are one perk
        first[2].set("Overzealous (Dull Totem)")
        app._calc_changed()
        assert "Overzealous (Hex Totem)" not in boxes[3].cget("values")
        assert {"Overzealous (Dull Totem)", "Overzealous (Hex Totem)"} <= set(boxes[2].cget("values"))
        first[3].set("Overzealous (Hex Totem)")
        app._calc_changed()
        assert first[3].get() == none
        # a place given up offers the perk again; in another area the rule is the same
        first[0].set(none)
        app._calc_changed()
        assert "Resilience" in boxes[1].cget("values") and "Resilience" in boxes[3].cget("values")
        app.calc_area_var.set("Heilen und Erholen")
        first[0].set("Botany Knowledge")
        app._calc_changed()
        assert "Botany Knowledge" not in boxes[3].cget("values") and "Botany Knowledge" in boxes[4].cget("values")
        # the add-on chosen in one place is not offered in the other
        app.calc_surv[0][1].set("Toolbox")
        app._calc_changed()
        (abox, avar), (bbox, _bvar) = app.calc_item_addons[0]
        avar.set("Socket Swivels")
        app._calc_changed()
        assert "Socket Swivels" not in bbox.cget("values") and "Socket Swivels" in abox.cget("values")
    finally:
        app.quit()



def test_the_build_cards_an_example_the_same_for_all_and_a_proposal_put_in(app_root):
    """1.57.95 (user picked draft B "Build-Karten"): a card per Survivor with five places, the answer as tiles,
    "Beispiel laden", "Für alle übernehmen" and "Einsetzen" beside each proposal of "Bester nächster Perk"."""
    from fogscout import app_qt
    from fogscout.app import App
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        assert [b.cget("text") for b in app.calc_surv_rows] == [f"Survivor {i}" for i in range(1, 5)]   # a card each
        first = app.calc_perk_boxes[0][0]
        node = app_qt.ui_layout(first, {})
        assert first._dbdms_slot == "Perk 1" and node["kind"] == "combo" and node["slot"] == "Perk 1"
        assert [t.title for t in app.calc_tiles.data][:2] == ["Ein Generator, alle 4", "Fünf Generatoren"]
        before = app.calc_tiles.data[0].value
        app._calc_example()
        perks, tool = app.calc_surv[0]
        assert perks[0].get() == "Prove Thyself" and tool.get() != app_calc.NONE
        assert app.calc_kill[0][0].get() == "Corrupt Intervention"
        assert app.calc_tiles.data[0].value != before                      # the Killer's perk costs time
        assert [t.title for t in app.calc_tiles.data] == ["Ein Generator, alle 4", "Fünf Generatoren",
                                                          "Der Killer kostet", "Tempo Survivor 1"]
        assert app.calc_tiles.data[2].value.startswith("+")
        # "Für alle übernehmen": the build of Survivor 1 for the team
        assert app.calc_surv[1][0][0].get() == app_calc.NONE
        app._calc_same_for_all()
        assert all(p[0].get() == "Prove Thyself" and t.get() == tool.get() for p, t in app.calc_surv)
        # "Einsetzen": the first proposal into the first free place of its build
        rows = [r for r, _tv in app.calc_tip_rows if r.winfo_manager()]
        assert rows and len(app._calc_tips_now) == len(rows) and len(app.calc_tip_lines()) >= len(rows)
        side, tip = app._calc_tips_now[0]
        places = app.calc_surv[tip.who][0] if side == "S" else [v for v, _n, _m in app.calc_kill]
        assert tip.name not in [v.get() for v in places]
        app._calc_tip_use(0)
        assert tip.name in [v.get() for v in places]
        app._calc_tip_use(99)                                              # no such row: nothing happens
        # another area: no tiles (they are about Generators)
        app.calc_area_var.set(app_calc._(app_calc.AREAS["move"]))
        app._calc_changed()
        assert app.calc_tiles.data == []
    finally:
        app.quit()
