"""1.51 (Saru: "Rechner … Perks kombinieren … wie schnell ich einen Generator habe … Diminishing returns"): the
generator calculator (fogscout/gencalc.py) against the wiki's own reference numbers."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fogscout import gencalc as g  # noqa: E402

D = g.load()
S, K, Sc = g.Survivor, g.Killer, g.Scenario
CALM = Sc(great=0, miss=0, kicks=0)


def test_the_co_op_penalty_gives_the_wikis_times():
    """Wiki "Generators", Efficiency Penalty: 90 / ~52.94 / ~42.86 / ~40.91 s for 1–4 Survivors."""
    want = [90.0, 90 / 1.7, 90 / 2.1, 90 / 2.2]
    for k, w in enumerate(want, 1):
        assert g.one_generator(D, [S()] * k, None, CALM).seconds == pytest.approx(w, abs=0.06)


def test_diminishing_returns_weigh_the_largest_fully_and_the_rest_less():
    """Wiki "Dead by Daylight Maths" (patch 9.6.0): 100 / 50 / 25 / 12.5 / 5 % from the largest down."""
    assert g.ranked([0.1, 0.5, 0.2, 0.3, 0.4, 0.6]) == pytest.approx([0.6, 0.25, 0.1, 0.0375, 0.01, 0.005])
    assert g.ranked([0.1, 0.5], diminishing=False) == [0.5, 0.1]
    # Commodious (+50 %) + Resilience (+9 %) + Déjà Vu (+6 %): 1 + 0.5 + 0.045 + 0.015 instead of 1.65
    s = S(("Resilience", "Déjà Vu"), "Commodious Toolbox")
    assert g.speed(D, s, [s], K(), CALM) == pytest.approx(1.56)
    assert g.speed(D, s, [s], K(), Sc(kicks=0, diminishing=False)) == pytest.approx(1.65)


def test_slowdowns_multiply_and_prove_thyself_counts_once_for_everyone():
    k = K(("Thanatophobia", "Distressing"), {"Thanatophobia": 4})
    s = S()
    # 20 % (four injured) and 8 % · ½ → 0.8 · 0.96
    assert g.speed(D, s, [s], k, CALM) == pytest.approx(0.8 * 0.96)
    pt = S(("Prove Thyself",))
    team = [pt, pt, S()]                                   # two copies: one instance, +20 % for all three
    assert g.speed(D, team[2], team, K(), CALM) == pytest.approx(1.2 * 0.7)
    both = S(("Overzealous (Dull Totem)", "Overzealous (Hex Totem)"))
    assert g.speed(D, both, [both], K(), CALM) == pytest.approx(1.2)      # the same perk twice: the better only


def test_a_toolbox_gives_its_charges_and_then_stops():
    """Wiki "Toolboxes": a Toolbox (20 Charges, +50 %) adds exactly its Charges at 1.5 c/s, then the base rate."""
    r = g.one_generator(D, [S(toolbox="Toolbox")], None, CALM)
    assert r.seconds == pytest.approx(20 / 1.5 + 70 / 1.0, abs=0.1)


def test_skill_checks_count_as_expected_progress():
    r = g.one_generator(D, [S()], None, Sc(great=1.0, miss=0, kicks=0))
    assert r.seconds == pytest.approx(90 / (1 + 0.08 * 0.9), abs=0.1)
    worse = g.one_generator(D, [S()], None, Sc(great=0, miss=0.5, kicks=0))
    assert worse.seconds > 90


def test_the_generator_jumps_from_event_to_event_and_never_below_zero():
    """1.52: the time runs to the next change (done, kick, toolbox empty, bonus over) instead of in steps – the
    seconds are the formula's, and missed checks with a toolbox (more lost than repaired) leave it at 0, not below."""
    two = [S(toolbox="Toolbox"), S(toolbox="Commodious Toolbox")]
    # 2 · 1.5 · 0.85 until the first box is empty, then 1.5 + 1 until the second, then 2 · 0.85
    t1 = 20 / (1.5 * 0.85)
    t2 = (32 - 20) / (1.5 * 0.85)
    done = (1.5 + 1.5) * 0.85 * t1 + (1.0 + 1.5) * 0.85 * t2
    assert g.one_generator(D, two, None, CALM).seconds == pytest.approx(t1 + t2 + (90 - done) / 1.7, abs=0.01)
    lost = g.one_generator(D, [S(toolbox="Toolbox")], None, Sc(great=0, miss=1.0, kicks=0))
    plain = g.one_generator(D, [S()], None, Sc(great=0, miss=1.0, kicks=0))
    assert lost.seconds is not None and lost.seconds > 20 / 1.5              # nothing gained while the box lasts
    assert plain.seconds == pytest.approx(lost.seconds - 20 / 1.5, abs=0.01)


