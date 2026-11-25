"""1.18.1: fsops (the file primitives of project saving – nothing is ever replaced) and paths (the per-user data
folder). Linux runs the POSIX path, the Windows job the handle path; both check the same promises."""
import ast
import errno
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fogscout import fsops, paths  # noqa: E402

WIN = sys.platform == "win32"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write(path, data=b"x"):
    with open(path, "wb") as fh:
        fh.write(data)


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_create_exclusive_refuses_an_existing_target(tmp_path):
    src, dst = str(tmp_path / "a.tmp"), str(tmp_path / "b.json")
    _write(src, b"ours")
    _write(dst, b"foreign")
    with pytest.raises(FileExistsError):
        fsops.create_exclusive(src, dst)
    assert _read(dst) == b"foreign" and _read(src) == b"ours"
    os.remove(dst)
    fsops.create_exclusive(src, dst)
    assert _read(dst) == b"ours" and not os.path.exists(src)


def test_write_new_is_complete_or_nothing_and_never_over_a_file(tmp_path):
    dst = str(tmp_path / "p.json")
    fsops.write_new(dst, b"first")
    with pytest.raises(FileExistsError):
        fsops.write_new(dst, b"second")
    assert _read(dst) == b"first"
    assert [n for n in os.listdir(tmp_path) if n.endswith(".tmp")] == []          # no temp file left behind


@pytest.mark.skipif(WIN, reason="the POSIX path")
def test_no_fallback_when_the_file_system_refuses(tmp_path, monkeypatch):
    """renameat2 missing or refused (EINVAL/ENOSYS) → UnsupportedFS, nothing renamed, and no other call (replace,
    rename, link, shutil) is tried."""
    import shutil
    calls = []
    for mod, name in ((os, "replace"), (os, "rename"), (os, "link"), (shutil, "move"), (shutil, "copyfile")):
        monkeypatch.setattr(mod, name, lambda *a, _n=name, **k: calls.append(_n))
    src, dst = str(tmp_path / "a.tmp"), str(tmp_path / "b.json")
    _write(src, b"ours")
    for code in (errno.EINVAL, errno.ENOSYS):
        def refuse(*a, _c=code):
            import ctypes
            ctypes.set_errno(_c)
            return -1
        monkeypatch.setattr(fsops, "_RENAMEAT2", [refuse])
        with pytest.raises(fsops.UnsupportedFS):
            fsops.create_exclusive(src, dst)
    monkeypatch.setattr(fsops, "_RENAMEAT2", [None])                               # glibc without renameat2
    with pytest.raises(fsops.UnsupportedFS):
        fsops.create_exclusive(src, dst)
    assert calls == [] and not os.path.exists(dst) and _read(src) == b"ours"


def test_an_unknown_platform_fails_safely(tmp_path, monkeypatch):
    monkeypatch.setattr(fsops, "WIN", False)
    monkeypatch.setattr(fsops, "LINUX", False)
    src = str(tmp_path / "a.tmp")
    _write(src)
    with pytest.raises(fsops.UnsupportedFS):
        fsops.create_exclusive(src, str(tmp_path / "b.json"))
    assert not os.path.exists(tmp_path / "b.json")


_RACE = r"""
import os, sys, time
sys.path.insert(0, sys.argv[1])
from fogscout import fsops
src, dst, go = sys.argv[2], sys.argv[3], sys.argv[4]
while not os.path.exists(go):
    time.sleep(0.001)
try:
    fsops.create_exclusive(src, dst)
    print("won")
except FileExistsError:
    print("lost")
"""


def test_two_processes_creating_the_same_file_exactly_one_wins(tmp_path):
    for round_ in range(20):
        d = tmp_path / str(round_)
        d.mkdir()
        dst, go = str(d / "p.json"), str(d / "go")
        procs = []
        for who in (b"one", b"two"):
            src = str(d / (who.decode() + ".tmp"))
            _write(src, who)
            procs.append(subprocess.Popen([sys.executable, "-c", _RACE, ROOT, src, dst, go], stdout=subprocess.PIPE,
                                          text=True))
        _write(go)
        outs = sorted(p.communicate(timeout=60)[0].strip() for p in procs)
        assert outs == ["lost", "won"], outs
        winner = b"one" if not os.path.exists(d / "one.tmp") else b"two"
        assert _read(dst) == winner                                               # the loser's file is untouched
        assert os.path.exists(d / ((b"two" if winner == b"one" else b"one").decode() + ".tmp"))


