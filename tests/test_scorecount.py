"""Score event tracker, step 4 (1.57.55): each event counted once over several looks (fogscout.scorecount)."""
from fogscout.scorecount import CAP, ScoreCounter, names_fit
from fogscout.scoreevents import Row

H = 21            # a name's height in the box at 1440p
STEP = 85         # one row lower (measured: a new event pushes the others down by ~85–91 px)


def row(name, points=None, y=480, category="boldness", capped=False):
    return Row(word=(400, y, 400 + 12 * len(name), y + H), name=name, points=points, capped=capped,
               category=category)


def feed(counter, looks, step=0.25):
    """looks: one list of rows per look, ``step`` s apart; then the match ends."""
    for i, rows in enumerate(looks):
        counter.feed(i * step, rows)
    counter.flush()
    return counter


def test_an_event_seen_over_several_looks_is_counted_once():
    c = feed(ScoreCounter(), [[row("VAULT", 100)]] * 10)
    assert [(e.name, e.points, e.category) for e in c.events] == [("VAULT", 100, "boldness")]
    assert c.totals()["boldness"] == 100 and c.role() == "survivor"


def test_a_new_event_on_top_pushes_the_old_one_down_and_both_count_once():
    looks = [[row("BOLD", 13)]] * 2 + [[row("VAULT", 100), row("BOLD", 13, y=480 + STEP)]] * 6 + [[row("VAULT", 100)]] * 4
    c = feed(ScoreCounter(), looks)
    assert sorted((e.name, e.points) for e in c.events) == [("BOLD", 13), ("VAULT", 100)]


def test_two_equal_events_at_once_are_two_events():
    looks = [[row("BOLD", 2), row("BOLD", 2, y=480 + STEP)]] * 6
    assert [e.points for e in feed(ScoreCounter(), looks).events] == [2, 2]


def test_a_name_cut_while_sliding_in_belongs_to_the_same_event():
    looks = [[row("OVERY", 40, category="survival")], [row("COVERY", 40, category="survival")]] + \
            [[row("RECOVERY", 40, category="survival")]] * 6
    c = feed(ScoreCounter(), looks)
    assert [(e.name, e.points) for e in c.events] == [("RECOVERY", 40)]
    assert names_fit("CAPED", "ESCAPED") and names_fit("SURVIVORFOUN", "SURVIVORFOUND")
    assert not names_fit("HEAL", "REPAIRS")


def test_a_growing_counter_counts_its_final_value_and_misreadings_are_outvoted():
    values = [100, 162, 250, 340, 488, 488, 4488, 488, 488, None, 488]          # one misreading, one unreadable
    looks = [[row("REPAIRS", v, category="objective")] for v in values]
    assert [e.points for e in feed(ScoreCounter(), looks).events] == [488]


def test_a_row_seen_once_or_never_read_is_not_counted():
    c = feed(ScoreCounter(), [[row("CHASED", 300)], [], [], [], [], [row("HIT", None, category="brutality")] ,
                              [row("HIT", None, category="brutality")], [], [], [], []])
    assert c.events == [] and c.dropped == 2


def test_a_different_category_is_a_different_event():
    looks = [[row("CHASE", 100, category="hunter")]] * 3 + [[row("CHASE", 100, category="boldness")]] * 3
    assert sorted(e.category for e in feed(ScoreCounter(), looks).events) == ["boldness", "hunter"]


def test_a_row_never_moves_up_a_lower_row_is_not_an_earlier_one():
    looks = [[row("BOLD", 5, y=480 + STEP)]] * 3 + [[row("BOLD", 7, y=480)]] * 3      # the second one is newer
    assert [e.points for e in feed(ScoreCounter(), looks).events] == [5, 7]


def test_max_fills_the_category_and_totals_stop_at_the_cap():
    looks = [[row("HOOKED", None, category="sacrifice", capped=True)]] * 4
    c = feed(ScoreCounter(), looks)
    assert c.events[0].capped and c.events[0].points == 0 and c.totals()["sacrifice"] == CAP
    many = ScoreCounter()
    for i in range(30):                     # 30 events of 500 = 15 000 → the cap
        for k in range(3):
            many.feed(i * 2 + k * 0.25, [row("SURVIVORFOUND", 500, category="hunter")])
    many.flush()
    assert len(many.events) == 30 and many.totals()["hunter"] == CAP and many.role() == "killer"


def test_an_event_ends_after_the_gap_and_is_returned_then():
    c = ScoreCounter()
    for i in range(4):
        assert c.feed(i * 0.25, [row("VAULT", 100)]) == []
    ended = c.feed(2.0, [])
    assert [e.name for e in ended] == ["VAULT"] and c.flush() == []


