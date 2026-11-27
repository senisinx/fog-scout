"""The overlay editor (1.46, user: "Overlay-Steuerung grundlegend modernisieren … das Overlay-Fenster ist sehr klein"):
the page "Overlay" as one workspace – a tool bar (Anordnen, Rückgängig, Vorlage, Test, Fokus), the list of the
elements on the left (shown / own place / size, eye and lock), the canvas in the middle with all the room the
window has (qt_preview.PreviewView in fill mode) and a status line below it, and on the right the inspector of the
element picked (quick places, size, opacity, its settings). Built by qt_pages.FormPage from the spec kind "editor";
every control is still one of the page's ``controls`` – the search, ``open_tab`` and the App work as before.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import qt_icons, qt_theme
from .i18n import N_, _
from .qt_common import on_zoom

# element -> its settings tab (appconst.ELEMENT_TABS; repeated here: the Qt side never imports the App's mixins)
TABS = {"map": "ov.look", "text": "ov.info_f", "hud": "ov.sys", "today": "ov.today_f", "music": "ov.music_f",
        "inputs": "ov.inputs_f", "loadouts": "ov.loadouts_f", "charts": "ov.charts_f"}
GENERAL_TAB = "ov.pos"
NAMES = {"map": N_("Karte"), "text": N_("Infos"), "hud": N_("Systemwerte"), "today": N_("Heute"),
         "music": N_("Musik"), "inputs": N_("Eingaben"), "loadouts": N_("Loadouts"), "charts": N_("Diagramme")}
WHAT = {"map": N_("Callout-Karte der Map"), "text": N_("Timer, Bilanz, Server"), "hud": N_("CPU, GPU, RAM"),
        "today": N_("Runden und Zeit heute"), "music": N_("Läuft gerade"), "inputs": N_("Tasten und Gamepad"),
        "loadouts": N_("Perks der Mitspieler"), "charts": N_("Ping, Punkte, Kills …")}
INSPECTOR_W = 344            # px at text zoom 1.0: the settings of the element picked
MEDIUM_FROM = 720            # px (× zoom): from here the "stage" (1.57.87), below it all in one column
STAGE_MIN_H = 200            # px: the stage's preview is at least this tall …
STAGE_SETTINGS_H = 280       # … and leaves the settings below it at least this much of the editor's height
STAGE_COLS = 5               # elements per line under the stage (9 rows: two lines), from STAGE_COLS_FROM px on
STAGE_COLS_FROM = 1000
ALIGN_LABEL, ALIGN_COMBO = 104, 196     # px: row labels / choices of the inspector aligned at most this wide
PRESET_W = 190               # px: the choice of a preset in the tool bar
CELL = QSize(30, 20)         # one cell of the quick places (a small screen, 3×3)


def _icon_button(glyph: str, tip: str) -> QToolButton:
    b = QToolButton()
    b.setObjectName("ovicon")
    b.setAutoRaise(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.TabFocus)
    on_zoom(b, lambda _z: b.setIconSize(QSize(qt_theme.icon_px(qt_theme.ICON["m"]),     # 1.55.7: with the text
                                              qt_theme.icon_px(qt_theme.ICON["m"]))))   # zoom
    b._glyph = glyph
    _set_tip(b, tip)
    return b


def _set_tip(b, tip: str, owner: str = ""):
    """An icon-only button's tooltip – 1.55.7 (a11y audit): also its accessible name (a screen reader read nothing),
    with the element it belongs to in front ("Karte: Ausblenden")."""
    name = f"{owner}: {tip}" if owner else tip
    if b.toolTip() != tip:
        b.setToolTip(tip)
    if b.accessibleName() != name:
        b.setAccessibleName(name)


class SwitchButton(QAbstractButton):
    """1.57.49 (user: "Ein/Aus-Knopf für jedes Overlay-Element wäre einfacher"): an on / off switch – a pill with a
    knob, the accent when on. Checkable; ``clicked`` only for the user (``setChecked`` from the App posts nothing)."""

    W, H = 34, 18                # px at text zoom 1.0

    def __init__(self, tip: str = ""):
        super().__init__()
        self.setObjectName("ovswitch")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setAccessibleName(tip)
        on_zoom(self, lambda _z: self.updateGeometry())

    def sizeHint(self):
        return QSize(qt_theme.icon_px(self.W), qt_theme.icon_px(self.H))

    minimumSizeHint = sizeHint

    def paintEvent(self, _e):
        c = qt_theme.colours(qt_theme.current_dark())
        size = self.sizeHint()
        w, h = size.width(), size.height()
        x, y = (self.width() - w) / 2, (self.height() - h) / 2
        on = self.isChecked()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QColor(c["accent"] if on else c["btn"])
        if not self.isEnabled():
            track = QColor(c["btn_dis"])
        elif self.underMouse() and not on:
            track = QColor(c["btn_hover"])
        p.setPen(QColor(c["accent"] if on else c["border"]))
        p.setBrush(track)
        p.drawRoundedRect(QRectF(x + 0.5, y + 0.5, w - 1, h - 1), (h - 1) / 2, (h - 1) / 2)
        pad = max(2, round(h * 0.17))
        d = h - 2 * pad
        kx = x + w - pad - d if on else x + pad
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["on_accent"] if on else c["dim"]))
        p.drawEllipse(QRectF(kx, y + pad, d, d))
        if self.hasFocus():
            p.setPen(QColor(c["accent"]))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(x - 2, y - 2, w + 4, h + 4), (h + 4) / 2, (h + 4) / 2)
        p.end()


class _ElideLabel(QLabel):
    """1.55.7 (audit V-1, 150 % in a small window): a one-line text of the element list ends in "…" when its room is
    narrower – it was cut in the middle of a word. The whole text stays ``text()`` (and the row's accessible name)."""

    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        return QSize(min(s.width(), self.fontMetrics().horizontalAdvance("…") + 2), s.height())

    def paintEvent(self, e):
        r = self.contentsRect()
        fm = self.fontMetrics()
        if fm.horizontalAdvance(self.text()) <= r.width():
            super().paintEvent(e)
            return
        p = QPainter(self)
        self.style().drawItemText(p, r, int(self.alignment()), self.palette(), self.isEnabled(),
                                  fm.elidedText(self.text(), Qt.ElideRight, r.width()), self.foregroundRole())
        p.end()


def _paint_icon(b: QToolButton, glyph: str, on: bool):
    c = qt_theme.colours(qt_theme.current_dark())
    side = qt_theme.icon_px(qt_theme.ICON["m"])
    if b.__dict__.get("_painted") != (glyph, on, c["accent"], c["dim"], side):
        b._painted = (glyph, on, c["accent"], c["dim"], side)
        b.setIcon(qt_icons.icon(glyph, c["accent"] if on else c["dim"], size=side))


class _Row(QFrame):
    """One element in the list: its name and state, a switch (on / off, 1.57.49 – was an eye) and a lock (stays
    where it is)."""

    def __init__(self, rail, name: str):
        super().__init__()
        self.setObjectName("ovrow")
        self.name = name
        self._rail = rail
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 4, 5)
        lay.setSpacing(4)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = _ElideLabel(_(NAMES.get(name, name)) if name != "general" else _("Allgemein"))
        self.title.setObjectName("ovrowname")
        self.info = _ElideLabel(_(WHAT.get(name, "")) if name != "general" else _("Stil, Abstand, Grenzen"))
        self.info.setObjectName("ovrowinfo")
        self.setAccessibleName(self.title.text())           # 1.55.7: the row is a focus stop of its own
        self.setAccessibleDescription(self.info.text())
        for lbl in (self.title, self.info):
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        texts.addWidget(self.title)
        texts.addWidget(self.info)
        lay.addLayout(texts, 1)
        self.eye = self.lock = None
        if name != "general":
            self.eye = SwitchButton(_("Ein oder aus"))
            _set_tip(self.eye, _("Ein oder aus"), self.title.text())
            self.eye.clicked.connect(lambda on: rail.post(("show", name, bool(on))))
            self.lock = _icon_button("lock_open", _("Sperren: im Modus „Anordnen“ nicht mehr verschiebbar"))
            _set_tip(self.lock, self.lock.toolTip(), self.title.text())
            self.lock.clicked.connect(lambda: rail.post(("lock", name, not self.lock.property("on"))))
            lay.addWidget(self.lock)
            lay.addSpacing(4)
            lay.addWidget(self.eye)

    def show_row(self, row: dict, selected: bool):
        if self.property("selected") != selected:
            self.setProperty("selected", selected)
            self.style().unpolish(self)
            self.style().polish(self)
        if self.eye is None:
            return
        shown, locked = bool(row.get("shown")), bool(row.get("locked"))
        off = not shown
        if self.title.property("off") != off:
            self.title.setProperty("off", off)
            self.title.style().unpolish(self.title)
            self.title.style().polish(self.title)
        parts = [_("eigener Platz") if row.get("own") else _("automatisch")] if shown else [_("ausgeblendet")]
        if shown and row.get("size"):
            parts.append(f"{round(row['size'])} %")
        info = " · ".join(parts)
        if self.info.text() != info:
            self.info.setText(info)
            self.setAccessibleDescription(info)
        if self.eye.isChecked() != shown:
            self.eye.setChecked(shown)
        _set_tip(self.eye, _("Ein – zum Ausschalten klicken") if shown else _("Aus – zum Einschalten klicken"),
                 self.title.text())
        self.lock.setProperty("on", locked)
        _paint_icon(self.lock, "lock" if locked else "lock_open", locked)
        _set_tip(self.lock, _("Entsperren: wieder verschiebbar") if locked else
                 _("Sperren: im Modus „Anordnen“ nicht mehr verschiebbar"), self.title.text())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._rail.post(("general",) if self.name == "general" else ("select", self.name))
            e.accept()
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._rail.post(("general",) if self.name == "general" else ("select", self.name))
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        if self.name != "general":
            gp = e.globalPos()
            self._rail.post(("menu", self.name, gp.x(), gp.y()))


