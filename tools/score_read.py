"""Score event tracker, step 2 (1.57.53): read the score events in the corners cut by ``tools/score_frames.py`` (or
saved live in debug/score) – to check ``fogscout.scoreevents`` on own pictures.

Prints one line per picture (name and points of each row) and a summary; ``--sheet`` writes a check picture
(each row next to what was read), ``--csv`` a table. Reads only the given pictures, sends nothing.

    .venv\\Scripts\\python tools\\score_read.py score_frames
    .venv\\Scripts\\python tools\\score_read.py --sheet check.png --limit 200 score_frames\\Runde_1
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from fogscout import scoreevents  # noqa: E402
from fogscout.ocr import Recognizer  # noqa: E402
from fogscout.textnorm import MAIN, MODEL_FILES  # noqa: E402

PICTURES = (".webp", ".png", ".jpg")
SHEET_ROWS = 25
SHEET_MAX = 100


def pictures(paths):
    for p in paths:
        if os.path.isdir(p):
            for base, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(PICTURES):
                        yield os.path.join(base, f)
        elif p.lower().endswith(PICTURES) and os.path.isfile(p):
            yield p


def label(row) -> str:
    points = "MAX" if row.capped else f"+{row.points}" if row.points is not None else f"?{row.raw}"
    return f"{points} {row.category or '?'}"


def sheet_tile(part, row):
    x0, y0, x1, y1 = row.word
    gx0 = min(g[0] for g in row.glyphs)
    gy1 = max(g[1] + g[3] for g in row.glyphs)
    cut = part[max(0, y0 - 4):gy1 + 4, max(0, min(x0, gx0) - 4):x1 + 6]
    cut = cv2.resize(cut, (240, 60))
    text = np.full((60, 260, 3), 255, np.uint8)
    cv2.putText(text, row.name[:16], (4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    cv2.putText(text, label(row), (4, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
    return np.hstack([cut, text])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score Events in Ausschnitten lesen")
    ap.add_argument("paths", nargs="+", help="Bilder oder Ordner (Unterordner werden mit durchsucht)")
    ap.add_argument("--limit", type=int, default=0, help="höchstens so viele Bilder (gleichmässig verteilt)")
    ap.add_argument("--sheet", help="Prüfbild schreiben (PNG)")
    ap.add_argument("--csv", help="Tabelle schreiben")
    ap.add_argument("--quiet", action="store_true", help="nur die Zusammenfassung")
    args = ap.parse_args(argv)
    files = list(pictures(args.paths))
    if args.limit and len(files) > args.limit:
        step = len(files) / args.limit
        files = [files[int(i * step)] for i in range(args.limit)]
    if not files:
        print("Keine Bilder gefunden.")
        return 1
    rec = Recognizer(os.path.join(ROOT, "models", MODEL_FILES[MAIN]))
    n_rows = n_read = 0
    tiles, table = [], []
    for f in files:
        part = cv2.imread(f)
        if part is None:
            continue
        rows = scoreevents.read_rows(rec, part)
        n_rows += len(rows)
        n_read += sum(r.readable for r in rows)
        if not args.quiet and rows:
            print(f"{os.path.relpath(f)}: " + " | ".join(f"{r.name} {label(r)}" for r in rows))
        for r in rows:
            table.append((os.path.relpath(f), r.name, r.points if r.points is not None else "", int(r.capped),
                          r.raw, int(r.readable), r.category or ""))
            if args.sheet and len(tiles) < SHEET_MAX:
                tiles.append(sheet_tile(part, r))
    share = f"{100 * n_read / n_rows:.0f} %" if n_rows else "–"
    print(f"{len(files)} Bilder, {n_rows} Zeilen, davon lesbar (Name + Punkte/MAX): {n_read} ({share})")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(("bild", "name", "punkte", "max", "gelesen", "lesbar", "kategorie"))
            w.writerows(table)
    if args.sheet and tiles:
        cols = [np.vstack(tiles[i:i + SHEET_ROWS]) for i in range(0, len(tiles), SHEET_ROWS)]
        h = max(c.shape[0] for c in cols)
        cols = [cv2.copyMakeBorder(c, 0, h - c.shape[0], 0, 8, cv2.BORDER_CONSTANT, value=(128, 128, 128))
                for c in cols]
        cv2.imwrite(args.sheet, np.hstack(cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
