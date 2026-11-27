"""Mixin of the page "Rechner" (1.51, Saru: "einen Art Rechner bei dem ich verschiedene Perks kombinieren kann … für
beide Seiten … Diminishing returns … für mehrere Leute die Builds angeben"; 1.52: "für alle Elemente von Diminishing
Returns … Haste, Repair, Vault", only as many builds as Survivors, every modifier listed, the best next perk, two
builds side by side): up to four Survivor builds and one Killer build for one area at a time – the arithmetic is
gencalc.py, the numbers perkdata.json. Everything stays on this PC; the builds are kept in the setting ``calc``."""
from __future__ import annotations

from . import gencalc, perkicons
from . import uimodel as ui
from .i18n import N_, _

NONE = "—"
SLOTS = 4                                     # perks per build
ADDON_SLOTS = 2                               # add-ons of an item or of the Killer's power
PERK_PX = 174                                 # width of a perk choice (four fit beside the name at 1100 px)
NAME_PX = 84                                  # width of "Survivor 1" / "Item" before the choices
PERK_MAX = 280                                # 1.55: a choice grows to this where the window has room – enough
                                              # for "Scourge Hook: Pain Resonance" beside its picture
EXAMPLE_SURVIVOR = ("Prove Thyself",)          # 1.57.95: "Beispiel laden"
EXAMPLE_KILLER = ("Corrupt Intervention",)
TIP_ROWS = 6                                  # 1.57.95: proposals of "Bester nächster Perk" with a button each
BESIDE_FROM = 1240                            # 1.55: page width from which the result stands beside the choices
                                              # (the builds need 870 px for four perks in one line, the tables 600)
GREAT_CHOICES = (0, 25, 50, 75, 100)          # % of Skill Checks hit Great
MISS_CHOICES = (0, 5, 10, 20)                 # % missed
KICK_CHOICES = (0, 1, 2, 3, 4)
KICK_AT_CHOICES = (25, 50, 75, 90)            # % progress when the Killer comes
AWAY_CHOICES = (0, 10, 20, 30, 45, 60)        # s the Survivors stay away after a kick
WALK_CHOICES = (0, 5, 10, 20)                 # s between two Generators
STACK_CHOICES = (100, 50, 0)                  # % of a Survivor perk's Tokens that count (0 = one Token)
COUNT_CHOICES = tuple(range(0, 14))
REPAIR_OPTS = ("great", "miss", "kicks", "kick_at", "away", "walk")       # asked only for Generators
CALC_DEFAULTS = {"area": gencalc.REPAIR, "n": 4, "survivors": [[[], ""] for _i in range(gencalc.MAX_SURVIVORS)],
                 "killer": [], "counts": {}, "killer_name": "", "killer_addons": [], "great": 50, "miss": 0, "kicks": 1, "kick_at": 50, "away": 20, "walk": 0,
                 "stacks": 100, "diminishing": True, "compare": None}

AREAS = {
    "repair": N_("Reparieren (Generatoren)"),
    "heal": N_("Heilen und Erholen"),
    "move": N_("Bewegung (Haste, Hindered)"),
    "vault": N_("Vaults (Fenster, Paletten)"),
    "objects": N_("Totems, Truhen, Tore"),
    "hook": N_("Haken (Befreien, Sabotieren)"),
    "k_move": N_("Killer: Bewegung"),
    "k_action": N_("Killer: Aktionen"),
    "k_attack": N_("Killer: Erholung nach Angriffen"),
}
ROWS = {
    "heal_other": N_("Andere heilen"), "heal_dying": N_("Sterbende aufheben"),
    "heal_self": N_("Sich selbst heilen (Med-Kit)"), "recover": N_("Erholen am Boden (bis 95 %)"),
    "run": N_("Rennen"), "walk": N_("Gehen"), "crouch": N_("Ducken"), "crawl": N_("Kriechen"),
    "window_fast": N_("Fenster, schnell"), "window_medium": N_("Fenster, mittel"),
    "window_slow": N_("Fenster, langsam"), "pallet_fast": N_("Palette, schnell"),
    "pallet_slow": N_("Palette, langsam"),
    "cleanse": N_("Totem reinigen"), "bless": N_("Totem segnen"), "bless_hex": N_("Hex-Totem segnen"),
    "chest": N_("Truhe öffnen"), "gate": N_("Ausgangstor öffnen"),
    "unhook": N_("Befreien"), "sabotage": N_("Haken sabotieren"),
    "k460": N_("Killer mit 4,6 m/s"), "k440": N_("Killer mit 4,4 m/s"), "k385": N_("Killer mit 3,85 m/s"),
    "carry": N_("Tragen"), "kbase": N_("Grundgeschwindigkeit"),
    "kvault": N_("Fenster-Vault"), "break": N_("Palette oder Wand zerstören"),
    "damage": N_("Generator beschädigen"), "locker": N_("Spind durchsuchen"),
    "pickup": N_("Aufheben und Ablegen"), "hooking": N_("Aufhängen"),
    "hit": N_("Nach einem Treffer"), "miss": N_("Nach einem Fehlschlag"),
}
# when a modifier holds (perkdata.json "when") – the calculator counts every condition as met
WHEN = {
    "injured": N_("verletzt"), "healthy": N_("gesund"), "gates": N_("Tore mit Strom"),
    "boon": N_("im Boon-Bereich"), "hex": N_("solange das Hex-Totem steht"), "trigger": N_("nach Auslösung"),
    "near": N_("in Reichweite"), "unhook": N_("nach einer Befreiung"), "obsession": N_("mit der Obsession"),
    "terror": N_("im Terrorradius"), "tokens": N_("{n} Tokens"),
    "hurt": N_("{n} verletzt, sterbend oder am Haken"), "hooks": N_("{n} Hakenstufen"),
    "alive": N_("{n} Survivor am Leben"),
}


# what "Anzahl" means for a Killer perk (perkdata.json has the same in English, as documentation)
COUNT_MEANS = {
    "Thanatophobia": N_("verletzte, sterbende oder aufgehängte Survivor"),
    "Dying Light / Cull the Weak": N_("Tokens (Haken an anderen als der Obsession)"),
    "Hex: Pentimento": N_("neu entzündete Totems"),
    "Distressing": N_("1 = die Survivor sind im Terrorradius"),
    "Scourge Hook: Weeping Wounds": N_("1 = die Survivor leiden nach dem Heilen unter dem Effekt"),
    "Pop Goes the Weasel": N_("Kicks mit aktivem Perk (20 % statt 5 %)"),
    "Scourge Hook: Pain Resonance": N_("Haken, die diesen Generator treffen"),
    "Surge": N_("Downs per Basisangriff in 32 m um diesen Generator"),
    "Eruption": N_("Downs, während dieser Generator markiert ist"),
    "Turn Back the Clock": N_("Einsätze auf diesen Generator"),
    "Undone": N_("Tokens beim ersten Kick"),
    "Deadlock / No Holds Barred": N_("so oft wird dieser Generator blockiert"),
    "Dead Man's Switch": N_("so oft wird dieser Generator blockiert"),
    "Grim Embrace": N_("erste Haken (1–3)"),
    "Corrupt Intervention": N_("1 = dieser Generator ist am Start blockiert"),
}
TOKENS = N_("Tokens des Perks")               # every other Killer perk that counts Tokens (perkdata.json "max_n")


