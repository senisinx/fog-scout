"""Background thread: capture -> detect -> events for the UI thread."""
from __future__ import annotations

import collections
import contextlib
import logging
import os
import queue
import re
import threading
import time
import traceback
from dataclasses import dataclass

import cv2
import numpy as np

from . import __version__, bloodpoints, corpus, fsops, gamelang, loadouts, scorecount, scoreevents
from .capture import (IS_WIN, ImageSource, ScreenGrabber, cursor_state, find_game_window, foreground_root,
                      overlaps, windows_above)
from .i18n import _
from .detector import (ROI, Accumulator, BannerReader, OutOfMatchWatcher, currency_box, has_loading_bar, is_dark,
                       letterbox_rows)
from .layout import MIN_VBAR
from .lobby import LobbyReader, QueueTracker, SteadyCorner, corner_box, crossplay_box, crossplay_off, result_box
from .ticktime import CpuShare, LookTimes
from .matchstart import LOADING_LOOKS, MatchStart
from .matchend import MatchEndTracker, Signals
from .ocr import LazyRecognizer, ModelPool
from .textnorm import MAIN, MODEL_FILES, fold


def write_lossless(path: str, img) -> None:
    """1.57.24 (user: "Speichere die Debug-Bilder künftig als WebP" – a ZIP of the full-size looks ran over the 30 MB
    an upload takes): a debug picture as lossless WebP (Pillow, method 0 – measured on the loadouts test pictures:
    38–50 % smaller than PNG, ~70 ms instead of 30–50 ms; OpenCV's lossless WebP took 0.5–0.9 s). Same pixels."""
    from PIL import Image
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    pic = Image.fromarray(img[:, :, ::-1].copy() if img.ndim == 3 else img)
    pic.save(path, "WEBP", lossless=True, method=0, quality=0)

log = logging.getLogger("fogscout")
END_CHECK_INTERVAL = 0.5          # seconds between two looks for result screen / lobby / loading screen …
END_IDLE_INTERVAL = 1.0           # … and while nothing points to the end yet (whole-screen grab: ~14 MB each)
LOADOUT_INTERVAL = 0.5           # 1.57: seconds between two looks at the pause menu's loadouts (while it is open);
                                  # 1.57.14: 0.9 before – the user opens it for a second or two
                                  # 1.57.4: every whole-screen look (1 s) – before 1.5 s, a menu open for 2 s gave one
UI_WAIT_S = 8.0                   # 1.57.34: the first looks wait at most this long for the App's window
LOADOUT_LOOKS = 8                 # … and after this many looks of a round the board is known: no more looks
LOADOUT_LAST_AFTER = 2            # 1.57.4: after this many HUD looks the only one missing is looked for at the free row (1.57.7: 3 before)
LOADOUT_HUD_LOOKS = 40            # 1.57.1: looks for the portraits in the HUD after the menu (a hurt survivor's
                                  # portrait is covered for a while)
LOADOUT_HUD_INTERVAL = 0.5        # 1.57.7: seconds between two of those looks (a place counts after two agreeing ones;
                                  # 1 s before – the user found it far too slow)
LOADOUT_HUD_SLOW = 3.0            # 1.57.12: after those, one look every this many s until all are placed (a teammate
                                  # hooked, downed or hurt shows an icon instead of the portrait for minutes – 1.57.11
                                  # gave up after 40 looks)
LOADOUT_MENU_MISSES = 3           # 1.57.14: after this many menu looks without a board (a pointer over another screen) …
# 1.57.21 (user: "muss die Maus sichtbar sein? ich spiele meist mit Controller, da kommt nur so ein Kreis"): with a
# controller DBD draws its own cursor and the Windows pointer stays hidden – the pause menu is known by its "QUIT"
# bottom right as well (read by the round-end check anyway: "CONTINUE -70 „QUIT“" in the diagnoses), for this long
MENU_QUIT_HOLD_S = 1.5
LOADOUT_MENU_SLOW = 2.0           # … one look every this many s only
LOADOUT_SAME_ROUND_S = 90.0       # 1.57.14: a map shown again this soon after the round's start is the same round
LOADOUT_KEPT = 12                 # 1.57.11: debug pictures of menu / HUD looks kept (each)
IN_MATCH_RATE = 1.0               # scans per second while a detected map is being played (banner only at the start)
VBAR_STRIP_S = 1.0                # 1.8.65: without a map, a look at the bars above/below at most this often
BLACK_WARN_S = 8.0                # a black banner strip this long (DBD found) = "Aufnahme ist schwarz"
VBAR_LOOKS = 5                    # looks (1/s) whose smallest black bar above/below counts (dark scenes at the edge)
MID_MATCH_AFTER = 30.0            # s after the map appeared: a "banner" now is in the game world -> strict reading
MID_MATCH_SPAN = 2.0              # … and it must stay on screen this long (a real banner stands still for ~5 s,
                                  # light strips in the world move with the camera)
RESULT_MISSES_KEPT = 10           # 1.11.1: result screens without a role kept in debug/result
# 1.11.8 (user's crops: the category bar there, its words not yet): no role at the end → looks again this many seconds
# after it (the result screen fades its headers in after the bar)
ROLE_RETRY_S = (1.5, 3.0, 5.0)
SIGHTINGS_KEPT = 20               # mid-match sightings kept in debug/midmatch (picture + text each), newest first
# CR-001: the names our debug pictures are saved under (stamp, optional tag) – only these are ever pruned
DEBUG_NAME = re.compile(r"^\d{8}-\d{6}(?:-[\w.-]+)?\.(?:jpg|webp|png|txt)$", re.ASCII)
# 1.57.52 (user: score event live tracker, step 1 – full-size pictures to tune on): the score events DBD shows top right
# in a match (category word in white, "+points"/"MAX" in red below, category icon in a ring). The user's screenshots
# (16:9 viewport fractions): words x 0.83–0.96, three rows y 0.10–0.29 – the box leaves room for longer words and more rows
SCORE_BOX = (0.62, 0.06, 1.0, 0.50)   # x0, y0 (fraction of the height), x1, y1 – inside the 16:9 viewport
SCORE_KEPT = 120                  # newest pictures kept in debug/score
SCORE_SAVE_GAP_S = 1.0            # at most one a second
SCORE_WHITE = 0.0004              # share of near-white pixels (the words) …
SCORE_RED = 0.00004               # … and of red ones (the points) for "something is shown" (screenshots: ≥ 0.0011 / 0.00012)
# 1.57.56 (user: "Arbeite selbständig" – the live tracker): in a match the score corner is looked at between the ticks
# this often (own recordings: 4 looks/s 7 % off the official points by the sum alone, 2/s 11 %, 1/s 26 %); only the
# corner (973×634 at 1440p), ~29 ms per look with events
SCORE_INTERVAL = 0.25
GLOBE_KEPT = 10                   # 1.5.4: unreadable cross-play globe crops kept in debug/lobby
GLOBE_SAVE_EVERY = 120.0          # s between two saved crops (one per lobby is enough)
MENU_RATE = 1.0                   # 1.6.4: banner scans per second in menus, store, bloodweb … (no banner there)
FAST_AFTER_LOBBY = 120.0          # … full rate for this long after the lobby button was last on screen (READY → match)
FAST_AFTER_LOADING = 90.0         # … and after a loading screen was seen (the banner follows it)
START_LOOK_INTERVAL = 1.0         # 1.6: seconds between two looks for the end of the loading screen (armed only)
LOBBY_INTERVAL = 1.0              # seconds between two looks at the lobby button (never during a match)
SEARCH_INTERVAL = 3.0             # 1.38.37: … while a confirmed search shows CANCEL + EST. (the clock below the
                                  # button changes every second, so the corner is never steady: 207 ms OCR on
                                  # 112 of 120 looks, Windows diagnosis); any other button → LOBBY_INTERVAL again
LOBBY_RATE = 1.0                  # banner scans per second while the lobby button is on screen: the banner
TICK_FAIL_LIMIT = 30               # 1.8.38: ticks in a row that raise before the detection counts as crashed
TICK_FAIL_WAIT_S = 1.0            # … pause after one (no busy loop on a lasting fault)
TICK_FAIL_LOG_S = 60.0            # … the same traceback goes to the log at most this often
WORKER_RESTARTS = 2               # 1.38.9: a broken detection is started again this often before it counts as crashed
WORKER_RESTART_S = 5.0            # … after this pause (a display change or the lock screen may be over by then)
BP_STEADY_S = 5.0                 # 1.16.2 (A7): bloodpoint counter read this seldom once CONFIRM_LOOKS looks agree
# The banner follows the end of the loading screen within seconds: none decided (detected/unknown) this long after
# the match began → one hint to scan by hand per round (the worker never scans by itself)
BANNER_MISS_S = 60.0
BANNER_MISS_LATE_S = 15.0        # … a check this long after that time is about a match long over: no hint
LOBBY_HOLD = 3.0                  # only comes after the loading screen; full rate again 3 s after the button went


def _wgc_grab(cap, window, box):
    """``box`` (game-picture coordinates) from the window capture, or None. In window mode its pictures
    include title bar and frame: the game picture sits at an offset that depends on the picture size."""
    size = cap.size
    off = window.capture_offset(size) if size is not None else (0, 0)
    if off is None:
        return None
    return cap.grab(box[0] + off[0], box[1] + off[1], box[2], box[3],
                    expect_size=size or (window.width, window.height))


@dataclass
class Event:
    kind: str          # status | detected | unknown | banner | menu | match_end | watch_info | warn | scan_result | error
    data: dict


def lobby_interval(kind, state) -> float:
    """Seconds to the next look at the lobby button (pure, 1.38.37): SEARCH_INTERVAL while the last look showed the
    search the tracker has confirmed – nothing there is waited for but its end, and DBD's own counter keeps the
    waiting time exact (``QueueTracker`` takes the start from it) –, LOBBY_INTERVAL for everything else (PLAY,
    READY, the lobby countdown, a first search look still to be confirmed)."""
    return SEARCH_INTERVAL if kind == "search" and state == "search" else LOBBY_INTERVAL


