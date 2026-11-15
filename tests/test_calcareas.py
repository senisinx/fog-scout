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
    assert sorted(p.source for p in ln.parts) == ["Hope", "Sprint Burst"]
    assert ln.parts[0].seconds == 2 and ln.parts[0].when == "trigger" and ln.parts[1].when == "gates"
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
    assert line("hook", "unhook", [S(("Slippery Meat",)), S()], subject=1).result == pytest.approx(0.5)
    # Tokens of a Survivor perk: all, half, one
    flow = [S(("Flow State",))]
    assert line("objects", "bless", flow).mult == pytest.approx(1.75)
    assert line("objects", "bless", flow, scen=Sc(stacks=0.5)).mult == pytest.approx(1 + 0.15 * 2)
    assert line("objects", "bless", flow, scen=Sc(stacks=0.0)).mult == pytest.approx(1.15)
    assert line("objects", "gate", [S(("Wake Up!",))]).mult == pytest.approx(1.7)        # 10 % + 4 · 15 %
    assert line("objects", "cleanse", [S(("Counterforce",))], scen=Sc(stacks=0.0)).mult == pytest.approx(2.5)


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
    empty = perkicons.Index([str(tmp_path / "nothing")])
    assert not empty.any() and empty.find("Botany Knowledge") is None
    assert perkicons.folders("D") == [os.path.join("D", perkicons.USER_FOLDER),
                                      os.path.join(perkicons.HERE, perkicons.FOLDER)]


def test_every_perk_of_the_calculator_has_its_picture_in_the_program():
    """Saru: "Wiki ist in Ordnung" – the perks' pictures come with the program (64 px PNG from the Dead by Daylight
    Wiki, THIRD_PARTY.md): one for every perk of perkdata.json, nothing else in the folder, each a small picture."""
    from PIL import Image
    folder = os.path.join(perkicons.HERE, perkicons.FOLDER)
    index = perkicons.Index([folder])
    names = set(D.survivor) | set(D.killer) | set(D.perks)
    assert [n for n in sorted(names) if index.find(n) is None] == []
    used = {index.find(part) for n in names for part in n.split(" / ")} - {None}
    files = sorted(os.listdir(folder))
    assert sorted(os.path.basename(p) for p in used) == files and len(files) > 100
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
        assert "Prove Thyself" not in values
        kbox = app.calc_perk_boxes[16][0]
        assert "Coulrophobia" in kbox.cget("values") and "Pop Goes the Weasel" not in kbox.cget("values")
        # the assumptions of the Generators are away, the Tokens are asked
        assert not shown(app, app.calc_opt_rows["kicks"]) and shown(app, app.calc_opt_rows["stacks"])
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
        tips = app.calc_tips_var.get()
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
        assert shown(app, app.calc_opt_rows["kicks"]) and not shown(app, app.calc_opt_rows["stacks"])
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
