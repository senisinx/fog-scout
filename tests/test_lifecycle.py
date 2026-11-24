"""CR-013 (code review): the overlay's 1-s timer ends with it, the YouTube link stays out of the log, and resetting
or importing the settings waits for a round, a recording, a clip and the editors' projects like an update does."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fogscout import app_settings, app_youtube  # noqa: E402
from fogscout.overlay_win32 import PictureOverlay  # noqa: E402


class _Root:
    def __init__(self):
        self.jobs, self.cancelled = [], []

    def after(self, ms, fn):
        self.jobs.append(fn)
        return len(self.jobs)

    def after_cancel(self, job):
        self.cancelled.append(job)


def test_a_destroyed_overlay_stops_its_keep_on_top_timer():
    o = PictureOverlay.__new__(PictureOverlay)
    o.root, o._shown = _Root(), False
    o._stop_anim = lambda: None
    o._destroy_window = lambda: None
    o._keep_on_top()
    assert len(o.root.jobs) == 1
    o.destroy()
    assert o.root.cancelled == [1]
    o._keep_on_top()                                     # a tick already queued: nothing new is planned
    assert len(o.root.jobs) == 1


def test_a_copied_youtube_link_is_not_written_to_the_log():
    logged, board = [], []
    s = SimpleNamespace(root=SimpleNamespace(clipboard_set=board.append),
                        _log=lambda text, cat: logged.append(text))
    app_youtube.YouTubeUpload._yt_copy_link(s, "abcDEF12345")
    assert board and "abcDEF12345" in board[0]
    assert logged and all("abcDEF12345" not in t and "youtu" not in t for t in logged)


def _settings_app(blocked="", secured=True):
    saved, told, waiting = [], [], []
    settings = SimpleNamespace(data={"x": 1}, save=lambda: saved.append(1), frozen=False)
    s = SimpleNamespace(settings=settings, _update_blocked=lambda: blocked,
                        _inform=lambda title, text: told.append(text),
                        _quit_phase1=lambda then: secured or waiting.append(then) and False,
                        _log=lambda *a: None, _no_bar_defaults=lambda d: None, root_dir="/nowhere", quit=lambda: None)
    s._restart_blocked = lambda title: app_settings.SettingsTab._restart_blocked(s, title)
    return s, saved, told, waiting


def test_resetting_or_importing_waits_for_a_round_and_for_the_editors(monkeypatch):
    from fogscout import restart
    monkeypatch.setattr(restart, "spawn_helper", lambda root: False)
    s, saved, told, _w = _settings_app(blocked="eine Runde läuft")
    app_settings.SettingsTab._reset_all_settings_go(s)
    app_settings.SettingsTab._import_settings_go(s, "x.json", {"y": 2})
    assert saved == [] and s.settings.data == {"x": 1} and len(told) == 2          # nothing written, told why
    s, saved, told, waiting = _settings_app(secured=False)
    app_settings.SettingsTab._import_settings_go(s, "x.json", {"y": 2})
    assert saved == [] and len(waiting) == 1                                        # the editors' projects first
    s, saved, told, _w = _settings_app()
    app_settings.SettingsTab._import_settings_go(s, "x.json", {"y": 2})
    assert saved == [1] and s.settings.data == {"y": 2}


def test_a_new_spotify_client_id_clears_the_stored_sign_in():
    """CR-016 (code review): the settings kept the old app's refresh token and handed it to the new id."""
    from fogscout import app_spotify

    class Settings(dict):
        def set(self, k, v):
            self[k] = v
    settings = Settings(spotify_client_id="a" * 32, spotify_token="old")
    sent = []
    s = SimpleNamespace(settings=settings, _save_soon=lambda: None,
                        sp_on_var=SimpleNamespace(get=lambda: True), sp_id_var=SimpleNamespace(get=lambda: "b" * 32),
                        spotify=SimpleNamespace(configure=lambda on, cid, tok: sent.append(tok)))
    app_spotify.SpotifyUpNext._spotify_setting(s)
    assert settings["spotify_token"] == "" and sent == [""]
    app_spotify.SpotifyUpNext._spotify_setting(s)                     # the same id again: nothing dropped
    assert sent == ["", ""]


def test_a_typed_file_name_is_a_windows_file_name():
    """CR-018 (code review): control characters, dots/spaces at the end and device names in the image editor's name."""
    from fogscout.imageedit import file_stem
    assert file_stem("a\x00b\x1fc") == "abc" and file_stem("name. . ") == "name" and file_stem("ok:na?me") == "okname"
    assert file_stem("CON") == "_CON" and file_stem("nul.txt") == "_nul.txt" and file_stem("COM1 ") == "_COM1"
    assert file_stem("Concert") == "Concert" and file_stem("...") == ""


def test_a_broken_accent_colour_is_gold():
    from fogscout import skin
    assert skin.accent_rgba("#zzzzzz") == skin.GOLD and skin.accent_rgba("#102030") == (16, 32, 48, 255)


def test_a_still_being_saved_stops_with_its_job():
    """CR-018: save_still ran ffmpeg outside its job – quitting could not stop it."""
    from fogscout import qt_clip
    job = qt_clip._SaveJob(None, "x.png")
    job.stop()
    assert job.run_out(["ffmpeg", "-version"]) is None                    # stopped: nothing started


def test_a_projects_broken_mix_level_is_clamped_or_skipped():
    """CR-018: "mix_vol" of a project file went through int() unguarded (a crash on "x") and unclamped."""
    from fogscout import obsrec, qt_editor
    src = list(obsrec.SOURCES)
    s = SimpleNamespace(_mix_on={}, _mix_vol={k: 100 for k in src}, _mix_fill=lambda: None)
    qt_editor.EditorWindow._apply_project_extra(s, {"mix_vol": {src[0]: "x", src[1]: 900, src[2]: -5}})
    assert s._mix_vol[src[0]] == 100 and s._mix_vol[src[1]] == qt_editor.MIX_MAX and s._mix_vol[src[2]] == 0
