"""1.55 (review of the calculator: its numbers are typed in by hand and nothing said which of them a patch
changed): tools/check_perkdata.py compares the wiki's entries behind fogscout/perkdata.json with the state they
had when the values were read (tools/perkdata_wiki.json: fingerprints and numbers, no text of the wiki).
The tests use made-up pages – nothing is fetched."""
import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_perkdata", os.path.join(ROOT, "tools", "check_perkdata.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LOADOUT = '''local p = {}
p.items = {
    ["Toolbox"]            = {id = 38, rarity = 2, category = 7, patch = "8.0.0", tags = {"Generators"}},
    ["Flashlight"]         = {id = 12, rarity = 2, category = 3},
}
p.addons = {
    -- toolbox add-ons
    ["Socket Swivels"]                 = {id = 65, rarity = 2, itemsCategory = 7, effect = "+30 %"},
    ['"Shadow Dance" - Blood']         = {id = 107, rarity = 4, killer = 2},
    ["Old Thing"]                      = {id = 9, rarity = 1, killer = 2, decom = true},
    ["Gum"]                            = {id = 700, rarity = 1, itemsCategory = 9},
}
p.perks = {
    ["Sprint Burst"]   = {id = 44, units = {1}, values = {60, 50, 40}, haste = "+50 %", durationHaste = "2 seconds"},
    ["Dying Light"]    = {charType = 'K', character = 5},
    ["Cull the Weak"]  = {id = 327, values = {2, 2.5, 3}},
    ["Lithe"]          = {id = 77, values = {60, 50, 40}, haste = "+50 %", durationHaste = "3 seconds"},
}
return p
'''
DESCRIPTIONS = '''local p = {}
p.addonDescriptions = {
    ---------------------------
    ["Socket Swivels"] = {
        desc =
            "Increases the Repair speed by #effect."
    },
}
p.perkDescriptions = {
    ["Sprint Burst"] = {
        desc =
            "Starting to run triggers #pn:" ..
            list("Grants " .. effects("perk", "Sprint Burst", ils.haste) .. " for " .. clro("#durationHaste"))
    },
    ["Lithe"] = {
        desc =
            "After a Rushed Vault, break into a sprint."
    },
}
return p
'''
DATATABLE = '''local p = {}
killers = {
	-- {id = number, name = "string"}
	{id = 2, name = "Wraith", speed = 4.6, altSpeed = {{6.9, "Cloaked"}}, radius = 32},
	{id = 4, name = "Nurse", speed = 3.85, altSpeed = {{13.33, "Blink"}}, radius = 32},
}
p.killers = killers
return p
'''
DATA = {
    "perks": [{"name": "Sprint Burst"}, {"name": "Lithe"}],
    "survivor": [], "killer": [{"name": "Dying Light / Cull the Weak"}],
    "not_modelled": ["Old Thing"], "not_modelled_areas": [],
    "toolboxes": [{"name": "Toolbox"}], "medkits": [], "items": {"flashlight": ["Flashlight"]},
    "addons": [], "killer_addons": [{"name": '"Shadow Dance" - Blood'}], "item_addons": [{"name": "Socket Swivels"}],
    "killer_addon_lists": {"The Wraith": ['"Shadow Dance" - Blood', "Old Thing"]},
    "item_addon_lists": {"toolbox": ["Socket Swivels"]},
    "killers": [{"name": "The Wraith", "speed": 4.6}, {"name": "The Nurse", "speed": 3.85}],
}


def pages(loadout=LOADOUT, descriptions=DESCRIPTIONS, datatable=DATATABLE) -> dict:
    return {"loadout.lua": loadout, "descriptions.lua": descriptions, "datatable.lua": datatable}


def test_the_tables_of_the_wiki_are_read_entry_by_entry(tool):
    perks = tool.blocks(tool.section(LOADOUT, "perks"))
    assert list(perks) == ["Sprint Burst", "Dying Light", "Cull the Weak", "Lithe"]
    assert 'durationHaste = "2 seconds"' in perks["Sprint Burst"] and "Lithe" not in perks["Sprint Burst"]
    addons = tool.blocks(tool.section(LOADOUT, "addons"))
    assert '"Shadow Dance" - Blood' in addons and "Gum" in addons                # a key in single quotes too
    assert tool.section(LOADOUT, "no such table") == []
    texts = tool.blocks(tool.section(DESCRIPTIONS, "perkDescriptions"))
    assert texts["Sprint Burst"].count("\n") == 4 and "Rushed Vault" not in texts["Sprint Burst"]   # its lines only
    assert tool.blocks(tool.section(DESCRIPTIONS, "addonDescriptions"))["Socket Swivels"].endswith("},")
    assert list(tool.killers(DATATABLE)) == ["The Wraith", "The Nurse"]          # the comment line is no Killer
    wiki = tool.entries(pages())
    assert "Grants" in wiki["perk:Sprint Burst"] and "speed = 3.85" in wiki["killer:The Nurse"]
    assert wiki["item:Toolbox"].startswith('    ["Toolbox"]') and wiki["perk:Dying Light"].strip().endswith("},")
    assert tool.retired(wiki["addon:Old Thing"]) and not tool.retired(wiki["addon:Gum"])


