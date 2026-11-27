"""The overlay element "Diagramme" (1.57.73): the charts the user picked (charts.CATALOGUE, setting overlay.charts) as
one card in a black bar – stacked like "Heute" and the music (layout.place_cards, the same for the preview). Shown
while the map is (like "Heute"): never in the lobby, where the worker reads the bloodpoints at the right edge of an
ultrawide window and would black out the card over them.

Data only from what the program keeps anyway (charts.py says which); drawn again only when a chart's values, the
width or the look changed – the overlay tick asks 4×/s and gets the same picture back.

Mixin of App (app.py) – the methods use App's attributes. Imports no other mixin (tests/test_mixins.py)."""
from __future__ import annotations

import logging
import time

from . import charts, history, layout
from .appconst import CHART_SPOTS
from .capture import IS_WIN
from .i18n import _

log = logging.getLogger("fogscout")

CHART_SCALE, CHART_WIDTH, chart_scale = charts.CHART_SCALE, charts.CHART_WIDTH, charts.chart_scale   # re-exported


def card_width(o: dict, gh: int, avail: float) -> int:
    """The card's width: its size setting, never wider than the room (``avail``) – never from the values."""
    return max(60, int(min(gh * CHART_WIDTH * chart_scale(o), avail)))


def picture(o: dict, items, gh: int, avail: float, accent, editing: bool = False):
    """The card of ``items`` (charts.Chart) for a game ``gh`` px tall in ``avail`` px of room (App and preview)."""
    from .overlay_render import add_border
    from .skin import accent_rgba
    pic = charts.draw(items, card_width(o, gh, avail), look_of(o, accent_rgba(accent)))
    return add_border(pic, _("DIAGRAMME")) if editing else pic


def look_of(o: dict, accent) -> charts.Look:
    """The look the settings ask for (overlay.charts_look / charts_dense / charts_backdrop)."""
    style = o.get("charts_look", "classic")
    return charts.Look(accent, bool(o.get("charts_backdrop", True)), style if style in charts.LOOKS else "classic",
                       bool(o.get("charts_dense", False)))


def samples(o: dict) -> list:
    """The charts picked, with made-up values (preview, "Overlay testen", moving)."""
    return [charts.sample(c) for c in charts.picked(o)]


