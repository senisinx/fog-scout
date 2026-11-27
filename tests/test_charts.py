"""1.57.73: the overlay element "Diagramme" – the catalogue, the series, the drawing (never breathes), the preview and
the App placing it like "Heute" (in a bar, on nothing else)."""
import os
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fogscout import charts, layout  # noqa: E402
from fogscout.config import DEFAULTS  # noqa: E402

WHOLE_APP = pytest.mark.skipif(sys.platform == "win32", reason="Linux: the Windows job tests the native parts")


def test_the_picked_charts_are_known_in_catalogue_order_and_limited():
    assert charts.picked({}) == charts.DEFAULT == DEFAULTS["overlay"]["charts"]
    assert charts.picked({"charts": ["kills", "nonsense", 3, "ping"]}) == ["ping", "kills"]
    assert charts.picked({"charts": "ping"}) == charts.DEFAULT           # a broken value: the defaults
    assert len(charts.picked({"charts": list(charts.IDS)})) == charts.MAX_PICKED
    assert charts.picked({"charts": []}) == []


def test_only_a_system_chart_switched_on_needs_the_monitor():
    assert not charts.needs_system({"show_charts": True, "charts": ["ping"]})
    assert not charts.needs_system({"show_charts": False, "charts": ["fps"]})
    assert charts.needs_system({"show_charts": True, "charts": ["ping", "gpu"]})


def test_the_chart_caps_match_the_readers():
    from fogscout import bloodpoints, scorecount, scoreevents
    assert charts.BP_CAP == bloodpoints.CAP and charts.SCORE_CAP == scorecount.CAP
    assert charts.KILLER_CATS == scoreevents.KILLER and charts.SURVIVOR_CATS == scoreevents.SURVIVOR


def test_a_card_never_breathes_whatever_its_values():
    """The same charts are the same size with values, without and with other values (a round fills them)."""
    for cid in charts.IDS:
        full = charts.sample(cid)
        empty = {"ping": charts.ping_chart(()), "score": charts.score_chart({}, ""), "time": charts.time_chart(None, None),
                 "kills": charts.kills_chart(()), "form": charts.form_chart(()), "map": charts.map_chart("killer", ()),
                 "wait": charts.wait_chart(()), "bp": charts.bp_chart(None), "fps": charts.system_chart("fps", ()),
                 "gpu": charts.system_chart("gpu", ()), "cpu": charts.system_chart("cpu", ())}[cid]
        assert full.kind == empty.kind and empty.value == "–", cid
        assert charts.draw([full], 240).size == charts.draw([empty], 240).size == charts.card_size([full.kind], 240)
    pings = charts.ping_chart([30] * 5)
    spike = charts.ping_chart([30, 30, 300, 30, 30])
    assert charts.draw([pings], 240).size == charts.draw([spike], 240).size and spike.hi == 320


def test_the_series_say_what_the_round_and_the_day_hold():
    assert charts.buckets(range(100), 10) == tuple(i * 10 + 4.5 for i in range(10))
    assert charts.buckets([1, None, float("nan"), 2]) == (1.0, 2.0)
    p = charts.ping_chart([28, 30, 63, 29])
    assert (p.lo, p.hi, p.value) == (0, 80, "29 ms") and p.data[-1] == 29
    k = charts.kills_chart([3, 4, None, 2])
    assert k.data == (3, 4, 2) and k.value == "Ø 3,0"
    s = charts.score_chart({"objective": 4000, "boldness": 12000, "x": True}, "")
    assert s.data == (4000, 0, 0, 10000) and s.labels[0] == "Ziel"        # survivor side, capped at a full one
    assert charts.score_chart({"objective": 1}, "killer").labels[0] == "Brutalität"   # the role decides
    assert [charts.outcome("killer", k) for k in (4, 3, 2, 1)] == ["W", "W", "D", "L"]
    assert (charts.outcome("survivor", escaped=True), charts.outcome("survivor", escaped=False),
            charts.outcome("killer")) == ("W", "L", "?")
    f = charts.form_chart("WWLWD?WWWWLW")
    assert f.data == tuple("LWD?WWWWLW") and f.value == "6 von 9"
    m = charts.map_chart("killer", [0, 4, 4, 3, None])
    assert m.data == (1, 0, 0, 1, 2) and m.value == "4 Runden"
    assert charts.map_chart("survivor", [True, False, True]).data == (1, 2)
    assert charts.bp_chart(6_000_000).data == (5_000_000.0,) and charts.bp_chart(6_000_000).value == "6 000 000"
    assert charts.time_chart(134, 612).value == "2:14" and charts.time_chart(134, 612).data == (134, 612)


