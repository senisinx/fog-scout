"""Score event tracker, step 4 (1.57.55): each event counted once over several looks (fogscout.scorecount)."""
from fogscout.scorecount import CAP, ScoreCounter, names_fit
from fogscout.scoreevents import Row

H = 21            # a name's height in the box at 1440p
STEP = 85         # one row lower (measured: a new event pushes the others down by ~85–91 px)


def row(name, points=None, y=480, category="boldness", capped=False):
    return Row(word=(400, y, 400 + 12 * len(name), y + H), name=name, points=points, capped=capped,
               category=category)


def feed(counter, looks, step=0.25):
    """looks: one list of rows per look, ``step`` s apart; then the match ends."""
    for i, rows in enumerate(looks):
        counter.feed(i * step, rows)
    counter.flush()
    return counter


def test_an_event_seen_over_several_looks_is_counted_once():
    c = feed(ScoreCounter(), [[row("VAULT", 100)]] * 10)
    assert [(e.name, e.points, e.category) for e in c.events] == [("VAULT", 100, "boldness")]
    assert c.totals()["boldness"] == 100 and c.role() == "survivor"


def test_a_new_event_on_top_pushes_the_old_one_down_and_both_count_once():
    looks = [[row("BOLD", 13)]] * 2 + [[row("VAULT", 100), row("BOLD", 13, y=480 + STEP)]] * 6 + [[row("VAULT", 100)]] * 4
    c = feed(ScoreCounter(), looks)
    assert sorted((e.name, e.points) for e in c.events) == [("BOLD", 13), ("VAULT", 100)]


def test_two_equal_events_at_once_are_two_events():
    looks = [[row("BOLD", 2), row("BOLD", 2, y=480 + STEP)]] * 6
    assert [e.points for e in feed(ScoreCounter(), looks).events] == [2, 2]


def test_a_name_cut_while_sliding_in_belongs_to_the_same_event():
    looks = [[row("OVERY", 40, category="survival")], [row("COVERY", 40, category="survival")]] + \
            [[row("RECOVERY", 40, category="survival")]] * 6
    c = feed(ScoreCounter(), looks)
    assert [(e.name, e.points) for e in c.events] == [("RECOVERY", 40)]
    assert names_fit("CAPED", "ESCAPED") and names_fit("SURVIVORFOUN", "SURVIVORFOUND")
    assert not names_fit("HEAL", "REPAIRS")


def test_a_growing_counter_counts_its_final_value_and_misreadings_are_outvoted():
    values = [100, 162, 250, 340, 488, 488, 4488, 488, 488, None, 488]          # one misreading, one unreadable
    looks = [[row("REPAIRS", v, category="objective")] for v in values]
    assert [e.points for e in feed(ScoreCounter(), looks).events] == [488]


def test_a_row_seen_once_or_never_read_is_not_counted():
    c = feed(ScoreCounter(), [[row("CHASED", 300)], [], [], [], [], [row("HIT", None, category="brutality")] ,
                              [row("HIT", None, category="brutality")], [], [], [], []])
    assert c.events == [] and c.dropped == 2


def test_a_different_category_is_a_different_event():
    looks = [[row("CHASE", 100, category="hunter")]] * 3 + [[row("CHASE", 100, category="boldness")]] * 3
    assert sorted(e.category for e in feed(ScoreCounter(), looks).events) == ["boldness", "hunter"]


def test_a_row_never_moves_up_a_lower_row_is_not_an_earlier_one():
    looks = [[row("BOLD", 5, y=480 + STEP)]] * 3 + [[row("BOLD", 7, y=480)]] * 3      # the second one is newer
    assert [e.points for e in feed(ScoreCounter(), looks).events] == [5, 7]


def test_max_fills_the_category_and_totals_stop_at_the_cap():
    looks = [[row("HOOKED", None, category="sacrifice", capped=True)]] * 4
    c = feed(ScoreCounter(), looks)
    assert c.events[0].capped and c.events[0].points == 0 and c.totals()["sacrifice"] == CAP
    many = ScoreCounter()
    for i in range(30):                     # 30 events of 500 = 15 000 → the cap
        for k in range(3):
            many.feed(i * 2 + k * 0.25, [row("SURVIVORFOUND", 500, category="hunter")])
    many.flush()
    assert len(many.events) == 30 and many.totals()["hunter"] == CAP and many.role() == "killer"


def test_an_event_ends_after_the_gap_and_is_returned_then():
    c = ScoreCounter()
    for i in range(4):
        assert c.feed(i * 0.25, [row("VAULT", 100)]) == []
    ended = c.feed(2.0, [])
    assert [e.name for e in ended] == ["VAULT"] and c.flush() == []


def test_a_category_total_is_its_newest_ring_plus_the_events_after_it():
    def ringed(name, points, ring, y=480):
        r = row(name, points, y=y, category="objective")
        r.ring = ring
        return r
    looks = [[ringed("REPAIRS", 500, 0.40)]] * 4 + [[]] * 5 + \
            [[ringed("GREATSKILLCHECK", 300, 0.43)]] * 4 + [[]] * 5 + \
            [[row("UNLOCKING", 476, category="objective")]] * 4                      # no ring read
    c = feed(ScoreCounter(), looks)
    assert [e.ring for e in c.events] == [0.40, 0.43, None]
    assert c.totals()["objective"] == 4300 + 476                                   # not 500 + 300 + 476
    # a missed event does not stay missing: the next ring has it
    c2 = feed(ScoreCounter(), [[ringed("REPAIRS", 500, 0.40)]] * 4)
    assert c2.totals()["objective"] == 4000


def test_an_event_takes_the_ring_of_its_last_looks():
    looks = []
    for v in (0.30, 0.31, 0.38, 0.40, 0.40, 0.41):                               # filling while it slides in
        r = row("HEAL", 120, category="altruism")
        r.ring = v
        looks.append([r])
    assert feed(ScoreCounter(), looks).events[0].ring == 0.40


def test_a_ring_far_below_the_running_total_is_a_misreading():
    def ringed(points, ring):
        r = row("REPAIRS", points, category="objective")
        r.ring = ring
        return r
    looks = [[ringed(500, 0.60)]] * 4 + [[]] * 5 + [[ringed(300, 0.05)]] * 4 + [[]] * 5 + [[ringed(200, 0.65)]] * 4
    c = feed(ScoreCounter(), looks)
    assert [e.ring for e in c.events] == [0.60, 0.05, 0.65]
    assert c.totals()["objective"] == 6500                     # 6000, the 5 % ring not believed (+300), then 6500
    # missed events: a ring above the running total is always believed
    up = feed(ScoreCounter(), [[ringed(500, 0.10)]] * 4 + [[]] * 5 + [[ringed(100, 0.50)]] * 4)
    assert up.totals()["objective"] == 5000