def test_numbers_and_fingerprint_see_the_game_not_the_layout(tool):
    assert tool.numbers('{id = 44, units = {1}, values = {60, 50, 40}, haste = "+50 %", patch = "10.1.0"}') == [
        1.0, 10.1, 40.0, 50.0, 60.0]                                           # no id; "10.1.0" reads as 10.1
    assert tool.numbers("speed = 3.85, radius = 32") == [3.85, 32.0]
    assert tool.fingerprint("a  =  1\n\tb") == tool.fingerprint("a = 1 b") != tool.fingerprint("a = 2 b")


def test_what_the_calculator_uses_and_how(tool):
    used = tool.used(DATA)
    assert used["perk:Sprint Burst"] is True and used["killer:The Nurse"] is True and used["item:Toolbox"] is True
    assert used["item:Flashlight"] is False                                      # only listed: no values of ours
    assert used["addon:Old Thing"] is False and "perk:Old Thing" not in used     # "not calculated" names an add-on
    assert used['addon:"Shadow Dance" - Blood'] is True and used["addon:Socket Swivels"] is True
    kept = tool.state(DATA, tool.entries(pages()))
    assert set(kept["entries"]) == set(used)
    assert kept["entries"]["perk:Sprint Burst"]["n"] == [1.0, 2.0, 40.0, 50.0, 60.0]
    assert "n" not in kept["entries"]["item:Flashlight"] and len(kept["entries"]["item:Flashlight"]["h"]) == 16
    assert kept["perks"] == ["Cull the Weak", "Dying Light", "Lithe", "Sprint Burst"]
    assert kept["addons"] == ['"Shadow Dance" - Blood', "Gum", "Socket Swivels"]       # the retired one is none
    assert "Grants" not in json.dumps(kept)                                      # no text of the wiki is kept


def test_a_patch_shows_as_what_to_read_again(tool):
    wiki = tool.entries(pages())
    kept = tool.state(DATA, wiki)
    same = tool.compare(DATA, wiki, kept)
    assert same == {"changed": [], "gone": [], "retired": ["addon:Old Thing"], "unknown": [], "new_perks": [],
                    "new_addons": []}
    assert tool.report(same) == ["ausgemustert addon:Old Thing  (decom im Wiki)"]
    patched = LOADOUT.replace('durationHaste = "2 seconds"', 'durationHaste = "3 seconds"')      # a number
    patched = patched.replace('    ["Lithe"]', '    ["Lithe (old)"]')                             # a name gone
    patched = patched.replace("values = {2, 2.5, 3}", "values = {2, 2.5, 4}")                    # behind an alias
    patched = patched.replace('p.perks = {', 'p.perks = {\n    ["Brand New Perk"] = {id = 900, values = {1, 2, 3}},')
    patched = patched.replace('    ["Gum"]', '    ["Fresh Add-on"] = {id = 901, killer = 2},\n    ["Gum"]')
    texts = DESCRIPTIONS.replace("Increases the Repair speed", "Raises the Repair speed")        # words only
    found = tool.compare(DATA, tool.entries(pages(patched, texts)), kept)
    assert found["changed"] == [
        ("addon:Socket Swivels", [2.0, 7.0, 30.0], [2.0, 7.0, 30.0]),           # rarity, category, +30 %
        ("perk:Dying Light / Cull the Weak", [2.0, 2.5, 3.0, 5.0], [2.0, 2.5, 4.0, 5.0]),
        ("perk:Sprint Burst", [1.0, 2.0, 40.0, 50.0, 60.0], [1.0, 3.0, 40.0, 50.0, 60.0])]
    assert found["gone"] == ["perk:Lithe"] and found["unknown"] == []
    assert found["new_perks"] == ["Brand New Perk", "Lithe (old)"] and found["new_addons"] == ["Fresh Add-on"]
    lines = tool.report(found)
    assert "geändert   addon:Socket Swivels  (nur Text, Zahlen gleich)" in lines
    assert "geändert   perk:Sprint Burst  Zahlen weg: 2  Zahlen neu: 3" in lines
    assert "geändert   perk:Dying Light / Cull the Weak  Zahlen weg: 3  Zahlen neu: 4" in lines
    assert any(line.startswith("fehlt      perk:Lithe") for line in lines)
    assert any(line.startswith("neu im Wiki  perk:Brand New Perk") for line in lines)
    # a perk added to perkdata.json that was never accepted
    more = {**DATA, "perks": DATA["perks"] + [{"name": "Cull the Weak"}]}
    assert tool.compare(more, wiki, kept)["unknown"] == ["perk:Cull the Weak"]
    # nothing kept yet: everything is unknown, nothing counts as new
    first = tool.compare(DATA, wiki, {})
    assert len(first["unknown"]) == len(tool.used(DATA)) and first["new_perks"] == first["new_addons"] == []


