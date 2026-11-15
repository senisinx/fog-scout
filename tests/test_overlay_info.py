"""Timer/server block below the map in the native overlay picture."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from fogscout import overlay_win32 as ow  # noqa: E402


def map_pic(w=300, h=400, empty_bottom=0):
    pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pic.paste((140, 147, 232, 255), (20, 20, w - 20, h - empty_bottom))
    return pic


def visible_rows(img, y0, y1):
    a = img.getchannel("A").crop((0, y0, img.width, y1))
    return a.getbbox() is not None


def test_nothing_to_show_keeps_picture():
    pic = map_pic()
    assert ow.add_info(pic, "", "", 400) is pic


def test_block_below_map_and_centred():
    pic = map_pic()
    out = ow.add_info(pic, "07:32", "Frankfurt", 400)
    assert out.width == pic.width and out.height > pic.height
    assert visible_rows(out, pic.height, out.height)                 # text below the map
    box = out.crop((0, pic.height, out.width, out.height)).getbbox()
    left, right = box[0], out.width - box[2]
    assert abs(left - right) <= 12                                    # centred


def test_uses_empty_margin_below_the_map():
    pic = map_pic(empty_bottom=150)                                   # map content ends 150 px above the edge
    out = ow.add_info(pic, "07:32", "", 400)
    assert out.height == pic.height                                   # fits into the empty margin
    assert visible_rows(out, 400 - 150, 400)


def test_backdrop_mode_extends_dark_rectangle():
    pic = map_pic()
    out = ow.add_info(pic, "07:32", "Irland", 400, backdrop=True)
    assert out.getpixel((2, out.height - 2)) == ow.BACKDROP + (255,)
    assert ow.add_info(pic, "07:32", "Irland", 400).getpixel((2, out.height - 2))[3] == 0


def test_ping_row_below_server_and_coloured():
    pic = map_pic()
    without = ow.add_info(pic, "07:32", "Frankfurt", 400)
    with_ping = ow.add_info(pic, "07:32", "Frankfurt", 400, ping=23)
    assert with_ping.height > without.height                         # extra row below the region
    assert ow.add_info(pic, "07:32", "", 400, ping=23).height == ow.add_info(pic, "07:32", "", 400).height
    assert ow.ping_colour(23) == ow.PING_COLOURS[0]
    assert ow.ping_colour(95) == ow.PING_COLOURS[1]
    assert ow.ping_colour(180) == ow.PING_COLOURS[2]
    green = ow.PING_COLOURS[0][:3]
    rows = with_ping.crop((0, without.height - 10, with_ping.width, with_ping.height)).convert("RGB")
    assert green in {c for _, c in rows.getcolors(1 << 20)}           # value drawn in its quality colour


def test_program_icon(tmp_path):
    from fogscout.icon import SIZES, draw, save_ico
    path = tmp_path / "x.ico"
    save_ico(str(path))
    ico = Image.open(path)
    assert sorted(ico.info["sizes"]) == [(n, n) for n in SIZES]
    small = draw(16)
    assert small.size == (16, 16) and small.getpixel((8, 8))[3] == 255     # visible even at 16 px


def test_waiting_card_lines():
    """No map on screen: only the status lines, on an empty picture, wide enough to read."""
    empty = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    one = ow.add_info(empty, "", "", 500, status=["Warte auf Map"])
    two = ow.add_info(empty, "", "", 500, status=["Warte auf Map", "Suche läuft: 02:13 · Nurse"])
    assert one.width > 100 and two.height > one.height and two.width >= one.width
    assert two.getchannel("A").getextrema()[1] > 200                    # white text is drawn
    assert ow.add_info(empty, "", "", 500, status=()) is empty
    boxed = ow.add_info(empty, "", "", 500, status=["Warte auf Map"], backdrop=True)
    assert boxed.getpixel((1, 1))[3] == 255                             # dark box when the edge is not transparent


def test_waiting_card_shows_the_server_below_the_status():
    """In the lobby DBD already talks to the match server: region and ping go below "Warte auf Map"."""
    empty = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    status = ["Warte auf Map", "Rolle: Nurse · Wartezeit 03:10"]
    plain = ow.add_info(empty, "", "", 500, status=status)
    with_server = ow.add_info(empty, "", "Frankfurt", 500, ping=24, status=status)
    assert with_server.height > plain.height
    top = with_server.crop((0, 0, with_server.width, plain.height - 10))
    assert top.getchannel("A").getextrema()[1] > 200                   # status rows still at the top


def test_warning_note_below_the_timer():
    pic = map_pic()
    plain = ow.add_info(pic, "07:32", "", 400)
    noted = ow.add_info(pic, "07:32", "", 400, note="? unsicher")
    assert noted.height > plain.height
    assert ow.add_info(pic, "", "", 400, note="? unsicher").height > pic.height     # a note alone is shown too


def test_a_map_in_the_bar_is_put_on_screen_once_per_change_at_its_final_size():
    """User (1.2.2): "die Map hat sich ständig vergrössert und verkleinert" – the timer line at full text size is
    wider than the 406-px bar; the App rendered it big, pushed it, then rendered smaller: two sizes on every tick."""
    pushes = []

    class Root:
        def after(self, *a):
            return None

        def after_cancel(self, *a):
            pass

    class Overlay(ow.PictureOverlay):
        def _push(self, *a):
            pushes.append(self._size)

    ov = Overlay(Root())
    ov._shown = True
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ov.set_map(os.path.join(root, "maps", "Forsaken Boneyard", "Eyrie of Crows.webp"), "")
    ov.set_server("Frankfurt", 28)
    ov.set_record("Ø 2.8 Kills · 12 Runden")
    widths = set()
    for s in range(55, 65):                       # "0:59" → "1:00": other digits, other widths
        ov.set_timer(f"{s // 60}:{s % 60:02d}")
        for _tick in range(4):                    # the App places the overlay 4× a second
            height = ov.fit_width(470, 518, 406)
            w, _h = ov.render(height)
            widths.add(w)
    assert len(widths) == 1 and max(widths) <= 406     # never wider than the bar (1.8.24: the map cut to what is
    assert len(pushes) == 10                      # drawn – it may stay a few px narrower); once per timer text,
    assert {w for w, _h in pushes} == widths      # never an in-between size


def test_dark_area_behind_the_map_fits_the_bar_and_keeps_every_frame_the_same_size():
    """1.2.4 (user: "einen Hintergrund dahinter, z. B. bei der Map – als Option für jedes UI-Element")."""
    class Root:
        def after(self, *a):
            return None

        def after_cancel(self, *a):
            pass

    class Overlay(ow.PictureOverlay):
        def _push(self, *a):
            pass

    ov = Overlay(Root())
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ov.set_map(os.path.join(root, "maps", "Forsaken Boneyard", "Eyrie of Crows.webp"), "")
    ov.set_timer("1:23")
    plain = ov.render(ov.fit_width(470, 518, 406))
    ov.set_backdrop(True)
    w, h = ov.render(ov.fit_width(470, 518, 406))
    assert w <= 406 and (w, h) != plain
    pic = ov._prepared[0]
    corner = pic[0][:4]                                  # BGRA of the top left pixel: rounded corner, see-through
    assert corner[3] == 0
    middle_left = (pic[2] // 2 * pic[1]) * 4             # left edge, half way down: the frame (1.2.20) …
    assert pic[0][middle_left + 3] == ow.CARD_EDGE[3]
    inside = (pic[2] // 2 * pic[1] + 6) * 4              # … and the dark area right behind it
    assert pic[0][inside + 3] == ow.CARD_BACKDROP[3]
    frames = [Image.new("RGBA", (100, 80), (0, 0, 0, 0)) for _i in range(2)]
    frames[0].paste((200, 200, 200, 255), (10, 10, 50, 50))
    frames[1].paste((200, 200, 200, 255), (40, 30, 90, 70))
    out = ow.map_backdrop(frames, 400)
    assert out[0].size == out[1].size == (80 + 2 * (400 // 45), 60 + 2 * (400 // 45))   # union of both, padded


def test_the_dark_area_does_not_make_the_map_smaller():
    """1.2.5 (user: "Warum wird die Map kleiner?"): the area's edge may use the margin around the map."""
    class Root:
        def after(self, *a):
            return None

        def after_cancel(self, *a):
            pass

    class Overlay(ow.PictureOverlay):
        def _push(self, *a):
            pass

    ov = Overlay(Root())
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ov.set_map(os.path.join(root, "maps", "Forsaken Boneyard", "Eyrie of Crows.webp"), "")
    ov.set_timer("1:23")
    from fogscout import layout
    height = layout.fit_height(470, 406, *ov.map_size())           # the map alone fits the bar (as the App does)
    plain_h = ov.fit_width(height, 518, 406)
    ov.set_backdrop(True)
    edge = ov.backdrop_pad(518)
    assert 0 < edge < 17                                           # fits into the 17-px margin of 1440p
    boxed_h = ov.fit_width(height, 518, 406 + 2 * edge)
    assert boxed_h == plain_h and ov.render(boxed_h)[0] <= 406 + 2 * edge