def test_the_exclusive_handle_reads_renames_and_never_replaces(tmp_path):
    a, b, c = str(tmp_path / "a.json"), str(tmp_path / "b.json"), tmp_path / "Sicherungen" / "c.json"
    _write(a, b"content")
    _write(b, b"foreign")
    c.parent.mkdir()
    with fsops.ExclusiveHandle(a) as h:
        assert h.read() == b"content"
        with pytest.raises(FileExistsError):
            h.rename_to(b)
        assert _read(b) == b"foreign"
        h.rename_to(str(c))                                                       # into a sub-folder (W23)
        assert h.read() == b"content"                                             # still the same file
    assert not os.path.exists(a) and _read(str(c)) == b"content"


def test_delete_verified_deletes_only_the_expected_content(tmp_path):
    a = str(tmp_path / "a.json")
    _write(a, b"kept")
    assert fsops.delete_verified(a, fsops.sha256_bytes(b"other"), 4) is False       # same size, other content
    assert fsops.delete_verified(a, fsops.sha256_bytes(b"kept"), 5) is False        # wrong size
    assert _read(a) == b"kept"
    assert fsops.delete_verified(a, fsops.sha256_bytes(b"kept"), 4) is True
    assert not os.path.exists(a)
    with pytest.raises(FileNotFoundError):
        fsops.delete_verified(a, fsops.sha256_bytes(b"kept"), 4)


_OPEN_TRY = r"""
import ctypes, sys
from ctypes import wintypes
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                          wintypes.DWORD, wintypes.HANDLE]
k.CreateFileW.restype = wintypes.HANDLE
h = k.CreateFileW(sys.argv[1], 0x40000000, 7, None, 3, 0x80, None)
print("blocked" if h is None or h in (-1, 2 ** 64 - 1, 2 ** 32 - 1) else "opened")
"""


@pytest.mark.skipif(not WIN, reason="Windows share modes")
def test_windows_nobody_can_open_the_file_between_the_check_and_the_rename(tmp_path):
    """While ExclusiveHandle holds the file – after reading it, before renaming – another process asking for write
    access with every share flag is refused; after the rename, too, until the handle closes."""
    a, b = str(tmp_path / "a.json"), str(tmp_path / "b.json")
    _write(a, b"content")
    with fsops.ExclusiveHandle(a) as h:
        assert h.read() == b"content"
        res = subprocess.run([sys.executable, "-c", _OPEN_TRY, a], capture_output=True, text=True, timeout=60)
        assert res.stdout.strip() == "blocked", res.stderr
        h.rename_to(b)
        res = subprocess.run([sys.executable, "-c", _OPEN_TRY, b], capture_output=True, text=True, timeout=60)
        assert res.stdout.strip() == "blocked", res.stderr
    res = subprocess.run([sys.executable, "-c", _OPEN_TRY, b], capture_output=True, text=True, timeout=60)
    assert res.stdout.strip() == "opened"


@pytest.mark.skipif(not WIN, reason="Windows share modes")
def test_windows_the_handle_cannot_be_had_while_another_program_has_the_file_open(tmp_path):
    a = str(tmp_path / "a.json")
    _write(a, b"content")
    with open(a, "rb"):
        with pytest.raises(PermissionError):
            fsops.ExclusiveHandle(a)
    fsops.ExclusiveHandle(a).close()


# ---- the guard: only these primitives touch names
ALLOWED = {                       # (module, function) → calls it may make
    ("fsops", "create_exclusive"): {"os.rename"},
    ("fsops", "rename_fallback"): {"os.rename"},
    ("fsops", "discard_tmp"): {"os.remove"},
    ("fsops", "delete_inside"): {"os.remove"},   # 1.33.5: POSIX, after every part below the folder was checked
    ("fsops", "delete"): {"os.unlink"},
    ("fsops", "_replace_into"): {"os.replace"},  # 1.34.2: the one replacing write (write_atomic, CR-007: …_stream)
}
WATCHED = {"os.rename", "os.replace", "os.remove", "os.unlink", "os.link", "shutil.move", "shutil.copyfile",
           "shutil.copy", "shutil.copy2", "shutil.rmtree", "os.renames", "os.removedirs"}