def test_a_kick_costs_progress_and_the_event_limit_holds():
    calm = g.one_generator(D, [S()], None, CALM).seconds
    kicked = g.one_generator(D, [S()], K(), Sc(great=0, kicks=1, kick_at=0.5, away=20))
    # 5 % of 90 + 20 s at 0.25 c/s are lost, plus 20 s away
    assert kicked.lost == pytest.approx(4.5 + 5.0, abs=0.1) and kicked.events == 1
    assert kicked.seconds == pytest.approx(calm + 20 + kicked.lost, abs=0.2)
    heavy = K(("Scourge Hook: Pain Resonance", "Surge"), {"Scourge Hook: Pain Resonance": 4, "Surge": 8})
    r = g.one_generator(D, [S()], heavy, Sc(great=0, kicks=8, kick_at=0.6, away=10))
    assert r.events == 8 and r.seconds is not None


def test_pop_and_undone_and_blocks():
    pop = g.one_generator(D, [S()], K(("Pop Goes the Weasel",)), Sc(great=0, kicks=1, away=0))
    assert pop.lost == pytest.approx(0.20 * 90, abs=0.1)
    undone = g.one_generator(D, [S()], K(("Undone",)), Sc(great=0, kicks=1, away=0))
    assert undone.lost == pytest.approx((0.05 + 0.30) * 90, abs=0.1) and undone.events == 1
    ci = g.one_generator(D, [S()], K(("Corrupt Intervention",)), Sc(great=0, kicks=0))
    assert ci.seconds == pytest.approx(90 + 120, abs=0.1)


def test_requirement_reductions_and_five_generators():
    need, notes = g.requirement(D, [S(("Invocation: Weaving Spiders", "Specialist"), "Toolbox", part=True)])
    assert need == 90 - 10 - 24 - 10 and len(notes) == 3
    assert g.requirement(D, [S(("Specialist",))], first=False)[0] == 90
    solo = [S()] * 4
    assert g.five_split(D, solo, None, CALM) == pytest.approx(180, abs=0.2)   # 4 at once, then one more
    together = g.five_together(D, solo, None, CALM)
    fc = g.five_together(D, [S(("Friendly Competition",))] * 4, None, CALM)
    assert together == pytest.approx(5 * 90 / 2.2, abs=0.5) and fc < together


def test_the_data_file_is_complete_and_sourced():
    with open(g.FILE, encoding="utf-8") as fh:
        raw = json.load(fh)
    assert raw["retrieved"] and "wiki.gg" in json.dumps(raw["mechanics"]["sources"])
    kinds = {"self", "self_with_others", "team", "team_per_other", "team_timed", "great_scale",
             "requirement_all", "requirement_once",
             "check_chance", "team_check_chance", "check_fail", "others_check_bonus"}          # 1.56: Skill Checks
    assert all(e["kind"] in kinds for e in raw["survivor"])
    for e in raw["killer"]:
        assert e["kind"] in {"slow", "slow_first", "kick_loss", "overcharge", "regress_mult", "ruin",
                             "instant", "undone", "block", "enemy_check_chance"}, e["name"]
    assert g.fmt(83.4) == "1:23" and g.fmt(None) == "–"


@pytest.fixture
def app_root(tmp_path):
    """The whole program offscreen (like tests/test_uimodel.py)."""
    if sys.platform == "win32":
        pytest.skip("Linux: the Windows job tests the native parts; the app would touch the system there")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("maps", "models", "maps.json"):
        os.symlink(os.path.join(root, name), tmp_path / name)
    (tmp_path / "sim").mkdir()
    return tmp_path


