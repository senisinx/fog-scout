"""1.8.66 (user: "das Programm crasht ab und zu, wenn ich Videos öffne"): a hard crash left nothing in the log.
faulthandler writes the thread stacks to a file; a normal end removes it, the next start keeps a crash's file and
"Diagnose kopieren" shows it."""
import os
import subprocess
import sys

import pytest

from fogscout import diagnose

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(code, tmp_path):
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, "-c", code, str(tmp_path)], env=env, timeout=60,
                          capture_output=True, text=True)


def test_a_hard_crash_is_kept_for_the_diagnosis_and_a_normal_end_leaves_nothing(tmp_path):
    crash, last = tmp_path / diagnose.CRASH_FILE, tmp_path / diagnose.CRASH_LAST
    assert diagnose.crash_lines(str(tmp_path)) == ["Letzter harter Absturz: keiner aufgezeichnet"]
    r = _run("import sys, faulthandler, threading\n"
             "from fogscout import __main__ as m\n"
             "m._enable_crash_log(sys.argv[1])\n"
             "threading.Thread(target=lambda: __import__('time').sleep(30), name='clip-player', daemon=True).start()\n"
             "faulthandler._sigsegv()\n", tmp_path)
    assert r.returncode != 0 and crash.stat().st_size > 0                  # the process died, the stacks are there
    r = _run("import sys\nfrom fogscout import __main__ as m\n"
             "m._enable_crash_log(sys.argv[1])\nm._crash_log_clear(sys.argv[1])\n", tmp_path)
    assert r.returncode == 0, r.stderr
    assert not crash.exists() and last.stat().st_size > 0                  # kept at the start, a normal end after
    lines = diagnose.crash_lines(str(tmp_path))
    assert lines[0].startswith("Letzter harter Absturz (") and diagnose.CRASH_LAST in lines[0]
    text = "\n".join(lines)
    assert "Fatal Python error" in text and len(lines) <= diagnose.CRASH_LINES + 2
    diagnose.keep_crash(str(tmp_path))                                    # nothing new: the kept one stays
    assert last.stat().st_size > 0


def test_a_thread_that_dies_of_an_exception_is_logged(caplog):
    """1.16.1 (audit): Python's default sends a thread's traceback to sys.stderr – None under pythonw.exe, so a
    dead recorder or player thread left no trace. The hook logs it with the thread's name."""
    import logging
    import threading
    from fogscout import __main__ as m
    old = threading.excepthook
    try:
        m._log_thread_deaths()
        assert threading.excepthook is not old

        def boom():
            raise RuntimeError("Platte voll")
        with caplog.at_level(logging.ERROR, logger="fogscout"):
            t = threading.Thread(target=boom, name="obs-recorder")
            t.start()
            t.join(5)
        assert any("obs-recorder" in r.getMessage() and r.exc_info and "Platte voll" in str(r.exc_info[1])
                   for r in caplog.records)
    finally:
        threading.excepthook = old


def _raise(exc):
    try:
        raise exc
    except BaseException:
        return sys.exc_info()


def test_an_uncaught_error_is_logged_once_a_minute_with_how_often_it_came(caplog, monkeypatch):
    """1.38.4: an exception in a Qt handler goes to sys.excepthook – by default to sys.stderr, None under pythonw.exe
    and in the .exe. Into the log instead; the same error (type + place) once per minute, then with its count."""
    import logging
    from fogscout import __main__ as m
    now = [1000.0]
    passed = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: passed.append(a[0]))
    m._log_uncaught(clock=lambda: now[0])
    hook = sys.excepthook
    with caplog.at_level(logging.ERROR, logger="fogscout"):
        info = _raise(ValueError("Klick"))
        hook(*info)
        hook(*info)                                      # same place, same second: counted, not logged
        hook(*info)
        hook(*_raise(KeyError("anderer Fehler")))        # another place: logged at once
        now[0] += m.UNCAUGHT_GAP_S + 1
        hook(*info)
    lines = [r.getMessage() for r in caplog.records if r.name == "fogscout"]
    assert lines[0] == "Unerwarteter Fehler" and caplog.records[0].exc_info[0] is ValueError
    assert lines[1] == "Unerwarteter Fehler" and caplog.records[1].exc_info[0] is KeyError
    assert len(lines) == 3 and lines[2].startswith("Unerwarteter Fehler (2× seit ") and lines[2].endswith(")")
    hook(*_raise(KeyboardInterrupt()))                   # Ctrl+C: the old hook, as before
    assert passed == [KeyboardInterrupt]


def test_an_error_in_a_qt_click_handler_reaches_the_log(caplog, monkeypatch):
    """The reason for the hook: PySide6 reports an exception in a slot through sys.excepthook (checked, 6.11.2)."""
    import logging
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QPushButton
    from fogscout import __main__ as m, qt_window
    qt_window.application()
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)          # restored after the test
    m._log_uncaught()
    b = QPushButton("x")

    def broken():
        raise RuntimeError("Handler kaputt")
    b.clicked.connect(broken)
    with caplog.at_level(logging.ERROR, logger="fogscout"):
        b.click()
    assert any(r.getMessage() == "Unerwarteter Fehler" and r.exc_info and "Handler kaputt" in str(r.exc_info[1])
               for r in caplog.records)


