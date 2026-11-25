"""Score event tracker, step 3 (1.57.54): make the category templates (``fogscout/score_icons.png``) from the
corners cut by ``tools/score_frames.py`` – and check them on rounds they were not made from.

Every row whose name is one of SEEDS (events that always count for one category) gives its icon to that category;
the template is the mean. Names that count for different categories by what they are done for (HEAL, GOOD SKILL
CHECK, COOP ACTION, MED-KIT HEAL) are not seeds. Reads only the given pictures, sends nothing.

    .venv\\Scripts\\python tools\\score_icons.py --check score_frames          (only check: half the rounds each)
    .venv\\Scripts\\python tools\\score_icons.py --write score_frames          (write fogscout\\score_icons.png)
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from fogscout import scoreevents  # noqa: E402
from fogscout.ocr import Recognizer  # noqa: E402
from fogscout.textnorm import MAIN, MODEL_FILES, fold  # noqa: E402

SEEDS = {
    "brutality": ("HIT", "DAMAGEGENERATOR", "DESTRUCTION"),
    "deviousness": ("LETHALBLINK", "PRECISEBLINK", "BLEEDING", "CHAINSAWSPRINT", "CURVE"),
    "hunter": ("CHASE", "SURVIVORFOUND"),
    "sacrifice": ("HOOKED", "CAUGHT", "SACRIFICE", "ENTITYSUMMONED"),
    "objective": ("REPAIRS", "UNLOCKING"),
    "survival": ("RECOVERY", "STRUGGLE", "SURVIVED", "GOODWIGGLESKILLCHECKS", "GREATWIGGLESKILLCHECKS"),
    "altruism": ("ASSIST", "HOOKRESCUE", "SAFEHOOKRESCUE", "REUNITED", "PROTECTION"),
    "boldness": ("BOLD", "CHASED", "ESCAPED", "VAULT"),
}
SEED_OF = {n: c for c, names in SEEDS.items() for n in names}
PICTURES = (".webp", ".png", ".jpg")


def collect(paths, limit):
    """[(round folder, category, feature)] of every seed row in the pictures (``limit`` spread evenly, 0 = all)."""
    files = []
    for p in paths:
        for base, _dirs, names in os.walk(p):
            files += [os.path.join(base, f) for f in sorted(names) if f.lower().endswith(PICTURES)]
    if limit and len(files) > limit:
        step = len(files) / limit
        files = [files[int(i * step)] for i in range(limit)]
    rec = Recognizer(os.path.join(ROOT, "models", MODEL_FILES[MAIN]))
    out = []
    for f in files:
        part = cv2.imread(f)
        if part is None:
            continue
        s = part.shape[0] / scoreevents.BOX_H
        for row in scoreevents.find_rows(part):
            cat = SEED_OF.get(fold(scoreevents.read_name(rec, part, row.word, s)))
            cut = scoreevents.icon_cut(part, row) if cat else None
            if cut is not None:
                out.append((os.path.dirname(f), cat, scoreevents.icon_feature(cut)))
    return out


def make(rows):
    temps = []
    for cat in scoreevents.CATEGORIES:
        mine = [f for _r, c, f in rows if c == cat]
        if not mine:
            raise SystemExit(f"Keine Zeile für {cat} – mehr Aufnahmen nötig.")
        t = np.mean(mine, axis=0)
        t -= t.mean()
        temps.append(t / np.linalg.norm(t))
    return np.array(temps)


def check(rows):
    rounds = sorted({r for r, _c, _f in rows})
    held = set(rounds[::2])
    temps = make([x for x in rows if x[0] not in held])
    right = sure = sure_right = n = 0
    wrong = collections.Counter()
    for r, cat, f in rows:
        if r not in held:
            continue
        s = scoreevents.icon_scores(f, temps)
        order = np.argsort(s)
        best = scoreevents.CATEGORIES[int(order[-1])]
        n += 1
        right += best == cat
        if best != cat:
            wrong[(cat, best)] += 1
        if s[order[-1]] >= scoreevents.ICON_MIN and s[order[-1]] - s[order[-2]] >= scoreevents.ICON_MARGIN:
            sure += 1
            sure_right += best == cat
    print(f"Prüfung auf {len(held)} von {len(rounds)} Runden ({n} Zeilen): {right} richtig ({100 * right / n:.1f} %); "
          f"sicher {sure} ({100 * sure / n:.0f} %), davon richtig {sure_right} ({100 * sure_right / max(1, sure):.1f} %)")
    for (want, got), k in wrong.most_common(8):
        print(f"  {want} -> {got}: {k}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vorlagen der Score-Kategorien aus eigenen Ausschnitten")
    ap.add_argument("paths", nargs="+", help="Ordner mit Ausschnitten (je Runde ein Unterordner)")
    ap.add_argument("--limit", type=int, default=2500, help="höchstens so viele Bilder (0 = alle)")
    ap.add_argument("--check", action="store_true", help="auf der Hälfte der Runden prüfen")
    ap.add_argument("--write", action="store_true", help="fogscout/score_icons.png schreiben (aus allen Runden)")
    args = ap.parse_args(argv)
    rows = collect(args.paths, args.limit)
    count = collections.Counter(c for _r, c, _f in rows)
    print(f"{len(rows)} Zeilen: " + ", ".join(f"{c} {count[c]}" for c in scoreevents.CATEGORIES))
    if args.check:
        check(rows)
    if args.write:
        scoreevents.save_templates(scoreevents.ICONS_FILE, make(rows))
        print(f"Geschrieben: {scoreevents.ICONS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