def test_a_category_total_is_its_newest_ring_plus_the_events_after_it():
    def ringed(name, points, ring, y=480):
        r = row(name, points, y=y, category="objective")
        r.ring = ring
        return r
    looks = [[ringed("REPAIRS", 500, 0.40)]] * 4 + [[]] * 5 + \
            [[ringed("GREATSKILLCHECK", 300, 0.43)]] * 4 + [[]] * 5 + \
            [[row("UNLOCKING", 476, category="objective")]] * 4                      # no ring read
    c = feed(ScoreCounter(), looks)
    assert [e.ring for e in c.events] == [0.40, 0.43, None]
    assert c.totals()["objective"] == 4300 + 476                                   # not 500 + 300 + 476
    # a missed event does not stay missing: the next ring has it
    c2 = feed(ScoreCounter(), [[ringed("REPAIRS", 500, 0.40)]] * 4)
    assert c2.totals()["objective"] == 4000


def test_an_event_takes_the_ring_of_its_last_looks():
    looks = []
    for v in (0.30, 0.31, 0.38, 0.40, 0.40, 0.41):                               # filling while it slides in
        r = row("HEAL", 120, category="altruism")
        r.ring = v
        looks.append([r])
    assert feed(ScoreCounter(), looks).events[0].ring == 0.40


def test_a_ring_far_below_the_running_total_is_a_misreading():
    def ringed(points, ring):
        r = row("REPAIRS", points, category="objective")
        r.ring = ring
        return r
    looks = [[ringed(500, 0.60)]] * 4 + [[]] * 5 + [[ringed(300, 0.05)]] * 4 + [[]] * 5 + [[ringed(200, 0.65)]] * 4
    c = feed(ScoreCounter(), looks)
    assert [e.ring for e in c.events] == [0.60, 0.05, 0.65]
    assert c.totals()["objective"] == 6500                     # 6000, the 5 % ring not believed (+300), then 6500
    # missed events: a ring above the running total is always believed
    up = feed(ScoreCounter(), [[ringed(500, 0.10)]] * 4 + [[]] * 5 + [[ringed(100, 0.50)]] * 4)
    assert up.totals()["objective"] == 5000


# --- 1.57.56: the live tracker in the worker and the app ----------------------------------------------------------

def _worker_stub(posts):
    import types
    from fogscout import worker
    from fogscout.ticktime import LookTimes
    w = types.SimpleNamespace(settings={"score_track": True}, times=LookTimes(), post=lambda k, **d: posts.append((k, d)),
                              _report=lambda what, text: posts.append(("report", {"what": what, "text": text})),
                              _mask_screen=lambda img, *a: None, _score=None,
                              _score_stats={"looks": 0, "shown": 0, "covered": 0, "ms": 0.0}, score_info="–")
    for name in ("_score_round", "_score_look", "_score_final", "_score_post", "_score_describe"):
        setattr(w, name, types.MethodType(getattr(worker.DetectionWorker, name), w))
    return w


def test_the_worker_counts_the_score_corner_and_gives_the_totals_before_the_round_ends():
    import os
    import cv2
    import numpy as np
    from fogscout import worker
    from fogscout.ocr import Recognizer
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rec = Recognizer(os.path.join(root, "models", "ch_PP-OCRv4_rec_infer.onnx"))
    corner = cv2.imread(os.path.join(root, "tests", "data", "score", "killer-three-rows.webp"))
    fw, fh = 3440, 1440
    x, y, w_, h_ = worker.score_box(fw, fh)
    assert (w_, h_) == corner.shape[1::-1]
    frame = np.zeros((fh, fw, 3), np.uint8)
    frame[y:y + h_, x:x + w_] = corner
    empty = np.zeros_like(frame)
    pictures = [frame] * 6 + [empty] * 6
    posts = []
    w = _worker_stub(posts)
    w._score_round(("gen", 1), same_round=False)
    for i, pic in enumerate(pictures):
        w._score_look(lambda box, p=pic: p[box[1]:box[1] + box[3], box[0]:box[0] + box[2]].copy(),
                      fw, fh, (0, 0), lambda: False, i * 0.25, rec)
    w._score_look(lambda box: None, fw, fh, (0, 0), lambda: False, 3.5, rec)       # covered: no look
    w._score_final(("gen", 1))
    scores = [d for k, d in posts if k == "score"]
    assert [k for k, _d in posts if k == "report"] == []
    assert scores and scores[-1]["final"] and scores[-1]["role"] == "killer"
    assert scores[-1]["events"] == 3 and set(scores[-1]["totals"]) == {"brutality", "deviousness", "hunter", "sacrifice"}
    tot = scores[-1]["totals"]
    # 1.57.65: the rings of the straight picture (hunter ~0.19, brutality ~0.12, deviousness ~0.05 of 10 000)
    assert tot["sacrifice"] == 0 and 1000 < tot["hunter"] < 3000 and 500 < tot["brutality"] < 2000
    assert 0 <= tot["deviousness"] < 1200
    assert w._score is None and w._score_stats["covered"] == 1 and w._score_stats["shown"] == 6
    assert "Runde vorbei" in w.score_info


