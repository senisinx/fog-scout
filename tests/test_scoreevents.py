"""Score event tracker, step 1 (1.57.52): full-size pictures of the top right of the 16:9 picture to tune on."""
import os
from types import SimpleNamespace

import cv2
import numpy as np

from fogscout import worker


def _frame_with_events(w=3440, h=1440, words=True, points=True, in_bar=False):
    frame = np.zeros((h, w, 3), np.uint8)
    vw = h * 16 // 9
    vx = (w - vw) // 2
    x = (w - 60) if in_bar else vx + int(0.84 * vw)     # in_bar: the right black bar (FPS counters live there)
    for i, word in enumerate(("CHASED", "PROTECTION", "BOLD")):
        y = int((0.12 + 0.07 * i) * h)
        if words:
            cv2.putText(frame, word, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3)
        if points:
            cv2.putText(frame, "+209", (x + 150, y + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 230), 2)
    return frame


def test_the_score_box_is_cut_from_the_16_9_picture_never_the_black_bars():
    part = worker.score_part(np.zeros((1440, 3440, 3), np.uint8))
    x0, y0, x1, y1 = worker.SCORE_BOX
    assert part.shape[:2] == (int(y1 * 1440) - int(y0 * 1440), int(x1 * 2560) - int(x0 * 2560))
    assert worker.score_part(None) is None
    assert not worker.score_shown(worker.score_part(_frame_with_events(in_bar=True)))


def test_score_events_are_seen_only_with_white_words_and_red_points():
    assert worker.score_shown(worker.score_part(_frame_with_events()))
    assert worker.score_shown(worker.score_part(_frame_with_events(w=2560)))           # 16:9 window, no bars
    assert not worker.score_shown(worker.score_part(_frame_with_events(points=False)))
    assert not worker.score_shown(worker.score_part(_frame_with_events(words=False)))
    assert not worker.score_shown(worker.score_part(np.zeros((1440, 3440, 3), np.uint8)))


def test_score_pictures_go_to_debug_score_full_size_and_only_the_newest_are_kept(tmp_path, monkeypatch):
    clock = iter(range(10_000))
    monkeypatch.setattr(worker.time, "strftime", lambda fmt, *a: f"20261125-{next(clock):06d}")   # one name each
    stub = SimpleNamespace(data_dir=str(tmp_path), _last_score_save=0.0)
    worker.DetectionWorker._save_score_look(stub, np.zeros((1440, 3440, 3), np.uint8), 5.0)
    assert not (tmp_path / "debug" / "score").exists() and stub._last_score_save == 0.0    # nothing shown: nothing kept
    frame = _frame_with_events()
    for i in range(worker.SCORE_KEPT + 3):
        worker.DetectionWorker._save_score_look(stub, frame, 10.0 + i)
    d = tmp_path / "debug" / "score"
    files = sorted(os.listdir(d))
    assert len(files) == worker.SCORE_KEPT and all(f.endswith("-score.webp") for f in files)
    assert np.array_equal(cv2.imread(str(d / files[-1])), worker.score_part(frame))       # lossless, full size
    assert stub._last_score_save == 10.0 + worker.SCORE_KEPT + 2


def test_the_recording_tool_cuts_each_new_sight_once(tmp_path):
    """tools/score_frames.py: the same box and test on the user's own recordings – each new sight once."""
    import subprocess
    import sys
    import pytest
    from fogscout.obsrec import ffmpeg_exe
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import score_frames
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        pytest.skip("imageio-ffmpeg 0.6.0 missing")
    w, h = 1720, 720
    plain = np.zeros((h, w, 3), np.uint8)
    seen = cv2.resize(_frame_with_events(), (w, h), interpolation=cv2.INTER_AREA)
    shown = [plain, seen, seen, plain, seen]                     # one second each: two separate sights
    video = tmp_path / "Runde 1.mkv"
    proc = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                             "-s", f"{w}x{h}", "-r", "4", "-i", "-", "-c:v", "libx264", "-crf", "12",
                             "-pix_fmt", "yuv444p", str(video)], stdin=subprocess.PIPE)
    for pic in shown:
        for _ in range(4):
            proc.stdin.write(pic.tobytes())
    proc.stdin.close()
    assert proc.wait(timeout=60) == 0
    assert score_frames.crop_box(3440, 1440)[:2] == worker.score_part(np.zeros((1440, 3440, 3), np.uint8)).shape[1::-1]
    looks, saved = score_frames.scan(str(video), str(tmp_path / "out"), 4.0, ffmpeg)
    assert (looks, saved) == (20, 2)
    files = sorted(os.listdir(tmp_path / "out" / "Runde_1"))
    assert files == ["000m001.00s.webp", "000m004.00s.webp"]


