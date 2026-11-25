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
    monkeypatch.setattr(worker.time, "strftime", lambda fmt: f"20261125-{next(clock):06d}")   # one name each
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
