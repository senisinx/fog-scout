"""Red-team audit (reports/red-team/): attacks turned into tests before any fix.

Each test names its attack id (RS-…) from reports/red-team/01_ATTACK_CATALOG.md. Tests marked "verified" reproduce an
attack the program already stops – they are expected to pass and document that. All others reproduced the attack on
the commit the audit started from (red) and stay red until the remediation in 04_REMEDIATION_PLAN.md is approved.

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


def _open(attack: str, strict: bool = True):
    """An attack that still works on this commit: strict xfail, so the suite stays green until the fix and turns
    red (XPASS) the moment the fix lands – then the marker goes. ``pytest --runxfail`` shows the attack failing."""
    return pytest.mark.xfail(strict=strict, reason=f"{attack} open – reports/red-team/04_REMEDIATION_PLAN.md")


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


@_open("RS-001")
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


@_open("RS-001")
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
@_open("RS-002", strict=not WIN)      # reproduced on Linux; Windows links not run in the audit
@pytest.mark.parametrize("linked", ["leaf", "parent"])
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
    else:
        _symlink_dir(str(victim), str(data / "cache"))
    cache = str(data / "cache" / "clipthumbs") if linked == "leaf" else str(data / "cache")
    thumbs.prune(cache)                                  # qt_library.ThumbLoader / app_recordings: .png/.jpg
    thumbs.prune(cache, exts=(".json",))                 # clipedit._analysis_write: the editor's analyses
    assert (victim / "holiday.jpg").exists(), "a picture outside the data folder was deleted"
    assert (victim / "config.json").exists(), "a JSON file outside the data folder was deleted"


@_open("RS-002", strict=not WIN)      # reproduced on Linux; Windows links not run in the audit
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


@_open("RS-002", strict=not WIN)      # reproduced on Linux; Windows links not run in the audit
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
@_open("RS-003")
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
@_open("RS-008")
def test_rs_008_a_section_without_its_end_marker_keeps_the_users_own_comments():
    from fogscout import hostsedit
    text = (hostsedit.BEGIN + "\r\n0.0.0.0 gamelift.eu-west-1.amazonaws.com\r\n"
            "# my note: printer at the office\r\n#10.0.0.5 printer.local\r\n127.0.0.1 localhost\r\n")
    for remove_foreign in (True, False):
        out = hostsedit.build(text, [], remove_foreign=remove_foreign)
        assert "gamelift.eu-west-1" not in out                        # our own line goes, as it should
        assert "# my note: printer at the office" in out and "#10.0.0.5 printer.local" in out, out


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