def test_more_room_below_the_timer_than_between_the_small_lines():
    """1.2.7 (user's screenshot): the lines sat right under the big timer digits."""
    import numpy as np
    pic = map_pic()
    out = ow.add_info(pic, "02:36", "Global", 518, record="40% Escaped · 5 Rounds")
    a = np.asarray(out.getchannel("A"))[pic.height:]
    rows = np.flatnonzero((a > 200).any(axis=1))           # rows with solid text (not the soft shadow)
    gaps = np.diff(rows)
    big = sorted(gaps[gaps > 1])
    assert len(big) >= 2 and big[-1] >= 2 * big[-2]        # the gap after the timer is the clearly largest one


def test_a_big_text_with_the_dark_area_still_fits_the_bar():
    """1.2.10 (combination sweep: 12 maps at text 160 % with the dark area were 1–4 px too wide): the area's edge
    does not scale – the map makes room for it and the text shrinks with the edge taken out."""
    class Root:
        def after(self, *a):
            return None

        def after_cancel(self, *a):
            pass

    class Overlay(ow.PictureOverlay):
        def _push(self, *a):
            pass

    ov = Overlay(Root())
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ov.set_map(os.path.join(root, "maps", "Azarovs", "Gas Heaven.webp"), "")
    ov.set_timer("0:59")
    ov.set_server("Frankfurt", 28)
    ov.set_record("Ø 2.8 Kills · 12 Runden")
    ov.set_backdrop(True)
    from fogscout import layout
    text_h = int(1440 * 0.36 * 1.6)
    edge = min(ov.backdrop_pad(text_h), 17 - 2)
    height = layout.fit_height(518, 406, *ov.map_size())
    h = ov.fit_width(height, text_h, 406 + 2 * edge)
    assert ov.render(h)[0] <= 406 + 2 * edge and ov.text_height >= 40


