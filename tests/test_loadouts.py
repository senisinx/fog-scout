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
- ``menu_3440_twins.jpg``/``hud_3440_twins.jpg`` and ``…_twins_second``: two matches (1.57.6) with the own Dwight
  (no perks equipped: an empty gold row) and a bot Dwight – alike portraits; HUD order own, Dwight, Adam, Lara and
  own, Lara, Adam, Dwight.
- ``menu_3440_dejavu.webp``/``hud_3440_dejavu.jpg``: a match of 1.57.7 – own Dwight, Lee, Jill, Lara; Lara's
  fourth perk is Déjà Vu (an eye like Kindred and the Obsession perks, only the pupil differs). In the HUD Fog
  Scout's own rows are blacked out (as the worker does).
- ``menu_3440_eyes.webp``/``hud_3440_eyes.jpg``: the user's test of the critical perks (1.57.9) – Lara Object of
  Obsession, Kindred, Déjà Vu; Lee Kindred; Jill Déjà Vu, Sole Survivor. All the bright eyes made the diamond size
  fit 52 px best (64 right): nothing was shown. Names, a Discord notice and the music card blacked out.
- ``real_menu_eyes.webp``: the worker's menu crop of a custom game of 1.57.14 (19.11.) – own Jake with one perk, the
  same three bots as ``menu_3440_eyes`` at another UI size: 52 px fitted 0.77, the right size only 0.64–0.71, none
  within SIZE_SPAN – eight menu looks, nothing read. Player names painted over.
- ``real_menu_two_empty.webp``: the worker's menu crop of the next custom game (1.57.15, 19.11.) – own Jake with
  Iron Will, Jonah with three eyes and Plot Twist, two bots without any loadout. Player names painted over.
- ``real_menu_claudettes.webp``/``real_hud_claudettes.jpg``: the worker's crops of a custom game of 1.57.26 (20.11.)
  – four Claudettes in one skin, own one with Empathy, a bot without any loadout, the Obsession (DBD's brackets
  around her portrait) in the menu's last row and the HUD's second. Only the own player name painted over (the bots'
  names are DBD's: "Claudette Morel_01" …, used by the name test).
- ``real_menu_thalitas.webp``/``real_hud_thalitas.jpg``: the worker's crops of a custom game of 1.57.30 (20.11.) –
  own Claudette, three "Thalita Lyra" bots (one empty), the Obsession in the menu's second row. Only the own player
  name painted over.
- ``real_menu_toothy_torte.webp``: the user's 2000×837 pause menu of a public match (1.57.35, 20.11.) – own Dwight
  with the 10th anniversary event's Toothy Torte (gold hexagon), Feng without an offering, Yui a Sealed Envelope,
  Thalita a hidden one. All player names painted over.
- ``real_menu_killer.webp``/``real_hud_killer.jpg``: the user's killer menu and killer HUD (1.57.36, 2000×837, two
  public matches) – the menu shows only the survivors' offerings (two Vees, two Kates: Fresh Bog Laurel, hidden,
  Toothy Torte, Escape! Cake) above the own red row with Mephisto's perks; the HUD lists four survivors on the rows
  where a survivor's own row and the three below sit. All player names painted over.