class ElementRail(QWidget):
    """The list of the overlay's elements (control kind "elements", model ``ui.Elements``): a click picks one, the
    eye shows / hides it, the lock keeps it where it is, a right click opens its quick actions. Posts
    ("act", (key, value)) like every control."""

    COMPACT_COLS = 4                # columns of the list on a narrower page

    def __init__(self, key, post):
        super().__init__()
        self._key, self._post = key, post
        self._rows = {}
        self._order = ()
        self._compact, self._cols = False, self.COMPACT_COLS
        self.general = False        # the tab "Allgemein" is open (the editor says so)
        self._data = {}
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(2)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

    def post(self, value):
        self._post("act", (self._key, value))

    def rows(self) -> dict:
        return dict(self._rows)

    def set_compact(self, on: bool, cols: int | None = None):
        """``cols``: chips per line (default COMPACT_COLS)."""
        cols = int(cols or self.COMPACT_COLS)
        if bool(on) != self._compact or cols != self._cols:
            self._compact, self._cols = bool(on), cols
            self._place()

    def _place(self):
        for row in self._rows.values():
            self.grid.removeWidget(row)
        names = list(self._order) + ["general"]
        cols = self._cols if self._compact else 1
        for c in range(max(self.grid.columnCount(), cols)):   # 1.55.7: chips share the width equally (a long name
            self.grid.setColumnStretch(c, 1 if self._compact and c < cols else 0)   # ends in "…", it squeezes none)
        for i, name in enumerate(n for n in names if n in self._rows):
            row = self._rows[name]
            row.setSizePolicy(QSizePolicy.Ignored if self._compact else QSizePolicy.Preferred,
                              row.sizePolicy().verticalPolicy())
            self.grid.addWidget(row, i // cols, i % cols)

    def show_state(self, st):
        self.setVisible(bool(st.get("visible", True)))
        data = st.get("data") or {}
        self._data = data
        order = tuple(data.get("order") or ())
        if order != self._order:
            for name in order + ("general",):
                if name not in self._rows:
                    self._rows[name] = _Row(self, name)
            for name in set(self._rows) - set(order) - {"general"}:
                self._rows.pop(name).deleteLater()
            self._order = order
            self._place()
        self.refresh()

    def refresh(self):
        data = self._data
        rows = data.get("rows") or {}
        sel = None if self.general else data.get("selected")
        for name, row in self._rows.items():
            if name == "general":
                row.show_row({}, self.general)
            else:
                r = rows.get(name) or {}
                row.show_row(r, name == sel)


class AnchorGrid(QWidget):
    """Quick places for the element picked (control kind "anchors", model ``ui.Anchors``): a small screen of 3×3
    cells – corners, edges, centre – and "Üblicher Platz" (the automatic place). Posts ("cell", col, row) /
    ("auto",)."""

    def __init__(self, key, post):
        super().__init__()
        self._key, self._post = key, post
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.screen = QFrame()
        self.screen.setObjectName("ovcanvas")
        g = QGridLayout(self.screen)
        g.setContentsMargins(5, 5, 5, 5)
        g.setSpacing(4)
        self.cells = {}
        words = {(0, 0): N_("oben links"), (1, 0): N_("oben Mitte"), (2, 0): N_("oben rechts"),
                 (0, 1): N_("links Mitte"), (1, 1): N_("Mitte"), (2, 1): N_("rechts Mitte"),
                 (0, 2): N_("unten links"), (1, 2): N_("unten Mitte"), (2, 2): N_("unten rechts")}
        for (c, r), word in words.items():
            b = QPushButton()
            b.setObjectName("ovcell")
            b.setCheckable(True)
            b.setFixedSize(CELL)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.TabFocus)
            _set_tip(b, _("Nach {where} legen (mit Rand)", where=_(word)))   # 1.55.7: also its accessible name
            b.clicked.connect(lambda _c=False, c=c, r=r: self._click(("cell", c, r)))
            g.addWidget(b, r, c)
            self.cells[(c, r)] = b
        lay.addWidget(self.screen)
        side = QVBoxLayout()
        side.setSpacing(6)
        self.auto = QPushButton(_("Üblicher Platz"))
        self.auto.setCheckable(True)
        self.auto.setProperty("class", "toggle")
        self.auto.setFocusPolicy(Qt.TabFocus)
        self.auto.setToolTip(_("Zurück an den automatischen Platz (im schwarzen Balken, neben den anderen)"))
        self.auto.clicked.connect(lambda _c=False: self._click(("auto",)))
        self.note = QLabel("")
        self.note.setProperty("class", "hint")
        self.note.setWordWrap(True)
        side.addWidget(self.auto, 0, Qt.AlignLeft)
        side.addWidget(self.note)
        side.addStretch()
        lay.addLayout(side, 1)
        self._data = {}

    def _click(self, value):
        self._post("act", (self._key, value))
        self._show(self._data)                  # the App's answer sets the real state (no half-checked cell)

    def show_state(self, st):
        self.setVisible(bool(st.get("visible", True)))
        self._data = st.get("data") or {}
        self._show(self._data)

    def _show(self, data):
        cell = data.get("cell")
        on = tuple(cell) if isinstance(cell, (list, tuple)) else None
        for key, b in self.cells.items():
            if b.isChecked() != (key == on):
                b.setChecked(key == on)
        if self.auto.isChecked() != (cell == "auto"):
            self.auto.setChecked(cell == "auto")
        enabled = bool(data.get("enabled", True))
        self.screen.setEnabled(enabled)
        self.auto.setEnabled(enabled)
        text = _("Gesperrt – erst entsperren") if not enabled else data.get("note", "")
        if self.note.text() != text:
            self.note.setText(text)