# what a perk does, in the program's words (the numbers come from perkdata.json) – by the entry's "kind"
EFFECTS = {
    "self": N_("+{p} % Tempo"),
    "self_with_others": N_("+{p} % Tempo, wenn mindestens ein weiterer Survivor mitrepariert"),
    "team_per_other": N_("+{p} % Tempo je weiterem Survivor am Generator (höchstens {max} %), für alle dort"),
    "team": N_("+{p} % Tempo für alle am Generator; er regressiert halb so schnell"),
    "team_timed": N_("+{p} % Tempo für alle, {s} s lang nach einem gemeinsam fertigen Generator"),
    "great_scale": N_("jeder Great Skill Check in Folge bringt {p} % mehr Bonus (bis {n} Tokens)"),
    "requirement_all": N_("jeder Generator braucht {v} Ladungen weniger"),
    "requirement_once": N_("ein Generator braucht {v} Ladungen weniger"),
    "slow": N_("−{p} % Tempo je Anzahl (höchstens {max} %)"),
    "slow_first": N_("−{first} % Tempo beim ersten, −{p} % je weiterem (höchstens {max} %)"),
    "kick_loss": N_("ein Kick nimmt {total} % statt {base} %"),
    "overcharge": N_("ein Kick nimmt {p} % mehr; die Regression steigt in {s} s von {a} % auf {b} %"),
    "regress_mult": N_("Regression mit {p} % für {s} s nach dem Kick"),
    "ruin": N_("Regression mit {p} %, solange niemand repariert"),
    "instant": N_("nimmt dem Generator sofort {p} %"),
    "undone": N_("der erste Kick nimmt {p} % mehr je Token und blockiert {s} s je Token"),
    "block": N_("blockiert den Generator {s} s"),
    # 1.55.2: Skill Checks (the odds as percentage points of the chance per second, see gencalc)
    "check_chance": N_("Skill Checks kommen öfter: +{p} Prozentpunkte Chance je Sekunde"),
    "team_check_chance": N_("Skill Checks kommen für alle am Generator öfter: +{p} Prozentpunkte Chance je Sekunde"),
    "enemy_check_chance": N_("Skill Checks der Survivor kommen öfter: +{p} Prozentpunkte Chance je Sekunde"),
    "check_fail": N_("ein verfehlter Skill Check kostet {p} % Fortschritt mehr"),
    "enemy_check_fail": N_("ein verfehlter Skill Check kostet die Survivor {p} % Fortschritt mehr"),      # 1.56.5
    "others_check_bonus": N_("jeder erfolgreiche Skill Check der anderen bringt im Mittel +{p} % Fortschritt (W20)"),
}
FAIL_LESS = N_("ein verfehlter Skill Check kostet {p} % weniger Fortschritt")     # Deadline ("fail_mult")
PER_TOKEN_CHANCE = N_("+{p} Prozentpunkte Skill-Check-Chance je Token")           # 1.55.2: Hyperfocus


def _pct(v) -> str:
    return f"{v * 100:g}"


def effect_text(entry: dict, mech: dict | None = None) -> str:
    """One line on what the perk ``entry`` (of perkdata.json) does in the calculation."""
    kind = entry.get("kind", "")
    text = EFFECTS.get(kind)
    if not text:
        return ""
    base = (mech or {}).get("kick_loss", 0.05)
    args = {"p": _pct(entry.get("value", entry.get("per", 0))), "max": _pct(entry.get("max", 0)),
            "s": f"{entry.get('seconds', entry.get('block', 0)):g}", "n": entry.get("tokens", 0),
            "v": f"{entry.get('value', 0):g}", "first": _pct(entry.get("first", 0)),
            "total": _pct(base + entry.get("value", 0)), "base": _pct(base),
            "a": _pct(entry.get("from", 0)), "b": _pct(entry.get("to", 0))}
    if kind in ("regress_mult", "ruin"):
        args["p"] = _pct(entry.get("value", 1))
    if kind == "slow" and entry.get("full_at"):
        return _(text, **args) + " · " + _("{p} % bei {n}", p=_pct(entry["full"]), n=entry["full_at"])
    if entry.get("chance_per_token"):
        return _(text, **args) + " · " + _(PER_TOKEN_CHANCE, p=_pct(entry["chance_per_token"]))
    if "fail_mult" in entry:
        return _(text, **args) + " · " + _(FAIL_LESS, p=_pct(1 - entry["fail_mult"]))
    return _(text, **args)


def addon_text(entry: dict, data) -> str:
    """One line on what a toolbox add-on does to a Generator ("" = nothing there)."""
    if entry.get("repair"):
        return _("+{p} % Tempo mit dem Werkzeugkasten (Add-on: zählt voll)", p=_pct(entry["repair"]))
    if entry.get("charges"):
        return _("+{n} Ladungen im Werkzeugkasten", n=f"{entry['charges']:g}")
    if entry.get("part"):
        return _(EFFECTS["requirement_once"], v=f"{data.addons['Brand New Part']['value']:g}")
    if entry.get("no_checks"):
        return _("keine regulären Skill Checks, solange der Werkzeugkasten läuft")
    return ""


def _secs(v) -> str:
    return _("{n} s", n=v)


def _stack_label(v) -> str:
    return _("alle") if v >= 100 else _("die Hälfte") if v > 0 else _("eine")


def when_text(part) -> str:
    """The condition of a modifier in words: "verletzt · 12 s lang"."""
    bits = []
    if part.when in WHEN and (part.when != "tokens" or part.stacks):
        bits.append(_(WHEN[part.when], n=part.stacks))
    if part.seconds:
        bits.append(_("{s} s lang", s=f"{part.seconds:g}"))
    return " · ".join(bits)


def signed_pct(v: float) -> str:
    """+50 % / −20 % (a typographic minus, no trailing zeros)."""
    return ("+" if v >= 0 else "−") + f"{abs(v) * 100:.3g} %"


def check_text(base: float, now: float) -> str:
    """A Skill Check value of one Survivor (odds per second, a share of the Generator): "8 %", or "8 % → 28 %"
    when the perks change it (three significant digits: Hyperfocus gives an expected value)."""
    one = f"{base * 100:.3g} %"
    return one if abs(now - base) < 1e-9 else f"{one} → {now * 100:.3g} %"


CHECK_LINES = (          # 1.56.4: shown only when a chosen perk changes the value for someone
    ("fail", N_("Ein verfehlter Skill Check kostet (Anteil am Generator): {odds}")),
    ("great", N_("Ein Great Skill Check bringt (Anteil am Generator, im Mittel): {odds}")),
    ("extra", N_("Jeder erfolgreiche Skill Check bringt zusätzlich (Anteil am Generator, im Mittel): {odds}")))


def value_text(kind: str, v) -> str:
    if v is None:
        return "–"
    return f"{v:.2f} m/s" if kind == "speed" else f"{v:.2f} s"


def delta_text(kind: str, now, old) -> str:
    """Now against Build A: "−1.20 s" (for times less is faster), "=" when the same."""
    if now is None or old is None:
        return "–"
    d = now - old
    if abs(d) < 0.005:
        return "="
    unit = " m/s" if kind == "speed" else " s"
    return ("+" if d > 0 else "−") + f"{abs(d):.2f}" + unit


def _time_delta(now, old) -> str:
    if now is None or old is None:
        return "–"
    d = int(round(now)) - int(round(old))
    return "=" if d == 0 else ("+" if d > 0 else "−") + gencalc.fmt(abs(d))