- ``menu_four_rows.png``: the four icon rows of the picture of the first request (another player's menu, other
  scale; names, pings and the killer's row painted over)."""
import dataclasses
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
    compared, never the colour. (1.57.18: an item's or add-on's colour is its rarity and narrows it – recoloured
    here with the perks, they are left out of the check.)"""
    hsv = cv2.cvtColor(menu, cv2.COLOR_BGR2HSV)
    purple = (hsv[..., 0] >= 125) & (hsv[..., 0] <= 160) & (hsv[..., 1] >= 40)
    hsv[..., 0][purple] = hue // 2                                   # OpenCV hue is 0–179: degrees / 2
    board = reader.read(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
    assert board is not None and len(board.rows) == 4
    for row, want in zip(board.rows, [OWN, BOT, BOT, BOT]):
        for slot, name in want.items():
            if slot < 4:
                assert row.perks[slot] == name, (slot, row.perks)


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
    assert abs(x - (0.177 * 3440 + face * layout.LOADOUT_NAME_X)) <= 1          # right of the status icon
    assert abs(y - (0.504 * 1440 + face * layout.LOADOUT_NAME_Y - size / 2)) <= 1   # beside the status icon
    assert pic.size == loadout_size(size, round((0.586 - 0.504) * 1440) + size, True, row=True)
    assert y + size <= 0.504 * 1440 + 0.11 * face                     # 1.57.17: above the name and the bar below it
    assert y >= 0.504 * 1440 - 1.07 * face                            # … below the row above
    assert x >= 0.177 * 3440 + 2.4 * face                             # … right of the status icon and its marks
    big = placed(dict(o, loadouts_scale=2.0), (0, 0, 3440, 1440), Board(rows=rows))
    big_row = big[0].height - round((0.586 - 0.504) * 1440)           # a larger size still fits in between
    assert big[2] >= 0.504 * 1440 - 1.07 * face and big[2] + big_row <= 0.504 * 1440 + 0.11 * face
    assert pic.width > 4 * size                                       # four perks side by side, then the item
    custom = dict(o, loadouts_pos="custom", loadouts_xy=[0.2, 0.4])
    diamond = placed(custom, (0, 0, 3440, 1440), Board(rows=rows))[0]
    row = placed(dict(custom, loadouts_style="row"), (0, 0, 3440, 1440), Board(rows=rows))[0]
    assert row.width > diamond.width and row.height < diamond.height  # at a place of one's own the style is a choice
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


def test_the_anniversary_toothy_torte_is_read():
    """1.57.35 (user: "der neue kuchen wird nicht angezeigt im Spiel bei den Survivor" – "toothy torte"): the 10th
    anniversary event's cake was no known offering (best fit Shiny Coin 0.75) and its slot stayed empty; its drawing
    is cut from the user's menu, as the wiki's picture could not be fetched."""
    for size in ((3440, 1440), (2560, 1071), None):
        board = loadouts.Reader().read(           # its own reader: the shared one keeps the last grid
            _load("real_menu_toothy_torte.webp", size))
        assert [r.offering for r in board.rows] == ["Toothy Torte", None, "Sealed Envelope",
                                                    loadouts.HIDDEN_OFFERING]
    assert loadouts.icon_file("Toothy Torte", "offerings").endswith("IconFavors_toothyTorte.png")


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
    best) and Saboteur stayed open. A slot of a found row counts with a weaker fit when it leads clearly, and most
    slots count after one look. (Lara's Déjà Vu, 0.04 ahead of Kindred, is read since 1.57.7 – where the eyes
    differ.)"""
    board = reader.read(_load("menu_3440_fourth.jpg"))
    assert board is not None and len(board.rows) == 4
    assert [r.perks for r in board.rows[1:]] == [
        ("Balanced Landing", "Boon: Dark Theory", "Breakout", "Déjà Vu"),   # Lara (1.57.7: told from Kindred)
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


def _round(menu, hud, looks=4):
    """The worker's order: menu looks, then the HUD (each look: all portraits, then the last one missing)."""
    reader = loadouts.Reader()
    v = Votes()
    for _ in range(2):
        v.note(reader.read(_load(menu)))
    frame = _load(hud)
    for _ in range(looks):
        v.place(loadouts.HudFinder().find(frame, v.faces(), v.side))
        gap = v.missing()
        if gap:
            who, free = gap
            v.place_last(who, {p: loadouts.score_at(frame, v.faces()[who], p) for p in free})
    return v.board()


def test_the_own_row_without_perks_is_read_gold_and_empty(reader):
    """User (1.57.6): no perks equipped – the own gold row is empty, still it is the own row."""
    board = reader.read(_load("menu_3440_twins.jpg"))
    assert len(board.rows) == 4 and board.rows[0].own
    assert board.rows[0].empty and not any(r.own for r in board.rows[1:])


@pytest.mark.parametrize("menu,hud,order", [
    ("menu_3440_twins.jpg", "hud_3440_twins.jpg", ["Wicked", "Saboteur", "Balanced Landing"]),
    ("menu_3440_twins_second.jpg", "hud_3440_twins_second.jpg", ["Balanced Landing", "Saboteur", "Wicked"]),
])
def test_the_same_character_twice_each_at_its_own_portrait(menu, hud, order):
    """User (1.57.6, "funktioniert nicht richtig"): the own Dwight and a bot Dwight – the bot was taken for the
    own one (top of the list) and hidden. Two rows of a look are never one survivor; the own one is on top."""
    board = _round(menu, hud)
    rows = sorted(board.rows, key=lambda r: r.hud[1])
    assert all(r.hud for r in board.rows)
    assert rows[0].own
    assert [r.perks[0] for r in rows[1:]] == order
    assert [r.perks[0] for r in board.others] and len(board.others) == 3


def test_deja_vu_is_told_from_the_other_eyes(reader):
    """User (1.57.7): "bei Lara fehlt immer das eine Perk" – Déjà Vu, 0.03 ahead of Kindred on the whole drawing,
    is clearly ahead where the eyes differ (the pupil)."""
    board = reader.read(_load("menu_3440_dejavu.webp"))
    lara = [r for r in board.rows if r.perks[:3] == ("Balanced Landing", "Boon: Dark Theory", "Breakout")]
    assert lara and lara[0].perks[3] == "Déjà Vu"
    assert board.rows[0].own and board.rows[0].perks == ("Ace in the Hole", "Adrenaline", "Bardic Inspiration", None)


def test_only_perks_get_the_second_look_where_drawings_differ():
    """The med-kits stayed too close there on the user's menus – items never get it."""
    assert loadouts.Templates("perks", {}).perks_kind and not loadouts.Templates("items", {}).perks_kind


@pytest.mark.parametrize("menu,hud", [("menu_3440_dejavu.webp", "hud_3440_dejavu.jpg"),
                                      ("menu_3440_twins.jpg", "hud_3440_twins.jpg")])
def test_every_survivor_is_placed_within_a_few_quick_looks(menu, hud):
    """User (1.57.7): "es geht viel zu lange, bis es angezeigt wird". The HUD is looked at every 0.5 s now; once
    placed, only the HUD's size is searched (and the next rounds keep it). Four looks (2 s) at most here."""
    reader = loadouts.Reader()
    v = Votes()
    for _ in range(2):
        v.note(reader.read(_load(menu)))
    frame = _load(hud)
    from fogscout.worker import LOADOUT_LAST_AFTER
    for look in range(1, 5):
        v.place(loadouts.HudFinder().find(frame, v.faces(), v.side, v.scales(frame.shape[0])))
        gap = v.missing() if look >= LOADOUT_LAST_AFTER else None
        if gap:
            v.place_last(gap[0], {p: loadouts.score_at(frame, v.faces()[gap[0]], p) for p in gap[1]})
        if v.placed:
            break
    assert v.placed and look <= 4
    rows = sorted(v.board().rows, key=lambda r: r.hud[1])
    assert rows[0].own
    assert len(v.scales(frame.shape[0])) == 3                        # the HUD's size known now
    v.reset()
    assert len(v.scales(frame.shape[0])) == len(loadouts.HUD_SCALES)    # no menu read yet: side unknown
    v.note(reader.read(_load(menu)))
    assert len(v.scales(frame.shape[0])) == 3                        # … the next round keeps the size


def _slot_picture(icon_file, box, quality):
    """A perk slot as on the user's pictures: the wiki picture over a purple diamond of ``box`` px in a grey field,
    (JPEG), scaled up ×1.72 (their 2000 px pictures to 3440) – (picture, centre x, centre y, side)."""
    from PIL import Image, ImageDraw
    big_side = box * 4
    field = int(big_side * 1.6)
    pic = Image.new("RGBA", (field, field), (40, 40, 40, 255))
    o = (field - big_side) // 2
    ImageDraw.Draw(pic).polygon([(o + big_side / 2, o), (o + big_side, o + big_side / 2),
                                 (o + big_side / 2, o + big_side), (o, o + big_side / 2)], fill=(90, 40, 120, 255))
    icon = Image.open(os.path.join(loadouts.ICONS, icon_file)).convert("RGBA").resize((big_side, big_side))
    pic.alpha_composite(icon, (o, o))
    bgr = cv2.cvtColor(np.asarray(pic.convert("RGB")), cv2.COLOR_RGB2BGR)
    bgr = cv2.resize(bgr, (field // 4, field // 4), interpolation=cv2.INTER_AREA)
    if quality:
        bgr = cv2.imdecode(cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])[1], cv2.IMREAD_COLOR)
    bgr = cv2.resize(bgr, None, fx=1.72, fy=1.72, interpolation=cv2.INTER_LANCZOS4)
    return bgr, bgr.shape[1] / 2, bgr.shape[0] / 2, box * 1.72


@pytest.mark.parametrize("box,quality,off", [(37, 85, (0, 0)), (32, 70, (1.5, -1.2))])
def test_every_perk_is_read_as_itself_or_left_open(box, quality, off):
    """1.57.7 (user: "ich will, dass es perfekt funktioniert"): every wiki perk drawn like the user's pictures – small,
    compressed, a pixel or two off – is read as itself or not at all, never as another perk (the looser rules of a
    found row and the second look where eyes differ included). A perk with two names (licensed or not) is read
    as the one name of ``SAME_AS``."""
    names = loadouts.load_names()["perks"]
    perks = loadouts.Templates("perks")
    wrong, read = [], 0
    for f, name in names.items():
        pic, cx, cy, side = _slot_picture(f, box, quality)
        got = perks.best(loadouts._fine_cuts(perks, pic, cx + off[0] * 1.72, cy + off[1] * 1.72, side), loose=True)[0]
        want = loadouts.SAME_AS.get(name, name)              # one perk, two names (1.57.8)
        if got is not None and got != want:
            wrong.append((name, got))
        read += got == want
    assert not wrong
    assert read >= 0.9 * len(names)


def test_a_perk_with_two_names_is_read_as_one():
    """User (1.57.8): "Object of Obsession heisst es, wenn man den Myers-DLC hat, sonst Bound by Obsession. Dasselbe
    bei Sole Survivor" – one picture, one perk: read (and drawn) as the first name, never left open for the twin."""
    perks = loadouts.Templates("perks")
    for other, name in loadouts.SAME_AS.items():
        assert other not in perks.names and name in perks.names
        assert loadouts.icon_file(other, "perks") and loadouts.icon_file(name, "perks")
    names = loadouts.load_names()["perks"]
    for f, name in names.items():
        if name in loadouts.SAME_AS:
            pic, cx, cy, side = _slot_picture(f, 44, 0)
            assert perks.best(loadouts._fine_cuts(perks, pic, cx, cy, side), loose=True)[0] == loadouts.SAME_AS[name]


def test_a_menu_full_of_eyes_finds_the_right_diamond_size():
    """User (1.57.9, test of the critical perks: nothing shown): the brightness fit is flat over a few sizes; with
    bright eyes everywhere 26 (52 px) won, the grid slipped, and the person icon before each name was read as "This
    Is Not Happening" in every row. The sizes fitting nearly as well are tried with real perk hits now, and the
    looser rules count only in a row with two clear reads. 1.57.36: a reader of its own – the shared one keeps the
    last menu's grid (``_again``, 1.57.33), and under pytest-xdist another menu of another UI size read before it in
    the same worker (menu_3440_dejavu, …_third, …_twins_second) gave its 56 px grid instead of the size search."""
    board = loadouts.Reader().read(_load("menu_3440_eyes.webp"))
    assert board is not None and board.size >= 60
    assert board.rows[0].own and board.rows[0].perks == ("Ace in the Hole", "Adrenaline", "Bardic Inspiration", None)
    others = {r.perks[1]: r.perks for r in board.others}
    assert others["Kindred"] == ("Object of Obsession", "Kindred", "Breakout", "Déjà Vu")                 # Lara
    assert others["Small Game"] == ("Kindred", "Small Game", "Adrenaline", "Plot Twist")                 # Lee
    assert others["Sole Survivor"][0] in ("Déjà Vu", None) and others["Sole Survivor"][1:] == (
        "Sole Survivor", "Resilience", "Wicked")                                                         # Jill
    assert not any("This Is Not Happening" in r.perks for r in board.rows)
    board_hud = _round("menu_3440_eyes.webp", "hud_3440_eyes.jpg")
    rows = sorted(board_hud.rows, key=lambda r: r.hud[1])
    assert rows[0].own and [r.perks[1] for r in rows[1:]] == ["Sole Survivor", "Kindred", "Small Game"]


def test_a_menu_whose_right_size_fits_far_below_the_best_is_read(reader):
    """User (1.57.14, diagnosis "Menü-Blicke 0/8", eight clear menu pictures): the bright eyes fitted 52 px best and
    every size within SIZE_SPAN found no perk. When the near sizes find too few, further sizes are tried."""
    board = reader.read(_crop_frame("real_menu_eyes.webp", True))
    assert board is not None and len(board.rows) == 4
    assert board.rows[0].own and board.rows[0].perks == ("Iron Will", None, None, None)
    others = {r.perks[1]: r.perks for r in board.others}
    assert others["Small Game"] == ("Kindred", "Small Game", "Adrenaline", "Plot Twist")
    assert others["Sole Survivor"] == ("Déjà Vu", "Sole Survivor", "Resilience", "Wicked")
    lara = next(r.perks for r in board.others if "Breakout" in r.perks)     # her eyes differ only in the pupil:
    assert lara[2] == "Breakout"                                         # open rather than guessed (CI decodes
    for got, want in zip(lara, ("Object of Obsession", "Kindred", "Breakout", "Déjà Vu")):   # the picture a hair
        assert got in (want, None)                                       # differently than here)
    near = [n for _s, _p, n in loadouts._diamonds(_crop_frame("real_menu_eyes.webp", True), loadouts.SIZE_TRIES)]
    assert near and all(near)                                     # without "more" only the near sizes, as before


def test_eyes_found_a_few_pixels_off_the_diamond_search_still_make_the_grid(reader):
    """User (1.57.15, diagnosis "Menü-Blicke 0/8" again): two bots had no loadout, so the grid rested on the own
    Iron Will and Jonah's row – three eyes and Plot Twist. Jonah's eyes fitted 0.46 where the diamond search put
    them and 0.76 four pixels left; the coarse search's steps (size/10) missed that, one row stayed, no menu. The
    search goes as far in finer steps now; the person icon before each name is still no perk."""
    board = reader.read(_crop_frame("real_menu_two_empty.webp", True))
    assert board is not None and len(board.rows) == 2                  # the empty bots are no rows
    own, jonah = board.rows
    assert own.own and own.perks == ("Iron Will", None, None, None)
    assert not jonah.own and jonah.perks[3] == "Plot Twist" and sum(1 for p in jonah.perks if p) >= 3
    assert jonah.addons == ("High-End Sapphire Lens", "Long Life Battery")
    assert not any("This Is Not Happening" in r.perks for r in board.rows)


def test_the_slots_colour_narrows_items_and_addons_to_their_rarity(reader):
    """User (1.57.17: "Gelbe Taschenlampe von Jonah wird nicht erkannt", "Seltenheitsfarbe auswerten", "Mach dass die
    gelbe Taschenlampe erkannt wird"): the own Worn-Out Tools (Common, brown) stayed open – the Toolbox (Uncommon)
    fitted its drawing 0.916 against 0.927; Jonah's yellow flashlight is the Banquet Flashlight (Event, patch 10.0.1),
    which had no picture – it was read as the Masquerade Flashlight once. The slot's colour leaves only its rarity
    (yellow = Event, green = Uncommon), the Banquet items have their pictures, an item is read strictly."""
    board = reader.read(_crop_frame("real_menu_two_empty.webp", True))
    own, jonah = board.rows
    assert own.item == "Worn-Out Tools" and own.addons[0] == "Scraps"
    assert jonah.item == "Banquet Flashlight"
    assert jonah.addons == ("High-End Sapphire Lens", "Long Life Battery")
    names, rarity = loadouts.load_names(), loadouts.load_rarity()
    assert rarity["items"]["Worn-Out Tools"] == 1 and rarity["items"]["Toolbox"] == 2
    assert rarity["items"]["Masquerade Flashlight"] == 8 and rarity["items"]["Banquet Flashlight"] == 8
    assert set(rarity["items"]) == set(names["items"].values())              # every item has its rarity
    assert set(rarity["addons"]) == set(names["addons"].values())
    for hue, sat, val, want in ((12, 117, 48, {1, 11}), (19, 238, 200, {8}), (64, 216, 62, {2}), (108, 143, 41, {3}),
                                (141, 165, 64, {4}), (171, 222, 104, {5}), (96, 60, 44, None)):
        bgr = cv2.cvtColor(np.full((1, 1, 3), (hue, sat, val), np.uint8), cv2.COLOR_HSV2BGR)[0, 0]
        frame = np.zeros((100, 100, 3), np.uint8)
        frame[:] = bgr
        got = loadouts.slot_rarities(frame, 50, 50, 40)
        assert (set(got) if got else None) == want, (hue, got)


def test_loose_reads_count_only_in_a_proven_row():
    """A row with fewer than PROVEN_ROW clear reads keeps only those (a slipped grid reads loosely what isn't there)."""
    assert loadouts.PROVEN_ROW == 2


def test_the_style_follows_the_position():
    """User (1.57.9): "Die Einstellung macht keinen Sinn – wie kann es Raute 2×2 sein, wenn es in einer Reihe sein
    soll". Beside the list always the diamond, below the name always a row; only at a place of one's own the
    setting counts – the box shows what is drawn and is greyed out otherwise."""
    from fogscout.app_loadouts import LoadoutsCard, placed, style_of
    from fogscout.appconst import LOADOUT_STYLES
    from fogscout import uimodel as ui
    assert style_of({"loadouts_pos": "name", "loadouts_style": "diamond"}) == "row"
    assert style_of({"loadouts_pos": "hud", "loadouts_style": "row"}) == "diamond"
    assert style_of({"loadouts_pos": "custom", "loadouts_style": "row"}) == "row"
    o = {"loadouts_scale": 1.0, "loadouts_items": True, "margin": 0.012}
    rows = (Row(perks=("Dead Hard", None, None, None), hud=(0.177, 0.504, 0.05)),)
    beside = placed(dict(o, loadouts_pos="hud", loadouts_style="row"), (0, 0, 3440, 1440), Board(rows=rows))[0]
    plain = placed(dict(o, loadouts_pos="hud"), (0, 0, 3440, 1440), Board(rows=rows))[0]
    assert beside.size == plain.size

    class App(LoadoutsCard):
        def __init__(self, overlay):
            self.settings = {"overlay": overlay}
            self.loadouts_style_var = ui.StringVar()
            self.loadouts_style_cb = ui.Combobox(textvariable=self.loadouts_style_var, state="readonly")
    labels = dict(LOADOUT_STYLES)
    for spot, style, shown, free in (("name", "diamond", "row", False), ("hud", "row", "diamond", False),
                                     ("custom", "row", "row", True)):
        app = App({"loadouts_pos": spot, "loadouts_style": style})
        app._loadouts_style_sync()
        assert app.loadouts_style_var.get() == labels[shown]
        assert app.loadouts_style_cb.instate(["!disabled"]) == free


def test_debug_pictures_of_menu_and_hud_looks_are_kept_few(tmp_path):
    """1.57.11 (user's diagnosis showed only the result screen's look): with "Debug-Bilder speichern" each look at
    the menu / the HUD is kept at full size (the menu's middle, the HUD's left part), the newest LOADOUT_KEPT."""
    from types import SimpleNamespace
    from fogscout import worker
    stub = SimpleNamespace(data_dir=str(tmp_path))
    frame = np.zeros((1440, 3440, 3), np.uint8)
    for _ in range(worker.LOADOUT_KEPT + 3):
        worker.DetectionWorker._save_loadout_look(stub, frame, "menu")
    worker.DetectionWorker._save_loadout_look(stub, frame, "hud")
    files = sorted(os.listdir(tmp_path / "debug" / "loadouts"))
    assert sum(f.endswith("-menu.webp") for f in files) == worker.LOADOUT_KEPT    # 1.57.24: lossless WebP
    hud = [f for f in files if f.endswith("-hud.webp")]
    menu = cv2.imread(str(tmp_path / "debug" / "loadouts" / files[0]))
    assert len(hud) == 1 and menu.shape[:2] == (1440, 2560 * 3 // 5)
    assert cv2.imread(str(tmp_path / "debug" / "loadouts" / hud[0])).shape[:2] == (1440, 2560 * 2 // 5)


def test_debug_pictures_are_lossless_webp_and_old_pngs_go_with_them(tmp_path):
    """1.57.24 (user: "Speichere die Debug-Bilder künftig als WebP" – a ZIP of the looks ran over 30 MB): the same
    pixels as before, as lossless WebP; the PNGs of an older version count towards LOADOUT_KEPT and are cleaned up."""
    from types import SimpleNamespace
    from fogscout import worker
    rng = np.random.default_rng(3)
    pic = rng.integers(0, 256, (90, 160, 3), dtype=np.uint8)
    worker.write_lossless(str(tmp_path / "a.webp"), pic)
    worker.write_lossless(str(tmp_path / "b.webp"), np.dstack([pic, np.full(pic.shape[:2], 255, np.uint8)]))
    worker.write_lossless(str(tmp_path / "c.webp"), pic[:, :, 0])
    assert np.array_equal(cv2.imread(str(tmp_path / "a.webp")), pic)
    assert np.array_equal(cv2.imread(str(tmp_path / "b.webp")), pic)
    assert np.array_equal(cv2.imread(str(tmp_path / "c.webp"), cv2.IMREAD_GRAYSCALE), pic[:, :, 0])
    d = tmp_path / "debug" / "loadouts"
    d.mkdir(parents=True)
    for i in range(3):
        (d / f"20200101-00000{i}-000-menu.png").write_bytes(b"old")
    stub = SimpleNamespace(data_dir=str(tmp_path))
    for _ in range(worker.LOADOUT_KEPT):
        worker.DetectionWorker._save_loadout_look(stub, np.zeros((1440, 3440, 3), np.uint8), "menu")
    files = sorted(os.listdir(d))
    assert len(files) == worker.LOADOUT_KEPT and all(f.endswith("-menu.webp") for f in files)


def test_the_menus_own_slot_pictures_are_cut_and_drawn_beside_the_survivor(reader):
    """1.57.25 (user: "Könnten wir bei der Perk-Erkennung nicht eine 2. Variante machen, dass wir einen Screenshot vom
    Menü nehmen, diesen verkleinern und dessen Survivor zuteilen?" – "gerne, die alte Variante soll drin bleiben"):
    each row keeps its eight slots as the menu showed them; Votes keeps them with the survivor, and with
    ``loadouts_look`` "picture" (the default) they are drawn instead of the icons of the names read – a slot read
    wrongly or not at all looks as in the game. "icons" draws as before."""
    from fogscout.app_loadouts import look_of, placed
    board = reader.read(_crop_frame("real_menu_two_empty.webp", True))
    jonah = board.rows[1]
    assert len(jonah.pics) == 8 and all(p is not None and p.shape == (loadouts.TILE, loadouts.TILE, 4)
                                        for p in jonah.pics)
    perk = jonah.pics[3]
    assert perk[0, 0, 3] == 0 and perk[loadouts.TILE // 2, loadouts.TILE // 2, 3] == 255     # the diamond cut free
    votes = Votes()
    votes.note(board)
    first = votes.board()
    assert first.rows[1].pics is jonah.pics and first.rows[1].pics_n > 0
    votes.note(board)
    assert votes.board().key() != first.key()             # pictures of a newer look redraw the card
    shown = Board(rows=tuple(dataclasses.replace(r, hud=(0.18, 0.5, 0.05)) for r in votes.board().rows))
    o = {"loadouts_pos": "hud", "margin": 0.012, "loadouts_items": True}
    assert look_of(o) == "picture" and look_of(dict(o, loadouts_look="icons")) == "icons"
    pic = placed(o, (0, 0, 3440, 1440), shown)[0]
    icons = placed(dict(o, loadouts_look="icons"), (0, 0, 3440, 1440), shown)[0]
    assert pic.size == icons.size and np.asarray(pic).tobytes() != np.asarray(icons).tobytes()
    blank = Board(rows=tuple(dataclasses.replace(r, pics=tuple(None for _ in range(8))) for r in shown.rows))
    assert placed(o, (0, 0, 3440, 1440), blank) is not None              # a slot without a picture: the old way


def test_nobody_takes_the_own_top_row():
    """User (1.57.11, a match with real players): the own portrait was hurt and not found – a teammate was found at
    the own, top row and its perks drawn there. With the own (gold) survivor known, the others count only below its
    place; unknown, nobody is placed. The own place is kept for the next rounds (the HUD stays put)."""
    faces = [np.zeros((loadouts.FACE, loadouts.FACE), np.uint8) for _ in range(3)]
    for i, f in enumerate(faces):
        f[i * 8:(i + 1) * 8, :] = 200
    board = Board(rows=(Row(own=True, face=faces[0]),) + tuple(
        Row(perks=(f"P{i}", None, None, None), face=f) for i, f in enumerate(faces[1:], 1)), pitch=40)
    top, second, third = (0.18, 0.418, 0.05), (0.18, 0.50, 0.05), (0.18, 0.582, 0.05)
    v = Votes()
    v.note(board)
    for _ in range(2):
        v.place({1: top, 2: third})                              # the own one not found: 1 sits on its row
    assert all(r.hud is None for r in v.board().rows)
    for _ in range(2):
        v.place({0: top, 1: second, 2: third})                   # the own one found: all placed
    assert v.placed
    v.reset()                                                    # next round: the own portrait hurt, not found
    v.note(board)
    for _ in range(2):
        v.place({1: top, 2: third})
    rows = {r.who: r.hud for r in v.board().rows}
    assert rows[1] is None and rows[2] == third                  # not on the remembered own row; below it fine


def _crop_frame(name, menu):
    """The worker's debug crops (1.57.11) back in a 3440×1440 picture: the menu's middle 3/5, the HUD's left 2/5."""
    crop = cv2.imread(os.path.join(DATA, name))
    frame = np.zeros((1440, 3440, 3), np.uint8)
    x = 440 + 512 if menu else 440
    frame[:, x:x + crop.shape[1]] = crop
    return frame


def test_a_real_match_with_hooked_and_hurt_teammates():
    """User (1.57.12, debug pictures of a real match at full size): the menu reads every slot, but in the HUD the own
    portrait is a hook, Jake's a hook, A2's marked red – only one portrait as it is (Hyper's Dwight, the own one's
    twin). 1.57.11 placed none (it needed two portraits on a grid in one look and the own one) and gave up after 40
    looks. DBD's list is where it always is: the own row is its top without being found, every portrait found on a
    row below counts alone, the last one by elimination – and the own Dwight never swaps with the other."""
    reader = loadouts.Reader()
    board = reader.read(_crop_frame("real_menu_crop.webp", True))
    assert [r.perks for r in board.rows] == [
        ("Fixated", "We're Gonna Live Forever", "For the People", "Dead Hard"),
        ("Adrenaline", "Sprint Burst", "Windows of Opportunity", "Decisive Strike"),
        ("Prove Thyself", "Windows of Opportunity", "Sprint Burst", "Adrenaline"),
        ("Déjà Vu", "Lithe", "Resilience", "Five Moves Ahead")]
    assert board.rows[0].own and not any(r.own for r in board.rows[1:])
    v = Votes()
    for _ in range(3):
        v.note(reader.read(_crop_frame("real_menu_crop.webp", True)))
    assert [r.own for r in v.board().rows] == [True, False, False, False]      # the gold Dwight stays the own one
    grid = loadouts.list_grid(3440, 1440)
    for name in ("real_hud_crop_1.jpg", "real_hud_crop_2.jpg") * 2:
        hud = _crop_frame(name, False)
        v.place(loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440)), grid)
    assert v.placed
    rows = {r.perks[0]: round(r.hud[1] * 1440) for r in v.board().rows}
    assert rows == {"Fixated": 608, "Déjà Vu": 726, "Adrenaline": 844, "Prove Thyself": 962}


def test_off_the_usual_list_the_found_grid_decides():
    """Another HUD size: nothing found fits DBD's usual list – the grid of the portraits found decides as before."""
    faces = [np.zeros((loadouts.FACE, loadouts.FACE), np.uint8) for _ in range(3)]
    for i, f in enumerate(faces):
        f[i * 8:(i + 1) * 8, :] = 200
    v = Votes()
    v.note(Board(rows=tuple(Row(perks=(f"P{i}", None, None, None), face=f) for i, f in enumerate(faces)), pitch=40))
    grid = loadouts.list_grid(3440, 1440)
    big = {0: (0.18, 0.30, 0.08), 1: (0.18, 0.43, 0.08), 2: (0.18, 0.56, 0.08)}   # a larger HUD: other rows, sides
    assert v.place_on_list(big, grid) is None
    for _ in range(2):
        v.place(big, grid)
    assert v.placed


def test_two_survivors_with_the_same_look_are_never_guessed():
    """User (1.57.13, real match: two Kate Densons in one skin – Diet Coke and Unlucky Juls – and Vittorio hooked
    all the time): two portraits alike (0.97–1.00; others ≤ 0.55) can't be told apart in the HUD – 1.57.12 put one
    Kate's perks at the other. Now neither is placed by a portrait (unless their loadouts are the same), each keeps
    its own perks from the menu (its row there), and their two rows still leave the last row to Vittorio."""
    reader = loadouts.Reader()
    v = Votes()
    for _ in range(3):
        v.note(reader.read(_crop_frame("real_menu_twins.webp", True)))
    rows = v.board().rows
    assert [r.perks[:2] for r in rows] == [("Fixated", "We're Gonna Live Forever"), ("Déjà Vu", "Five Moves Ahead"),
                                           ("Lithe", "Decisive Strike"), ("Déjà Vu", "Iron Will")]
    assert v.twins() == {1, 3}
    grid = loadouts.list_grid(3440, 1440)
    for name in ("real_hud_twins_1.jpg", "real_hud_twins_2.jpg") * 2:
        hud = _crop_frame(name, False)
        v.place(loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440)), grid)
    placed = {r.perks[1]: (round(r.hud[1] * 1440) if r.hud else None) for r in v.board().rows}
    assert placed == {"We're Gonna Live Forever": 608, "Five Moves Ahead": None, "Decisive Strike": 962,
                      "Iron Will": None}


def test_two_alike_survivors_whose_pictures_differ_are_twins_even_when_nothing_is_read():
    """User (1.57.25, after the slots are drawn as the menu's pictures: "Was wenn mehrere gleiche Survivor in der
    Runde sind"): twins were told apart only by the names read – two Kates whose perks were read alike (none, or the
    same misreading) were placed by their portraits and one Kate's pictures could stand at the other. Now their slot
    pictures of one look decide too (one grid for all rows of a look: the same loadout ≤ 11, other loadouts 58–93
    at 8 px); the same pictures still let either place be right."""
    reader = loadouts.Reader()
    board = reader.read(_crop_frame("real_menu_twins.webp", True))
    unread = Board(rows=tuple(dataclasses.replace(r, perks=(None,) * 4, item=None, addons=(None, None), offering=None)
                              for r in board.rows), pitch=board.pitch)
    v = Votes()
    for _ in range(2):
        v.note(unread)
    assert v.twins() == {1, 3}
    kates = list(unread.rows)
    kates[3] = dataclasses.replace(kates[3], pics=kates[1].pics)            # both Kates bring the same
    same = Votes()
    for _ in range(2):
        same.note(Board(rows=tuple(kates), pitch=board.pitch))
    assert same.twins() == set()
    blind = Votes()                                                        # no pictures: as before 1.57.26
    for _ in range(2):
        blind.note(Board(rows=tuple(dataclasses.replace(r, pics=()) for r in unread.rows), pitch=board.pitch))
    assert blind.twins() == set()


def test_an_obsession_bracket_does_not_hide_that_two_survivors_look_the_same():
    """User (1.57.26, a custom game with four Claudettes in one skin: "hier wurde den falschen Survivors die Perks
    zugeteilt"; "Die Klammer bedeutet Obsession und dies kann immer anders sein"): one bot Claudette was the
    Obsession – DBD's brackets "( )" around her portrait made it 0.70 like the other by ``same_face``, so the two were
    no twins, and HudFinder (which compares only the round middle – 0.98–1.00 there) put each one's perks one row
    too low. Now twins are decided by the round middle (``hud_alike``): neither is placed by a portrait, nothing is
    drawn at a wrong survivor. Player names painted over."""
    reader = loadouts.Reader()
    menu = reader.read(_crop_frame("real_menu_claudettes.webp", True))
    assert [r.own for r in menu.rows] == [True, False, False]          # the bot without anything is no row
    faces = [r.face for r in menu.rows]
    assert loadouts.same_face(faces[1], faces[2]) < loadouts.TWIN_FACE <= loadouts.hud_alike(faces[1], faces[2])
    v = Votes()
    for _ in range(2):
        v.note(menu)
    assert v.twins() == {1, 2}
    hud = _crop_frame("real_hud_claudettes.jpg", False)
    grid = loadouts.list_grid(3440, 1440)
    for look in range(4):
        v.place(loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440)), grid)
        miss = v.missing() if look >= 1 else None
        if miss:
            v.place_last(miss[0], {c: loadouts.score_at(hud, v.faces().get(miss[0]), c) for c in miss[1]})
    rows = v.board().rows
    assert rows[0].own and rows[0].hud is not None
    assert rows[1].hud is None and rows[2].hud is None              # never at the other Claudette's row


