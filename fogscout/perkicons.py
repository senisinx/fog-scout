"""Perk pictures for the calculator's choices (pure, 1.52): finds a picture file for a perk name in the user's
folder ``<data folder>/perk_icons`` (the user's own pictures come first) and in the program's own folder
``fogscout/perkicons`` (the perks, items and add-ons of perkdata.json, 64 px, from the Dead by Daylight Wiki – see
THIRD_PARTY.md; Saru: "Wiki ist in Ordnung", and "ja" for items and add-ons) – files named like the perk
("Prove Thyself.png") or like the game's icons ("iconPerks_proveThyself.png", "T_UI_iconsPerks_Rampage.png",
"IconAddon_scraps.png", "IconItems_toolbox.png"), in sub-folders too. Only these two folders are read,
never the game's files (hard rule); nothing is written."""
from __future__ import annotations

import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = "perkicons"                  # beside this module
USER_FOLDER = "perk_icons"            # in the data folder
EXTS = (".png", ".webp")
MAX_FILES = 8000                      # a folder with more is not an icon folder (the program's own: ~1 200)
MAX_BYTES = 2 * 1024 * 1024           # a picture larger than this is not an icon
PREFIXES = ("hex", "boon", "scourgehook", "teamwork", "invocation")       # some packs name the file without it
# how the game and the wiki begin a file name: "iconPerks_", "T_UI_iconsPerks_", "IconAddon_", "IconItems_" – only
# with the underscore, or "IconAddon_scraps" would lose the s of its name
LEAD = re.compile(r"^(?:t_ui_)?icons?(perks|addons?|items)_", re.IGNORECASE)
KINDS = ("perks", "addon", "items")   # what a file shows, by the beginning of its name ("" = named plainly)


def kind_of(stem: str) -> str:
    """"perks", "addon" or "items" for a file named like the game's icons, "" for any other name."""
    m = LEAD.match(str(stem))
    return m.group(1).lower().rstrip("s").replace("perk", "perks").replace("item", "items") if m else ""


def key(text: str) -> str:
    """"Boon: Circle of Healing" and "iconPerks_boonCircleOfHealing" → "booncircleofhealing"."""
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    return "".join(c for c in LEAD.sub("", plain, count=1) if c.isalnum())


def folders(data_dir: str) -> list:
    return [os.path.join(data_dir, USER_FOLDER), os.path.join(HERE, FOLDER)]


def candidates(name: str) -> list:
    """The keys a file for this name may have: the whole name, each half of "A / B", without "(…)", without the
    kind in front ("Hex: Ruin" → "ruin")."""
    out = []
    for part in [name] + [p for p in name.split(" / ") if p != name]:
        for text in (part, part.split(" (")[0]):           # "Jump Rope (Dream Demon)": with the bracket first
            k = key(text)
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
                    files.setdefault((kind_of(stem), key(stem)), path)     # the first folder (the user's) first
        return files

    def any(self) -> bool:
        if self._files is None:
            self._files = self._scan()
        return bool(self._files)

    def find(self, name: str, kind: str = ""):
        """The picture file for a name, or None. ``kind`` ("perks", "addon", "items"): a file of this kind or one
        named plainly – a perk and an add-on of the same name never take each other's picture (1.54: 950
        add-ons). Without a kind any file of the name."""
        if (name, kind) not in self._found:
            kinds = (kind, "") if kind else KINDS + ("",)
            self._found[(name, kind)] = next((self._files[(kd, k)] for k in candidates(name) for kd in kinds
                                              if (kd, k) in self._files), None) if self.any() else None
        return self._found[(name, kind)]

    def finder(self, kind: str):
        """``find`` for one kind of picture (what a choice's entries are)."""
        return lambda name: self.find(name, kind)