def test_the_system_history_keeps_ten_minutes_of_new_readings():
    h = charts.SystemHistory(keep_s=60)
    snap = SimpleNamespace(t=100.0, fps=140.0, gpu_temp=60.0, cpu_load=None)
    assert h.add(snap) and not h.add(snap)                                # the same reading once
    for t in range(101, 200):
        h.add(SimpleNamespace(t=float(t), fps=float(t), gpu_temp=60.0, cpu_load=30.0))
    assert len(h.rows) == 61 and h.values("fps")[0] == 139.0 and len(h.values("cpu")) == 61
    h.clear()
    assert h.rows == []


def test_today_outcomes_are_normal_rounds_of_today_with_their_match():
    from fogscout import history
    now = time.time()
    day = history.period_start("day", now)

    def rnd(t, role, **kw):
        return history.Round(t=t, seconds=600, map_id="m", map="M", role=role, **kw)
    a, b, c, d = rnd(day + 10, "killer"), rnd(day + 20, "survivor"), rnd(day - 100, "killer"), \
        rnd(day + 30, "killer", farming=True)
    killer = SimpleNamespace(role="killer")
    import fogscout.official as official
    old_kills, old_esc = official.kills, official.escaped
    official.kills = lambda m: 3 if m is killer else None
    official.escaped = lambda m: None
    try:
        out = charts.today_outcomes([b, a, c, d], {id(a): killer}, now)
    finally:
        official.kills, official.escaped = old_kills, old_esc
    assert out == [("killer", 3, None), ("survivor", None, None)]


def test_the_preview_stacks_the_charts_in_a_bar_on_nothing_else():
    from fogscout import app_charts, preview
    o = dict(DEFAULTS["overlay"], show_charts=True, charts=["ping", "kills", "fps"])
    items = app_charts.samples(o)
    assert [c.id for c in items] == ["ping", "kills", "fps"]
    out, map_rect = preview.layers(1720, 720, o, "right", [[("CPU ", (150, 156, 170, 255)), ("50 %", (255,) * 4)]],
                                   None, None, "", {}, 0.36, None, [[("HEUTE ", (150, 156, 170, 255))]],
                                   charts=lambda gh, avail: app_charts.picture(o, items, gh, avail, None))
    boxes = {n: (x, y, img.width, img.height) for n, img, x, y in out}
    assert "charts" in boxes
    bar = layout.bar_width(1720, 720)
    x, y, w, h = boxes["charts"]
    assert x + w <= bar or x >= 1720 - bar
    for n, b in boxes.items():
        if n != "charts":
            assert not layout.boxes_overlap(boxes["charts"], b), n


