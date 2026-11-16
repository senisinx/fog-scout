"""Developer tool, not part of the program: have the wiki's entries behind ``fogscout/perkdata.json`` changed?

The calculator's numbers are typed in by hand from the Dead by Daylight Wiki. After a patch somebody has to
find out which of them to read again – this tool says so. It reads the three data tables of the wiki
(``PAGES``, plain text, one fixed host, read-only) and compares every entry the calculator uses – perks,
add-ons, items, Killers – with the state kept in ``tools/perkdata_wiki.json``: a fingerprint of the entry and
the numbers in it, written when the values were last read (``--accept``). No text of the wiki is kept.

    python tools/check_perkdata.py              what changed in the wiki since the values were read
    python tools/check_perkdata.py --from DIR   the same from saved pages (files named as in PAGES)
    python tools/check_perkdata.py --accept     after reading the changed entries again: keep the new state

What it finds: an entry whose wiki text or numbers changed (with the numbers before and now), an entry that is
gone or retired (``decom``), perks and add-ons that are new in the wiki, and (1.55.2) every perk whose wiki tags
touch what the calculator computes (``RELEVANT_TAGS``) but that perkdata.json neither calculates nor names in
``not_modelled``/``not_modelled_areas``/``not_relevant`` – before, only perks new since the last ``--accept`` were
reported, so perks that were already there were never looked at. What it cannot find: a value that was
read wrongly in the first place ("raises to 125 %" taken as +125 %) – it compares the wiki with the wiki of
before, not with the meaning of a sentence.

Exit code: 0 = nothing changed, 1 = something to read again, 2 = the pages could not be read."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "fogscout", "perkdata.json")
SNAPSHOT = os.path.join(ROOT, "tools", "perkdata_wiki.json")
HOST = "deadbydaylight.wiki.gg"
PAGES = {                                     # file name of a saved page -> its title in the wiki
    "loadout.lua": "Module:Datatable/Loadout",
    "descriptions.lua": "Module:Datatable/Loadout/Descriptions",
    "datatable.lua": "Module:Datatable",
}
MAX_BYTES = 4 * 1024 * 1024                   # the largest page has 1 MB
TIMEOUT_S = 60
# a name of perkdata.json that the wiki has under other names (two perks in one entry of the calculator)
ALIASES = {
    "perk:Dying Light / Cull the Weak": ("perk:Dying Light", "perk:Cull the Weak"),
    "perk:Deadlock / No Holds Barred": ("perk:Deadlock", "perk:No Holds Barred"),
    "perk:Overzealous (Dull Totem)": ("perk:Overzealous",),
    "perk:Overzealous (Hex Totem)": ("perk:Overzealous",),
}
# 1.55.2: wiki tags of perks that may change a speed, a Skill Check or a Generator's progress – every perk with one
# of them must be decided on in perkdata.json (calculated, "not_modelled", "not_modelled_areas" or "not_relevant")
RELEVANT_TAGS = frozenset({
    "SkillChecks", "SkillCheckProbability", "BonusProgression", "Repairing", "RepairingProficiency", "RepairSpeed",
    "ActionSpeed", "Haste", "MovementSpeed", "Regression", "RegressionSpeed", "ProgressionPenalty",
    "HealingProficiency", "Hindered"})
TAGS = re.compile(r"\btags\s*=\s*\{([^}]*)\}")
KEY = re.compile(r"""^(\s*)\[(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\]\s*=""")
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def fetch(title: str) -> str:
    """The wiki's page ``title`` as plain text (https, the one host, read-only, limited in size and time)."""
    url = f"https://{HOST}/index.php?title={urllib.parse.quote(title)}&action=raw"
    req = urllib.request.Request(url, headers={"User-Agent": "perkdata-check"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:         # fixed host, read-only
        if urllib.parse.urlsplit(r.geturl()).hostname != HOST:
            raise OSError("redirected to another host")
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise OSError("page larger than expected")
    return raw.decode("utf-8")


def read_pages(folder: str | None = None) -> dict:
    """{file name: text} of the three pages – from ``folder`` or from the wiki."""
    if folder:
        out = {}
        for name in PAGES:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                out[name] = fh.read()
        return out
    return {name: fetch(title) for name, title in PAGES.items()}


def section(text: str, name: str) -> list:
    """The lines of the table ``p.<name> = {`` … up to the ``}`` that closes it at the start of a line."""
    lines = text.split("\n")
    start = re.compile(rf"^(?:p\.)?{re.escape(name)}\s*=\s*\{{")
    for i, line in enumerate(lines):
        if start.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("}"):
                    return lines[i + 1:j]
            return lines[i + 1:]
    return []


def blocks(lines: list) -> dict:
    """{name: text} of the entries of a table: an entry starts at ``["name"] =`` (or ``['name'] =``) and goes on
    to the next key at the same indentation. Comment lines between two entries belong to neither."""
    out, name, depth, body = {}, None, None, []

    def close():
        if name is not None:
            while body and (not body[-1].strip() or body[-1].strip().startswith("--")):
                body.pop()
            out.setdefault(name, "\n".join(body))

    for line in lines:
        m = KEY.match(line)
        if m and (depth is None or len(m.group(1).expandtabs(4)) <= depth):
            close()
            name = (m.group(2) if m.group(2) is not None else m.group(3)).replace('\\"', '"').replace("\\'", "'")
            depth, body = len(m.group(1).expandtabs(4)), [line]
        elif name is not None:
            body.append(line)
    close()
    return out


def killers(text: str) -> dict:
    """{"The Nurse": its line} from the table of the Killers (entries without a key: ``{id = 4, name = "Nurse", …}``)."""
    out = {}
    for line in section(text, "killers"):
        m = re.search(r'\bname\s*=\s*"([^"]+)"', line)
        if m and line.lstrip().startswith("{"):
            out.setdefault("The " + m.group(1), line)
    return out


def entries(pages: dict) -> dict:
    """{"perk:Name" | "addon:Name" | "item:Name" | "killer:The Name": the wiki's text of the entry} – the line of
    the data table and, where there is one, the description below it."""
    out = {}
    rows = {kind: blocks(section(pages["loadout.lua"], sec))
            for kind, sec in (("perk", "perks"), ("addon", "addons"), ("item", "items"))}
    texts = {kind: blocks(section(pages["descriptions.lua"], sec))
             for kind, sec in (("perk", "perkDescriptions"), ("addon", "addonDescriptions"),
                               ("item", "itemDescriptions"))}
    for kind, table in rows.items():
        for name, row in table.items():
            out[f"{kind}:{name}"] = row + "\n" + texts[kind].get(name, "")
    for name, row in killers(pages["datatable.lua"]).items():
        out[f"killer:{name}"] = row
    return out


def retired(text: str) -> bool:
    return bool(re.search(r"\bdecom\s*=\s*true\b", text.split("\n", 1)[0]))


def tags(text: str) -> list:
    """The wiki tags of an entry (from its row of the data table, the first line), sorted."""
    m = TAGS.search(text.split("\n", 1)[0])
    return sorted(set(re.findall(r'"([^"]+)"', m.group(1)))) if m else []


def numbers(text: str) -> list:
    """The numbers of an entry, sorted – without its id, which says nothing about the game."""
    text = re.sub(r"\bid\s*=\s*\d+", "", text)
    return sorted({float(n) for n in NUMBER.findall(text)})


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


def used(data: dict) -> dict:
    """{key: True where the calculator works with the entry's values, False where it only lists the name}."""
    out = {}

    def add(kind, names, valued):
        for name in names:
            key = f"{kind}:{name}"
            out[key] = out.get(key, False) or valued

    add("perk", (e["name"] for k in ("perks", "survivor", "killer") for e in data.get(k, ())), True)
    listed = {n for k in ("killer_addon_lists", "item_addon_lists") for names in data.get(k, {}).values() for n in names}
    for name in list(data.get("not_modelled", ())) + list(data.get("not_modelled_areas", ())):
        add("addon" if name in listed else "perk", [name], False)      # "not calculated" names perks and add-ons
    add("perk", data.get("not_relevant", ()), False)                  # 1.55.2: judged irrelevant – watched too
    add("item", (e["name"] for k in ("toolboxes", "medkits") for e in data.get(k, ())), True)
    add("item", (n for names in data.get("items", {}).values() for n in names), False)
    add("addon", (e["name"] for k in ("addons", "killer_addons", "item_addons") for e in data.get(k, ())), True)
    add("addon", (n for k in ("killer_addon_lists", "item_addon_lists")
                  for names in data.get(k, {}).values() for n in names), False)
    add("killer", (e["name"] for e in data.get("killers", ())), True)
    return out


def state(data: dict, wiki: dict) -> dict:
    """What ``--accept`` keeps: per used entry its fingerprint (and, where the calculator has values for it, its
    numbers), and the names of all perks and add-ons the wiki has now."""
    kept = {}
    for key, valued in sorted(used(data).items()):
        names = [k for k in ALIASES.get(key, (key,)) if k in wiki]
        if not names:
            continue
        text = "\n".join(wiki[k] for k in names)
        kept[key] = {"h": fingerprint(text), "n": numbers(text)} if valued else {"h": fingerprint(text)}
    perks = sorted(k[5:] for k in wiki if k.startswith("perk:") and not retired(wiki[k]))
    return {"entries": kept, "perks": perks,
            "addons": sorted(k[6:] for k in wiki if k.startswith("addon:") and not retired(wiki[k])),
            "tags": {n: t for n in perks for t in [tags(wiki["perk:" + n])] if t}}      # 1.55.2


def classified(data: dict) -> set:
    """1.55.2: the wiki names of the perks perkdata.json has decided on – calculated (under the wiki's own names,
    ``ALIASES``), not calculated (``not_modelled``, ``not_modelled_areas``) or judged irrelevant (``not_relevant``)."""
    out = set()
    for name in (e["name"] for k in ("perks", "survivor", "killer") for e in data.get(k, ())):
        out.update(k[5:] for k in ALIASES.get(f"perk:{name}", (f"perk:{name}",)))
    out.update(data.get("not_modelled", ()))
    out.update(data.get("not_modelled_areas", ()))
    out.update(data.get("not_relevant", ()))
    return out


def unclassified(data: dict, snapshot: dict) -> list:
    """1.55.2: [(perk, its relevant tags)] of the perks in ``snapshot`` (the state of ``state``) whose tags touch
    ``RELEVANT_TAGS`` but that perkdata.json has not decided on (``classified``)."""
    known = classified(data)
    return [(name, sorted(set(t) & RELEVANT_TAGS)) for name, t in sorted(snapshot.get("tags", {}).items())
            if set(t) & RELEVANT_TAGS and name not in known]


def compare(data: dict, wiki: dict, snapshot: dict) -> dict:
    """What to read again: {"changed": [(key, numbers before or None, numbers now or None)], "gone": [key],
    "retired": [key], "unknown": [key], "new_perks": [name], "new_addons": [name]}. ``unknown``: used by the
    calculator, in the wiki, but never accepted – a new entry of perkdata.json."""
    now = state(data, wiki)
    before = snapshot.get("entries", {})
    out = {"changed": [], "gone": [], "retired": [], "unknown": [], "new_perks": [], "new_addons": []}
    for key in sorted(used(data)):
        names = ALIASES.get(key, (key,))
        if not all(k in wiki for k in names):
            out["gone"].append(key)
            continue
        if any(retired(wiki[k]) for k in names):
            out["retired"].append(key)
        new, old = now["entries"][key], before.get(key)
        if old is None:
            out["unknown"].append(key)
        elif old.get("h") != new["h"]:
            out["changed"].append((key, old.get("n"), new.get("n")))
    for kind in ("perks", "addons"):
        if kind in snapshot:
            out["new_" + kind] = sorted(set(now[kind]) - set(snapshot[kind]))
    return out


def _num(v: float) -> str:
    return f"{v:g}"


def report(found: dict, open_perks=()) -> list:
    """The findings as lines of text (none: nothing changed). ``open_perks``: the result of ``unclassified``."""
    lines = []
    for key, old, new in found["changed"]:
        line = f"geändert   {key}"
        if old is not None and new is not None:
            away, come = sorted(set(old) - set(new)), sorted(set(new) - set(old))
            line += ("  Zahlen weg: " + ", ".join(map(_num, away)) if away else "") + \
                    ("  Zahlen neu: " + ", ".join(map(_num, come)) if come else "") + \
                    ("" if away or come else "  (nur Text, Zahlen gleich)")
        lines.append(line)
    lines += [f"fehlt      {key}  (im Wiki nicht mehr unter diesem Namen)" for key in found["gone"]]
    lines += [f"ausgemustert {key}  (decom im Wiki)" for key in found["retired"]]
    lines += [f"ungeprüft  {key}  (in perkdata.json, aber noch nie mit --accept übernommen)" for key in found["unknown"]]
    lines += [f"neu im Wiki  perk:{name}  (greift er ins Tempo ein?)" for name in found["new_perks"]]
    lines += [f"neu im Wiki  addon:{name}  (in die Add-on-Liste aufnehmen?)" for name in found["new_addons"]]
    lines += [f"nicht eingeordnet  perk:{name}  (Tags {', '.join(t)}: berechnen oder in not_modelled, "
              "not_modelled_areas bzw. not_relevant eintragen)" for name, t in open_perks]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="folder", help="read the pages from this folder instead of the wiki "
                                                   "(files: " + ", ".join(PAGES) + ")")
    ap.add_argument("--accept", action="store_true", help="keep the wiki's state of now as the one the values "
                                                          "were read from (after reading the changed entries again)")
    ap.add_argument("--data", default=DATA, help=argparse.SUPPRESS)
    ap.add_argument("--snapshot", default=SNAPSHOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        pages = read_pages(args.folder)
    except (OSError, ValueError) as e:
        print(f"Seiten nicht lesbar: {e}", file=sys.stderr)
        return 2
    wiki = entries(pages)
    if not any(k.startswith("perk:") for k in wiki) or not any(k.startswith("killer:") for k in wiki):
        print("Seiten nicht lesbar: keine Perks oder Killer gefunden (Aufbau der Wiki-Tabellen geändert?)",
              file=sys.stderr)
        return 2
    with open(args.data, encoding="utf-8") as fh:
        data = json.load(fh)
    try:
        with open(args.snapshot, encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except FileNotFoundError:
        snapshot = {}
    found = compare(data, wiki, snapshot)
    kept = state(data, wiki)
    open_perks = unclassified(data, kept)
    lines = report(found, open_perks)
    for line in lines:
        print(line)
    if args.accept:
        with open(args.snapshot, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(kept, fh, ensure_ascii=False, indent=0, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        # the path as it is: a relative one cannot be formed across two drives (Windows: C: and D:)
        print(f"Stand übernommen: {len(kept['entries'])} Einträge in {args.snapshot}. "
              "Das Datum „retrieved“ in perkdata.json von Hand nachziehen.")
        return 1 if found["gone"] or open_perks else 0
    if not lines:
        print(f"Nichts geändert: {len(snapshot.get('entries', {}))} Einträge wie beim letzten Lesen.")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