def test_the_tool_runs_from_saved_pages_and_says_so_with_its_exit_code(tool, tmp_path, capsys):
    folder = tmp_path / "pages"
    folder.mkdir()
    for name, text in pages().items():
        (folder / name).write_text(text, encoding="utf-8")
    data, snap = tmp_path / "perkdata.json", tmp_path / "kept.json"
    data.write_text(json.dumps(DATA), encoding="utf-8")
    args = ["--from", str(folder), "--data", str(data), "--snapshot", str(snap)]
    assert tool.main(args) == 1 and "ungeprüft  perk:Sprint Burst" in capsys.readouterr().out     # nothing kept yet
    assert tool.main(args + ["--accept"]) == 0 and snap.exists()
    # 1.55 (the Windows job): the message named the file relative to the repository – impossible when the two
    # are on different drives (ValueError from os.path.relpath); the path is printed as given
    assert f"Einträge in {snap}." in capsys.readouterr().out
    assert tool.main(args) == 1                                      # the retired add-on stays a finding
    assert capsys.readouterr().out.strip() == "ausgemustert addon:Old Thing  (decom im Wiki)"
    slim = {**DATA, "not_modelled": [], "killer_addon_lists": {"The Wraith": ['"Shadow Dance" - Blood']}}
    data.write_text(json.dumps(slim), encoding="utf-8")
    assert tool.main(args) == 0 and "Nichts geändert" in capsys.readouterr().out
    (folder / "loadout.lua").write_text(LOADOUT.replace("2 seconds", "3 seconds"), encoding="utf-8")
    assert tool.main(args) == 1 and "perk:Sprint Burst  Zahlen weg: 2  Zahlen neu: 3" in capsys.readouterr().out
    (folder / "loadout.lua").write_text("something else entirely", encoding="utf-8")
    assert tool.main(args) == 2 and "nicht lesbar" in capsys.readouterr().err      # another layout: no verdict
    os.remove(folder / "datatable.lua")
    assert tool.main(args) == 2


def test_pages_come_from_the_one_host_only(tool, monkeypatch):
    """Read-only, https, the wiki's host – and a redirect elsewhere is refused."""
    seen = []

    class Answer:
        def __init__(self, url, body=b"local p = {}"):
            self.url, self.body = url, body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def geturl(self):
            return self.url

        def read(self, n):
            return self.body[:n]

    def opened(req, timeout=None):
        seen.append((req.full_url, req.get_method(), timeout))
        return Answer(req.full_url)

    monkeypatch.setattr(tool.urllib.request, "urlopen", opened)
    assert tool.fetch("Module:Datatable/Loadout") == "local p = {}"
    url, method, timeout = seen[0]
    assert url == "https://deadbydaylight.wiki.gg/index.php?title=Module%3ADatatable/Loadout&action=raw"
    assert method == "GET" and timeout == tool.TIMEOUT_S
    assert set(tool.read_pages()) == set(tool.PAGES) and len(seen) == 4
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda req, timeout=None: Answer("https://elsewhere.example/x"))
    with pytest.raises(OSError):
        tool.fetch("Module:Datatable")
    monkeypatch.setattr(tool.urllib.request, "urlopen",
                        lambda req, timeout=None: Answer(req.full_url, b"x" * (tool.MAX_BYTES + 5)))
    with pytest.raises(OSError):
        tool.fetch("Module:Datatable")


