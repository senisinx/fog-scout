"""Overlay additions built on data the program already has: the own note on the lobby's killer on the waiting card,
"Zuletzt hier" below the record, the FPS row of the system values, the session's streak in "Heute", and the long
lobby line of the waiting card in two lines when the bar is too narrow for it even at the smallest text."""
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from fogscout import history, layout, mapnotes, official, overlay_win32 as ow, records, skin, sysinfo  # noqa: E402
from fogscout.app_place import OverlayPlacement  # noqa: E402
from fogscout.app_stats import StatsTab  # noqa: E402
from fogscout.app_sysinfo import SysInfo, today_rows  # noqa: E402
from fogscout.config import DEFAULTS  # noqa: E402
from fogscout.lobby import killer_label  # noqa: E402

LONG = ["Warte auf Map", "Suche läuft: 00:05 · Farming · Krankenschwester"]
SHORT = ["Warte auf Map", "Suche läuft: 00:05 · Nurse"]


def _bare_overlay():
    class Root:
        def after(self, *a):
            return None

        def after_cancel(self, *a):
            pass

    class Overlay(ow.PictureOverlay):
        def _push(self, *a):
            pass

    return Overlay(Root())


def _bar_avail(style: str, text_h: int = 518) -> float:
    """What App._place_overlay_map gives fit_width at 3440×1440 (auto, in the left bar, default margin)."""
    gh, bar = 1440, layout.bar_width(3440, 1440)
    margin = int(gh * DEFAULTS["overlay"]["margin"])
    ov = _bare_overlay()
    ov.set_skin(style, "#c9a227")
    edge = min(ov.backdrop_pad(text_h), max(0, margin - 2))
    return layout.max_width(bar, margin) + 2 * edge


def _fit_waiting_card(style, lines, memo=()):
    ov = _bare_overlay()
    ov.set_skin(style, "#c9a227")
    ov.set_waiting(lines, memo)
    avail = _bar_avail(style)
    h = ov.fit_width(518, 518, avail)
    w, hh = ov.render(ov.fit_room(h, 1400))
    return ov, avail, (w, hh)


# ------------------------------------------------------------------ the long lobby line (3440×1440)
def test_the_long_lobby_line_wraps_only_when_it_does_not_fit_at_the_smallest_text():
    """At 3440×1440 in style classic the line "Suche läuft: 00:05 · Farming · Krankenschwester" was 494 px wide at
    the smallest text (14 px) in the 406 px bar – 88 px over the edge. It now goes into two lines, only then: the
    card fits the bar in classic and glass, a shorter lobby line stays one line."""
    assert ow.wrap_status(LONG[1]) == ("Suche läuft: 00:05", "Farming · Krankenschwester")
    assert ow.wrap_status("Custom Game") == ("Custom Game",)
    assert _bar_avail("classic") == 406
    for style in ("classic", "glass"):
        ov, avail, (w, _h) = _fit_waiting_card(style, LONG)
        assert w <= avail, (style, w, avail)
        ov.set_waiting(LONG)                             # the next tick: the same lines, the same fit and wrap
        assert ov.render(ov.fit_room(ov.fit_width(518, 518, avail), 1400))[0] == w
        short, _a, (ws, _hs) = _fit_waiting_card(style, SHORT)
        assert not short._wait_wrap and short._waiting_shown() == tuple(SHORT) and ws <= avail
    classic, _a, _s = _fit_waiting_card("classic", LONG)
    assert classic._wait_wrap and classic._waiting_shown() == ("Warte auf Map", "Suche läuft: 00:05",
                                                               "Farming · Krankenschwester")
    assert classic.text_height > 40                     # two lines: larger text than the smallest one fits again
    # set_waiting alone (no fit this tick, e.g. an own place) draws the line as set
    classic.set_waiting(LONG)
    assert classic._waiting_shown() == tuple(LONG)