def test_alike_survivors_are_told_apart_by_the_names_below_them():
    """User (1.57.28: "Erkläre mir, wie du unterscheidest, zu wem das gehört, wenn alle 4 Porträts gleich aussehen" –
    "Weshalb sollte das mit dem Namen ein Problem sein? Wir laden dies ja nirgends hoch" – "ja, setz das so um"):
    for portraits the HUD can't tell apart the worker reads the menu row's line and the name below each free HUD
    portrait (OCR, only there, only in memory) – each Claudette goes to the row whose name stands in her line
    ("Claudette Morel_02" in the HUD, "… Claudette Morel_02 0 ms BOT" in the menu; O/0, I/l/1 alike). Only the own
    player name is painted over in these pictures (the bots' names are DBD's)."""
    from fogscout.ocr import Recognizer
    rec = Recognizer(os.path.join(ROOT, "models", "ch_PP-OCRv4_rec_infer.onnx"))
    text = lambda img: rec.text(rec.probs(img))                          # noqa: E731
    reader = loadouts.Reader()
    menu = reader.read(_crop_frame("real_menu_claudettes.webp", True), text=text)
    assert [bool(r.line) for r in menu.rows] == [False, True, True]       # the own row and lone faces: never read
    assert "02" in loadouts.fold_name(menu.rows[1].line) and "01" in loadouts.fold_name(menu.rows[2].line)
    assert not reader.read(_crop_frame("real_menu_claudettes.webp", True)).rows[1].line     # no OCR: no names
    v = Votes()
    for _ in range(2):
        v.note(menu)
    hud = _crop_frame("real_hud_claudettes.jpg", False)
    grid = loadouts.list_grid(3440, 1440)
    gx, gy, step, side = grid
    for _ in range(3):
        v.place(loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440)), grid)
        rows = v.name_rows(grid)
        read = {k: text(loadouts.name_box(hud, loadouts.hud_name_box((gx, gy + k * step, side), 3440, 1440)))
                for k in rows}
        v.place_by_names(read, grid)
    at = {r.perks[0]: round((r.hud[1] - gy) / step) if r.hud else None for r in v.board().rows}
    assert at == {"Empathy": 0, "Déjà Vu": 2, "Kindred": 1}             # _02 third in the HUD, _01 second
    assert v.name_rows(grid) == []                                      # all placed: no more reading
    assert loadouts.name_cost("Claudette Morel o2EeT", "CLAUDETTE MOREL Claudette Morel O1 Oms BOT") > \
        loadouts.name_cost("Claudette Morel o2EeT", "CLAUDETTE MOREL Claudette Morel O2 Oms BOT")


