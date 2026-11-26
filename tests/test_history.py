"""Round history (fogscout/history.py)."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fogscout import history as h  # noqa: E402


def rnd(m, s, t=0.0, region=""):
    return h.Round(t=t, seconds=s, map_id=m.lower(), map=m, region=region, source="auto")


def test_short_rounds_do_not_count():
    assert not h.should_record(12) and not h.should_record(59.9) and h.should_record(60)


def test_file_round_trip(tmp_path):
    p = str(tmp_path / h.FILE)
    assert h.load(p) == []                                           # no file yet
    h.append(p, rnd("Coal Tower", 600, 1.0, "eu-central-1"))
    h.append(p, rnd("Léry's Memorial Institute", 420, 2.0))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("kaputt\n{}\n")                                     # broken lines are skipped
    got = h.load(p)
    assert [r.map for r in got] == ["Coal Tower", "Léry's Memorial Institute"]
    assert got[0].region == "eu-central-1" and got[0].seconds == 600
    h.clear(p)
    assert h.load(p) == [] and not os.path.exists(p)


def test_statistics():
    rs = [rnd("Coal Tower", 600), rnd("Coal Tower", 300), rnd("Badham Preschool II", 900)]
    assert h.summary(rs) == {"count": 3, "total": 1800, "avg": 600}
    assert h.summary([]) == {"count": 0, "total": 0, "avg": 0.0}
    assert h.per_map(rs) == [("Coal Tower", 2, 450, 600), ("Badham Preschool II", 1, 900, 900)]


def test_file_is_tidied(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "KEEP", 10)
    p = str(tmp_path / h.FILE)
    for i in range(30):
        h.append(p, rnd("Coal Tower", 100 + i, float(i)))
    got = h.load(p)
    assert len(got) <= 30 and got[-1].seconds == 129                # newest kept
    assert len(got) >= 10


def test_periods_are_calendar_based():
    import datetime
    now = datetime.datetime(2026, 9, 30, 15, 30).timestamp()            # a Wednesday
    ts = lambda *a: datetime.datetime(*a).timestamp()                   # noqa: E731
    assert h.period_start("all", now) is None
    assert h.period_start("day", now) == ts(2026, 9, 30)
    assert h.period_start("week", now) == ts(2026, 9, 28)              # Monday
    assert h.period_start("month", now) == ts(2026, 9, 1)
    assert h.period_start("year", now) == ts(2026, 1, 1)


def test_select_and_per_region():
    rs = [rnd("A", 100, 10, "eu-central-1"), rnd("B", 300, 20, "eu-central-1"), rnd("C", 200, 30, "eu-west-2"),
          rnd("D", 400, 40)]
    assert [r.map for r in h.select(rs, since=25)] == ["C", "D"]
    assert [r.map for r in h.select(rs, region="eu-central-1")] == ["A", "B"]
    assert [r.map for r in h.select(rs, region=h.NO_REGION)] == ["D"]
    assert h.regions_used(rs) == ["eu-central-1", "eu-west-2"]
    assert h.per_region(rs) == [("eu-central-1", 2, 200, 0.5), ("eu-west-2", 1, 200, 0.25),
                                (h.NO_REGION, 1, 400, 0.25)]
    assert h.per_region([]) == []


def test_wait_and_role_round_trip(tmp_path):
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=1.0, seconds=600, map_id="a", map="A", wait=125.0, role="killer"))
    h.append(p, h.Round(t=2.0, seconds=600, map_id="b", map="B", custom=True))
    with open(p, "a", encoding="utf-8") as fh:
        fh.write('{"t": 3, "seconds": 70, "map_id": "c", "role": "hacker", "wait": -5}\n')   # nonsense is dropped
    a, b, c = h.load(p)
    assert (a.wait, a.role, a.custom) == (125.0, "killer", False)
    assert (b.wait, b.role, b.custom) == (None, "", True)
    assert (c.wait, c.role) == (None, "")


def test_role_filter_and_waiting_times():
    import datetime
    ts = lambda *a: datetime.datetime(*a).timestamp()                   # noqa: E731
    rs = [h.Round(ts(2026, 9, 28, 20, 5), 600, "a", "A", "eu-central-1", wait=60, role="killer"),      # Monday
          h.Round(ts(2026, 9, 28, 21, 0), 600, "a", "A", "eu-west-2", wait=180, role="killer"),
          h.Round(ts(2026, 9, 29, 9, 0), 600, "a", "A", "eu-central-1", wait=30, role="survivor"),        # Tuesday
          h.Round(ts(2026, 9, 29, 10, 0), 600, "a", "A", custom=True, role="killer"),
          h.Round(ts(2026, 9, 29, 11, 0), 600, "a", "A", role="survivor")]                              # search not seen
    assert len(h.select(rs, role="killer")) == 2 and len(h.select(rs, role="custom")) == 1
    assert len(h.select(rs, role="survivor")) == 2 and len(h.select(rs)) == 5
    assert h.wait_summary(rs) == {"count": 3, "avg": 90.0, "median": 60, "min": 30, "max": 180}
    assert h.wait_summary([])["count"] == 0
    assert h.wait_by(rs, "weekday") == [(0, 2, 120.0, 60), (1, 1, 30.0, 30)]
    assert h.wait_by(rs, "hour") == [(9, 1, 30.0, 30), (18, 1, 60.0, 60), (21, 1, 180.0, 180)]
    assert h.wait_by(rs, "region") == [("eu-central-1", 2, 45.0, 30), ("eu-west-2", 1, 180.0, 180)]


def test_role_can_be_corrected(tmp_path):
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=100.5, seconds=600, map_id="a", map="A", wait=90.0, role="survivor"))
    h.append(p, h.Round(t=200.25, seconds=600, map_id="b", map="B", role="killer"))
    assert h.set_role(p, 100.5, "killer").map == "A"
    assert [r.role for r in h.load(p)] == ["killer", "killer"]
    h.set_role(p, 100.5, "custom")
    a = h.load(p)[0]
    assert (a.custom, a.role, a.wait) == (True, "", 90.0)             # wait kept: undo-able, ignored while custom
    assert h.wait_summary(h.load(p))["count"] == 0
    h.set_role(p, 100.5, "survivor")
    assert (h.load(p)[0].custom, h.load(p)[0].role) == (False, "survivor")
    assert h.set_role(p, 999.0, "killer") is None
    import pytest
    with pytest.raises(ValueError):
        h.set_role(p, 100.5, "hacker")



def test_a_round_can_be_deleted(tmp_path):
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=100.5, seconds=600, map_id="a", map="A"))
    h.append(p, h.Round(t=200.25, seconds=300, map_id="b", map="B"))
    h.append_lost(p, 150.0, "C", "banner")
    assert h.delete(p, 200.25).map == "B"
    assert [r.map for r in h.load(p)] == ["A"] and len(h.load_lost(p)) == 1     # lost lines stay
    assert h.delete(p, 999.0) is None
def test_ping_per_round_and_region(tmp_path):
    assert h.median([30, None, 10, 20]) == 20 and h.median([10, 20]) == 15 and h.median([]) is None
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=1.0, seconds=600, map_id="a", map="A", region="eu-central-1", ping=20.0))
    h.append(p, h.Round(t=2.0, seconds=600, map_id="a", map="A", region="eu-central-1", ping=30.0))
    h.append(p, h.Round(t=3.0, seconds=600, map_id="a", map="A", region="eu-west-2"))               # no ping
    rs = h.load(p)
    assert [r.ping for r in rs] == [20.0, 30.0, None]
    assert h.ping_by_region(rs) == {"eu-central-1": 25.0}


def test_lost_rounds_are_kept_apart(tmp_path, monkeypatch):
    p = str(tmp_path / h.FILE)
    h.append(p, rnd("Coal Tower", 600, 1.0))
    h.append_lost(p, 2.0, "Badham Preschool I", "banner")
    h.append(p, rnd("Hawkins", 700, 3.0))
    h.append_lost(p, 4.0, "Ormond", "quit")
    assert [r.map for r in h.load(p)] == ["Coal Tower", "Hawkins"]            # not counted as rounds
    assert h.load_lost(p) == [(2.0, "Badham Preschool I", "banner"), (4.0, "Ormond", "quit")]
    h.set_role(p, 1.0, "killer")                                               # rewriting keeps them
    assert len(h.load_lost(p)) == 2 and h.load(p)[0].role == "killer"
    monkeypatch.setattr(h, "KEEP", 1)                                          # tidy: old lost lines go too
    import os
    monkeypatch.setattr(os.path, "getsize", lambda _p: 10 ** 9)
    h._tidy(p)
    assert [r.map for r in h.load(p)] == ["Hawkins"] and h.load_lost(p) == [(4.0, "Ormond", "quit")]


def test_killer_per_round(tmp_path):
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=1.0, seconds=600, map_id="a", map="A", role="killer", killer="The Nurse"))
    h.append(p, h.Round(t=2.0, seconds=300, map_id="b", map="B", role="killer", killer="The Nurse"))
    h.append(p, h.Round(t=3.0, seconds=900, map_id="b", map="B", role="killer", killer="The Hillbilly"))
    h.append(p, h.Round(t=4.0, seconds=500, map_id="b", map="B", role="killer", killer="The Hillbilly"))
    h.append(p, h.Round(t=5.0, seconds=700, map_id="c", map="C", role="survivor"))
    rs = h.load(p)
    assert [r.killer for r in rs] == ["The Nurse", "The Nurse", "The Hillbilly", "The Hillbilly", ""]
    assert [r.map for r in h.select(rs, killer="The Nurse")] == ["A", "B"]
    assert h.killers_used(rs) == ["The Hillbilly", "The Nurse"]                    # tie: by name
    assert h.per_killer(rs) == [("The Hillbilly", 2, 700.0, "B"), ("The Nurse", 2, 450.0, "A")]
    h.set_role(p, 1.0, "survivor")                                             # corrected: no killer round any more
    rs = h.load(p)
    assert [r.map for r in h.select(rs, killer="The Nurse")] == ["B"] and rs[0].killer == "The Nurse"   # undo-able
    assert h.select(rs, role="survivor", killer="The Nurse") == []


def test_killer_of_one_round_can_be_set(tmp_path):
    """A round counted as survivor has no killer name – setting one makes it a killer round with that killer."""
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=1.0, seconds=600, map_id="a", map="A", wait=90.0, role="survivor"))
    h.append(p, h.Round(t=2.0, seconds=300, map_id="b", map="B", custom=True))
    assert h.set_killer(p, 1.0, "The Nurse").map == "A"
    a = h.load(p)[0]
    assert (a.role, a.killer, a.custom, a.wait) == ("killer", "The Nurse", False, 90.0)
    assert h.per_killer(h.load(p)) == [("The Nurse", 1, 600.0, "A")]
    h.set_killer(p, 2.0, "The Oni")                                            # custom game -> killer round
    assert [r.map for r in h.select(h.load(p), killer="The Oni")] == ["B"]
    assert h.set_killer(p, 9.0, "The Oni") is None
    import pytest
    with pytest.raises(ValueError):
        h.set_killer(p, 1.0, "")


def test_the_map_of_a_stored_round_can_be_corrected(tmp_path):
    """1.38.26 (project review F3): a banner read as the wrong map could not be corrected in the history – every
    other field had a setter (role, killer, farming, balance), the map had none."""
    p = str(tmp_path / h.FILE)
    h.append(p, h.Round(t=1.0, seconds=600, map_id="coal-tower", map="Coal Tower", role="killer", killer="The Nurse"))
    h.append_lost(p, 2.0, "Ormond", "banner")
    r = h.set_map(p, 1.0, "ironworks", "Ironworks of Misery")
    assert (r.map_id, r.map, r.role, r.killer) == ("ironworks", "Ironworks of Misery", "killer", "The Nurse")
    assert [(x.map_id, x.map) for x in h.load(p)] == [("ironworks", "Ironworks of Misery")]
    assert h.set_map(p, 1.0, "ironworks", "Ironworks of Misery") is None       # already that map: nothing written
    assert h.set_map(p, 9.0, "ironworks", "Ironworks of Misery") is None       # no such round
    assert len(h.load_lost(p)) == 1                                            # the lost line survived the rewrite
    import pytest
    with pytest.raises(ValueError):
        h.set_map(p, 1.0, "", "x")


def test_roles_per_map():
    rs = [h.Round(1, 600, "a", "Coal Tower", role="killer"), h.Round(2, 600, "a", "Coal Tower", role="survivor"),
          h.Round(3, 600, "a", "Coal Tower", role="killer"), h.Round(4, 600, "a", "Coal Tower", custom=True),
          h.Round(5, 600, "b", "Ormond")]                                      # role unknown
    assert h.roles_per_map(rs) == {"Coal Tower": (2, 1), "Ormond": (0, 0)}


def test_today_at_a_glance():
    import datetime
    now = datetime.datetime(2026, 10, 2, 20, 0).timestamp()
    yesterday = now - 86400
    rounds = [h.Round(t=now - 3600, seconds=600, map_id="a", map="A", role="killer", killer="The Nurse", wait=120,
                      ping=30),
              h.Round(t=now - 1800, seconds=900, map_id="b", map="B", role="survivor", wait=60, ping=40),
              h.Round(t=now - 900, seconds=300, map_id="b", map="B", custom=True),
              h.Round(t=yesterday, seconds=999, map_id="c", map="C", role="killer", killer="The Hag", wait=999)]
    d = h.today(rounds, now)
    assert d["count"] == 3 and d["total"] == 1800 and (d["killer"], d["survivor"]) == (1, 1)
    assert d["wait"] == 90 and d["top_killer"] == "The Nurse" and d["ping"] == 35
    empty = h.today(rounds[3:], now)
    assert empty["count"] == 0 and empty["wait"] is None and empty["ping"] is None and not empty["top_killer"]


def test_lost_rounds_keep_what_was_known(tmp_path):
    p = str(tmp_path / h.FILE)
    h.append(p, rnd("Coal Tower", 600, 1.0))
    h.append_lost(p, 2.0, "Coal Tower II", "banner", map_id="coal-tower", region="eu-central-1", wait=95.0,
                  role="killer", killer="The Nurse", ping=None, pings=[1, 2])      # unknown keys are dropped
    with open(p, "a", encoding="utf-8") as fh:
        fh.write('{"lost": true, "t": 3.0, "map": "Old Line", "reason": "banner"}\n')   # written before 1.35
    assert h.load_lost(p) == [(2.0, "Coal Tower II", "banner"), (3.0, "Old Line", "banner")]
    a, b = h.load_lost_rounds(p)
    assert (a.t, a.seconds, a.map_id, a.map, a.region, a.wait, a.role, a.killer, a.ping) == \
        (2.0, 0.0, "coal-tower", "Coal Tower II", "eu-central-1", 95.0, "killer", "The Nurse", None)
    assert (b.map_id, b.map, b.role, b.wait) == ("", "Old Line", "", None)
    h.set_role(p, 1.0, "survivor")                         # rewriting the file keeps the lost lines whole
    assert [r.wait for r in h.load_lost_rounds(p)] == [95.0, None]
    assert [r.role for r in h.load(p)] == ["survivor"]


def test_last_days_periods_and_map_filter():
    """1.2.16: "Letzte 7/30 Tage" start at midnight 6 / 29 days back; select() takes a map label. (The CSV export
    is roundexport's since 1.8.91 – history.export_csv went in 1.50.4.)"""
    import datetime
    now = datetime.datetime(2026, 10, 16, 15, 30).timestamp()
    assert h.period_start("7d", now) == datetime.datetime(2026, 10, 10).timestamp()
    assert h.period_start("30d", now) == datetime.datetime(2026, 9, 17).timestamp()
    rounds = [h.Round(t=now - i * 3600, seconds=600, map_id="coal", map="Coal Tower" if i % 2 else "Gas Heaven")
              for i in range(4)]
    assert [r.map for r in h.select(rounds, map_label="Coal Tower")] == ["Coal Tower", "Coal Tower"]
    assert len(h.select(rounds, map_label=None)) == 4


def test_farming_rounds_count_everywhere_until_the_switch_hides_them(tmp_path):
    """1.2.20 (user: rounds without cross-play / on the farming region are farming rounds, not normal ones) –
    until 1.11.4 every role filter left them out. 1.11.5 (user: "die Filterung von Farming find ich kacke" →
    "überall mitzählen, Schalter zum Ausblenden"): they count like any other round; ``farming=False`` is the switch
    "Farming ausblenden", ``farming=True`` / role "farming" = only them. Waiting times stay a thing of public
    searches (a farming lobby is arranged)."""
    rs = [h.Round(100, 600, "a", "A", "eu-central-1", wait=60, role="killer"),
          h.Round(200, 600, "a", "A", "ap-southeast-1", wait=30, role="killer", farming=True),
          h.Round(300, 600, "a", "A", role="survivor", farming=True),
          h.Round(400, 600, "a", "A", custom=True, farming=True)]
    assert [r.t for r in h.select(rs)] == [100, 200, 300, 400]             # "all" has farming in
    assert [r.t for r in h.select(rs, farming=False)] == [100, 400]        # the switch; custom stays custom
    assert [r.t for r in h.select(rs, role="killer")] == [100, 200]
    assert [r.t for r in h.select(rs, role="killer", farming=False)] == [100]
    assert [r.t for r in h.select(rs, role="farming")] == [200, 300] == [r.t for r in h.select(rs, farming=True)]
    assert [r.t for r in h.select(rs, role="custom")] == [400]
    assert h.wait_summary(rs)["count"] == 1 and h.roles_per_map(rs) == {"A": (2, 1)}
    assert h.roles_per_map(h.select(rs, farming=False)) == {"A": (1, 0)}
    assert [h.normal(r) for r in rs] == [True, False, False, False]
    assert "farming" in h.LOST_KEYS
    path = str(tmp_path / "rounds.jsonl")
    for r in rs[:2]:
        h.append(path, r)
    assert [r.farming for r in h.load(path)] == [False, True]
    assert h.set_farming(path, 100, True).farming is True
    assert [r.farming for r in h.load(path)] == [True, True]
    assert h.set_farming(path, 200, False).role == "killer"                # the role stays
    h.append(path, h.Round(t=300, map_id="x", map="X", seconds=400, role="", custom=True))
    r = h.set_farming(path, 300, True)                                     # 1.5.5: farming drops "custom game"
    assert r.farming and not r.custom and [x.t for x in h.select(h.load(path), role="farming")] == [100, 300]
    assert h.set_farming(path, 999, True) is None


def test_bloodpoints_per_round_and_per_hour_with_and_without_waiting():
    """1.6.3 (user: farming evaluation): BP per round, per hour in the match (the page's length, else banner to
    end) and per hour with the search time; rounds without a known wait count with the average of the others."""
    from fogscout import dashboard
    from fogscout.official import Match
    rs = [h.Round(t=1, seconds=500, map_id="a", map="A", role="survivor", wait=60.0),
          h.Round(t=2, seconds=500, map_id="a", map="A", role="killer", killer="The Nurse", wait=None),
          h.Round(t=3, seconds=500, map_id="a", map="A", role="killer", killer="The Nurse", wait=120.0),
          h.Round(t=4, seconds=500, map_id="a", map="A", role="survivor", wait=30.0)]
    ms = [Match(t=0, map="A", seconds=600, bp=30000), Match(t=0, map="A", seconds=0, bp=40000),
          Match(t=0, map="A", seconds=900, bp=50000), Match(t=0, map="A", seconds=600, bp=0)]   # no BP: left out
    b = dashboard.bp_rate(list(zip(rs, ms)))
    assert (b.rounds, b.bp, b.play_s) == (3, 120000, 600 + 500 + 900) and b.per_round == 40000
    assert b.wait_s == 60 + 90 + 120                                    # the unknown wait = mean of 60 and 120
    assert b.per_hour == 120000 * 3600 / 2000 and b.per_hour_waiting == 120000 * 3600 / 2270
    rows = dashboard.bp_rows(list(zip(rs, ms)), lambda k: k[4:])
    assert [g for g, _b in rows] == ["Alle", "Survivor", "Killer", "   Nurse"]
    assert rows[2][1].bp == 90000 and dashboard.bp_rate([]).per_hour is None
    tile = dashboard.tiles(rs, list(zip(rs, ms)))[-1]
    assert tile.title == "Bloodpoints pro Stunde" and tile.value == "216k" and tile.sub.startswith("mit Wartezeit")


def test_the_bloodpoints_dashboard_tiles_and_trend():
    """1.7.1 (user: a small dashboard for the bloodpoints): tiles above the table – total, per round, per hour,
    best round, Ø per role with bars relative to the higher one – and Ø BP per bucket with empty buckets kept."""
    from fogscout import dashboard
    from fogscout.official import Match, bucket_start
    day = 86400
    t0 = bucket_start(1_760_000_000, "day")
    rs = [h.Round(t=t0 + 60, seconds=600, map_id="a", map="Coal Tower", role="killer", wait=60.0),
          h.Round(t=t0 + 2 * day, seconds=600, map_id="b", map="Badham", role="survivor", wait=30.0),
          h.Round(t=t0 + 2 * day + 900, seconds=600, map_id="b", map="Badham", role="survivor", wait=30.0)]
    ms = [Match(t=0, map="Coal Tower", seconds=600, bp=30000), Match(t=0, map="Badham", seconds=600, bp=50000),
          Match(t=0, map="Badham", seconds=600, bp=0)]
    tiles = {t.title: t for t in dashboard.bp_tiles(list(zip(rs, ms)), lambda r: r.upper())}
    assert tiles["Bloodpoints"].value == "80k" and tiles["Bloodpoints"].sub.startswith("2 Runden")
    assert tiles["Ø pro Runde"].value == "40k" and tiles["BP/h im Match"].value == "240k"
    assert tiles["Beste Runde"].value == "50k" and tiles["Beste Runde"].sub.startswith("Badham · ")
    assert tiles["Beste Runde"].sub.endswith("SURVIVOR")
    assert tiles["Ø BP als Killer"].frac == 30000 / 50000 and tiles["Ø BP als Survivor"].frac == 1.0
    assert dashboard.bp_tiles([]) == []
    trend = dashboard.bp_trend(list(zip(rs, ms)), "day")
    assert [(round((b - t0) / day), bps) for b, bps in trend] == [(0, [30000]), (1, []), (2, [50000])]
    assert dashboard.bp_trend([], "day") == []


def test_a_round_after_a_line_cut_off_by_a_crash_is_kept(tmp_path):
    """1.8.38 (QA audit): a crash while writing left the last line without its line break – the next round was
    glued to it and both were lost (and dropped for good by the next rewrite)."""
    path = str(tmp_path / "rounds.jsonl")
    h.append(path, h.Round(t=1.0, seconds=60.0, map_id="a", map="A"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"t": 2.0, "seconds": 60.0, "map_id": "b", "ma')                # cut off
    h.append(path, h.Round(t=3.0, seconds=60.0, map_id="c", map="C"))
    h.append_lost(path, 4.0, "D", "neues Banner")
    assert [r.t for r in h.load(path)] == [1.0, 3.0]
    assert [d["t"] for d in h._lost_lines(path)] == [4.0]


def test_a_later_result_role_changes_only_the_role(tmp_path):
    """1.11.8: the second look at the result screen corrects the role of the round just saved – a custom game stays
    one, farming stays; the same role again or an unknown round changes nothing."""
    path = str(tmp_path / "rounds.jsonl")
    h.append(path, h.Round(100, 600, "a", "A", role="survivor", custom=True))
    h.append(path, h.Round(200, 600, "a", "A", farming=True))
    assert h.set_result_role(path, 100, "killer").role == "killer"
    assert h.set_result_role(path, 200, "survivor").farming
    got = {r.t: r for r in h.load(path)}
    assert (got[100].role, got[100].custom) == ("killer", True) and (got[200].role, got[200].farming) == ("survivor", True)
    assert h.set_result_role(path, 100, "killer") is None and h.set_result_role(path, 999, "killer") is None
    with pytest.raises(ValueError):
        h.set_result_role(path, 100, "custom")


def test_a_later_balance_is_stored_with_the_round(tmp_path):
    """1.13: the bloodpoint balance read in the lobby after the round – set after the round was saved; old lines
    without it and odd values read as "not read"."""
    path = str(tmp_path / "rounds.jsonl")
    h.append(path, h.Round(100, 600, "a", "A", role="killer"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"t": 200, "seconds": 600, "map_id": "a", "map": "A", "balance": "5000000"}\n')
        fh.write('{"t": 300, "seconds": 600, "map_id": "a", "map": "A", "balance": true}\n')
    assert [r.balance for r in h.load(path)] == [None, None, None]
    full = h._LINES.full
    assert h.set_balance(path, 100, 5000000).balance == 5000000
    # 1.38.24 (PERF-1): the rewrite primes the line cache – the next load parses nothing again (before: the prefix
    # hash no longer matched and the whole file was parsed, twice per round, then the statistics joined anew)
    tail = h._LINES.tail
    assert [r.balance for r in h.load(path)] == [5000000, None, None]
    assert h._LINES.full == full and h._LINES.tail == tail + 1
    assert h.set_balance(path, 100, 5000000) is None and h.set_balance(path, 999, 1) is None
    got = {r.t: r for r in h.load(path)}
    assert (got[100].balance, got[100].role, got[200].balance) == (5000000, "killer", None)
    with pytest.raises(ValueError):
        h.set_balance(path, 100, -1)
    with pytest.raises(ValueError):
        h.set_balance(path, 100, True)


def test_a_correction_keeps_the_other_lines_as_stored(tmp_path):
    """1.57.36 (user's diagnosis: "Ereignis bloodpoints 81 ms" – one balance dumped all 1814 rounds again): only
    the changed round is written anew; every other line stays byte for byte (an old line without the newer fields,
    two rounds of one start), a broken line goes and a lost round's line is written as before, and the file reads the
    same."""
    path = str(tmp_path / "rounds.jsonl")
    h.append(path, h.Round(100, 600, "a", "A", role="killer"))
    old = '{"t": 200, "seconds": 600, "map_id": "b", "map": "B", "wait": -5}'
    twin_a = '{"t": 300, "seconds": 500, "map_id": "c", "map": "C"}'
    twin_b = '{"t": 300, "seconds": 700, "map_id": "d", "map": "D"}'
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(old + "\n" + twin_a + "\n" + "{broken\n" + twin_b + "\n")
    h.append_lost(path, 250, "Lost", "no end")
    before = [(r.t, r.map, r.wait) for r in h.load(path)]
    assert h.set_balance(path, 100, 7).balance == 7
    lines = open(path, encoding="utf-8").read().splitlines()
    assert lines[0] == h._dump(next(r for r in h.load(path) if r.t == 100))     # the changed one, dumped anew
    assert lines[1] == old and lines[3:] == [twin_a, twin_b]                     # the rest as stored, in time order
    assert json.loads(lines[2]) == {"lost": True, "t": 250.0, "map": "Lost", "reason": "no end"}
    h._LINES.forget(path)                                                        # read from the file itself
    assert [(r.t, r.map, r.wait) for r in h.load(path)] == before
    assert [r.balance for r in h.load(path)] == [7, None, None, None]
    assert h.set_balance(path, 300, 9).map == "C"                                # the first of one start
    assert open(path, encoding="utf-8").read().splitlines()[4] == twin_b
    with open(path, "a", encoding="utf-8") as fh:                                # a cut line of a known start
        fh.write('{"t": 200, "seconds": 6\n')
    h.set_balance(path, 100, 8)
    assert [(r.t, r.map, r.wait) for r in h.load(path)] == before


def test_a_rounds_dropouts_are_stored_and_read_back(tmp_path):
    """1.11.9: stalls / stall_max per round; old lines without them and broken values read as not measured."""
    import json
    path = str(tmp_path / "rounds.jsonl")
    h.append(path, h.Round(100, 600, "a", "A", region="eu-central-1", stalls=3, stall_max=0.8))
    h.append(path, h.Round(200, 600, "a", "A"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": 300, "seconds": 600, "map_id": "a", "stalls": "x", "stall_max": 1}) + "\n")
        fh.write(json.dumps({"t": 400, "seconds": 600, "map_id": "a", "stalls": True}) + "\n")
    got = [(r.stalls, r.stall_max) for r in h.load(path)]
    assert got == [(3, 0.8), (None, None), (None, None), (None, None)]


def test_a_line_cut_inside_a_character_breaks_no_correction(tmp_path):
    """1.12.3 (audit): a crash while appending can cut a line inside a multi-byte character ("é" of a label). load()
    skipped that line, but the lost-round reader decoded the whole file as text – UnicodeDecodeError, so every
    correction (role, killer, farming, delete), the lost rounds of the statistics and the tidy-up after the next
    round failed until the file was repaired by hand."""
    path = str(tmp_path / "rounds.jsonl")
    h.append(path, h.Round(t=1000.0, seconds=600.0, map_id="coal", map="Coal Tower"))
    with open(path, "ab") as fh:
        fh.write('{"t": 1500.0, "map": "Café'.encode("utf-8")[:-1])     # cut inside the "é"
    h.append_lost(path, 1800.0, "Coal Tower", "neues Banner", map_id="coal")
    h.append(path, h.Round(t=2000.0, seconds=500.0, map_id="coal", map="Coal Tower"))
    assert [r.t for r in h.load(path)] == [1000.0, 2000.0]
    assert [t for t, _m, _r in h.load_lost(path)] == [1800.0]
    assert [r.t for r in h.load_lost_rounds(path)] == [1800.0]
    assert h.set_role(path, 2000.0, "killer").role == "killer"
    assert [r.role for r in h.load(path)] == ["", "killer"] and len(h.load_lost(path)) == 1


def test_the_fastest_region_at_this_time_of_day():
    """1.38.31 (project review F7): per region, the rounds of the same 3-hour block with a known waiting time –
    median wait, Ø ping; regions with fewer than min_rounds left out; custom/farming never count."""
    import datetime
    base = datetime.datetime(2026, 11, 2, 19, 10).timestamp()            # Monday 19:10 local
    rs = []
    for i, w in enumerate((60, 70, 400)):
        rs.append(h.Round(t=base + i * 86400, seconds=600, map_id="a", map="A", region="eu-central-1", wait=w, ping=30.0))
    for i, w in enumerate((200, 210, 220, 230)):
        rs.append(h.Round(t=base + i * 86400 + 600, seconds=600, map_id="a", map="A", region="us-east-1", wait=w))
    rs.append(h.Round(t=base + 3600 * 5, seconds=600, map_id="a", map="A", region="eu-west-2", wait=5))   # other block
    rs.append(h.Round(t=base, seconds=600, map_id="a", map="A", region="eu-west-2", wait=1, custom=True))
    block, rows = h.regions_at(rs, base + 1800)
    assert block == datetime.datetime.fromtimestamp(base).hour // h.HOUR_BLOCK * h.HOUR_BLOCK
    # 1.55.5 (F8): an even count is the mean of both middle values (210, 220), as history.median
    assert [(c, n, w) for c, n, w, _p in rows] == [("eu-central-1", 3, 70), ("us-east-1", 4, 215.0)]
    assert rows[0][3] == 30.0 and rows[1][3] is None
    assert h.regions_at(rs, base + 1800, min_rounds=4)[1][0][0] == "us-east-1"
    assert h.regions_at([], base)[1] == []


def test_the_round_count_of_today_says_what_it_is_made_of():
    """1.38.52 (user's screenshot: "Rounds 20 · 0 killer / 0 survivor" beside 20 farming rounds): the line under
    today's round count names only the parts that are there and they add up to the count – killer, survivor,
    farming, custom games and rounds whose role was not read."""
    import time as _time
    from fogscout import history as h, overview
    now = _time.time()
    t = h.period_start("day", now) + 60
    farm = [h.Round(t + i, 600, "coal", "Coal Tower", role="killer", farming=True) for i in range(20)]
    d = h.today(farm, now)
    assert d["count"] == 20 and d["custom"] == 0
    assert overview.rounds_parts(d) == "20× Farming"
    mixed = farm[:2] + [h.Round(t + 100, 600, "c", "C", role="killer"), h.Round(t + 101, 600, "c", "C", role="killer"),
                        h.Round(t + 102, 600, "c", "C", role="survivor"), h.Round(t + 103, 600, "c", "C", custom=True),
                        h.Round(t + 104, 600, "c", "C")]
    d = h.today(mixed, now)
    assert overview.rounds_parts(d) == "2× Killer · 1× Survivor · 2× Farming · 1× Custom Game · 1× ohne Rolle"
    assert d["count"] == 7
    d = h.today(mixed + [h.Round(t + 105, 600, "c", "C", custom=True)], now)
    assert "2× Custom Game" in overview.rounds_parts(d)


def test_rounds_beyond_the_limit_go_to_the_archive_not_away(tmp_path, monkeypatch):
    """1.50.6 (review): the tidying dropped the oldest rounds for good. They are appended to rounds-archive.jsonl
    first; when that cannot be written, nothing is taken out; "delete all rounds" removes the archive too."""
    import json
    import os
    monkeypatch.setattr(h, "KEEP", 3)
    p = str(tmp_path / "rounds.jsonl")
    for i in range(40):                                    # far beyond KEEP × 200 bytes: the tidying runs
        h.append(p, h.Round(1000.0 + i, 60.0 + i, "m", "Map %d" % i))
    kept = h.load(p)
    arch = h.archive_path(p, h.ARCHIVE)
    old = [json.loads(line) for line in open(arch, encoding="utf-8")]
    assert len(kept) == 3 and [r.t for r in kept] == [1037.0, 1038.0, 1039.0]
    assert sorted(d["t"] for d in old) == [1000.0 + i for i in range(37)]       # each once, none lost
    assert all(d["map"].startswith("Map ") for d in old)

    def refuse(path, lines):
        raise OSError("disk full")
    monkeypatch.setattr(h, "archive_lines", refuse)
    for i in range(40, 60):
        h.append(p, h.Round(1000.0 + i, 60.0, "m", "Map"))
    assert len(h.load(p)) == 23                            # not archived = not dropped
    h.clear(p)
    assert not os.path.exists(p) and not os.path.exists(arch)


def test_the_file_is_tidied_once_per_slack_not_after_every_round(tmp_path, monkeypatch):
    """1.55.5 (review F1): trimmed to exactly KEEP, every round after the 5000th rewrote the whole file (~150 ms in the
    window's thread). It may now grow by _slack() (5 % of KEEP) before it is cut back to KEEP."""
    import json
    from fogscout import fsops
    monkeypatch.setattr(h, "KEEP", 40)
    assert h._slack() == 2
    p = str(tmp_path / h.FILE)
    writes = []
    real = fsops.write_atomic
    monkeypatch.setattr(fsops, "write_atomic", lambda path, data: (writes.append(path), real(path, data)))
    for i in range(60):
        h.append(p, h.Round(1000.0 + i, 600.0, "m", "Map %d" % i, sys={"gpu_temp": 60.0}))   # > 200 bytes a line
        assert len(h.load(p)) <= h.KEEP + h._slack()
    assert len(writes) == 6                                  # after rounds 43, 46, …, 58 – not one for each of 20
    kept = h.load(p)
    arch = [json.loads(line)["t"] for line in open(h.archive_path(p, h.ARCHIVE), encoding="utf-8")]
    assert arch == [1000.0 + i for i in range(len(arch))] and len(arch) + len(kept) == 60   # each once, in order
    assert kept[0].t == 1000.0 + len(arch)


def test_a_tidied_lost_round_goes_to_the_archive_too(tmp_path, monkeypatch):
    """1.55.5 (review F5): lost-round lines older than the kept rounds were dropped by the tidying – they go to the
    archive with the rounds, in time order."""
    import json
    monkeypatch.setattr(h, "KEEP", 2)
    monkeypatch.setattr(os.path, "getsize", lambda _p: 10 ** 9)
    p = str(tmp_path / h.FILE)
    h.append(p, rnd("A", 600, 1.0))
    h.append_lost(p, 1.5, "Old Lost", "banner", map_id="old", role="killer")
    h.append(p, rnd("B", 600, 2.0))
    h.append(p, rnd("C", 600, 3.0))                          # 3 rounds > KEEP + 0: tidied to B, C
    h.append_lost(p, 3.5, "New Lost", "banner")
    h.append(p, rnd("D", 600, 4.0))                          # tidied to C, D
    assert [r.map for r in h.load(p)] == ["C", "D"] and h.load_lost(p) == [(3.5, "New Lost", "banner")]
    arch = [json.loads(line) for line in open(h.archive_path(p, h.ARCHIVE), encoding="utf-8")]
    assert [d["t"] for d in arch] == [1.0, 1.5, 2.0]
    assert arch[1] == {"lost": True, "t": 1.5, "map": "Old Lost", "reason": "banner", "map_id": "old", "role": "killer"}


def test_lines_archived_before_a_failed_rewrite_are_not_archived_twice(tmp_path, monkeypatch):
    """1.55.5 (review F7): archive first, then rewrite – when the rewrite failed, the next tidying archived the same
    lines again. Lines whose start already stands at the archive's end are left out; an older line that is not
    there yet (a restored round) still goes in."""
    import json
    from fogscout import fsops
    monkeypatch.setattr(h, "KEEP", 5)
    monkeypatch.setattr(os.path, "getsize", lambda _p: 10 ** 9)
    p = str(tmp_path / h.FILE)
    for i in range(5):
        h.append(p, h.Round(1000.0 + i, 600, "m", "M"))
    real = fsops.write_atomic

    def locked(path, data):
        raise PermissionError(13, "locked", path)
    monkeypatch.setattr(fsops, "write_atomic", locked)
    h.append(p, h.Round(1005.0, 600, "m", "M"))              # archived 1000, the rewrite fails (swallowed)
    monkeypatch.setattr(fsops, "write_atomic", real)
    h.append(p, h.Round(1006.0, 600, "m", "M"))              # archives 1000 and 1001 – 1000 only once
    arch = h.archive_path(p, h.ARCHIVE)
    assert [json.loads(line)["t"] for line in open(arch, encoding="utf-8")] == [1000.0, 1001.0]
    assert [r.t for r in h.load(p)] == [1002.0 + i for i in range(5)]
    again = open(arch, encoding="utf-8").read().splitlines()[-1:]           # the 1001 line, handed over again
    h.archive_lines(arch, [h._dump(h.Round(10.0, 600, "m", "M"))] + again)  # 10: older, but new to the archive
    assert [json.loads(line)["t"] for line in open(arch, encoding="utf-8")] == [1000.0, 1001.0, 10.0]


def test_a_round_is_written_as_asdict_wrote_it(tmp_path):
    """1.55.5 (review F2): the lines come from _dump instead of dataclasses.asdict – the same bytes, every field in
    its order; a correction leaves the other lines byte for byte as they were."""
    import dataclasses
    import json
    full = h.Round(t=1700000000.25, seconds=612.5, map_id="coal", map="Coal Tower – Léry's", region="eu-central-1",
                   source="auto", wait=33.0, role="killer", custom=False, farming=True, ping=41.5, killer="The Nurse",
                   sys={"gpu_temp": 61.0, "fps": 118.0}, stalls=2, stall_max=1.5, balance=1234567)
    bare = h.Round(t=5.0, seconds=60.0, map_id="m", map="M")
    for r in (full, bare):
        assert h._dump(r) == json.dumps(dataclasses.asdict(r), ensure_ascii=False)
    assert list(json.loads(h._dump(full))) == [f.name for f in dataclasses.fields(h.Round)]
    p = str(tmp_path / h.FILE)
    h.append(p, bare)
    h.append(p, h.Round(t=9.0, seconds=60.0, map_id="x", map="X"))
    h.append(p, full)
    before = open(p, "rb").read().splitlines()
    assert h.set_farming(p, 9.0, True) is not None
    after = open(p, "rb").read().splitlines()
    assert after[0] == before[0] and after[2] == before[2] and after[1] != before[1]
    assert json.loads(after[1])["farming"] is True


def test_corrections_of_many_rounds_rewrite_the_file_once(tmp_path, monkeypatch):
    """1.55.5 (review F2): marking k rounds was k full rewrites (~100 ms each at 5000 rounds). The *_many functions
    change all of them and write once; they return what they changed, in the order asked, each round once."""
    from fogscout import fsops
    p = str(tmp_path / h.FILE)
    for i in range(6):
        h.append(p, h.Round(t=100.0 + i, seconds=600, map_id="a", map="A", role="survivor", custom=i == 0))
    writes = []
    real = fsops.write_atomic
    monkeypatch.setattr(fsops, "write_atomic", lambda path, data: (writes.append(path), real(path, data)))
    got = h.set_farming_many(p, [103.0, 100.0, 103.0, 999.0], True)
    assert [r.t for r in got] == [103.0, 100.0] and len(writes) == 1
    rs = {r.t: r for r in h.load(p)}
    assert rs[100.0].farming and not rs[100.0].custom and rs[103.0].farming and not rs[101.0].farming
    assert [r.t for r in h.set_role_many(p, [101.0, 102.0], "killer")] == [101.0, 102.0] and len(writes) == 2
    assert [r.t for r in h.set_killer_many(p, [102.0, 104.0], "The Nurse")] == [102.0, 104.0]
    assert [r.t for r in h.set_map_many(p, [104.0, 105.0], "b", "B")] == [104.0, 105.0] and len(writes) == 4
    assert h.set_map_many(p, [104.0], "b", "B") == [] and len(writes) == 4      # nothing changed: nothing written
    assert [r.t for r in h.delete_many(p, [101.0, 105.0, 7.0])] == [101.0, 105.0] and len(writes) == 5
    assert [(r.t, r.role, r.killer, r.map, r.farming) for r in h.load(p)] == [
        (100.0, "survivor", "", "A", True), (102.0, "killer", "The Nurse", "A", False),
        (103.0, "survivor", "", "A", True), (104.0, "killer", "The Nurse", "B", False)]
    assert h.delete(p, 999.0) is None and h.set_killer(p, 100.0, "The Hag").killer == "The Hag"


def test_the_median_wait_of_an_even_count_is_the_mean_of_both_middle_values():
    """1.55.5 (review F8): wait_summary and regions_at took the upper middle value; history.median averages."""
    import datetime
    base = datetime.datetime(2026, 11, 2, 19, 10).timestamp()
    rs = [h.Round(t=base + i * 86400, seconds=600, map_id="a", map="A", region="eu-central-1", wait=w)
          for i, w in enumerate((10.0, 20.0, 40.0, 100.0))]
    assert h.wait_summary(rs)["median"] == 30.0
    assert h.wait_summary(rs[:3])["median"] == 20.0                      # an odd count: the middle one, as before
    assert h.regions_at(rs, base, min_rounds=1)[1][0][2] == 30.0


def test_a_correction_waits_for_a_restore_that_is_writing_and_both_stay(tmp_path, monkeypatch):
    """1.55.5 (review F14): a restore (its own thread) and a correction in the window's thread (the balance after a
    round) both read, change and write rounds.jsonl – the one writing last threw the other's change away. With
    history.LOCK the correction waits until the restore has written, then reads its result."""
    import threading
    from fogscout import backups, fsops
    data, src = str(tmp_path / "data"), str(tmp_path / "src")
    os.makedirs(data)
    os.makedirs(src)
    p = os.path.join(data, h.FILE)
    h.append(p, h.Round(t=1000.0, seconds=600, map_id="a", map="A"))
    h.append(os.path.join(src, h.FILE), h.Round(t=500.0, seconds=600, map_id="b", map="B"))
    zpath = str(tmp_path / "b.zip")
    backups.archive(src, zpath, {})
    entered, go = threading.Event(), threading.Event()
    real = fsops.write_atomic

    def slow(path, data_):
        if threading.current_thread().name == "restore" and path == p:
            entered.set()
            assert go.wait(30)
        return real(path, data_)
    monkeypatch.setattr(fsops, "write_atomic", slow)
    restore = threading.Thread(target=backups.restore, args=(data, zpath), name="restore")
    restore.start()
    assert entered.wait(30)                                  # the restore has read the file and is writing it
    done = []
    balance = threading.Thread(target=lambda: done.append(h.set_balance(p, 1000.0, 123456)))
    balance.start()
    balance.join(0.3)
    assert balance.is_alive() and done == []                 # waits for the lock instead of reading the old file
    go.set()
    restore.join(30)
    balance.join(30)
    assert done and done[0].balance == 123456
    assert [(r.t, r.balance) for r in h.load(p)] == [(500.0, None), (1000.0, 123456)]   # the restore and the balance


@pytest.mark.skipif(not hasattr(__import__("time"), "tzset"), reason="time.tzset: not on Windows")
def test_last_week_starts_on_its_monday_also_in_the_week_after_a_clock_change(monkeypatch):
    """1.55.5 (review F10): the week before was start − 7 × 24 h – in the week after the clocks went back (Europe/Berlin,
    25.10.2026) that is Monday 01:00, a round in its first hour fell out of "Vorwoche" (overview tiles and the week
    Claude gets)."""
    import time
    from types import SimpleNamespace
    from fogscout import overview, statsclaude
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        now = time.mktime((2026, 10, 28, 12, 0, 0, 0, 0, -1))                   # Wednesday after the change
        early = h.Round(t=time.mktime((2026, 10, 19, 0, 30, 0, 0, 0, -1)), seconds=600, map_id="a", map="A",
                        role="killer")                                          # Monday 00:30 of the week before
        this = h.Round(t=now - 3600, seconds=600, map_id="a", map="A", role="killer")
        wk = statsclaude.week([early, this], {}, now)
        assert wk["last_week"]["rounds"] == 1 and wk["this_week"]["rounds"] == 1
        app = SimpleNamespace(_joined=lambda: SimpleNamespace(rounds=[early, this], off={}))
        tiles, _note = overview.week(app, now)
        assert tiles[0].value == "1" and tiles[0].sub.startswith("Vorwoche 1")
    finally:
        monkeypatch.undo()
        time.tzset()


def test_a_farming_round_without_a_wait_counts_as_instant_for_bloodpoints_per_hour():
    """1.55.5 (review F11): the tables show "sofort" for a farming round without a measured wait (its lobby filled at
    once); BP per hour with waiting gave it the average wait of the others. It counts 0 s now; other rounds without
    a wait keep the average, a custom game is never "sofort"."""
    from fogscout import dashboard
    from fogscout.official import Match
    rs = [h.Round(t=1, seconds=500, map_id="a", map="A", role="survivor", wait=60.0),
          h.Round(t=2, seconds=500, map_id="a", map="A", role="survivor", wait=120.0),
          h.Round(t=3, seconds=500, map_id="a", map="A", role="survivor", farming=True),              # sofort
          h.Round(t=4, seconds=500, map_id="a", map="A", role="survivor"),                            # unknown
          h.Round(t=5, seconds=500, map_id="a", map="A", role="survivor", farming=True, custom=True)]  # unknown
    ms = [Match(t=0, map="A", seconds=600, bp=10000) for _r in rs]
    assert dashboard.bp_rate(list(zip(rs, ms))).wait_s == 60 + 120 + 0 + 90 + 90


def test_a_line_no_reader_can_take_is_kept_aside_and_never_deleted_by_a_correction(tmp_path):
    """1.57.70 (deep review DATA-01, reproduced): _rewrite wrote only what could be read – an unreadable round line
    vanished from the statistics and the next correction (set_balance, twice per round) deleted it for good. Now it
    goes to rounds.jsonl.rejected first; a lost round with a number too big for a float no longer breaks the join."""
    p = str(tmp_path / h.FILE)
    t0 = 1_780_000_000.0
    h.append(p, rnd("Coal Tower", 600, t=t0))
    broken = '{"t": %r, "seconds": 1e300, "map_id": "x"}' % (t0 + 1000)
    lost = json.dumps({"lost": True, "t": t0 + 2000, "map": "A", "reason": "x", "ping": 10 ** 400, "wait": 10 ** 400})
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(broken + "\n" + lost + "\n")
    lost_rounds = h.load_lost_rounds(p)                                # raised OverflowError before
    assert len(lost_rounds) == 1 and lost_rounds[0].ping is None and lost_rounds[0].wait is None
    h.set_balance(p, t0, 123456)
    assert [r.balance for r in h.load(p)] == [123456]
    with open(p + h.REJECTED, encoding="utf-8") as fh:
        assert fh.read().splitlines() == [broken]
    with open(p, encoding="utf-8") as fh:
        assert broken not in fh.read()
    h.set_balance(p, t0, 7)                                            # nothing odd left: nothing added again
    with open(p + h.REJECTED, encoding="utf-8") as fh:
        assert fh.read().splitlines() == [broken]
