"""Loadouts from the pause menu (loadouts.py): the survivors' perks, item and add-ons read from the picture only,
placed beside their portraits in the HUD's survivor list.

Test pictures (tests/data/loadouts, every player name painted over):
- ``menu_3440_survivor.jpg``: the user's 3440×1440 pause menu as a survivor (shown at 2000×837) – own row gold,
  three bots; the menu's order (Dwight, Renato, Ellen, Dustin) is not the HUD's.
- ``menu_3440_hidden.jpg``: the same menu in another state – the survivors' loadouts hidden, the killer's shown,
  another order.
- ``hud_3440.jpg``: the HUD of that match – own portrait on top, then Dustin, Renato, Ellen.
- ``menu_3440_fourth.jpg``: the user's menu of a fourth match (1.57.5) – Lara, Vittorio, Eleven; Vittorio's
  Small Game fits only 0.76 but far ahead of any other perk.
- ``menu_four_rows.png``: the four icon rows of the picture of the first request (another player's menu, other
  scale; names, pings and the killer's row painted over)."""
import json
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fogscout import loadouts  # noqa: E402
from fogscout.loadouts import Board, Row, Votes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tests", "data", "loadouts")

# read by eye on the original pictures (a slot the reader may leave open is not listed)
OWN = {0: "Head On", 1: "Quick & Quiet", 2: "Deception", 3: "Background Player", 4: "Utility Flashlight",
       5: "Long Life Battery", 6: "High-End Sapphire Lens"}
BOT = {0: "Hyperfocus", 1: "Stake Out", 2: None, 3: "Prove Thyself", 6: "Self Adherent Wrap"}
FIRST = [
    {0: "Bond", 2: "Botany Knowledge", 3: "Iron Will"},
    {0: "Dead Hard", 1: "Resurgence", 2: "Made for This"},
    {0: "Sprint Burst", 2: "We'll Make It", 3: "Resilience"},
    {0: "Sprint Burst", 2: "Resilience", 4: "Utility Flashlight", 5: "Long Life Battery"},
]


def _load(name, size=(3440, 1440)):
    pic = cv2.imread(os.path.join(DATA, name))
    assert pic is not None, name
    return cv2.resize(pic, size, interpolation=cv2.INTER_LANCZOS4) if size else pic


@pytest.fixture(scope="module")
def reader():
    return loadouts.Reader()


@pytest.fixture(scope="module")
def menu():
    return _load("menu_3440_survivor.jpg")


def _slots(row: Row) -> list:
    return list(row.perks) + [row.item] + list(row.addons)


def _check_real(board: Board):
    assert board is not None and len(board.rows) == 4
    assert [r.own for r in board.rows] == [True, False, False, False]        # the gold row
    for row, want in zip(board.rows, [OWN, BOT, BOT, BOT]):
        got = _slots(row)
        for slot, name in want.items():
            assert got[slot] == name, (slot, got)
    assert all(r.face is not None for r in board.rows)


def test_the_names_file_knows_every_picture_and_each_name_once():
    names = loadouts.load_names()
    assert len(names["perks"]) >= 175 and len(names["items"]) >= 40 and len(names["addons"]) >= 50
    for kind, files in names.items():
        assert len(set(files.values())) == len(files), kind              # a name has one picture
        for f in files:
            assert os.path.isfile(os.path.join(loadouts.ICONS, f)), f
    assert loadouts.icon_file("Dead Hard", "perks").endswith("IconPerks_deadHard.png")
    assert loadouts.icon_file("Hex: Ruin", "perks") is None                 # a killer's perk is no survivor's
    with open(loadouts.NAMES_FILE, encoding="utf-8") as f:
        assert "Wiki" in json.load(f)["about"]


def test_the_users_real_menu_is_read(reader, menu):
    """1.57.1 (user: "funktioniert nicht" – the real menu's diamonds are darker than on the first picture, the
    drawing covers most of them): perks, item, add-ons and the own (gold) row of the 3440×1440 menu."""
    _check_real(reader.read(menu))