def test_a_menu_a_pixel_further_is_read_on_the_same_grid():
    """User (1.57.26: "untersuche den 1-Pixel-Raster-Fehler"): the coarse search (at half size) found the first perk
    column 7–9 px too far right – one pixel more and no first perk was hit: the second column became "perk 1" and
    every slot was read one place too far right; and the grey person icon of each row's header (read as "This Is
    Not Happening" at a smaller size) won the size choice at every odd offset. Now a clearly read column left of
    the grid moves it there, and a hit needs a coloured diamond (``PERK_COLOUR``) – measured on five real menus
    shifted 1–3 px: 32.2 % → 1.5 % of the slots read otherwise, 7 → 0 boards lost."""
    reader = loadouts.Reader()
    for name, first in (("real_menu_twins.webp", ("Fixated", "We're Gonna Live Forever")),
                        ("real_menu_two_empty.webp", ("Iron Will", None))):
        frame = _crop_frame(name, True)
        for dx in (0, 1, 2, 3):
            board = reader.read(np.roll(frame, dx, axis=1))
            assert board.rows[0].perks[:2] == first, (name, dx)
            assert not any("This Is Not Happening" in r.perks for r in board.rows), (name, dx)
    icon = _crop_frame("real_menu_two_empty.webp", True)
    assert loadouts._coloured(icon, 1434, 424, 52) < loadouts.PERK_COLOUR    # a bot row header's person icon
    assert loadouts._coloured(icon, 1434, 340, 64) >= loadouts.PERK_COLOUR   # the own Iron Will below it


