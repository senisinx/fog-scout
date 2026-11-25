"""1.57.67 (user: "1:1 die DBD-Icons benutzen und nicht die eigenen"): the game's category icons are taken from the
user's own screen (the ring beside every score event), saved in the own cache and drawn in the overlay's rings – the
game's pictures never ship with the program."""
import os

import cv2
import numpy as np
import pytest

from fogscout import scoreevents, scoreicons, scoreview

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "tests", "data", "score")


@pytest.fixture(autouse=True)
def _no_learned_icons_left():
    yield
    scoreview.set_learned({})


def _rows(name):
    part = cv2.imread(os.path.join(DATA, name))
    return part, scoreevents.find_rows(part)


def test_the_icon_inside_the_ring_is_cut_as_a_mask():
    part, rows = _rows("killer-three-rows.webp")
    masks = [scoreevents.icon_picture(part, r) for r in rows]
    assert all(m is not None and m.shape == (96, 96) and m.dtype == np.uint8 for m in masks)
    assert all(0.04 < (m > 128).mean() < 0.6 for m in masks)             # a drawing, not an empty or a full disc
    assert all(m[0, 0] == 0 and m[95, 95] == 0 for m in masks)           # nothing outside the circle (the ring)
    assert len({m.tobytes() for m in masks}) == 3                        # three categories, three drawings
    x0, y0, x1, y1 = rows[0].word
    off = scoreevents.Row(word=(part.shape[1] - (x1 - x0), y0, part.shape[1], y1))
    assert scoreevents.icon_picture(part, off) is None                   # the ring would be outside the picture


def test_the_collector_picks_one_typical_sighting_per_category_once():
    part, rows = _rows("killer-three-rows.webp")
    good = scoreevents.icon_picture(part, rows[0])
    noisy = np.clip(good.astype(int) + np.random.default_rng(1).integers(-25, 25, good.shape), 0, 255).astype(np.uint8)
    other = scoreevents.icon_picture(part, rows[1])                      # an outlier: another drawing
    col = scoreicons.Collector(keep=5)
    assert col.add("hunter", np.zeros((96, 96), np.uint8)) is None       # an empty ring is no sighting
    assert col.add("nonsense", good) is None and col.add("hunter", good[:50]) is None
    got = [col.add("hunter", m) for m in (noisy, other, good, noisy, good)]
    assert got[:4] == [None] * 4 and got[4] is not None
    assert not np.array_equal(got[4], other)                             # the outlier is never the pick
    assert "hunter" in col.done and col.add("hunter", good) is None      # once per category
    assert scoreicons.Collector(done={"hunter"}).add("hunter", good) is None


def test_saved_icons_are_loaded_and_only_our_own_plain_files(tmp_path):
    part, rows = _rows("killer-max.webp")
    mask = scoreevents.icon_picture(part, rows[0])
    path = scoreicons.save(str(tmp_path), "sacrifice", mask)
    assert path.endswith(os.path.join("cache", "score_icons", "sacrifice.png"))
    with pytest.raises(ValueError):
        scoreicons.save(str(tmp_path), "../evil", mask)
    folder = os.path.dirname(path)
    cv2.imwrite(os.path.join(folder, "hunter.png"), np.zeros((40, 40), np.uint8))          # another size: not ours
    with open(os.path.join(folder, "brutality.png"), "wb") as fh:
        fh.write(b"not a picture")
    got = scoreicons.load(str(tmp_path))
    assert list(got) == ["sacrifice"] and got["sacrifice"].size == (96, 96) and got["sacrifice"].mode == "L"
    assert np.array_equal(np.asarray(got["sacrifice"]), mask)
    assert scoreicons.load(str(tmp_path / "missing")) == {}


def test_the_overlay_draws_the_learned_icon_and_every_cache_sees_it(tmp_path):
    totals = {"brutality": 4300, "sacrifice": 10000}
    before = scoreview.for_overlay(totals, (), "rings")
    drawn = scoreview.picture(before[2], "rings", 1.5, scoreview.rev(before)).tobytes()
    part, rows = _rows("killer-max.webp")
    scoreicons.save(str(tmp_path), "sacrifice", scoreevents.icon_picture(part, rows[0]))
    scoreview.set_learned(scoreicons.load(str(tmp_path)))
    after = scoreview.for_overlay(totals, (), "rings")
    assert after != before and after[:4] == before[:4]                   # only the revision: a new picture key
    learned = scoreview.picture(after[2], "rings", 1.5, scoreview.rev(after))
    assert learned.tobytes() != drawn and learned.size == scoreview.picture(before[2], "rings", 1.5).size
    assert scoreview.icon("brutality", 40).tobytes() != scoreview.icon("sacrifice", 40).tobytes()
    scoreview.set_learned({})
    assert scoreview.picture(after[2], "rings", 1.5, scoreview.rev(scoreview.for_overlay(totals))).tobytes() == drawn


def test_the_worker_learns_an_icon_after_enough_sure_looks_and_tells_the_app(tmp_path):
    import types
    from fogscout import worker
    part = cv2.imread(os.path.join(DATA, "killer-max.webp"))
    from fogscout.ocr import Recognizer
    rec = Recognizer(os.path.join(ROOT, "models", "ch_PP-OCRv4_rec_infer.onnx"))
    rows = scoreevents.read_rows(rec, part)
    assert rows[0].category == "sacrifice" and rows[0].ring is not None
    posts = []
    w = types.SimpleNamespace(data_dir=str(tmp_path), _score_icons=None, post=lambda k, **d: posts.append((k, d)),
                              _report=lambda *a: posts.append(("report", a)))
    learn = types.MethodType(worker.DetectionWorker._learn_icons, w)
    for _ in range(scoreicons.KEEP - 1):
        learn(part, rows)
    assert posts == [] and scoreicons.load(str(tmp_path)) == {}
    learn(part, rows)
    learn(part, rows)                                                    # already learned: nothing more
    assert posts == [("score_icon", {"category": "sacrifice"})] and list(scoreicons.load(str(tmp_path))) == ["sacrifice"]
    rows[0].ring = None
    w2 = types.SimpleNamespace(data_dir=str(tmp_path / "b"), _score_icons=None, post=lambda k, **d: posts.append(k),
                               _report=lambda *a: None)
    for _ in range(scoreicons.KEEP + 2):
        types.MethodType(worker.DetectionWorker._learn_icons, w2)(part, rows)
    assert scoreicons.load(str(tmp_path / "b")) == {}                    # no ring read: not sure enough to learn from
