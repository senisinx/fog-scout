"""Red-team audit (reports/red-team/): attacks turned into tests before any fix.

Each test names its attack id (RS-…) from reports/red-team/01_ATTACK_CATALOG.md. Tests marked "verified" reproduce an
attack the program already stopped at the audited commit (1469fbf). All others reproduced the attack there (red, see
03_EXPLOIT_TESTS.md) and pass since the fixes of 1.57.48 (05_FINAL_VERIFICATION.md).

Nothing here touches real user data, the hosts file, the registry, the task scheduler or the network: temp folders,
symlinks below tmp_path and monkeypatched process starts only.
"""
import json
import os
import sys
import time
import zipfile

import pytest

from fogscout import backups, history, launch, mapstyle, obsrec, thumbs, corpus

WIN = sys.platform == "win32"
OLD = time.time() - 400 * 86400          # older than every prune age the program uses


def _symlink_dir(target, link):
    """A directory link the way a normal program of the same user makes one (a junction on Windows needs no
    privilege; os.symlink may) – skipped where the test cannot make it."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"cannot create a directory link here: {e}")


def _old_file(path, data=b"x"):
    with open(path, "wb") as fh:
        fh.write(data)
    os.utime(path, (OLD, OLD))


# ---------------------------------------------------------------------------------------------------------------
# RS-001: a backup ZIP (untrusted file the user picks) stores times the statistics cannot show – 1.46.4 refused
# NaN/Infinity only for counted rounds; lost-round lines and finite but huge values still get in.
def _backup_zip(path, rounds_lines):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("rounds.jsonl", "\n".join(rounds_lines) + "\n")


GOOD = '{"t": 1700000000.0, "seconds": 600, "map_id": "coal-tower", "map": "Coal Tower"}'
HOSTILE_ROUNDS = {
    "lost_infinity": '{"lost": true, "t": Infinity, "map": "Coal Tower", "reason": "quit"}',
    "lost_nan": '{"lost": true, "t": NaN, "map": "Coal Tower", "reason": "quit"}',
    "lost_huge": '{"lost": true, "t": 1e300, "map": "Coal Tower", "reason": "quit"}',
    "round_huge_start": '{"t": 1e300, "seconds": 600, "map_id": "coal-tower", "map": "Coal Tower"}',
    "round_huge_length": '{"t": 1700001000.0, "seconds": 1e300, "map_id": "coal-tower", "map": "Coal Tower"}',
}


def _showable(t):
    """What the statistics do with a start/end: a local date (time.localtime), as app_stats does."""
    try:
        time.localtime(t)
        return True
    except (OverflowError, OSError, ValueError):
        return False


@pytest.mark.parametrize("case", sorted(HOSTILE_ROUNDS))
def test_rs_001_a_restored_backup_never_stores_a_time_the_program_cannot_show(tmp_path, case):
    """Invariant: whatever a backup ZIP holds, every round and lost round the program stores afterwards has a start
    and an end that are real dates. Attack: a crafted ZIP whose rounds.jsonl holds one hostile line."""
    data = tmp_path / "data"
    data.mkdir()
    z = str(tmp_path / "evil.zip")
    _backup_zip(z, [GOOD, HOSTILE_ROUNDS[case]])
    backups.restore(str(data), z)
    path = str(data / history.FILE)
    for r in history.load(path):
        assert _showable(r.t) and _showable(r.t + r.seconds), (case, r.t, r.seconds)
    for r in history.load_lost_rounds(path):
        assert _showable(r.t), (case, r.t)


@pytest.mark.parametrize("line", ['{"t": 1e300, "map": "Coal Tower"}',
                                  '{"t": 1700000000.0, "map": "Coal Tower", "seconds": 1e300}',
                                  '{"t": -1e300, "map": "Coal Tower"}'])
def test_rs_001_official_matches_from_a_backup_hold_only_showable_times(tmp_path, line):
    from fogscout import official
    data = tmp_path / "data"
    data.mkdir()
    z = str(tmp_path / "evil.zip")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("official.jsonl", '{"t": 1700000500.0, "map": "Coal Tower"}\n' + line + "\n")
    backups.restore(str(data), z)
    for m in official.load(str(data / official.FILE)):
        assert _showable(m.t) and _showable(m.t + m.seconds), (m.t, m.seconds)


def test_rs_001_a_match_file_in_the_downloads_folder_cannot_store_an_endless_length(tmp_path):
    """The userscript's file is read from the downloads folder – any web page can put one there."""
    from fogscout import official
    dl = tmp_path / "dl"
    dl.mkdir()
    now = time.time()
    data = {"format": official.FORMAT, "script": 9, "matches": [{"start": now - 3600, "map": "Coal Tower",
            "player": {"role": "killer", "seconds": 1e300, "character": "The Trapper"}, "opponents": []}]}
    (dl / "fogscout-matches.json").write_text(json.dumps(data), encoding="utf-8")
    store = tmp_path / official.FILE
    official.take_downloads(str(dl), str(store), now)
    matches = official.load(str(store))
    assert len(matches) == 1 and _showable(matches[0].t + matches[0].seconds)