def test_alike_survivors_are_told_apart_even_when_their_names_are_misread():
    """User (1.57.30, a custom game with three "Thalita Lyra" bots, one empty, ZIP of the looks): the menu's lines
    were read "THAUTA LYRA Thalita Lyra_03 …" – one misread letter broke 1.57.29's longest common run and nobody was
    placed in 56 HUD looks. Now the twins get the free rows all at once by the fewest changes for each HUD name to
    stand in a menu line (``name_cost``; here 1 for the right row, 2 for the other). Only the own name is painted
    over (the bots' names are DBD's)."""
    from fogscout.ocr import Recognizer
    rec = Recognizer(os.path.join(ROOT, "models", "ch_PP-OCRv4_rec_infer.onnx"))
    text = lambda img: rec.text(rec.probs(img))                          # noqa: E731
    menu = loadouts.Reader().read(_crop_frame("real_menu_thalitas.webp", True), text=text)
    v = Votes()
    for _ in range(2):
        v.note(menu)
    assert v.twins() == {1, 2}
    hud = _crop_frame("real_hud_thalitas.jpg", False)
    grid = loadouts.list_grid(3440, 1440)
    gx, gy, step, side = grid
    for _ in range(3):
        v.place(loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440)), grid)
        rows = v.name_rows(grid)
        v.place_by_names({k: text(loadouts.name_box(hud, loadouts.hud_name_box((gx, gy + k * step, side), 3440,
                                                                                1440))) for k in rows}, grid)
    at = {r.perks[0]: round((r.hud[1] - gy) / step) if r.hud else None for r in v.board().rows}
    assert at == {"Empathy": 0, "Déjà Vu": 1, "Kindred": 2}             # Lyra_02 second in the HUD, Lyra_03 third
    assert loadouts.name_cost("Thalita Lyra_O2BT", "THAUTA LYRA Thalita Lyra O2 Oms BOT") == 0
    assert loadouts.name_cost("Thalita Lyra_O2BOT", "THAUTA LYRA Thalita Lyra O3 Oms BOT") == 1


