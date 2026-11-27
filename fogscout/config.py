"""User settings (settings.json next to the program)."""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import shutil
import time

from . import fsops

log = logging.getLogger(__name__)

HUD_SHOWN = ("above", "left", "right", "custom")    # settings.sysinfo values that show the system values
SETTINGS_VERSION = 13

DEFAULTS = {
    "settings_version": SETTINGS_VERSION,
    # languages the game may show map names in (en, de, fr, es, es-MX, it, pl, pt-BR, tr)
    "languages": ["en", "de"],
    "game_lang_auto": True,             # 1.48: a banner in a game language not ticked ticks it (gamelang.py)
    "auto_detect": True,
    "scans_per_second": 5,
    "hide_after_match": True,
    "pause_in_menus": True,             # hide the overlay while a DBD menu is open (mouse pointer visible)
    "window_capture": True,             # DBD in the background: picture via Windows Graphics Capture (like OBS)
    "show_connection": False,           # Server tab: show the connected game server (elevated netwatch helper)
    "overlay": {
        "anchor": "auto",              # auto | top-left | top-right | bottom-left | bottom-right | custom
                                        # auto = in the black bar left of a 16:9 picture, else top-left
        "native_window": True,          # Windows: native layered window (False = Qt window)
        "style": "classic",             # 1.3: look of the cards – classic | glass | chips | line (skin.py)
        "pos_x": 0.0,                   # anchor=custom: 0 = left edge, 1 = right edge of the free space
        "pos_y": 0.0,                   # anchor=custom: 0 = top, 1 = bottom
        "margin": 0.012,                # distance to the window edge (fraction of the game height)
        "height": 0.36,                 # overlay height as a fraction of the game height
        "opacity": 0.85,                # of the map (+ its lines); the other cards have their own (1.2.7)
        "hud_opacity": 0.85,
        "today_opacity": 0.85,
        "media_opacity": 0.85,
        "only_when_game_focused": True,
        "show_caption": False,          # the map pictures already carry their name
        "show_timer": True,             # round timer below the map (map shown -> map gone)
        "show_waiting": True,           # no map on screen: small card "Warte auf Map" + lobby state
        "show_server": True,            # connected server region below the timer (needs the Server tab option)
        "transparent": True,            # transparent area around the map (off = dark rectangle)
        "keep_in_bar": True,
        "cards_same_width": True,       # 1.8.29: system values / today / music in the same bar share one width
        "info_pos": "below",            # 1.8.24: timer/record/server below / above the map, custom or "inside" it (1.8.34: "inside_top" = inside, above the map)
        "info_xy": None,                # … their own place (centre as shares of the window)
        "fill_bar": False,              # 1.11.12: the map as wide as its black bar, its height follows from that
        "grow_past_bar": False,         # a map bigger than the bar may reach into the game picture (1.65.4)            # ultrawide: shrink/move the map so it stays inside the black bar
        "map_heights": {},              # map id -> own size (hotkeys / mouse wheel with that map on display)
        "map_rotations": {},            # map id -> map turned clockwise by 90/180/270° (button / hotkey)
        "floor_auto": True,             # maps with floors (Midwich): all one below the other (False: bottom only)
        "show_record": False,           # own record on the map below the timer (official match data); 1.11.11 off
        "show_notes": True,             # 1.8.54: own note on the map below the timer (mapnotes)
        "show_last_round": False,       # "Zuletzt hier": date (+ official result) of the own last round on the map
        "show_score": True,             # 1.57.56: the points counted from the score events (scorecount.line)
        "score_style": "rings",         # 1.57.64: how they look – rings / bars / line (scoreview.STYLES)
        "show_map": True,               # off: overlay shows only timer, server and ping
        "show_info": True,              # 1.9.x: the element "Infos" (timer, server, record, last round, note) on/off
        "show_media": True,             # "Läuft gerade": music of the Windows media controls (1.64)
        "media_pos": "bottom_right",    # its own window: below / bottom_right / bottom_left / custom (1.64.7)
        "media_xy": [1.0, 1.0],         # custom: share of the free room in the DBD window (dragged in edit mode)
        "media_progress": True,         # music card: how far the song is (bar + times, 1.64.7)
        "map_style": "classic",         # callout maps: classic = as supplied / dark = see-through floor (1.66)
        "media_cover_shape": "style",   # 1.8.24: the cover round / square / like the style
        "media_style": "big",           # music card: big = cover on top (1.64.7) / compact = cover left (1.64)
        "media_scale": 1.0,             # size of the music card (slider 60–200 %)
        "media_cover": True,            # album cover left of title and artist
        "media_videos": True,           # 1.8.4: a video (YouTube, Twitch …) shows too ("▶ Titel"); off = music only
        "media_next_pos": "below",      # 1.8: the Spotify queue below the song / right of it
        "media_next_n": 3,              # … how many coming tracks (1–5)
        "map_backdrop": False,          # dark area with rounded corners behind the map and its lines (1.2.4)
        "hud_backdrop": False,          # … behind the system values / "today"
        "hud_rows": {"cpu": True, "gpu": True, "spot": True, "vram": True, "ram": True,   # rows shown (1.2.8)
                     "fps": False},     # FPS from HWiNFO's shared memory (hard rule): an extra, off by default
        "stack_gap": 8,                 # px at 1440p between stacked cards / above the map (1.2.8)
        "bar_align": "centre",
        "bar_limits_on": False,         # 1.8.14: limiter lines at the top/bottom of the black bars
        "bar_limits": [0.08, 0.08, 0.08, 0.08],   # left top, left bottom, right top, right bottom (share of the height)
        "bar_limits_same": False,       # 1.8.17: each bar has lines of its own (on: dragging one moves the other too)          # left / centre / right: cards and the map "auto" in the black bar (1.2.8)
        "media_accent": True,           # music card: progress bar in the cover's main colour (1.2.4)
        "media_remaining": True,        # … time left ("−1:46") right of the bar instead of the length
        "media_backdrop": True,         # … on a dark half-transparent area
        "media_fade": True,             # … fades in/out (also on a new song)
        "fade": True,                   # map, system values and "today" fade in/out too (1.2.9)
        "text_scale": 1.0,              # name/timer/info lines of the map, independent of its size (1.65)
        "hud_scale": 1.0,               # size of the system values / "today" (60–200 %, 1.64.9)
        "show_today": True,             # block "today" (rounds, play time, kills/escaped, clock; 1.62)
        "today_pos": "below",           # 1.2.6: its own element – below the system values / bottom_right /
        "today_xy": [1.0, 0.0],         #   bottom_left / custom (centre of the card as a share of the window)
        "today_scale": 1.0,             # size of "today" (slider 60–200 %)
        "today_backdrop": False,        # dark area behind "today"
        "today_streak": False,          # row "Serie" in "today": 4Ks / escapes in a row of the running session
        "show_inputs": False,           # 1.39: the input card "Eingaben" (keys / mouse / gamepad held right now)
        "inputs_layout": "auto",        #   auto (device used last) / keyboard / gamepad
        "inputs_pos": "bottom_right",   #   bottom_left / bottom_right (in the black bar) / custom
        "inputs_xy": [0.9, 0.9],        #   custom: centre of the card as a share of the window
        "inputs_scale": 1.0,            #   size (slider 60–200 %)
        "inputs_opacity": 0.85,
        "inputs_backdrop": True,        #   dark area behind the keys
        "show_loadouts": False,         # 1.57: the other survivors' loadouts read from the pause menu
        "loadouts_items": True,         #   item and add-ons beside the perks
        "loadouts_pos": "hud",          #   hud (beside DBD's survivor list) / name (below each name, 1.57.3) / custom
        "loadouts_style": "diamond",    #   1.57.3: diamond (2×2) / row (the four side by side)
        "loadouts_look": "picture",     #   1.57.25: picture (the slots cut from the menu) / icons (the names read)
        "loadouts_xy": [0.05, 0.6],     #   custom: centre as a share of the window
        "loadouts_scale": 1.0,          #   size (slider 50–200 %): DBD's HUD scale can be set
        "loadouts_opacity": 0.9,
        "show_charts": False,           # 1.57.73: the element "Diagramme" (charts.CATALOGUE)
        "charts": ["ping", "score", "kills"],   # the charts switched on (ids, at most charts.MAX_PICKED)
        "charts_pos": "under_music",    #   stacked like "today" (layout.place_cards) / bottom corners / custom
        "charts_xy": [0.94, 0.75],      #   custom: centre of the card as a share of the window
        "charts_scale": 1.0,            #   size (slider 60–200 %)
        "charts_opacity": 0.9,
        "charts_backdrop": True,        #   dark area behind the charts
        "locked": [],                   # 1.46: elements locked in place ("map", "hud", "today", …) – not dragged
    },
    "hotkeys": {
        "toggle_overlay": "ctrl+alt+m",
        "next_variant": "ctrl+alt+v",
        "scan_now": "ctrl+alt+s",
        "next_map": "ctrl+alt+right",
        "prev_map": "ctrl+alt+left",
        "bigger": "ctrl+alt+up",
        "smaller": "ctrl+alt+down",
        "edit_position": "ctrl+alt+p",
        "rotate_map": "ctrl+alt+r",
        "next_floor": "ctrl+alt+f",     # not E: Ctrl+Alt+E is AltGr+E = € on German keyboards
        "reject_map": "ctrl+alt+x",
        "mark_clip": "f8",              # 1.4.2: a mark in the running OBS recording (single key: only while DBD is in front)
        "record_toggle": "f9",          # 1.15: start / stop an OBS recording by hand (only while DBD is in front)
        "record_pause": "f10",          # 1.15: pause / resume the recording on air
    },
    "overlay_on": True,               # 1.8.18: master switch – off hides every overlay window, detection goes on
    "overlay_small_off": True,        # 1.8.62: a small DBD window (app_place.small_window) hides it the same way
    "ui_language": "auto",            # auto (Windows language) | de | en
    "dark_mode": True,
    "color_theme": "gold",              # control window: qt_theme.THEMES (accent colour)
    "accent_custom": "#2f8fe0",         # control window: own accent (color_theme "custom", qt_theme.derive_accent)
    "oled_black": False,                # control window: true black instead of the dark greys (qt_theme.OLED)
    "ui_zoom": 1.0,                     # control window: font size factor (qt_theme.ZOOMS)
    "qt_geometry": "",                  # control window: QWidget.saveGeometry() as base64
    "card_order": {},
    "tab_order": {},                    # 1.7.6: {page: {tabs id: [tab ids]}} – the user's order of the tab rows
    "nav_order": [],                    # 1.7.6: page keys in the user's order of the navigation
    "hidden_columns": {},             # 1.3.6: {"col|col|…" of a table: [column ids]} hidden by a right-click
    "layout_per_size": True,            # overlay: place and size of every element per DBD window size (1.65)
    "layouts": {},                      # {"3440x1440": layoutmem.snapshot(...)}
    "own_presets": {},                  # 1.57.42: the user's named layouts {name: layoutmem.snapshot(...)}
    "layout_key": "",                   # the window size the current layout belongs to                   # control window: own order of the cards {page: {run: [card ids]}}
    "log_categories": ["Erkennung", "Overlay", "System", "Fehler"],
    "ocr_threads": 2,
    "save_debug_images": False,
    "corpus_save": True,                # 1.38.29: keep the banner of every detection (corpus/) for "Erkennung prüfen"
    "show_advanced": False,             # log page (1.8.78; before: detection tab): technical options unfolded
    "tray": True,                       # minimise into the notification area
    "autostart": True,                  # start with Windows (logon task, set up as admin) unless switched off
    "lobby_notify": True,               # sound + notification when a lobby was found
    "lobby_remind": True,               # … and when its countdown runs out while READY is not pressed
    "notify_background_only": True,     # only while DBD is not the active window
    "score_track": True,                # 1.57.56: count the score events top right in a match (scoreevents/scorecount)
    "bp_cap_notify": True,              # 1.13: sound + notification when a round left the bloodpoint balance unchanged (cap)
    "banner_missed_notify": True,       # sound + notification when no banner came within a minute of the match start
    "session_notify": True,             # 1.38.27: notification with the session's numbers once DBD was closed
    "auto_update": True,                # start.bat: pull the newest state from GitHub before starting
    "user_aliases": {},                 # own assignments of unknown banner texts: {map_id: [text, ...]}
    "map_notes": {},                    # 1.8.54: own notes per map, shown with the map: {map_id: text}
    "killer_notes": {},                 # 1.38.30: own notes per killer, shown below the map's once the killer is known
    "welcome_seen": False,              # the setup assistant of the first start was finished or skipped
    "seen_version": "",                 # 1.8.79: the version last run – the overview lists what is new since
    "killer_aliases": {},               # killer names as read (skins, new killers): {fold(name): "The Nurse"}
    "stats_mode": "",                   # 1.8.51: game-mode filter of the statistics, "" = all modes
    "hide_farming": False,              # 1.11.5: "Farming ausblenden" – statistics, recordings and clips without farming rounds
    "export_columns": [],               # 1.8.91: columns of the export dialog ([] = roundexport.DEFAULT_COLUMNS)
    "export_format": "csv",             # 1.8.91: csv | text
    "official_open_after_dbd": False,   # open stats.deadbydaylight.com once DBD was closed (userscript saves the matches)
    "official_dir": "",                 # where the userscript's files land ("" = the Windows download folder)
    "official_notify": True,
    "farming_crossplay": True,          # 1.2.20: a round whose lobby showed cross-play off is a farming round
    "farming_region": "ap-southeast-1",  # … and every round on this server region ("" = none)
    "farming_ignored": [],              # 1.6.1: rounds (repr of the start) not to offer as farming again
    "farming_opponents": [],            # 1.8.73: characters (as the stats page names them) you only meet while farming
    "rec_on": False,                    # 1.4: round recordings with OBS (obs-websocket on this PC)
    "rec_port": 4455,
    "rec_password": "",                 # 1.16.2: DPAPI-protected (spotify.protect), clear text before – read both
    "rec_volume": "",                   # the recording folder's drive (volume GUID) + path on it + last path
    "rec_rel": "",
    "rec_folder": "",
    "shots_folder": "",          # 1.12: the user's own screenshot folder instead of Steam's (empty = Steam's DBD folder)
    "rec_limit_gb": 0,                  # 0 = the whole drive (older recordings go when it fills up)
    "rec_pre": False,                   # save OBS's replay buffer at the banner (1.5.5: off – it holds the lobby)
    "rec_tail_s": 5,                    # 1.4.1: seconds recorded after the detected end (result screen)
    "rec_buffer_auto": True,            # 1.4.1: start/stop OBS's replay buffer with DBD
    "rec_obs_start": False,             # 1.8.47: start OBS when DBD starts (OBS stays open afterwards)
    "rec_window": False,                # 1.8.41: our window capture of DBD in OBS instead of the monitor
    "rec_capture": "window",            # 1.11.7: … through OBS's window capture or its game capture ("game")
    "rec_overlay": False,               # 1.8.89: our overlay as an image source over that window capture
    "rec_merge": False,                 # 1.4.2: pre-roll + round → one file (1.5.5: off – played too fast at the user's PC)
    "rec_farming_days": 7,              # 1.8.23: farming recordings go after this many days (0 = never)
    "rec_farming_dir": True,            # 1.5.3: recordings of farming rounds go into the subfolder "Farming"
    "rec_early": True,                  # 1.6: start at the end of the loading screen (spawn), the banner names it
    "rec_instant": True,                # 1.6: F8 also saves the last seconds of the replay buffer as a clip
    "rec_clip_s": 30,
    "rec_obs_before": {},               # 1.29: OBS's values before "In OBS einstellen" (recquality) – "Zurücksetzen"
    "rec_clip_notify": True,            # 1.8.13: a short notification for the F8 clip (also while DBD is in front)
    "rec_audio": True,                  # 1.6: set OBS's audio sources when DBD starts (user: only DBD + Discord)
    "rec_audio_dbd": True,
    "rec_audio_discord": True,
    "rec_audio_desktop": False,
    "rec_audio_mic": False,
    "rec_tracks": True,                 # 1.8.6: every sound source on its own OBS track (1 all, 2 game, 3 Discord, 4 mic)
    "rec_clip_sources": ["dbd", "discord", "mic", "other"],   # 1.8.6: what the F8 instant clip keeps when the buffer
                                        # file has the tracks; 1.11.4: every source (was game + microphone)
    "clip_mode": "copy",                # 1.5.1: clip editor – "copy" (key frames, fast) / "exact" (re-encoded)
    "clip_sound": True,                 # 1.5.1: clip editor plays the sound while previewing (Windows)
    "clip_target_mb": 10,               # 1.6.1: clip editor "Für Discord" – stays under this many MB
    "clip_codec": "h264",               # 1.15: clip editor, re-encoded clips – h264 | hevc
    "clip_quality": "balanced",         # … fast | balanced (= x264 CRF 18 as before) | high
    "clip_height": 0,                   # … picture height of the clip (0 = as recorded, else 1440/1080/720)
    "clip_hw": "auto",                  # … encoder: "" CPU | auto (first working graphics-card encoder) | nvenc/amf/qsv
    "clip_censor_on": False,            # 1.7.2: clip editor hides the censor boxes when saving
    "clip_censor_style": "pixel",       # pixel | blur | black
    "clip_censor_boxes": [],            # [[x, y, w, h] …] as fractions of the picture (the names stay put)
    "clip_mix_on": {"dbd": True, "discord": True, "mic": True},     # 1.8.6: clip editor sound mix – source on/off
    "clip_mix_vol": {"dbd": 100, "discord": 100, "mic": 100},       # and its level in percent (MIX_MAX 150)
    "editor_layout": {},                # 1.16: the editor window's panels (splitter sizes, library/inspector shown)
    "editor_autosave": True,            # 1.18.1: the big editor saves its project by itself (off: only Strg+S)
    "discord_on": False,                # 1.7: Rich Presence over the local Discord client (user's pick)
    "discord_client_id": "",            # the Application-ID the user registered in Discord's developer portal
    "discord_killer": True,             # name the killer in the status
    "discord_lobby": True,              # also show lobby / search / menu (else only the match)
    "spotify_on": False,                # 1.8: "Als nächstes" from the Spotify Web API on the music card (user's pick)
    "spotify_client_id": "",            # the Client-ID of the app the user registered in Spotify's dashboard
    "spotify_token": "",                # the refresh token, DPAPI-protected (spotify.protect), PC-specific
    "youtube_on": False,                # 1.10: clips go to YouTube by themselves (user's pick; the queue runs either way)
    "youtube_client_id": "",            # the OAuth client ("Desktop app") the user made in the Google Cloud console …
    "youtube_client_secret": "",        # … and its secret, DPAPI-protected (spotify.protect), PC-specific
    "youtube_token": "",                # the refresh token, DPAPI-protected, PC-specific
    "youtube_privacy": "private",       # private | unlisted | public (ytupload.PRIVACY)
    "youtube_queue": [],                # pending uploads (ytupload.Job dicts), PC-specific – they name local files
    "youtube_quota": {},                # {"day", "used"}: the API units spent today (ytupload.Quota)
    "youtube_playlists": False,         # 1.11: videos go into playlists after the upload (login asks for the wider scope)
    "youtube_playlist_clip": "",        # playlist id for clips …
    "youtube_playlist_round": "",       # … and for rounds ("" = none)
    "youtube_playlist_names": {},       # {id: title} as Google listed them (the two choices)
    "claude_on": False,                 # 1.26: the search (command palette) may ask Claude – only on the user's pick
    "claude_editor": False,             # 1.27: the clip editor may ask Claude („Mit Claude bearbeiten“) – user's pick
    "claude_image": False,              # 1.35: the screenshot editor may send the picture to Claude – user's pick
    "claude_frame": False,              # 1.35: the clip editor may send a still of the recording to Claude
    "claude_stats": False,              # 1.35: the search may ask Claude about summed-up round values
    "edit_templates": [],               # 1.44: [{name, ops}] – applied edits kept as recipes (editcommands.to_template)
    "crash_seen": 0.0,                  # 1.36: time of the last crash the start already asked about (diagnose)
    "loadouts_told": False,             # 1.57: the note on what the loadouts read was shown once
    "inputs_told": False,               # 1.39: the note on what the input card reads was shown once
    "inputs_record": True,              # 1.39.1: with the input card on, a round's inputs go next to its recording
    "claude_model": "opus",             # 1.36: opus | sonnet | haiku for every Claude request (askclaude.MODELS)
    "claude_spent": {},                 # 1.36: {"YYYY-MM": estimated $} – what the requests cost per month, this PC
    "claude_key": "",                   # the user's own Anthropic API key, DPAPI-protected (spotify.protect), PC-specific
    "palette_recent": [],               # 1.26: ids of the palette's last picks (palette.RECENT_KEPT), PC-specific
    "sysinfo": "right",                 # system values at the top of a black bar: off | left | right | custom
    "sysinfo_pos": [1.0, 0.0],          # sysinfo = custom: 0..1 of the free space in the DBD window (x, y)
}