def test_the_waiting_card_keeps_its_size_while_the_search_time_counts():
    """The lobby line counts seconds: the card is sized with the widest digits (like the timer), so 00:05 → 01:11
    neither moves nor resizes it – classic and glass, one line and two."""
    for style in ("classic", "glass"):
        for base in (LONG, SHORT):
            sizes = set()
            for t in ("00:05", "01:11", "11:41", "59:59"):   # textnorm.fmt_duration: always mm:ss
                ov, avail, size = _fit_waiting_card(style, [base[0], base[1].replace("00:05", t)])
                sizes.add(size)
            assert len(sizes) == 1, (style, base, sizes)


# ------------------------------------------------------------------ the killer's note on the waiting card
def _placement(queue, notes, show=True, aliases=None):
    class Fake(OverlayPlacement):
        pass
    f = Fake()
    f._queue = queue
    f.settings = {"overlay": {"show_notes": show}, mapnotes.KILLER_KEY: notes, "killer_aliases": aliases or {}}
    f._killer_of = lambda name: {"The Nurse": "The Nurse", "Krankenschwester": "The Nurse"}.get(name, name)
    return f


def test_the_waiting_card_shows_the_own_note_on_the_killer_the_lobby_read():
    """Once the lobby read the killer, the own note on that killer (Statistik › Killer) shows on the waiting card –
    the same lines as below the map ("Nurse: …", at most four), off with the note setting, nothing without one."""
    notes = {"The Nurse": "blinks through walls\ncheck the window"}
    f = _placement({"state": "search", "killer": "Krankenschwester"}, notes)
    lines = f._waiting_memo()
    name = killer_label("The Nurse")                         # the killer's name in the UI language
    assert lines and lines[0].startswith(name + ": ") and len(lines) <= mapnotes.MAX_LINES
    assert all(len(line) <= mapnotes.LINE_CHARS + 1 for line in lines)
    assert lines == mapnotes.memo_lines("", notes["The Nurse"], name)
    assert _placement({"state": "search", "killer": "The Nurse"}, notes, show=False)._waiting_memo() == ()
    assert _placement({"state": "search"}, notes)._waiting_memo() == ()                   # killer not read yet
    assert _placement({"state": "search", "killer": "The Trapper"}, notes)._waiting_memo() == ()   # no note


def test_the_killer_note_sits_below_the_waiting_lines_and_the_card_fits_the_bar():
    """The note comes below "Warte auf Map" and the lobby line (classic: below the status rows; the modern card below
    its lines), the card fits the 3440×1440 bar in classic and glass and is measured with it (fit_width's key)."""
    memo = mapnotes.memo_lines("", "blinks through walls · check every window twice", "Nurse")
    for style in ("classic", "glass"):
        plain, avail, (w0, h0) = _fit_waiting_card(style, LONG)
        ov, avail, (w, h) = _fit_waiting_card(style, LONG, memo)
        assert w <= avail and h > h0, (style, w, avail, h, h0)
    # classic: the status rows first (the lobby line in the map's light tone), the note's lines below them
    pic = ow.add_info(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), "", "", 518, status=["Warte", "Suche läuft"],
                      memo=("Nurse: note",))
    px = pic.load()

    def rows_of(colour):
        return [y for y in range(pic.height) if any(px[x, y] == colour for x in range(pic.width))]
    assert rows_of(ow.INFO_SERVER) and rows_of(ow.INFO_MEMO)
    assert max(rows_of(ow.INFO_SERVER)) < min(rows_of(ow.INFO_MEMO))
    ov = _bare_overlay()
    ov.set_waiting(LONG, memo)
    ov.set_waiting([])                                       # no waiting card: no note either
    assert ov._waiting_memo == ()


# ------------------------------------------------------------------ "Zuletzt hier"
def _last_texts(rounds, off, before=None, result=None):
    j = SimpleNamespace(rounds=rounds, off=off)
    fake = SimpleNamespace(_joined=lambda: j,
                           _official_result=result or (lambda m: StatsTab._official_result(None, m)))
    return StatsTab._last_round_texts(fake, "coal", before)