@pytest.mark.parametrize("scale", [0.8, 0.9, 1.1])
def test_another_ui_scale_and_place_is_read_too(reader, menu, scale):
    """DBD's UI scale can be set: the menu smaller / larger, somewhere else in the 3440×1440 window. (The test
    picture is a 2000-px copy blown up again: much larger is too blurred to say anything – a real one is sharp.)"""
    small = cv2.resize(menu, None, fx=scale, fy=scale,
                       interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    frame = np.zeros((1440, 3440, 3), np.uint8)
    h, w = min(1440, small.shape[0]), min(3440, small.shape[1])
    frame[:h, :w] = small[:h, :w]
    _check_real(reader.read(frame))


@pytest.mark.parametrize("hue", [25, 60])
def test_a_perk_of_tier_one_or_two_has_another_colour_and_is_read_the_same(reader, menu, hue):
    """Saru: a perk not at tier 3 is drawn on yellow (tier 1) or green (tier 2) instead of purple – the drawing is
    compared, never the colour."""
    hsv = cv2.cvtColor(menu, cv2.COLOR_BGR2HSV)
    purple = (hsv[..., 0] >= 125) & (hsv[..., 0] <= 160) & (hsv[..., 1] >= 40)
    hsv[..., 0][purple] = hue // 2                                   # OpenCV hue is 0–179: degrees / 2
    _check_real(reader.read(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)))


def test_the_menu_with_hidden_loadouts_gives_nothing(reader):
    """Another state of the menu: the survivors' loadouts hidden, the killer's shown – no survivor row, and the
    killer's (red) row is never one."""
    board = reader.read(_load("menu_3440_hidden.jpg"))
    assert board is None or all(r.empty for r in board.rows)


def test_the_first_picture_of_another_scale_is_read(reader):
    board = reader.read(_load("menu_four_rows.png", None))
    assert board is not None and len(board.rows) == 4
    for row, want in zip(board.rows, FIRST):
        got = _slots(row)
        for slot, name in want.items():
            assert got[slot] == name, (slot, got)


def test_a_picture_without_the_menu_gives_nothing(reader):
    for name in os.listdir(os.path.join(ROOT, "tests", "data", "end")):
        pic = cv2.imread(os.path.join(ROOT, "tests", "data", "end", name))
        board = reader.read(pic)
        assert board is None or all(r.empty for r in board.rows), name
    assert reader.read(_load("hud_3440.jpg")) is None or all(r.empty for r in reader.read(_load("hud_3440.jpg")).rows)
    assert reader.read(np.zeros((1440, 3440, 3), np.uint8)) is None
    rng = np.random.default_rng(1)
    assert reader.read(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)) is None