class ChartsCard:
    def _charts_init(self):
        self.charts_win = None
        self._charts_sys = charts.SystemHistory()
        self._charts_cache = None            # (key, [Chart]) of the charts built from the history (once a minute)
        self._charts_box = None
        if IS_WIN:
            try:
                from .overlay_win32 import HudWindow
                self.charts_win = HudWindow("Fog Scout Diagramme")
            except Exception as e:
                log.warning("Diagramme-Fenster nicht verfügbar: %s", e)
        if self.charts_win is not None:
            self.charts_win.on_moved = lambda x, y: self.events.put(("call", self._charts_dragged, (x, y)))
            self.charts_win.on_reset = lambda: self.events.put(("call", self._el_reset, ("charts",)))
            self.charts_win.on_menu = lambda: self.events.put(("call", self._game_menu, ("charts",)))
            self._edit_comfort("charts", self.charts_win)
            self.charts_win.edit_label = _("DIAGRAMME")

    def _charts_on(self) -> bool:
        return bool(self.settings["overlay"].get("show_charts", False))

    # ---- the values
    def _charts_role(self) -> str:
        return (self._hist or {}).get("role") or (self._queue or {}).get("role") or ""

    def _charts_from_history(self, now: float) -> dict:
        """The charts built from the rounds and the stats page's matches – once a minute, or when the joined data,
        the round's map or role changed (a full pass over thousands of rounds is too much for every tick)."""
        j = self._joined()
        hist = self._hist or {}
        key = (id(j), hist.get("map_id"), self._charts_role(), int(now // 60), bool(hist))
        if self._charts_cache is not None and self._charts_cache[0] == key:
            return self._charts_cache[1]
        rounds, off = j.rounds, j.off
        today = charts.today_outcomes(rounds, off, now)
        role = self._charts_role()
        recent = sorted((r for r in rounds if history.normal(r)), key=lambda r: r.t)[-charts.FORM_N:]
        form = [charts.outcome(r.role, *((None, None) if off.get(id(r)) is None else
                                         _match_result(off[id(r)]))) for r in recent]
        mid = hist.get("map_id")
        on_map = [r for r in rounds if mid and r.map_id == mid and history.normal(r)
                  and (r.role == role or not role)]
        map_role = role or (on_map[-1].role if on_map else "killer")
        results = [(_match_result(off[id(r)])[1] if map_role == "survivor" else _match_result(off[id(r)])[0])
                   for r in on_map if off.get(id(r)) is not None and r.role == map_role]
        times = [r.seconds for r in on_map if r.seconds >= 60]
        since = history.period_start("day", now)
        out = {"kills": charts.kills_chart([k for role_r, k, _e in today if role_r == "killer"]),
               "form": charts.form_chart(form),
               "map": charts.map_chart(map_role, results),
               "wait": charts.wait_chart([r.wait for r in sorted(rounds, key=lambda r: r.t)
                                          if r.t >= since and history.normal(r) and r.wait is not None]),
               "_avg": (sum(times) / len(times)) if times else None}
        self._charts_cache = (key, out)
        return out

    def _charts_items(self, now: float) -> list:
        """The charts picked, with the values of now."""
        o = self.settings["overlay"]
        ids = charts.picked(o)
        if not ids:
            return []
        if any(c in charts.SYSTEM for c in ids):
            self._charts_sys.add(self.sysmon.snapshot)
        past = self._charts_from_history(now) if any(c in ("kills", "form", "map", "wait", "time") for c in ids) \
            else {}
        hist = self._hist or {}
        out = []
        for cid in ids:
            if cid == "ping":
                out.append(charts.ping_chart(hist.get("pings") or ()))
            elif cid == "score":
                out.append(charts.score_chart(getattr(self, "_score_now", None) or {}, self._charts_role()))
            elif cid == "time":
                out.append(charts.time_chart(now - hist["t"] if hist.get("t") else None, past.get("_avg")))
            elif cid == "bp":
                out.append(charts.bp_chart(self.bloodpoints.balance))
            elif cid in charts.SYSTEM:
                out.append(charts.system_chart(cid, self._charts_sys.values(cid)))
            else:
                out.append(past[cid])
        return out

    # ---- drawing (asked by _cards_measure every overlay tick)
    def _charts_card(self):
        """The card for this tick: its size, or None (hidden) – placed by _cards_place like "Heute"."""
        o = self.settings["overlay"]
        win = self.charts_win
        if win is None:
            return None
        on = self._charts_on()
        editing = on and self.overlay.editing
        win.set_editing(editing and not self._el_locked("charts"))
        spot = o.get("charts_pos", "under_music")
        gx, gy, gw, gh, show = self._media_ctx or (0, 0, 0, 0, False)
        bar = layout.bar_width(gw, gh) if gh else 0
        forced = getattr(self, "_forced", False)
        fade = bool(o.get("fade", True)) and not editing
        possible = bool(self._media_ctx and (show or editing) and (self.game is not None or editing or forced)
                        and (bar >= layout.MIN_BAR or spot == "custom" or editing))
        sample = editing or (forced and self._hist is None)
        items = (samples(o) if sample else self._charts_items(time.time())) if on and possible else []
        if not items:
            self._fade_hide("charts", fade)
            self.worker.charts_rect = None
            self._charts_box = None
            return None
        margin = int(gh * o["margin"])
        avail = layout.max_width(bar, margin) if bar >= layout.MIN_BAR and spot != "custom" else gw / 3
        accent = self._skin_accent()
        key = (tuple(items), card_width(o, gh, avail), look_of(o, accent), win.editing)
        if key != getattr(win, "_key", None):
            win.set_picture(picture(o, items, gh, avail, accent, win.editing), key)
        win.opacity = o.get("charts_opacity", o["opacity"])
        return win.size

    # ---- settings and dragging
    def _charts_dragged(self, x, y) -> None:
        self._layout_mark()
        gx, gy, gw, gh = self._game_rect()
        self._charts_own_place(*layout.media_own(gw, gh, self.charts_win.size, x - gx, y - gy))

    def _charts_own_place(self, fx, fy) -> None:
        """Dragged in the preview or the game: its own place (its centre, share of the window)."""
        o = self.settings["overlay"]
        o["charts_xy"], o["charts_pos"] = [fx, fy], "custom"
        if hasattr(self, "charts_pos_var"):
            self.charts_pos_var.set(_(dict(CHART_SPOTS)["custom"]))
        self._el_dropped("charts")
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _charts_on_changed(self) -> None:
        self.settings["overlay"]["show_charts"] = bool(self.charts_on_var.get())
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _charts_spot_changed(self) -> None:
        self._layout_mark()
        key = dict((_(label), k) for k, label in CHART_SPOTS).get(self.charts_pos_var.get(), "under_music")
        self.settings["overlay"]["charts_pos"] = key
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _charts_pick_changed(self, cid: str | None = None) -> None:
        """A box of the catalogue (``cid`` the one clicked): the charts switched on, in catalogue order – at most
        charts.MAX_PICKED; the box beyond that is switched off again and the log says why."""
        want = [c for c in charts.IDS if self.chart_vars[c].get()]
        if len(want) > charts.MAX_PICKED:
            drop = cid if cid in want else want[-1]
            self.chart_vars[drop].set(False)
            want.remove(drop)
            self._log(_("Höchstens {n} Diagramme auf einmal – mehr passt nicht in den Balken.",
                        n=charts.MAX_PICKED), "Overlay")
        self.settings["overlay"]["charts"] = want
        self._charts_cache = None
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _charts_look_changed(self) -> None:
        """1.57.74: the look (classic / map table / glass / line) and the density (normal / one row per chart)."""
        from .appconst import CHART_DENSITIES, CHART_LOOKS
        o = self.settings["overlay"]
        o["charts_look"] = dict((_(label), k) for k, label in CHART_LOOKS).get(self.charts_look_var.get(), "classic")
        o["charts_dense"] = dict((_(label), k) for k, label in CHART_DENSITIES).get(self.charts_dense_var.get(),
                                                                                    "normal") == "dense"
        self._save_soon()
        self._tick_overlay(reschedule=False)

    def _charts_backdrop_changed(self) -> None:
        self.settings["overlay"]["charts_backdrop"] = bool(self.charts_backdrop_var.get())
        self._save_soon()
        self._tick_overlay(reschedule=False)


def _match_result(m) -> tuple:
    """(kills, escaped) of a stats-page match."""
    from . import official
    return official.kills(m), official.escaped(m)