MODULES = ("fsops", "paths", "project", "filehash", "projectsave")


def test_filesystem_calls_are_only_the_allowed_primitives():
    """1.18.1 (plan 3.7): in the modules of project saving, renaming/replacing/removing happens only in the reviewed
    primitives – os.replace only for the hash cache, no shutil anywhere."""
    found = []
    for mod in MODULES:
        path = os.path.join(ROOT, "fogscout", mod + ".py")
        if not os.path.exists(path):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())

        def visit(node, func):
            for child in ast.iter_child_nodes(node):
                f = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) \
                        and isinstance(child.func.value, ast.Name):
                    name = f"{child.func.value.id}.{child.func.attr}"
                    if name in WATCHED and name not in ALLOWED.get((mod, func), set()):
                        found.append((mod, func, name, child.lineno))
                visit(child, f)
        visit(tree, None)
    assert found == []


# CR-001 (code review): a raw os.remove/os.unlink deletes through junctions and links – with administrator rights
# (installed: RunLevel Highest) a folder of the user swapped for a junction would have its target's files deleted.
# Deleting goes through fsops.delete_inside (or delete_verified); these few places delete one exact file the program
# itself just made or named, each reviewed. A new raw delete fails here until it is reviewed and named.
RAW_DELETES = {
    ("__main__", "_crash_log_clear"),       # the crash file in the program/data folder, by its fixed name
    ("app_settings", "_show_update_status"),  # .venv/update_status.txt of start.bat, by its fixed name
    ("autostart", "install"),               # old icon files by fixed names (icon.OLD_FILES)
    ("clipedit", "_remove"),                # the ffmpeg output .tmp the program itself just created
    ("clipedit", "sound_wav"),              # its own temp wav (mkstemp)
    ("clipedit", "_sound_with_music"),      # its own temp wav (mkstemp)
    ("connwatch", "_remove"),               # the helper's control/result files it made itself (mkstemp)
    ("fsops", "discard_tmp"), ("fsops", "delete"), ("fsops", "delete_inside"),   # the primitives
    ("history", "clear"),                   # rounds.jsonl by its fixed name in the data folder
    ("imageedit", "save"),                  # its own .tmp next to the copy
    ("mapimage", "save"),                   # user_maps/<slug>.<ext> variants of the picture just saved
    ("obsrec", "merge_files"),              # the concat list / unfinished output it made itself
    ("obsrec", "_join"),                    # its own .tmp and the joined part after a checked join
    ("obsrec", "_instant_clip"),            # its own ffmpeg output that failed (the buffer: delete_inside, CR-007)
    ("official", "clear"), ("official", "take_downloads"),   # official.jsonl; our own marked exports
    ("picturedlg", "delete"),               # a user_maps picture the user deleted
    ("qt_clip", "_drop_wav"),               # its own temp wav
    ("regions", "run_job"),                 # its own job/result files (mkstemp)
    ("rename", "migrate"),                  # files of the old name in the program folder
    ("restart", "staged_setup"),            # its own copy that failed the hash
    ("takeover", "_copy_file"), ("takeover", "finish"),   # its own .tmp; its note of the old folder
}


def test_raw_deletes_are_only_the_reviewed_places():
    found = set()
    for name in sorted(os.listdir(os.path.join(ROOT, "fogscout"))):
        if not name.endswith(".py"):
            continue
        mod = name[:-3]
        tree = ast.parse(open(os.path.join(ROOT, "fogscout", name), encoding="utf-8").read())

        def visit(node, func):
            for child in ast.iter_child_nodes(node):
                f = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) \
                        and isinstance(child.func.value, ast.Name) \
                        and f"{child.func.value.id}.{child.func.attr}" in ("os.remove", "os.unlink"):
                    found.add((mod, func))
                visit(child, f)
        visit(tree, None)
    assert found - RAW_DELETES == set()
    assert RAW_DELETES - found == set(), "a reviewed place no longer deletes – take it off the list"


