"""Loadouts from the pause menu (loadouts.py): the survivors' perks, item and add-ons read from the picture only.

``menu_four_rows.png``: the four icon rows of the user's own picture of the menu (names, pings and the killer's
row painted over, the rest of the menu's grey filled in)."""
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
MENU = os.path.join(ROOT, "tests", "data", "loadouts", "menu_four_rows.png")

# what the picture shows – read by eye on the original (a slot the reader may leave open is not listed)
EXPECTED = [
    {0: "Bond", 2: "Botany Knowledge", 3: "Iron Will"},
    {0: "Dead Hard", 1: "Resurgence", 2: "Made for This"},
    {0: "Sprint Burst", 2: "We'll Make It", 3: "Resilience"},
    {0: "Sprint Burst", 2: "Resilience", 4: "Utility Flashlight", 5: "Long Life Battery"},
]


@pytest.fixture(scope="module")
def reader():
    return loadouts.Reader()


@pytest.fixture(scope="module")
def menu():
    pic = cv2.imread(MENU)
    assert pic is not None
    return pic


def _slots(row: Row) -> list:
    return list(row.perks) + [row.item] + list(row.addons)


def _check(board: Board):
    assert board is not None and len(board.rows) == 4
    assert board.rows[0].own and not any(r.own for r in board.rows[1:])
    assert len(board.others) == 3
    for row, want in zip(board.rows, EXPECTED):
        got = _slots(row)
        for slot, name in want.items():
            assert got[slot] == name, (slot, got)


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


def test_the_rows_of_the_users_menu_are_read(reader, menu):
    _check(reader.read(menu))


@pytest.mark.parametrize("scale", [1.5, 1.9])
def test_the_menu_is_found_at_any_size_anywhere_in_a_wide_window(reader, menu, scale):
    """DBD's HUD scale can be set and the menu's place is not known: larger, inside a black 3440×1440 frame."""
    big = cv2.resize(menu, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    frame = np.zeros((1440, 3440, 3), np.uint8)
    frame[30:30 + big.shape[0], 500:500 + big.shape[1]] = big
    _check(reader.read(frame))


def test_a_picture_without_the_menu_gives_nothing(reader):
    for name in os.listdir(os.path.join(ROOT, "tests", "data", "end")):
        pic = cv2.imread(os.path.join(ROOT, "tests", "data", "end", name))
        board = reader.read(pic)
        assert board is None or all(r.empty for r in board.rows), name
    assert reader.read(np.zeros((1440, 3440, 3), np.uint8)) is None
    rng = np.random.default_rng(1)
    assert reader.read(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)) is None


def test_an_unknown_drawing_is_never_given_a_name(reader):
    """A slot whose drawing fits no picture clearly stays open (never the nearest guess)."""
    templ = reader.perks
    blob = np.zeros((1, loadouts.GLYPH * loadouts.GLYPH), np.float32)
    blob[0, ::7] = 1
    assert templ.best(blob)[0] is None
    assert templ.best(np.zeros((0, loadouts.GLYPH ** 2), np.float32))[0] is None


def _row(*perks, own=False, item=None):
    return Row(perks=tuple(perks) + (None,) * (4 - len(perks)), item=item, own=own)


def test_a_slot_counts_after_two_equal_readings_and_a_tie_stays_open():
    v = Votes()
    first = Board(rows=(_row("Bond", own=True), _row("Dead Hard", "Adrenaline")))
    assert v.note(first) is False and v.board().rows[1].perks == (None,) * 4       # one look: nothing yet
    assert v.note(first) is True
    assert v.board().rows[1].perks[:2] == ("Dead Hard", "Adrenaline")
    assert v.board().others[0].perks[0] == "Dead Hard"
    v.note(Board(rows=(_row("Bond", own=True), _row("Dead Hard", "Lithe"))))
    v.note(Board(rows=(_row("Bond", own=True), _row("Dead Hard", "Lithe"))))
    assert v.board().rows[1].perks[1] is None                      # 2 × Adrenaline, 2 × Lithe: open
    v.note(Board(rows=(_row("Bond", own=True), _row("Dead Hard", "Lithe"))))
    assert v.board().rows[1].perks[1] == "Lithe"
    assert v.note(None) is False
    v.reset()
    assert v.board().rows == () and v.looks == 0


