"""1.57.62 (security review): Qt shows a label's text as HTML when it looks like HTML (AutoText) – an <img> in a name
from an imported match file loaded that path (checked with a local file). Every label the pages make shows plain text."""
import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)


def test_the_labels_of_the_pages_never_show_html(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from fogscout import qt_common, qt_pages, qt_window
    qt_window.application()
    pic = tmp_path / "p.png"
    img = QImage(400, 400, QImage.Format_RGB32)
    img.fill(0xff0000)
    img.save(str(pic))
    text = f'<img src="{pic.as_posix()}"> Wraith'
    made = [qt_common._label(text), qt_common._label(text, cls="dim", wrap=True), qt_pages.HintLabel()]
    made[2].setText(text)
    for w in made:
        assert w.textFormat() == Qt.PlainText and w.text() == text
        w.adjustSize()
        assert w.sizeHint().height() < 200                   # the 400-px picture was not loaded: only text