# ---- paths
def test_the_data_folder_is_the_test_folder_and_its_files_are_made_once(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV, str(tmp_path / "data"))
    assert paths.user_data_dir() == str(tmp_path / "data")
    wid = paths.writer_id()
    assert wid and len(wid) == 32 and paths.writer_id() == wid
    key = paths.backup_key()
    assert key and len(key) == 32 and paths.backup_key() == key


def test_a_broken_key_file_is_never_rewritten(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ENV, str(tmp_path))
    _write(str(tmp_path / paths.KEY_FILE), b"short")
    assert paths.backup_key() is None
    assert _read(str(tmp_path / paths.KEY_FILE)) == b"short"


def test_without_a_user_location_there_is_none_never_the_program_folder(monkeypatch):
    monkeypatch.delenv(paths.ENV, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(paths, "_qt_location", lambda: "")
    assert paths.user_data_dir() is None and paths.ensure() is None
    monkeypatch.setenv("LOCALAPPDATA", os.path.join(os.sep, "users", "x", "AppData", "Local"))
    assert paths.user_data_dir() == os.path.join(os.sep, "users", "x", "AppData", "Local", "FogScout")


def test_an_unwritable_data_folder_reports_none(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    _write(str(blocker))
    monkeypatch.setenv(paths.ENV, str(blocker / "below-a-file"))
    assert paths.ensure() is None and paths.writer_id() is None


def test_the_one_replacing_write_is_whole_or_nothing(tmp_path, monkeypatch):
    """1.34.2 (review W8): the settings backup and a format-1 project were written to "<name>.tmp" without fsync, and
    a value json could not write left that .tmp behind – now one write_atomic: fsync'ed temp file, one replace."""
    from fogscout import config, project
    target = tmp_path / "f.json"
    fsops.write_atomic(str(target), b"one")
    fsops.write_atomic(str(target), b"two")
    assert target.read_bytes() == b"two" and os.listdir(tmp_path) == ["f.json"]

    def broken(src, dst):
        raise PermissionError(13, "locked")
    monkeypatch.setattr(fsops.os, "replace", broken)
    with pytest.raises(PermissionError):
        fsops.write_atomic(str(target), b"three")
    assert target.read_bytes() == b"two" and os.listdir(tmp_path) == ["f.json"]   # old file kept, no temp left
    monkeypatch.undo()
    proj = tmp_path / "Projekte" / "a.fogscout-project.json"
    assert project.save(str(proj), {"v": 1}) and json.loads(proj.read_text(encoding="utf-8")) == {"v": 1}
    assert not project.save(str(proj), {"v": object()})                  # not writable as json: nothing left over
    assert os.listdir(proj.parent) == [proj.name] and json.loads(proj.read_text(encoding="utf-8")) == {"v": 1}
    backup = tmp_path / "backup.json"
    config.export_settings({"ui_language": "de", "rec_password": "secret"}, str(backup))
    assert json.loads(backup.read_text(encoding="utf-8")) == {"ui_language": "de"}
    assert sorted(os.listdir(tmp_path)) == ["Projekte", "backup.json", "f.json"]


# ---- 1.38.5: the program's data files go through write_atomic; every other replace is a reviewed place
REPLACE_PLACES = {               # (module, function): why it may rename/replace without write_atomic
    ("fsops", "_replace_into"): "the one replacing write (write_atomic, write_atomic_stream)",
    ("fsops", "create_exclusive"): "never over an existing name (project saving)",
    ("fsops", "rename_fallback"): "never over an existing name (project saving)",
    ("clipedit", "_publish"): "a finished ffmpeg output gets its name",
    ("obsrec", "_join"): "the joined recording (ffmpeg output) takes the round's name",
    ("obsrec", "_move"): "a recording moved into its folder",
    ("recindex", "settle_parts"): "a whole clip left as .tmp by a quit gets its name",
    ("recindex", "adopt_old_file"): "an index of the old program name taken over once",
    ("diagnose", "keep_crash"): "the crash file of the last run kept",
    ("__main__", "_keep_old_logs"): "the last sessions' logs move on by fixed names (1.57.60; never through a link)",
    ("rename", "migrate"): "files of the old program name taken over once",
    ("restart", "staged_setup"): "the checked setup copy under its final name",
    ("relupdate", "download"): "a whole, checked download gets its name",
    ("icon", "ensure_ico"): "cache – rebuilt when lost, no fsync wanted",
    ("thumbs", "thumbnail"): "cache – rebuilt when lost, no fsync per tile",
    ("mapstyle", "styled_path"): "cache – rebuilt when lost",
    ("imageedit", "save"): "a copy the user saves; own temp name and cleanup",
    ("obsoverlay", "_write"): "rewritten many times a round; no fsync per picture",
}


def test_every_rename_or_replace_is_a_reviewed_place():
    """1.38.5: config, history, official, the recordings/clips index and the backups wrote their own tmp + replace;
    now write_atomic. A new os.replace/os.rename anywhere needs a line in REPLACE_PLACES."""
    found = set()
    folder = os.path.join(ROOT, "fogscout")
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(folder, name), encoding="utf-8").read())

        def visit(node, func, mod=name[:-3]):
            for child in ast.iter_child_nodes(node):
                f = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) \
                        and isinstance(child.func.value, ast.Name) \
                        and f"{child.func.value.id}.{child.func.attr}" in ("os.replace", "os.rename"):
                    found.add((mod, f))
                visit(child, f)
        visit(tree, "<module>")
    assert found - set(REPLACE_PLACES) == set()
    assert set(REPLACE_PLACES) - found == set(), "a reviewed place is gone – drop its line"