RECENT_KEPT = 8                         # palette.RECENT_KEPT (palette imports nothing from here)
# 1.28 (audit F11): settings whose type the code relies on – a hand-edited "claude_on": "false" counted as on
TYPED = {"claude_on": bool, "claude_editor": bool, "claude_image": bool, "claude_frame": bool, "claude_stats": bool,
         "claude_model": str, "claude_spent": dict, "palette_recent": list, "rec_obs_before": dict}


def _typed(key, value, default):
    """A stored value of a TYPED setting with the expected type, else the default (palette_recent: strings only)."""
    want = TYPED[key]
    if want is bool:
        return value if isinstance(value, bool) else copy.deepcopy(default)
    if want is str or want is dict:
        # 1.38.17 (audit): only bool and list had a branch – a str such as claude_model always fell through to the
        # default, so a picked "haiku"/"sonnet" came back as "opus" at every start (dicts never got here: _merge
        # merges them before, but a stored non-dict for a dict key does, and keeps the default as before)
        return value if isinstance(value, want) else copy.deepcopy(default)
    if not isinstance(value, list):
        return copy.deepcopy(default)
    return [v for v in value if isinstance(v, str)][:RECENT_KEPT]


# 1.57.70 (deep review STAB-01, 156 of 1 980 fuzzed files): a readable settings.json with a wrong type or an absurd
# number ("ui_zoom": 1e9, "languages": 5) passed the load and stopped every start in App.__init__ – now a value whose
# type does not fit its default is replaced by the default (``fixed``, logged), numbers must be finite and within
# NUM_LIMIT, and these keys within their range (the ends of what the controls offer, generously)
NUM_LIMIT = 1e6
RANGES = {"ui_zoom": (0.5, 3.0), "height": (0.01, 1.0), "margin": (0.0, 0.5)}     # these exact keys (overlay.height)
RANGE_ENDS = {"opacity": (0.0, 1.0), "scale": (0.05, 20.0)}                         # and every key ending "_<end>"