def same_round_again(gen, previous, ended: bool, since_start: float) -> bool:
    """1.57.14: a map shown again (a new generation) still belongs to the round on display – the banner read a
    second time at the start, a layout picked: the round's loadouts stay. Not after its end, not after
    ``LOADOUT_SAME_ROUND_S`` (a new banner then is a new round)."""
    return gen is not None and previous is not None and not ended and since_start < LOADOUT_SAME_ROUND_S


def scan_rate(base: float, *, in_match: bool, session: bool, since_button: float, since_loading: float,
              live: bool, lobby_visible: bool) -> float:
    """Banner scans per second (pure, 1.6.4). Full rate while a banner is being read, after a loading screen and in
    the two minutes after the lobby button (READY, loading, spawn); 1/s in the match (banner only at its start), in
    the lobby (no banner possible) and everywhere else in the menus – there a banner is read at most a second late,
    after its first frame the session runs at full rate. Simulation (not live): full rate outside the match."""
    base = max(1.0, base)
    if session:
        return base
    if in_match:
        return min(base, IN_MATCH_RATE)
    if lobby_visible:
        return min(base, LOBBY_RATE)
    if not live or since_loading <= FAST_AFTER_LOADING or since_button <= FAST_AFTER_LOBBY:
        return base
    return min(base, MENU_RATE)