def test_write_atomic_sweeps_only_its_own_stale_temp_files(tmp_path, monkeypatch):
    """1.38.5: the random temp names are not overwritten by the next save – a hard stop between write and replace
    would leave one for good. The first write of a path sweeps those older than STALE_TMP_S; fresh ones (another
    save may be writing) and every other name stay."""
    target = tmp_path / "rounds.jsonl"
    old = tmp_path / ".rounds.jsonl.4242.deadbeef.tmp"
    fresh = tmp_path / ".rounds.jsonl.4243.cafebabe.tmp"
    others = [tmp_path / n for n in (".settings.json.4242.deadbeef.tmp", "rounds.jsonl.tmp",
                                     ".rounds.jsonl.x.deadbeef.tmp", "rounds.jsonl")]
    for p in [old, fresh, *others]:
        p.write_bytes(b"x")
    past = os.stat(old).st_mtime - fsops.STALE_TMP_S - 60
    os.utime(old, (past, past))
    monkeypatch.setattr(fsops, "_SWEPT", set())
    fsops.write_atomic(str(target), b"new\n")
    assert not old.exists() and fresh.exists() and all(p.exists() for p in others[:3])
    assert target.read_bytes() == b"new\n"
    assert {n for n in os.listdir(tmp_path) if n.startswith(".rounds.jsonl.")} == {fresh.name,
                                                                                   ".rounds.jsonl.x.deadbeef.tmp"}
    os.utime(fresh, (past, past))
    fsops.write_atomic(str(target), b"again\n")              # once per path and process: no second sweep
    assert fresh.exists()


def test_the_data_files_go_through_write_atomic(tmp_path, monkeypatch):
    from fogscout import backups, config, history, obsrec, official
    written = []
    real = fsops.write_atomic
    monkeypatch.setattr(fsops, "write_atomic", lambda p, d: (written.append(os.path.basename(p)), real(p, d)))
    s = config.Settings(str(tmp_path / "settings.json"))
    s.set("ui_zoom", 1.25)
    s.save()
    r = history.Round(t=1000.0, seconds=300.0, map_id="coal-tower", map="Coal Tower")
    history._rewrite(str(tmp_path / "rounds.jsonl"), [r], [])
    official._write(str(tmp_path / "official.jsonl"), [], [(1.0, 2.0)])
    obsrec.save_index(str(tmp_path), [])
    obsrec.save_clips(str(tmp_path), [])
    backups.snapshot(str(tmp_path))
    assert written[:5] == ["settings.json", "rounds.jsonl", "official.jsonl", obsrec.INDEX, obsrec.CLIPS_INDEX]
    assert {n for n in written[5:] if n.startswith("rounds-")} and {n for n in written[5:] if n.startswith("official-")}
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["ui_zoom"] == 1.25
    assert [x.map_id for x in history.load(str(tmp_path / "rounds.jsonl"))] == ["coal-tower"]
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