class OverlayEditor(QWidget):
    """The page "Overlay" as an editor (see the module's text). ``item`` = ("editor", toolbar, rail, canvas,
    inspector): lists of spec items, built through the FormPage ``page`` (so every control is in page.controls)."""

    def __init__(self, page, item, page_key):
        super().__init__()
        from .qt_layouts import FlowRow
        self.page = page
        self._post = page._post
        _kind, toolbar, rail, canvas, inspector = item
        self._focus = False
        self._editing = False
        self._selected = None
        self._wide = None
        self._arranging = False
        # its width is the page's: its parts' minimum must not widen it (each width picks its own arrangement)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        # ---- tool bar: the moving mode first (the main action), the rarer ones after it, focus at the right end
        self.bar = QFrame()
        self.bar.setObjectName("ovbar")
        bl = QVBoxLayout(self.bar)
        bl.setContentsMargins(10, 8, 10, 8)
        row = FlowRow()
        cut = next((i for i, c in enumerate(toolbar) if c[0] == "stretch"), len(toolbar))
        row.right = len([c for c in toolbar[cut:] if c[0] != "stretch"])
        for c in toolbar:
            if c[0] != "stretch":
                page._add(c, row)
        from .qt_pages import _link_names                 # 1.55.7: the preset choice is named by its label
        _link_names(page.controls, [c[1] for c in toolbar if c[0] != "stretch"])
        bl.addLayout(row)
        preset = page.controls.get("ov.preset")
        if preset is not None:                          # the presets' names are long: the bar stays one line
            on_zoom(preset[1], lambda z, w=preset[1]: w.setMaximumWidth(round(PRESET_W * z)))   # 1.55.7: and on a change
        outer.addWidget(self.bar)
        # ---- body: list | canvas + status | inspector (a grid: arrange() puts them per width)
        self.body = QGridLayout()
        self.body.setSpacing(10)
        self.rail = QFrame()
        self.rail.setObjectName("ovrail")
        rl = QVBoxLayout(self.rail)
        rl.setContentsMargins(8, 10, 8, 10)
        rl.setSpacing(4)
        self.rail_head = QLabel(_("Elemente").upper())
        self.rail_head.setObjectName("ovsection")
        rl.addWidget(self.rail_head)
        page._items(rail, rl, page_key)
        rl.addStretch()
        self.canvas_box = QFrame()
        self.canvas_box.setObjectName("ovcanvas")
        cl = QVBoxLayout(self.canvas_box)
        cl.setContentsMargins(8, 8, 8, 6)
        cl.setSpacing(4)
        page._items(canvas, cl, page_key)
        self.canvas = next((w for k, (kind, w, _x) in page.controls.items() if kind == "preview"), None)
        if self.canvas is not None:
            self.canvas.set_fill(True)
            self.canvas.status_changed.connect(self._status)
            cl.setStretchFactor(self.canvas, 1)
        sl = QHBoxLayout()
        sl.setSpacing(12)
        self.status = QLabel("")
        self.status.setObjectName("ovstatus")
        self.status.setWordWrap(True)
        self.layout_label = QLabel("")
        self.layout_label.setObjectName("ovstatus")
        self.layout_label.setToolTip(_("Position und Grösse werden je DBD-Fenstergrösse gemerkt (Reiter Allgemein)."))
        sl.addWidget(self.status, 1)
        sl.addWidget(self.layout_label, 0, Qt.AlignRight | Qt.AlignTop)
        cl.addLayout(sl)
        self.inspector = QFrame()
        self.inspector.setObjectName("ovinspector")
        il = QVBoxLayout(self.inspector)
        il.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        from .qt_common import steady_scroll
        steady_scroll(self.scroll)
        content = QWidget()
        content.setObjectName("page")
        self.content = content
        cl2 = QVBoxLayout(content)
        cl2.setContentsMargins(*qt_theme.PAD_CARD)
        cl2.setSpacing(6)
        self.head = QLabel("")
        self.head.setObjectName("ovhead")
        self.subhead = QLabel("")
        self.subhead.setObjectName("ovrowinfo")
        cl2.addWidget(self.head)
        cl2.addWidget(self.subhead)
        page.align_label_max, page.align_combo_max = ALIGN_LABEL, ALIGN_COMBO   # a narrow column: compact rows
        # the element's own part (quick place, size, opacity): one box the editor hides for "Allgemein" – never
        # the controls themselves (show_control shows them again on every refresh)
        self.element_box = QWidget()
        eb = QVBoxLayout(self.element_box)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(6)
        cut = next((i for i, it in enumerate(inspector) if it[0] == "tabs"), len(inspector))
        page._group = []
        page._items(inspector[:cut], eb, page_key)
        page._align()                                   # sizes and opacity line up (aligned once texts are in)
        eb.addStretch()
        # 1.57.87 (user picked the draft "Bühne"): place / size / opacity and the element's own settings side by
        # side under the preview (below each other in a narrow window)
        self.columns = QBoxLayout(QBoxLayout.LeftToRight)
        self.columns.setContentsMargins(0, 0, 0, 0)
        self.columns.setSpacing(24)
        self.columns.addWidget(self.element_box)
        self.own_box = QWidget()
        ob = QVBoxLayout(self.own_box)
        ob.setContentsMargins(0, 0, 0, 0)
        ob.setSpacing(6)
        page._items(inspector[cut:], ob, page_key)
        ob.addStretch()
        self.columns.addWidget(self.own_box, 1)
        cl2.addLayout(self.columns)
        cl2.addStretch()
        self.scroll.setWidget(content)
        il.addWidget(self.scroll)
        outer.addLayout(self.body, 1)
        # the element tabs: the inspector shows the one of the element picked – no tab row (the list is it)
        self.tabs = next((w for k, (kind, w, _x) in page.controls.items() if kind == "tab"), None)
        if self.tabs is not None:
            self.tabs.tabBar().hide()
            self.tabs.currentChanged.connect(self._tab_changed)
        self.rail_view = next((w for k, (kind, w, _x) in page.controls.items() if kind == "elements"), None)
        for body in (b for _k, (kind, _w, b) in page.controls.items() if kind == "tab"):
            body.layout().setContentsMargins(0, 4, 0, 0)    # the inspector has its own padding
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._escape, context=Qt.WidgetWithChildrenShortcut)
        on_zoom(self, lambda _z: self._rezoomed())
        self.arrange(1400)

    # ------------------------------------------------------------ layout
    def mode_for(self, width: int) -> str:
        return "stage" if width >= MEDIUM_FROM * qt_theme.current_zoom() else "narrow"

    def arrange(self, width: int):
        """1.57.87 (user picked the draft "Bühne"): "stage" – the preview on top across the page, below it the row
        of all elements with their switches, below that the settings of the element picked (place and size beside
        its own settings); "narrow": the same order, the settings in one column (the page scrolls). Before: the
        list, the preview and the settings side by side."""
        mode = self.mode_for(width)
        if mode == self._wide:
            return
        self._wide = mode
        z = qt_theme.current_zoom()
        for w in (self.rail, self.canvas_box, self.inspector):
            self.body.removeWidget(w)
            w.setMinimumSize(0, 0)
            w.setMaximumSize(16777215, 16777215)
        for i in range(3):
            self.body.setColumnStretch(i, 0)
            self.body.setRowStretch(i, 0)
        if self.rail_view is not None:
            self.rail_view.set_compact(True, STAGE_COLS if width >= STAGE_COLS_FROM * z else None)
        self.rail_head.setVisible(False)
        self.body.addWidget(self.canvas_box, 0, 0)
        self.body.addWidget(self.rail, 1, 0)
        self.body.addWidget(self.inspector, 2, 0)
        self.body.setColumnStretch(0, 1)
        if mode == "stage":
            self.columns.setDirection(QBoxLayout.LeftToRight)
            self.element_box.setFixedWidth(round(INSPECTOR_W * z))
            self.inspector.setMinimumHeight(STAGE_SETTINGS_H)
            self.body.setRowStretch(2, 1)
            self._stage_canvas()
        else:
            self.columns.setDirection(QBoxLayout.TopToBottom)
            self.element_box.setMinimumWidth(0)
            self.element_box.setMaximumWidth(16777215)
            self.inspector.setMinimumHeight(420)
            self._narrow_canvas()

    def _stage_canvas(self):
        """The stage: as tall as a 21:9 picture across the page – less where the settings below would not keep
        STAGE_SETTINGS_H of the editor's height, never under STAGE_MIN_H."""
        gap = self.body.spacing()
        room = self._view_height() - self.bar.sizeHint().height() - self.rail.sizeHint().height() - 3 * gap \
            - STAGE_SETTINGS_H
        h = max(STAGE_MIN_H, min(round(self.width() * 9 / 21) + 40, room))
        if self.canvas_box.minimumHeight() != h or self.canvas_box.maximumHeight() != h:
            self.canvas_box.setFixedHeight(h)

    def _view_height(self) -> int:
        """The height the editor has on display: the page scrolls, so its own height is what it asks for – the
        scroll area's view minus what stands above the editor."""
        w = self.parentWidget()
        while w is not None and not isinstance(w, QScrollArea):
            w = w.parentWidget()
        if w is None:
            return self.height()
        return max(0, w.viewport().height() - self.mapTo(w.widget(), self.rect().topLeft()).y())

    def _narrow_canvas(self):
        h = max(220, round(self.width() * 0.5))
        if self.canvas_box.minimumHeight() != h:
            self.canvas_box.setMinimumHeight(h)

    def mode(self) -> str:
        return self._wide or ""

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.mode_for(self.width()) != self._wide and not self._arranging:
            # never re-arrange inside a resize: removing and adding the parts makes the layout resize again (it
            # crashed Qt) – once, right after this event
            self._arranging = True
            QTimer.singleShot(0, self, self._arrange_now)
        elif self._wide == "narrow":
            self._narrow_canvas()
        elif self._wide == "stage":
            self._stage_canvas()

    def _rezoomed(self):
        """1.55.7: the text zoom changed while the window runs – the list's and inspector's widths follow it (arranged
        again right after, never inside the theme switch's own layout pass)."""
        if self._wide is not None and not self._arranging:
            self._wide = None
            self._arranging = True
            QTimer.singleShot(0, self, self._arrange_now)

    def _arrange_now(self):
        self._arranging = False
        self.arrange(self.width())

    # ------------------------------------------------------------ state from the App
    def show_states(self, states):
        st = states.get("ov.focus_mode")
        if st is not None:
            self._set_focus(bool(st.get("pressed")))
        st = states.get("ov.elements")
        if st is not None:
            data = st.get("data") or {}
            self._editing = bool(data.get("editing"))
            self._selected = data.get("selected")
            if self.canvas_box.property("editing") != self._editing:
                self.canvas_box.setProperty("editing", self._editing)
                self.canvas_box.style().unpolish(self.canvas_box)
                self.canvas_box.style().polish(self.canvas_box)
            key = data.get("layout") or ""
            text = _("Layout für {size}", size=key.replace("x", "×")) if key else ""
            if self.layout_label.text() != text:
                self.layout_label.setText(text)
            self._head(data)
            if self.canvas is not None:
                self._status(self.canvas.__dict__.get("_status") or {})

    def _head(self, data):
        general = self.tabs is not None and self._current_frame() == GENERAL_TAB
        if self.rail_view is not None and self.rail_view.general != general:
            self.rail_view.general = general
            self.rail_view.refresh()
        name = data.get("selected")
        row = (data.get("rows") or {}).get(name) or {}
        if general:
            head, sub = _("Allgemein"), _("Gilt für alle Elemente")
        else:
            head = _(NAMES.get(name, name or ""))
            sub = _("gesperrt") if row.get("locked") else ""
            place = (_("eigener Platz") if row.get("own") else _("automatisch")) if row.get("shown", True) \
                else _("ausgeblendet")
            sub = " · ".join(p for p in (place, sub) if p)
        if self.head.text() != head:
            self.head.setText(head)
        if self.subhead.text() != sub:
            self.subhead.setText(sub)
        if self.element_box.isHidden() != general:
            self.element_box.setVisible(not general)

    def _current_frame(self):
        if self.tabs is None:
            return None
        cur = self.tabs.currentWidget()
        return next((k for k, (kind, w, body) in self.page.controls.items() if kind == "tab" and body is cur), None)

    def _tab_changed(self, _i):
        """A tab opened by the search / reveal: the list follows (the element of that tab is picked). A tab the App
        opened for its own pick (MainWindow.open_tab) is not reported back – with a stale pick on a page not shown,
        the two picks sent each other back and forth for ever."""
        frame = self._current_frame()
        if self.tabs.__dict__.get("_by_app"):
            pass
        elif frame == GENERAL_TAB:
            self._post("act", ("ov.elements", ("general",)))
        elif frame and TABS.get(self._selected) != frame:
            name = next((n for n, f in TABS.items() if f == frame), None)
            if name:
                self._post("act", ("ov.elements", ("select", name)))
        if self.rail_view is not None:
            self.rail_view.general = frame == GENERAL_TAB
            self.rail_view.refresh()
        self.scroll.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------ focus view, Esc, status line
    def _set_focus(self, on: bool):
        if on == self._focus:
            return
        self._focus = on
        self.rail.setVisible(not on)
        self.inspector.setVisible(not on)
        for lbl in self.page.findChildren(QLabel):
            if lbl.property("class") in ("h1", "subtitle") and not self.isAncestorOf(lbl):
                lbl.setVisible(not on)

    def focus_on(self) -> bool:
        return self._focus

    def _escape(self):
        if self._focus:
            self._post("act", ("ov.focus_mode", None))
        elif self._editing:
            self._post("act", ("ov.edit", None))

    def _status(self, st: dict):
        name = lambda n: _(NAMES.get(n, n or ""))          # noqa: E731
        editing = bool(st.get("editing", self._editing))
        if st.get("limit"):
            text = _("Grenzlinie: ziehen, bis wohin die Elemente im Balken reichen")
        elif st.get("sizing"):
            text = _("Grösse von {name}: Ecke ziehen", name=name(st["sizing"]))
        elif st.get("grab"):
            text = _("Ziehst: {name}", name=name(st["grab"])) + " · " + \
                (_("eingerastet") if st.get("snapped") else _("rastet an Mitte, Balken und anderen ein (Alt = frei)"))
        elif editing and st.get("hover") and st["hover"] in (st.get("locked") or ()):
            text = _("{name} ist gesperrt – das Schloss in der Liste löst es", name=name(st["hover"]))
        elif editing and st.get("hover"):
            text = _("{name}: ziehen = verschieben · Ecke oder Strg+Mausrad = Grösse · Rechtsklick = Menü",
                     name=name(st["hover"]))
        elif editing:
            text = _("Anordnen aktiv – auch im Spiel: Elemente ziehen · Pfeiltasten = fein (Shift = 10 px) · "
                     "Tab = nächstes Element · Esc = fertig")
            if st.get("limits_off"):
                text += " · " + _("graue Linien in den Balken = Grenzen (aus) – eine ziehen schaltet sie ein")
        elif st.get("hover"):
            text = _("Klick wählt {name}", name=name(st["hover"]))
        else:
            text = _("Klick wählt ein Element · „Anordnen“ schaltet das Verschieben ein – hier und im Spiel")
        if self.status.text() != text:
            self.status.setText(text)
        if self.status.property("editing") != editing:
            self.status.setProperty("editing", editing)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

