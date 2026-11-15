"""Facts the detection already has, kept and shown (feature batch K): the "banner missed" hint after the match
began, the banner decision stored with each round (diagnosis: detection health), the loading time from the lobby
found to the end of the loading screen and DBD's queue estimate ("EST.") against the real wait. None of it changes
when a round ends or which map is detected."""
import json
import os
import queue
import sys
import time

import numpy as np
import pytest

from fogscout import diagnose, history
from fogscout.lobby import Found, LobbyView, QueueTracker, parse_est

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ EST. parser
@pytest.mark.parametrize("text, seconds", [
    ("0:06 EST. 4:39", 279), ("0:06 EST.4:39", 279), ("0:06   est. 4:39  ", 279), ("EST. 4:39", 279),
    ("0:06 EST 4:39", 279),                                    # the dot lost by the OCR
    ("0:06 EST. 1:02:03", 3723), ("0:06 EST. 0:01", 1), ("1:02:03 EST. 12:00", 720),
])
def test_the_estimate_is_read_from_a_clean_est_text(text, seconds):
    assert parse_est(text) == seconds


@pytest.mark.parametrize("text", [
    "", None, "00:34", "1:02:03", "0:06",                          # no EST. at all (lobby countdown, waited time)
    "7:29 EST. 0:-01", "0:00 EST. 0:00",                          # DBD before it knows: no estimate
    "0:06 EST. 4:3", "0:06 EST. 4:39x", "0:06 EST. 4:3O", "0:06 EST. O:39", "0:06 EST. 4.39",   # OCR noise
    "0:06 EST. 4:75", "0:06 EST. 1:75:00", "0:06 EST. 1:02:75",   # no clock
    "0:06 EST. 4:39 EST. 1:00", "0:06 EST.",                      # garbled / cut
    "0:06 EST. 9:59:00",                                          # above EST_MAX: a misread
])
def test_an_unclean_est_text_gives_no_estimate_never_a_guess(text):
    assert parse_est(text) is None


def _search(t_text):
    return LobbyView("cancel", 0.0, "", t_text)


def test_the_estimate_of_the_search_goes_with_the_lobby_found():
    q = QueueTracker()
    looks = [(10, _search("0:00 EST. 4:16")), (11, _search("0:01 EST. 4:16")), (12, _search("0:02 EST. 3:59")),
             (130, LobbyView("ready", 0.0, "", "00:59")), (131, LobbyView("ready", 0.0, "", "00:58"))]
    found = [e[1] for t, v in looks for e in q.update(v, t) if e[0] == "found"][0]
    assert found.est == 256 and found.wait == pytest.approx(120, abs=1)
    assert q.est is None                                           # used up with the lobby


def test_one_misread_estimate_is_no_estimate():
    q = QueueTracker()
    for t, text in ((10, "0:00 EST. 4:16"), (11, "0:01 EST. 4:46"), (12, "0:02 EST. 4:7")):
        q.update(_search(text), t)
    assert q.est is None                                           # never the same value twice
    q.update(_search("0:03 EST. 4:46"), 13)
    assert q.est == 286                                            # the first value read twice
    q.update(LobbyView("play", 0.0), 20)
    q.update(LobbyView("play", 0.0), 21)
    assert q.est is None                                           # cancelled: gone with the search


def test_a_lobby_without_a_seen_search_or_a_custom_game_has_no_estimate():
    q = QueueTracker()
    ev = []
    for t in (1, 2):
        ev += q.update(LobbyView("ready", 0.0, "", "00:59"), t)
    assert [e[1] for e in ev if e[0] == "found"][0].est is None
    q = QueueTracker()
    ev = []
    for t in (1, 2):
        ev += q.update(LobbyView("ready", 0.0, "", ""), t)
    f = [e[1] for e in ev if e[0] == "found"][0]
    assert f.custom and f.est is None


# ------------------------------------------------------------------ the round's new fields
def _round(t, **kw):
    base = {"seconds": 600.0, "map_id": "coal", "map": "Coal Tower"}
    base.update(kw)
    return history.Round(t=t, **base)


def test_the_new_round_fields_are_stored_and_old_lines_load_without_them(tmp_path):
    path = str(tmp_path / history.FILE)
    old = {"t": 1.0, "seconds": 600.0, "map_id": "coal", "map": "Coal Tower", "region": "", "source": "auto",
           "wait": 30.0, "role": "killer", "custom": False, "farming": False, "ping": None, "killer": "",
           "sys": None, "stalls": None, "stall_max": None, "balance": None}
    broken = dict(old, t=2.0, fit="x", frames=True, unsure=1, latency=-1, load="60", est=[1])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(old) + "\n" + json.dumps(broken) + "\n")
    history.append(path, _round(3.0, fit=-0.4, frames=3, unsure=False, latency=1.25, load=95.5, est=256.0))
    a, b, c = history.load(path)
    for r in (a, b):
        assert (r.fit, r.frames, r.unsure, r.latency, r.load, r.est) == (None,) * 6
    assert (c.fit, c.frames, c.unsure, c.latency, c.load, c.est) == (-0.4, 3, False, 1.25, 95.5, 256.0)
    history.set_role(path, 1.0, "survivor")                        # a rewrite keeps them
    assert history.load(path)[2].load == 95.5 and history.load(path)[0].role == "survivor"