def test_every_drawing_name_is_still_importable_from_overlay_win32():
    """1.38.34 (Phase 5, ARCH-3): the drawing moved to overlay_render; old imports from overlay_win32 keep working –
    the same objects (the glyph cache is shared, not copied)."""
    import ast
    import os
    from fogscout import overlay_render, overlay_win32
    src = open(os.path.join(os.path.dirname(overlay_render.__file__), "overlay_render.py"), encoding="utf-8").read()
    names = set()
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    missing = [n for n in sorted(names) if getattr(overlay_win32, n, None) is not getattr(overlay_render, n)]
    assert missing == []
    assert overlay_win32._GLYPHS is overlay_render._GLYPHS and overlay_win32.BACKDROP == overlay_render.BACKDROP


def _bare_overlay(pushes):
    class Root:
        def after(self, *a):
            return None

        def after_cancel(self, *a):
            pass

    class Overlay(ow.PictureOverlay):
        def _push(self, *a):
            pushes.append(self._size)

    return Overlay(Root())


def test_the_waiting_card_fits_by_its_own_lines_whatever_was_measured_before():
    """1.56 (audit B3): the waiting lines were not part of fit_width's key – "Warte auf Map" alone measured first,
    the lobby line then reused that fit (classic: 768 px in a 406 px bar), and the long line measured first left
    the short card tiny. Each card now measures the same as on a fresh overlay; the long lobby line (wider than the
    bar even at the smallest font) settles on the largest text at that narrowest width."""
    short = ["Warte auf Map"]
    long = ["Warte auf Map", "Suche läuft: 00:05 · Farming · Krankenschwester"]

    def fit(ov, lines, avail):
        ov.set_waiting(lines)
        h = ov.fit_width(518, 518, avail)
        w, _h = ov.render(ov.fit_room(h, 1400))
        return w, ov.text_height

    for skin, avail in (("classic", 406), ("glass", 436)):
        fresh = {}
        for lines in (short, long):
            ov = _bare_overlay([])
            ov.set_skin(skin, "#c9a227")
            fresh[len(lines)] = fit(ov, lines, avail)
        for order in ((short, long, short), (long, short, long)):
            ov = _bare_overlay([])
            ov.set_skin(skin, "#c9a227")
            for lines in order:
                assert fit(ov, lines, avail) == fresh[len(lines)], (skin, lines)
        assert fresh[1] == (fresh[1][0], 518) and fresh[1][0] <= avail      # the short card keeps its text size
        w, text_h = fresh[2]
        if w > avail:                                   # classic: no text height fits – the narrowest, largest
            ov = _bare_overlay([])
            ov.set_skin(skin, "#c9a227")
            ov.set_waiting(long)
            ov.text_height = 40
            assert ov.render(40, push=False)[0] == w
            ov.text_height = text_h + 1
            assert ov.render(text_h + 1, push=False)[0] > w
        else:                                           # it fits: at the largest text that does (fonts differ
            assert text_h <= 518                        # per system – on Windows glass fits even at 518)
            if text_h < 518:
                ov = _bare_overlay([])
                ov.set_skin(skin, "#c9a227")
                ov.set_waiting(long)
                ov.text_height = text_h + 1
                assert ov.render(text_h + 1, push=False)[0] > avail, (skin, text_h)


