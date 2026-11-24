"""Window capture (Windows Graphics Capture) while DBD is in the background."""
import os
import sys
import threading
import time
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fogscout.wincapture import CapturePolicy, WindowCapture, describe  # noqa: E402


# ------------------------------------------------------------------ policy
def test_policy_runs_only_while_dbd_is_in_the_background():
    p = CapturePolicy()
    assert not p.update(0.0, True, True, True)          # DBD active in front: screen capture as before
    assert p.update(1.0, True, True, False)             # another window active: window capture
    assert p.update(2.0, True, True, True)              # back to DBD: keep it a while (quick Alt+Tab)
    assert p.update(2.0 + p.STOP_AFTER - 0.1, True, True, True)
    assert not p.update(2.0 + p.STOP_AFTER, True, True, True)   # active long enough: off again


def test_policy_restarts_the_hold_after_another_alt_tab():
    p = CapturePolicy()
    p.update(0.0, True, True, False)
    p.update(1.0, True, True, True)
    p.update(4.0, True, True, False)                    # away again before the hold ran out
    assert p.update(4.0 + p.STOP_AFTER - 0.1, True, True, True)


def test_policy_off_without_window_or_option():
    p = CapturePolicy()
    assert not p.update(0.0, False, True, False)        # option off
    assert not p.update(0.0, True, False, False)        # DBD gone or minimised
    p.update(1.0, True, True, False)
    assert not p.update(1.5, True, False, False)        # window vanished: stop at once


# ------------------------------------------------------------------ capture (fake windows_capture)
class _FakeLib:
    """Behaves like windows_capture 2.0.1: callbacks on its own thread, BGRA buffer valid only
    during the callback, options that older Windows refuses raise at construction."""

    def __init__(self, refuse=(), size=(64, 40)):
        self.refuse, self.size, self.made = set(refuse), size, []
        lib = self

        class WindowsCapture:
            def __init__(self, **kw):
                if any(k in lib.refuse and v not in (None,) for k, v in kw.items()):
                    raise RuntimeError("unsupported")
                lib.made.append(kw)
                self.handlers = {}

            def event(self, h):
                self.handlers[h.__name__] = h
                return h

            def start_free_threaded(self):
                stop = threading.Event()

                def loop():
                    n = 0
                    while not stop.is_set():
                        w, h = lib.size
                        buf = np.zeros((h, w, 4), np.uint8)
                        buf[..., 0], buf[..., 1], buf[..., 2], buf[..., 3] = n % 256, 7, 9, 255
                        self.handlers["on_frame_arrived"](types.SimpleNamespace(frame_buffer=buf, width=w, height=h),
                                                          None)
                        buf[:] = 0                                        # "unmapped" after the callback
                        n += 1
                        time.sleep(0.01)
                    self.handlers["on_closed"]()

                threading.Thread(target=loop, daemon=True).start()
                return types.SimpleNamespace(stop=stop.set)

        self.module = types.SimpleNamespace(WindowsCapture=WindowsCapture)


def _with_lib(monkeypatch, lib):
    monkeypatch.setitem(sys.modules, "windows_capture", lib.module)


def test_capture_copies_the_requested_region(monkeypatch):
    lib = _FakeLib()
    _with_lib(monkeypatch, lib)
    cap = WindowCapture(1234)
    assert cap.start()
    assert lib.made[0] == {"window_hwnd": 1234, "cursor_capture": False, "draw_border": False,
                           "minimum_update_interval": 200}
    img = cap.grab(10, 5, 20, 8, expect_size=(64, 40))
    assert img is not None and img.shape == (8, 20, 3)         # BGR, requested region only
    assert (img[..., 1] == 7).all() and (img[..., 2] == 9).all()   # still valid after the callback
    cap.stop()
    time.sleep(0.05)
    assert cap.grab(0, 0, 4, 4) is None                         # stopped


def test_capture_falls_back_to_options_older_windows_accepts(monkeypatch):
    lib = _FakeLib(refuse={"minimum_update_interval", "draw_border"})
    _with_lib(monkeypatch, lib)
    cap = WindowCapture(1)
    assert cap.start()
    assert cap.options == {"cursor_capture": False}
    assert describe(cap, True) == "Fenster (WGC)"
    cap.stop()


