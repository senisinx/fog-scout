"""MEASUREMENT ONLY, TEMPORARY (removed before the merge): a pytest plugin for the one question why a label in a
window with the light sheet once had the dark theme's colour on Windows.

Qt keeps each parsed style sheet under the address of the widget that carries it. This plugin sees every sheet the
program sets (``QWidget.setStyleSheet`` is wrapped) and gives every widget with a whole theme sheet a rule of its
own: a colour no other widget has (the program reads its sheets back without it). Whenever a widget gets its first
theme sheet, a label below it is looked at once: if it has another widget's colour, Qt styled it with a sheet that
is not this widget's – the fault, seen where it happens, also where the two sheets are the same theme.

    PYTHONPATH=tests python -m pytest -q -p staleprobe tests

STALEPROBE_UNFIXED=1 takes the remedy away again (qt_app.set_sheet only sets the sheet, as before 1.54.2), so
the same suite runs with and without it; the three tests of the remedy fail then.
"""
import json
import os
import re
import sys

import pytest

UNFIXED = os.environ.get("STALEPROBE_UNFIXED") == "1"
if UNFIXED:                                            # before any module takes the name from qt_app
    from fogscout import qt_app
    qt_app.set_sheet = lambda w, qss: w.setStyleSheet(qss)

DIM = re.compile(r'QLabel\[class="dim"\] \{ color: (#[0-9a-fA-F]{6});')
TAG = re.compile(r'\n/\*staleprobe\*/ QLabel\[class="staleprobe"\] \{ color: (#[0-9a-f]{6}); \}')
state = {"test": "", "live": {}, "owner": {}, "next": 1, "busy": False, "wrong": [],
         "n": {"first theme sheets": 0, "at the address of a dead widget with a theme sheet": 0,
               "styled with another widget's sheet": 0, "… of a dead widget": 0,
               "… where both sheets were the same theme": 0, "times Qt dropped all its caches": 0}}


def _install():
    import shiboken6
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QLabel, QWidget
    real, real_get = QWidget.setStyleSheet, QWidget.styleSheet
    n = state["n"]
    dead = {}                                          # address -> colour of the widget that died there

    def addr(w):
        return shiboken6.getCppPointer(w)[0]

    def died(a):
        colour = state["live"].pop(a, None)
        if colour is not None:
            state["owner"][colour]["dead in"] = state["test"]
            dead[a] = colour
        if not state["live"]:                          # no widget with a sheet is left: Qt deletes its caches
            if dead:
                n["times Qt dropped all its caches"] += 1
            dead.clear()

    def look(w):
        label = QLabel(w)
        label.setProperty("class", "staleprobe")
        label.ensurePolished()
        got = label.palette().color(QPalette.WindowText).name()
        shiboken6.delete(label)
        return got

    def style_sheet(self):
        return TAG.sub("", real_get(self))

    def set_style_sheet(self, qss):
        theme = DIM.search(qss or "")
        if state["busy"] or not theme:
            real(self, qss)
            return
        a = addr(self)
        first = not real_get(self)
        colour = state["live"].get(a)
        if colour is None:
            colour = "#%06x" % state["next"]
            state["next"] += 1
            state["live"][a] = colour
            state["owner"][colour] = {"widget": f"{type(self).__name__}#{QWidget.objectName(self)}",
                                      "made in": state["test"], "theme": theme.group(1)}
            self.destroyed.connect(lambda _o=None, a=a: died(a))
        else:
            state["owner"][colour]["theme"] = theme.group(1)
        real(self, qss + f'\n/*staleprobe*/ QLabel[class="staleprobe"] {{ color: {colour}; }}')
        if not first:
            return
        n["first theme sheets"] += 1
        before = dead.pop(a, None)
        n["at the address of a dead widget with a theme sheet"] += before is not None
        state["busy"] = True
        try:
            got = look(self)
        finally:
            state["busy"] = False
        if got != colour:
            other = state["owner"].get(got)
            n["styled with another widget's sheet"] += 1
            n["… of a dead widget"] += bool(other and "dead in" in other)
            n["… where both sheets were the same theme"] += bool(other and other["theme"] == theme.group(1))
            state["wrong"].append({"test": state["test"], "widget": state["owner"][colour]["widget"],
                                   "its sheet says dim": theme.group(1), "the sheet Qt used was of": other,
                                   "a widget with a theme sheet died at this address": before is not None})

    QWidget.setStyleSheet = set_style_sheet
    QWidget.styleSheet = style_sheet


@pytest.fixture(autouse=True)
def _stale_probe(request):
    if "installed" not in state and "PySide6.QtWidgets" in sys.modules:
        state["installed"] = True
        _install()
    state["test"] = request.node.nodeid
    yield


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line("STALEPROBE " + ("without" if UNFIXED else "with") + " the remedy "
                                + json.dumps(state["n"], ensure_ascii=True))
    for w in state["wrong"]:
        terminalreporter.write_line("STALEPROBE-WRONG " + json.dumps(w, ensure_ascii=True))