def test_a_failed_settings_save_leaves_no_temp_file_and_says_it_once(tmp_path, monkeypatch, caplog):
    import logging
    from fogscout import config
    s = config.Settings(str(tmp_path / "settings.json"))
    real = os.replace
    monkeypatch.setattr(fsops.os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError(13, "gesperrt")))
    with caplog.at_level(logging.WARNING):
        s.save()
        s.save()
    monkeypatch.setattr(fsops.os, "replace", real)
    assert len([r for r in caplog.records if "Einstellungen nicht gespeichert" in r.getMessage()]) == 1
    assert os.listdir(tmp_path) == []
    s.save()
    assert os.listdir(tmp_path) == ["settings.json"]


def test_a_rewritten_history_is_read_whole_again(tmp_path):
    """The cache reads only lines added since the last read; a rewrite (now "\\n" where the text mode wrote "\\r\\n"
    on Windows) makes the file different from the bytes it remembers – it parses from the start."""
    import dataclasses
    from fogscout import history
    path = str(tmp_path / "rounds.jsonl")
    rounds = [history.Round(t=1000.0 + i, seconds=300.0, map_id=f"m{i}", map=f"M{i}") for i in range(3)]
    with open(path, "wb") as fh:                              # as Windows text mode wrote it
        for r in rounds:
            fh.write(json.dumps(dataclasses.asdict(r)).encode() + b"\r\n")
    assert [r.map_id for r in history.load(path)] == ["m0", "m1", "m2"]
    history._rewrite(path, rounds[1:], [])
    assert [r.map_id for r in history.load(path)] == ["m1", "m2"]
    assert b"\r" not in open(path, "rb").read()


def test_a_temp_file_of_the_clips_index_is_never_taken_for_a_clip(tmp_path):
    """Pflichtprüfung 1.38.5: the index's temp file sits in Clips/ and ends in .tmp like a clip the editor writes."""
    from fogscout import obsrec
    cdir = obsrec.clips_dir(str(tmp_path))
    os.makedirs(cdir)
    tmp = os.path.join(cdir, f".{obsrec.CLIPS_INDEX}.4242.deadbeef.tmp")
    with open(tmp, "wb") as fh:
        fh.write(b'{"file": "x.mp4"}\n')
    old = os.stat(tmp).st_mtime - 10 * 3600
    os.utime(tmp, (old, old))
    assert obsrec.list_clips(cdir, []) == []
    assert obsrec.settle_parts(str(tmp_path), now=old + 20 * 3600) == []
    assert os.path.exists(tmp)


def test_write_atomic_waits_for_a_reader_that_blocks_the_replace(tmp_path, monkeypatch):
    """1.38.24 (review STAB-3): on Windows os.replace fails with a PermissionError while another handle has the
    target open without FILE_SHARE_DELETE (our own reader thread, a virus scanner, OneDrive) – the write was lost.
    A few short retries; when they run out the error still comes and no temp file stays."""
    p = tmp_path / "rounds.jsonl"
    p.write_bytes(b"old\n")
    real = os.replace
    fails = {"n": 2}

    def flaky(src, dst):
        if fails["n"]:
            fails["n"] -= 1
            raise PermissionError(13, "Der Prozess kann nicht auf die Datei zugreifen")
        return real(src, dst)
    monkeypatch.setattr(fsops.os, "replace", flaky)
    monkeypatch.setattr(fsops, "REPLACE_WAIT_S", 0.001)
    fsops.write_atomic(str(p), b"new\n")
    assert p.read_bytes() == b"new\n" and fails["n"] == 0 and os.listdir(tmp_path) == ["rounds.jsonl"]
    fails["n"] = 99
    with pytest.raises(PermissionError):
        fsops.write_atomic(str(p), b"newer\n")
    assert p.read_bytes() == b"new\n" and os.listdir(tmp_path) == ["rounds.jsonl"]