def test_last_round_on_this_map_shows_the_date_and_the_official_result():
    """The own latest stored round on the map on display: its date, and its result when the round is linked to an
    official match – the open round (started at ``before``) and other maps do not count."""
    t0 = time.mktime((2026, 11, 12, 20, 0, 0, 0, 0, -1))
    old = history.Round(t0 - 86400, 600, "coal", "Coal Tower", role="killer")
    last = history.Round(t0, 600, "coal", "Coal Tower", role="killer")
    other = history.Round(t0 + 3600, 600, "ormond", "Ormond", role="killer")
    opp = [official.Player("survivor", "Meg Thomas", "Sacrificed" if i < 3 else "Escaped") for i in range(4)]
    linked = {id(last): official.Match(t=last.t, map="Coal Tower", role="killer", opp=opp)}
    texts = _last_texts([old, last, other], linked)
    assert texts[0] == "Zuletzt hier: 12.11.26 · 3K"
    assert "Zuletzt hier: 12.11.26" in texts and "Zuletzt hier: 12.11.26 · 4K" in texts   # what it may become
    assert _last_texts([old, last, other], {})[0] == "Zuletzt hier: 12.11.26"           # no official match: date
    assert _last_texts([old, last], {}, before=t0)[0] == "Zuletzt hier: 11.11.26"       # the open round left out
    assert _last_texts([other], {}) == ()


def test_the_last_round_line_keeps_the_card_size_whatever_it_says():
    """The line is sized for the widest text it may show – a later round on the map (another date, another result)
    never resizes the card: classic (below the map / the lines apart) and the modern chip."""
    texts = [("Zuletzt hier: 12.11.26 · 3K",), ("Zuletzt hier: 01.01.27 · aufgegeben",), ("Zuletzt hier: 09.09.26",)]
    others = tuple(t[0] for t in texts)
    shapes = [(t[0],) + others for t in texts]
    blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    assert len({ow.add_info(blank, "3:27", "", 518, last=s).size for s in shapes}) == 1
    assert len({ow.info_card("3:27", "", None, "", "Ø 2.8 Kills", 518, last=s).size for s in shapes}) == 1
    assert len({skin.map_card(None, "", "", "3:27", "", "", "", None, (), 518, "glass", None, last=s).size
                for s in shapes}) == 1
    ov = _bare_overlay()
    assert not ov.has_info()
    ov.set_last(shapes[0])
    assert ov.has_info()


# ------------------------------------------------------------------ FPS row
def test_the_fps_row_is_off_by_default_and_shows_only_with_hwinfo_fps():
    s = sysinfo.Snapshot(cpu_load=38, cpu_temp=64, fps=143.6)
    text = lambda rows: ["".join(t for t, _c in r) for r in rows]
    assert not any(t.startswith("FPS") for t in text(sysinfo.hud_rows(s)))                  # default off
    assert DEFAULTS["overlay"]["hud_rows"]["fps"] is False and "fps" in sysinfo.HUD_ROW_KEYS
    on = {"fps": True}
    assert text(sysinfo.hud_rows(s, on))[-1] == "FPS 144"
    assert not any(t.startswith("FPS") for t in text(sysinfo.hud_rows(sysinfo.Snapshot(cpu_load=38), on)))   # no HWiNFO


def test_the_fps_row_keeps_three_digits_of_room():
    """9 → 60 → 144 FPS never resizes the system values: the value is measured as three widest digits (classic);
    the modern tiles have a fixed width anyway."""
    def rows(fps, alone):
        snap = sysinfo.Snapshot(fps=fps) if alone else sysinfo.Snapshot(ram_used=7.0, ram_total=32, fps=fps)
        return sysinfo.hud_rows(snap, {"fps": True})
    for alone in (True, False):
        assert len({ow.render_hud(rows(f, alone), 1440).size for f in (9, 60, 144, 111)}) == 1, alone
        assert len({skin.card(rows(f, alone), 1440, "glass", None, "SYSTEM").size for f in (9, 60, 144)}) == 1
    assert ow.render_hud([[("CPU ", sysinfo.DIM), ("9", sysinfo.WHITE)]], 1440).size != \
        ow.render_hud([[("CPU ", sysinfo.DIM), ("144", sysinfo.WHITE)]], 1440).size     # only the FPS row is held