def test_a_lost_round_keeps_its_loading_time_and_estimate(tmp_path):
    path = str(tmp_path / history.FILE)
    history.append_lost(path, 5.0, "Coal Tower", "banner", map_id="coal", load=80.0, est=120.0, fit=-0.3,
                        frames=2, unsure=False, latency=0.8)
    (r,) = history.load_lost_rounds(path)
    assert (r.load, r.est, r.fit, r.frames, r.unsure, r.latency) == (80.0, 120.0, -0.3, 2, False, 0.8)


# ------------------------------------------------------------------ loading time per map / region
def test_the_loading_time_per_map_and_region():
    rs = [_round(1, map="Coal Tower", region="eu-central-1", load=60.0),
          _round(2, map="Coal Tower", region="eu-central-1", load=90.0),
          _round(3, map="Coal Tower", region="us-east-1", load=120.0),
          _round(4, map="Haddonfield", region="eu-central-1", load=30.0),
          _round(5, map="Haddonfield", region="", load=200.0),
          _round(6, map="Haddonfield", region="us-east-1", load=None)]       # not seen: left out
    # Coal Tower 60/90/120 → Ø 90, median 90; Haddonfield 30/200 → Ø 115, median 115 (longest first)
    assert history.load_by(rs, "map") == [("Haddonfield", 2, 115.0, 115.0), ("Coal Tower", 3, 90.0, 90.0)]
    # us-east-1 120 → 120; eu-central-1 60/90/30 → Ø 60, median 60; without a region (200) last
    assert history.load_by(rs, "region") == [("us-east-1", 1, 120.0, 120.0), ("eu-central-1", 3, 60.0, 60.0),
                                             (history.NO_REGION, 1, 200.0, 200.0)]
    assert history.load_by([], "map") == []


def test_the_real_wait_against_dbds_estimate_per_role():
    rs = [_round(1, role="killer", wait=300.0, est=240.0),           # +60: within ±1 min
          _round(2, role="killer", wait=100.0, est=200.0),           # −100
          _round(3, role="killer", wait=250.0, est=250.0),           # 0
          _round(4, role="survivor", wait=500.0, est=300.0),         # +200
          _round(5, role="survivor", wait=500.0, est=None),          # no estimate
          _round(6, role="survivor", wait=None, est=100.0),          # no wait
          _round(7, role="killer", wait=900.0, est=10.0, custom=True),     # not a public round
          _round(8, role="killer", wait=900.0, est=10.0, farming=True),
          _round(9, role="", wait=130.0, est=100.0)]                 # role unknown: only in "all"
    # killer: diffs 60, −100, 0 → median 0, 2 of 3 within; survivor: 200 → 0 of 1
    # all: 60, −100, 0, 200, 30 → median 30, 3 of 5 within
    assert history.est_accuracy(rs) == [("killer", 3, 0.0, pytest.approx(2 / 3)), ("survivor", 1, 200.0, 0.0),
                                        ("", 5, 30.0, pytest.approx(0.6))]
    assert history.est_accuracy([]) == []


def test_a_difference_of_times_keeps_its_sign():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from fogscout.app_stats import signed_duration
    assert (signed_duration(72), signed_duration(-30.4), signed_duration(0.2)) == ("+01:12", "−00:30", "00:00")


# ------------------------------------------------------------------ detection health (diagnosis)
def test_the_detection_health_line_and_when_it_gets_worse():
    assert diagnose.detection_health([_round(1)]) == [
        "Erkennung je Runde: noch keine automatisch erkannte Runde mit Messwerten"]
    t0 = time.mktime((2026, 11, 10, 18, 0, 0, 0, 0, -1))
    good = [_round(t0 + i * 900, fit=-0.2, frames=2, unsure=False, latency=0.5) for i in range(10)]
    bad = [_round(t0 + (10 + i) * 900, fit=-1.6, frames=4, unsure=i < 2, latency=1.5) for i in range(10)]
    lines = diagnose.detection_health(good + bad + [_round(t0 + 99999)])      # a manual round: left out
    assert lines[0] == ("Erkennung je Runde (letzte 20): Passung Median -0.9 · Banner→Entscheidung Median 1.0 s"
                        " · Bilder Median 3 · unsicher 2")
    since = time.strftime("%Y-%m-%d %H:%M", time.localtime(bad[0].t))
    assert lines[1] == (f"Erkennung wird schlechter seit {since}: Passung Median -1.6 in den letzten 10 Runden, "
                        "davor -0.2")
    # a drop of less than FIT_DROP (0.6) says nothing; fewer than 2 × 10 rounds no trend at all
    near = [_round(r.t, fit=-0.8, frames=2, unsure=False, latency=0.5) for r in bad]
    assert len(diagnose.detection_health(good + near)) == 1
    assert len(diagnose.detection_health(good[1:] + bad)) == 1


