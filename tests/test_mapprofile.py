"""The map profile (mapprofile.py): the own record on one map, shown with the map big on the maps page."""
import os
import queue
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fogscout import mapprofile, official  # noqa: E402
from fogscout.dashboard import rounds_target  # noqa: E402
from fogscout.history import Round  # noqa: E402


def _round(t, map_id="coal", role="killer", killer="The Nurse", seconds=600.0, **more):
    return Round(t=float(t), seconds=seconds, map_id=map_id, map=map_id, role=role,
                 killer=killer if role == "killer" else "", **more)


def _killer_match(t, kills):
    states = ["sacrificed"] * kills + ["escaped"] * (4 - kills)
    return official.Match(t=float(t), map="x", role="killer",
                          opp=[official.Player(role="survivor", status=s) for s in states])


def _survivor_match(t, escaped):
    return official.Match(t=float(t), map="x", role="survivor", status="escaped" if escaped else "sacrificed")


def test_a_map_never_played_has_an_empty_profile():
    p = mapprofile.build([_round(1, map_id="other")], {}, "coal")
    assert p.rounds == 0 and p.tiles == [] and p.killers == [] and p.recent == []


def test_the_profile_counts_only_normal_rounds_of_this_map():
    rounds = [_round(1000), _round(2000, map_id="other"), _round(3000, custom=True), _round(4000, farming=True),
              _round(5000, role="survivor", seconds=300.0)]
    p = mapprofile.build(rounds, {}, "coal")
    assert p.rounds == 2
    runden, kills, escaped, length = p.tiles
    assert runden.value == "2" and runden.sub == "1 als Killer · 1 als Survivor"
    assert runden.open == rounds_target([1000.0, 5000.0])          # a click shows exactly these rounds
    assert kills.value == "–" and escaped.value == "–"             # no official match: no result is made up
    assert length.value == "07:30"


def test_results_come_from_the_official_matches():
    rounds = [_round(1000), _round(2000), _round(3000, killer="The Wraith"), _round(4000, role="survivor"),
              _round(5000, role="survivor"), _round(6000)]            # the last one has no match
    off = {id(rounds[0]): _killer_match(1000, 4), id(rounds[1]): _killer_match(2000, 2),
           id(rounds[2]): _killer_match(3000, 3), id(rounds[3]): _survivor_match(4000, True),
           id(rounds[4]): _survivor_match(5000, False)}
    p = mapprofile.build(rounds, off, "coal", killer_name=lambda k: k.replace("The ", ""),
                         result=lambda m: "?" if m is None else "x")
    _runden, kills, escaped, _length = p.tiles
    assert kills.value == "3.0" and kills.sub == "3 Runden · 1× 4K" and kills.frac == 0.75
    assert escaped.value == "50%" and escaped.sub == "2 Runden" and escaped.frac == 0.5
    assert p.killers == [("Nurse", "3 Runden", "Ø 3.0 Kills"), ("Wraith", "1 Runden", "Ø 3.0 Kills")]
    assert [r[1:3] for r in p.recent] == [("Nurse", "?"), ("Survivor", "x"), ("Survivor", "x"), ("Wraith", "x"),
                                          ("Nurse", "x")]            # newest first, RECENT_KEPT of them


def test_the_lists_are_capped():
    killers = ["The Nurse", "The Wraith", "The Trapper", "The Spirit", "The Blight", "The Hag"]
    rounds = [_round(1000 * i, killer=killers[i % len(killers)]) for i in range(1, 300)]
    p = mapprofile.build(rounds, {}, "coal")
    assert len(p.killers) == mapprofile.KILLERS_KEPT and len(p.recent) == mapprofile.RECENT_KEPT
    assert len(p.tiles[0].open.split(",")) == mapprofile.OPEN_MAX


# ---------------------------------------------------------------- the maps page
@pytest.fixture
def page():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import shiboken6
    from fogscout import qt_window
    qapp = qt_window.application()
    posted = queue.Queue()
    p = qt_window.MapsPage(lambda a, arg=None: posted.put((a, arg)))
    p.posted = posted
    yield p
    if shiboken6.isValid(p):
        p.hide()
        shiboken6.delete(p)
    qapp.processEvents()


def _texts(lines):
    return [[w.text() for w in line] for line in lines if not line[0].isHidden()]


def test_the_map_shown_big_carries_its_profile(page):
    rounds = [_round(1000), _round(2000, role="survivor")]
    prof = mapprofile.build(rounds, {id(rounds[0]): _killer_match(1000, 4)}, "coal", result=lambda m: "4K" if m else "–")
    page.show_preview(("coal", 1, "Coal Tower", "MacMillan", None, "", prof))
    assert not page.p_stats.isHidden() and page.p_empty.isHidden()
    assert [b.value.text() for b in page.p_tiles] == ["2", "4.0", "–", "10:00"]
    assert _texts(page.p_killers) == [["The Nurse", "1 Runden", "Ø 4.0 Kills"]]
    assert [line[1:3] for line in _texts(page.p_recent)] == [["Survivor", "–"], ["The Nurse", "4K"]]
    page.p_tiles[0].mouseReleaseEvent(_click(page.p_tiles[0]))          # „Runden“ opens these rounds in the statistics
    assert ("tile_open", rounds_target([1000.0, 2000.0])) in [page.posted.get_nowait()
                                                              for _i in range(page.posted.qsize())]


def test_a_map_without_rounds_says_so_and_an_old_preview_still_works(page):
    page.show_preview(("coal", 1, "Coal Tower", "MacMillan", None, "", mapprofile.Profile()))
    assert page.p_stats.isHidden() and not page.p_empty.isHidden()
    page.show_preview(("coal", 1, "Coal Tower", "MacMillan", None, ""))       # six fields (no profile): nothing shown
    assert page.p_stats.isHidden() and page.p_empty.isHidden()


def _click(widget):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    widget.resize(120, 60)
    pos = QPointF(5, 5)
    return QMouseEvent(QEvent.MouseButtonRelease, pos, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