def test_the_page_shows_the_times_of_the_builds_and_keeps_them(app_root):
    """The page "Rechner": saved builds come back, a pick recalculates and is saved, the table has the six lines."""
    from fogscout.app import App
    from fogscout import app_calc
    calc = {"n": 2, "survivors": [[["Prove Thyself", "No Such Perk"], "Toolbox"], [[], ""], [[], ""], [[], ""]],
            "killer": ["Pop Goes the Weasel"], "counts": {"Pop Goes the Weasel": 1}, "great": 0, "miss": 0,
            "kicks": 1, "kick_at": 50, "away": 0, "walk": 0, "diminishing": True}
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True, "calc": calc}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        assert "calc" in app._qt_mod.AUTO_PAGES and app.tab_calc is not None
        vars_, tool = app.calc_surv[0]
        assert [v.get() for v in vars_] == ["Prove Thyself", app_calc.NONE, app_calc.NONE, app_calc.NONE]
        assert tool.get() == "Toolbox" and app.calc_kill[0][0].get() == "Pop Goes the Weasel"
        t = app.calc_tree
        assert list(t.get_children()) == ["k1", "k2", "all", "split"]            # two Survivors at the Generator
        solo = g.one_generator(D, [S(("Prove Thyself",), "Toolbox")], None, Sc(great=0, kicks=0)).seconds
        assert t.item("k1", "values")[0] == g.fmt(solo)
        popped = g.one_generator(D, [S(("Prove Thyself",), "Toolbox")], K(("Pop Goes the Weasel",)),
                                 Sc(great=0, kicks=1, away=0)).seconds
        assert t.item("k1", "values")[1] == g.fmt(popped) and popped > solo
        assert "Kicks mit aktivem Perk" in app.calc_kill[0][2].get()
        # a pick: recalculated and kept in the settings; an unknown saved perk is gone
        app.calc_n_var.set("4")
        vars_[1].set("Resilience")
        app._calc_changed()
        assert list(t.get_children()) == ["k1", "k2", "k3", "k4", "all", "split"]
        saved = app.settings.get("calc")
        assert saved["n"] == 4 and saved["survivors"][0] == [["Prove Thyself", "Resilience"], "Toolbox", [], 100]
        assert "0.85" not in app.calc_rates_var.get() and app.calc_rates_var.get()
        # the Killer perk picked sets its usual count
        app.calc_kill[1][0].set("Thanatophobia")
        app._calc_killer_picked(1)
        assert app.calc_kill[1][1].get() == "2" and app.settings.get("calc")["counts"]["Thanatophobia"] == "2"
        app.calc_dr_var.set(False)
        app._calc_changed()
        assert app.settings.get("calc")["diminishing"] is False
        # 1.51.1: what the chosen perks do, each once; reset. 1.55: a perk without a count has no count beside it
        # (the box was greyed before – four of them stood beside empty places)
        text = app.calc_effects_var.get()
        assert "Prove Thyself – +10 % Tempo je weiterem Survivor" in text and text.count("Resilience") == 1
        assert "Pop Goes the Weasel – ein Kick nimmt 20 % statt 5 %" in text and "Toolbox – +50 % Tempo" in text
        from fogscout import app_qt
        assert app_qt.ui_shown(app.calc_count_boxes[0])                       # Pop: kicks with the perk
        app.calc_kill[2][0].set("Call of Brine")
        app._calc_killer_picked(2)
        assert not app_qt.ui_shown(app.calc_count_boxes[2]) and not app_qt.ui_shown(app.calc_count_boxes[3])
        app._calc_reset()
        assert [v.get() for v in vars_] == [app_calc.NONE] * 4 and tool.get() == app_calc.NONE
        assert app.settings.get("calc")["killer"] == [] and app.calc_dr_var.get() is True
        assert app.calc_effects_var.get() == "Noch kein Perk gewählt."
    finally:
        app.quit()


def test_every_perk_of_the_data_file_has_a_line_that_says_what_it_does():
    """1.51.1: the page explains each chosen perk – no entry without a text, no placeholder left open."""
    from fogscout import app_calc
    for e in list(D.survivor.values()) + list(D.killer.values()):
        text = app_calc.effect_text(e, D.mech)
        assert text and "{" not in text, e["name"]
    assert app_calc.effect_text(D.killer["Thanatophobia"], D.mech).endswith("20 % bei 4")
    # 1.56: the Skill Check perks say what the calculation does with them
    assert app_calc.effect_text(D.survivor["Deadline"], D.mech) == (
        "Skill Checks kommen öfter: +10 Prozentpunkte Chance je Sekunde · ein verfehlter Skill Check kostet 50 % "
        "weniger Fortschritt")
    assert "+1.5 % Fortschritt" in app_calc.effect_text(D.survivor["Bardic Inspiration"], D.mech)
    assert "+10 Prozentpunkte" in app_calc.effect_text(D.killer["Unnerving Presence"], D.mech)
    assert set(app_calc.COUNT_MEANS) == {n for n, e in D.killer.items() if e.get("count")}