# ------------------------------------------------------------------ "banner missed" hint (worker)
def _bare_worker():
    from fogscout import worker
    from fogscout.matchstart import MatchStart
    w = worker.DetectionWorker.__new__(worker.DetectionWorker)
    w.posted, w.map_on_screen, w._banner_due = [], False, None
    w.post = lambda kind, **d: w.posted.append((kind, d))
    w.match_start, w.queue = MatchStart(), QueueTracker()
    return w


def test_the_hint_comes_once_and_only_without_a_banner_or_a_map():
    from fogscout import worker
    w = _bare_worker()
    w._banner_due = 100.0
    w._banner_check(99.0, False, True)
    w._banner_check(100.5, True, True)                             # a banner is being read: wait for it
    assert w.posted == []
    w._banner_check(101.0, False, True)
    w._banner_check(102.0, False, True)
    assert [k for k, _d in w.posted] == ["banner_missed"] and w._banner_due is None
    w.posted, w.map_on_screen, w._banner_due = [], True, 100.0      # a map picked by hand
    w._banner_check(101.0, False, True)
    assert w.posted == [] and w._banner_due is None
    w.map_on_screen, w._banner_due = False, 100.0                  # DBD gone / the detection switched off
    w._banner_check(101.0, False, False)
    assert w.posted == [] and w._banner_due is None
    w._banner_due = 100.0                                          # the loop did not get here for long: stale
    w._banner_check(100.0 + worker.BANNER_MISS_LATE_S + 1, False, True)
    assert w.posted == [] and w._banner_due is None
    for what in ("search", "cancel", "left", ("found", Found(1.0, 10.0, "killer"))):
        w._banner_due = 100.0                                      # back in the lobby screens: that match is over
        w._queue_event(what if isinstance(what, tuple) else (what,), 50.0)
        assert w._banner_due is None


def test_the_worker_hints_after_a_match_start_without_a_banner_and_not_in_a_custom_game(tmp_path, monkeypatch):
    """The real loop with a fake screen: the loading screen ends (match_start), no banner follows → one
    banner_missed after BANNER_MISS_S (shortened here); a match from a custom lobby gives none."""
    pytest.importorskip("onnxruntime")
    from types import SimpleNamespace
    from fogscout import config, worker
    from fogscout.catalog import Catalog
    from fogscout.matchstart import MatchStart
    W, H = 2560, 1440
    frame = np.full((H, W, 3), 60, np.uint8)

    class Grabber:
        def grab(self, left, top, width, height):
            return frame[top:top + height, left:left + width].copy()

        def primary_monitor(self):
            return 0, 0, W, H

        def close(self):
            pass

    class StartsAtOnce(MatchStart):
        def update(self, t, loading_bar, dark, lobby_button):     # the loading screen is over at the first look
            if self.armed_t is None:
                return False
            self.disarm()
            self.started_t = t
            return True

    game = SimpleNamespace(hwnd=1, left=0, top=0, width=W, height=H, minimized=False)
    monkeypatch.setattr(worker, "ScreenGrabber", Grabber)
    monkeypatch.setattr(worker, "find_game_window", lambda *a, **k: game)
    monkeypatch.setattr(worker, "foreground_root", lambda: 1)
    monkeypatch.setattr(worker, "cursor_state", lambda: None)
    monkeypatch.setattr(worker, "BANNER_MISS_S", 0.5)

    def run(custom):
        events = queue.Queue()
        wk = worker.DetectionWorker(ROOT, config.Settings(str(tmp_path / "settings.json")), Catalog(ROOT, ["en"]),
                                    events, data_dir=str(tmp_path))
        wk.match_start = StartsAtOnce()
        wk.match_start.arm(time.time())
        wk.queue.found = Found(time.time(), None if custom else 30.0, None if custom else "killer", custom=custom)
        kinds, started = [], None
        wk.start()
        try:
            deadline = time.time() + 60                            # generous: shared CI runners
            while time.time() < deadline and (started is None or time.time() < started + 3):
                try:
                    kinds.append(events.get(timeout=0.1).kind)
                except queue.Empty:
                    pass
                if started is None and "match_start" in kinds:
                    started = time.time()                          # then 3 s more (BANNER_MISS_S is 0.5 here)
        finally:
            wk.stop()
            wk.join(timeout=10)
        return kinds

    kinds = run(custom=False)
    assert kinds.count("match_start") == 1 and kinds.count("banner_missed") == 1
    assert kinds.index("match_start") < kinds.index("banner_missed")
    kinds = run(custom=True)
    assert kinds.count("match_start") == 1 and "banner_missed" not in kinds


