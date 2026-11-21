"""The overlay element "Loadouts" (1.57, user: "Man sieht seit paar Monaten neu, was jeder Survivor mitnimmt, wenn
man ins Menü geht. Wäre es möglich, die Perks so anzeigen zu lassen links vom entsprechenden Spieler?" – Killer
sehen es nicht): the other survivors' perks (and item, add-ons) as DBD's 2×2 perk diamond beside each of them in
the HUD's survivor list. Read by the worker from the pause menu (loadouts.Reader, only the screen picture, only
while the menu is open, a few looks per round); drawn by overlay_render.loadout_card; placed by layout.loadouts_xy
(shared with the preview). 1.57.36 (user: "Ich meine die Offerings der Survivor. Die sieht man als killer im
spiel"): as the killer DBD's menu shows the survivors' offerings – those are read and drawn beside each of them
(overlay_render.offering_card).

Mixin of App (app.py) – the methods use App's attributes. Imports no other mixin (tests/test_mixins.py)."""
from __future__ import annotations

import logging

import numpy as np

from . import layout, loadouts
from .appconst import LOADOUT_LOOKS, LOADOUT_SPOTS, LOADOUT_STYLES
from .capture import IS_WIN
from .i18n import _

log = logging.getLogger("fogscout")

# what the preview and "Overlay testen" show (made up; names of the wiki's survivor perks) – at the list's usual rows
SAMPLE = loadouts.Board(rows=(
    loadouts.Row(own=True),
    loadouts.Row(perks=("Dead Hard", "Resurgence", "Made for This", "Windows of Opportunity"),
                 item="Emergency Med-Kit", addons=("Gel Dressings", None), offering=loadouts.HIDDEN_OFFERING),
    loadouts.Row(perks=("Sprint Burst", None, "We'll Make It", "Resilience")),
    loadouts.Row(perks=("Sprint Burst", "Vigil", "Resilience", "Finesse"), item="Utility Flashlight",
                 addons=("Long Life Battery", "Odd Bulb"), offering="Petrified Oak")))


def icon_for(name, kind):
    """The picture file of a name the reader gave (overlay_render.loadout_card's ``icon``); a slot cut from the
    menu (1.57.25, a PIL picture) as it is."""
    if name is None or not isinstance(name, str):
        return name
    return loadouts.icon_file(name, kind)


def look_of(o: dict) -> str:
    """1.57.25: "picture" – the slots as cut from the menu (default), "icons" – the names read, drawn with the
    wiki's pictures (until 1.57.24 the only way)."""
    return "icons" if o.get("loadouts_look", "picture") == "icons" else "picture"


def with_pictures(row):
    """1.57.25: ``row`` with each slot the menu showed as its picture (PIL) instead of the name read – what the menu
    showed is what is drawn, read or not. A row without pictures stays as it is."""
    import dataclasses
    from PIL import Image
    if not row.pics:
        return row
    names = row.perks + (row.item,) + row.addons + (row.offering,)
    pics = [Image.fromarray(np.ascontiguousarray(p[:, :, [2, 1, 0, 3]]), "RGBA") if p is not None else name
            for p, name in zip(row.pics, names)]          # a slot cut off the picture: its name read, as before
    return dataclasses.replace(row, perks=tuple(pics[:4]), item=pics[4], addons=tuple(pics[5:7]), offering=pics[7])


def style_of(o: dict) -> str:
    """1.57.9 (user: "Die Einstellung macht keinen Sinn – wie kann es Raute 2×2 sein, wenn es in einer Reihe sein
    soll"): the style drawn – beside the list always the diamond (a row doesn't fit there), below the name always a
    row; only at a place of one's own the setting ``loadouts_style`` counts."""
    spot = o.get("loadouts_pos", "hud")
    if spot == "name":
        return "row"
    if spot == "custom":
        return o.get("loadouts_style", "diamond")
    return "diamond"