@pytest.mark.parametrize("value", [1e300, -1e300, 5e12])
def test_rs_001_a_recordings_index_holds_only_showable_times(tmp_path, value):
    """Found in the counter-check (05): the index lies in the recordings folder (writable, maybe synced) –
    {"t": 1e300} made the page Aufnahmen raise OverflowError on every render. The entry stays (its file can still be
    pruned), only its time is unknown (0)."""
    from fogscout import recindex
    folder = tmp_path / "rec"
    (folder / "Clips").mkdir(parents=True)
    (folder / recindex.INDEX).write_text(json.dumps({"t": value, "file": "a.mkv", "end": value}) + "\n",
                                         encoding="utf-8")
    (folder / "Clips" / recindex.CLIPS_INDEX).write_text(json.dumps({"file": "c.mp4", "t": value, "source": value})
                                                         + "\n", encoding="utf-8")
    recs = recindex.load_index(str(folder))
    assert [r.file for r in recs] == ["a.mkv"] and _showable(recs[0].t) and _showable(recs[0].end)
    clips = recindex.load_clips(str(folder / "Clips"))
    assert [c.file for c in clips] == ["c.mp4"] and _showable(clips[0].t) and _showable(clips[0].source)


def test_rs_001_the_statistics_still_open_after_restoring_a_hostile_backup(tmp_path):
    """The impact of RS-001 in the real program: after the restore, every page and every statistics tab renders
    without an error (before: OverflowError/ValueError on each render – the statistics stayed broken for good)."""
    if WIN:
        pytest.skip("Linux: the Windows job tests the native parts; the app would touch the system there")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from test_robustness import _pump_app, _start
    root = tmp_path / "root"
    root.mkdir()
    z = str(tmp_path / "evil.zip")
    _backup_zip(z, [GOOD, HOSTILE_ROUNDS["lost_infinity"], HOSTILE_ROUNDS["round_huge_length"]])
    backups.restore(str(root), z)
    a = _start(root, {"welcome_seen": True}, rounds=(root / history.FILE).read_bytes())
    try:
        _pump_app(a, 0.3)
        for key in a.qt.nav_keys():
            a.qt.show_page(key)
            _pump_app(a, 0.05)
        a.qt.show_page("stats")
        for title, _part in list(a._stats_parts.values()):
            a._stats_select(title)
            a._stats_render()
            a._stats_render_tab()
            _pump_app(a, 0.02)
        errors = [e for e in a._log_entries if e[1] == "Fehler"]
        assert not a._errors_seen and not errors, errors[:3]
    finally:
        a.quit()