# ------------------------------------------------------------------ the app: hint, decision, loading time, EST.
@pytest.fixture
def app_root(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Linux: the Windows job tests the native parts; the app would touch the system there")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    for name in ("maps", "models", "maps.json"):
        os.symlink(os.path.join(ROOT, name), tmp_path / name)
    (tmp_path / "sim").mkdir()
    return tmp_path


def test_the_app_says_how_to_scan_once_and_keeps_the_round_facts(app_root):
    from fogscout.app import App
    from fogscout.worker import Event
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    toasts, logs = [], []
    app.toast.show = lambda title, text, seconds=8.0: toasts.append((title, text))
    log = app._log
    app._log = lambda text, *a, **k: (logs.append(text), log(text, *a, **k))
    try:
        app._dispatch(Event("banner_missed", {"t": 1.0}))
        assert toasts == [("Map nicht erkannt", "Seit dem Matchbeginn kein Map-Banner erkannt – „Bildschirm scannen“ "
                                                "(Strg+Alt+S) sucht den Map-Namen auf dem Bildschirm.")]
        assert toasts[0][1] in logs
        app.settings["hotkeys"]["scan_now"] = ""
        app._dispatch(Event("banner_missed", {"t": 2.0}))
        assert "„Scannen“ im Steuerfenster" in toasts[-1][1]
        # the match begins 95 s after the lobby was found, the banner opens the round: loading time, EST., decision
        now = time.time()
        app._queue = {"state": "lobby", "found": Found(now - 95.0, 40.0, "killer", est=256.0)}
        app._dispatch(Event("match_start", {"t": now}))
        mid = list(app.catalog.maps)[2]
        app._dispatch(Event("detected", {"map_id": mid, "variant": 1, "probability": .9, "variant_probability": 1.0,
                                         "name_text": "x", "realm_text": "y", "frames": 3, "name_fit": -0.4321,
                                         "unsure": False, "latency": 1.234}))
        rec = app._hist
        assert (rec["load"], rec["est"], rec["fit"], rec["frames"], rec["unsure"], rec["latency"]) == \
            (95.0, 256.0, -0.43, 3, False, 1.23)
        n = len(toasts)
        app._dispatch(Event("banner_missed", {"t": 3.0}))           # a round is open: no hint
        assert len(toasts) == n
        app._hist["t"] -= 600
        app._dispatch(Event("match_end", {"reason": "x", "gen": app._watch_gen, "t": time.time()}))
        (r,) = history.load(str(app_root / history.FILE))
        assert (r.load, r.est, r.fit, r.wait) == (95.0, 256.0, -0.43, 40.0)
        # a custom lobby: no loading time; a match start long before the banner: not this round's
        app._queue = {"state": "custom", "found": Found(time.time() - 95.0, None, None, custom=True)}
        app._dispatch(Event("match_start", {"t": time.time()}))
        assert app._match_load is None
    finally:
        app.quit()


def test_the_wait_page_shows_the_estimate_and_loading_tables(app_root):
    from fogscout.app import App
    path = str(app_root / history.FILE)
    t0 = time.time() - 3600
    history.append(path, _round(t0, role="killer", wait=300.0, est=240.0, load=60.0, region="eu-central-1"))
    history.append(path, _round(t0 + 700, role="killer", wait=100.0, est=200.0, load=90.0, region="eu-central-1"))
    (app_root / "settings.json").write_text(json.dumps({"welcome_seen": True}), encoding="utf-8")
    app = App(str(app_root), simulate=str(app_root / "sim"))
    try:
        app._stats_wait_more(history.load(path))
        est = [app.stats_est.item(i)["values"] for i in app.stats_est.get_children()]
        assert [list(map(str, v)) for v in est] == [["Killer", "2", "−00:20", "50%"], ["Alle Rollen", "2", "−00:20",
                                                                                        "50%"]]
        maps = [app.stats_load_map.item(i)["values"] for i in app.stats_load_map.get_children()]
        assert [list(map(str, v)) for v in maps] == [["Coal Tower", "2", "01:15", "01:15"]]
        regs = [app.stats_load_reg.item(i)["values"] for i in app.stats_load_reg.get_children()]
        assert len(regs) == 1 and str(regs[0][1]) == "2"
    finally:
        app.quit()