def test_a_banner_read_twice_keeps_the_rounds_counter():
    posts = []
    w = _worker_stub(posts)
    w._score_round(("a", 1), same_round=False)
    first = w._score[1]
    w._score_round(("a", 2), same_round=True)
    assert w._score == (("a", 2), first)
    w._score_round(("b", 3), same_round=False)
    assert w._score[1] is not first
    w._score_round(None, same_round=False)
    assert w._score is None
    w._score_final(None)                    # nothing open: nothing posted
    assert posts == []


def test_the_app_keeps_the_final_points_with_the_round_and_logs_them():
    import types
    from fogscout.app_stats import StatsTab
    logged = []
    shown = []
    app = types.SimpleNamespace(_hist={"t": 1.0}, _log=lambda text, cat: logged.append(text),
                                _update_score=lambda: shown.append(dict(app._score_now)))
    StatsTab._score_event(app, {"final": False, "totals": {"objective": 100}})
    assert "score" not in app._hist and app._score_now == {"objective": 100} and logged == []
    StatsTab._score_event(app, {"final": True, "totals": {"objective": 4200, "boldness": 10000, "x": True}})
    assert app._hist["score"] == {"objective": 4200, "boldness": 10000}
    assert len(logged) == 1 and "Objective 4200" in logged[0]
    assert shown == [{"objective": 100}, {"objective": 4200, "boldness": 10000}]      # the overlay line follows


def test_the_overlay_line_is_short_and_never_changes_its_size():
    from fogscout.scorecount import line
    text, widest = line({"brutality": 4300, "deviousness": 1460, "hunter": 8260, "sacrifice": 10000})
    assert text == "BRU 4.3k · DEV 1.5k · HUN 8.3k · SAC MAX"
    assert widest == "BRU 00.0k · DEV 00.0k · HUN 00.0k · SAC 00.0k"
    assert line({"objective": 0, "boldness": 9999}, full=("boldness",))[0] == "OBJ 0.0k · BOL MAX"
    assert line({}) == ()


def test_a_rounds_counted_points_are_stored_and_broken_ones_dropped(tmp_path):
    import json
    from fogscout import history
    path = str(tmp_path / "rounds.jsonl")
    history.append(path, history.Round(t=1795600000.0, seconds=600.0, map_id="m", map="M",
                                       score={"hunter": 8300, "sacrifice": 10000}))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": 1795601000.0, "seconds": 500.0, "map_id": "m", "map": "M",
                             "score": {"hunter": "9000", "nope": 5, "brutality": -1, "deviousness": 4000}}) + "\n")
    rounds = history.load(path)
    assert rounds[0].score == {"hunter": 8300, "sacrifice": 10000}
    assert rounds[1].score == {"deviousness": 4000}


# --- 1.57.61: the waiting card stays away while DBD uses the whole width ------------------------------------------

def test_the_waiting_card_stays_away_while_dbd_fills_the_bars(monkeypatch):
    """User's recordings: the card lay on the lobby's menu column and on the scoreboard; user: "Ausblenden"."""
    import time
    import types
    from fogscout import app_place
    stub = types.SimpleNamespace(
        settings={"overlay": {"show_waiting": True}, "auto_detect": True}, game=object(), simulate=None,
        overlay=types.SimpleNamespace(editing=False, has_map=lambda: False), hidden_after_match=False,
        _queue={}, round=types.SimpleNamespace(start_t=None, running=False),
        worker=types.SimpleNamespace(full_width_at=-1e9))
    assert app_place.OverlayPlacement._waiting_lines(stub) != []
    stub.worker.full_width_at = time.time() - 1.0                  # a look a second ago: lobby, menu, result screen
    assert app_place.OverlayPlacement._waiting_lines(stub) == []
    stub.worker.full_width_at = time.time() - app_place.FULL_WIDTH_HOLD_S - 1      # back in a loading screen
    assert app_place.OverlayPlacement._waiting_lines(stub) != []


def test_the_worker_lists_every_own_window_clipped_to_the_picture():
    import types
    from fogscout import worker
    w = types.SimpleNamespace(overlay_rect=(100, 200, 300, 400), info_rect=None, hud_rect=(3300, 100, 300, 300),
                              media_rect=None, today_rect=None, inputs_rect=None, loadouts_rect=None, toast_rect=None,
                              guide_rects=[], fade_rects=[(-50, -50, 100, 100)])
    boxes = worker.DetectionWorker._own_boxes(w, (1440, 3440, 3), 0, 0)
    assert boxes == [(100, 200, 400, 600), (3300, 100, 3440, 400), (0, 0, 50, 50)]