def _range(key: str):
    if key in RANGES:
        return RANGES[key]
    for end, lo_hi in RANGE_ENDS.items():
        if key == end or key.endswith("_" + end):
            return lo_hi
    return None


def _number(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v) and abs(v) <= NUM_LIMIT
    except OverflowError:                                 # an int too big for a float
        return False


def _fits(key: str, value, default) -> bool:
    """Does a stored ``value`` have the shape of ``default`` (bool, number, text, list of texts/numbers)? A default
    of None or an empty list says nothing – anything fits."""
    if default is None:
        return True
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        if not _number(value):
            return False
        lo_hi = _range(key)
        return lo_hi is None or lo_hi[0] <= value <= lo_hi[1]
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):
        if not isinstance(value, list):
            return False
        if default and all(isinstance(d, str) for d in default):
            return all(isinstance(v, str) for v in value)
        if default and all(_number(d) for d in default):
            return len(value) == len(default) and all(_number(v) for v in value)
    return True


def _merge(base: dict, override: dict, fixed: list | None = None, where: str = "") -> dict:
    out = copy.deepcopy(base)
    for k, v in (override if isinstance(override, dict) else {}).items():
        if isinstance(out.get(k), dict):
            if isinstance(v, dict):
                out[k] = _merge(out[k], v, fixed, f"{where}{k}.")
            # 1.8.38: anything else where the defaults hold a dict ("overlay": null) keeps the defaults
        elif base is DEFAULTS and k in TYPED:
            out[k] = _typed(k, v, base.get(k))
        elif fixed is not None and k in base and k != "settings_version" and not _fits(k, v, base[k]):
            out[k] = copy.deepcopy(base[k])               # 1.57.70 (STAB-01)
            fixed.append(where + str(k))
        else:
            out[k] = v
    return out