def test_wrong_picture_size_is_not_used(monkeypatch):
    lib = _FakeLib(size=(64, 70))                               # e.g. with a title bar: pixels would be shifted
    _with_lib(monkeypatch, lib)
    cap = WindowCapture(1)
    cap.start()
    assert cap.grab(0, 0, 10, 10, expect_size=(64, 40)) is None
    assert cap.grab(0, 0, 10, 10, expect_size=(64, 40)) is None   # size known now: refused at once
    cap.stop()


def test_no_picture_in_time_returns_none(monkeypatch):
    lib = _FakeLib()
    _with_lib(monkeypatch, lib)
    cap = WindowCapture(1)
    cap.start()
    cap._on_frame = lambda frame: None                          # frames arrive but never answer
    # 1.28 (audit F12): what is waited for, not how long it took (no time limits on a shared runner)
    waits, real_wait = [], cap._got.wait

    def spy(timeout=None):
        waits.append(timeout)
        return real_wait(timeout)
    cap._got.wait = spy
    assert cap.grab(0, 0, 4, 4, timeout=0.1) is None
    assert waits == [0.1]                                       # the caller's timeout, once
    assert cap.grab(0, 0, 4, 4, timeout=0.1) is None             # right after a timeout: no waiting at all
    assert waits == [0.1]
    cap.stop()


def test_missing_package_reports_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "windows_capture", None)  # import fails
    cap = WindowCapture(1)
    assert not cap.start() and "windows-capture" in cap.error
    assert describe(None, True).startswith("Bildschirm")
    assert describe(None, False) == "Bildschirm"


def test_a_minimized_dbd_ends_the_window_capture(tmp_path, monkeypatch):
    """1.51.1 (review): the worker skipped the rest of the tick for a minimized DBD – before the place that stops
    the capture. A running capture went on copying pictures nobody looked at until DBD came back."""
    import queue
    from types import SimpleNamespace
    import numpy as np
    from fogscout import config, worker
    from fogscout.catalog import Catalog
    root = os.path.join(os.path.dirname(__file__), "..")
    made = []

    class FakeCapture:
        def __init__(self, hwnd):
            self.hwnd, self.closed, self.error, self.options, self.size = hwnd, False, "", {}, None
            self.running = False
            made.append(self)

        def start(self):
            self.running = True
            return True

        def grab(self, *a, **k):
            return None

        def stop(self):
            self.running = False

    class Grabber:
        def grab(self, left, top, width, height):
            return np.zeros((height, width, 3), np.uint8)

        def primary_monitor(self):
            return 0, 0, 1280, 720

    game = SimpleNamespace(hwnd=7, left=0, top=0, width=1280, height=720, minimized=False)
    monkeypatch.setattr(worker, "IS_WIN", True)
    monkeypatch.setattr(worker, "ScreenGrabber", Grabber)
    from fogscout import wincapture
    monkeypatch.setattr(wincapture, "WindowCapture", FakeCapture)          # the worker imports it when it starts
    monkeypatch.setattr(worker, "find_game_window", lambda known=None: game)
    monkeypatch.setattr(worker, "foreground_root", lambda: 99)             # another window in front
    monkeypatch.setattr(worker, "windows_above", lambda hwnd: [])
    monkeypatch.setattr(worker, "cursor_state", lambda: None)
    wk = worker.DetectionWorker(root, config.Settings(str(tmp_path / "settings.json")), Catalog(root, ["en"]),
                                queue.Queue(), data_dir=str(tmp_path))
    wk.start()
    try:
        deadline = time.time() + 30
        while not (made and made[0].running) and time.time() < deadline:
            time.sleep(0.05)
        assert made and made[0].running                                    # DBD in the background: captured
        game.minimized = True
        while made[0].running and time.time() < deadline:
            time.sleep(0.05)
        assert not made[0].running                                         # minimized: the capture ended
    finally:
        wk.stop()
        wk.join(timeout=10)


def test_a_region_outside_the_picture_is_no_picture_and_no_crash(monkeypatch):
    """CR-011 (code review): the window shrank between two looks – an empty slice made cv2 raise on the capture
    thread; now the answer is "no picture"."""
    lib = _FakeLib(size=(64, 40))
    _with_lib(monkeypatch, lib)
    cap = WindowCapture(1)
    cap.start()
    assert cap.grab(60, 0, 10, 10) is None                       # beyond the right edge
    assert cap.grab(-1, 0, 4, 4) is None
    img = cap.grab(0, 0, 4, 4)
    assert img is not None and img.shape == (4, 4, 3) and cap._out is None     # not kept after it was handed out
    cap.stop()
