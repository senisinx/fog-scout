"""Score event tracker, step 4 (1.57.55): count the score events of a whole own recording – what the live
tracker would count (``scoreevents.read_rows`` + ``scorecount.ScoreCounter`` at ``--fps`` looks a second).

Prints every counted event and the points per category; ``--json`` writes them. Runs only on the user's own video
files with the ffmpeg of imageio-ffmpeg 0.6.0; reads nothing else, sends nothing.

    .venv\\Scripts\\python tools\\score_round.py "D:\\Videos\\Fog Scout\\2026-11-21 20-57 Family Residence.mp4"
    .venv\\Scripts\\python tools\\score_round.py --fps 2 --json runde.json runde.mp4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numpy as np  # noqa: E402

from fogscout import clipedit, scorecount, scoreevents, worker  # noqa: E402
from fogscout.obsrec import ffmpeg_exe  # noqa: E402
from fogscout.ocr import Recognizer  # noqa: E402
from fogscout.textnorm import MAIN, MODEL_FILES  # noqa: E402
from score_frames import crop_box  # noqa: E402


def count(path: str, fps: float, ffmpeg: str, rec) -> scorecount.ScoreCounter | None:
    info = clipedit.probe(path, ffmpeg)
    if not info.ok or info.width <= 0 or info.height <= 0:
        return None                     # probe gave up (slow disk: 30 s): never read frames of size 0 – endless
    w, h, x, y = crop_box(info.width, info.height)
    need = w * h * 3
    if need <= 0:
        return None
    proc = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-an",
                             "-vf", f"fps={fps},crop={w}:{h}:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=clipedit._flags())
    counter = scorecount.ScoreCounter()
    n = 0
    most = int((info.duration or 3 * 3600) * fps) + int(5 * fps)       # never more looks than the video has
    try:
        while n < most:
            data = proc.stdout.read(need)
            if len(data) < need:
                break
            part = np.frombuffer(data, np.uint8).reshape(h, w, 3)
            t = n / fps
            n += 1
            rows = scoreevents.read_rows(rec, part) if worker.score_shown(part) else []
            counter.feed(t, rows)
    finally:
        proc.kill()
        proc.stdout.close()
        proc.wait(timeout=10)
    counter.flush()
    return counter


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score Events einer eigenen Aufnahme zählen")
    ap.add_argument("video", help="Aufnahme (eine Runde)")
    ap.add_argument("--fps", type=float, default=4.0, help="Blicke je Sekunde (Standard 4)")
    ap.add_argument("--json", help="Ereignisse und Summen als JSON schreiben")
    ap.add_argument("--quiet", action="store_true", help="nur die Summen")
    args = ap.parse_args(argv)
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        print("ffmpeg fehlt: .venv\\Scripts\\python -m pip install imageio-ffmpeg==0.6.0")
        return 2
    rec = Recognizer(os.path.join(ROOT, "models", MODEL_FILES[MAIN]))
    counter = count(args.video, args.fps, ffmpeg, rec)
    if counter is None:
        print(f"Nicht lesbar: {args.video}")
        return 1
    if not args.quiet:
        for e in counter.events:
            pts = "MAX" if e.capped else f"+{e.points}"
            print(f"{int(e.t // 60):02d}:{e.t % 60:05.2f}  {e.category:<12} {pts:>6}  {e.name}")
    totals = counter.totals()
    shown = [c for c in scoreevents.CATEGORIES if totals[c] or c in counter.full]
    print(f"{len(counter.events)} Events ({counter.dropped} verworfen), Rolle {counter.role() or '?'}: "
          + ", ".join(f"{c} {totals[c]}" for c in shown))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"events": [e.__dict__ for e in counter.events], "totals": totals,
                       "full": sorted(counter.full), "dropped": counter.dropped}, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