def _version(raw: dict) -> int:
    """settings_version of a stored file; a hand-edited odd value counts as current (no migration runs on it)."""
    v = raw.get("settings_version", 1)
    if isinstance(v, bool):
        return SETTINGS_VERSION
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):        # 1.57.70 (STAB-01): 1e999 = inf stopped Settings()
        return SETTINGS_VERSION


# 1.28 (audit F10): not secret, but this PC's own and not for a file the user passes on: the YouTube queue holds
# the upload session URIs (whoever has one can upload to it for a while) and file paths of the recordings folder
EXPORT_SKIP = ("youtube_queue",)
SECRET_KEYS = ("rec_password", "spotify_token", "youtube_client_secret", "youtube_token", "claude_key")   # 1.8.38: never in a backup


def export_settings(data: dict, path: str) -> None:
    """Backup of all settings (hotkeys, sizes/rotations per map, own map assignments …) – without the secrets
    (SECRET_KEYS), the YouTube queue (EXPORT_SKIP) and (review F-01) this PC's own values
    (LOCAL_KEYS: folders, setup path, window geometry …): read_backup never takes them from a file anyway, so in a
    shared backup they only told others about this PC. Old backups that still hold them import as before."""
    data = {k: v for k, v in data.items() if k not in SECRET_KEYS and k not in EXPORT_SKIP and k not in LOCAL_KEYS}
    fsops.write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