# ---------------------------------------------------------------------------------------------------------------
# RS-002: the elevated program prunes its caches below the data folder (%LOCALAPPDATA%\FogScout, the user's). The
# folder it prunes may itself be a link a normal program of the user made – fsops.delete_inside resolves the folder
# and deletes inside its target with administrator rights.
@pytest.mark.parametrize("linked", ["leaf", "parent", "cache_above_leaf"])
def test_rs_002_thumbnail_pruning_never_deletes_through_a_linked_cache_folder(tmp_path, linked):
    """Invariant: pruning a cache folder below the data folder deletes only files that really lie below the data
    folder. Attack: data/cache/clipthumbs (or data/cache) is a directory link to a folder of someone else's
    pictures; the elevated program prunes "old thumbnails" once per session."""
    victim = tmp_path / "victim"
    victim.mkdir()
    _old_file(str(victim / "holiday.jpg"))
    _old_file(str(victim / "config.json"))
    data = tmp_path / "data"
    data.mkdir()
    if linked == "leaf":
        (data / "cache").mkdir()
        _symlink_dir(str(victim), str(data / "cache" / "clipthumbs"))
        cache = str(data / "cache" / "clipthumbs")
    elif linked == "parent":
        _symlink_dir(str(victim), str(data / "cache"))
        cache = str(data / "cache")
    else:                                                # data/cache → victim, pruned: data/cache/clipthumbs
        (victim / "clipthumbs").mkdir()
        for name in ("holiday.jpg", "config.json"):
            _old_file(str(victim / "clipthumbs" / name))
        _symlink_dir(str(victim), str(data / "cache"))
        cache = str(data / "cache" / "clipthumbs")
        victim = victim / "clipthumbs"
    thumbs.prune(cache)                                  # qt_library.ThumbLoader / app_recordings: .png/.jpg
    thumbs.prune(cache, exts=(".json",))                 # clipedit._analysis_write: the editor's analyses
    assert (victim / "holiday.jpg").exists(), "a picture outside the data folder was deleted"
    assert (victim / "config.json").exists(), "a JSON file outside the data folder was deleted"


def test_rs_002_style_cache_pruning_never_deletes_through_a_linked_cache_folder(tmp_path):
    victim = tmp_path / "victim"
    (victim / "maps").mkdir(parents=True)
    name = f"coal-tower-0abc-1280-v{mapstyle.STYLE_VERSION - 1}.webp"      # a name of ours, of an old version
    _old_file(str(victim / "maps" / name))
    data = tmp_path / "data"
    (data / "cache").mkdir(parents=True)
    _symlink_dir(str(victim), str(data / "cache" / "maps_dark"))
    mapstyle.prune(str(data / "cache" / "maps_dark"))
    assert (victim / "maps" / name).exists()


def test_rs_002_corpus_pruning_never_deletes_through_a_linked_corpus_folder(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    stamps = ["20200101-000000-000", "20200101-000000-001"]       # names of ours: 19 characters + .json/.jpg
    for stamp in stamps:
        _old_file(str(victim / (stamp + ".json")))
        _old_file(str(victim / (stamp + ".jpg")))
    data = tmp_path / "data"
    data.mkdir()
    _symlink_dir(str(victim), str(data / corpus.DIR))
    corpus.prune(corpus.folder(str(data)), keep=1)                 # the oldest beyond "keep" go
    assert all((victim / (s + ext)).exists() for s in stamps for ext in (".json", ".jpg"))


def test_rs_002_backup_pruning_never_deletes_through_a_linked_backup_folder(tmp_path):
    """The daily copies of rounds.jsonl (backup/, KEEP newest): a linked backup folder is neither pruned."""
    victim = tmp_path / "victim"
    victim.mkdir()
    olds = [f"rounds-2020-01-0{d}.jsonl" for d in range(1, 9)]
    for name in olds:
        _old_file(str(victim / name), b"{}\n")
    data = tmp_path / "data"
    data.mkdir()
    _symlink_dir(str(victim), str(data / "backup"))
    for day in range(backups.KEEP + 5):                  # a new state every day: one copy each, then pruning
        (data / history.FILE).write_text(GOOD + "\n" * (day + 1), encoding="utf-8")
        backups.snapshot(str(data), now=time.time() + day * 86400)
    assert all((victim / name).exists() for name in olds)


def test_rs_002_verified_a_link_below_the_pruned_folder_is_still_not_followed(tmp_path):
    """verified (1.38.57): a link *inside* the pruned folder is never followed – the gap is only the folder itself."""
    victim = tmp_path / "victim"
    victim.mkdir()
    _old_file(str(victim / "a.jpg"))
    cache = tmp_path / "data" / "cache" / "clipthumbs"
    cache.mkdir(parents=True)
    try:
        os.symlink(str(victim / "a.jpg"), str(cache / "a.jpg"))
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"cannot create a file link here: {e}")
    os.utime(str(cache / "a.jpg"), (OLD, OLD), follow_symlinks=False)
    thumbs.prune(str(cache))
    assert (victim / "a.jpg").exists()