def placed(o: dict, game, board, editing: bool = False, sample: bool = False):
    """(picture, x, y) of the loadouts in the game window ``game`` (also the preview's), or None. Live (not
    ``sample``) only the rows whose portrait the worker found in the HUD – beside it; the sample at the list's
    usual rows."""
    if board is None:
        return None
    rows = [r for r in board.others if sample or r.hud]
    if not sample and look_of(o) == "picture":       # 1.57.25: the menu's own pictures
        rows = [with_pictures(r) for r in rows]
    rows = [r for r in rows if not r.empty]
    if not rows:
        return None
    from .overlay_render import add_border, loadout_card, offering_card
    gx, gy, gw, gh = game
    spot = o.get("loadouts_pos", "hud")
    cluster, centres, left, face, mid = layout.loadout_rows(o, game, rows)
    row = style_of(o) == "row"
    items = bool(o.get("loadouts_items", True))
    if not row and spot == "hud" and not board.killer:
        cluster = fit_before(o, game, cluster, face, left, items)   # 1.57.42: never into the bar for want of room
    if row:                                          # a row of perks: as tall as the room below a name
        cluster = max(10, int(face * layout.LOADOUT_ROW_H * layout.loadout_scale(o)))
        if spot == "name":                           # 1.57.17: between the row above and the name
            cluster = min(cluster, max(10, int(face * layout.LOADOUT_NAME_ROOM)))
    if spot == "name":                               # 1.57.17: beside the status icon above the name
        starts = [c + face * layout.LOADOUT_NAME_Y - cluster / 2 for _r, c in centres]
    else:                                            # beside the portrait: centred on it
        starts = [c - cluster / 2 for _r, c in centres]
    extra, over = None, 0.0
    if not row and not board.killer and items:
        extra = extra_side(o, game, cluster, face, left)
        over = max(0.0, (4 * extra + 3 * max(1, cluster // 48) - cluster) / 2)   # the column past the diamond
    top = starts[0] - over
    height = int(round(starts[-1] + over - top + cluster))
    if board.killer:                                 # 1.57.36: as the killer only the survivors' offerings
        pic = offering_card([r for r, _c in centres], cluster, [s - top for s in starts], height, icon_for)
    else:
        pic = loadout_card([r for r, _c in centres], cluster, [s - top for s in starts], height,
                           items, icon_for, row=row, extra=extra)
    if editing:
        pic = add_border(pic, _("LOADOUTS"))
    if spot == "name":
        x = int(round(min(mid + face * layout.LOADOUT_NAME_X, gx + gw - pic.width)))
        return pic, x, int(round(top))
    x, y = layout.loadouts_xy(spot, game, pic.size, int(gh * o.get("margin", 0.012)), top, o.get("loadouts_xy"), left)
    return pic, x, y


EXTRA_ROOM = 0.92            # 1.57.41: the small slots' column may fill this share of the step between two rows


def extra_side(o: dict, game, cluster: int, face: float, left: float) -> int:
    """1.57.41 (user to "the small slots are tiny – bigger?": "gern"): the side of the four small slots beside a
    perk diamond – as tall as the step between two rows of the list allows (``EXTRA_ROOM``) and, beside the
    portraits, as wide as the room between the 16:9 picture's edge and them allows; never smaller than before (a
    quarter of the diamond)."""
    gx, gy, gw, gh = game
    gap = max(1, cluster // 48)
    step = face * layout.LOADOUT_STEP / layout.LOADOUT_FACE
    side = (EXTRA_ROOM * step - 3 * gap) / 4
    if o.get("loadouts_pos", "hud") == "hud" and left is not None:
        vx = gx + (gw - min(gw, gh * 16 / 9)) / 2
        side = min(side, left - vx - 2 - cluster - max(2, cluster // 16))
    return max(cluster // 4, int(side))


FIT_SMALLEST = 0.6          # 1.57.42: the diamond shrinks down to this share to stay before the portraits


def fit_before(o: dict, game, cluster: int, face: float, left: float, items: bool) -> int:
    """1.57.42 (user's screenshot: the loadouts on the map in the black bar – no room before the portraits, so
    loadouts_xy put them beside the 16:9 picture, where the map stands): the diamond's size that lets the loadouts
    stand right before the portraits – the small slots first give up their extra size (``extra_side`` follows the
    room), then the diamond shrinks, down to ``FIT_SMALLEST``; below that the old place in the bar."""
    gx, gy, gw, gh = game
    if left is None:
        return cluster
    vx = gx + (gw - min(gw, gh * 16 / 9)) / 2
    room = left - vx - 2
    for k in range(0, 9):
        c = max(10, int(cluster * (1 - k * (1 - FIT_SMALLEST) / 8)))
        w = c + ((extra_side(o, game, c, face, left) + max(2, c // 16)) if items else 0)
        if w <= room:
            return c
    return cluster


class LoadoutsCard:
    def _loadouts_init(self):
        self._loadout_board = None           # the board of the round on display (loadouts.Board) or None
        self._loadout_gen = None             # … read for this map (worker.watch_gen)
        self._loadout_key, self._loadout_at = None, None     # (picture, x, y) for the last board / window / settings
        self.loadouts_win = None
        if IS_WIN:
            try:
                from .overlay_win32 import HudWindow
                self.loadouts_win = HudWindow("Fog Scout Loadouts")
            except Exception as e:
                log.warning("Loadouts-Fenster nicht verfügbar: %s", e)
        if self.loadouts_win is not None:
            self.loadouts_win.on_moved = lambda x, y: self.events.put(("call", self._loadouts_dragged, (x, y)))
            self.loadouts_win.on_reset = lambda: self.events.put(("call", self._el_reset, ("loadouts",)))
            self.loadouts_win.on_menu = lambda: self.events.put(("call", self._game_menu, ("loadouts",)))
            self._edit_comfort("loadouts", self.loadouts_win)
            self.loadouts_win.edit_label = _("LOADOUTS")

    # ---- what the worker reads, what is shown
    def _loadouts_on(self) -> bool:
        return bool(self.settings["overlay"].get("show_loadouts", False))

    def _loadouts_killer(self) -> bool:
        """The round is the killer's (lobby or round said so). 1.57.36: DBD's menu shows the survivors' offerings
        then (no perks) – read like a survivor's menu (``loadouts.Reader._killer``)."""
        role = (getattr(self, "_hist", None) or {}).get("role") or (getattr(self, "_queue", None) or {}).get("role")
        return role == "killer"

    def _loadouts_want(self) -> None:
        """Tell the worker whether to look at the pause menu (the element on; 1.57.36: as the killer too)."""
        self.worker.loadouts_wanted = self._loadouts_on()

    def _loadouts_event(self, d: dict) -> None:
        """The worker read (more of) the board of the round on display."""
        if d.get("gen") != self.worker.watch_gen:
            return                                   # about a map no longer on display
        board = d.get("board")
        first = self._loadout_board is None
        self._loadout_board, self._loadout_gen = board, d.get("gen")
        if first and board is not None:
            if board.killer:                         # 1.57.36: the killer's menu – offerings only
                n = sum(1 for r in board.rows if r.offering)
                self._log(_("Opfergaben der Survivor aus dem Menü gelesen ({n}).", n=n), "Erkennung")
            else:
                n = sum(1 for r in board.others for p in r.perks if p)
                self._log(_("Loadouts der Mitspieler aus dem Menü gelesen ({n} Perks).", n=n), "Erkennung")
        self._tick_overlay(reschedule=False)

    def _loadouts_board(self):
        """(board, sample?) to show now, or (None, False)."""
        if self.loadouts_win is None or not self._loadouts_on():
            return None, False
        if self.overlay.editing or getattr(self, "_forced", False):
            return SAMPLE, True
        if self._loadout_gen != self.worker.watch_gen:
            self._loadout_board = None                 # a new map: the old round's survivors are gone
        board = self._loadout_board
        # 1.57.40 (user: "wieso verschwindet die perk ansicht immer wenn ich ins menü gehe? Die soll drin bleiben"):
        # the pause menu no longer hides them (1.57.2 did: DBD hides its HUD there) – neither DBD's menu read by
        # the worker nor the map's menu pause; everything else that hides the map still hides them (1.57.23)
        menu_only = getattr(self, "_map_by_menu", False)
        if (board is None or self.hidden_after_match
                or not self.overlay.has_map() or not self.user_visible
                or (getattr(self, "_map_reason", None) and not menu_only)):     # hidden with the map (DBD not in
            return None, False                                                   # front, hidden by hand …)
        return board, False

    # ---- placing (every overlay tick)
    def _loadouts_hide(self) -> None:
        if self.loadouts_win is not None:
            self.loadouts_win.hide()
        self.worker.loadouts_rect = None

    def _loadouts_place(self) -> None:
        """Called by the overlay tick before the elements are moved apart (_el_resolve)."""
        self._loadouts_want()
        win = self.loadouts_win
        if win is None:
            return
        o = self.settings["overlay"]
        win.set_editing(self._loadouts_on() and self._el_editable("loadouts"))
        board, sample = self._loadouts_board()
        game = self._game_rect()
        if board is None or game[3] <= 0:
            self._loadouts_hide()
            return
        key = (board.key(), game, o.get("loadouts_scale"), o.get("loadouts_pos"), o.get("loadouts_xy"),
               o.get("loadouts_style"), look_of(o),
               bool(o.get("loadouts_items", True)), win.editing, sample)
        if key != getattr(self, "_loadout_key", None):
            self._loadout_key = key
            self._loadout_at = placed(o, game, board, win.editing, sample)
        at = self._loadout_at
        if at is None:
            self._loadouts_hide()
            return
        pic, x, y = at
        win.set_picture(pic, key)
        win.opacity = o.get("loadouts_opacity", o["opacity"])
        self.worker.loadouts_rect = self._el_show("loadouts", win, x, y, win.size)

    # ---- settings and dragging
    def _loadouts_dragged(self, x, y) -> None:
        """Dropped somewhere in the game (edit mode): its own place from now on."""
        self._layout_mark()
        gx, gy, gw, gh = self._game_rect()
        self._loadouts_own_place(*layout.media_own(gw, gh, self.loadouts_win.size, x - gx, y - gy))

    def _loadouts_own_place(self, fx, fy) -> None:
        o = self.settings["overlay"]
        o["loadouts_xy"], o["loadouts_pos"] = [fx, fy], "custom"
        if hasattr(self, "loadouts_pos_var"):
            self.loadouts_pos_var.set(_(dict(LOADOUT_SPOTS)["custom"]))
        self._loadouts_style_sync()
        self._el_dropped("loadouts")
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _loadouts_on_changed(self) -> None:
        """The box "Loadouts der Mitspieler zeigen"; the first time a note says what is read."""
        on = bool(self.loadouts_on_var.get())
        self.settings["overlay"]["show_loadouts"] = on
        if on and not self.settings.get("loadouts_told", False):
            self.settings.set("loadouts_told", True)
            self._inform(_("Loadouts der Mitspieler"), LOADOUTS_NOTE())
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _loadouts_spot_changed(self) -> None:
        self._layout_mark()
        key = dict((_(label), k) for k, label in LOADOUT_SPOTS).get(self.loadouts_pos_var.get(), "hud")
        self.settings["overlay"]["loadouts_pos"] = key
        self._loadouts_style_sync()
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _loadouts_style_sync(self) -> None:
        """1.57.9: the box "Darstellung" shows the style drawn. 1.57.42: it can always be chosen (see
        ``_loadouts_style_changed``)."""
        box = getattr(self, "loadouts_style_cb", None)
        if box is None:
            return
        o = self.settings["overlay"]
        self.loadouts_style_var.set(_(dict(LOADOUT_STYLES)[style_of(o)]))
        box.state(["!disabled"])

    def _loadouts_style_changed(self) -> None:
        """1.57.3: the perks as a 2×2 diamond or in one row. 1.57.42 (user: "es soll sich live ändern im spiel wenn
        ich zb die option in one row zu 2x2 ändere"): beside the list only the diamond fits and below the name only
        the row (1.57.9) – the box was locked there and a pick did nothing; now the pick moves them where that style
        goes (row → below the name, diamond → beside the list), at once in the game; at a place of one's own only
        the style changes."""
        key = dict((_(label), k) for k, label in LOADOUT_STYLES).get(self.loadouts_style_var.get(), "diamond")
        o = self.settings["overlay"]
        o["loadouts_style"] = key
        spot = o.get("loadouts_pos", "hud")
        new = {"row": "name", "diamond": "hud"}[key] if spot in ("hud", "name") else spot
        if new != spot:
            self._layout_mark()
            o["loadouts_pos"] = new
            if hasattr(self, "loadouts_pos_var"):
                self.loadouts_pos_var.set(_(dict(LOADOUT_SPOTS)[new]))
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _loadouts_look_changed(self) -> None:
        """1.57.25: the slots as the menu shows them, or the perks read drawn with the program's own icons."""
        key = dict((_(label), k) for k, label in LOADOUT_LOOKS).get(self.loadouts_look_var.get(), "picture")
        self.settings["overlay"]["loadouts_look"] = key
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _loadouts_items_changed(self) -> None:
        self.settings["overlay"]["loadouts_items"] = bool(self.loadouts_items_var.get())
        self._save_soon()
        self._tick_overlay(reschedule=False)


def LOADOUTS_NOTE() -> str:        # noqa: N802 – a text, translated when asked for
    return _("Als Survivor zeigt Dead by Daylight im Pausenmenü (Esc), was die anderen Survivor mitnehmen. Fog "
             "Scout liest das nur aus dem Bild, solange das Menü offen ist (ein paar Blicke je Runde), und zeigt die "
             "Perks danach als Raute neben jedem Mitspieler – Item und Add-ons auf Wunsch daneben. Als Killer zeigt "
             "das Menü nur die Opfergaben der Survivor – die stehen dann neben ihnen. Nichts wird gespeichert oder gesendet; Spielernamen liest es nur, um gleich aussehende "
             "Survivor auseinanderzuhalten, und nur im Arbeitsspeicher. Einmal kurz Esc drücken reicht.")