# ------------------------------------------------------------------ drawing and place (1.57)
def test_the_card_has_one_size_whatever_was_read_and_skips_empty_rows():
    from fogscout.app_loadouts import SAMPLE, icon_for
    from fogscout.overlay_render import loadout_card, loadout_size
    full = loadout_card(SAMPLE.others, 96, 104, True, icon_for)
    assert full.size == loadout_size(96, 104, 3, True)
    some = loadout_card((Row(perks=("Dead Hard", None, None, None)), None), 96, 104, True, icon_for)
    assert some.size == full.size                                     # never breathes
    alpha = np.asarray(some)[..., 3]
    assert alpha[:96].any() and not alpha[110:].any()                 # rows 2 and 3 empty: nothing drawn there
    assert loadout_card((), 96, 104, False).size == loadout_size(96, 104, 3, False)
    assert loadout_size(96, 104, 3, False)[0] < full.width            # the item squares need room


def test_beside_the_survivor_list_in_the_bar_or_just_inside_a_16_9_window():
    from fogscout import layout
    o = {"loadouts_scale": 1.0}
    cluster, step = layout.loadout_metrics(o, (0, 0, 3440, 1440))
    assert cluster == int(1440 * layout.LOADOUT_CLUSTER) and step == int(1440 * layout.LOADOUT_STEP)
    w, h = 140, cluster + 2 * step
    x, y = layout.loadouts_xy("hud", (0, 0, 3440, 1440), (w, h), 17, cluster)
    assert x + w <= 440 and x > 440 - w - 20                          # in the left bar, at its inner edge
    assert abs(y + cluster / 2 - layout.LOADOUT_TOP * 1440) <= 1
    x, y = layout.loadouts_xy("hud", (0, 0, 2560, 1440), (w, h), 17, cluster)
    assert 0 < x < 20                                                 # no bar: just inside the picture
    x, y = layout.loadouts_xy("custom", (100, 0, 2560, 1440), (w, h), 17, cluster, (0.5, 0.5))
    assert abs(x + w / 2 - (100 + 1280)) <= 1 and abs(y + h / 2 - 720) <= 1
    assert layout.loadout_metrics({"loadouts_scale": 9}, (0, 0, 2560, 1440))[0] == int(1440 * 0.08 * 2)


def test_the_preview_shows_the_sample_beside_the_list():
    from fogscout import config, preview
    from fogscout.app_loadouts import SAMPLE, picture
    o = dict(config.DEFAULTS["overlay"], show_loadouts=True)
    out, _rect = preview.layers(1720, 720, o, "", [], None, None, "", {}, 0.4,
                                loadouts=lambda oo, game: picture(oo, game, SAMPLE))
    names = [n for n, *_ in out]
    assert "loadouts" in names
    _n, pic, x, y = out[names.index("loadouts")]
    assert x + pic.width <= 220                                       # the left bar of 1720 × 720


def test_names_in_any_script_between_the_rows_change_nothing(reader, menu):
    """Saru: player names can be Japanese, Latin, Russian … – the reader never reads them: a row is found by its
    coloured diamonds only, so white text of any script (and any length) between the rows changes nothing."""
    from PIL import Image, ImageDraw
    pic = Image.fromarray(cv2.cvtColor(menu, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pic)
    for y in (100, 200, 302, 405):                     # where the menu writes the names
        d.text((250, y), "ПРИЗРАК_ninja 忍者サバイバー 生存者 xX__Xx", fill=(235, 235, 235))
        d.rectangle((215, y, 240, y + 14), fill=(230, 230, 230))       # a light icon like the menu's head
    _check(reader.read(cv2.cvtColor(np.asarray(pic), cv2.COLOR_RGB2BGR)))
