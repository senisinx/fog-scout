"""start.bat's first setup (1.8.50): only a Python every pinned package has Windows wheels for."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_setup_asks_the_launcher_for_a_supported_python_newest_first():
    # the user had only Python 3.15: "py -3" took it and pip found no onnxruntime for it
    s = _read("start.bat")
    assert "py -3\"" not in s and "where python" not in s
    tried = re.search(r"for %%V in \(([\d. ]+)\) do if not defined PY \(py -%%V -I -c \"pass\" <nul", s)
    assert tried and tried.group(1).split() == ["3.14", "3.13", "3.12"]
    # python on PATH only within the same range
    assert "sys.exit(not (3, 12) <= sys.version_info[:2] <= (3, 14))" in s
    # a half-finished .venv (other Python) is rebuilt instead of reused
    assert s.index('rd /s /q "%VENV%"') < s.index('%PY% -I -m venv "%VENV%"')


def test_readmes_name_the_same_python_range():
    assert "Python 3.12, 3.13 oder 3.14" in _read("start.bat")
    assert "3.12 bis 3.14" in _read("README.md")
    assert "3.12 to 3.14" in _read("README.en.md")


def test_the_program_and_the_updater_ignore_python_environment_variables():
    """1.38.21 (audit SEC-2): start.bat runs as administrator with the user's environment – PYTHONPATH/PYTHONHOME
    from HKCU\\Environment would make the elevated Python import the user's code. ``-E`` ignores PYTHON* (not -I:
    ``-m fogscout`` needs the program folder on sys.path)."""
    lines = [line for line in _read("start.bat").splitlines()
             if ("update.py" in line or "-m fogscout" in line) and not line.lstrip().lower().startswith("rem")]
    assert len(lines) == 4, lines
    assert all(re.search(r'python(w)?\.exe" -E ', line) for line in lines), lines


# a line that runs a Python: the venv's python(w).exe, the launcher "py", a "python" on PATH, or %PY% (one of those)
PYTHON_RUN = re.compile(r'(?:python(?:w)?\.exe"|(?<![\w%])py -%%V|(?<![\w\\%"])python(?= )|%PY%)\s+(\S+)')


def test_every_python_the_starters_run_ignores_python_environment_variables():
    """1.55.4 (audit SEC-2): start.bat and verknuepfung_erstellen.bat run as administrator – not only the program and
    the updater, every Python they start ignores PYTHONPATH/PYTHONHOME of the user: the launcher probe, the venv
    creation and the first pip installs (``-I``: pip needs no current folder), the task setup (``-E``: ``-m
    fogscout.autostart`` needs the program folder on sys.path)."""
    for name, count in (("start.bat", 9), ("verknuepfung_erstellen.bat", 1)):
        runs = []
        for line in _read(name).splitlines():
            if re.match(r"\s*(rem|echo)\b", line, re.I):                   # comments and texts
                continue
            line = re.sub(r'exist "[^"]*"', "", line)                       # a file check runs nothing
            runs += [(m.group(1), line) for m in PYTHON_RUN.finditer(line)]
        assert len(runs) == count, runs
        assert all(flag in ("-E", "-I") for flag, _line in runs), [r for r in runs if r[0] not in ("-E", "-I")]
    assert '-I -m pip install' in _read("start.bat") and " -m pip install" not in _read("start.bat").replace(
        "-I -m pip install", "")


def test_the_first_setup_installs_wheels_only():
    """1.12.3 (audit): start.bat runs as administrator – pip must never build a source package (its setup.py)."""
    pip_lines = [line for line in _read("start.bat").splitlines() if " -m pip install" in line]
    assert len(pip_lines) == 2 and all("--only-binary=:all:" in line for line in pip_lines)