def test_every_entry_of_the_calculator_has_a_kept_state(tool):
    """The guard: a perk, add-on, item or Killer added to perkdata.json without running the tool (--accept)
    fails here – so no value gets in whose wiki entry nobody can watch."""
    with open(os.path.join(ROOT, "fogscout", "perkdata.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    with open(os.path.join(ROOT, "tools", "perkdata_wiki.json"), encoding="utf-8") as fh:
        kept = json.load(fh)
    used = tool.used(data)
    missing = sorted(set(used) - set(kept["entries"]))
    assert missing == [], f"python tools/check_perkdata.py --accept: {missing[:5]}"
    assert sorted(set(kept["entries"]) - set(used)) == []                        # and nothing left over
    assert all(("n" in kept["entries"][key]) == valued for key, valued in used.items())
    assert all(key in used for key in tool.ALIASES)
    assert len(kept["perks"]) > 300 and len(kept["addons"]) > 900
    text = json.dumps(kept)
    assert "desc =" not in text and "Grants" not in text                         # fingerprints, numbers, names


def test_every_perk_whose_tags_touch_the_calculator_is_decided_on(tool, tmp_path, capsys):
    """1.55.2 (audit: Bardic Inspiration, Deadline, Technician … were missing, because the tool only named perks new
    since the last --accept): a perk whose wiki tags touch a speed, a Skill Check or a Generator's progress must be
    calculated or named in not_modelled / not_modelled_areas / not_relevant – made-up pages first."""
    loadout = LOADOUT.replace('p.perks = {', 'p.perks = {\n    ["Fresh Perk"] = {id = 902, values = {1, 2, 3}, '
                                             'tags = {"Auras", "SkillChecks"}},\n    ["Aura Perk"] = {id = 903, '
                                             'tags = {"Auras", "Generators"}},')
    wiki = tool.entries(pages(loadout))
    kept = tool.state(DATA, wiki)
    assert kept["tags"] == {"Aura Perk": ["Auras", "Generators"], "Fresh Perk": ["Auras", "SkillChecks"]}
    assert tool.unclassified(DATA, kept) == [("Fresh Perk", ["SkillChecks"])]       # "Generators" alone: no
    for key in ("not_modelled", "not_modelled_areas"):
        assert tool.unclassified({**DATA, key: ["Fresh Perk"]}, kept) == []
    judged = {**DATA, "not_relevant": {"Fresh Perk": "only an aura"}}
    assert tool.unclassified(judged, kept) == []
    assert tool.used(judged)["perk:Fresh Perk"] is False                           # watched like "not calculated"
    # a calculated perk under its wiki names (two perks in one entry of the calculator)
    culled = tool.state(DATA, tool.entries(pages(LOADOUT.replace("values = {2, 2.5, 3}",
                                                                  'values = {2, 2.5, 3}, tags = {"Regression"}'))))
    assert culled["tags"] == {"Cull the Weak": ["Regression"]} and tool.unclassified(DATA, culled) == []
    # the tool says so and does not end with 0, not even with --accept
    folder = tmp_path / "pages"
    folder.mkdir()
    for name, text in pages(loadout).items():
        (folder / name).write_text(text, encoding="utf-8")
    data, snap = tmp_path / "perkdata.json", tmp_path / "kept.json"
    data.write_text(json.dumps(DATA), encoding="utf-8")
    args = ["--from", str(folder), "--data", str(data), "--snapshot", str(snap)]
    assert tool.main(args + ["--accept"]) == 1
    assert "nicht eingeordnet  perk:Fresh Perk  (Tags SkillChecks:" in capsys.readouterr().out
    data.write_text(json.dumps(judged), encoding="utf-8")
    assert tool.main(args + ["--accept"]) == 0


def test_the_kept_state_has_every_relevant_perk_decided_on(tool):
    """The guard on the real files (no network): every perk of the kept wiki state whose tags touch the calculator
    is calculated, not calculated by name, or judged irrelevant – a new one that nobody looked at fails here."""
    with open(os.path.join(ROOT, "fogscout", "perkdata.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    with open(os.path.join(ROOT, "tools", "perkdata_wiki.json"), encoding="utf-8") as fh:
        kept = json.load(fh)
    assert len(kept["tags"]) > 300 and set(kept["tags"]) <= set(kept["perks"])
    assert tool.unclassified(data, kept) == [], "decide on them in fogscout/perkdata.json"
    relevant = [n for n, t in kept["tags"].items() if set(t) & tool.RELEVANT_TAGS]
    assert len(relevant) > 100
    # each name decided once: a perk judged irrelevant is neither calculated nor "not calculated"
    calculated = {e["name"] for k in ("perks", "survivor", "killer") for e in data[k]}
    judged = set(data["not_relevant"])
    assert judged <= set(kept["perks"]) and all(data["not_relevant"][n] for n in judged)
    assert not judged & (calculated | set(data["not_modelled"]) | set(data["not_modelled_areas"]))
    # the guard works on this state: a relevant perk added to it is reported
    more = {**kept, "tags": {**kept["tags"], "Tomorrow's Perk": ["RepairSpeed"]}}
    assert tool.unclassified(data, more) == [("Tomorrow's Perk", ["RepairSpeed"])]