# ------------------------------------------------------------------ the session's streak in "Heute"
def _session(now, results):
    """Rounds 20 minutes apart ending before ``now``, each with its official result (kills or escaped)."""
    rs, off = [], {}
    for i, res in enumerate(results):
        t = now - (len(results) - i) * 1200
        if isinstance(res, int):
            r = history.Round(t, 600, "coal", "Coal Tower", role="killer")
            opp = [official.Player("survivor", "Meg Thomas", "Sacrificed" if k < res else "Escaped") for k in range(4)]
            off[id(r)] = official.Match(t=t, map="Coal Tower", role="killer", opp=opp)
        else:
            r = history.Round(t, 600, "coal", "Coal Tower", role="survivor")
            off[id(r)] = official.Match(t=t, map="Coal Tower", role="survivor", status=res,
                                        opp=[official.Player("killer", "The Trapper")])
        rs.append(r)
    return rs, off


def test_session_streak_counts_the_running_sessions_4ks_or_escapes():
    now = time.time()
    rs, off = _session(now, [2, 4, 4, 4])
    assert records.session_streak(rs, off, now) == ("killer", 3)
    rs, off = _session(now, [4, "Escaped", "Sacrificed", "Escaped", "Escaped"])
    assert records.session_streak(rs, off, now) == ("survivor", 2)               # the latest role counts
    rs, off = _session(now, [4, 4])
    assert records.session_streak(rs, off, now + 3 * 3600) is None               # the session is over
    assert records.session_streak(rs, {}, now) is None                           # no official results


def test_today_card_shows_the_streak_row_only_when_switched_on_and_keeps_its_width():
    now = time.time()
    rs, off = _session(now, [4, 4, 1, 4, 4])
    j = SimpleNamespace(rounds=rs, off=off, matches=list(off.values()))
    text = lambda rows: ["".join(t for t, _c in r) for r in rows]
    assert not any(t.startswith("SERIE") for t in text(today_rows(j, now, "normal")))
    assert text(today_rows(j, now, "normal", streak=True))[-1] == "SERIE 2 × 4K"
    empty = SimpleNamespace(rounds=[], off={}, matches=[])
    assert text(today_rows(empty, now, "normal", streak=True))[-1] == "SERIE –"     # the row stays: no jump
    # the App: the setting is part of the minute cache's key
    app = SimpleNamespace(_joined=lambda: j, _hist=None, _queue={},
                          settings={"farming_crossplay": True, "overlay": {"today_streak": False}})
    assert not any(t.startswith("SERIE") for t in text(SysInfo._today_rows(app, now)))
    app.settings["overlay"]["today_streak"] = True
    assert any(t.startswith("SERIE") for t in text(SysInfo._today_rows(app, now)))
    # a changing value keeps the label: the steady width (keyed by the labels) holds the widest; glass: fixed tiles
    a, b = today_rows(j, now, "normal", streak=True), today_rows(empty, now, "normal", streak=True)
    assert [r[0][0] for r in a] == [r[0][0] for r in b]
    st, w1 = layout.steady_width(None, ("k", tuple(r[0][0] for r in a)), ow.render_hud(a, 1440).width)
    st, w2 = layout.steady_width(st, ("k", tuple(r[0][0] for r in b)), ow.render_hud(b, 1440).width)
    assert w2 == max(w1, ow.render_hud(b, 1440).width) >= w1          # never narrower while the labels stay
    assert skin.card(a, 1440, "glass").size == skin.card(b, 1440, "glass").size
