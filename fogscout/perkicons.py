"""Perk pictures for the calculator's choices (pure, 1.52): finds a picture file for a perk name in the user's
folder ``<data folder>/perk_icons`` (the user's own pictures come first) and in the program's own folder
``fogscout/perkicons`` (the perks of perkdata.json, 64 px, from the Dead by Daylight Wiki – see THIRD_PARTY.md;
Saru: "Wiki ist in Ordnung") – files named like the perk ("Prove Thyself.png") or like the game's icons
("iconPerks_proveThyself.png", "T_UI_iconsPerks_Rampage.png"), in sub-folders too. Only these two folders are read,
never the game's files (hard rule); nothing is written."""
from __future__ import annotations

import os
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = "perkicons"                  # beside this module
USER_FOLDER = "perk_icons"            # in the data folder
EXTS = (".png", ".webp")
MAX_FILES = 3000                      # a folder with more is not an icon folder
MAX_BYTES = 2 * 1024 * 1024           # a picture larger than this is not an icon
PREFIXES = ("hex", "boon", "scourgehook", "teamwork", "invocation")       # some packs name the file without it
LEADS = ("tuiiconsperks", "tuiiconperks", "iconsperks", "iconperks")       # how the game and the wiki begin a name


def key(text: str) -> str:
    """"Boon: Circle of Healing" and "iconPerks_boonCircleOfHealing" → "booncircleofhealing"."""
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    out = "".join(c for c in plain if c.isalnum())
    for lead in LEADS:                                     # "T_UI_iconsPerks_", "IconsPerks_", "iconPerks_"
        if out.startswith(lead) and len(out) > len(lead):
            return out[len(lead):]
    return out


def folders(data_dir: str) -> list:
    return [os.path.join(data_dir, USER_FOLDER), os.path.join(HERE, FOLDER)]


def candidates(name: str) -> list:
    """The keys a file for this perk may have: the whole name, each half of "A / B", without "(…)", without the
    kind in front ("Hex: Ruin" → "ruin")."""
    out = []
    for part in [name] + [p for p in name.split(" / ") if p != name]:
        part = part.split(" (")[0]
        k = key(part)
        for cand in [k] + [k[len(p):] for p in PREFIXES if k.startswith(p) and len(k) > len(p)]:
            if cand and cand not in out:
                out.append(cand)
    return out


class Index:
    """The picture files of the folders by key, read once at the first question."""

    def __init__(self, dirs):
        self._dirs = list(dirs)
        self._files = None
        self._found = {}

    def _scan(self) -> dict:
        files, seen = {}, 0
        for top in self._dirs:
            if not os.path.isdir(top):
                continue
            for folder, _subs, names in os.walk(top, followlinks=False):
                for name in sorted(names):
                    stem, ext = os.path.splitext(name)
                    if ext.lower() not in EXTS:
                        continue
                    seen += 1
                    if seen > MAX_FILES:
                        return files
                    path = os.path.join(folder, name)
                    try:
                        if os.path.islink(path) or os.path.getsize(path) > MAX_BYTES:
                            continue
                    except OSError:
                        continue
                    files.setdefault(key(stem), path)          # the first folder (the user's) comes first
        return files

    def any(self) -> bool:
        if self._files is None:
            self._files = self._scan()
        return bool(self._files)

    def find(self, name: str):
        """The picture file for a perk name, or None."""
        if name not in self._found:
            self._found[name] = next((self._files[k] for k in candidates(name) if k in self._files), None) \
                if self.any() else None
        return self._found[name]
