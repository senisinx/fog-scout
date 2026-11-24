"""1.38.2: tools/screenshots.py draws every page offscreen – the pictures are how a GUI change is checked before and
after (not a timing, not a pixel comparison: only that each page, tab and setup step yields a file)."""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tool():
    spec = importlib.util.spec_from_file_location("screenshots", os.path.join(ROOT, "tools", "screenshots.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def app_root(tmp_path):
    if sys.platform == "win32":
        pytest.skip("Linux: the Windows job tests the native parts; the app would touch the system there")
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    for name in ("maps", "models", "maps.json"):
        os.symlink(os.path.join(ROOT, name), tmp_path / name)
    (tmp_path / "sim").mkdir()
    (tmp_path / "settings.json").write_text('{"welcome_seen": true}', encoding="utf-8")
    return tmp_path


def test_every_page_tab_and_setup_step_gives_a_picture(app_root):
    from fogscout.app import App
    from fogscout import qt_window
    tool = _tool()
    app = App(str(app_root), simulate=str(app_root / "sim"))
    app.qt.resize(1100, 760)
    out = app_root / "shots"
    try:
        files = tool.shoot(app, str(out), pages=["settings", "overlay", "log", "setup"])
    finally:
        app.quit()
    names = sorted(os.path.basename(f) for f in files)
    assert all(os.path.getsize(f) > 1000 for f in files)
    tabs = qt_window.SPECS["settings"][0][1]                       # ("tabs", ((key, title, items), …))
    assert len(tabs) == 6
    for _key, title, _items in tabs:
        assert any(n.startswith("settings-" + tool._name(title)[:-4]) for n in names), (title, names)
    assert "log.png" in names and "overlay-Karte.png" in names
    assert [n for n in names if n.startswith("setup-")] == [f"setup-{i}.png" for i in range(1, 9)]
    assert all(not n.startswith(("overview", "stats", "maps")) for n in names)        # only the pages asked for


def test_names_of_tabs_in_other_scripts_stay_apart():
    """1.55.7 (audit): `_name` dropped every non-Latin letter – the Russian/Chinese/Japanese/Korean tabs of one page
    all became "settings.png" and overwrote each other. Letters of any script stay; a repeat gets a number."""
    tool = _tool()
    names = {tool._name("settings", t) for t in ("Общие", "Распознавание", "常规", "識別", "일반", "Match-Daten")}
    assert len(names) == 6 and "settings-Match_Daten.png" in names
    assert tool._name("settings", "Erkennung", "full") == "settings-Erkennung-full.png"
    taken = set()
    assert [tool._unique(p, taken) for p in ("a/x.png", "a/x.png", "a/x.png")] == ["a/x.png", "a/x-2.png", "a/x-3.png"]


def test_every_control_has_an_accessible_name(app_root):
    """1.55.7 (a11y audit, agent-ui/dyn6.py): most controls had no accessible name – every labelled tick box (its text
    is a label beside the box), most choices, the sliders, the entries and the overlay list's icon-only buttons. With
    every page and tab shown once (tools/screenshots.shoot: the App fills what is on display), each tick box, choice,
    slider and entry has a name, and every button a screen reader can reach says what it is."""
    from PySide6.QtGui import QAccessible
    from PySide6.QtWidgets import QAbstractButton, QAbstractSpinBox, QCheckBox, QComboBox, QLineEdit, QSlider
    from fogscout.app import App
    from fogscout.qt_layouts import WrapCheck
    tool = _tool()
    app = App(str(app_root), simulate=str(app_root / "sim"))
    app.qt.resize(1100, 760)
    try:
        tool.shoot(app, str(app_root / "shots"))
        q = app.qt
        missing = []
        checks = [wc for wc in q.findChildren(WrapCheck) if wc.text().strip()]
        missing += [("check", wc.text()[:40]) for wc in checks if wc.box.accessibleName() != wc.text()]
        fields = [w for cls in (QComboBox, QSlider, QLineEdit) for w in q.findChildren(cls)
                  if not isinstance(w.parentWidget(), (QComboBox, QAbstractSpinBox))]
        missing += [(type(w).__name__, w.toolTip()[:40]) for w in fields if not w.accessibleName().strip()]
        for b in q.findChildren(QAbstractButton):
            if isinstance(b, QCheckBox) and isinstance(b.parentWidget(), WrapCheck):
                continue
            if not b.isVisibleTo(q) and not b.text():             # a button the App never showed (no text yet)
                continue
            i = QAccessible.queryAccessibleInterface(b)
            if not (i and i.text(QAccessible.Name).strip()):
                missing.append((type(b).__name__, b.objectName(), b.toolTip()[:40]))
        assert len(checks) > 40 and len(fields) > 100
        assert not missing, missing
        icons = q.findChildren(QAbstractButton, "ovicon") + q.findChildren(QAbstractButton, "ovcell")
        assert len(icons) >= 12 and all(b.accessibleName() for b in icons)
        switches = q.findChildren(QAbstractButton, "ovswitch")             # 1.57.49: on / off instead of the eye
        assert len(switches) == 7 and any(b.accessibleName() == "Karte: Ein – zum Ausschalten klicken"
                                          for b in switches)
    finally:
        app.quit()
