"""1.57.64 (user: "den Kreis mit den Symbolen wie im Spiel … gefällt mir alles, nur die Logos näher ans Spiel"): the
counted points as rings, bars or a line, with own icons."""
import numpy as np

from fogscout import scoreview as sv
from fogscout.overlay_render import info_card
from fogscout.scoreevents import CATEGORIES

KILLER = {"brutality": 4300, "deviousness": 1450, "hunter": 8260, "sacrifice": 10000}


def _has(im, colour, tol=40):
    a = np.asarray(im.convert("RGBA")).astype(int)
    near = (np.abs(a[:, :, :3] - np.array(colour[:3])).sum(axis=2) < tol) & (a[:, :, 3] > 200)
    return int(near.sum())


def test_every_category_has_its_own_icon():
    pics = {c: np.asarray(sv.icon(c, 48))[:, :, 3] for c in CATEGORIES}
    assert all(p.max() > 200 and (p > 128).mean() > 0.1 for p in pics.values())
    shapes = [p.tobytes() for p in pics.values()]
    assert len(set(shapes)) == len(CATEGORIES)


def test_a_new_value_never_resizes_any_look():
    for style in sv.STYLES:
        sizes = {sv.picture(sv.items(t), style, 1.0).size
                 for t in ({c: 0 for c in KILLER}, {c: 9999 for c in KILLER}, KILLER, {c: 10000 for c in KILLER})}
        assert len(sizes) == 1, (style, sizes)


def test_the_arc_shows_how_full_a_category_is_and_a_full_one_is_gold():
    empty = sv.picture(sv.items({"hunter": 100}), "rings", 1.0)
    half = sv.picture(sv.items({"hunter": 5000}), "rings", 1.0)
    full = sv.picture(sv.items({"hunter": 10000}), "rings", 1.0)
    assert _has(half, sv.RED) > 3 * _has(empty, sv.RED)
    assert _has(full, sv.GOLD) > 50 and _has(full, sv.RED) == 0


def test_the_overlay_value_keeps_the_text_and_falls_back_to_rings():
    v = sv.for_overlay(KILLER, (), "nonsense")
    assert v[0].startswith("BRU 4.3k") and v[3] == "rings" and v[2][3] == ("sacrifice", 10000, True)
    assert sv.for_overlay({}, (), "bars") == ()
    assert sv.of(v[:2]) is None and sv.of(v).size == sv.picture(v[2], "rings").size


def test_the_info_card_shows_the_picture_in_every_style():
    for skin in ("classic", "glass"):
        text = info_card("3:27", "", None, "", "", 200, skin, score=sv.for_overlay(KILLER, (), "line")[:2])
        for style in sv.STYLES:
            card = info_card("3:27", "", None, "", "", 200, skin, score=sv.for_overlay(KILLER, (), style))
            assert _has(card, sv.GOLD) > 5, (skin, style)                  # the full category, gold
            if style != "line":
                assert card.height > text.height, (skin, style)