def test_the_style_sheet_pictures_go_to_a_folder_of_this_process_alone():
    """CR-007: not the fixed %TEMP%/fogscout-ui another program could make first or swap for a junction."""
    import tempfile
    from fogscout import qt_theme
    path = qt_theme.ui_icon("check", "#123456")
    assert path and os.path.isfile(path)
    folder = os.path.dirname(path)
    assert os.path.basename(folder).startswith("fogscout-ui-") and folder != os.path.join(tempfile.gettempdir(),
                                                                                         "fogscout-ui")
    if os.name != "nt":
        assert os.stat(folder).st_mode & 0o077 == 0                       # only the user may enter
    assert qt_theme._qss_url('C:\\a"b') == 'C:/a\\"b'


@pytest.mark.skipif(not WIN, reason="Windows handles")
def test_a_file_system_without_attribute_tags_still_deletes_inside(tmp_path, monkeypatch):
    """1.57.58 (the user's recordings on an exFAT SSD): GetFileInformationByHandleEx(FileAttributeTagInfo) fails there
    with ERROR_INVALID_PARAMETER – every delete_inside failed and the farming recordings stayed for weeks. The same
    attributes come from GetFileInformationByHandle; a link is still refused."""
    real = fsops._k32_more()

    class NoTagInfo:                                # exFAT: the call fails, the error is "invalid parameter"
        def __getattr__(self, name):
            return getattr(real, name)

        @staticmethod
        def GetFileInformationByHandleEx(*a):
            return 0
    monkeypatch.setattr(fsops, "_k32_more", lambda: NoTagInfo())
    monkeypatch.setattr(fsops.ctypes, "get_last_error", lambda: fsops.ERROR_INVALID_PARAMETER)
    f = tmp_path / "round.mp4"
    f.write_bytes(b"video")
    fsops.delete_inside(str(tmp_path), str(f))
    assert not f.exists()
    d = tmp_path / "sub"
    d.mkdir()
    with pytest.raises(OSError):                    # a directory is still never deleted (it is not even opened)
        fsops.delete_inside(str(tmp_path), str(d))
    assert d.is_dir()
    monkeypatch.setattr(fsops.ctypes, "get_last_error", lambda: 5)          # any other error: raised as before
    g = tmp_path / "other.mp4"
    g.write_bytes(b"x")
    with pytest.raises(OSError):
        fsops.delete_inside(str(tmp_path), str(g))
    assert g.exists()


def test_a_cache_folder_behind_a_link_is_never_written_by_any_cache(tmp_path):
    """Code review 1.57.68 (CR-4): the caches below the data folder were only pruned with a link check – thumbnails,
    styled maps, the OBS overlay picture, the corpus and the analysis cache were still written through a folder a
    program of the user had swapped for a junction, with the administrator rights of the program."""
    import numpy as np
    import pytest
    from PIL import Image
    from fogscout import clipedit, corpus, fsops, mapstyle, obsoverlay, thumbs
    plain = tmp_path / "plain" / "cache" / "thumbs"
    assert fsops.plain_dir(str(plain), 2) and plain.is_dir()
    outside = tmp_path / "outside"
    outside.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    try:
        os.symlink(str(outside), str(data / "cache"), target_is_directory=True)
        os.symlink(str(outside), str(data / "corpus"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    cache = str(data / "cache")
    assert not fsops.plain_dir(os.path.join(cache, "thumbs"), 2) and not fsops.plain_dir(cache, 1)
    src = tmp_path / "map.png"
    Image.new("RGBA", (300, 200), (200, 200, 200, 255)).save(src)
    assert thumbs.thumbnail(str(src), (64, 64), cache_dir=os.path.join(cache, "thumbs")) is not None    # still a picture
    assert mapstyle.styled_path(str(src), os.path.join(cache, "maps_dark")) == str(src)                # the original
    import types
    with pytest.raises(OSError):
        obsoverlay.Writer._write(types.SimpleNamespace(file=os.path.join(cache, "obs-overlay.png")), [], (0, 0))
    clipedit._analysis_write(os.path.join(cache, "analysis"), os.path.join(cache, "analysis", "x.json"), {"a": 1})
    assert corpus.save(str(data), np.zeros((40, 200, 3), np.uint8), None, None, "x", (200, 40), False, None,
                       ("en",), "1") is None
    assert os.listdir(outside) == []                                     # nothing arrived behind the links
