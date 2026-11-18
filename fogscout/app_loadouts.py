"""The overlay element "Loadouts" (1.57, user: "Man sieht seit paar Monaten neu, was jeder Survivor mitnimmt, wenn
man ins Menü geht. Wäre es möglich, die Perks so anzeigen zu lassen links vom entsprechenden Spieler?" – Killer
sehen es nicht): the other survivors' perks (and item, add-ons) as DBD's 2×2 perk diamond beside each of them in
the HUD's survivor list. Read by the worker from the pause menu (loadouts.Reader, only the screen picture, only
while the menu is open, a few looks per round, never as the killer); drawn by overlay_render.loadout_card; placed
by layout.loadouts_xy (shared with the preview).

Mixin of App (app.py) – the methods use App's attributes. Imports no other mixin (tests/test_mixins.py)."""
from __future__ import annotations

import logging

from . import layout, loadouts
from .appconst import LOADOUT_SPOTS
from .capture import IS_WIN
from .i18n import _

log = logging.getLogger("fogscout")

# what the preview and "Overlay testen" show (made up; names of the wiki's survivor perks) – at the list's usual rows
SAMPLE = loadouts.Board(rows=(
    loadouts.Row(own=True),
    loadouts.Row(perks=("Dead Hard", "Resurgence", "Made for This", "Windows of Opportunity"),
                 item="Emergency Med-Kit", addons=("Gel Dressings", None)),
    loadouts.Row(perks=("Sprint Burst", None, "We'll Make It", "Resilience")),
    loadouts.Row(perks=("Sprint Burst", "Vigil", "Resilience", "Finesse"), item="Utility Flashlight",
                 addons=("Long Life Battery", "Odd Bulb"))))


def icon_for(name, kind):
    """The picture file of a name the reader gave (overlay_render.loadout_card's ``icon``)."""
    return loadouts.icon_file(name, kind) if name else None


def placed(o: dict, game, board, editing: bool = False, sample: bool = False):
    """(picture, x, y) of the loadouts in the game window ``game`` (also the preview's), or None. Live (not
    ``sample``) only the rows whose portrait the worker found in the HUD – beside it; the sample at the list's
    usual rows."""
    if board is None:
        return None
    rows = [r for r in board.others if sample or r.hud]
    if not rows:
        return None
    from .overlay_render import add_border, loadout_card
    gx, gy, gw, gh = game
    cluster, centres, left = layout.loadout_rows(o, game, rows)
    top = centres[0][1] - cluster / 2
    height = int(round(centres[-1][1] - top + cluster / 2))
    pic = loadout_card([r for r, _c in centres], cluster, [c - cluster / 2 - top for _r, c in centres], height,
                       bool(o.get("loadouts_items", True)), icon_for)
    if editing:
        pic = add_border(pic, _("LOADOUTS"))
    x, y = layout.loadouts_xy(o.get("loadouts_pos", "hud"), game, pic.size, int(gh * o.get("margin", 0.012)), top,
                              o.get("loadouts_xy"), left)
    return pic, x, y


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
        """The round is the killer's (lobby or round said so): DBD shows no loadouts then – nothing is read."""
        role = (getattr(self, "_hist", None) or {}).get("role") or (getattr(self, "_queue", None) or {}).get("role")
        return role == "killer"

    def _loadouts_want(self) -> None:
        """Tell the worker whether to look at the pause menu (the element on, a round of a survivor or unknown)."""
        self.worker.loadouts_wanted = self._loadouts_on() and not self._loadouts_killer()

    def _loadouts_event(self, d: dict) -> None:
        """The worker read (more of) the board of the round on display."""
        if d.get("gen") != self.worker.watch_gen:
            return                                   # about a map no longer on display
        board = d.get("board")
        first = self._loadout_board is None
        self._loadout_board, self._loadout_gen = board, d.get("gen")
        if first and board is not None:
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
        if (board is None or self._loadouts_killer() or self.menu_paused or self.hidden_after_match
                or not self.overlay.has_map() or not self.user_visible):
            return None, False
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
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _loadouts_items_changed(self) -> None:
        self.settings["overlay"]["loadouts_items"] = bool(self.loadouts_items_var.get())
        self._save_soon()
        self._tick_overlay(reschedule=False)


def LOADOUTS_NOTE() -> str:        # noqa: N802 – a text, translated when asked for
    return _("Als Survivor zeigt Dead by Daylight im Pausenmenü (Esc), was die anderen Survivor mitnehmen. Fog "
             "Scout liest das nur aus dem Bild, solange das Menü offen ist (ein paar Blicke je Runde), und zeigt die "
             "Perks danach als Raute neben jedem Mitspieler – Item und Add-ons auf Wunsch daneben. Als Killer wird "
             "nichts gelesen. Nichts wird gespeichert oder gesendet, keine Namen. Einmal kurz Esc drücken reicht.")