# 1.56 (audit of the calculator: perks that change Skill Checks were missing). Hand-worked expected values: one
# Survivor without a toolbox gains 1 c/s; a check comes with the chance per second, a Great one adds 1 % of the
# 90 Charges (0.9 c), a missed one takes 10 % (9 c) and 3 s – so the Generator runs at
# (1 + chance · (great · 0.9 + (1 − miss) · extra − miss · loss)) · (1 − chance · miss · 3) c/s.
def test_deadline_unnerving_and_one_two_three_four_add_percentage_points_to_the_chance():
    great = Sc(great=1.0, miss=0, kicks=0)
    # Deadline (tier III, injured): 8 % + 10 points = 18 % → 1 + 0.18 · 0.9 = 1.162 c/s → 77.45 s
    assert g.one_generator(D, [S(("Deadline",))], None, great).seconds == pytest.approx(90 / 1.162, abs=0.01)
    # Unnerving Presence: the same +10 points for the Survivors in the Terror Radius
    assert g.one_generator(D, [S()], K(("Unnerving Presence",)), great).seconds == pytest.approx(90 / 1.162, abs=0.01)
    # both: 28 % → 1 + 0.28 · 0.9 = 1.252 c/s → 71.89 s
    assert g.one_generator(D, [S(("Deadline",))], K(("Unnerving Presence",)), great).seconds == \
        pytest.approx(90 / 1.252, abs=0.01)
    # One-Two-Three-Four!: +20 points for everyone at the Generator, the performer too, one instance:
    # alone 28 % → 71.89 s; two Survivors 2 · 0.85 + 2 · 0.28 · 0.9 = 2.204 c/s → 40.83 s, two copies the same
    assert g.one_generator(D, [S(("One-Two-Three-Four!",))], None, great).seconds == pytest.approx(90 / 1.252, abs=0.01)
    one = g.one_generator(D, [S(("One-Two-Three-Four!",)), S()], None, great).seconds
    assert one == pytest.approx(90 / 2.204, abs=0.01)
    assert g.one_generator(D, [S(("One-Two-Three-Four!",))] * 2, None, great).seconds == one
    # Instructions: no regular check while the toolbox lasts (20 Charges at 1.5 c/s) – a perk's odds do not bring
    # them back; afterwards 18 %: 20 / 1.5 + 70 / 1.162
    quiet = S(toolbox="Toolbox", addons=("Instructions",))
    assert g.one_generator(D, [quiet], K(("Unnerving Presence",)), great).seconds == \
        pytest.approx(20 / 1.5 + 70 / 1.162, abs=0.01)
    assert g.skill_checks(D, [quiet], K(("Unnerving Presence",))) == [(pytest.approx(0.1), 0.1, 0.0)]


def test_deadline_halves_and_technician_raises_what_a_missed_check_costs():
    missing = Sc(great=0, miss=0.5, kicks=0)
    # plain: (1 − 0.08 · 0.5 · 9) · (1 − 0.08 · 0.5 · 3) = 0.64 · 0.88 = 0.5632 c/s → 159.80 s
    assert g.one_generator(D, [S()], None, missing).seconds == pytest.approx(90 / 0.5632, abs=0.02)
    # Technician (tier III): a miss costs 10 % + 2 % = 10.8 c → (1 − 0.08 · 0.5 · 10.8) · 0.88 = 0.49984 → 180.06 s
    assert g.one_generator(D, [S(("Technician",))], None, missing).seconds == pytest.approx(90 / 0.49984, abs=0.02)
    # Deadline: 18 %, a miss costs 5 % = 4.5 c → (1 − 0.18 · 0.5 · 4.5) · (1 − 0.18 · 0.5 · 3) = 0.595 · 0.73
    assert g.one_generator(D, [S(("Deadline",))], None, missing).seconds == \
        pytest.approx(90 / (0.595 * 0.73), abs=0.02)
    # both: (10 % + 2 %) halved = 6 % = 5.4 c → (1 − 0.18 · 0.5 · 5.4) · 0.73 = 0.514 · 0.73 = 0.37522 → 239.86 s
    assert g.one_generator(D, [S(("Deadline", "Technician"))], None, missing).seconds == \
        pytest.approx(90 / 0.37522, abs=0.02)
    assert g.skill_checks(D, [S(("Deadline", "Technician"))]) == [(pytest.approx(0.1), pytest.approx(0.06), 0.0)]