def test_names_in_any_script_change_nothing(reader, menu):
    """Saru: player names can be Japanese, Latin, Russian … – the reader never reads them (a row is found by its
    perks, a survivor by the portrait): text of any script and length in the name lines changes nothing."""
    from PIL import Image, ImageDraw
    pic = Image.fromarray(cv2.cvtColor(menu, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pic)
    for y in (268, 420, 573, 724):                   # the name lines at 3440×1440
        d.rectangle((1470, y - 22, 2090, y + 22), fill=(25, 28, 30))
        d.text((1475, y - 10), "ПРИЗРАК_ninja 忍者サバイバー 생존자 xX__Xx", fill=(235, 235, 235))
    _check_real(reader.read(cv2.cvtColor(np.asarray(pic), cv2.COLOR_RGB2BGR)))


def test_an_unknown_drawing_is_never_given_a_name(reader):
    """A slot whose drawing fits no picture clearly stays open (never the nearest guess)."""
    templ = reader.perks
    blob = np.zeros((1, loadouts.GLYPH * loadouts.GLYPH), np.float32)
    blob[0, ::7] = 1
    assert templ.best(blob)[0] is None
    assert templ.best(np.zeros((0, loadouts.GLYPH ** 2), np.float32))[0] is None


# ------------------------------------------------------------------ who is who: portraits, not names (1.57.1)
def test_each_survivor_is_found_by_the_portrait_in_the_hud(reader, menu):
    """The menu's order is not the HUD's (user's pictures): menu Dwight, Renato, Ellen, Dustin – HUD own on top,
    then Dustin, Renato, Ellen. Each portrait of the menu is found beside its player in the HUD."""
    v = Votes()
    for pic in (menu, _load("menu_3440_hidden.jpg"), menu):      # the hidden state in between changes nothing
        v.note(reader.read(pic))
    assert v.side > 0 and len(v.faces()) == 4 and not v.placed
    found = loadouts.HudFinder().find(_load("hud_3440.jpg"), v.faces(), v.side)
    assert set(found) == {0, 1, 2, 3}
    assert not v.place(found) and not v.placed                    # one look is not enough (1.57.2) …
    assert v.place(found) and v.placed                            # … the second one agrees
    board = v.board()
    by_y = [r.who for r in sorted(board.rows, key=lambda r: r.hud[1])]
    assert by_y == [0, 3, 1, 2]                                   # own (Dwight), Dustin, Renato, Ellen
    ys = [round(r.hud[1] * 837) for r in sorted(board.rows, key=lambda r: r.hud[1])]
    for got, want in zip(ys, (355, 422, 491, 560)):              # the portraits' centres in the 2000×837 picture
        assert abs(got - want) <= 6, ys
    assert board.rows[0].own and [r.who for r in board.others] == [1, 2, 3]
    assert board.others[0].perks[:2] == ("Hyperfocus", "Stake Out")


def test_a_survivor_keeps_its_slots_when_the_menu_changes_its_order():
    """Rows are found again by the portrait, never by their place in the menu."""
    faces = [np.full((loadouts.FACE, loadouts.FACE), 0, np.uint8) for _ in range(2)]
    faces[0][:, :12] = 200
    faces[1][:12, :] = 200
    a = Row(perks=("Dead Hard", None, None, None), face=faces[0])
    b = Row(perks=("Lithe", None, None, None), face=faces[1])
    v = Votes()
    v.note(Board(rows=(a, b)))
    v.note(Board(rows=(b, a)))
    rows = v.board().rows
    assert [r.perks[0] for r in rows] == ["Dead Hard", "Lithe"] and len(rows) == 2


def test_the_own_survivor_without_gold_is_the_top_of_the_hud():
    """No gold row seen: the own survivor is the top portrait of the HUD's list – once every survivor has its
    place there; until then nobody is taken for the own one."""
    faces = [np.zeros((loadouts.FACE, loadouts.FACE), np.uint8) for _ in range(3)]
    for i, f in enumerate(faces):
        f[i * 8:(i + 1) * 8, :] = 200
    v = Votes()
    v.note(Board(rows=tuple(Row(perks=(f"P{i}", None, None, None), face=f) for i, f in enumerate(faces)), pitch=40))
    assert not any(r.own for r in v.board().rows)
    for _ in range(2):
        v.place({0: (0.18, 0.582, 0.05), 1: (0.18, 0.418, 0.05)})
    assert not any(r.own for r in v.board().rows)                # one still missing
    for _ in range(2):
        v.place({0: (0.18, 0.582, 0.05), 1: (0.18, 0.418, 0.05), 2: (0.18, 0.50, 0.05)})
    assert [r.own for r in v.board().rows] == [False, True, False]


def _row(*perks, own=False, item=None):
    return Row(perks=tuple(perks) + (None,) * (4 - len(perks)), item=item, own=own)


def test_a_slot_counts_after_two_equal_readings_and_a_tie_stays_open():
    v = Votes()
    first = Board(rows=(_row("Bond", own=True), _row("Dead Hard", "Adrenaline")))
    assert v.note(first) is False                                 # one look: nothing yet
    assert v.board().rows[1].perks == (None,) * 4
    assert v.note(first) is True
    assert v.board().rows[1].perks[:2] == ("Dead Hard", "Adrenaline")   # rows without a portrait: by their place
    assert len(v.board().rows) == 2
    assert v.note(None) is False
    v.reset()
    assert v.board().rows == () and v.looks == 0
    two = Votes()
    for perk in ("Adrenaline", "Adrenaline", "Lithe", "Lithe"):
        two.note(Board(rows=(_row("Dead Hard", perk),)))
    assert two.board().rows[0].perks[1] is None                   # 2 × Adrenaline, 2 × Lithe: open
    two.note(Board(rows=(_row("Dead Hard", "Lithe"),)))
    assert two.board().rows[0].perks[1] == "Lithe"


# ------------------------------------------------------------------ drawing and place
def test_the_card_is_as_wide_whatever_was_read_and_skips_empty_rows():
    from fogscout.app_loadouts import SAMPLE, icon_for
    from fogscout.overlay_render import loadout_card, loadout_size
    rows = SAMPLE.others
    full = loadout_card(rows, 96, (0, 110, 220), 316, True, icon_for)
    assert full.size == loadout_size(96, 316, True)
    some = loadout_card((Row(perks=("Dead Hard", None, None, None)), Row()), 96, (0, 110), 316, True, icon_for)
    assert some.width == full.width                                   # never breathes
    alpha = np.asarray(some)[..., 3]
    assert alpha[:96].any() and not alpha[100:].any()                 # the empty row: nothing drawn
    assert loadout_size(96, 316, False)[0] < full.width               # the item squares need room


def test_beside_the_portraits_found_in_the_hud():
    from fogscout import layout
    from fogscout.app_loadouts import placed
    o = {"loadouts_scale": 1.0, "loadouts_items": True, "loadouts_pos": "hud", "margin": 0.012}
    rows = (Row(own=True, hud=(0.177, 0.422, 0.05)),
            Row(perks=("Dead Hard", None, None, None), hud=(0.177, 0.586, 0.05)),
            Row(perks=("Lithe", None, None, None), hud=(0.177, 0.504, 0.05)),
            Row(perks=("Vigil", None, None, None)))                   # not found in the HUD: not drawn
    pic, x, y = placed(o, (0, 0, 3440, 1440), Board(rows=rows))
    cluster = int(0.05 * 1440 * layout.LOADOUT_PER_FACE)
    left = 0.177 * 3440 - 0.05 * 1440 / 2                             # the portraits' left edge
    assert 440 <= x and x + pic.width <= left                         # right before the portraits (the sketch)
    far = tuple(Row(perks=r.perks, own=r.own, hud=(0.13, r.hud[1], r.hud[2])) if r.hud else r for r in rows)
    pic3, x3, y3 = placed(o, (0, 0, 3440, 1440), Board(rows=far))     # no room before them: in the black bar
    assert x3 + pic3.width <= 440 and x3 > 440 - pic3.width - 20
    assert abs(y + cluster / 2 - 0.504 * 1440) <= 1                   # the first row at the first portrait
    assert abs(pic.height - (0.586 - 0.504) * 1440 - cluster) <= 2
    assert placed(o, (0, 0, 3440, 1440), Board(rows=rows[3:])) is None    # nothing found yet: nothing shown
    pic, x, y = placed(o, (0, 0, 2560, 1440), Board(rows=rows))
    assert 0 <= x and x + pic.width <= 0.177 * 2560 - 36              # a 16:9 window: before the portraits too
    pic2, x, y = placed(dict(o, loadouts_pos="custom", loadouts_xy=[0.5, 0.5]), (100, 0, 2560, 1440),
                        Board(rows=rows))
    assert abs(x + pic2.width / 2 - (100 + 1280)) <= 1 and abs(y + pic2.height / 2 - 720) <= 1
    big = placed(dict(o, loadouts_scale=9), (0, 0, 3440, 1440), Board(rows=rows))[0]
    assert big.width > pic.width                                      # the size slider (capped at 200 %)


def test_the_preview_shows_the_sample_beside_the_list():
    from fogscout import config, layout, preview
    from fogscout.app_loadouts import SAMPLE, placed
    o = dict(config.DEFAULTS["overlay"], show_loadouts=True)
    out, _rect = preview.layers(1720, 720, o, "", [], None, None, "", {}, 0.4,
                                loadouts=lambda oo, game: placed(oo, game, SAMPLE, sample=True))
    names = [n for n, *_ in out]
    assert "loadouts" in names
    _n, pic, x, y = out[names.index("loadouts")]
    left = 220 + layout.LOADOUT_LEFT * 1280                           # where the portraits begin in 1720 × 720
    assert 220 <= x and x + pic.width <= left


# ------------------------------------------------------------------ 1.57.2: one stray match never sticks
def _second_hud(scale=1.16):
    """The user's second HUD picture (a crop: their own diamonds and the names blacked out) in a 3440×1440
    frame, the portraits where DBD draws them."""
    crop = cv2.imread(os.path.join(DATA, "hud_crop_second.jpg"))
    big = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    frame = np.zeros((1440, 3440, 3), np.uint8)
    x0, y0 = int(610 - 220 * scale), 300
    frame[y0:y0 + big.shape[0], x0:x0 + big.shape[1]] = big[:1440 - y0]
    return frame, y0, scale


def test_the_second_match_puts_every_bot_beside_its_portrait(reader):
    """User (1.57.1): a diamond above the own portrait, none at Feng Min. Menu: own Dwight, Steve, Alan, Feng; HUD:
    own, Feng, Steve, Alan."""
    menu = _load("menu_3440_second.jpg")
    board = reader.read(menu)
    assert board is not None and [r.own for r in board.rows] == [True, False, False, False]
    for row in board.others:
        assert row.perks == ("Hyperfocus", "Stake Out", "Better than New", "Prove Thyself")
        # Sport and Masquerade Flashlight are drawn nearly alike (0.88 / 0.86 here): left open, never the wrong one
        assert row.item in (None, "Sport Flashlight")
    v = Votes()
    v.note(board)
    v.note(reader.read(menu))
    frame, y0, sc = _second_hud()
    for _ in range(2):
        v.place(loadouts.HudFinder().find(frame, v.faces(), v.side))
    assert v.placed
    rows = sorted(v.board().rows, key=lambda r: r.hud[1])
    assert [r.who for r in rows] == [0, 3, 1, 2]                  # own, Feng, Steve, Alan
    for r, want in zip(rows, (150, 268, 384, 504)):               # the portraits' centres in the crop
        assert abs((r.hud[1] * 1440 - y0) / sc - want) <= 8
    assert rows[0].own and not any(r.own for r in rows[1:])


def test_a_place_off_the_lists_grid_or_seen_once_is_never_taken():
    def at(y):
        return (0.177, y, 0.05)
    grid = {0: at(0.42), 1: at(0.502), 2: at(0.584)}
    assert loadouts.on_grid(grid) == grid
    assert set(loadouts.on_grid({**grid, 3: at(0.38)})) == {0, 1, 2}        # half a row above: not on the grid
    assert set(loadouts.on_grid({**grid, 3: (0.4, 0.666, 0.05)})) == {0, 1, 2}   # another column
    assert loadouts.on_grid({0: at(0.42)}) == {}                              # alone: says nothing
    assert set(loadouts.on_grid({0: at(0.42), 2: at(0.584)})) == {0, 2}       # a row between may be covered
    faces = [np.zeros((loadouts.FACE, loadouts.FACE), np.uint8) for _ in range(4)]
    for i, f in enumerate(faces):
        f[i * 6:(i + 1) * 6, :] = 200
    v = Votes()
    v.note(Board(rows=tuple(Row(perks=(f"P{i}", None, None, None), face=f, own=i == 0) for i, f in enumerate(faces)),
                 pitch=40))
    v.place({0: at(0.42), 1: at(0.502), 3: at(0.38)})          # 3 strays above the list …
    v.place({0: at(0.42), 1: at(0.502), 3: at(0.666)})         # … and is found right the next time
    rows = {r.who: r.hud for r in v.board().rows}
    assert rows[0] and rows[1] and rows[3] is None and rows[2] is None   # 3: two looks disagree – not yet
    v.place({0: at(0.42), 1: at(0.502), 2: at(0.584), 3: at(0.666)})
    rows = {r.who: r.hud for r in v.board().rows}
    assert rows[3] is not None and abs(rows[3][1] - 0.666) < 0.01 and rows[2] is None   # 2: seen once only


# ------------------------------------------------------------------ 1.57.3: below the name, in one row
def test_below_each_name_the_perks_stand_in_one_row():
    """User: "evtl. unter dem Namen der entsprechenden Person", "Perks in einer Reihe" – each row's top just below
    its name (right of the portrait), the four perks side by side; the row is as tall as the room there."""
    from fogscout import layout
    from fogscout.app_loadouts import placed
    from fogscout.overlay_render import loadout_size
    o = {"loadouts_scale": 1.0, "loadouts_items": True, "loadouts_pos": "name", "margin": 0.012}
    rows = (Row(perks=("Dead Hard", None, None, None), hud=(0.177, 0.504, 0.05)),
            Row(perks=("Lithe", None, None, None), hud=(0.177, 0.586, 0.05)))
    pic, x, y = placed(o, (0, 0, 3440, 1440), Board(rows=rows))
    face = 0.05 * 1440
    size = int(face * layout.LOADOUT_ROW_H)
    assert abs(x - (0.177 * 3440 + face * layout.LOADOUT_NAME_X)) <= 1          # where the names begin
    assert abs(y - (0.504 * 1440 + face * layout.LOADOUT_NAME_Y)) <= 1          # just below the first name
    assert pic.size == loadout_size(size, round((0.586 - 0.504) * 1440) + size, True, row=True)
    assert y + size < 0.586 * 1440 - face / 2                         # above the next portrait
    assert pic.width > 4 * size                                       # four perks side by side, then the item
    diamond = placed(dict(o, loadouts_pos="hud"), (0, 0, 3440, 1440), Board(rows=rows))[0]
    row = placed(dict(o, loadouts_pos="hud", loadouts_style="row"), (0, 0, 3440, 1440), Board(rows=rows))[0]
    assert row.width > diamond.width and row.height < diamond.height  # the style is a choice beside the list too
    from fogscout.appconst import LOADOUT_SPOTS, LOADOUT_STYLES
    assert [k for k, _t in LOADOUT_SPOTS] == ["hud", "name", "custom"]
    assert [k for k, _t in LOADOUT_STYLES] == ["diamond", "row"]


# ------------------------------------------------------------------ 1.57.4: offerings, the last one missing
def test_the_offering_is_read_and_a_hidden_one_is_named_so(reader, menu):
    """User: "Offerings bitte auch", "falls jemand was Verstecktes wirft, soll dies ebenfalls so angezeigt werden"
    – the own Petrified Oak, the bots' hidden offerings; an empty hexagon stays empty."""
    board = reader.read(menu)
    assert [r.offering for r in board.rows] == ["Petrified Oak"] + [loadouts.HIDDEN_OFFERING] * 3
    third = reader.read(_load("menu_3440_third.jpg"))
    assert [r.offering for r in third.rows] == ["Petrified Oak", loadouts.HIDDEN_OFFERING,
                                                loadouts.HIDDEN_OFFERING, None]
    assert loadouts.icon_file("Petrified Oak", "offerings").endswith(".png")
    assert loadouts.icon_file(loadouts.HIDDEN_OFFERING, "offerings") is None      # drawn, not a picture


def test_a_hidden_offering_is_drawn_with_a_question_mark():
    from fogscout.app_loadouts import icon_for
    from fogscout.overlay_render import loadout_card
    row = Row(perks=("Dead Hard", None, None, None), offering=loadouts.HIDDEN_OFFERING)
    empty = Row(perks=("Dead Hard", None, None, None))
    for style in (False, True):
        a = np.asarray(loadout_card((row,), 96, (0,), 96, True, icon_for, row=style))
        b = np.asarray(loadout_card((empty,), 96, (0,), 96, True, icon_for, row=style))
        assert a.shape == b.shape and (a != b).any()                  # the hexagon differs (a "?" inside)
        assert np.asarray(loadout_card((row,), 96, (0,), 96, False, icon_for, row=style)).shape[1] < a.shape[1]


def test_the_third_match_finds_every_portrait(reader):
    """User (1.57.3): Nancy never placed. Only the round middle of a portrait is compared now (the corners show
    the game behind it, a framed one its brackets)."""
    v = Votes()
    for _ in range(2):
        v.note(reader.read(_load("menu_3440_third.jpg")))
    frame = _load("hud_3440_third.jpg")
    for _ in range(2):
        v.place(loadouts.HudFinder().find(frame, v.faces(), v.side))
    assert v.placed
    rows = sorted(v.board().rows, key=lambda r: r.hud[1])
    assert [r.who for r in rows] == [0, 3, 1, 2]                  # own, Mikaela, Jeff, Nancy
    for r, want in zip(rows, (353, 422, 489, 558)):
        assert abs(r.hud[1] * 837 - want) <= 6


def test_the_last_one_missing_is_looked_for_at_the_free_row(reader):
    """Three of four placed: the fourth is looked for only at the list's free row, with a lower bar – two looks."""
    v = Votes()
    for _ in range(2):
        v.note(reader.read(_load("menu_3440_third.jpg")))
    frame = _load("hud_3440_third.jpg")
    places = loadouts.HudFinder().find(frame, v.faces(), v.side)
    nancy = places.pop(2)
    for _ in range(2):
        v.place(places)
    who, free = v.missing()
    assert who == 2 and any(abs(p[1] - nancy[1]) < 0.01 for p in free)
    scores = {p: loadouts.score_at(frame, v.faces()[2], p) for p in free}
    assert max(scores.values()) >= loadouts.HUD_LAST_FIT
    assert not v.place_last(2, scores)                            # once: not yet
    assert v.place_last(2, scores) and v.placed                   # twice the same row: placed
    assert abs({r.who: r.hud for r in v.board().rows}[2][1] - nancy[1]) < 0.01
    assert "HUD ja" in v.describe() and "eigener" in v.describe()


@pytest.mark.parametrize("quality,noise", [(70, 0), (80, 4), (95, 2)])
def test_a_row_with_few_perks_is_kept_however_the_picture_is_decoded(reader, quality, noise):
    """CI on Windows (Python 3.14) decoded the third menu a hair differently: the row with only two perks fell
    below the bar and was missing. Menu rows are evenly spaced – a row on the grid is read like the others."""
    base = cv2.imread(os.path.join(DATA, "menu_3440_third.jpg"))
    _ok, buf = cv2.imencode(".jpg", base, [cv2.IMWRITE_JPEG_QUALITY, quality])
    pic = cv2.imdecode(buf, cv2.IMREAD_COLOR).astype(np.int16)
    if noise:
        pic = pic + np.random.default_rng(quality).normal(0, noise, pic.shape)
    pic = cv2.resize(np.clip(pic, 0, 255).astype(np.uint8), (3440, 1440), interpolation=cv2.INTER_LANCZOS4)
    board = reader.read(pic)
    assert board is not None and len(board.rows) == 4
    assert [r.offering for r in board.rows] == ["Petrified Oak", loadouts.HIDDEN_OFFERING,
                                                loadouts.HIDDEN_OFFERING, None]


def test_the_menu_rows_follow_their_grid():
    rows = loadouts._menu_rows([300.0, 450.0, 600.0], 70.0, 1440)          # 150 apart: three found …
    assert [round(y) for y, _i in rows if not _i] == [300, 450, 600]
    assert 750 in [round(y) for y, inferred in rows if inferred]         # … the fourth on their grid
    assert loadouts._menu_rows([300.0, 340.0], 70.0, 1440) == [(300.0, False), (340.0, False)]   # too close: no grid


def test_a_clear_lead_lets_a_weaker_fit_count(reader):
    """User (1.57.5): "Perks werden nicht alle sauber erkannt" – Small Game (fit 0.76, far ahead of the second
    best) and Saboteur stayed open. A slot of a found row counts with a weaker fit when it leads clearly; a close
    one (lead under LOOSE_MARGIN) still stays open, and most slots count after one look."""
    board = reader.read(_load("menu_3440_fourth.jpg"))
    assert board is not None and len(board.rows) == 4
    assert [r.perks for r in board.rows[1:]] == [
        ("Balanced Landing", "Boon: Dark Theory", "Breakout", None),        # Lara: Déjà Vu too close to call
        ("Wicked", "Small Game", "Adrenaline", "Plot Twist"),               # Vittorio
        ("Saboteur", "Resilience", None, "Change of Plan")]                 # Eleven: slot 3 is empty
    v = Votes()
    v.note(board)
    once = sum(1 for r in v.board().rows for p in r.perks if p)
    assert once >= 10                                                   # one look: nearly all perks already


def _fit(top, second):
    """Templates of two drawings and a glyph that fits them ``top`` and ``second``."""
    rng = np.random.default_rng(5)
    q, _r = np.linalg.qr(rng.normal(size=(loadouts.GLYPH * loadouts.GLYPH, 3)))
    q = q - q.mean(axis=0)
    q, _r = np.linalg.qr(q)
    e1, e2, e3 = q.T
    assert top ** 2 + second ** 2 <= 1
    glyph = top * e1 + second * e2 + np.sqrt(max(0.0, 1 - top ** 2 - second ** 2)) * e3
    t = loadouts.Templates("none", {}, extra={"A": e1, "B": e2})
    return t, glyph.reshape(1, -1).astype(np.float32)


@pytest.mark.parametrize("top,second,strict,loose", [
    (0.80, 0.55, True, True),       # the strict bars
    (0.72, 0.20, False, True),      # weaker, far ahead: only in a found row
    (0.66, 0.30, False, True),
    (0.60, 0.10, False, False),     # below the floor
    (0.79, 0.60, True, True),       # lead 0.19: both
    (0.70, 0.67, False, False),     # too close to call
])
def test_the_loose_rule_counts_only_in_a_found_row(top, second, strict, loose):
    t, glyph = _fit(top, second)
    name, score, lead = t.best(glyph)
    assert abs(score - top) < 0.01 and abs(lead - (top - second)) < 0.01
    assert (name == "A") == strict
    assert (t.best(glyph, loose=True)[0] == "A") == loose
