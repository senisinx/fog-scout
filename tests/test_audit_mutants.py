"""1.57.71 (deep review 1.57.67, TEST-03): 15 of 56 one-line faults in critical logic went unnoticed by the suite.
One test each for the ones that matter most – every test here fails with the fault the report names."""
import hashlib
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fogscout import config, hostsedit, official, relupdate  # noqa: E402
from test_relupdate import SETUP, FakeGitHub, _release  # noqa: E402


def test_a_release_asset_of_another_tag_is_refused():
    """Mutant: parse_release checked only the prefix of the download URL. An asset of this repository but of another
    release (an older, maybe vulnerable build) must not pass for this one."""
    data = _release(build=42)
    for a in data["assets"]:
        a["browser_download_url"] = a["browser_download_url"].replace("build-42/", "build-41/")
    with pytest.raises(ValueError):
        relupdate.parse_release(data)
    assert relupdate.parse_release(_release(build=42)).tag == "build-42"


def test_a_download_bigger_than_the_release_says_is_refused(tmp_path):
    """Mutant: the size check of the download removed. The checksum alone does not catch it when the checksum
    itself names the bigger file – the size from the release must hold too."""
    big = SETUP + b"appended"
    digest = hashlib.sha256(big).hexdigest()
    data = _release()
    data["assets"][0]["digest"] = "sha256:" + digest                    # size still says len(SETUP)
    rel = relupdate.parse_release(data)
    gh = FakeGitHub(release=data, setup=big, sha_text=f"{digest}  FogScout-Setup-1.33.exe\n")
    with pytest.raises((OSError, ValueError)):
        relupdate.download(rel, str(tmp_path), opener=gh)
    folder = os.path.join(str(tmp_path), relupdate.UPDATE_DIR)
    assert not os.path.exists(os.path.join(folder, "FogScout-Setup-1.33.exe"))


def test_a_hosts_line_with_a_managed_and_a_foreign_name_is_not_ours():
    """Mutant: _ours with any() instead of all(). After a begin marker without its end marker, a line that names a
    managed server and the user's own name belongs to the user – deleting it with our section loses their entry."""
    managed = hostsedit.MANAGED[0]
    text = hostsedit.BEGIN + "\r\n0.0.0.0 " + managed + " printer.local\r\n127.0.0.1 localhost\r\n"
    out = hostsedit.build(text, [], remove_foreign=False)
    assert "printer.local" in out and "localhost" in out
    assert not hostsedit._ours("0.0.0.0 " + managed + " printer.local") and hostsedit._ours("0.0.0.0 " + managed)


def test_a_settings_version_of_true_runs_no_migration_again(tmp_path):
    """Mutant: the bool guard of config._version removed – True counted as version 1 and every migration ran again
    (the pre-roll and the join of recordings switched off, the record row hidden …)."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"settings_version": True, "rec_pre": True, "rec_merge": True}), encoding="utf-8")
    s = config.Settings(str(p))
    assert s["rec_pre"] is True and s["rec_merge"] is True and s["settings_version"] == config.SETTINGS_VERSION


def test_of_two_official_matches_the_one_at_the_usual_offset_is_tied():
    """Mutant: official.link ranked by abs(offset) instead of abs(offset - LINK_TYPICAL). The banner shows about
    LINK_TYPICAL seconds after the match started – of two candidates on the same map that one is the round's."""
    banner = 1_780_000_000.0
    rnd = SimpleNamespace(t=banner, map_id="coal-tower")
    near = SimpleNamespace(t=banner - 5, map="Coal Tower")
    usual = SimpleNamespace(t=banner - official.LINK_TYPICAL, map="Coal Tower")
    tied, other = official.link([rnd], [near, usual], lambda name: "coal-tower")
    assert tied[0] is usual and other == []