def score_box(fw: int, fh: int):
    """1.57.56: SCORE_BOX as (x, y, w, h) in a picture of fw×fh – the same cut as ``score_part``."""
    vw = min(fw, fh * 16 // 9)
    vx = (fw - vw) // 2
    x0, y0, x1, y1 = SCORE_BOX
    x, y = vx + int(x0 * vw), int(y0 * fh)
    return x, y, vx + int(x1 * vw) - x, int(y1 * fh) - y


def score_part(frame):
    """1.57.52: SCORE_BOX cut from ``frame`` (inside the 16:9 viewport, never the black bars); None when empty."""
    if frame is None or frame.ndim != 3 or not frame.size:
        return None
    h, w = frame.shape[:2]
    vw = min(w, h * 16 // 9)
    vx = (w - vw) // 2
    x0, y0, x1, y1 = SCORE_BOX
    part = frame[int(y0 * h):int(y1 * h), vx + int(x0 * vw):vx + int(x1 * vw), :3]
    return part if part.size else None


def score_shown(part) -> bool:
    """1.57.52: does ``part`` (BGR) seem to show score events – enough near-white (words) and red pixels (points)."""
    b, g, r = (part[:, :, i].astype(np.int16) for i in range(3))
    white = int(np.count_nonzero((b > 200) & (g > 200) & (r > 200)))
    red = int(np.count_nonzero((r > 170) & (g < 70) & (b < 70)))
    n = part.shape[0] * part.shape[1]
    return white >= SCORE_WHITE * n and red >= SCORE_RED * n


def _stamp() -> str:
    """Name stamp of a debug picture, "YYYYmmdd-HHMMSS-mmm", from ONE reading of the clock (1.57.54: seconds and
    milliseconds read apart could straddle a second – the name came out up to 1 s early, out of order, and pruning
    "the newest" kept the wrong pictures; CI saw a HUD look sort before the menu looks)."""
    now = time.time()
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"


def _debug_dir(data_dir, *sub):
    """Code review CR-001: the debug folder (``debug`` or ``debug/<sub>``) made and returned – None when it or
    ``debug`` is a link/junction (RS-002): the program runs with administrator rights and must neither write
    into nor prune a folder a program of the user swapped for a junction."""
    d = os.path.join(data_dir, "debug", *sub)
    levels = 1 + len(sub)
    if fsops.linked_root(d, levels):
        return None
    os.makedirs(d, exist_ok=True)
    return None if fsops.linked_root(d, levels) else d

def _prune_debug(d, names, keep):
    """CR-001: delete all but the newest ``keep`` of ``names`` (own stamped names only, ``DEBUG_NAME``) inside
    ``d`` – through ``fsops.delete_inside``, never a raw os.remove. ``keep`` 0 deletes them all."""
    own = sorted(n for n in names if DEBUG_NAME.match(n))
    for old in (own[:-keep] if keep else own):
        try:
            fsops.delete_inside(d, os.path.join(d, old))
        except OSError:
            pass


class DetectionWorker(threading.Thread):
    inputs_rect = None               # 1.39: the input card on screen (set by the UI; a default for bare instances)
    loadouts_rect = None             # 1.57: the survivors' loadouts on screen (the same)
    menu_open = False                # 1.57.2 (the same)
    fade_rects = ()                  # 1.55.6: windows still fading out (their *_rect is cleared already)

    def __init__(self, root_dir: str, settings, catalog, events: queue.Queue, simulate: str | None = None,
                 data_dir: str | None = None):
        super().__init__(daemon=True, name="detector")
        # 1.57.34 (user: "Weiter mit Optimierungen"): the looks (and the OCR models they load) wait until the App's
        # window is up – with DBD already running both shared the start (window 119–191 → ~97 ms on Linux) – at
        # most UI_WAIT_S; the App clears it before the start and sets it with its window. Without an App: set.
        self.ui_ready = threading.Event()
        self.ui_ready.set()
        self._born = time.monotonic()
        self.root_dir = root_dir
        self.data_dir = data_dir or root_dir     # 1.30.1: debug pictures go there (models stay in root_dir)
        self.settings = settings
        self.catalog = catalog
        self.events = events
        self.simulate = simulate
        self.commands: queue.Queue = queue.Queue()
        self.running = True
        self.map_on_screen = False       # set by the UI: a map is displayed (not hidden after a match)
        self.watch_gen = None            # set by the UI: (number, source) of the map on display
        self.overlay_rect = None         # set by the UI: overlay position on screen (x, y, w, h) or None
        self.hud_rect = None             # … and of the system values at the top of a bar
        self.media_rect = None           # … and of the music card ("Läuft gerade", 1.64)
        self.today_rect = None           # … and of "today" (its own card since 1.2.6)
        self.info_rect = None            # … and of the map's lines when they are their own element (1.8.24)
        self.inputs_rect = None          # … and of the input card (1.39)
        self.loadouts_rect = None        # … and of the survivors' loadouts (1.57)
        self.loadouts_wanted = False     # set by the UI: the loadouts are shown (1.57; 1.57.36 as the killer too)
        self.loadout_info = "–"          # 1.57: last look at the pause menu's loadouts (diagnosis)
        self.loadout_menu_info = "–"     # 1.57.11: … the last one at the menu itself (not the HUD / result)
        self.loadout_menu_tally = {}     # 1.57.16: the outcomes of this round's menu looks ("kein Raster": 8)
        self.loadout_state = "–"         # 1.57.11: … and why looks happen (diagnosis)
        self.menu_open = False           # 1.57.2: the pointer is visible over DBD in a round (a menu is open)
        self.prefetch = None             # 1.57.20: set by the App – decodes a found map's picture in this thread
        self.guide_rects = ()            # … and of the centre guide lines while moving (1.64.5)
        self.toast_rect = None           # … and of the notification window (1.8.13: F8 clip, lobby found)
        self.vbars = None                # (top, bottom, time, (w, h)): black bars above/below the picture
        self._vbar_looks = collections.deque(maxlen=VBAR_LOOKS)
        self._vbar_strip_t = 0.0
        self.watch_status = _("keine Map angezeigt")
        self.capture_info = "Bildschirm"                     # where the pictures come from (diagnosis)
        self.end_history = collections.deque(maxlen=80)     # for the diagnosis
        self.times = LookTimes()                             # 1.38.22: what each look costs (diagnosis)
        self.cpu = CpuShare()                                # … and this thread's CPU share
        self.queue = QueueTracker()                          # lobby: search / waiting time / role
        self.match_start = MatchStart()                      # 1.6: end of the loading screen (recording start)
        self.lobby_info = "–"                                # last look at the lobby button (diagnosis)
        self.bp_info = "–"                                   # 1.13: last look at the bloodpoint counter (diagnosis)
        self._bp_seen = (None, 0, -1e9, None)                # 1.16.2: (value, same in a row, last look, map gen)
        self.banner_history = collections.deque(maxlen=20)  # every banner-like sighting and its outcome (diagnosis)
        self.role_misses = collections.deque(maxlen=5)      # 1.11.1: result screens without a role read (diagnosis)
        self._scanner = None
        self._pool = None                 # CR-006: the other scripts' models, for the manual scan too
        self.recognizer = None            # 1.50.4: ocr.LazyRecognizer of the run (built once DBD is found)
        self._reported = set()
        self._report_logged = {}          # key -> (text, time): what _report last wrote to the log file
        self._fail_text, self._fail_logged = "", 0.0     # 1.8.38: last tick error logged, when
        self._broken = None                              # 1.38.9: why the current run gave up (None: it did not)
        self._last_frame_save = 0.0
        self._last_score_save = 0.0
        self.score_info = "–"                            # 1.57.56: the live score tracker for the diagnosis
        self._score = None                               # (gen, ScoreCounter) of the round on display
        self._score_stats = {"looks": 0, "shown": 0, "covered": 0, "ms": 0.0}
        self._last_sighting_save = 0.0
        self._banner_due = None          # when to hint "scan by hand" if no banner was decided since the match began

    # ------------------------------------------------------------- helpers
    def post(self, kind, **data):
        self.events.put(Event(kind, data))

    def stop(self):
        self.running = False
        self.commands.put(("stop",))

    def _nap(self, seconds: float):
        """1.8.84: wait like time.sleep, but a command (stop, scan, catalog) ends the wait at once – the
        command stays queued for the top of the next loop. Quitting no longer waits for a sleep to end."""
        try:
            self.commands.put(self.commands.get(timeout=max(0.0, seconds)))
        except queue.Empty:
            pass

    def request_scan(self):
        self.commands.put(("scan",))

    def set_catalog(self, catalog):
        self.commands.put(("catalog", catalog))

    def _banner_seen(self, t, strict, frames, acc, picture=None):
        """One line per banner-like sighting for the diagnosis: what was read and what came of it."""
        best = max(frames, key=lambda f: f[2]) if frames else ("", "", None)
        lead = acc.best()
        outcome = ("erkannt " + acc.decided[0] + (" (unsicher)" if acc.decided_unsure else "") if acc.decided
                   else "ignoriert" if strict and frames else "unbekannt" if frames else "kein Text")
        fit = "–" if best[2] is None else f"{best[2]:.1f}"
        like = f" · am ehesten {lead[0]} p={lead[1]:.2f}" if lead else ""
        self.banner_history.append(
            f"{time.strftime('%H:%M:%S', time.localtime(t))} {'mitten in der Runde' if strict else 'Rundenstart'} · "
            f"{len(frames)} Bilder, {acc.good_frames} lesbar · „{best[0]}“ / „{best[1]}“ Passung {fit}{like} "
            f"→ {outcome}" + (f" · Bild debug/midmatch/{picture}" if picture else ""))

    def _report(self, key, text):
        """An unexpected error: full text to the log file, one line to the UI (once per kind)."""
        # 1.50.5 (review): the looks call this about once a second – the same text goes to the file at most every
        # TICK_FAIL_LOG_S (before: a lasting fault wrote one traceback per second into a log without a size limit)
        now = time.time()
        last = self._report_logged.get(key)
        if last is None or last[0] != text or now - last[1] >= TICK_FAIL_LOG_S:
            self._report_logged[key] = (text, now)
            log.error(text)
        if key not in self._reported:
            self._reported.add(key)
            last = text.strip().splitlines()[-1] if text.strip() else key
            self.post("warn", text=f"{key}: {last}")

    def _tick_failed(self, text: str, fails: int) -> bool:
        """1.8.38: a tick raised (OCR, capture, a tracker …). The full text goes to the log (a repeated one at most
        every TICK_FAIL_LOG_S), the UI hears it once; the loop goes on with the next frame. False after
        TICK_FAIL_LIMIT ticks in a row: this run of the detection is broken – ``run`` decides (1.38.9: start again)."""
        now = time.time()
        if text != self._fail_text or now - self._fail_logged >= TICK_FAIL_LOG_S:
            self._fail_text, self._fail_logged = text, now
            self._report("Erkennung", text)
        if fails >= TICK_FAIL_LIMIT:
            self._broken = text
            return False
        return True

    # ---------------------------------------------------------------- loop
    def run(self):
        """1.38.9: a run that breaks (its setup raised, or TICK_FAIL_LIMIT ticks in a row) is started again up to
        WORKER_RESTARTS times after WORKER_RESTART_S – before, the detection stayed off until Fog Scout was
        restarted, also for a passing cause (a display change, the lock screen). Only the last failure is a crash."""
        broken = None
        for attempt in range(WORKER_RESTARTS + 1):
            self._broken = None
            try:
                self._run()
                broken = self._broken
            except Exception:
                broken = traceback.format_exc()
            if broken is None or not self.running:
                return                                   # stopped (quit) – nothing to report
            if attempt == WORKER_RESTARTS:
                break
            log.error("Erkennung abgebrochen, Neustart %d/%d:\n%s", attempt + 1, WORKER_RESTARTS, broken)
            self.post("warn", text=_("Erkennung neu gestartet ({n}/{total})", n=attempt + 1, total=WORKER_RESTARTS))
            self._nap(WORKER_RESTART_S)                  # stop() ends the wait at once
            if not self.running:
                return
        self.post("error", text=broken)

    def _run(self):
        models = os.path.join(self.root_dir, "models")
        # 1.50.4: the session is built once DBD is found (or a manual scan / simulation needs it) – a tray start
        # without the game holds no model
        rec = LazyRecognizer(os.path.join(models, MODEL_FILES[MAIN]), threads=self.settings.get("ocr_threads", 2))
        self.recognizer = rec
        # 1.49: the models of the other scripts (Cyrillic, Chinese/Japanese, Korean) – loaded only for a
        # game language that is ticked, or for a look at a banner nothing ticked can read (gamelang)
        pool = ModelPool(models, threads=self.settings.get("ocr_threads", 2),
                         on_error=lambda model, e: self._report(f"Modell {model}", f"{type(e).__name__}: {e}"))
        self._pool = pool
        reader = BannerReader(rec, self.catalog, pool)
        acc = Accumulator()
        out_of_match = OutOfMatchWatcher(rec)
        lobby_reader = LobbyReader(rec)
        loadout_reader = None             # 1.57: built at the first look at an open menu
        loadout_votes = loadouts.Votes()
        last_loadout = -1e9
        hud_looks = 0
        steady = self.lobby_steady = SteadyCorner()   # 1.38.14: an unchanged corner is not read again
        last_lobby = 0.0
        lobby_button_t = -1e9             # last look that saw PLAY / CANCEL / READY
        lobby_gap = LOBBY_INTERVAL        # 1.38.37: SEARCH_INTERVAL while a confirmed search is on screen
        last_start_look = -1e9            # 1.6: last look for the end of the loading screen
        last_loading = -1e9               # 1.6.4: last look that showed a loading screen (scan rate)
        source = ImageSource(self.simulate) if self.simulate else None
        grabber = None if source else ScreenGrabber()
        from .wincapture import CapturePolicy, WindowCapture, describe
        policy = CapturePolicy()          # window capture (WGC) while DBD is in the background
        wcap = None
        wcap_failed = None                # hwnd the window capture could not be started for
        wcap_told = False
        via = {"screen": True}            # last picture came from the screen (-> our overlay is in it)

        def from_screen() -> bool:
            """The last picture came from the screen – not the window capture, not a simulation – so our own
            windows may be in it (1.13.1: one place for the test every look makes before _mask_screen)."""
            return source is None and via["screen"]

        role_retry = None                 # 1.11.8: {"gen", "t", "due": [tick …], "crop", "text"} after a role-less end
        score_next = 0.0                  # 1.57.56: next look at the score corner
        self.hidden_looks = 0
        self.scan_rate = 0.0                                 # 1.6.4: banner scans per second right now (diagnosis)
        self._globe_saved = 0.0           # 1.5.4: last saved cross-play crop             # looks skipped: DBD in the background, another window over it

        window, window_checked = None, 0.0
        session, last_seen, session_frames = False, 0.0, []
        session_strict, session_t, session_saved = False, 0.0, None
        lang_votes = None                 # 1.48: {(code, map id): looks} of the banner on screen; None = said already
        lang_probes = 0                   # 1.49: looks of this banner the other scripts' models were asked for
        tracker = MatchEndTracker()
        tracker_gen = None
        trial_since = 0.0                 # when the map on display appeared (tracker reset)
        menu_misses = 0                   # 1.57.14: menu looks in a row without a board (another screen with a pointer)
        quit_t = -1e9                     # 1.57.21: when "QUIT" (the pause menu) was read last – a controller's menu
        round_since = 0.0                 # 1.57.14: … the round's first map (loadouts: shown again = same round)
        last_end_check = 0.0
        last_hist = 0.0
        last_status = None
        black_since = None
        capture_warn = None               # 1.55.3: black/failed capture – overrides "DBD gefunden" until a good look
        fails, failed = 0, False          # 1.8.38: ticks in a row that raised, did the last one

        while self.running:
            try:
                fails, failed = (fails if failed else 0), False   # a tick that ends in "continue" counts as fine
                tick = time.time()
                self.times.end()                 # 1.38.22: the previous look's steps (sum, without the sleep)
                self.times.start()
                self.cpu.note(tick, time.thread_time())
                # --------------------------------------------------- commands
                try:
                    while True:
                        cmd = self.commands.get_nowait()
                        if cmd[0] == "stop":
                            self.running = False
                            break
                        if cmd[0] == "catalog":
                            self.catalog = cmd[1]
                            reader = BannerReader(rec, self.catalog, pool)
                            pool.drop(keep=self.catalog.models)      # a model only a probe needed
                            acc.reset()
                            if self._scanner:
                                self._scanner = None
                        if cmd[0] == "scan":
                            self._manual_scan(rec, grabber, source, window, wcap)
                except queue.Empty:
                    pass
                if not self.running:
                    break                        # 1.8.38: not return – the capture below is closed
                if not self.ui_ready.is_set() and time.monotonic() - self._born < UI_WAIT_S:
                    self._nap(0.1)               # 1.57.34: the window is being built – no look yet
                    continue

                # 1.16.2 (A7): the whole picture of this tick, when the look for the loading screen takes one anyway
                # (menus and lobby, once a second) – banner strip, lobby corner, globe and currency bar are cut from
                # it instead of being grabbed one by one (up to 5 grabs; with the window capture each waits for a
                # new picture). Same pixels, one moment; covered or failed → the parts are grabbed as before.
                shot = []
                # --------------------------------------------- where is DBD?
                if source is None and tick - window_checked > 1.5:
                    with self.times.measure("window"):
                        window = find_game_window(window)   # 1.34.1 (P4): the known window checked first
                    window_checked = tick
                # 1.55.6 (audit D-5): with the automatic detection off only a map on display needs the model here (its
                # round end); a manual scan or any other look builds it on first use
                auto = bool(self.settings.get("auto_detect", True))
                if (source is not None or (window is not None and (auto or self.map_on_screen))) and not rec.built:
                    rec.load()                       # 1.50.4: built here, before the first look needs it
                if auto and (source is not None or window is not None):
                    reader.load()                    # 1.55.6 (D-4): the other scripts' models (ticked ones) the same way
                if source is not None:
                    frame = source.current()
                    if frame is None:
                        self._nap(0.5)
                        continue
                    fh, fw = frame.shape[:2]
                    status = f"Simulation: {os.path.basename(self.simulate)}"
                    grab = self.times.timed("grab", lambda box: frame[box[1]:box[1] + box[3], box[0]:box[0] + box[2]])
                    origin = (0, 0)
                else:
                    if window is not None and window.minimized:
                        if wcap is not None:           # 1.51.1 (review): a minimized DBD is not looked at – the
                            wcap.stop()                # capture went on copying its pictures (the stop below is
                            wcap = None                # never reached from here)
                            self.capture_info = describe(None, False)
                        capture_warn = None
                        self._status(_("DBD ist minimiert"), last_status, problem=True)
                        last_status = _("DBD ist minimiert")
                        self._nap(0.5)
                        continue
                    if window is not None and window.width > 100 and window.height > 100:
                        origin = (window.left, window.top)
                        fw, fh = window.width, window.height
                        status = _("DBD gefunden ({w}×{h}) – warte auf Map-Banner", w=fw, h=fh)
                    else:
                        # no DBD: no automatic detection – a DBD video or screenshot on the desktop must not open
                        # the overlay over other work ("Scannen" still looks at the main screen)
                        ml, mt, mw, mh = grabber.primary_monitor()
                        origin, fw, fh = (ml, mt), mw, mh
                        status = _("DBD nicht gefunden – Erkennung startet, sobald DBD läuft")
                    # ---- DBD in the background: take its picture from Windows instead of the screen
                    win_ok = source is None and window is not None and not window.minimized and window.width > 100
                    fg_now = win_ok and foreground_root() == window.hwnd
                    if policy.update(tick, IS_WIN and bool(self.settings.get("window_capture", True)), win_ok, fg_now):
                        if wcap is not None and (wcap.hwnd != window.hwnd or wcap.closed):
                            if wcap.closed and wcap.hwnd == window.hwnd:
                                wcap_failed = window.hwnd           # ended by itself: do not restart every tick
                            wcap.stop()
                            wcap = None
                        if wcap is None and wcap_failed != window.hwnd:
                            wcap = WindowCapture(window.hwnd)
                            if wcap.start():
                                if not wcap_told:
                                    wcap_told = True
                                    self.post("watch_info", text=_("DBD im Hintergrund – Fensteraufnahme aktiv: die Map "
                                                                   "wird auch erkannt, wenn andere Fenster darüber "
                                                                   "liegen."))
                            else:
                                self.post("warn", text=_("Fensteraufnahme nicht möglich, nutze Bildschirmaufnahme "
                                                         "({error})", error=wcap.error))
                                wcap_failed, wcap = window.hwnd, None
                    elif wcap is not None:
                        wcap.stop()
                        wcap = None
                    self.capture_info = describe(wcap, policy.active)
                    if wcap is not None and via["screen"]:
                        self.capture_info += " · letztes Bild vom Bildschirm (Fensteraufnahme ohne Bild)"
                    if self.hidden_looks:
                        self.capture_info += f" · {self.hidden_looks}× verdeckt, ausgelassen"
                    covers = []                       # windows over DBD (looked up once per tick, when needed)

                    def grab(box, _o=origin, _cap=wcap, _win=window, _fg=fg_now, _covers=covers, _shot=shot):
                        """Part of the game picture, or None: DBD is in the background, the window capture had
                        no picture and another window lies over that part of the screen (e.g. our own
                        statistics) – then nothing is read rather than someone else's pixels. 1.16.2 (A7): a
                        copy out of this tick's whole picture when one was taken (see ``shot``)."""
                        if _shot:
                            whole = _shot[0]
                            x, y, w, h = box
                            if x >= 0 and y >= 0 and x + w <= whole.shape[1] and y + h <= whole.shape[0]:
                                return whole[y:y + h, x:x + w].copy()
                        if _cap is not None and _win is not None:
                            img = _wgc_grab(_cap, _win, box)
                            if img is not None:
                                via["screen"] = False
                                return img
                        via["screen"] = True
                        rect = (_o[0] + box[0], _o[1] + box[1], box[2], box[3])
                        if _win is not None and not _fg:
                            if not _covers:
                                _covers.append(windows_above(_win.hwnd))
                            if overlaps(rect, _covers[0]):
                                self.hidden_looks += 1
                                return None
                        return grabber.grab(*rect)
                    grab = self.times.timed("grab", grab)

                if not self.settings.get("auto_detect", True):
                    status = _("Automatische Erkennung ist aus")
                if not (self.settings.get("auto_detect", True) and (source is not None or window is not None)):
                    capture_warn = None          # no banner look this tick: nothing left to warn about
                # 1.55.3: one status per tick – a black or failed capture stays the status until a good look (it
                # alternated with "DBD gefunden" every tick before: two log lines a second)
                shown = capture_warn or status
                if shown != last_status:
                    self._status(shown, last_status, problem=bool(capture_warn))
                    last_status = shown
                sep = None
                # 1.55.6 (D-5): only with the automatic detection – the lobby look arms the match start, and without it
                # the whole picture once a second was taken for nothing
                start_due = (auto and not self.map_on_screen and not session
                             and tick - last_start_look >= START_LOOK_INTERVAL
                             and (source is not None or window is not None))
                whole_tried = False
                if start_due and source is None:
                    try:
                        whole = grab((0, 0, fw, fh))
                        whole_tried = True
                    except Exception:            # e.g. window moved off-screen: the grabs below say it
                        whole = None
                    if whole is not None:
                        shot.append(whole)
                # 1.34.1 (review P3): in a match the round-end look takes the whole picture about once a second –
                # taken first, the banner strip is cut from it (one grab, with the window capture one wait, instead
                # of two). Due exactly as below (same tracker state; not on the tick the map changes); a banner
                # seen leaves it unused, as the look below needs no banner.
                end_tried = False
                if (source is None and not shot and window is not None and self.map_on_screen
                        and self.watch_gen is not None and self.watch_gen == tracker_gen
                        and tracker.active and not tracker.ended
                        and (self.settings.get("hide_after_match", True) or self.settings.get("pause_in_menus", True))
                        and tick - last_end_check >= (END_CHECK_INTERVAL if tracker.candidate else END_IDLE_INTERVAL)):
                    try:
                        whole = grab((0, 0, fw, fh))
                        end_tried = True
                    except Exception:            # the look below grabs (and reports) itself
                        whole = None
                    if whole is not None:
                        shot.append(whole)
                if self.settings.get("auto_detect", True) and (source is not None or window is not None):
                    # ------------------------------------------------ banner search
                    box = (int(ROI[0] * fw), int(ROI[1] * fh), int((ROI[2] - ROI[0]) * fw), int((ROI[3] - ROI[1]) * fh))
                    try:
                        img = grab(box)
                    except Exception as e:           # e.g. window moved off-screen
                        capture_warn = _("Bildschirmaufnahme fehlgeschlagen: {error}", error=e)
                        self._status(capture_warn, last_status, problem=True)
                        last_status = capture_warn
                        self._nap(1.0)
                        continue
                    if img is not None and img.size and sum(cv2.mean(img)[:3]) < 3.0 and window is not None:
                        black_since = black_since or tick
                        capture_warn = (_("Aufnahme ist schwarz – DBD im Modus „Fenster-Vollbild“ betreiben")
                                        if tick - black_since > BLACK_WARN_S else None)
                    else:
                        black_since = None
                        capture_warn = None
                    shown = capture_warn or status        # 1.55.3: the grab worked – a failure warning ends here
                    if shown != last_status:
                        self._status(shown, last_status, problem=bool(capture_warn))
                        last_status = shown

                    if img is None:
                        sep = res = None                # covered by another window: nothing of DBD to read
                    else:
                        self._mask_screen(img, from_screen(), origin[0] + box[0], origin[1] + box[1])
                        if not self.map_on_screen:
                            self._vbar_strip(grab, fw, fh, tick, origin, from_screen)
                        boxed = self._letterboxed(fw, fh)
                        # 1.8.62: without a line, read at the banner's spot – not well into a round (game world)
                        mid = self.map_on_screen and tracker.in_trial and tick - trial_since >= MID_MATCH_AFTER
                        bars = self._vbar_looks[-1][:2] if boxed and not mid else None
                        with self.times.measure("banner"):
                            sep, res = reader.read(img, fw, fh, letterboxed=boxed, bars=bars)
                    if sep is not None:
                        if not session:
                            session, session_frames, session_t, session_saved = True, [], tick, None
                            lang_votes, lang_probes = {}, 0
                            # DBD shows the banner only at the start of a trial: well into a running round it is
                            # something in the game world (neon strips, signs) – only a clean read may switch
                            session_strict = (self.map_on_screen and tracker.in_trial
                                              and tick - trial_since >= MID_MATCH_AFTER)
                            acc.reset()
                            if not session_strict:
                                self.post("banner", t=tick)
                        last_seen = tick
                        if res is not None:
                            session_frames.append((res.name_text, res.realm_text, res.name_fit))
                            d = acc.add(res, strict=session_strict,
                                        hold=session_strict and tick - session_t < MID_MATCH_SPAN)
                            if session_strict and (d is not None or (session_saved is None
                                                                     and tick - self._last_sighting_save >= 10)):
                                # always kept (no debug switch needed): the only way to see what fooled the reader
                                self._last_sighting_save = tick
                                session_saved = self._save_sighting(img, res, sep, "umgeschaltet" if d else "gesehen")
                            if (d is None and not session_strict and lang_votes is not None
                                    and self.settings.get("game_lang_auto", True)):
                                maps_, active = self.catalog.maps.values(), set(self.catalog.languages)
                                hit = gamelang.vote(lang_votes, res.name_text, res.realm_text, maps_, active)
                                if hit is None and res.name_fit < acc.fit_ok:
                                    # 1.49: another script? From the second look nothing ticked can read (the
                                    # first is often the banner fading in) the models of the scripts not in use
                                    # read the same two lines – PROBE_LOOKS times per banner, then never again
                                    lang_probes += 1
                                    if 2 <= lang_probes <= 1 + gamelang.PROBE_LOOKS:
                                        for name_text, realm_text in reader.probe():
                                            hit = hit or gamelang.vote(lang_votes, name_text, realm_text,
                                                                       maps_, active)
                                if hit is not None:      # 1.48: the App ticks the language, a new catalog follows
                                    # 1.49.1: the text first, then "said already" – the other way round this
                                    # raised on None and no language was ever named (1.49)
                                    read_as = lang_votes.get("text") or res.name_text
                                    lang_votes = None
                                    self.post("game_language", code=hit[0], map_id=hit[1], name_text=read_as)
                            if d is not None:
                                lobby = self.queue.lobby_for_round(tick)   # 1.8.71: also a lobby seen only briefly
                                self.queue.round_started(tick)  # 1.8.43: the lobby is used up (same custom lobby next)
                                self._banner_due = None
                                if self.prefetch is not None:   # 1.57.20 (user: "alles schnell"): the picture is
                                    try:                        # decoded here, the window thread only takes it
                                        self.prefetch(d.map_id, d.variant)
                                    except Exception:
                                        log.debug("Kartenbild vorab: %s", traceback.format_exc())
                                self.post("detected", lobby=lobby, map_id=d.map_id, variant=d.variant, probability=d.probability,
                                          variant_probability=d.variant_probability, name_text=d.name_text,
                                          realm_text=d.realm_text, frames=d.frames, name_fit=d.name_fit,
                                          unsure=d.unsure, latency=max(0.0, tick - session_t))
                                if self.settings.get("corpus_save", True):     # 1.38.29: the banner for "Erkennung prüfen"
                                    try:
                                        corpus.save(self.data_dir, img, sep, res, d, (fw, fh), boxed, bars,
                                                    self.settings.get("languages") or [], __version__)
                                    except Exception:
                                        log.exception("Korpus")
                            if self.settings.get("save_debug_images"):
                                self._save_debug(img, res, sep)
                    elif session and tick - last_seen > 1.5:
                        session = False
                        pool.drop(keep=self.catalog.models)          # 1.49: models only a probe loaded
                        self._banner_seen(session_t, session_strict, session_frames, acc, session_saved)
                        if acc.decided is None and session_frames:
                            best = max(session_frames, key=lambda f: f[2])
                            if session_strict:            # mid-match: only a note in the log, no "unknown map" bar
                                lead = acc.best()
                                self.post("ignored", name_text=best[0], realm_text=best[1],
                                          map_id=lead[0] if lead else None, name_fit=best[2], frames=acc.good_frames)
                            else:
                                self._banner_due = None
                                self.post("unknown", name_text=best[0], realm_text=best[1])

                # ------------------------------------- lobby: searching / found / role (never in a match)
                if (self.settings.get("auto_detect", True) and sep is None and not session
                        and tick - last_lobby >= lobby_gap and (source is not None or window is not None)
                        and not (self.map_on_screen and tracker.in_trial)):
                    last_lobby = tick
                    try:
                        cb = corner_box(fw, fh)
                        corner = grab(cb)
                        if corner is not None:
                            self._mask_screen(corner, from_screen(), origin[0] + cb[0], origin[1] + cb[1])
                            view = steady.reuse(corner, tick)
                            same = view is not None
                            if view is None:
                                with self.times.measure("lobby"):
                                    view = lobby_reader.read(corner, fw, fh)
                                steady.remember(corner, view, tick)
                            if view.button is not None:
                                lobby_button_t = tick
                                # 1.2.20: the cross-play globe above the button (farming rounds) – a second small grab
                                xb = crossplay_box(fw, fh)
                                globe = grab(xb)
                                if globe is not None:
                                    self._mask_screen(globe, from_screen(), origin[0] + xb[0], origin[1] + xb[1])
                                    with self.times.measure("lobby"):
                                        view.crossplay_off = crossplay_off(globe, fw, fh)
                                    if view.crossplay_off is None and tick - self._globe_saved > GLOBE_SAVE_EVERY:
                                        self._globe_saved = tick    # 1.5.4 (user: farming not recognised): keep the
                                        self._save_globe(globe, view.button)   # unreadable crop for a look
                                # 1.13: the bloodpoint counter top right – before and after a round (cap reached?)
                                if self._bp_due(tick):
                                    self._bp_look(grab, fw, fh, tick, origin, from_screen(), out_of_match)
                            fit = "–" if view.fit is None else f"{view.fit:.1f}"
                            cross = {True: " · Crossplay aus", False: " · Crossplay an"}.get(view.crossplay_off, "")
                            self.lobby_info = (f"{view.button or '–'} ({fit}) "
                                               f"„{view.name}“ „{view.time_text}“ → {view.kind or '–'}{cross}"
                                               + (" · unverändert" if same else ""))
                            for ev in self.queue.update(view, tick):
                                self._queue_event(ev, tick)
                            lobby_gap = lobby_interval(view.kind, self.queue.state)
                    except Exception:
                        self._report("Lobby-Erkennung", traceback.format_exc())

                # ------------------------------------- 1.6: loading screen over -> the match begins (recording)
                # 1.6.4: also unarmed – a loading screen tells the scan rate that a banner is coming
                ms = self.match_start
                if self.map_on_screen and ms.armed:
                    ms.disarm()                          # a banner came first: the recording starts there
                elif start_due and sep is None:
                    last_start_look = tick
                    try:
                        if whole_tried:                  # taken above (None: covered – not grabbed twice)
                            look = shot.pop() if shot else None
                        else:
                            look = grab((0, 0, fw, fh))
                        if look is not None:             # None: covered -> no look, nothing changes
                            self._mask_screen(look, from_screen(), origin[0], origin[1])
                            bar = has_loading_bar(look)
                            # 1.34.1 (review P7): "dark" counts only with the bar, or after the loading screen
                            # (black before the match) – any other look never reads it
                            dark = bool((bar or (ms.armed and ms.loading >= LOADING_LOOKS)) and is_dark(look))
                            if bar and dark:
                                last_loading = tick
                            if ms.armed and ms.update(tick, bar, dark, tick - lobby_button_t < START_LOOK_INTERVAL * 1.5):
                                log.info("Ladebildschirm vorbei – das Match beginnt")
                                self.post("match_start", t=tick)
                                found = self.queue.found          # the lobby that armed it (custom known here)
                                self._banner_due = (None if found is not None and found.custom
                                                    else tick + BANNER_MISS_S)
                    except Exception:
                        self._report("Matchbeginn", traceback.format_exc())
                self._banner_check(tick, session, auto and (source is not None or window is not None))

                # ------------------------------------- left the trial? -> hide map
                gen = self.watch_gen
                if gen != tracker_gen:
                    # 1.57.14 (user: "ich öffne oft das Menü, wenn ich in die Runde lade"): the banner is often read
                    # twice at the start (23:02:37 and 23:02:41) and each shown map is a new generation – the
                    # loadouts read in between were thrown away. Shown again early in a round not ended: the same
                    # round, its survivors stay (and are posted for the new generation)
                    same_round = same_round_again(gen, tracker_gen, tracker.ended, tick - round_since)
                    self._score_round(gen, same_round)
                    tracker.reset(gen[0] if gen else None, gen[1] if gen else None, tick)
                    tracker_gen = gen
                    trial_since = tick
                    if same_round:
                        if loadout_votes.looks:
                            self.post("loadouts", gen=gen, board=loadout_votes.board())
                    else:
                        loadout_votes.reset()     # 1.57: a new map, a new round – other survivors
                        self.loadout_menu_tally = {}
                        hud_looks = 0
                        round_since = tick
                use_end = bool(self.settings.get("hide_after_match", True))
                use_menu = bool(self.settings.get("pause_in_menus", True))
                watching = (self.map_on_screen and gen is not None and (use_end or use_menu)
                            and tracker.active and not tracker.ended)
                if not watching:
                    self.menu_open = False
                if watching:
                    tracker.use_end, tracker.use_cursor = use_end, use_menu
                    if source is not None:                       # simulation: no window, no pointer
                        game, foreground, pointer = True, True, None
                    else:
                        game = window is not None
                        foreground = game and foreground_root() == window.hwnd
                        pointer = None
                        if foreground:
                            cur = cursor_state()
                            if cur is not None:
                                vis, cx, cy = cur
                                pointer = vis and (window.left <= cx < window.left + window.width
                                                   and window.top <= cy < window.top + window.height)
                    obs = full = look = None
                    paused = bool(pointer) or (foreground and tick - quit_t <= MENU_QUIT_HOLD_S)   # 1.57.21
                    interval = END_CHECK_INTERVAL if tracker.candidate else END_IDLE_INTERVAL
                    if (self.loadouts_wanted and loadout_votes.looks and not loadout_votes.placed
                            and not paused and source is None and hud_looks < LOADOUT_HUD_LOOKS):
                        interval = min(interval, LOADOUT_HUD_INTERVAL)      # 1.57.7: the HUD looks after the menu
                    # 1.57.14 (user: "sobald die Karte anzeigt, öffne ich das Menü"): with the menu open a look every
                    # LOADOUT_INTERVAL – also while the start banner is still seen (no look was taken then, and the
                    # end check took one a second only); a few menu looks without a board: slower
                    menu_due = bool(self.loadouts_wanted and paused and source is None
                                    and loadout_votes.looks < LOADOUT_LOOKS)
                    if menu_due:
                        interval = min(interval, LOADOUT_INTERVAL if menu_misses < LOADOUT_MENU_MISSES
                                       else LOADOUT_MENU_SLOW)
                    else:
                        menu_misses = 0
                    if ((sep is None or menu_due) and tick - last_end_check >= interval
                            and (game or source is not None)):
                        last_end_check = tick
                        try:
                            if end_tried:                        # taken above (None: covered – not again)
                                full = look = shot.pop() if shot else None
                            else:
                                full = look = grab((0, 0, fw, fh))
                            if look is not None:                 # None: covered -> no observation, nothing changes
                                ignore = self._mask_screen(look, from_screen(), origin[0], origin[1])   # in place: no 14 MB copy
                                if sep is None:                  # with the banner seen only the menu is read
                                    with self.times.measure("end"):
                                        obs = out_of_match.observe(look, ignore)
                                self._note_vbars(look, fw, fh)
                        except Exception:
                            self._report("Rundenende-Prüfung", traceback.format_exc())
                    # 1.57: the pause menu shows the other survivors' loadouts – read while it is open (the
                    # pointer is visible over DBD), a few looks per round (1.57.36: as the killer too – the
                    # survivors' offerings); 1.57.1: once the menu is shut, their portraits are looked for in the HUD's survivor list (where to draw them)
                    if obs is not None and foreground and "QUIT" in fold(obs.continue_text or ""):
                        quit_t = tick                     # 1.57.21: the pause menu without a pointer (controller)
                    paused = bool(pointer) or (foreground and tick - quit_t <= MENU_QUIT_HOLD_S)
                    menu_open = paused or (source is not None)
                    self.menu_open = bool(paused)         # 1.57.2: the App hides the loadouts meanwhile
                    due = tick - last_loadout >= (LOADOUT_HUD_INTERVAL if not menu_open else LOADOUT_INTERVAL)
                    # 1.57.11 (user's diagnosis: a menu look, then nothing for five minutes): why a look happens or not
                    self.loadout_state = (f"gewünscht={self.loadouts_wanted} Map={gen is not None} "
                                          f"Bild={look is not None} Menü offen={bool(menu_open)} "
                                          f"Menü-Blicke {loadout_votes.looks}/{LOADOUT_LOOKS} "
                                          f"HUD-Blicke {hud_looks}/{LOADOUT_HUD_LOOKS} alle platziert={loadout_votes.placed}")
                    if look is not None and self.loadouts_wanted and gen is not None and due:
                        try:
                            if menu_open and loadout_votes.looks < LOADOUT_LOOKS:
                                last_loadout = tick
                                if loadout_reader is None:
                                    loadout_reader = loadouts.Reader()
                                with self.times.measure("loadouts"):
                                    # 1.57.29: names only for alike portraits, only in memory (never logged)
                                    board = loadout_reader.read(look, text=lambda img: rec.text(rec.probs(img)))
                                self.loadout_info = f"{time.strftime('%H:%M:%S')} {loadout_reader.last}"
                                menu_misses = 0 if board is not None else menu_misses + 1
                                outcome = "gelesen" if board is not None else loadout_reader.last.split(", ")[-1]
                                self.loadout_menu_tally[outcome] = self.loadout_menu_tally.get(outcome, 0) + 1
                                if board is not None and loadout_votes.note(board):
                                    self.post("loadouts", gen=gen, board=loadout_votes.board())
                                # 1.57.11 (user's diagnosis showed only the result screen's look): the last look
                                # at the menu itself – what each row read this time, then the round's votes
                                read = " ".join(f"{sum(1 for p in r.perks if p)}/4" for r in board.rows) \
                                    if board is not None else "–"
                                self.loadout_menu_info = (f"{time.strftime('%H:%M:%S')} Menü-Blick "
                                                          f"{loadout_votes.looks}: {loadout_reader.last} · "
                                                          f"dieser Blick Perks {read} · {loadout_votes.describe()}")
                                if self.settings.get("save_debug_images"):
                                    self._save_loadout_look(look, "menu")
                            elif (not menu_open and loadout_votes.looks and not loadout_votes.placed
                                  and (hud_looks < LOADOUT_HUD_LOOKS or tick - last_loadout >= LOADOUT_HUD_SLOW)):
                                last_loadout, hud_looks = tick, hud_looks + 1
                                finder = loadouts.HudFinder()
                                with self.times.measure("loadouts"):
                                    grid = loadouts.list_grid(look.shape[1], look.shape[0])
                                    # 1.57.32: once DBD's list was seen, only its column is searched
                                    box = (loadouts.list_box(grid, look.shape[1], look.shape[0])
                                           if loadout_votes.list_seen else None)
                                    found = finder.find(look, loadout_votes.faces(), loadout_votes.side,
                                                        loadout_votes.scales(look.shape[0]), box=box)
                                    changed = loadout_votes.place(found, grid)
                                    rows = loadout_votes.name_rows(grid)
                                    if rows:                  # 1.57.29: alike portraits – their names below them
                                        gx, gy, step, side = grid
                                        read = {}
                                        for k in rows:
                                            cut = loadouts.name_box(look, loadouts.hud_name_box(
                                                (gx, gy + k * step, side), look.shape[1], look.shape[0]))
                                            if cut is not None:
                                                read[k] = rec.text(rec.probs(cut))
                                        changed |= loadout_votes.place_by_names(read, grid)
                                    miss = loadout_votes.missing() if hud_looks >= LOADOUT_LAST_AFTER else None
                                    if miss:              # 1.57.4: the last one, only at the free row(s)
                                        face = loadout_votes.faces().get(miss[0])
                                        changed |= loadout_votes.place_last(
                                            miss[0], {c: loadouts.score_at(look, face, c) for c in miss[1]})
                                self.loadout_info = (f"{time.strftime('%H:%M:%S')} HUD-Blick {hud_looks}: "
                                                     f"{loadout_votes.describe(getattr(finder, 'scores', {}))}")
                                if self.settings.get("save_debug_images"):
                                    self._save_loadout_look(look, "hud")
                                if changed:
                                    self.post("loadouts", gen=gen, board=loadout_votes.board())
                        except Exception:
                            self._report("Loadouts", traceback.format_exc())
                    events = tracker.update(Signals(t=tick, game=game, foreground=foreground, cursor=pointer,
                                                    banner=sep is not None, obs=obs))
                    self.watch_status = tracker.describe()
                    interesting = obs is not None and (obs.reason or obs.continue_fit is not None
                                                       or obs.currency_groups or obs.loading)
                    if interesting or events or (obs is not None and tick - last_hist > 30):
                        last_hist = tick
                        ptr = "–" if pointer is None else ("sichtbar" if pointer else "verborgen")
                        line = (f"{time.strftime('%H:%M:%S')} {obs.describe() if obs else '(kein Bild)'} · "
                                f"Maus {ptr} · DBD aktiv {'ja' if foreground else 'nein'} · {tracker.describe()}")
                        if events:
                            line += " · " + ", ".join(e[0] + (f"={e[1]}" if len(e) > 1 else "") for e in events)
                        self.end_history.append(line)
                        if interesting or events:
                            log.info("Rundenende: %s", line)
                    if full is not None and self.settings.get("save_debug_images"):
                        tag = ("ende" if any(e[0] == "match_end" for e in events) else
                               "menue" if events else "hinweis" if interesting else None)
                        if tag or tick - self._last_frame_save > 5:
                            self._save_frame(full, tag or "runde")
                        if not events and tick - self._last_score_save >= SCORE_SAVE_GAP_S:
                            self._save_score_look(full, tick)
                    for ev in events:
                        if ev[0] == "menu":
                            self.post("menu", on=ev[1], gen=tracker.generation)
                        elif ev[0] == "match_end":
                            role = None
                            if look is not None and ev[1] == "Ergebnisbildschirm":
                                try:     # categories BRUTALITY … / OBJECTIVES … (our overlay blacked out: 2 of 4 words do)
                                    rx, ry, rw, rh = result_box(fw, fh)
                                    crop = look[ry:ry + rh, rx:rx + rw]
                                    role = lobby_reader.result_role(crop)
                                    if role is None:     # 1.11.8: look again in a moment (1.11.1: kept then)
                                        role_retry = {"gen": tracker.generation, "t": tracker.end_t,
                                                      # 1.46.4: a copy – the view kept the whole frame
                                                      # (~15 MB) alive until the last retry
                                                      "due": [tick + s for s in ROLE_RETRY_S], "crop": crop.copy(),
                                                      "text": getattr(lobby_reader, "last_result_text", "")}
                                except Exception:
                                    self._report("Rolle", traceback.format_exc())
                            self._score_final(tracker.generation)          # 1.57.56: the round's points first
                            self.post("match_end", reason=ev[1], gen=tracker.generation, t=tracker.end_t, role=role)
                        elif ev[0] == "armed" and tracker.source != "auto":
                            self.post("watch_info", text=_("Rundenende-Erkennung für die gewählte Map ist jetzt aktiv."))
                        elif ev[0] == "cursor_unreliable":
                            self.post("watch_info", text=_("Mauszeiger war beim Map-Banner sichtbar – Menü-Erkennung "
                                                           "per Mauszeiger ist für diese Runde aus."))
                elif not (use_end or use_menu):
                    self.watch_status = _("aus (Einstellung)")
                elif tracker.ended and self.map_on_screen:
                    self.watch_status = tracker.describe()
                elif not self.map_on_screen:
                    self.watch_status = (_("Runde vorbei – wartet auf die nächste Map") if tracker.ended
                                         else _("keine Map angezeigt"))

                if role_retry is not None and role_retry["due"] and tick >= role_retry["due"][0]:
                    role_retry = self._role_again(role_retry, tick, grab if (window is not None or source is not None)
                                                  else None, fw, fh, origin, via, source, lobby_reader)

                in_match = self.map_on_screen and tracker.in_trial
                rate = scan_rate(float(self.settings.get("scans_per_second", 5)), in_match=in_match, session=session,
                                 since_button=tick - lobby_button_t, since_loading=tick - last_loading,
                                 live=source is None,
                                 lobby_visible=tick - lobby_button_t < LOBBY_HOLD + lobby_gap - LOBBY_INTERVAL)
                if in_match and not session and watching and "Scan/s" not in self.watch_status:
                    self.watch_status += f" · {IN_MATCH_RATE:.0f} Scan/s"
                if source is None and window is None:
                    rate = 1.0                               # no DBD: only looking for its window
                self.scan_rate = rate                        # diagnosis
                # 1.57.56: in a match the score corner is looked at while waiting for the next tick
                score_on = bool(self._score is not None and in_match and watching and not tracker.ended
                                and self.settings.get("score_track", True)
                                and (window is not None or source is not None))
                deadline = tick + 1.0 / rate
                while True:
                    now = time.time()
                    if score_on and now >= score_next:
                        score_next = now + SCORE_INTERVAL
                        shot.clear()                 # the tick's whole picture is old now: grab the corner anew
                        self._score_look(grab, fw, fh, origin, from_screen, now, rec)
                        now = time.time()
                    left = deadline - now
                    if left <= 0 and score_on:
                        break
                    try:
                        cmd = self.commands.get(timeout=max(0.02, min(left, score_next - now) if score_on else left))
                        self.commands.put(cmd)       # handled at the top of the next loop
                        break
                    except queue.Empty:
                        if not score_on:
                            break
            except Exception:                    # 1.8.38: one bad frame must not end the detection for good
                fails, failed = fails + 1, True
                if not self._tick_failed(traceback.format_exc(), fails):
                    break
                time.sleep(TICK_FAIL_WAIT_S)
        if grabber:
            grabber.close()
        if wcap is not None:
            wcap.stop()

    def _banner_check(self, tick, session: bool, live: bool):
        """One hint per round when no banner was decided BANNER_MISS_S after the match began: "banner_missed" (the
        app suggests "Scannen" with its hotkey). Nothing while a banner is being read; a map on display (picked by
        hand), the detection switched off or DBD gone end the wait without a hint. Only a hint – no look of its own."""
        due = self._banner_due
        if due is None or session:
            return
        if self.map_on_screen or not live or tick > due + BANNER_MISS_LATE_S:
            self._banner_due = None              # late: the loop did not get here for a while (DBD gone) – stale
        elif tick >= due:
            self._banner_due = None
            log.info("Kein Map-Banner %.0f s nach dem Matchbeginn", BANNER_MISS_S)
            self.post("banner_missed", t=tick)

    def _queue_event(self, ev, tick):
        """QueueTracker events -> UI: what=search | cancel | role | found."""
        if ev[0] in ("search", "cancel", "left", "found"):
            self._banner_due = None              # back in the lobby screens: that match is over (or never began)
        if ev[0] == "search":
            self.post("queue", what="search", since=self.queue.search_start, role=self.queue.role,
                      killer=self.queue.killer, crossplay_off=self.queue.crossplay_off)
        elif ev[0] == "cancel":
            self.match_start.disarm()
            self.post("queue", what="cancel")
        elif ev[0] == "left":
            self.match_start.disarm()
            self.post("queue", what="left")
        elif ev[0] == "role":
            self.post("queue", what="role", role=ev[1], killer=self.queue.killer,
                      crossplay_off=self.queue.crossplay_off)
        elif ev[0] == "found":
            self.match_start.arm(tick)                # 1.6: one lobby arms one match start
            self.post("queue", what="found", found=ev[1], role=ev[1].role)
        elif ev[0] == "remind":
            self.post("queue", what="remind", seconds=ev[1])

    def _status(self, text, last, problem=False):
        """1.55.3: ``problem`` = needs the player's action (minimised, black or failed capture) – a flag, since
        the text is translated and the app cannot tell it from the words."""
        if text != last:
            self.post("status", text=text, problem=problem)

    def _bp_due(self, tick) -> bool:
        """1.16.2 (A7): read the counter every lobby look until CONFIRM_LOOKS readings agree (what the app needs
        to confirm a balance), then every BP_STEADY_S – a fifth of the OCR while sitting in the lobby. A new map
        (the round in between) or another value starts the run again: the reading after a round is as fast as
        before, the one before a round at most BP_STEADY_S old (the app accepts BEFORE_MAX_S)."""
        value, run, last, gen = self._bp_seen
        if gen != self.watch_gen:
            self._bp_seen = (None, 0, last, self.watch_gen)
            return True
        return value is None or run < bloodpoints.CONFIRM_LOOKS or tick - last >= BP_STEADY_S

    def _bp_look(self, grab, fw, fh, tick, origin, from_screen, watcher):
        """1.13: one reading of the currency bar top right while the lobby button is on screen – the bloodpoints
        before and after a round (bloodpoints.py: unchanged after a counted round = the cap is reached). A small
        grab of its own (the strip of ``currency_box``), our own windows blacked out first when it came from the
        screen; the text of every look goes to the app, which confirms and compares. Only read, nothing else."""
        box = currency_box(fw, fh)
        img = grab(box)
        if img is None:                                  # covered by another window: nothing of DBD to read
            return
        self._mask_screen(img, from_screen, origin[0] + box[0], origin[1] + box[1])
        text = watcher.currency_text(img, fh)
        value = bloodpoints.parse(text)
        before, run, _last, gen = getattr(self, "_bp_seen", (None, 0, 0.0, None))
        self._bp_seen = (value, run + 1 if value is not None and value == before else 1, tick, gen)
        self.bp_info = (f"{time.strftime('%H:%M:%S', time.localtime(tick))} „{text}“ → "
                        f"{bloodpoints.fmt(value) if value is not None else '–'}")
        if text:
            self.post("bloodpoints", value=value, text=text, t=tick)

    # ---------------------------------------------------------- full scan
    def _manual_scan(self, rec, grabber, source, window, wcap=None):
        from .fullscan import FullScanner, TextDetector
        t0 = time.time()
        try:
            if self._scanner is None:
                det = TextDetector(os.path.join(self.root_dir, "models", "ch_PP-OCRv4_det_infer.onnx"),
                                   threads=max(2, int(self.settings.get("ocr_threads", 2))))
                self._scanner = FullScanner(det, rec, self.catalog, self._pool)     # CR-006: every script
            if source is not None:
                frame = source.current()
            elif window is not None and not window.minimized:
                frame = None
                if wcap is not None:
                    frame = _wgc_grab(wcap, window, (0, 0, window.width, window.height))
                if frame is None:
                    frame = grabber.grab(window.left, window.top, window.width, window.height)
            else:
                frame = grabber.grab(*grabber.primary_monitor())
            hits = self._scanner.scan(frame)
            self.post("scan_result", hits=hits, seconds=time.time() - t0)
        except Exception as e:
            self.post("scan_result", hits=[], seconds=time.time() - t0, error=str(e))

    # ------------------------------------------------------------- helpers
    def _note_vbars(self, look, fw, fh):
        """Black bars above/below the picture (window narrower than 16:9): the smallest of the last looks, so a
        dark scene at the picture edge does not count as bar; smaller bars apply at once (intro → gameplay)."""
        if self._vbar_looks and self._vbar_looks[-1][2] != (fw, fh):
            self._vbar_looks.clear()                 # window resized: old looks are void
        if fw * 9 >= fh * 16 - 32:                   # 1.38.23 (PERF-3): 16:9 or wider has no bars above/below – the
            top, bottom = 0, 0                       # grey pass over the whole frame (~3 ms, 1.11.13) was thrown away
        else:                                        # by layout.vbars anyway (same test as _vbar_strip)
            with self._measure("vbars"):
                top, bottom = letterbox_rows(look)
        self._vbar_looks.append((top, bottom, (fw, fh)))
        self.vbars = (min(t for t, _b, _s in self._vbar_looks), min(b for _t, b, _s in self._vbar_looks),
                      time.time(), (fw, fh))

    def _vbar_strip(self, grab, fw, fh, tick, origin=(0, 0), from_screen=lambda: False):
        """1.8.65 (user's diagnosis 1718×1360: "Letzte Banner: keine"): the bars were measured only in the round-end
        looks, i.e. while a map is on display – before a round's banner there is none, so the picture never counted
        as letterboxed and neither the tolerant line pass nor the banner's fixed spot (1.8.62) ran. Now, in a window
        narrower than 16:9 and without a map, a quarter-wide strip from the middle at most every VBAR_STRIP_S.
        ``from_screen()``: the strip came from the screen (at ``origin``) – our own windows are blacked out first."""
        if fw * 9 >= fh * 16 - 32 or tick - self._vbar_strip_t < VBAR_STRIP_S:
            return
        self._vbar_strip_t = tick
        box = (fw * 3 // 8, 0, max(1, fw // 4), fh)
        strip = grab(box)
        if strip is None:
            return
        self._mask_screen(strip, from_screen(), origin[0] + box[0], origin[1] + box[1])
        self._note_vbars(strip, fw, fh)

    def _letterboxed(self, fw, fh) -> bool:
        """The last whole-screen look (≤ ~1 s old) showed black bars above and below: a trial in a narrow window."""
        last = self._vbar_looks[-1] if self._vbar_looks else None
        return bool(last and last[2] == (fw, fh) and min(last[0], last[1]) >= MIN_VBAR)

    def _own_windows(self) -> bool:
        """Any of our own windows up (the UI sets their screen rectangles): a screen picture needs them blacked out."""
        return bool(self.overlay_rect or self.hud_rect or self.media_rect or self.today_rect or self.info_rect
                    or self.inputs_rect or self.loadouts_rect or self.guide_rects or self.toast_rect or self.fade_rects)

    def _mask_screen(self, img, from_screen: bool, left, top):
        """1.13.1: the one test before every look – black out our own windows in ``img`` (picture of the screen
        at ``left``/``top``) when it came from the screen and any of them is up. Returns what ``_mask_overlay``
        returns (the map's box in picture coordinates, for ``fills_bars``), None when nothing was done. Before,
        this condition stood copied at every look (seven times, each a chance to forget a window)."""
        if not from_screen or not self._own_windows():
            return None
        with self._measure("mask"):
            return self._mask_overlay(img, left, top)

    def _measure(self, step: str):
        """``times.measure(step)`` – a no-op for a worker built without __init__ (tests call the helpers alone)."""
        times = getattr(self, "times", None)
        return times.measure(step) if times is not None else contextlib.nullcontext()

    def _mask_overlay(self, img, left, top):
        """Black out our own overlay in a screenshot (it is always on top and would
        otherwise be read as part of the game picture)."""
        for r in (self.hud_rect, self.media_rect, self.today_rect, self.inputs_rect, self.loadouts_rect, self.toast_rect,
                  *self.guide_rects, *self.fade_rects):
            if r:
                self._black_out(img, r, left, top)
        lines = self._black_out(img, self.info_rect, left, top)      # 1.8.24: the map's lines apart – they
        done = self._black_out(img, self.overlay_rect, left, top)     # count as the map (fills_bars' ignore)
        if lines and done:
            return (min(lines[0], done[0]), min(lines[1], done[1]), max(lines[2], done[2]), max(lines[3], done[3]))
        return done or lines

    @staticmethod
    def _black_out(img, r, left, top):
        if not r:
            return None
        x0, y0 = int(r[0] - left), int(r[1] - top)
        x1, y1 = x0 + int(r[2]), y0 + int(r[3])
        h, w = img.shape[:2]
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0:x1] = 0
            return x0, y0, x1, y1                    # the blacked-out part, in picture coordinates
        return None

    def _save_frame(self, frame, tag):
        """Debug: downscaled screenshots while a map is shown (folder debug/frames)."""
        try:
            self._last_frame_save = time.time()
            d = _debug_dir(self.data_dir, "frames")
            if d is None:
                return
            h, w = frame.shape[:2]
            s = min(1.0, 1280.0 / max(1, w))
            small = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else frame
            stamp = _stamp()
            cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tofile(os.path.join(d, f"{stamp}-{tag}.jpg"))
            _prune_debug(d, os.listdir(d), 150)
        except Exception:
            pass

    # --------------------------------------------------------------- debug
    def _save_globe(self, img, button):
        """1.5.4: the cross-play zone when the globe could not be read (farming rounds not recognised) – PNG in
        debug/lobby, newest GLOBE_KEPT. The user sends these; the detector is tuned on them."""
        try:
            d = _debug_dir(self.data_dir, "lobby")
            if d is None:
                return
            name = time.strftime("%Y%m%d-%H%M%S") + f"-crossplay-{button or 'x'}.webp"
            write_lossless(os.path.join(d, name), img)
            _prune_debug(d, [f for f in os.listdir(d) if "-crossplay-" in f], GLOBE_KEPT)
        except Exception:
            pass

    def _role_again(self, retry, tick, grab, fw, fh, origin, via, source, lobby_reader):
        """1.11.8: one more look at the result screen's categories after a role-less end. A role → event
        "result_role" (the app corrects the round just saved); after the last look without one the crop goes to
        debug/result as before (1.11.1) and, with debug pictures on, the whole screen to debug/frames ("rolle").
        Returns the retry state to keep, or None."""
        retry["due"].pop(0)
        role, frame = None, None
        try:
            frame = grab((0, 0, fw, fh)) if grab is not None else None
            if frame is not None:
                self._mask_screen(frame, source is None and via["screen"], origin[0], origin[1])
                rx, ry, rw, rh = result_box(fw, fh)
                crop = frame[ry:ry + rh, rx:rx + rw]
                role = lobby_reader.result_role(crop)
                retry["crop"], retry["text"] = crop.copy(), getattr(lobby_reader, "last_result_text", "")
        except Exception:
            self._report("Rolle", traceback.format_exc())
        if role:
            self.post("result_role", gen=retry["gen"], t=retry["t"], role=role,
                      after=round(len(ROLE_RETRY_S) - len(retry["due"])))
            return None
        if retry["due"]:
            return retry
        self._result_miss(retry["crop"], retry["text"])
        if frame is not None and self.settings.get("save_debug_images"):
            self._save_frame(frame, "rolle")
        return None

    def _result_miss(self, crop, text):
        """1.11.1: the result screen gave no role – what was read goes to the diagnosis, the picture of the category
        zone to debug/result (only the newest RESULT_MISSES_KEPT)."""
        self.role_misses.append(f"{time.strftime('%H:%M:%S')} Bild {crop.shape[1]}×{crop.shape[0]} · "
                                f"gelesen „{text[:60]}“")
        try:
            d = _debug_dir(self.data_dir, "result")
            if d is None:
                return
            cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tofile(
                os.path.join(d, time.strftime("%Y%m%d-%H%M%S") + ".jpg"))
            _prune_debug(d, [f for f in os.listdir(d) if f.endswith(".jpg")], RESULT_MISSES_KEPT)
        except Exception:
            pass

    # ------------------------------------------------------------------ 1.57.56: live score tracker
    def _score_round(self, gen, same_round: bool):
        """A new map on display: a new counter – the same round shown again (a banner read twice) keeps its own."""
        if same_round and self._score is not None:
            self._score = (gen, self._score[1])
        else:
            self._score = (gen, scorecount.ScoreCounter()) if gen is not None else None
            self._score_stats = {"looks": 0, "shown": 0, "covered": 0, "ms": 0.0}

    def _score_look(self, grab, fw, fh, origin, from_screen, t, rec):
        """One look at the score corner: read its rows, count them; "score" to the app when an event ended."""
        if self._score is None:
            return
        gen, counter = self._score
        st = self._score_stats
        t0 = time.perf_counter()
        try:
            box = score_box(fw, fh)
            img = grab(box)
            st["looks"] += 1
            if img is None:                       # covered: no look – nothing ends because of it
                st["covered"] += 1
                return
            self._mask_screen(img, from_screen(), origin[0] + box[0], origin[1] + box[1])
            rows = []
            if score_shown(img):
                st["shown"] += 1
                with self.times.measure("score"):
                    rows = scoreevents.read_rows(rec, img)
            if counter.feed(t, rows):
                self._score_post(gen, counter, final=False)
        except Exception:
            self._report("Score", traceback.format_exc())
        finally:
            st["ms"] += (time.perf_counter() - t0) * 1000
            self._score_describe()

    def _score_final(self, gen):
        """The round ended: every event still on screen counts, the totals go to the app (before "match_end")."""
        if self._score is None:
            return
        counter = self._score[1]
        counter.flush()
        self._score_post(gen, counter, final=True)
        self._score_describe()
        self._score = None
        self.score_info = f"{time.strftime('%H:%M:%S')} Runde vorbei: {self.score_info}"   # kept for the diagnosis

    def _score_post(self, gen, counter, final: bool):
        role = counter.role()
        cats = scoreevents.KILLER if role == "killer" else scoreevents.SURVIVOR if role else ()
        totals = counter.totals()
        self.post("score", gen=gen, final=final, role=role, events=len(counter.events),
                  totals={c: totals[c] for c in cats}, full=sorted(counter.full))

    def _score_describe(self):
        st = self._score_stats
        looks = st["looks"]
        if self._score is None:
            return
        counter = self._score[1]
        tot = counter.totals()
        role = counter.role()
        cats = scoreevents.KILLER if role == "killer" else scoreevents.SURVIVOR if role else ()
        parts = ", ".join(f"{c} {tot[c]}" for c in cats)
        self.score_info = (f"{looks} Blicke ({st['shown']} mit Events, {st['covered']} verdeckt), "
                           f"Ø {st['ms'] / max(1, looks):.0f} ms · {len(counter.events)} Events, "
                           f"{counter.dropped} verworfen" + (f" · {parts}" if parts else ""))

    def _save_score_look(self, frame, tick):
        """1.57.52: the top right of the 16:9 picture at full size (own windows already blacked out) to debug/score
        when it seems to show score events – white words and red points (``score_shown``); the newest SCORE_KEPT.
        Only with "Debug-Bilder speichern"; the score event tracker is tuned on them."""
        try:
            part = score_part(frame)
            if part is None or not score_shown(part):
                return
            self._last_score_save = tick
            d = _debug_dir(self.data_dir, "score")
            if d is None:
                return
            stamp = _stamp()
            write_lossless(os.path.join(d, f"{stamp}-score.webp"), part)
            _prune_debug(d, [f for f in os.listdir(d) if f.endswith("-score.webp")], SCORE_KEPT)
        except Exception:
            pass

    def _save_loadout_look(self, frame, tag):
        """1.57.11: a look at the pause menu ("menu": the middle of the picture) or at the HUD ("hud": its left
        part) at full size – what the loadouts reader saw (own windows already blacked out), in debug/loadouts,
        the newest LOADOUT_KEPT of each. Only with "Debug-Bilder speichern"; the user sends them to tune on."""
        try:
            d = _debug_dir(self.data_dir, "loadouts")
            if d is None:
                return
            h, w = frame.shape[:2]
            vw = min(w, h * 16 // 9)
            vx = (w - vw) // 2
            if tag == "menu":
                part = frame[:, vx + vw // 5:vx + vw * 4 // 5]
            else:
                part = frame[:, vx:vx + vw * 2 // 5]
            stamp = _stamp()
            write_lossless(os.path.join(d, f"{stamp}-{tag}.webp"), part)
            _prune_debug(d, [f for f in os.listdir(d)                    # .png: before 1.57.24
                                  if f.endswith((f"-{tag}.webp", f"-{tag}.png"))], LOADOUT_KEPT)
        except Exception:
            pass

    def _save_sighting(self, img, res, sep, tag):
        """Mid-match banner-like sighting: the captured region (separator marked) + what was read, in
        debug/midmatch – only the newest SIGHTINGS_KEPT. Returns the file name (None on failure)."""
        try:
            d = _debug_dir(self.data_dir, "midmatch")
            if d is None:
                return None
            stamp = _stamp()
            name = f"{stamp}-{tag}.jpg"
            vis = img.copy()
            cv2.line(vis, (sep.x0, sep.y), (sep.x1, sep.y), (0, 0, 255), 1)
            cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tofile(os.path.join(d, name))
            with open(os.path.join(d, f"{stamp}-{tag}.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"name: {res.name_text}\nrealm: {res.realm_text}\nbest: {res.best}\nfit: {res.name_fit:.2f}\n"
                         f"separator: x {sep.x0}-{sep.x1}, y {sep.y}, frac {sep.frac:.2f}\n")
            files = [f for f in os.listdir(d) if DEBUG_NAME.match(f)]
            stamps = sorted({f.rsplit("-", 1)[0] for f in files})
            old = set(stamps[:-SIGHTINGS_KEPT])
            _prune_debug(d, [f for f in files if f.rsplit("-", 1)[0] in old], 0)
            return name
        except Exception:
            return None

    def _save_debug(self, img, res, sep):
        try:
            d = _debug_dir(self.data_dir)
            if d is None:
                return
            stamp = _stamp()
            vis = img.copy()
            cv2.line(vis, (sep.x0, sep.y), (sep.x1, sep.y), (0, 0, 255), 1)
            write_lossless(os.path.join(d, f"{stamp}.webp"), vis)
            with open(os.path.join(d, f"{stamp}.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"name: {res.name_text}\nrealm: {res.realm_text}\nbest: {res.best}\nfit: {res.name_fit:.2f}\n")
            _prune_debug(d, [f for f in os.listdir(d)            # keep the folder small
                                  if os.path.isfile(os.path.join(d, f))], 400)
        except Exception:
            pass