# ---------------------------------------------------------------------------------------------------------------
# RS-003: "OBS mit DBD starten" – the elevated program (scheduled task, highest rights) starts obs64.exe as a child:
# OBS runs as administrator and loads the scripts listed in the user's scene collection (%APPDATA%\obs-studio, any
# program of the user may write it). Invariant: the elevated program never hands its administrator token to OBS.
def test_rs_003_the_elevated_program_never_starts_obs_with_its_own_token(monkeypatch):
    started = []

    class FakePopen:
        def __init__(self, args, *a, **k):
            started.append(list(args))
    monkeypatch.setattr(launch, "elevated", lambda: True)
    monkeypatch.setattr(launch.subprocess, "Popen", FakePopen)
    exe = os.path.join(os.sep, "Program Files", "obs-studio", "bin", "64bit", obsrec.OBS_EXE)
    try:
        obsrec.Recorder._start_obs_process(exe)
    except OSError:
        pass                                             # refusing to start it is fine as well
    direct = [a for a in started if a and os.path.basename(str(a[0])).lower() == obsrec.OBS_EXE]
    assert not direct, f"OBS started as a child of the elevated program: {direct}"


def test_rs_003_dbd_starting_while_elevated_says_start_obs_yourself_and_starts_nothing(tmp_path, monkeypatch):
    """The whole path: DBD starts, OBS is not reachable, "OBS mit DBD starten" is on and Fog Scout runs as
    administrator – nothing is started, one warning says why, and it does not repeat within the DBD session."""
    from test_obsrec import FakeObs, _drain, _recorder
    obs = FakeObs(record_dir=str(tmp_path))
    obs.start()
    try:
        monkeypatch.setattr(launch, "elevated", lambda: True)
        monkeypatch.setattr(obsrec, "obs_exe", lambda: str(tmp_path / obsrec.OBS_EXE))
        monkeypatch.setattr(obsrec, "_top_windows", lambda: [])
        r, posted = _recorder(obs, str(tmp_path), pre=False, instant=True, buffer_auto=True, audio=False,
                              obs_start=True)
        started = []
        r.start_obs = started.append
        r.cfg.port = 1                                       # OBS not running
        r._game_changed(True)
        warns = [d["text"] for k, d in _drain(posted) if k == "warn"]
        assert started == [] and warns == [obsrec.OBS_ELEVATED()]
        r._next_check = 0
        r._recheck()
        assert started == [] and obsrec.OBS_ELEVATED() not in [d.get("text") for k, d in _drain(posted)]
    finally:
        obs.stop()


def test_rs_003_verified_not_elevated_obs_is_started_as_before(monkeypatch):
    """verified: without administrator rights nothing changes – OBS is started directly, in its own folder."""
    started = []

    class FakePopen:
        def __init__(self, args, *a, **k):
            started.append((list(args), k.get("cwd")))
    monkeypatch.setattr(launch, "elevated", lambda: False)
    monkeypatch.setattr(launch.subprocess, "Popen", FakePopen)
    exe = os.path.join(os.sep, "obs", "bin", "64bit", obsrec.OBS_EXE)
    obsrec.Recorder._start_obs_process(exe)
    assert started and started[0][0][0] == exe and started[0][1] == os.path.dirname(exe)


# ---------------------------------------------------------------------------------------------------------------
# RS-008: the elevated hosts helper treats every comment after a begin marker without its end marker as its own and
# deletes it – the user's notes and commented-out entries go (a file cut by another tool, an editor, a sync).
def test_rs_008_a_section_without_its_end_marker_keeps_the_users_own_comments():
    from fogscout import hostsedit
    text = (hostsedit.BEGIN + "\r\n0.0.0.0 gamelift.eu-west-1.amazonaws.com\r\n"
            "# my note: printer at the office\r\n#10.0.0.5 printer.local\r\n127.0.0.1 localhost\r\n")
    for remove_foreign in (True, False):
        out = hostsedit.build(text, [], remove_foreign=remove_foreign)
        assert "gamelift.eu-west-1" not in out                        # our own line goes, as it should
        assert "# my note: printer at the office" in out and "#10.0.0.5 printer.local" in out, out