# --- step 2 (1.57.53): rows found and read (fogscout.scoreevents) ---------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORE_DATA = os.path.join(ROOT, "tests", "data", "score")
# corners cut from own recordings (3440×1440, so the box is 973×634), all but the events blacked out
SCORE_PICTURES = {      # name (folded), points, MAX, category from the icon (1.57.54)
    "killer-three-rows.webp": [("SURVIVORFOUND", 250, False, "hunter"), ("HIT", 300, False, "brutality"),
                               ("LETHALBLINK", 250, False, "deviousness")],
    "survivor-two-rows.webp": [("ESCAPED", 375, False, "boldness"), ("CHASED", 450, False, "boldness")],
    "killer-max.webp": [("HOOKED", None, True, "sacrifice")],
}


def _recognizer():
    from fogscout.ocr import Recognizer
    return Recognizer(os.path.join(ROOT, "models", "ch_PP-OCRv4_rec_infer.onnx"))


def _read(rec, part):
    from fogscout import scoreevents
    from fogscout.textnorm import fold
    return [(fold(r.name), r.points, r.capped, r.category) for r in scoreevents.read_rows(rec, part)]


def test_score_events_are_read_from_own_recordings_name_points_max_and_category():
    """Name and points of each row, top to bottom; "+" is never read as a digit (+375, not +4375 or +775); the
    category from the icon beside it."""
    rec = _recognizer()
    for name, want in SCORE_PICTURES.items():
        part = cv2.imread(os.path.join(SCORE_DATA, name))
        assert part.shape[:2] == (634, 973), name
        assert _read(rec, part) == want, name