@pytest.mark.parametrize("before, after", [(1.0, 0.8), (0.8, 1.2), (1.2, 0.8), (1.0, 1.0)])
def test_the_last_diamond_size_is_tried_first_and_a_new_ui_size_still_found(menu, before, after):
    """1.57.32 (user: "Weiter mit Optimierungen"; a look took 625 ms on average): the reader tries the last board's
    diamond size and its neighbours first (533 → 317 ms per menu look on the user's menus) – when DBD's UI size was
    changed meanwhile the size found lies at that window's edge and all sizes are tried, the board the same as a
    fresh reader's."""
    def scaled(scale):
        small = cv2.resize(menu, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        frame = np.zeros((1440, 3440, 3), np.uint8)
        h, w = min(1440, small.shape[0]), min(3440, small.shape[1])
        frame[:h, :w] = small[:h, :w]
        return frame
    warm = loadouts.Reader()
    warm.read(scaled(before))
    assert warm._known is not None
    got, fresh = warm.read(scaled(after)), loadouts.Reader().read(scaled(after))
    assert [r.perks for r in got.rows] == [r.perks for r in fresh.rows]
    assert got.size == fresh.size


def test_once_the_list_is_known_only_its_column_is_searched():
    """1.57.32: a HUD look searched 30 % × 68 % of the 16:9 picture (104–148 ms) – once DBD's list was seen at its
    place only places on it count (``place_on_list``), so only its column is searched (``list_box``, 21–28 ms).
    The places on the list are the same as with the whole search."""
    for menu_name, hud_name in (("real_menu_thalitas.webp", "real_hud_thalitas.jpg"),
                                ("real_menu_claudettes.webp", "real_hud_claudettes.jpg"),
                                ("real_menu_twins.webp", "real_hud_twins_2.jpg")):
        v = Votes()
        board = loadouts.Reader().read(_crop_frame(menu_name, True))
        v.note(board)
        v.note(board)
        hud = _crop_frame(hud_name, False)
        grid = loadouts.list_grid(3440, 1440)
        box = loadouts.list_box(grid, 3440, 1440)
        on = lambda found: {k: a for k, a in found.items() if abs(a[0] - grid[0]) <= loadouts.HUD_COL}  # noqa: E731
        whole = loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440))
        column = loadouts.HudFinder().find(hud, v.faces(), v.side, v.scales(1440), box=box)
        assert on(whole) == on(column), hud_name
    assert not v.list_seen
    v.place(column, grid)
    assert v.list_seen


