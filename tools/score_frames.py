"""Score event tracker, step 1 (1.57.52): cut the score events (top right of the 16:9 picture) out of own
recordings – the same box and test as the live debug pictures (``worker.SCORE_BOX``/``score_shown``).

Runs only on the user's own video files, with the ffmpeg of imageio-ffmpeg 0.6.0 (``obsrec.ffmpeg_exe``); reads
nothing else, sends nothing. Writes one lossless WebP per new sight to OUT/<recording>/<second>.webp – only the
corner, never the rest of the picture (no player names: those are in the HUD on the left).

    .venv\\Scripts\\python tools\\score_frames.py --out score_frames "D:\\Videos\\Fog Scout"
    .venv\\Scripts\\python tools\\score_frames.py --fps 4 --out score_frames runde1.mkv runde2.mp4
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from fogscout import clipedit, worker  # noqa: E402
from fogscout.obsrec import ffmpeg_exe  # noqa: E402

VIDEO = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
SAME_DIFF = 3.0          # mean difference (0–255) under which a sight counts as the one saved before


def videos(paths):
    for p in paths:
        if os.path.isdir(p):
            for base, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(VIDEO):
                        yield os.path.join(base, f)
        elif p.lower().endswith(VIDEO) and os.path.isfile(p):
            yield p


def crop_box(width: int, height: int):
    """(w, h, x, y) of ``worker.SCORE_BOX`` in a picture of this size – the same cut as ``worker.score_part``."""
    vw = min(width, height * 16 // 9)
    vx = (width - vw) // 2
    x0, y0, x1, y1 = worker.SCORE_BOX
    x, y = vx + int(x0 * vw), int(y0 * height)
    return vx + int(x1 * vw) - x, int(y1 * height) - y, x, y


def safe_name(path: str) -> str:
    return re.sub(r"[^\w.-]+", "_", os.path.splitext(os.path.basename(path))[0])[:80] or "video"


def scan(path: str, out: str, fps: float, ffmpeg: str) -> tuple[int, int]:
    """(looks, saved) for one recording."""
    info = clipedit.probe(path, ffmpeg)
    if not info.ok:
        print(f"  übersprungen (nicht lesbar): {path}")
        return 0, 0
    w, h, x, y = crop_box(info.width, info.height)
    need = w * h * 3
    folder = os.path.join(out, safe_name(path))
    proc = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-an",
                             "-vf", f"fps={fps},crop={w}:{h}:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            creationflags=clipedit._flags())
    looks = saved = 0
    last = None
    try:
        while True:
            data = proc.stdout.read(need)
            if len(data) < need:
                break
            part = np.frombuffer(data, np.uint8).reshape(h, w, 3)
            t = looks / fps
            looks += 1
            if not worker.score_shown(part):
                last = None
                continue
            if last is not None and float(np.mean(np.abs(part.astype(np.int16) - last))) < SAME_DIFF:
                continue
            last = part.astype(np.int16)
            os.makedirs(folder, exist_ok=True)
            worker.write_lossless(os.path.join(folder, f"{int(t // 60):03d}m{t % 60:06.2f}s.webp"), part)
            saved += 1
    finally:
        proc.kill()
        proc.stdout.close()
        proc.wait(timeout=10)
    return looks, saved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score-Event-Ecken aus eigenen Aufnahmen schneiden")
    ap.add_argument("paths", nargs="+", help="Videodateien oder Ordner (Unterordner werden mit durchsucht)")
    ap.add_argument("--out", required=True, help="Zielordner für die Ausschnitte")
    ap.add_argument("--fps", type=float, default=4.0, help="Blicke je Sekunde Video (Standard 4)")
    args = ap.parse_args(argv)
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        print("ffmpeg fehlt: .venv\\Scripts\\python -m pip install imageio-ffmpeg==0.6.0")
        return 2
    files = list(videos(args.paths))
    if not files:
        print("Keine Videos gefunden.")
        return 1
    total = 0
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {os.path.basename(f)}")
        looks, saved = scan(f, args.out, args.fps, ffmpeg)
        total += saved
        print(f"  {looks} Blicke, {saved} Ausschnitte")
    print(f"Fertig: {total} Ausschnitte in {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
