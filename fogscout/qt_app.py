"""The one QApplication of the process (1.14.2: out of qt_window, so the splash screen can make it before the heavy
modules – the pages, PIL, numpy, the OCR – are even imported; qt_window re-exports ``application``) and the one
place a widget gets a style sheet (``set_sheet``, 1.54.2)."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget

FIRA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "FiraSans-ExtraBold.ttf")   # = mapimage.FONT


def application() -> QApplication:
    """The one QApplication of the process (main thread, before any widget)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setQuitOnLastWindowClosed(False)          # closing goes through the App (quit / tray)
        QFontDatabase.addApplicationFont(FIRA)         # map names like on the map pictures
    return app


def set_sheet(w, qss: str):
    """Every style sheet of the program is set here, never with ``setStyleSheet`` (guard in tests/test_qt.py).

    1.54.2 (a theme test failed once on Windows: a label in a window with the light sheet had the dark theme's
    colour): Qt keeps every parsed sheet under the **address** of the widget that carries it and forgets it only
    when that very widget was polished (Qt 6.11.2, qstylesheetstyle.cpp: ``styleRules`` puts the sheets of all
    parents into ``styleSheetCache``, ``initWidget`` connects ``destroyed`` only for the widget whose rules are
    worked out). A widget that got a sheet, whose children worked out their rules (a size hint is enough) and that
    died without ever being shown left its sheet behind – and the next widget at that address was styled with it,
    whatever its own sheet said: colours of the other theme, sizes of another zoom.

    So before a widget gets its **first** sheet, Qt is made to track it and to drop what it holds under the
    address: two ``polish`` calls of a sheet style – the first connects ``destroyed`` and works out the rules, the
    second finds them and clears the widget's caches, the kept sheet with them (``QStyleSheetStyle::polish``).
    Only ``w`` is polished, none of its children (hidden pages stay cheap – ``_style_lazily``). A widget Qt does
    not style before it has a sheet of its own (a scroll area's viewport) is tracked after it has one; setting the
    sheet again lets Qt redo the children that were polished with the old one. A later sheet of the same widget
    needs none of this: Qt drops the old one itself."""
    if not qss or w.styleSheet():
        w.setStyleSheet(qss)
        return
    probe = QWidget()                              # any widget with a sheet: its style is Qt's sheet style
    probe.setStyleSheet("QWidget {}")
    style = probe.style()
    # WA_StyleSheet = "tracked" to Qt. A widget that lost its sheet unpolished keeps the mark although Qt may have
    # deleted its caches (and the connection) with the last sheet style – without the mark Qt connects again
    w.setAttribute(Qt.WA_StyleSheet, False)
    style.polish(w)
    style.polish(w)
    tracked = w.testAttribute(Qt.WA_StyleSheet)
    w.setStyleSheet(qss)                           # while the probe lives: Qt's caches live as long as a sheet style
    if not tracked:
        style = w.style()
        style.polish(w)
        style.polish(w)
        w.setStyleSheet(qss)
    del style                                      # the probe dies here (no parent: Python owns it)
