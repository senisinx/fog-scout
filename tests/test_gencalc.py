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
             "requirement_all", "requirement_once"}
    assert all(e["kind"] in kinds for e in raw["survivor"])
    for e in raw["killer"]:
        assert e["kind"] in {"slow", "slow_first", "kick_loss", "overcharge", "regress_mult", "ruin",
                             "instant", "undone", "block"}, e["name"]
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
        assert saved["n"] == 4 and saved["survivors"][0] == [["Prove Thyself", "Resilience"], "Toolbox", []]
        assert "0.85" not in app.calc_rates_var.get() and app.calc_rates_var.get()
        # the Killer perk picked sets its usual count
        app.calc_kill[1][0].set("Thanatophobia")
        app._calc_killer_picked(1)
        assert app.calc_kill[1][1].get() == "2" and app.settings.get("calc")["counts"]["Thanatophobia"] == "2"
        app.calc_dr_var.set(False)
        app._calc_changed()
        assert app.settings.get("calc")["diminishing"] is False
        # 1.51.1: what the chosen perks do, each once; a perk without a count greys its count out; reset
        text = app.calc_effects_var.get()
        assert "Prove Thyself – +10 % Tempo je weiterem Survivor" in text and text.count("Resilience") == 1
        assert "Pop Goes the Weasel – ein Kick nimmt 20 % statt 5 %" in text and "Toolbox – +50 % Tempo" in text
        assert not app.calc_count_boxes[0].instate(["disabled"])              # Pop: kicks with the perk
        app.calc_kill[2][0].set("Call of Brine")
        app._calc_killer_picked(2)
        assert app.calc_count_boxes[2].instate(["disabled"]) and app.calc_count_boxes[3].instate(["disabled"])
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
    assert set(app_calc.COUNT_MEANS) == {n for n, e in D.killer.items() if e.get("count")}
