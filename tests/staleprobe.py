"""MEASUREMENT ONLY, TEMPORARY (removed before the merge): a pytest plugin for the one question why a label in a
window with the light sheet once had the dark theme's colour on Windows.

Qt keeps each parsed style sheet under the address of the widget that carries it. This plugin sees every sheet the
program sets (``QWidget.setStyleSheet`` is wrapped), remembers at which address a widget with a whole theme sheet
died, and – whenever a widget gets its first theme sheet – looks at once whether a label below it is drawn with
the colour that sheet says. A wrong colour at a dead widget's address is the fault, seen where it happens.

    PYTHONPATH=tests python -m pytest -q -p staleprobe tests
"""
import json
import re
import sys

import pytest

DIM = re.compile(r'QLabel\[class="dim"\] \{ color: (#[0-9a-fA-F]{6});')
state = {"test": "", "live": {}, "dead": {}, "busy": False, "wrong": [],
         "n": {"first theme sheets": 0, "at the address of a dead widget with a theme sheet": 0,
               "… whose sheet was another one": 0, "wrong colour": 0, "wrong colour at such an address": 0,
               "times Qt dropped all its caches": 0}}


def _install():
    import shiboken6
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QLabel, QWidget
    real = QWidget.setStyleSheet
    n = state["n"]

    def addr(w):
        return shiboken6.getCppPointer(w)[0]

    def died(a):
        sheet = state["live"].pop(a, None)
        if sheet is not None:
            state["dead"][a] = (sheet, state["test"])
        if not state["live"]:                      # no widget with a sheet is left: Qt deletes its caches
            if state["dead"]:
                n["times Qt dropped all its caches"] += 1
            state["dead"].clear()

    def look(w, want):
        label = QLabel(w)
        label.setProperty("class", "dim")
        label.ensurePolished()
        got = label.palette().color(QPalette.WindowText).name()
        shiboken6.delete(label)
        return got

    def set_style_sheet(self, qss):
        first = not QWidget.styleSheet(self)
        real(self, qss)
        if state["busy"]:
            return
        a = addr(self)
        theme = DIM.search(qss or "")
        if a in state["live"]:
            state["live"][a] = qss if theme else None
        elif qss:
            state["live"][a] = qss if theme else None
            self.destroyed.connect(lambda _o=None, a=a: died(a))
        if not (first and theme):
            return
        n["first theme sheets"] += 1
        before = state["dead"].pop(a, None)
        if before is not None:
            n["at the address of a dead widget with a theme sheet"] += 1
            n["… whose sheet was another one"] += before[0] != qss
        state["busy"] = True
        try:
            got = look(self, theme.group(1))
        finally:
            state["busy"] = False
        if got != theme.group(1):
            n["wrong colour"] += 1
            n["wrong colour at such an address"] += before is not None
            old = DIM.search(before[0]) if before else None
            state["wrong"].append({
                "test": state["test"], "widget": f"{type(self).__name__}#{QWidget.objectName(self)}",
                "the sheet says": theme.group(1), "the label got": got,
                "a widget with a theme sheet died at this address": before is not None,
                "its sheet said": old.group(1) if old else None, "it died in": before[1] if before else None})

    QWidget.setStyleSheet = set_style_sheet


@pytest.fixture(autouse=True)
def _stale_probe(request):
    if "installed" not in state and "PySide6.QtWidgets" in sys.modules:
        state["installed"] = True
        _install()
    state["test"] = request.node.nodeid
    yield


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line("STALEPROBE " + json.dumps(state["n"], ensure_ascii=False))
    for w in state["wrong"]:
        terminalreporter.write_line("STALEPROBE-WRONG " + json.dumps(w, ensure_ascii=False))