# per-PC values that must not come along from a backup (other folder / other machine)
LOCAL_KEYS = ("setup_version", "setup_root", "qt_geometry", "official_dir", "layouts", "layout_key",
              "rec_volume", "rec_rel", "rec_folder", "rec_password", "spotify_token", "seen_version",
              "youtube_client_secret", "youtube_token", "youtube_queue", "youtube_quota", "shots_folder",
              "editor_layout", "claude_key", "palette_recent", "rec_obs_before", "claude_spent", "crash_seen")


def no_bar_defaults(data: dict) -> dict:
    """1.46.8 (user: "falls 1920×1080, soll das mit schwarzen Balken standardmässig aus sein"): the defaults of a
    screen without black bars beside the picture (layout.side_bars) – system values, "today" and the music card
    stand in those bars; without them they would lie on the game picture, so they start switched off (the map
    stays, top left). Only for settings nobody has chosen yet: a first start, "Alle Einstellungen zurücksetzen"."""
    data["sysinfo"] = "off"
    data.setdefault("overlay", {}).update(show_today=False, show_media=False)
    return data


KEPT_CONTENT = ("map_notes", "killer_notes", "edit_templates")   # 1.57.70 (DATA-03): the user's own texts, not settings


def reset_data(current: dict, keep_content: bool = True) -> dict:
    """1.2.19 ("Alle Einstellungen zurücksetzen"): the defaults, with the PC-specific values (LOCAL_KEYS) of
    ``current`` kept – the window geometry, the setup marker, the download folder; the layouts per window size
    go with the layout (they are layout). ``welcome_seen`` stays: the assistant is not forced again. 1.57.70 (deep
    review DATA-03): the notes per map and killer and the editor's templates stay too (``keep_content``) – they are
    the user's writing, the reset deleted them without a word."""
    data = copy.deepcopy(DEFAULTS)
    for k in ("setup_version", "setup_root", "qt_geometry", "official_dir"):
        if k in current:
            data[k] = copy.deepcopy(current[k])
    if current.get("welcome_seen"):
        data["welcome_seen"] = True
    if keep_content:
        for k in KEPT_CONTENT:
            if k in current and _fits(k, current[k], DEFAULTS.get(k)) and isinstance(current[k], type(DEFAULTS[k])):
                data[k] = copy.deepcopy(current[k])
    return data