def test_the_next_look_reads_the_last_grid_and_falls_back_when_the_menu_differs(menu):
    """1.57.33 (user: "Loadout-Erkennung weiter optimieren"): DBD draws the menu at the same pixels every time – the
    next look reads the last board's grid directly, without searching diamonds and perks (510 → 127 ms per look on
    the user's menus), the board the same. Another UI size, the menu elsewhere or no menu: the search as before."""
    key = lambda b: [(r.own, r.perks, r.item, r.addons, r.offering) for r in b.rows] if b else None  # noqa: E731
    for name in ("real_menu_twins.webp", "real_menu_thalitas.webp", "real_menu_two_empty.webp"):
        frame = _crop_frame(name, True)
        reader = loadouts.Reader()
        first = reader.read(frame)
        again = reader.read(frame)
        assert key(again) == key(first) and "Raster wie zuvor" in reader.last, name

    def placed(scale, dx=0, dy=0):
        small = cv2.resize(menu, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        frame = np.zeros((1440, 3440, 3), np.uint8)
        h, w = min(1440 - dy, small.shape[0]), min(3440 - dx, small.shape[1])
        frame[dy:dy + h, dx:dx + w] = small[:h, :w]
        return frame
    for other in (placed(0.8), placed(1.2), placed(1.0, dx=300, dy=60)):
        reader = loadouts.Reader()
        reader.read(placed(1.0))
        got = reader.read(other)
        assert key(got) == key(loadouts.Reader().read(other)) and "Raster wie zuvor" not in reader.last
    reader = loadouts.Reader()
    reader.read(placed(1.0))
    assert reader.read(_crop_frame("real_hud_thalitas.jpg", False)) is None


def test_one_short_look_at_the_menu_is_enough():
    """User (1.57.14, a real match: the menu open twice for a moment – once under an add-on's tooltip, once just
    before the end – nothing shown): every strict read counts after one look (none ever differed between looks on
    the user's real menus), so one look gives (nearly) every perk; the HUD's size is taken from DBD's usual list
    before any portrait is found (three sizes, not nine)."""
    reader = loadouts.Reader()
    v = Votes()
    v.note(reader.read(_crop_frame("real_menu_crop.webp", True)))
    assert sum(1 for r in v.board().rows for p in r.perks if p) >= 15
    assert len(v.scales(1440)) == 3
    from fogscout import worker
    assert worker.LOADOUT_INTERVAL <= 0.5


def test_the_map_read_again_at_the_start_keeps_the_loadouts():
    """User (1.57.14): "Ich öffne oft das Menü, wenn ich in die Runde lade" – the banner is read twice at the start
    (23:02:37 and 23:02:41 in the diagnosis); each shown map was a new generation and threw the loadouts read in
    between away. Shown again early in a round not ended: the same round."""
    from fogscout.worker import LOADOUT_SAME_ROUND_S, same_round_again
    assert same_round_again((2, "auto"), (1, "auto"), False, 4.0)
    assert same_round_again((2, "manual"), (1, "auto"), False, 60.0)               # a layout picked early
    assert not same_round_again((2, "auto"), (1, "auto"), True, 4.0)               # after the round's end
    assert not same_round_again((2, "auto"), (1, "auto"), False, LOADOUT_SAME_ROUND_S + 1)   # a new round
    assert not same_round_again((2, "auto"), None, False, 4.0)                     # the first map
    assert not same_round_again(None, (1, "auto"), False, 4.0)


def test_the_whole_way_with_the_real_loop(tmp_path, monkeypatch):
    """User (1.57.14): "Sobald die Karte anzeigt, öffne ich das Menü" – the real worker loop with a fake screen: the
    map on display, the menu open (pointer visible) right away, the map shown a second time meanwhile (the banner
    read twice at the start), the menu shut, the HUD (three of four portraits an icon or marked red) – every
    survivor ends at its row, the board posted for the map now on display."""
    pytest.importorskip("onnxruntime")
    import queue
    import time
    from types import SimpleNamespace
    from fogscout import config, worker
    from fogscout.catalog import Catalog
    W, H = 3440, 1440
    menu = _crop_frame("real_menu_crop.webp", True)
    huds = [_crop_frame(n, False) for n in ("real_hud_crop_1.jpg", "real_hud_crop_2.jpg")]
    screen = {"frame": menu, "pointer": True, "n": 0}

    class Grabber:
        def grab(self, left, top, width, height):
            frame = screen["frame"]
            if frame is not menu:                                  # the HUD changes a little from look to look
                screen["n"] += 1
                frame = huds[screen["n"] % 2]
            return frame[top:top + height, left:left + width].copy()

        def primary_monitor(self):
            return 0, 0, W, H

        def close(self):
            pass

    game = SimpleNamespace(hwnd=1, left=0, top=0, width=W, height=H, minimized=False)
    monkeypatch.setattr(worker, "ScreenGrabber", Grabber)
    monkeypatch.setattr(worker, "find_game_window", lambda *a, **k: game)
    monkeypatch.setattr(worker, "foreground_root", lambda: 1)
    monkeypatch.setattr(worker, "cursor_state", lambda: (screen["pointer"], 1720, 720))
    events = queue.Queue()
    wk = worker.DetectionWorker(ROOT, config.Settings(str(tmp_path / "settings.json")), Catalog(ROOT, ["en"]),
                                events, data_dir=str(tmp_path))
    wk.watch_gen, wk.map_on_screen, wk.loadouts_wanted = (1, "auto"), True, True
    last = {}

    def wait(test, seconds=60):
        deadline = time.time() + seconds                          # generous: shared CI runners
        while time.time() < deadline:
            try:
                ev = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if ev.kind == "loadouts":
                last.update(gen=ev.data["gen"], board=ev.data["board"])
                if test():
                    return True
        return False

    wk.start()
    try:
        # the menu read – a second look adds A2's Déjà Vu (an eye close to others: two agreeing reads; at a look
        # every LOADOUT_INTERVAL the menu open about a second)
        assert wait(lambda: sum(1 for r in last["board"].rows for p in r.perks if p) == 16)
        screen["frame"], screen["pointer"] = huds[0], False        # the menu shut: the HUD …
        wk.watch_gen = (2, "auto")                                 # … and the banner read a second time
        assert wait(lambda: last["gen"] == (2, "auto"))           # the same round: the board stays
        assert sum(1 for r in last["board"].rows for p in r.perks if p) >= 15
        assert wait(lambda: all(r.hud for r in last["board"].rows))
    finally:
        wk.stop()
        wk.join(timeout=10)
    rows = {r.perks[0]: round(r.hud[1] * H) for r in last["board"].rows}
    assert rows == {"Fixated": 608, "Déjà Vu": 726, "Adrenaline": 844, "Prove Thyself": 962}
    assert last["gen"] == (2, "auto")


def test_a_controller_menu_without_a_pointer_is_read_by_its_quit(tmp_path, monkeypatch):
    """User (1.57.20): "Muss die Maus sichtbar sein? Ich spiele meist mit Controller, da kommt nur so ein Kreis" –
    with a controller the Windows pointer stays hidden, the menu was never read. The round-end check reads the pause
    menu's "QUIT" bottom right anyway: that counts as the menu open too (MENU_QUIT_HOLD_S), the pointer stays None."""
    pytest.importorskip("onnxruntime")
    import queue
    import time
    from types import SimpleNamespace
    from fogscout import config, detector, worker
    from fogscout.catalog import Catalog
    W, H = 3440, 1440
    menu = _crop_frame("real_menu_crop.webp", True)
    screen = {"menu": True}

    class Grabber:
        def grab(self, left, top, width, height):
            return menu[top:top + height, left:left + width].copy()

        def primary_monitor(self):
            return 0, 0, W, H

        def close(self):
            pass

    real_observe = detector.OutOfMatchWatcher.observe

    def observe(self, frame, ignore=None):                     # the menu's "QUIT" as the OCR reads it
        ob = real_observe(self, frame, ignore)
        if screen["menu"]:
            ob.continue_fit, ob.continue_text = -70.0, "QUIT"
        return ob
    game = SimpleNamespace(hwnd=1, left=0, top=0, width=W, height=H, minimized=False)
    monkeypatch.setattr(worker, "ScreenGrabber", Grabber)
    monkeypatch.setattr(worker, "find_game_window", lambda *a, **k: game)
    monkeypatch.setattr(worker, "foreground_root", lambda: 1)
    monkeypatch.setattr(worker, "cursor_state", lambda: (False, 1720, 720))      # a controller: no pointer
    monkeypatch.setattr(detector.OutOfMatchWatcher, "observe", observe)
    events = queue.Queue()
    wk = worker.DetectionWorker(ROOT, config.Settings(str(tmp_path / "settings.json")), Catalog(ROOT, ["en"]),
                                events, data_dir=str(tmp_path))
    wk.watch_gen, wk.map_on_screen, wk.loadouts_wanted = (1, "auto"), True, True
    board = None
    wk.start()
    try:
        deadline = time.time() + 60                              # generous: shared CI runners
        while time.time() < deadline and board is None:
            try:
                ev = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if ev.kind == "loadouts":
                board = ev.data["board"]
        assert board is not None and wk.menu_open                 # read, and the loadouts hidden meanwhile
        assert sum(1 for r in board.rows for p in r.perks if p) >= 12
    finally:
        wk.stop()
        wk.join(timeout=10)


def test_the_killers_row_is_left_out_even_with_an_offering(reader):
    """User (1.57.20, public match: The Pig had a hidden offering): the killer's row was read as a fifth survivor
    with only that offering and drawn over the own row. _strip averaged the pixels' hues – red lies at 0 and 179,
    the killer's row came out at hue 10–37 and was never red; now the mean colour is converted (hue 0, saturation
    240 on every menu), the own gold row stays no killer's."""
    assert loadouts._red((0, 240, 70)) and not loadouts._red((24, 115, 57))   # killer / own gold row
    assert not loadouts._red((97, 56, 35)) and not loadouts._red(None)
    menu = _crop_frame("real_menu_two_empty.webp", True)
    ys = []
    real = loadouts._strip

    def strip(frame, x0, x1, y, half, colour=False):
        v = real(frame, x0, x1, y, half, colour)
        if colour and loadouts._red(v):
            ys.append(y)
        return v
    loadouts._strip = strip
    try:
        board = loadouts.Reader().read(menu)
    finally:
        loadouts._strip = real
    assert len(ys) == 1 and ys[0] > 900                               # the red row below the four survivors
    assert len(board.rows) == 2                                       # and still only the survivors read


# ------------------------------------------------------------------ 1.57.36: the killer sees the survivors' offerings
KILLER_OFFERINGS = ["Fresh Bog Laurel", loadouts.HIDDEN_OFFERING, "Toothy Torte", "Escape! Cake"]


def test_the_killers_menu_gives_the_survivors_offerings():
    """User: "Ich meine die Offerings der Survivor. Die sieht man als killer im spiel" – the killer's menu has no
    survivor perk (the own red row holds the killer's, unknown to the reader: "kein Raster" before); its diamonds
    find the grid, the four survivors' rows above give their offerings and portraits, at any size."""
    for size in ((3440, 1440), (2560, 1071), None):
        reader = loadouts.Reader()
        board = reader.read(_load("real_menu_killer.webp", size))
        assert board is not None and board.killer, reader.last
        assert [r.offering for r in board.rows] == KILLER_OFFERINGS
        assert all(r.face is not None and not r.own and not any(r.perks) and r.item is None for r in board.rows)
        assert all(r.pics[:7] == (None,) * 7 and r.pics[7] is not None for r in board.rows)   # the hexagon only
    assert not loadouts.Reader().read(_load("real_menu_toothy_torte.webp")).killer          # a survivor's menu


def test_as_the_killer_all_four_rows_of_the_list_are_survivors():
    """The killer's HUD lists the four survivors where a survivor sees the own row and the three below (the
    user's killer HUD: its portraits found exactly on DBD's list, rows 0–3); no survivor is "the own one", the
    top row is placed like the others and the last one follows by elimination."""
    hud = _load("real_hud_killer.jpg")
    h, w = hud.shape[:2]
    grid = loadouts.list_grid(w, h)
    gx, gy, step, side = grid
    faces = {k: loadouts._face(hud, gx * w, (gy + k * step) * h, side * h * loadouts.PORTRAIT) for k in range(4)}
    found = loadouts.HudFinder().find(hud, faces, side * h, (1.0,))
    assert sorted(round((a[1] - gy) / step) for a in found.values()) == [0, 1, 2, 3]
    votes = loadouts.Votes()
    rows = tuple(Row(offering=name, face=faces[k]) for k, name in enumerate(KILLER_OFFERINGS))
    for _ in range(2):
        votes.note(Board(rows=rows, killer=True))
    seen = {k: a for k, a in found.items() if k != 3}                  # the last one hooked all the time
    votes.place(seen, grid)
    votes.place(seen, grid)
    board = votes.board()
    assert board.killer and votes.placed and len(board.others) == 4
    assert {r.offering: round((r.hud[1] - gy) / step) for r in board.rows} == dict(zip(KILLER_OFFERINGS, range(4)))


def test_as_the_killer_only_the_offerings_are_drawn():
    from fogscout import config
    from fogscout.app_loadouts import placed
    o = dict(config.DEFAULTS["overlay"], show_loadouts=True, loadouts_look="icons")
    grid = loadouts.list_grid(3440, 1440)
    rows = tuple(Row(offering=name, who=k, hud=(grid[0], grid[1] + k * grid[2], grid[3]))
                 for k, name in enumerate(KILLER_OFFERINGS[:3] + [None]))
    killer = placed(o, (0, 0, 3440, 1440), Board(rows=rows, killer=True))
    survivor = placed(o, (0, 0, 3440, 1440), Board(rows=rows))
    assert killer is not None and survivor is not None
    assert killer[0].width < 0.6 * survivor[0].width                  # a hexagon, no perk diamond beside it
    a = np.asarray(killer[0])
    centres = [int((grid[1] + k * grid[2]) * 1440 - killer[2]) for k in range(4)]
    assert all((a[c, :, 3] > 0).any() for c in centres[:3])           # a hexagon beside each of the first three
    assert a.shape[0] <= centres[3]                                   # a survivor without an offering: nothing

