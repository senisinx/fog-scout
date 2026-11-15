"""Statistics built from data already stored (rounds.jsonl + official.jsonl): survival share, perk pairs, bloodpoints
per loadout entry, weekday × time of day, connection, waiting-time trend, form within a session – pure logic, every
expected value worked out by hand in the comments."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fogscout import builds, dashboard, official, records  # noqa: E402
from fogscout.history import Round  # noqa: E402
from fogscout.official import Match, Player  # noqa: E402


def _t(day, hour=20, minute=0):
    """Local time in the week of Monday 16 November 2026 (day 16 = Monday)."""
    return datetime.datetime(2026, 11, day, hour, minute).timestamp()


def _killer(kills, perks=(), bp=0, t=0.0):
    stats = ["SACRIFICED"] * kills + ["ESCAPED"] * (4 - kills)
    return Match(t=t, map="Coal Tower", role="killer", character="The Nurse", seconds=600, bp=bp,
                 opp=[Player(role="survivor", status=s) for s in stats], perks=[[p, p] for p in perks])


def _survivor(escaped, perks=(), bp=0, t=0.0, seconds=600.0, duration=0.0, killer=""):
    opp = [Player(role="killer", character=killer, status="")] if killer else []
    return Match(t=t, map="Coal Tower", role="survivor", character="Meg Thomas", seconds=seconds, duration=duration,
                 status="ESCAPED" if escaped else "SACRIFICED", bp=bp, opp=opp, perks=[[p, p] for p in perks])


def _round(t=0.0, seconds=600.0, map_label="Coal Tower", role="killer", **kw):
    return Round(t, seconds, "coal", map_label, role=role, **kw)


# ------------------------------------------------------------------ 1. survival share
def test_survival_share_per_map_and_opposing_killer():
    pairs = [(_round(map_label="Coal Tower"), _survivor(True, seconds=300, duration=600, killer="The Nurse")),   # 0.5
             (_round(map_label="Coal Tower"), _survivor(True, seconds=600, duration=600, killer="The Nurse")),   # 1.0
             (_round(map_label="Badham"), _survivor(False, seconds=700, duration=600, killer="The Blight")),     # 1.0 (capped)
             (_round(map_label="Badham"), _survivor(False, seconds=300, duration=0.0, killer="The Blight")),     # no length
             (_round(map_label="Badham"), _killer(4))]                                                         # killer
    s = dashboard.survival(pairs, lambda k: k.upper())
    n, mean = s["all"]
    assert n == 3 and abs(mean - 2.5 / 3) < 1e-9                         # (0.5 + 1 + 1) / 3
    assert s["maps"] == [("Coal Tower", 2, 0.75), ("Badham", 1, 1.0)]  # most played first
    assert s["killers"] == [("THE NURSE", 2, 0.75), ("THE BLIGHT", 1, 1.0)]
    assert dashboard.survival([]) == {"all": (0, None), "maps": [], "killers": []}


# ------------------------------------------------------------------ 2. + 3. perk pairs, bloodpoints per entry
def _loadouts():
    return [(None, _killer(4, "ABCD", bp=30000)), (None, _killer(2, "ABEF", bp=20000)), (None, _killer(0, "AC")),
            (None, _survivor(True, "XY", bp=10000)), (None, _survivor(False, "XY"))]


def test_perk_pairs_count_each_combination_once_and_compare_without_it():
    got = builds.perk_pairs(_loadouts())
    assert [(p.role, p.name, p.n) for p in got] == [("killer", "A + B", 2), ("killer", "A + C", 2),
                                                     ("survivor", "X + Y", 2)]    # pairs played once: left out
    ab, ac, xy = got
    # A+B: kills 4 and 2 → 3; without it only the third killer match (0 kills) → 0; share 2 of 3 killer loadouts
    assert ab.mean == 3 and ab.mean_without == 0 and abs(ab.share - 2 / 3) < 1e-9
    assert ab.bp_mean == 25000 and ab.bp_without is None                 # the match without it had no bloodpoints
    assert ac.mean == 2 and ac.mean_without == 2                         # 4, 0 → 2; without: the 2-kill match
    assert ac.bp_mean == 30000 and ac.bp_without == 20000
    assert xy.mean == 0.5 and xy.mean_without is None and xy.bp_mean == 10000
    # ABCD and ABEF: 6 each, A+B in both → 11; A+C is one of ABCD's; X+Y → 12 distinct pairs
    assert len(builds.perk_pairs(_loadouts(), minimum=1)) == 12
    assert builds.perk_pairs([(None, _killer(4, "AAB"))], minimum=1)[0].name == "A + B"   # a doubled perk: one pair


def test_items_carry_the_bloodpoints_with_and_without_them():
    got = {(i.kind, i.role, i.name): i for i in builds.items(_loadouts())}
    a, e, x = got[("perk", "killer", "A")], got[("perk", "killer", "E")], got[("perk", "survivor", "X")]
    assert a.n == 3 and a.bp_mean == 25000 and a.bp_without is None      # (30000 + 20000) / 2; nothing without A
    assert e.bp_mean == 20000 and e.bp_without == 30000
    assert got[("perk", "killer", "C")].bp_mean == 30000 and got[("perk", "killer", "C")].bp_without == 20000
    assert x.bp_mean == 10000 and x.bp_without is None


# ------------------------------------------------------------------ 4. weekday × time of day
def test_the_result_by_weekday_and_time_of_day():
    pairs = [(_round(_t(16, 10)), _killer(4)), (_round(_t(16, 11, 30)), _killer(2)),   # Monday 09–12: 3.0 (2)
             (_round(_t(16, 22)), _killer(1)),                                         # one round: no cell
             (_round(_t(17, 1), role="survivor"), _survivor(True)),                    # Tuesday 00–03: 50 %
             (_round(_t(17, 2, 30), role="survivor"), _survivor(False)),
             (_round(_t(17, 5)), Match(t=0, map="x", role="killer"))]                  # unknown result
    g = dashboard.time_grids(pairs)
    k, s = g["killer"], g["survivor"]
    assert k.rows == ["Montag"] and k.columns == ["09–12"] and k.cells == {("Montag", "09–12"): (3.0, 2)}
    assert k.top == 4.0 and not k.share and k.n == 3
    assert s.rows == ["Dienstag"] and s.columns == ["00–03"] and s.cells == {("Dienstag", "00–03"): (0.5, 2)}
    assert s.top == 1.0 and s.share and s.n == 2 and "100 %" in s.legend
    empty = dashboard.time_grids([])
    assert empty["killer"].rows == [] and empty["survivor"].cells == {}


# ------------------------------------------------------------------ 5. connection
def test_ping_bands_and_stalls_against_the_result():
    pairs = [(_round(ping=30.0, stalls=0), _killer(4)),
             (_round(ping=50.0, stalls=2), _killer(2)),
             (_round(ping=40.0, role="survivor"), _survivor(True)),          # 40 ms: the middle band
             (_round(ping=80.0, role="survivor"), _survivor(False)),         # 80 ms: still the middle band
             (_round(ping=81.0, role="survivor"), _survivor(False)),
             (_round(stalls=0, role="survivor"), _survivor(True)),           # no ping, gaps measured
             (_round(ping=20.0, stalls=1), Match(t=0, map="x", role="killer"))]   # unknown result: not counted
    got = dict(dashboard.connection(pairs))
    assert list(got) == ["<40", "40-80", ">80", "stalls", "no_stalls"]
    assert (got["<40"].kills, got["<40"].kills_n, got["<40"].survivor_n) == (4, 1, 0)
    assert got["40-80"].kills == 2 and got["40-80"].escape_share == 0.5 and got["40-80"].survivor_n == 2
    assert got[">80"].kills is None and got[">80"].escape_share == 0.0
    assert got["stalls"].kills == 2 and got["stalls"].survivor_n == 0
    assert got["no_stalls"].kills == 4 and got["no_stalls"].escape_share == 1.0
    assert dashboard.connection([(_round(), _killer(3))]) == []         # neither ping nor gaps measured


# ------------------------------------------------------------------ 6. waiting-time trend
def test_the_median_waiting_time_per_day_and_role():
    d16, d18 = _t(16, 10), _t(18, 9)
    rounds = [_round(d16, wait=30.0), _round(_t(16, 12), wait=90.0), _round(_t(16, 13), wait=60.0, role="survivor"),
              _round(d18, wait=10.0),
              _round(_t(16, 14), wait=500.0, custom=True), _round(_t(16, 15), wait=500.0, farming=True),
              _round(_t(16, 16), wait=500.0, role=""), _round(_t(17, 10))]                 # no wait
    got = dashboard.wait_trend(rounds, "day")
    day = official.bucket_start
    assert got == [(day(d16, "day"), {"killer": (60.0, 2), "survivor": (60.0, 1)}),       # median of 30 and 90
                   (day(_t(17, 0), "day"), {}),                                          # a day without: empty
                   (day(d18, "day"), {"killer": (10.0, 1)})]
    assert dashboard.wait_trend([], "week") == []


# ------------------------------------------------------------------ 7. form within a session
def test_the_result_by_the_rounds_place_in_its_session():
    rs, linked = [], {}

    def play(t, seconds, match=None):
        r = _round(t, seconds)
        rs.append(r)
        if match is not None:
            linked[id(r)] = match
        return t + seconds

    t = _t(16, 18)
    t = play(t, 600, _killer(4, bp=20000))              # session 1: 1st
    t = play(t + 100, 600, _killer(2))                  # 2nd
    t = play(t + 60, 600, _survivor(True))              # 3rd
    t = play(t + 60, 600, _killer(0))                   # 4th
    t = play(t + 60, 600, _killer(1))                   # 5th → "4th and later"
    t = play(t + 7200, 600, _killer(3))                 # two hours later: session 2, 1st
    play(t + 60, 600)                                   # 2nd, no match: counts for the place only
    rs.reverse()                                        # any order in: sorted by start
    first, second, third, later = records.session_form(rs, linked)
    assert (first.kills, first.kills_n, first.bp) == (3.5, 2, 20000)       # 4 and 3; only the first had BP
    assert (second.kills, second.kills_n, second.survivor_n) == (2, 1, 0)
    assert (third.kills_n, third.escape_share) == (0, 1.0)
    assert (later.kills, later.kills_n) == (0.5, 2)                         # 0 and 1
    assert all(f.kills_n == f.survivor_n == 0 for f in records.session_form([], {}))