def test_score_events_are_read_in_smaller_pictures_too():
    """1080p and 720p: the lengths scale with the height of the box."""
    rec = _recognizer()
    for name, want in SCORE_PICTURES.items():
        part = cv2.imread(os.path.join(SCORE_DATA, name))
        for scale in (0.75, 0.5):
            small = cv2.resize(part, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            assert _read(rec, small) == want, (name, scale)


def test_no_rows_without_white_words_and_red_points():
    from fogscout import scoreevents
    assert scoreevents.find_rows(None) == []
    assert scoreevents.find_rows(np.zeros((634, 973, 3), np.uint8)) == []
    words = np.zeros((634, 973, 3), np.uint8)
    cv2.putText(words, "CHASED", (500, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3)
    assert scoreevents.find_rows(words) == []                        # a white word alone is no event
    streak = words.copy()
    cv2.line(streak, (420, 150), (640, 140), (20, 20, 230), 3)       # a red light streak below it is no points
    assert scoreevents.find_rows(streak) == []


def test_points_text_is_parsed_strictly():
    from fogscout import scoreevents
    assert scoreevents.parse_points("+250") == (250, False)
    assert scoreevents.parse_points("MAX") == (None, True)
    for text in ("+", "", "250", "+25x", "4250+", "MA"):
        assert scoreevents.parse_points(text) == (None, False), text


def test_the_reading_tool_reads_a_folder_and_writes_its_table(tmp_path, capsys):
    import csv
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import score_read
    table = tmp_path / "rows.csv"
    assert score_read.main([SCORE_DATA, "--csv", str(table), "--sheet", str(tmp_path / "check.png")]) == 0
    assert "3 Bilder, 6 Zeilen, davon lesbar (Name + Punkte/MAX): 6 (100 %)" in capsys.readouterr().out
    with open(table, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert sorted(r["punkte"] for r in rows) == ["", "250", "250", "300", "375", "450"]
    assert (tmp_path / "check.png").exists()


# --- step 3 (1.57.54): the category from the icon ---------------------------------------------------------------------

def test_the_templates_are_eight_tiles_in_the_order_of_the_categories(tmp_path, monkeypatch):
    from fogscout import scoreevents
    temps = scoreevents.templates()
    assert temps.shape == (8, 26, 34) and scoreevents.CATEGORIES[:4] == scoreevents.KILLER
    assert np.allclose(np.linalg.norm(temps.reshape(8, -1), axis=1), 1.0)
    # written and read back: the same templates (up to the 8-bit steps), each still best for itself
    path = tmp_path / "icons.png"
    scoreevents.save_templates(str(path), temps)
    monkeypatch.setattr(scoreevents, "ICONS_FILE", str(path))
    monkeypatch.setattr(scoreevents, "_TEMPLATES", [])
    again = scoreevents.templates()
    assert (again.reshape(8, -1) * temps.reshape(8, -1)).sum(1).min() > 0.99
    for i, t in enumerate(temps):
        assert int(np.argmax(scoreevents.icon_scores(t, again))) == i


def test_an_icon_that_is_not_to_be_seen_or_not_clear_has_no_category():
    from fogscout import scoreevents
    part = cv2.imread(os.path.join(SCORE_DATA, "killer-max.webp"))
    row = scoreevents.find_rows(part)[0]
    assert scoreevents.icon_category(part, row)[0] == "sacrifice"
    x0, y0, x1, y1 = row.word
    off = scoreevents.Row(word=(part.shape[1] - (x1 - x0), y0, part.shape[1], y1))     # icon right of the box
    assert scoreevents.icon_cut(part, off) is None
    assert scoreevents.icon_category(part, off) == (None, 0.0, 0.0)
    blank = part.copy()
    blank[:, x1:] = 0                                                   # the ring gone: nothing to compare
    assert scoreevents.icon_category(blank, row)[0] is None


def test_the_template_tool_takes_only_seed_names_and_needs_every_category():
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import pytest
    import score_icons
    rows = score_icons.collect([SCORE_DATA], 0)
    assert sorted(c for _r, c, _f in rows) == ["boldness", "boldness", "brutality", "deviousness", "hunter",
                                               "sacrifice"]
    with pytest.raises(SystemExit, match="objective"):                   # survivors' categories missing here
        score_icons.make(rows)
    assert not set(score_icons.SEED_OF) & {"HEAL", "GOODSKILLCHECK", "GREATSKILLCHECK", "COOPACTION", "MEDKITHEAL"}


def test_a_debug_name_reads_the_clock_once_so_names_sort_in_time(monkeypatch):
    """1.57.54: seconds and milliseconds from two readings straddled a second (…-12:00:00-000 for 12:00:00.999 →
    12:00:01.000 – a name 1 s early); one reading gives the true order."""
    import time as real
    clock = iter([1795600000.999, 1795600001.0005, 1795600001.2])
    monkeypatch.setattr(worker.time, "time", lambda: next(clock))
    a, b = worker._stamp(), worker._stamp()
    assert a < b and a.endswith("-999") and b.endswith("-000")
    assert a[:15] == real.strftime("%Y%m%d-%H%M%S", real.localtime(1795600000.999))


# --- 1.57.55: the ring shows how full the category is -----------------------------------------------------------------

def _ring_picture(share, h=21, grey=(120, 120, 120)):
    """A row's name and its ring drawn as DBD does: grey all round, red from RING_START for ``share`` of it."""
    from fogscout import scoreevents
    part = np.zeros((634, 973, 3), np.uint8)
    word = (400, 200, 560, 200 + h)
    cx, cy = word[2] + scoreevents.RING_MIDDLE[0] * h, word[1] + scoreevents.RING_MIDDLE[1] * h
    axes = (int(round(scoreevents.RING_AXES[0] * h / 2)), int(round(scoreevents.RING_AXES[1] * h / 2)))
    centre = (int(round(cx)), int(round(cy)))
    cv2.ellipse(part, centre, axes, scoreevents.RING_ANGLE, 0, 360, grey, 3)
    if share > 0:
        cv2.ellipse(part, centre, axes, scoreevents.RING_ANGLE, scoreevents.RING_START,
                    scoreevents.RING_START + 360 * share, (30, 30, 230), 3)
    return part, scoreevents.Row(word=word)


def test_a_drawn_ring_is_read_back_at_its_share():
    from fogscout import scoreevents
    for share in (0.0, 0.05, 0.25, 0.5, 0.73, 0.98, 1.0):
        part, row = _ring_picture(share)
        got = scoreevents.ring_progress(part, row)
        # 3.5 points: near the ends of the long axis a few pixels of stroke span several degrees (0.05 → 0.08)
        assert got is not None and abs(got - share) <= 0.035, (share, got)
    part, row = _ring_picture(0.4, grey=(60, 60, 60))              # the Nurse's dark ring on black (was None)
    assert abs(scoreevents.ring_progress(part, row) - 0.4) <= 0.035


def test_no_ring_no_progress():
    from fogscout import scoreevents
    part, row = _ring_picture(0.5)
    assert scoreevents.ring_progress(np.zeros_like(part), row) is None
    off = scoreevents.Row(word=(900, 600, 973, 621))                 # its ring would be outside the box
    assert scoreevents.ring_progress(part, off) is None


def test_the_rings_of_own_recordings():
    """MAX = full; two Boldness rows: the newer (upper) one is at least as full as the older one."""
    from fogscout import scoreevents
    rec = _recognizer()
    full = scoreevents.read_rows(rec, cv2.imread(os.path.join(SCORE_DATA, "killer-max.webp")))
    assert full[0].ring == 1.0
    two = scoreevents.read_rows(rec, cv2.imread(os.path.join(SCORE_DATA, "survivor-two-rows.webp")))
    assert 0.8 < two[1].ring <= two[0].ring < 0.95
    three = scoreevents.read_rows(rec, cv2.imread(os.path.join(SCORE_DATA, "killer-three-rows.webp")))
    assert all(r.ring is not None and 0.3 < r.ring < 0.7 for r in three)