@WHOLE_APP
def test_the_app_shows_the_charts_in_a_bar_and_hides_them_with_the_switch(tmp_path):
    """The App with real drawing windows: switched on, "Overlay testen" shows the card in a black bar, on no other
    element; the list's switch hides it again and the worker no longer blacks it out."""
    import json
    from fogscout import sysinfo
    from fogscout.app import App
    from test_info_apart import _DrawWin
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("maps", "models", "maps.json"):
        os.symlink(os.path.join(root, name), tmp_path / name)
    (tmp_path / "sim").mkdir()
    (tmp_path / "settings.json").write_text(json.dumps({"welcome_seen": True, "sysinfo": "right", "overlay": {
        "show_charts": True, "charts": ["ping", "score", "gpu"], "fade": False}}), encoding="utf-8")
    app = App(str(tmp_path), simulate=str(tmp_path / "sim"))
    try:
        app.info_win, app.hud = _DrawWin("INFOS"), _DrawWin("SYSTEM")
        app.today_win, app.media_win, app.charts_win = _DrawWin("HEUTE"), _DrawWin("MUSIK"), _DrawWin("DIAGRAMME")
        app._game_rect = lambda: (0, 0, 3440, 1440)
        app._force_until = time.time() + 30
        app._forced = True
        app.sysmon.snapshot = sysinfo.Snapshot(t=time.time(), cpu_load=40, gpu_temp=60, gpu_load=50)
        app.show_map("shattered-square", 1, "auto")
        for _ in range(3):
            app._place_overlay()
        win = app.charts_win
        assert win.shown and win.size[0] > 0 and app.worker.charts_rect is not None
        x, y, w, h = (*win.at, *win.size)
        bar = layout.bar_width(3440, 1440)
        assert x + w <= bar or x >= 3440 - bar
        assert 0 <= y and y + h <= 1440
        for other in (app.hud, app.today_win, app.media_win, app.info_win):
            if other.shown:
                assert not layout.boxes_overlap((x, y, w, h), (*other.at, *other.size))
        assert not layout.boxes_overlap((x, y, w, h), app._last_place)
        # live values (no test mode): the round's pings, the counted points, the GPU readings so far
        app._hist = {"t": time.time() - 90, "map_id": "shattered-square", "role": "killer", "pings": [30.0, 44.0]}
        app._score_now = {"brutality": 2500}
        items = {c.id: c for c in app._charts_items(time.time())}
        assert list(items) == ["ping", "score", "gpu"]
        assert items["ping"].value == "44 ms" and items["score"].data[0] == 2500 and items["gpu"].value == "–"
        app._hist = None
        app._el_show_switch("charts", False)
        assert app.settings["overlay"]["show_charts"] is False
        app._place_overlay()
        assert not win.shown and app.worker.charts_rect is None
    finally:
        app.quit()


def test_every_look_and_density_keeps_one_size_and_the_dense_columns_hold_their_texts():
    """1.57.74: four looks, two densities – a look never changes the size, a density has its own (one row per
    chart); in a dense row the name and the figure of every chart fit their columns (German, the longest texts)."""
    cs = [charts.sample(c) for c in charts.IDS]
    kinds = [c.kind for c in cs]
    for dense in (False, True):
        sizes = {charts.draw(cs, 245, charts.Look(style=s, dense=dense)).size for s in charts.LOOKS}
        assert sizes == {charts.card_size(kinds, 245, dense)}
    assert charts.card_size(kinds, 245, True)[1] < charts.card_size(kinds, 245)[1] / 2
    w = 245
    pad = max(3, int(w * charts.PAD))
    name_f, value_f = charts._font(int(w * 0.047), True), charts._font(int(w * 0.054), True)
    for c in cs:
        assert name_f.getlength(c.title) <= int(w * charts.DENSE_NAME), c.id
        assert value_f.getlength(c.value) <= int(w * charts.DENSE_VALUE), c.id
    assert w - 2 * pad - int(w * charts.DENSE_NAME) - int(w * charts.DENSE_VALUE) >= 30      # room for the small plot


def test_the_look_comes_from_the_settings_and_a_broken_one_is_classic():
    from fogscout import app_charts
    acc = (1, 2, 3, 255)
    assert app_charts.look_of({}, acc) == charts.Look(acc, True, "classic", False)
    assert app_charts.look_of({"charts_look": "glass", "charts_dense": True}, acc) == charts.Look(acc, True, "glass", True)
    assert app_charts.look_of({"charts_look": "nonsense"}, acc).style == "classic"
    assert charts.palette(charts.Look(style="map")).back is None and charts.palette(charts.Look(style="line")).hollow
    assert charts.palette(charts.Look(backdrop=False)).back is None


# ------------------------------------------------------------------ 1.57.75: views of the system values (sysview)
def _snaps():
    from fogscout import sysinfo
    return (sysinfo.Snapshot(t=1, fps=141, cpu_temp=75, cpu_load=63, gpu_temp=77, gpu_load=89, gpu_hot=98,
                             vram_used=5.8, vram_total=12, ram_used=21.2, ram_total=32),
            sysinfo.Snapshot(t=2, fps=96, cpu_temp=92, cpu_load=91, gpu_temp=86, gpu_load=99, gpu_hot=104,
                             vram_used=11.4, vram_total=12, ram_used=29.1, ram_total=32, throttle="thermal"),
            sysinfo.Snapshot(t=3, cpu_load=40, ram_used=10, ram_total=32))        # no NVIDIA card, no HWiNFO