def test_bardic_inspiration_gives_the_others_the_mean_of_the_d20():
    """d20: 1 nothing, 2–10 +1 %, 11–19 +2 %, 20 +3 % → 0.45 · 1 + 0.45 · 2 + 0.05 · 3 = 1.5 % per successful check,
    for the other Survivors only."""
    assert D.survivor["Bardic Inspiration"]["value"] == pytest.approx(0.45 * 0.01 + 0.45 * 0.02 + 0.05 * 0.03)
    good = Sc(great=0, miss=0, kicks=0)
    assert g.one_generator(D, [S(("Bardic Inspiration",))], None, good).seconds == pytest.approx(90)   # not oneself
    # the other gets 0.08 · 1.35 c = 0.108 c/s: 2 · 0.85 + 0.108 = 1.808 c/s → 49.78 s
    team = [S(("Bardic Inspiration",)), S()]
    assert g.one_generator(D, team, None, good).seconds == pytest.approx(90 / 1.808, abs=0.01)
    # all Great: the bard 0.08 · 0.9, the other 0.08 · (0.9 + 1.35) → 1.7 + 0.072 + 0.18 = 1.952 c/s → 46.11 s
    assert g.one_generator(D, team, None, Sc(great=1.0, miss=0, kicks=0)).seconds == pytest.approx(90 / 1.952, abs=0.01)
    assert [b for _c, _f, b in g.skill_checks(D, team)] == [0.0, pytest.approx(0.015)]
    # a missed check gets nothing: half missed, none Great (the co-op penalty is on the repairing, not on the
    # checks) → the bard 0.85 + 0.08 · (−0.5 · 9) = 0.49, the other 0.85 + 0.08 · (0.5 · 1.35 − 0.5 · 9) = 0.544;
    # both pause 0.08 · 0.5 · 3: (0.49 + 0.544) · (1 − 0.24) = 0.78584 c/s → 114.53 s
    assert g.one_generator(D, team, None, Sc(great=0, miss=0.5, kicks=0)).seconds == \
        pytest.approx(90 / 0.78584, abs=0.02)


def test_pop_and_steadfast_take_their_values_from_the_data_file():
    """1.56: 0.15 (Pop Goes the Weasel) and 0.5 (Boon: Steadfast) were typed into the code as well."""
    import copy
    d = copy.deepcopy(D)
    d.killer["Pop Goes the Weasel"]["value"] = 0.25
    pop = g.one_generator(d, [S()], K(("Pop Goes the Weasel",)), Sc(great=0, kicks=1, away=0))
    assert pop.lost == pytest.approx((0.05 + 0.25) * 90, abs=0.1)
    # Steadfast: 4.5 c from the kick, then 20 s at 0.25 c/s · (1 − 0.5) = 2.5 c; with 0.25 in the file 3.75 c
    scen = Sc(great=0, kicks=1, away=20)
    assert g.one_generator(D, [S(("Boon: Steadfast",))], K(), scen).lost == pytest.approx(4.5 + 2.5, abs=0.1)
    d.survivor["Boon: Steadfast"]["regression"] = 0.25
    assert g.one_generator(d, [S(("Boon: Steadfast",))], K(), scen).lost == pytest.approx(4.5 + 3.75, abs=0.1)


def test_hyperfocus_also_raises_the_trigger_odds_per_token():
    """Wiki: +4 % Skill Check trigger odds per Token (max 6) – percentage points like Unnerving Presence (whose
    change log names it a static increase of the base chance). Expected over the stationary Token counts."""
    assert D.survivor["Hyperfocus"]["chance_per_token"] == pytest.approx(0.04)
    hyper = S(("Hyperfocus",))
    # every check Great: always 6 Tokens → +24 points
    assert g.skill_checks(D, [hyper], None, 1.0)[0][0] == pytest.approx(0.24)
    # half Great: Token shares 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.015625, 0.015625 → mean 0.984375 Tokens
    assert g.skill_checks(D, [hyper], None, 0.5)[0][0] == pytest.approx(0.04 * 0.984375)
    # none Great: no Token, nothing added; without the perk nothing either
    assert g.skill_checks(D, [hyper], None, 0.0)[0][0] == 0.0
    assert g.skill_checks(D, [S()], None, 1.0)[0][0] == 0.0
    # on the Generator, all Great, alone: 1 c/s + 0.32 · 0.9 c · 2.8 (bonus +30 % × 6 Tokens) = 1.8064 c/s → 49.82 s
    assert g.one_generator(D, [hyper], None, Sc(great=1.0, miss=0, kicks=0)).seconds == \
        pytest.approx(90 / 1.8064, abs=0.01)