def test_a_closed_dialog_is_deleted(monkeypatch):
    """1.38.4: close_dialog only closed – every dialog stayed a child of the main window until Fog Scout quit."""
    import types
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QDialog
    from fogscout import qt_window
    qt_window.application()
    dlg = QDialog()
    dlg.show()
    owner = types.SimpleNamespace(dialogs={"assign": dlg})
    qt_window.MainWindow.close_dialog(owner, "assign")
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert owner.dialogs == {} and dlg.closing_from_app and not shiboken6.isValid(dlg)


def test_the_logs_of_the_last_sessions_are_kept(tmp_path):
    """1.57.60: the log was opened with "w" – after a restart nothing of the session before was left. Now the last
    LOG_KEPT logs move on (.1 newest) and the oldest goes; only renames."""
    from fogscout import __main__ as main
    log = tmp_path / "fogscout.log"
    for i in range(5):
        log.write_text(f"Sitzung {i}", encoding="utf-8")
        main._keep_old_logs(str(tmp_path))
    assert not log.exists()
    kept = {n: (tmp_path / n).read_text(encoding="utf-8") for n in ("fogscout.log.1", "fogscout.log.2", "fogscout.log.3")}
    assert kept == {"fogscout.log.1": "Sitzung 4", "fogscout.log.2": "Sitzung 3", "fogscout.log.3": "Sitzung 2"}
    assert not (tmp_path / "fogscout.log.4").exists()
    main._keep_old_logs(str(tmp_path / "missing"))                  # nothing there: nothing happens, no error


def test_a_linked_log_name_moves_nothing(tmp_path):
    import os
    import pytest
    from fogscout import __main__ as main
    (tmp_path / "fogscout.log").write_text("jetzt", encoding="utf-8")
    target = tmp_path / "elsewhere.txt"
    target.write_text("fremd", encoding="utf-8")
    try:
        os.symlink(str(target), str(tmp_path / "fogscout.log.2"))
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    main._keep_old_logs(str(tmp_path))
    assert (tmp_path / "fogscout.log").read_text(encoding="utf-8") == "jetzt" and target.read_text(encoding="utf-8") == "fremd"


def test_the_log_and_the_crash_file_are_never_opened_through_a_link(tmp_path, dir_link):
    """1.57.69 (deep review SEC-04, reproduced): logging.basicConfig(filename=…, filemode="w") opened fogscout.log even
    when the name was a link – the elevated program cut and overwrote its target at every start. Now a link at the
    log's or the crash file's name is not followed: no log file this session, the start goes on."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    dir_link(target, data / "fogscout.log")
    dir_link(target, data / diagnose.CRASH_FILE)
    r = _run("import sys, logging\nfrom fogscout import __main__ as m\n"
             "m._setup_logging(sys.argv[1] + '/data')\nlogging.getLogger('fogscout').info('probe')\n"
             "m._crash_log_clear(sys.argv[1] + '/data')\nprint('started')\n", tmp_path)
    assert r.returncode == 0 and "started" in r.stdout, r.stderr
    assert list(target.iterdir()) == []


def test_the_log_is_written_to_a_plain_file_and_never_to_a_second_hard_link(tmp_path):
    """1.57.69 (SEC-04): the log file of the data folder opens fresh; a file of that name with a second hard link
    (that could be any file of the user) is not written."""
    from fogscout import fsops
    data = tmp_path / "data"
    data.mkdir()
    r = _run("import sys, logging\nfrom fogscout import __main__ as m\n"
             "m._setup_logging(sys.argv[1] + '/data')\nlogging.getLogger('fogscout').info('Probe-Zeile')\n"
             "logging.shutdown()\n", tmp_path)
    assert r.returncode == 0, r.stderr
    assert "Probe-Zeile" in (data / "fogscout.log").read_text(encoding="utf-8")
    victim = tmp_path / "victim.txt"
    victim.write_text("bleibt", encoding="utf-8")
    os.link(str(victim), str(tmp_path / "hard.log"))
    with pytest.raises(fsops.NotInside):
        fsops.open_own_for_write(str(tmp_path / "hard.log"))
    assert victim.read_text(encoding="utf-8") == "bleibt"


def test_the_diagnosis_shows_the_warnings_of_the_session_before(tmp_path, monkeypatch):
    """1.57.60: "Diagnose kopieren" after a restart – the last warnings/errors of fogscout.log.1, masked."""
    home = os.path.expanduser("~")
    lines = ["2026-11-25 10:00:00,000 INFO alles gut"]
    lines += [f"2026-11-25 10:00:{i:02d},000 WARNING Platz schaffen: 1 Datei(en) nicht gelöscht, z. B. "
              + os.path.join(home, f"x{i}.mp4") + " – Fehler 87" for i in range(20)]
    (tmp_path / "fogscout.log.1").write_text("\n".join(lines) + "\n", encoding="utf-8")
    lines = diagnose.previous_log_lines(str(tmp_path))
    assert lines[0].startswith("Vorige Sitzung (fogscout.log.1), letzte 12 von 20")
    assert len(lines) == 13 and "x19.mp4" in lines[-1] and "alles gut" not in " ".join(lines)
    assert home not in " ".join(lines)                                 # the account name never in the diagnosis
    assert diagnose.previous_log_lines(str(tmp_path / "nichts")) == ["Vorige Sitzung: kein Log"]