def test_a_view_of_the_system_values_has_one_size_for_any_readings():
    from fogscout import sysview
    for view in sysview.VIEWS:
        sizes = {sysview.draw(view, s, h, p, 240).size
                 for s, h, p in zip(_snaps(), (sysview.sample_history(), sysview.sample_history(), None),
                                    (28.0, 47.0, None))}
        assert sizes == {sysview.size(view, 240)}, view
    assert sysview.size("compact", 240)[1] < sysview.size("meters", 240)[1] < sysview.size("curves", 240)[1]
    assert sysview.size("curves", 480) == (480, 2 * sysview.size("curves", 240)[1])


def test_the_warning_colours_follow_the_rows_thresholds():
    from fogscout import sysinfo, sysview
    assert [sysview.level("gpu", t) for t in (sysinfo.GPU_WARM - 1, sysinfo.GPU_WARM, sysinfo.GPU_HOT)] == [0, 1, 2]
    assert [sysview.level("cpu", t) for t in (sysinfo.CPU_WARM - 1, sysinfo.CPU_WARM, sysinfo.CPU_HOT)] == [0, 1, 2]
    assert [sysview.level("fps", v) for v in (141, 100, 60)] == [0, 1, 2]
    assert sysview.level("ping", None) == 0 and sysview.colour("full", 0.95) == sysview.BAD
    ok, hot, bare = _snaps()
    a, b = sysview.draw("compact", ok, None, 28, 240), sysview.draw("compact", hot, None, 47, 240)
    assert a.tobytes() != b.tobytes()


@WHOLE_APP
def test_the_app_draws_the_system_values_as_the_view_picked(tmp_path):
    """The view replaces the text rows in the same window: shown in the bar at the view's size, and back to the rows."""
    import json
    from fogscout import sysinfo, sysview
    from fogscout.app import App
    from test_info_apart import _DrawWin
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("maps", "models", "maps.json"):
        os.symlink(os.path.join(root, name), tmp_path / name)
    (tmp_path / "sim").mkdir()
    (tmp_path / "settings.json").write_text(json.dumps({"welcome_seen": True, "sysinfo": "right", "overlay": {
        "hud_view": "meters", "fade": False, "show_today": False, "show_media": False}}), encoding="utf-8")
    app = App(str(tmp_path), simulate=str(tmp_path / "sim"))
    try:
        app.info_win, app.hud = _DrawWin("INFOS"), _DrawWin("SYSTEM")
        app.today_win, app.media_win, app.charts_win = _DrawWin("HEUTE"), _DrawWin("MUSIK"), _DrawWin("DIAGRAMME")
        app._game_rect = lambda: (0, 0, 3440, 1440)
        app._force_until = time.time() + 30
        app._forced = True
        app.sysmon.snapshot = sysinfo.Snapshot(t=time.time(), cpu_load=40, gpu_temp=60, gpu_load=50)
        app.show_map("shattered-square", 1, "auto")
        for view in ("meters", "curves", "compact"):
            app.settings["overlay"]["hud_view"] = view
            app._hud_steady = None
            for _ in range(2):
                app._place_overlay()
            assert app.hud.shown and app.hud.size == sysview.size(view, int(1440 * sysview.WIDTH)), view
            x, y = app.hud.at
            assert x >= 3440 - layout.bar_width(3440, 1440) and x + app.hud.size[0] <= 3440
            assert any(n == "hud" and (w, h) == app.hud.size for n, _x, _y, w, h in app._preview_data()["layers"])
        app.settings["overlay"]["hud_view"] = "rows"
        app._hud_steady = None
        app._place_overlay()
        assert app.hud.shown and app.hud.size != sysview.size("compact", int(1440 * sysview.WIDTH))
    finally:
        app.quit()
