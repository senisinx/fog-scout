"""CR-009 (code review): stored values the program reads back (rounds, matches, index, montages, project heads) –
Infinity, NaN, 10**400, 1e300 or a broken field are skipped or "not known", never a crash or a frozen window; the
time axes of the charts are counted back from the newest bucket."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fogscout import builds, dashboard, history, medialib, official, project, recindex  # noqa: E402

NOW = 1_790_000_000.0


def test_a_round_of_1970_next_to_one_of_today_gives_30_buckets_in_few_steps(monkeypatch):
    calls = [0]
    real = official.bucket_start

    def counted(t, unit):
        calls[0] += 1
        return real(t, unit)
    monkeypatch.setattr(official, "bucket_start", counted)
    span = official.bucket_span(real(1.0, "hour"), real(NOW, "hour"), "hour")
    assert len(span) == official.MAX_BUCKETS and span == sorted(span) and span[-1] == real(NOW, "hour")
    assert calls[0] <= official.MAX_BUCKETS + 1                               # not a million steps
    r = history.Round(t=NOW, seconds=600.0, map_id="x", map="X", balance=5)
    old = history.Round(t=1.0, seconds=600.0, map_id="x", map="X", balance=1)
    assert len(dashboard.balance_trend([old, r], "hour")) == official.MAX_BUCKETS
    old.wait = r.wait = 30.0
    old.role = r.role = "killer"
    assert len(dashboard.wait_trend([old, r], "hour")) == official.MAX_BUCKETS
    assert len(history.sys_trend([history.Round(t=1.0, seconds=1, map_id="x", map="X", sys={"gpu_temp": 60.0}),
                                  history.Round(t=NOW, seconds=1, map_id="x", map="X",
                                                sys={"gpu_temp": 61.0})],
                                 "day")) == official.MAX_BUCKETS


def test_the_span_counted_back_matches_the_forward_walk_over_a_dst_change(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        for start, end in ((1761429600, 1761451200), (1743199200, 1743217200)):     # autumn, spring
            first, last = official.bucket_start(start, "hour"), official.bucket_start(end, "hour")
            b, walk = first, []
            while b <= last:
                walk.append(b)
                b = official._next_bucket(b, "hour")
            assert official.bucket_span(first, last, "hour") == walk[-official.MAX_BUCKETS:]
    finally:
        monkeypatch.undo()
        time.tzset()


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")


def test_rounds_with_infinite_or_huge_values_load_as_not_known(tmp_path):
    path = str(tmp_path / "rounds.jsonl")
    _write(path, [
        '{"t": %d, "seconds": 600, "map_id": "a", "wait": Infinity, "ping": NaN, "stalls": 2, "stall_max": Infinity,'
        ' "sys": {"gpu_temp": Infinity, "cpu": 40}}' % NOW,
        '{"t": %s, "seconds": 600, "map_id": "b"}' % ("1" + "0" * 400),          # 10**400: an int no float holds
        '{"lost": true, "t": %s, "map": "c"}' % ("1" + "0" * 400),
        '{"lost": true, "t": %d, "map": "d", "wait": 1e308, "ping": true}' % NOW,
    ])
    rounds = history.load(path)
    assert [r.map_id for r in rounds] == ["a"]
    r = rounds[0]
    assert r.wait is None and r.ping is None and r.stall_max is None and r.sys == {"cpu": 40.0}
    lost = history.load_lost_rounds(path)
    assert [x.map for x in lost] == ["d"] and lost[0].wait is None and lost[0].ping is None


def test_gaps_and_match_fields_out_of_range_are_skipped(tmp_path):
    path = str(tmp_path / "official.jsonl")
    _write(path, [{"gap": True, "from": 1e300, "to": NOW}, {"gap": True, "from": NOW, "to": NOW - 10},
                  '{"gap": true, "from": %s, "to": 1}' % ("1" + "0" * 400),
                  {"gap": True, "from": NOW - 10, "to": NOW}])
    assert official.load_gaps(path) == [(NOW - 10, NOW)]
    extra = official._stored_extra({"duration": float("inf"), "score": {"a": float("nan"), "b": 5, "c": True},
                                    "prestige": float("inf"), "level": 3})
    assert extra["duration"] == history.MAX_SECONDS or extra["duration"] == 0.0
    assert extra["score"] == {"b": 5.0} and extra["prestige"] is None and extra["level"] == 3


def test_an_index_line_with_a_number_no_float_holds_is_skipped(tmp_path):
    with open(tmp_path / recindex.INDEX, "w", encoding="utf-8") as fh:
        fh.write('{"t": %s, "file": "a.mkv"}\n' % ("1" + "0" * 400))
        fh.write('{"t": 5, "file": "b.mkv", "marks": [1, %s, 2]}\n' % ("1" + "0" * 400))
    recs = recindex.load_index(str(tmp_path))                  # no OverflowError: the number is "not known"
    assert [r.file for r in recs] == ["a.mkv", "b.mkv"] and recs[0].t == 0.0 and recs[1].marks == [1.0, 2.0]


def test_a_montage_with_an_infinite_part_or_date_is_listed_without_it(tmp_path):
    d = {"format": project.FORMAT, "version": 2, "name": "M", "saved": 1e300,
         "sources": [str(tmp_path / "a.mkv")],
         "parts": [[0, "Infinity", 1], [0, 10, 1], [0, 1e308, 1e-300]]}
    (tmp_path / "a.mkv").write_bytes(b"x")
    (tmp_path / ("m" + project.EXT)).write_text(json.dumps(d).replace('"Infinity"', "Infinity"), encoding="utf-8")
    items = medialib.montage_items(str(tmp_path))
    assert len(items) == 1 and items[0].seconds == 10.0 and history.plausible(items[0].when)
    assert medialib.fmt_when(items[0].when)


def test_a_project_head_with_a_broken_version_is_unreadable_not_a_crash(tmp_path):
    for bad in ('"x"', "[1]", "1e400", '{"a": 1}'):
        p = tmp_path / ("p" + project.EXT)
        p.write_text('{"format": "%s", "version": %s, "saved": %s}' % (project.FORMAT, bad, "1" + "0" * 400),
                     encoding="utf-8")
        project._SCAN_CACHE.clear()
        e = project.read_entry(str(p))
        assert e is not None and not e.ok and e.version == 0 and e.saved == 0.0
    project._SCAN_CACHE.clear()
    assert len(project.scan(str(tmp_path))) == 1


def test_prestige_series_is_bounded(monkeypatch):
    class M:
        def __init__(self, t):
            self.t, self.character, self.prestige, self.level = t, "Meg", 1, 2
    monkeypatch.setattr(builds, "_graded", lambda m: True)
    assert len(builds.prestige_series([M(1.0), M(NOW)], "Meg", "hour")) == official.MAX_BUCKETS