class CalcTab:
    """The page "Rechner" (AutoPage from this tab's structure)."""

    def _calc_data(self):
        data = self.__dict__.get("_calc_loaded")
        if data is None:
            data = self._calc_loaded = gencalc.load()
        return data

    def _calc_state(self) -> dict:
        saved = self.settings.get("calc") if isinstance(self.settings.get("calc"), dict) else {}
        st = {**CALC_DEFAULTS, **saved}
        if st["area"] not in self._calc_data().areas:
            st["area"] = gencalc.REPAIR
        return st

    def _calc_icons(self):
        icons = self.__dict__.get("_calc_icon_index")
        if icons is None:
            icons = self._calc_icon_index = perkicons.Index(perkicons.folders(self.data_dir))
        return icons

    def _calc_choice(self, parent, var, values, width=17, px=PERK_PX, icons=""):
        """A choice of the page. ``icons``: the kind of picture its entries have ("perks", "addon", "items")."""
        c = ui.Combobox(parent, textvariable=var, values=values, state="readonly", width=width)
        if px:
            c._dbdms_px = px
            c._dbdms_px_max = max(px, PERK_MAX)
            # 1.54.1: a box of fixed width cuts a long name ("Scourge Hook: Pain Resonance") – the whole of it
            # on hover
            c._dbdms_tip = lambda: "" if var.get() in ("", NONE) else var.get()
        if icons and self._calc_icons().any():
            c._dbdms_icons = self._calc_icons().finder(icons)   # value -> picture file or None (app_qt.ui_state)
        c.bind("<<ComboboxSelected>>", lambda e: self._calc_changed())
        return c

    def _calc_slot(self, parent, var, values, what: str, icons: str):
        """1.57.95 (user picked draft B "Build-Karten"): a place of a build – drawn as a tile with the perk's
        picture and its name; empty, it says what goes there (``what``). A choice like the others underneath."""
        c = self._calc_choice(parent, var, values, px=0, icons=icons)
        c._dbdms_slot = what
        c._dbdms_tip = lambda: "" if var.get() in ("", NONE) else var.get()
        return c

    def _tab_calc(self):
        outer, f = self._scroll_tab()
        d = self._calc_data()
        st = self._calc_state()
        item_names = [NONE] + gencalc.item_names(d)
        # 1.55 (user: the result beside the choices – it began 900 px down the page and every choice meant
        # scrolling): two columns on a wide page, what is chosen on the left, what comes of it on the right
        cols = ui.Frame(f)
        cols.pack(fill="x")
        cols._dbdms_beside = BESIDE_FROM
        left, right = ui.Frame(cols), ui.Frame(cols)
        left.pack(fill="x")
        right.pack(fill="x")

        top = ui.LabelFrame(left, text=_("Bereich"), padding=8)
        top.pack(fill="x")
        row = ui.Frame(top)
        row.pack(fill="x")
        self.calc_area_ids = [a for a in d.areas if a in AREAS]
        labels = [_(AREAS[a]) for a in self.calc_area_ids]
        self.calc_area_var = ui.StringVar(value=_(AREAS[st["area"]]))
        cb = self._calc_choice(row, self.calc_area_var, labels, width=30, px=PERK_PX + 90)
        cb._dbdms_name = _("Bereich")                      # 1.55.7: its accessible name (no label)
        cb.pack(side="left")
        ui.Label(row, text=_("Survivor im Team")).pack(side="left", padx=(16, 0))
        self.calc_n_var = ui.StringVar(value=str(st["n"]))
        cb = self._calc_choice(row, self.calc_n_var, [str(i) for i in range(1, 5)], width=4, px=0)
        cb.pack(side="left", padx=(8, 0))
        ui.Button(row, text=_("Beispiel laden"), command=self._calc_example).pack(side="left", padx=(16, 0))
        self.calc_area_var_hint = ui.StringVar(value="")
        ui.Label(top, textvariable=self.calc_area_var_hint, style="Dim.TLabel", wraplength=640).pack(
            anchor="w", pady=(6, 0))

        team = ui.Frame(left)                                # 1.57.95: a card per build, not one card for all
        team.pack(fill="x", pady=(8, 0))
        self.calc_surv, self.calc_surv_rows, self.calc_perk_boxes, self.calc_item_addons = [], [], [], []
        self.calc_tokens = []                                # per build: (its line, the choice, the perks it is for)
        for i in range(gencalc.MAX_SURVIVORS):
            perks, tool, had = self._calc_entry((st["survivors"] + [[[], ""]] * 4)[i])
            block = ui.LabelFrame(team, text=_("Survivor {n}", n=i + 1), padding=8)   # shown only for the team's Survivors
            block.pack(fill="x", pady=(0 if i == 0 else 8, 0))
            r = ui.Frame(block)                              # four perks and the item: five places in a row
            r.pack(fill="x")
            vars_ = []
            for slot in range(SLOTS):
                v = ui.StringVar(value=perks[slot] if slot < len(perks) and self._calc_known(perks[slot], "S")
                                 else NONE)
                c = self._calc_slot(r, v, [NONE], _("Perk {n}", n=slot + 1), "perks")
                c._dbdms_name = _("Survivor {n}", n=i + 1) + " · " + _("Perk {n}", n=slot + 1)
                c.pack(side="left", padx=(0 if slot == 0 else 6, 0))
                self.calc_perk_boxes.append((c, v, "S"))
                vars_.append(v)
            tv = ui.StringVar(value=tool if tool in item_names else NONE)
            c = self._calc_slot(r, tv, item_names, _("Item"), "items")
            c._dbdms_name = _("Survivor {n}", n=i + 1) + " · " + _("Item")
            c.pack(side="left", padx=(6, 0))
            r = ui.Frame(block)                              # the item's add-ons below, and "the same for all"
            r.pack(fill="x", pady=(6, 0))
            ui.Label(r, text=_("Add-ons")).pack(side="left")
            slots = []
            for k in range(ADDON_SLOTS):                    # 1.53: the item's add-ons (those of the item in hand)
                av = ui.StringVar(value=had[k] if k < len(had) and had[k] else NONE)       # _calc_tidy checks it
                c = self._calc_choice(r, av, [NONE], icons="addon")
                c._dbdms_name = _("Survivor {n}", n=i + 1) + " · " + _("Add-on {n}", n=k + 1)
                c.pack(side="left", padx=(6, 0))
                slots.append((c, av))
            self.calc_item_addons.append(slots)
            if i == 0:
                self.calc_same_btn = ui.Button(r, text=_("Für alle übernehmen"), command=self._calc_same_for_all)
                self.calc_same_btn.pack(side="right")
            # 1.55 (user's yes to "Tokens je Survivor"): how many Tokens this Survivor's perks have – a line of
            # the build, there only while one of its perks counts Tokens (_calc_arrange). Before: one choice for all
            tr = ui.Frame(block)
            lab = ui.Label(tr, text=_("Tokens"), width=14)
            lab._dbdms_px = NAME_PX
            lab.pack(side="left")
            labels = [_stack_label(c) for c in STACK_CHOICES]
            cur = self._calc_tokens((st["survivors"] + [[[], ""]] * 4)[i], st.get("stacks"))
            sv = ui.StringVar(value=labels[STACK_CHOICES.index(cur)])
            self._calc_choice(tr, sv, labels, width=10, px=0).pack(side="left", padx=(6, 0))
            nv = ui.StringVar(value="")
            ui.Label(tr, textvariable=nv, style="Dim.TLabel", wraplength=420).pack(side="left", padx=(10, 0))
            self.calc_tokens.append((tr, sv, nv))
            self.calc_surv.append((vars_, tv))
            self.calc_surv_rows.append(block)
        self.calc_team_hint = ui.Label(
            team, text=_("Bedingte Perks zählen als aktiv (z. B. Resilience = verletzt, Hope = Tore mit Strom); die "
                         "Bedingung steht in der Aufschlüsselung. Ein Werkzeugkasten wirkt beim Reparieren und "
                         "Sabotieren, ein Med-Kit beim Heilen; Add-ons zählen voll (keine Diminishing Returns)."),
            style="Dim.TLabel", wraplength=620)
        self.calc_team_hint.pack(anchor="w", pady=(6, 0))
        self.calc_plain_var = ui.StringVar(value="")         # 1.54: chosen add-ons that change nothing computed
        ui.Label(team, textvariable=self.calc_plain_var, style="Dim.TLabel", wraplength=620).pack(anchor="w")

        kf = ui.LabelFrame(left, text=_("Killer-Build"), padding=8)
        kf.pack(fill="x", pady=(8, 0))
        r = ui.Frame(kf)                                     # 1.53: which Killer, and the power's add-ons
        r.pack(fill="x", pady=(0, 6))
        self.calc_killer_var = ui.StringVar(value=st["killer_name"] if st["killer_name"] in d.killers else NONE)
        kc = self._calc_choice(r, self.calc_killer_var, [NONE] + sorted(d.killers, key=str.lower), width=26,
                               px=PERK_PX + 40)
        kc._dbdms_name = _("Killer")
        kc.pack(side="left")
        ui.Label(r, text=_("Add-ons")).pack(side="left", padx=(12, 0))
        self.calc_killer_addons = []
        had = list(st["killer_addons"]) if isinstance(st["killer_addons"], list) else []
        for k in range(ADDON_SLOTS):
            av = ui.StringVar(value=str(had[k]) if k < len(had) and had[k] else NONE)   # _calc_tidy checks it
            c = self._calc_choice(r, av, [NONE], px=PERK_PX + 16, icons="addon")
            c.pack(side="left", padx=(6, 0))
            self.calc_killer_addons.append((c, av))
        self.calc_killer_hint = ui.StringVar(value="")
        ui.Label(kf, textvariable=self.calc_killer_hint, style="Dim.TLabel", wraplength=620).pack(
            anchor="w", pady=(0, 6))
        self.calc_kill = []
        self.calc_count_boxes = []
        killer, counts = st["killer"], st["counts"] if isinstance(st["counts"], dict) else {}
        pr = ui.Frame(kf)                                    # 1.57.95: the four perks as places in one row
        pr.pack(fill="x")
        self.calc_counts_frame = cl = ui.Frame(kf)           # … and below, a line per perk that counts something
        cl.pack(fill="x")
        for slot in range(SLOTS):
            name = killer[slot] if slot < len(killer) and self._calc_known(killer[slot], "K") else NONE
            v = ui.StringVar(value=name)
            c = ui.Combobox(pr, textvariable=v, values=[NONE], state="readonly", width=26)
            c._dbdms_slot = _("Perk {n}", n=slot + 1)
            c._dbdms_name = _("Killer-Perk {n}", n=slot + 1)
            c._dbdms_tip = lambda v=v: "" if v.get() in ("", NONE) else v.get()
            if self._calc_icons().any():
                c._dbdms_icons = self._calc_icons().finder("perks")
            c.pack(side="left", padx=(0 if slot == 0 else 6, 0))
            c.bind("<<ComboboxSelected>>", lambda e, s=slot: self._calc_killer_picked(s))
            self.calc_perk_boxes.append((c, v, "K"))
            cf = ui.Frame(cl)                                # 1.55: only for a perk that counts something
            pv = ui.StringVar(value="")                      # which perk the line is of
            ui.Label(cf, textvariable=pv).pack(side="left")
            ui.Label(cf, text=_("Anzahl")).pack(side="left", padx=(10, 0))
            nv = ui.StringVar(value=str(counts.get(name, self._calc_count_default(name))))
            c = self._calc_choice(cf, nv, [str(x) for x in COUNT_CHOICES], width=4, px=0)
            c.pack(side="left", padx=(6, 0))
            self.calc_count_boxes.append(cf)
            mv = ui.StringVar(value="")
            ui.Label(cf, textvariable=mv, style="Dim.TLabel", wraplength=360).pack(side="left", padx=(10, 0))
            self.calc_kill.append((v, nv, mv))
            cf._calc_name = pv

        af = ui.LabelFrame(left, text=_("Annahmen"), padding=8)
        af.pack(fill="x", pady=(8, 0))
        self.calc_opts, self.calc_opt_rows = {}, {}
        self.calc_opt_grid = grid = ui.Frame(af)             # 1.57.95: side by side (they wrap), not a list
        grid.pack(fill="x")
        for key, label, choices, show in (
                ("great", N_("Great Skill Checks"), GREAT_CHOICES, lambda v: f"{v} %"),
                ("miss", N_("Verfehlte Skill Checks"), MISS_CHOICES, lambda v: f"{v} %"),
                ("kicks", N_("Kicks am Generator"), KICK_CHOICES, str),
                ("kick_at", N_("Killer kommt bei"), KICK_AT_CHOICES, lambda v: f"{v} %"),
                ("away", N_("Weg nach dem Kick"), AWAY_CHOICES, _secs),
                ("walk", N_("Laufweg zwischen Generatoren"), WALK_CHOICES, _secs)):
            r = ui.Frame(grid)
            r.pack(side="left", padx=(0, 14), pady=(0, 4))
            ui.Label(r, text=_(label), style="Dim.TLabel").pack(anchor="w")
            labels = [show(c) for c in choices]
            cur = st.get(key, CALC_DEFAULTS[key])
            v = ui.StringVar(value=labels[choices.index(cur)] if cur in choices else labels[0])
            c = self._calc_choice(r, v, labels, width=10, px=0)
            c._dbdms_name = _(label)
            c.pack(anchor="w")
            self.calc_opts[key] = (v, choices, labels)
            self.calc_opt_rows[key] = r
        self.calc_kick_hint = ui.Label(
            af, text=_("Kicks und die Anzahl je Killer-Perk gelten für jeden Generator einzeln."),
            style="Dim.TLabel", wraplength=620)
        self.calc_kick_hint.pack(anchor="w")
        self.calc_dr_var = ui.BooleanVar(value=bool(st.get("diminishing", True)))
        self.calc_dr_box = ui.Checkbutton(af, text=_("Diminishing Returns anwenden"), variable=self.calc_dr_var,
                                          command=self._calc_changed)
        self.calc_dr_box.pack(anchor="w", pady=(2, 0))
        ui.Button(af, text=_("Rechner zurücksetzen"), command=self._calc_reset).pack(anchor="w", pady=(6, 0))

        self.calc_tiles = ui.Tiles(right)                    # 1.57.95: the answer in big numbers (Generators)
        self.calc_tiles.pack(fill="x")
        rf = ui.LabelFrame(right, text=_("Ergebnis"), padding=8)
        rf.pack(fill="x", pady=(8, 0))
        t = ui.Treeview(rf, columns=("a", "b"), show="tree headings", height=6, selectmode="none")
        t.heading("#0", text=_("Situation"), anchor="w")
        t.column("#0", width=300, stretch=False)
        t.pack(fill="x")
        self.calc_tree = t
        self.calc_rates_var = ui.StringVar(value="")
        # 1.57.95: a plain line – the big numbers are the tiles above now (as a bold headline of four lines it
        # was drawn over the table in a narrow column: a big label's height does not follow its width)
        ui.Label(rf, textvariable=self.calc_rates_var, style="Dim.TLabel", wraplength=640).pack(
            anchor="w", pady=(6, 0))
        self.calc_note_var = ui.StringVar(value="")
        ui.Label(rf, textvariable=self.calc_note_var, style="Dim.TLabel", wraplength=640).pack(
            anchor="w", pady=(2, 0))
        row = ui.Frame(rf)
        row.pack(fill="x", pady=(6, 0))
        ui.Button(row, text=_("Als Build A merken"), command=self._calc_keep).pack(side="left")
        self.calc_drop_btn = ui.Button(row, text=_("Vergleich beenden"), command=self._calc_drop)
        self.calc_drop_btn.pack(side="left", padx=(8, 0))
        self.calc_compare_var = ui.StringVar(value="")
        ui.Label(rf, textvariable=self.calc_compare_var, style="Dim.TLabel", wraplength=640).pack(
            anchor="w", pady=(4, 0))

        nf = ui.LabelFrame(right, text=_("Bester nächster Perk"), padding=8)
        nf.pack(fill="x", pady=(8, 0))
        self.calc_tip_rows, self._calc_tips_now = [], []     # 1.57.95: each proposal with "Einsetzen"
        for k in range(TIP_ROWS):
            r = ui.Frame(nf)
            tv = ui.StringVar(value="")
            ui.Button(r, text=_("Einsetzen"), command=lambda k=k: self._calc_tip_use(k)).pack(side="right")
            ui.Label(r, textvariable=tv, wraplength=520, justify="left").pack(side="left")
            self.calc_tip_rows.append((r, tv))
        self.calc_tips_var = ui.StringVar(value="")          # what cannot be put in: "kein freier Platz", …
        self.calc_tips_label = ui.Label(nf, textvariable=self.calc_tips_var, wraplength=640, justify="left")
        self.calc_tips_label.pack(anchor="w")

        bf = ui.LabelFrame(right, text=_("Aufschlüsselung"), padding=8)
        bf.pack(fill="x", pady=(8, 0))
        b = ui.Treeview(bf, columns=("value", "weight", "counted", "when"), show="tree headings", height=8,
                        selectmode="none")
        b.heading("#0", text=_("Quelle"), anchor="w")
        b.heading("value", text=_("Nennwert"), anchor="e")
        b.heading("weight", text=_("zählt zu"), anchor="e")
        b.heading("counted", text=_("wirkt mit"), anchor="e")
        b.heading("when", text=_("Bedingung"), anchor="w")
        b.column("#0", width=250, stretch=False)
        b.column("value", width=80, anchor="e", stretch=False)
        b.column("weight", width=70, anchor="e", stretch=False)
        b.column("counted", width=80, anchor="e", stretch=False)
        b.column("when", width=160, anchor="w", stretch=True)
        b._dbdms_empty = _("Noch kein Perk gewählt, der in diesem Bereich wirkt.")
        b.pack(fill="x")
        self.calc_parts_tree = b
        ui.Label(bf, text=_("Von mehreren Boni (oder Mali) auf dasselbe zählt der größte voll, der zweite zur "
                            "Hälfte, der dritte zu 25 %, der vierte zu 12,5 %, jeder weitere zu 5 % (seit Patch "
                            "9.6.0). Boni werden addiert, Mali multipliziert."),
                 style="Dim.TLabel", wraplength=640).pack(anchor="w", pady=(6, 0))

        self.calc_effects_frame = ef = ui.LabelFrame(right, text=_("Was die gewählten Perks tun"), padding=8)
        ef.pack(fill="x", pady=(8, 0))
        self.calc_effects_var = ui.StringVar(value="")
        ui.Label(ef, textvariable=self.calc_effects_var, wraplength=640, justify="left").pack(anchor="w")

        self.calc_source_var = ui.StringVar(value="")
        ui.Label(f, textvariable=self.calc_source_var, style="Dim.TLabel", wraplength=640).pack(
            anchor="w", pady=(6, 0))
        ui.Label(f, text=_("Perk-Bilder: eigene Bilder (PNG oder WebP, benannt wie der Perk) im Ordner „{folder}“ des "
                            "Datenordners erscheinen nach dem nächsten Start in den Auswahllisten.",
                            folder=perkicons.USER_FOLDER),
                 style="Dim.TLabel", wraplength=640).pack(anchor="w", pady=(2, 0))
        self._calc_render()
        return outer

    # ---------------------------------------------------------------- reading the page
    def _calc_known(self, name: str, side: str) -> bool:
        d = self._calc_data()
        own = d.survivor if side == "S" else d.killer
        return name in own or d.perks.get(name, {}).get("side") == side

    @staticmethod
    def _calc_entry(entry) -> tuple:
        """(perks, item, add-ons) of a saved Survivor entry – older settings have no add-ons."""
        try:
            perks, item = list(entry[0]), str(entry[1] or "")
            addons = [str(a) for a in entry[2]] if len(entry) > 2 else []
        except (TypeError, ValueError, IndexError):
            return [], "", []
        return perks, item, addons

    @staticmethod
    def _calc_tokens(entry, default=None) -> int:
        """The Token choice of a saved Survivor entry (a value of STACK_CHOICES); an entry from before 1.55 has
        none: the one choice all Survivors shared then."""
        try:
            value = int(entry[3]) if len(entry) > 3 else int(default)
        except (TypeError, ValueError, IndexError):
            value = CALC_DEFAULTS["stacks"]
        return value if value in STACK_CHOICES else CALC_DEFAULTS["stacks"]

    def _calc_count_default(self, name: str) -> int:
        d = self._calc_data()
        if name in d.killer:
            return int(d.killer[name].get("default", 1))
        return gencalc.max_stacks(d, name) or 1

    def _calc_area(self) -> str:
        labels = [_(AREAS[a]) for a in self.calc_area_ids]
        cur = self.calc_area_var.get()
        return self.calc_area_ids[labels.index(cur)] if cur in labels else gencalc.REPAIR

    def _calc_read(self) -> dict:
        """What the page says now, in the shape of the setting ``calc`` (without the kept Build A)."""
        try:
            n = max(1, min(4, int(self.calc_n_var.get())))
        except ValueError:
            n = 4
        opts = {}
        for key, (v, choices, labels) in self.calc_opts.items():
            opts[key] = choices[labels.index(v.get())] if v.get() in labels else CALC_DEFAULTS[key]
        return {"area": self._calc_area(), "n": n,
                "survivors": [[[v.get() for v in vars_ if v.get() != NONE], tv.get() if tv.get() != NONE else "",
                               [av.get() for _c, av in slots if av.get() != NONE], self._calc_token_choice(sv)]
                              for (vars_, tv), slots, (_tr, sv, _nv) in zip(self.calc_surv, self.calc_item_addons,
                                                                            self.calc_tokens)],
                "killer": [v.get() for v, _nv, _mv in self.calc_kill if v.get() != NONE],
                "killer_name": self.calc_killer_var.get() if self.calc_killer_var.get() != NONE else "",
                "killer_addons": [av.get() for _c, av in self.calc_killer_addons if av.get() != NONE],
                "counts": {v.get(): nv.get() for v, nv, _mv in self.calc_kill if v.get() != NONE},
                **opts, "diminishing": bool(self.calc_dr_var.get())}

    @staticmethod
    def _calc_token_choice(var) -> int:
        labels = [_stack_label(c) for c in STACK_CHOICES]
        return STACK_CHOICES[labels.index(var.get())] if var.get() in labels else CALC_DEFAULTS["stacks"]

    def _calc_build(self, st: dict):
        """(team, Killer, Scenario) of a state as ``_calc_read`` gives it (also the kept Build A)."""
        d = self._calc_data()
        try:
            n = max(1, min(4, int(st.get("n", 4))))
        except (TypeError, ValueError):
            n = 4
        team = []
        for entry in (list(st.get("survivors") or []) + [[[], ""]] * 4)[:n]:
            perks, item, addons = self._calc_entry(entry)
            perks = tuple(p for p in perks if self._calc_known(p, "S"))
            kind = gencalc.item_kind(d, item)
            team.append(gencalc.Survivor(perks, item if kind == "toolbox" else "",
                                         medkit=item if kind == "medkit" else "", addons=tuple(addons),
                                         item=item if kind not in ("", "toolbox", "medkit") else "",
                                         stacks=self._calc_tokens(entry, st.get("stacks")) / 100))
        names = tuple(p for p in st.get("killer") or [] if self._calc_known(p, "K"))
        counts = {}
        for name, value in (st.get("counts") or {}).items():
            try:
                counts[name] = int(value)
            except (TypeError, ValueError):
                pass

        def num(key):
            try:
                return float(st.get(key, CALC_DEFAULTS[key]))
            except (TypeError, ValueError):
                return float(CALC_DEFAULTS[key])
        scen = gencalc.Scenario(great=num("great") / 100, miss=num("miss") / 100,
                                diminishing=bool(st.get("diminishing", True)), kicks=int(num("kicks")),
                                kick_at=num("kick_at") / 100, away=num("away"), walk=num("walk"),
                                stacks=num("stacks") / 100)
        name = str(st.get("killer_name") or "")
        addons = tuple(str(a) for a in st.get("killer_addons") or [])
        return team, gencalc.Killer(names, counts, name if name in d.killers else "", addons), scen

    def _calc_killer_picked(self, slot: int):
        v, nv, _mv = self.calc_kill[slot]
        if v.get() != NONE:
            nv.set(str(self._calc_count_default(v.get())))
        self._calc_changed()

    def _calc_same(self, name: str) -> str:
        """What makes two choices the same perk: its name – the two kinds of Overzealous are one perk."""
        d = self._calc_data()
        return (d.survivor.get(name) or d.killer.get(name) or {}).get("group", name)

    def _calc_builds(self) -> list:
        """The perk choices build by build: [(box, variable, side)] of each Survivor, then of the Killer."""
        boxes = self.calc_perk_boxes
        return [boxes[i:i + SLOTS] for i in range(0, len(boxes), SLOTS)]

    def _calc_tidy(self):
        """A perk is in a build once (1.53.1, Saru: "kann ein Survivor 2x dasselbe Perk haben. Das macht keinen
        Sinn"): a second one is taken out. The add-on choices follow the item and the Killer chosen: their lists,
        and an add-on that no longer fits is taken out; the other place does not offer the add-on chosen here."""
        d = self._calc_data()
        for build in self._calc_builds():
            taken = set()
            for _box, var, _side in build:
                if var.get() != NONE and self._calc_same(var.get()) in taken:
                    var.set(NONE)
                taken.add(self._calc_same(var.get()))
        rows = [(slots, gencalc.item_addon_names(d, tv.get()))
                for (_vars, tv), slots in zip(self.calc_surv, self.calc_item_addons)]
        rows.append((self.calc_killer_addons, gencalc.killer_addon_names(d, self.calc_killer_var.get())))
        for slots, names in rows:
            taken = set()
            for box, var in slots:
                if var.get() != NONE and (var.get() not in names or var.get() in taken):
                    var.set(NONE)                              # another item, or the same add-on twice
                taken.add(var.get())
            for box, var in slots:
                values = [NONE] + [n for n in names if n == var.get() or n not in taken]
                if list(box.cget("values") or ()) != values:
                    box.configure(values=values)
                box.state(["!disabled" if names else "disabled"])

    def _calc_changed(self):
        self._calc_tidy()
        st = self._calc_read()
        st["compare"] = self._calc_state().get("compare")
        self.settings.set("calc", st)
        self._save_soon()
        self._calc_render()

    def calc_tip_lines(self) -> list:
        """Every line of "Bester nächster Perk" as shown: the proposals (each with "Einsetzen"), then the notes."""
        rows = [tv.get() for r, tv in self.calc_tip_rows if r.winfo_manager()]
        return rows + [ln for ln in self.calc_tips_var.get().split("\n") if ln]

    def _calc_tip_use(self, k: int):
        """"Einsetzen": the proposed perk into the first free place of the build it is for."""
        if k >= len(self._calc_tips_now):
            return
        side, tip = self._calc_tips_now[k]
        if side == "S":
            who = min(max(int(getattr(tip, "who", 0) or 0), 0), len(self.calc_surv) - 1)
            places = self.calc_surv[who][0]
        else:
            places = [v for v, _nv, _mv in self.calc_kill]
        free = next((v for v in places if v.get() == NONE), None)
        if free is None or any(v.get() == tip.name for v in places):
            return
        free.set(tip.name)
        self._calc_changed()

    def _calc_same_for_all(self):
        """"Für alle übernehmen": the build of Survivor 1 – perks, item, add-ons – for every Survivor of the team."""
        vars_, tv = self.calc_surv[0]
        for (other, otv), slots in list(zip(self.calc_surv, self.calc_item_addons))[1:]:
            for src, dst in zip(vars_, other):
                dst.set(src.get())
            otv.set(tv.get())
            for (_b, src), (_b2, dst) in zip(self.calc_item_addons[0], slots):
                dst.set(src.get())
        self._calc_changed()

    def _calc_example(self):
        """"Beispiel laden": a common case to see what the page does – four Survivors on the Generators, the first
        with Prove Thyself and a toolbox, against a Killer with Corrupt Intervention. Only names the data has."""
        d = self._calc_data()
        self._calc_reset()
        self.calc_area_var.set(_(AREAS[gencalc.REPAIR]))
        self.calc_n_var.set("4")
        for var, name in zip(self.calc_surv[0][0], EXAMPLE_SURVIVOR):
            if self._calc_known(name, "S"):
                var.set(name)
        tool = next((n for n in gencalc.item_names(d) if gencalc.item_kind(d, n) == "toolbox"), None)
        if tool:
            self.calc_surv[0][1].set(tool)
        for (v, _nv, _mv), name in zip(self.calc_kill, EXAMPLE_KILLER):
            if self._calc_known(name, "K"):
                v.set(name)
        self._calc_changed()

    def _calc_keep(self):
        """Keep what is chosen now as Build A; the result then shows it beside every change."""
        st = self._calc_read()
        st["compare"] = {k: v for k, v in st.items() if k != "area"}
        self.settings.set("calc", st)
        self._save_soon()
        self._calc_render()

    def _calc_drop(self):
        st = self._calc_read()
        st["compare"] = None
        self.settings.set("calc", st)
        self._save_soon()
        self._calc_render()

    def _calc_reset(self):
        """All builds and assumptions back to the start values (the area stays)."""
        self.calc_n_var.set(str(CALC_DEFAULTS["n"]))
        for vars_, tv in self.calc_surv:
            for v in vars_:
                v.set(NONE)
            tv.set(NONE)
        for v, nv, _mv in self.calc_kill:
            v.set(NONE)
            nv.set("1")
        for _tr, sv, _nv in self.calc_tokens:
            sv.set(_stack_label(CALC_DEFAULTS["stacks"]))
        self.calc_killer_var.set(NONE)
        for slots in self.calc_item_addons + [self.calc_killer_addons]:
            for _box, var in slots:
                var.set(NONE)
        for key, (v, choices, labels) in self.calc_opts.items():
            v.set(labels[choices.index(CALC_DEFAULTS[key])])
        self.calc_dr_var.set(True)
        self._calc_tidy()
        self.settings.set("calc", {**self._calc_read(), "compare": None})
        self._save_soon()
        self._calc_render()

    def _calc_effects(self, d, team, killer) -> str:
        """One line per chosen perk and toolbox (each once): what it does to a Generator."""
        lines, seen = [], set()
        for s in team:
            for name in s.perks:
                if name not in seen and name in d.survivor:
                    seen.add(name)
                    lines.append(f"{name} – {effect_text(d.survivor[name], d.mech)}")
            if s.toolbox in d.toolboxes and s.toolbox not in seen:
                seen.add(s.toolbox)
                e = d.toolboxes[s.toolbox]
                lines.append(f"{s.toolbox} – " + _("+{p} % Tempo, bis {n} Ladungen übertragen sind",
                                                   p=_pct(e["bonus"]), n=f"{gencalc.tool_charges(d, s):g}"))
            for a in gencalc.item_addons(d, s):               # 1.53: what the toolbox's add-ons do to a Generator
                text = addon_text(a, d)
                if text and a["name"] not in seen:
                    seen.add(a["name"])
                    lines.append(f"{a['name']} – {text}")
        for name in killer.perks:
            if name not in seen and name in d.killer:
                seen.add(name)
                lines.append(f"{name} – {effect_text(d.killer[name], d.mech)}")
        return "\n".join(lines) if lines else _("Noch kein Perk gewählt.")

    # ---------------------------------------------------------------- what the page shows for the area
    def _calc_arrange(self, area: str, n: int):
        """Only what the area and the team size need: the builds of the first ``n`` Survivors, the perks that act
        in this area (a perk already chosen stays in its list), the assumptions asked here."""
        d = self._calc_data()
        self._calc_tidy()
        name = self.calc_killer_var.get()
        hint = _("Add-ons: alle des gewählten Killers. Berechnet werden die mit Haste, Hindered, Mangled oder "
                 "Aktionstempo; die Kraft selbst zählt nur dort mit, wo ein gewähltes Add-on sie verstärkt.")
        chosen = gencalc.Killer(name=name, addons=tuple(v.get() for _b, v in self.calc_killer_addons))
        plain = gencalc.plain_addons(d, killer=chosen)
        if plain:                                            # in a place, but nothing the calculator works out
            hint += " " + _("Ohne berechenbare Wirkung: {names}.", names=", ".join(plain))
        self.calc_killer_hint.set(hint)
        lines = []
        for i, ((_vars, tv), slots) in enumerate(zip(self.calc_surv, self.calc_item_addons)):
            if i >= n or tv.get() == NONE:
                continue
            plain = gencalc.plain_addons(d, tv.get(), tuple(v.get() for _b, v in slots))
            if gencalc.item_kind(d, tv.get()) not in ("toolbox", "medkit"):
                plain = [tv.get()] + plain                   # a flashlight, key, map or fog vial: no speed at all
            if plain:
                lines.append(_("Survivor {n}", n=i + 1) + ": " + ", ".join(plain))
        self.calc_plain_var.set(_("Ohne berechenbare Wirkung: {names}.", names=" · ".join(lines)) if lines else "")
        for i, block in enumerate(self.calc_surv_rows):
            if i < n and not block.winfo_manager():
                block.pack(fill="x", pady=(0 if i == 0 else 8, 0), before=self.calc_team_hint)
            elif i >= n and block.winfo_manager():
                block.pack_forget()
        for i, ((vars_, _tv), (tr, _sv, nv)) in enumerate(zip(self.calc_surv, self.calc_tokens)):
            counting = [v.get() for v in vars_ if v.get() != NONE and gencalc.max_stacks(d, v.get())]
            nv.set(", ".join(counting))
            want = bool(counting) and i < n and area != gencalc.REPAIR
            if want and not tr.winfo_manager():
                tr.pack(fill="x", pady=(4, 0))
            elif not want and tr.winfo_manager():
                tr.pack_forget()
        names = {side: gencalc.perk_names(d, side, area) for side in ("S", "K")}
        for build in self._calc_builds():                   # a perk chosen in a build is not offered in its other
            chosen = {self._calc_same(var.get()) for _box, var, _side in build if var.get() != NONE}    # places
            for box, var, side in build:
                own = self._calc_same(var.get())
                values = [NONE] + [n for n in names[side] if self._calc_same(n) == own or
                                   self._calc_same(n) not in chosen]
                if var.get() != NONE and var.get() not in values:
                    values.append(var.get())
                if list(box.cget("values") or ()) != values:
                    box.configure(values=values)
        repair = area == gencalc.REPAIR
        for key, r in self.calc_opt_rows.items():
            want = repair if key in REPAIR_OPTS else not repair
            if want and not r.winfo_manager():
                later = [o for k, o in self.calc_opt_rows.items()
                         if o.winfo_manager() and list(self.calc_opt_rows).index(k) > list(self.calc_opt_rows).index(key)]
                r.pack(side="left", padx=(0, 14), pady=(0, 4), **({"before": later[0]} if later else {}))
            elif not want and r.winfo_manager():
                r.pack_forget()
        for w, kw in ((self.calc_kick_hint, {"anchor": "w", "before": self.calc_dr_box}),
                      (self.calc_effects_frame, {"fill": "x", "pady": (8, 0)})):
            if repair and not w.winfo_manager():
                w.pack(**kw)
            elif not repair and w.winfo_manager():
                w.pack_forget()

    def _calc_columns(self, columns):
        """The result table's columns for this area: [(id, heading)], numbers right-aligned."""
        t = self.calc_tree
        if tuple(t.cget("columns")) != tuple(c for c, _h in columns):
            t.configure(columns=tuple(c for c, _h in columns))
        wide = len(columns) > 3                              # with Build A: five columns must fit beside the name
        t.column("#0", width=230 if wide else 300, stretch=False)
        for i, (c, head) in enumerate(columns):
            t.heading(c, text=head, anchor="e")
            t.column(c, width=100 if wide else 110, anchor="e", stretch=i == len(columns) - 1)

    @staticmethod
    def _calc_row(row: str, label: str = "") -> str:
        """The name of a result row; a Killer's own speeds carry the wiki's name of the mode ("Cloaked")."""
        if row.startswith("kalt"):
            return label or row
        name = _(ROWS.get(row, row))
        return f"{name} ({label})" if label and row == "kbase" else name

    def _calc_who(self, subject: int, many: bool) -> str:
        if subject == gencalc.KILLER:
            return _("Killer")
        return _("Survivor {n}", n=subject + 1) if many else ""

    def _calc_tip_lines(self, d, area, tips, team, killer) -> str:
        kind = d.areas[area].get("kind")
        lines = []
        for side, title in (("S", _("Survivor")), ("K", _("Killer"))):
            full = all(len(s.perks) >= SLOTS for s in team) if side == "S" else len(killer.perks) >= SLOTS
            if full:
                lines.append(_("{side}: kein freier Platz im Build.", side=title))
                continue
            if not tips[side]:
                lines.append(_("{side}: kein weiterer Perk ändert hier etwas.", side=title))
                continue
            for tip in tips[side]:
                who = _(" für Survivor {n}", n=tip.who + 1) if side == "S" and len(team) > 1 else ""
                if area == gencalc.REPAIR:
                    what = _("ein Generator, alle zusammen: {a} → {b}", a=gencalc.fmt(tip.before),
                             b=gencalc.fmt(tip.after))
                else:
                    what = self._calc_row(tip.row)
                    if len(team) > 1 and tip.subject != gencalc.KILLER and (side == "K" or tip.subject != tip.who):
                        what = _("Survivor {n}", n=tip.subject + 1) + " · " + what      # someone else's row
                    if tip.before is not None and tip.after is not None:
                        what += f": {value_text(kind, tip.before)} → {value_text(kind, tip.after)}"
                lines.append(f"{title}: {tip.name}{who} – {what}")
        return "\n".join(lines)

    def _calc_part_rows(self, tree, groups):
        """``groups``: [(heading, factor, [Part], Line or None)] → the breakdown table (a heading row, its
        modifiers below). With the line, a timed speed modifier also says what it is worth in metres (1.55)."""
        tree.delete(*tree.get_children())
        for gi, (head, mult, parts, line) in enumerate(groups):
            if not parts:
                continue
            top = tree.insert("", "end", iid=f"g{gi}", text=head, open=True,
                              values=("", "", _("Tempo {p} %", p=f"{mult * 100:.4g}"), ""))
            for pi, p in enumerate(parts):
                if p.beaten:                              # 1.54.1: of one group only the strongest counts
                    values = (signed_pct(p.value), "0 %", "—", _("nur {name} zählt", name=p.beaten))
                elif p.cap is not None:
                    values = ("", "", _("höchstens {p}", p=signed_pct(p.cap)), when_text(p))
                else:
                    share = _("Add-on: 100 %") if p.exempt else f"{p.weight * 100:g} %"
                    when = when_text(p)
                    m = gencalc.metres(line, p) if line is not None else None
                    if m is not None:                        # "nach Auslösung · 3 s lang · +6 m"
                        when += " · " + ("+" if m >= 0 else "−") + f"{abs(m):.3g} m"
                    values = (signed_pct(p.value), share, signed_pct(p.counted), when)
                tree.insert(top, "end", iid=f"g{gi}p{pi}", text=p.source, values=values)

    # ---------------------------------------------------------------- the result
    def _calc_render(self):
        d = self._calc_data()
        st = self._calc_read()
        area, n = st["area"], st["n"]
        self._calc_arrange(area, n)
        team, killer, scen = self._calc_build(st)
        kept = self._calc_state().get("compare")
        old = self._calc_build(kept) if isinstance(kept, dict) else None
        for (v, nv, mv), box in zip(self.calc_kill, self.calc_count_boxes):
            name = v.get()
            what = COUNT_MEANS.get(name) or (TOKENS if gencalc.max_stacks(d, name) else None)
            mv.set(_("Anzahl = {what}", what=_(what)) if what and name != NONE else "")
            want = bool(what) and name != NONE                # no count: nothing to choose, nothing shown
            box._calc_name.set(name if want else "")
            if want and not box.winfo_manager():
                box.pack(anchor="w", pady=(6, 0))
            elif not want and box.winfo_manager():
                box.pack_forget()
        self.calc_same_btn.state(["!disabled" if n > 1 else "disabled"])
        self.calc_drop_btn.state(["!disabled" if old else "disabled"])
        self.calc_compare_var.set(
            _("Build A ist gemerkt: die Spalten „Build A“ und „Unterschied“ zeigen ihn neben dem, was jetzt gewählt "
              "ist (− = jetzt schneller bzw. kürzer).") if old else
            _("„Als Build A merken“ hält die jetzige Auswahl fest; danach zeigt die Tabelle jede Änderung daneben."))
        tips = gencalc.suggest(d, area, team, killer, scen, slots=SLOTS)
        lines = self._calc_tip_lines(d, area, tips, team, killer).split("\n")
        usable = [(side, tip) for side in ("S", "K") for tip in tips[side]
                  if not (all(len(s.perks) >= SLOTS for s in team) if side == "S" else len(killer.perks) >= SLOTS)]
        texts = [ln for ln in lines if ln]
        self._calc_tips_now = usable[:TIP_ROWS]
        notes = []                                          # the lines that are no proposal: said below the rows
        it = iter(texts)
        shown = []
        for side, title in (("S", _("Survivor")), ("K", _("Killer"))):
            mine = [x for x in usable if x[0] == side]
            for _x in (mine or [None]):
                line = next(it, "")
                (shown if mine else notes).append(line)
        for k, (r, tv) in enumerate(self.calc_tip_rows):
            want = k < len(self._calc_tips_now) and k < len(shown)
            tv.set(shown[k] if want else "")
            if want and not r.winfo_manager():
                r.pack(fill="x", pady=(0, 4), before=self.calc_tips_label)
            elif not want and r.winfo_manager():
                r.pack_forget()
        self.calc_tips_var.set("\n".join(shown[TIP_ROWS:] + notes))
        if area == gencalc.REPAIR:
            self._calc_render_repair(d, team, killer, scen, old)
        else:
            self._calc_render_area(d, area, team, killer, scen, old)

    def _calc_render_repair(self, d, team, killer, scen, old):
        self.calc_area_var_hint.set(_("Ein Generator braucht 90 Ladungen, ein Survivor schafft 1 pro Sekunde; jeder "
                                      "weitere am selben Generator kostet alle 15 % Tempo."))
        self.calc_effects_var.set(self._calc_effects(d, team, killer))
        columns = [("calm", _("ohne Killer")), ("killer", _("mit Killer"))]
        if old:
            columns += [("a", _("Build A")), ("delta", _("Unterschied"))]
        self._calc_columns(columns)
        t = self.calc_tree
        t.delete(*t.get_children())
        calm_scen = gencalc.Scenario(**{**scen.__dict__, "kicks": 0})
        sizes = gencalc.by_size(d, team, killer, scen)
        old_sizes = gencalc.by_size(d, old[0], old[1], old[2]) if old else []

        def cells(calm, hard, was):
            extra = (gencalc.fmt(was), _time_delta(hard, was)) if old else ()
            return (gencalc.fmt(calm), gencalc.fmt(hard)) + extra

        for k, calm, hard in sizes:
            was = old_sizes[k - 1][2].seconds if k <= len(old_sizes) else None
            t.insert("", "end", iid=f"k{k}", text=_("Ein Generator, {n} Survivor", n=k) if k > 1
                     else _("Ein Generator, Survivor 1 allein"), values=cells(calm.seconds, hard.seconds, was))
        for iid, text, fn in (("all", _("Fünf Generatoren, alle zusammen"), gencalc.five_together),
                              ("split", _("Fünf Generatoren, jeder allein"), gencalc.five_split)):
            was = fn(d, old[0], old[1], old[2]) if old else None
            t.insert("", "end", iid=iid, text=text,
                     values=cells(fn(d, team, None, calm_scen), fn(d, team, killer, scen), was))
        self.calc_tiles.data = self._calc_tiles(d, team, killer, scen, calm_scen, sizes)
        last = sizes[-1][2] if sizes else None
        speeds = " · ".join(_("S{n}: {v} c/s", n=i + 1, v=f"{r:.2f}") for i, r in enumerate(last.rates)) \
            if last else ""
        rates = [_("Tempo am Generator (Ladungen pro Sekunde, Grundwert 1): {speeds}", speeds=speeds)] \
            if speeds else []
        # 1.56.4 (Saru): what the chosen perks make of the Skill Check odds – the number the times are counted with
        def per_survivor(pairs) -> str:                     # no words: the same in every language
            return " · ".join(f"S{i + 1}: {check_text(base, now)}" for i, (base, now) in enumerate(pairs))
        odds = per_survivor(gencalc.check_chances(d, team, killer, scen))
        if odds:
            rates.append(_("Skill-Check-Chance je Sekunde (mit den gewählten Perks): {odds}", odds=odds))
        values = gencalc.check_values(d, team, killer, scen)
        for key, text in CHECK_LINES:
            pairs = [v[key] for v in values]
            if any(abs(now - base) > 1e-9 for base, now in pairs):
                rates.append(_(text, odds=per_survivor(pairs)))
        self.calc_rates_var.set("\n".join(rates))
        notes = []
        if last:
            if last.events:
                notes.append(_("Der Killer nimmt dem Generator {lost} Ladungen (Regressions-Ereignisse: {events}).",
                               lost=f"{last.lost:.1f}", events=last.events))
            if last.notes:
                notes.append(_("Eingerechnet: {what}.", what=", ".join(last.notes)))
        other = gencalc.Scenario(**{**scen.__dict__, "diminishing": not scen.diminishing, "kicks": 0})
        alt = gencalc.one_generator(d, team, None, other).seconds
        if alt is not None and sizes:
            notes.append(_("Mit Diminishing Returns: {on} · ohne: {off} (ein Generator, alle, ohne Killer).",
                           on=gencalc.fmt(sizes[-1][1].seconds if scen.diminishing else alt),
                           off=gencalc.fmt(alt if scen.diminishing else sizes[-1][1].seconds)))
        self.calc_note_var.set(" ".join(notes))
        coop = max(0.0, 1.0 - d.mech["coop_penalty"] * (len(team) - 1))
        groups = []
        for i in range(len(team)):
            parts = gencalc.repair_parts(d, team, i, killer, scen)
            head = _("Survivor {n}", n=i + 1) + (" · " + _("zu {k}. am Generator: ×{c}", k=len(team),
                                                           c=f"{coop:.2f}") if len(team) > 1 else "")
            groups.append((head, gencalc.factor(parts) * coop, parts, None))
        self._calc_part_rows(self.calc_parts_tree, groups)
        self.calc_source_var.set(_("Werte aus dem Dead by Daylight Wiki (deadbydaylight.wiki.gg, Stand {date}), nach "
                                   "jedem Patch zu prüfen. Nicht berechnet: {names}.",
                                   date=d.retrieved, names=", ".join(d.not_modelled)))

    def _calc_tiles(self, d, team, killer, scen, calm_scen, sizes) -> list:
        """1.57.95: the answer in big numbers above the table – one Generator with the whole team, all five, what
        the Killer costs, the first Survivor's speed."""
        from .dashboard import Tile
        if not sizes:
            return []
        k, calm, hard = sizes[-1]
        who = _("Ein Generator, alle {n}", n=k) if k > 1 else _("Ein Generator, allein")
        five_calm = gencalc.five_together(d, team, None, calm_scen)
        five_hard = gencalc.five_together(d, team, killer, scen)
        out = [Tile(who, gencalc.fmt(hard.seconds), _("ohne Killer {t}", t=gencalc.fmt(calm.seconds))),
               Tile(_("Fünf Generatoren"), gencalc.fmt(five_hard), _("ohne Killer {t}", t=gencalc.fmt(five_calm)))]
        if five_calm is not None and five_hard is not None:
            cost = five_hard - five_calm
            out.append(Tile(_("Der Killer kostet"), ("+" if cost >= 0 else "−") + gencalc.fmt(abs(cost)),
                            _("auf fünf Generatoren"), colour="#f07a74" if cost > 0.5 else None))
        if hard.rates:
            rate = hard.rates[0]
            out.append(Tile(_("Tempo Survivor 1"), f"{rate:.2f}", _("Ladungen pro Sekunde"),
                            colour="#4fd06a" if rate > 1.0 else None))
        return out

    def _calc_render_area(self, d, area, team, killer, scen, old):
        self.calc_tiles.data = []                            # the tiles are for Generators
        kind = d.areas[area]["kind"]
        self.calc_area_var_hint.set(
            _("Geschwindigkeit in m/s. Für Haste zusammen mit Hindered nennt das Wiki keine eigene Formel – "
              "gerechnet wird wie bei Aktionen (Annahme).") if kind == "speed" else
            _("Zeit je Aktion; ohne Grundwert im Wiki steht nur das Tempo da."))
        columns = [("base", _("Grundwert")), ("now", _("Ergebnis")), ("speed", _("Tempo (relativ)"))]
        if old:
            columns += [("a", _("Build A")), ("delta", _("Unterschied"))]
        self._calc_columns(columns)
        lines = gencalc.area_lines(d, area, team, killer, scen)
        was = {}
        if old:
            was = {(ln.subject, ln.row): ln for ln in gencalc.area_lines(d, area, old[0], old[1], old[2])}
        many = len(team) > 1
        t = self.calc_tree
        t.delete(*t.get_children())
        for ln in lines:
            who = self._calc_who(ln.subject, many) if ln.subject != gencalc.KILLER else ""
            text = (who + " · " if who else "") + self._calc_row(ln.row, ln.label)
            values = (value_text(kind, ln.base), value_text(kind, ln.result), f"{ln.mult * 100:.4g} %")
            if old:
                prev = was.get((ln.subject, ln.row))
                if prev is None:
                    values += ("–", "–")
                elif ln.base is None:
                    values += (f"{prev.mult * 100:.4g} %", "=" if abs(prev.mult - ln.mult) < 1e-9 else
                               signed_pct(ln.mult - prev.mult))
                else:
                    values += (value_text(kind, prev.result), delta_text(kind, ln.result, prev.result))
            t.insert("", "end", iid=f"{ln.subject}:{ln.row}", text=text, values=values)
        self.calc_rates_var.set("")
        other = gencalc.Scenario(**{**scen.__dict__, "diminishing": not scen.diminishing})
        alt = {(ln.subject, ln.row): ln for ln in gencalc.area_lines(d, area, team, killer, other)}
        most = max(lines, key=lambda ln: abs(alt[(ln.subject, ln.row)].mult - ln.mult), default=None)
        note = ""
        if most is not None and abs(alt[(most.subject, most.row)].mult - most.mult) > 1e-9:
            on, off = (most, alt[(most.subject, most.row)]) if scen.diminishing else \
                (alt[(most.subject, most.row)], most)
            who = self._calc_who(most.subject, many) if most.subject != gencalc.KILLER else ""
            note = _("Mit Diminishing Returns: {on} · ohne: {off} ({what}).",
                     on=value_text(kind, on.result) if on.base is not None else f"{on.mult * 100:.4g} %",
                     off=value_text(kind, off.result) if off.base is not None else f"{off.mult * 100:.4g} %",
                     what=(who + " · " if who else "") + self._calc_row(most.row, most.label))
        self.calc_note_var.set(note)
        # the breakdown: rows of one subject with the same modifiers share a heading
        groups, index = [], {}
        for ln in lines:
            if not ln.parts:
                continue
            timed = ln.kind == "speed" and any(p.seconds for p in ln.parts)     # metres differ by the row's speed
            key = (ln.subject, ln.base if timed else None,
                   tuple((p.source, p.value, p.weight, p.when, p.seconds, p.cap, p.exempt, p.beaten)
                         for p in ln.parts))
            if key in index:
                groups[index[key]][0].append(self._calc_row(ln.row, ln.label))
                continue
            index[key] = len(groups)
            groups.append(([self._calc_row(ln.row, ln.label)], ln.mult, ln.parts, ln.subject, ln))
        shown = []
        for rows, mult, parts, subject, ln in groups:
            who = self._calc_who(subject, many) if subject != gencalc.KILLER else ""
            names = ", ".join(rows) if len(rows) <= 2 else rows[0] + " " + _("+ {n} weitere", n=len(rows) - 1)
            shown.append(((who + " · " if who else "") + names, mult, parts, ln))   # a long line widens the table
        self._calc_part_rows(self.calc_parts_tree, shown)
        self.calc_source_var.set(_("Werte aus dem Dead by Daylight Wiki (deadbydaylight.wiki.gg, Stand {date}), nach "
                                   "jedem Patch zu prüfen. Nicht berechnet: {names}.",
                                   date=d.retrieved, names=", ".join(d.not_modelled_areas)))