def save_before_reset(data: dict, folder: str, now: float | None = None) -> str:
    """1.57.70 (deep review DATA-03): the settings as they are, written to ``folder`` (the data folder's backup/)
    before "Alle Einstellungen zurücksetzen" – as "Einstellungen exportieren" writes them (no secrets, no PC-own
    values), so "Einstellungen importieren" brings them back. Its path; OSError when it could not be written."""
    if not fsops.plain_dir(folder, 1):
        raise OSError("the backup folder is a link")
    path = os.path.join(folder, time.strftime("settings-%Y-%m-%d-%H%M%S.json", time.localtime(now)))
    export_settings(data, path)
    return path


def keep_and_reset(path: str) -> bool:
    """1.57.70 (deep review STAB-01): the program did not start with these settings – the file is kept as
    ``settings.json.broken`` (an older one there is replaced) and settings.json starts over with the defaults (the
    PC-specific values kept, as "Alle Einstellungen zurücksetzen"). False when it could not be done."""
    try:
        current = _read_json(path)
    except (OSError, ValueError, RecursionError):
        current = {}
    try:
        shutil.copy2(path, path + ".broken")
        fsops.write_atomic(path, json.dumps(reset_data(current if isinstance(current, dict) else {}, keep_content=False),
                                            ensure_ascii=False, indent=2).encode("utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    return True


def read_backup(path: str, current: dict) -> dict:
    """Settings from a backup file, merged over the defaults (keys missing in older backups get their
    default) and migrated like a stored settings.json (1.55.3: a backup of an older version brought back what the
    migrations remove – old tab orders, the record row …); ValueError if it is no settings file of this program."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError, RecursionError) as e:
        raise ValueError(str(e)) from e
    if not isinstance(raw, dict) or not isinstance(raw.get("overlay"), dict) or "hotkeys" not in raw:
        raise ValueError("no Fog Scout settings")
    for k in LOCAL_KEYS:
        raw.pop(k, None)
        if k in current:
            raw[k] = current[k]
    try:
        return _load(raw)
    except (TypeError, ValueError, AttributeError, KeyError, RecursionError, ArithmeticError) as e:   # as Settings()
        raise ValueError(f"{type(e).__name__}: {e}") from e


def _read_json(path: str):
    """The stored file; one retry when it is locked for a moment (virus scanner, cloud sync)."""
    for attempt in (0, 1):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except PermissionError:
            if attempt:
                raise
            time.sleep(0.5)


def _load(raw, fixed: list | None = None) -> dict:
    """Stored settings -> merged over the defaults and migrated (1.8.38: built aside, so a failure leaves nothing
    half-merged behind). ``fixed`` collects the keys whose stored value did not fit (1.57.70, STAB-01)."""
    if not isinstance(raw, dict):
        raise ValueError("settings.json holds no object")
    ver = _version(raw)
    data = _merge(DEFAULTS, raw, fixed if fixed is not None else [])
    ov = data["overlay"]
    if ver < 2:  # defaults changed in 1.1
        if ov.get("anchor") == "top-left":
            ov["anchor"] = "auto"
        ov["show_caption"] = False
    if ver < 3:  # 1.2: position sliders
        ov["pos_x"] = min(1.0, max(0.0, float(ov.pop("custom_x", 0.0))))
        ov["pos_y"] = min(1.0, max(0.0, float(ov.pop("custom_y", 0.0))))
    if ver < 4 and ov.get("media_pos") == "below":
        ov["media_pos"] = "bottom_right"  # 1.64.7: the music card stands on its own (user's wish)
    if ver < 5:  # 1.2.6: "today" is an element of its own
        if data.pop("today_side", None) == "custom" and raw.get("sysinfo") not in HUD_SHOWN:
            ov["today_pos"] = "custom"                    # it stood alone at its own place
            fx, fy = (data.get("sysinfo_pos") or [1.0, 0.0])[:2]
            ov["today_xy"] = [float(fx), float(fy)]
    if ver < 6:  # 1.2.7: opacity per card, cards stack
        for key in ("hud_opacity", "today_opacity", "media_opacity"):
            ov[key] = ov.get("opacity", 0.85)             # as before: one opacity for everything
        if ov.get("media_pos") == "below" and ov.get("today_pos", "below") == "below" \
                and ov.get("show_today", True):
            ov["media_pos"] = "under_today"               # 1.2.6 hung the music below "today"
    if ver < 7:  # 1.5.5 (user: "no lobby in the recording",
        data["rec_pre"] = False                      # joined files played too fast in the round)
        data["rec_merge"] = False
    if ver < 8:  # 1.8.17 (user: left and right lines of their own)
        ov["bar_limits_same"] = False
    if ver < 9:  # 1.8.76: the statistics' tabs are four groups now – a saved order of the thirteen would reorder them
        (data.get("tab_order") or {}).pop("stats", None)
    if ver < 10:  # 1.8.78: the page "Erkennung" went into the settings and the log – nothing of it to order any more
        if "detect" in (data.get("nav_order") or []):
            data["nav_order"] = [k for k in data["nav_order"] if k != "detect"]
        (data.get("card_order") or {}).pop("detect", None)
        (data.get("tab_order") or {}).pop("detect", None)
    if ver < 11 and data.get("rec_clip_sources") == ["dbd", "mic"]:   # 1.11.4: the old default follows the new one
        data["rec_clip_sources"] = list(DEFAULTS["rec_clip_sources"])
    if ver < 12:  # 1.11.11 (user: "entferne das Avg-Kill, damit falls es stockt nicht noch eine Zeile entsteht")
        ov["show_record"] = False
    if ver < 13:  # 1.12.7: Bloodpoints/Farming/System moved to other groups – a saved order of the old rows would
        (data.get("tab_order") or {}).pop("stats", None)   # put the wrong tabs first (tabs count by position)
    if data.get("color_theme") == "oled":            # 1.62.0: OLED was a theme of its own
        data["color_theme"], data["oled_black"] = "gold", True
    for key in ("keep_out_on", "keep_out"):         # 1.57.10 (user: "Drin soll nur Fog Scout sein"): Discord's areas gone
        (data.get("overlay") or {}).pop(key, None)
    data["settings_version"] = SETTINGS_VERSION
    return data


class Settings:
    def __init__(self, path: str):
        self.path = path
        self.frozen = False             # after importing a backup: nothing is written until the restart
        self._save_failed = False
        self.data = copy.deepcopy(DEFAULTS)
        self.load_error = ""            # 1.8.38: the file could not be read (the app says so in the log)
        self.fixed = []                 # 1.57.70 (STAB-01): keys whose stored value did not fit – the default instead
        self.fresh = not os.path.exists(path)   # 1.46.8: a first start – nothing here was chosen by the user yet
        if os.path.exists(path):
            try:
                self.data = _load(_read_json(path), self.fixed)
            except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError, ArithmeticError) as e:
                self.load_error = f"{type(e).__name__}: {e}"
                self._keep_broken(path)

    def _keep_broken(self, path: str):
        """1.8.38: a file that could not be read is never overwritten with the defaults (it held the hotkeys, the
        layouts, the OBS password …): it is copied to settings.json.broken first; if not even that works (locked),
        nothing is written in this session."""
        try:
            shutil.copy2(path, path + ".broken")
        except OSError:
            self.frozen = True

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        if self.frozen:
            return
        try:                            # 1.38.5: fsops.write_atomic – fsync'ed temp file, one replace, no temp left
            fsops.write_atomic(self.path, json.dumps(self.data, indent=2, ensure_ascii=False).encode("utf-8"))
        except OSError as e:
            if not self._save_failed:   # disk full, locked: said once in the log, the next save tries again
                log.warning("Einstellungen nicht gespeichert: %s", e)
            self._save_failed = True
        else:
            self._save_failed = False