def test_rs_008_our_own_section_without_its_end_marker_still_goes_completely():
    """The counter-check: a section of ours cut after its own lines (no end marker) is removed as before – our
    comments, the managed entries and the blank lines – and the user's lines around it stay."""
    from fogscout import hostsedit
    text = ("127.0.0.1 localhost\r\n\r\n" + hostsedit.BEGIN + "\r\n# Written by Fog Scout. Blocked names = …\r\n"
            "# allowed: eu-west-1\r\n0.0.0.0 gamelift.eu-central-1.amazonaws.com\r\n\r\n")
    assert hostsedit.build(text, []) == "127.0.0.1 localhost\r\n"
    assert hostsedit.build(text, [], remove_foreign=False) == "127.0.0.1 localhost\r\n"


# ---------------------------------------------------------------------------------------------------------------
# Verified (no finding): attacks the program already stops, re-run here on the audited commit.
@pytest.mark.parametrize("name", ["../settings.json", "user_maps/../settings.json", "/user_maps/a.png",
                                  "C:/Windows/a.png", "user_maps\\..\\..\\a.png", "user_maps/a/b.png",
                                  "user_maps/..", "corpus/../../x.json", "user_maps/\u2025/a.png"])
def test_rs_010_verified_zip_member_names_never_leave_the_data_folder(name):
    assert not backups._allowed(name), name


def test_rs_011_verified_claude_operations_with_non_numbers_change_nothing():
    """verified (1.28): an answer with NaN/Infinity/huge/negative/boolean values or unknown kinds is refused, never
    clamped – the edit stays as it was."""
    from fogscout import editcommands, sequence
    state = sequence.EditState(parts=[sequence.Part(0.0, 60.0)])
    ops = [{"op": "cut", "from": float("nan"), "to": 10}, {"op": "cut", "from": 0, "to": float("inf")},
           {"op": "hold", "at": 5, "seconds": 1e9}, {"op": "speed", "from": 0, "to": 10, "factor": 1e6},
           {"op": "split", "at": True}, {"op": "shell", "cmd": "calc.exe"}, {"op": "censor", "x": -1e308, "y": 0,
                                                                              "w": 1e308, "h": 1}]
    new, mode, done, skipped = editcommands.apply(state, ops, "clip", picture=False)
    assert done == [] and len(skipped) == len(ops) and mode is None
    assert [(p.start, p.end) for p in new.parts] == [(0.0, 60.0)]


def test_rs_012_verified_the_hosts_job_cannot_name_any_other_server(tmp_path, monkeypatch):
    """verified: the job file lies in %TEMP% (the user's) – a changed job can only name GameLift servers."""
    from fogscout import hostsedit
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"127.0.0.1 localhost\r\n")
    monkeypatch.setattr(hostsedit, "hosts_path", lambda: str(hosts))
    for evil in (["windowsupdate.microsoft.com"], ["gamelift.eu-west-1.amazonaws.com\r\n1.2.3.4 evil"],
                 ["GAMELIFT.EU-WEST-1.AMAZONAWS.COM evil.com"]):
        res = hostsedit.apply_job({"block": evil})
        assert not res["ok"], evil
    assert hosts.read_bytes() == b"127.0.0.1 localhost\r\n"
    res = hostsedit.apply_job({"block": ["gamelift.eu-west-1.amazonaws.com"], "allowed": ["x\r\n1.2.3.4 evil"]})
    assert res["ok"] and b"evil" not in hosts.read_bytes()


def test_rs_013_verified_a_queued_upload_cannot_point_outside_the_recordings_folder():
    from fogscout import fsops
    for name in ("..\\..\\Windows\\win.ini", "/etc/passwd", "C:x.mp4", "a/b/c.mp4", "\\\\server\\share\\a.mp4",
                 "a\x00.mp4", "./../a.mp4"):
        assert fsops.rel_path("/rec", name) is None, name
    assert json.dumps(fsops.rel_path("/rec", "Farming/a.mp4"))