def test_the_waiting_card_is_measured_off_screen_and_shown_once():
    """1.56: _render_waiting pushed every size fit_width tried while the card was on screen."""
    pushes = []
    ov = _bare_overlay(pushes)
    ov._shown = True
    ov.set_waiting(["Warte auf Map", "Suche läuft: 00:05 · Farming · Krankenschwester"])
    ov.render(ov.fit_width(518, 518, 406))
    assert pushes == [ov._size]
    ov.render(ov.fit_width(518, 518, 406))           # the next tick: nothing new
    assert pushes == [ov._size]


def test_a_card_shown_again_after_a_fade_out_is_pushed_at_full_opacity(monkeypatch):
    """1.56 (audit B4): HudWindow.show_at pushed only when (x, y, opacity) changed – the fade was not in it. After a
    fade-out (_fade_tick: hide(), set_fade(1.0) – no push while hidden) the card came back at the same place with
    the surface still at opacity 0: invisible. Window calls stubbed, the pushes recorded."""
    import ctypes

    class Calls:
        def __getattr__(self, name):
            return lambda *a, **k: 1

    for name in ("_u", "_g", "_k"):
        monkeypatch.setattr(ow, name, Calls(), raising=False)
    monkeypatch.setattr(ow, "WNDPROC", ctypes.CFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
                                                        ctypes.c_size_t, ctypes.c_ssize_t), raising=False)
    monkeypatch.setattr(ow, "_SetLong", lambda *a: 0, raising=False)
    monkeypatch.setattr(ow, "_GetLong", lambda *a: 0, raising=False)
    monkeypatch.setattr(ow, "HWND_TOPMOST", -1, raising=False)
    pushed = []
    monkeypatch.setattr(ow.LayeredSurface, "push",
                        lambda self, hwnd, data, w, h, pos, opacity: pushed.append(round(opacity, 3)) or "")
    win = ow.HudWindow("test")
    win.opacity = 0.85
    rows = [[("HEUTE ", (150, 156, 170, 255)), ("3 RUNDEN", (255, 255, 255, 255))]]
    win.render(rows, 1440)
    win.show_at(100, 100)
    assert pushed == [0.85]
    for fade in (0.6, 0.3, 0.0):                      # what _fade_tick does while fading out …
        win.set_fade(fade)
        win.show_at(100, 100)                         # (a tick in between: nothing new to push)
    win.hide()                                        # … and at its end
    win.set_fade(1.0)
    assert pushed == [0.85, 0.51, 0.255, 0.0] and not win.shown
    win.render(rows, 1440)
    win.show_at(100, 100)                             # shown again at the same place, no fading
    assert pushed[-1] == 0.85 and win.shown


def test_the_still_up_next_block_is_drawn_once_and_stays_pixel_identical():
    """1.56 (audit P2): the classic music card is redrawn every second and drew the unchanged "Als nächstes" block
    each time (~1.8 ms, twice beside the card). The still block is kept by its inputs – the same pixels as drawn
    anew; a sliding block (song change) is always drawn."""
    from fogscout import overlay_render as orr
    items = [["Save Your Tears", "The Weeknd"], ("Levitating", "Dua Lipa")]
    a = ow.upnext_block("ALS NÄCHSTES", items, 1440)
    b = ow.upnext_block("ALS NÄCHSTES", [tuple(i) for i in items], 1440)
    assert a is b and a.tobytes() == orr._upnext_draw("ALS NÄCHSTES", items, 1440).tobytes()
    assert ow.upnext_block("ALS NÄCHSTES", items[:1], 1440) is not a
    moving = ow.upnext_block("ALS NÄCHSTES", items, 1440, (("Blinding Lights", "The Weeknd"), 0.5))
    assert moving is not a and moving.size == a.size
    assert ow.upnext_block("ALS NÄCHSTES", items, 1440, (("Blinding Lights", "The Weeknd"), 0.5)) is not moving
