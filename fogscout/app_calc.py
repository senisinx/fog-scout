"""Mixin of the page "Rechner" (1.51, Saru: "einen Art Rechner bei dem ich verschiedene Perks kombinieren kann … für
beide Seiten … Diminishing returns … für mehrere Leute die Builds angeben"): up to four Survivor builds and one Killer
build, the time for a Generator and for all five – the arithmetic is gencalc.py, the numbers perkdata.json.
Everything stays on this PC; the builds are kept in the setting ``calc``."""
from __future__ import annotations

from . import gencalc
from . import uimodel as ui
from .i18n import N_, _

NONE = "—"
SLOTS = 4                                     # perks per build
PERK_PX = 174                                 # width of a perk choice (four fit beside the name at 1100 px)
GREAT_CHOICES = (0, 25, 50, 75, 100)          # % of Skill Checks hit Great
MISS_CHOICES = (0, 5, 10, 20)                 # % missed
KICK_CHOICES = (0, 1, 2, 3, 4)
KICK_AT_CHOICES = (25, 50, 75, 90)            # % progress when the Killer comes
AWAY_CHOICES = (0, 10, 20, 30, 45, 60)        # s the Survivors stay away after a kick
WALK_CHOICES = (0, 5, 10, 20)                 # s between two Generators
COUNT_CHOICES = tuple(range(0, 12))
CALC_DEFAULTS = {"n": 4, "survivors": [[[], ""] for _i in range(gencalc.MAX_SURVIVORS)], "killer": [],
                 "counts": {}, "great": 50, "miss": 0, "kicks": 1, "kick_at": 50, "away": 20, "walk": 0,
                 "diminishing": True}


# what "Anzahl" means for a Killer perk (perkdata.json has the same in English, as documentation)
COUNT_MEANS = {
    "Thanatophobia": N_("verletzte, sterbende oder aufgehängte Survivor"),
    "Dying Light / Cull the Weak": N_("Tokens (Haken an anderen als der Obsession)"),
    "Hex: Pentimento": N_("neu entzündete Totems"),
    "Distressing": N_("1 = die Survivor sind im Terrorradius"),
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
}


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
    return _(text, **args)


def _secs(v) -> str:
    return _("{n} s", n=v)


class CalcTab:
    """The page "Rechner" (AutoPage from this tab's structure)."""

    def _calc_data(self):
        data = self.__dict__.get("_calc_loaded")
        if data is None:
            data = self._calc_loaded = gencalc.load()
        return data

    def _calc_state(self) -> dict:
        saved = self.settings.get("calc") if isinstance(self.settings.get("calc"), dict) else {}
        return {**CALC_DEFAULTS, **saved}

    def _tab_calc(self):
        outer, f = self._scroll_tab()
        d = self._calc_data()
        st = self._calc_state()
        surv_names = [NONE] + sorted(d.survivor, key=str.lower)
        tool_names = [NONE] + list(d.toolboxes)
        kill_names = [NONE] + sorted(d.killer, key=str.lower)

        team = ui.LabelFrame(f, text=_("Survivor-Builds"), padding=8)
        team.pack(fill="x")
        row = ui.Frame(team)
        row.pack(fill="x")
        ui.Label(row, text=_("Survivor am Generator")).pack(side="left")
        self.calc_n_var = ui.StringVar(value=str(st["n"]))
        cb = ui.Combobox(row, textvariable=self.calc_n_var, values=[str(i) for i in range(1, 5)], state="readonly",
                         width=4)
        cb.pack(side="left", padx=(8, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._calc_changed())
        self.calc_surv = []
        for i in range(gencalc.MAX_SURVIVORS):
            perks, tool = (st["survivors"] + [[[], ""]] * 4)[i]
            r = ui.Frame(team)
            r.pack(fill="x", pady=(8, 0))
            ui.Label(r, text=_("Survivor {n}", n=i + 1), width=14).pack(side="left")
            vars_ = []
            for slot in range(SLOTS):
                v = ui.StringVar(value=perks[slot] if slot < len(perks) and perks[slot] in d.survivor else NONE)
                c = ui.Combobox(r, textvariable=v, values=surv_names, state="readonly", width=17)
                c._dbdms_px = PERK_PX
                c.pack(side="left", padx=(6, 0))
                c.bind("<<ComboboxSelected>>", lambda e: self._calc_changed())
                vars_.append(v)
            r = ui.Frame(team)                              # the item in its own line: four perks fill the first
            r.pack(fill="x", pady=(4, 0))
            ui.Label(r, text=_("Werkzeugkasten"), width=14).pack(side="left")
            tv = ui.StringVar(value=tool if tool in d.toolboxes else NONE)
            c = ui.Combobox(r, textvariable=tv, values=tool_names, state="readonly", width=17)
            c._dbdms_px = PERK_PX
            c.pack(side="left", padx=(6, 0))
            c.bind("<<ComboboxSelected>>", lambda e: self._calc_changed())
            self.calc_surv.append((vars_, tv))
        ui.Label(team, text=_("Bedingte Perks zählen als aktiv (z. B. Resilience = verletzt, Déjà Vu = auf einem der "
                               "drei nahen Generatoren)."),
                 style="Dim.TLabel", wraplength=620).pack(anchor="w", pady=(6, 0))

        kf = ui.LabelFrame(f, text=_("Killer-Build"), padding=8)
        kf.pack(fill="x", pady=(8, 0))
        self.calc_kill = []
        self.calc_count_boxes = []
        killer, counts = st["killer"], st["counts"] if isinstance(st["counts"], dict) else {}
        for slot in range(SLOTS):
            r = ui.Frame(kf)
            r.pack(fill="x", pady=(0 if slot == 0 else 4, 0))
            name = killer[slot] if slot < len(killer) and killer[slot] in d.killer else NONE
            v = ui.StringVar(value=name)
            c = ui.Combobox(r, textvariable=v, values=kill_names, state="readonly", width=26)
            c._dbdms_px = PERK_PX + 40
            c.pack(side="left")
            c.bind("<<ComboboxSelected>>", lambda e, s=slot: self._calc_killer_picked(s))
            ui.Label(r, text=_("Anzahl")).pack(side="left", padx=(10, 0))
            n = counts.get(name, d.killer[name].get("default", 1)) if name in d.killer else 1
            nv = ui.StringVar(value=str(n))
            c = ui.Combobox(r, textvariable=nv, values=[str(x) for x in COUNT_CHOICES], state="readonly", width=4)
            c.pack(side="left", padx=(6, 0))
            c.bind("<<ComboboxSelected>>", lambda e: self._calc_changed())
            self.calc_count_boxes.append(c)
            mv = ui.StringVar(value="")
            ui.Label(r, textvariable=mv, style="Dim.TLabel", wraplength=360).pack(side="left", padx=(10, 0))
            self.calc_kill.append((v, nv, mv))

        af = ui.LabelFrame(f, text=_("Annahmen"), padding=8)
        af.pack(fill="x", pady=(8, 0))
        self.calc_opts = {}
        for key, label, choices, show in (
                ("great", N_("Great Skill Checks"), GREAT_CHOICES, lambda v: f"{v} %"),
                ("miss", N_("Verfehlte Skill Checks"), MISS_CHOICES, lambda v: f"{v} %"),
                ("kicks", N_("Kicks am Generator"), KICK_CHOICES, str),
                ("kick_at", N_("Killer kommt bei"), KICK_AT_CHOICES, lambda v: f"{v} %"),
                ("away", N_("Weg nach dem Kick"), AWAY_CHOICES, _secs),
                ("walk", N_("Laufweg zwischen Generatoren"), WALK_CHOICES, _secs)):
            r = ui.Frame(af)
            r.pack(fill="x", pady=(0, 4))
            ui.Label(r, text=_(label), width=26).pack(side="left")
            labels = [show(c) for c in choices]
            cur = st.get(key, CALC_DEFAULTS[key])
            v = ui.StringVar(value=labels[choices.index(cur)] if cur in choices else labels[0])
            c = ui.Combobox(r, textvariable=v, values=labels, state="readonly", width=8)
            c.pack(side="left")
            c.bind("<<ComboboxSelected>>", lambda e: self._calc_changed())
            self.calc_opts[key] = (v, choices, labels)
        ui.Label(af, text=_("Kicks und die Anzahl je Killer-Perk gelten für jeden Generator einzeln."),
                 style="Dim.TLabel", wraplength=620).pack(anchor="w")
        self.calc_dr_var = ui.BooleanVar(value=bool(st.get("diminishing", True)))
        ui.Checkbutton(af, text=_("Diminishing Returns anwenden"), variable=self.calc_dr_var,
                       command=self._calc_changed).pack(anchor="w", pady=(2, 0))
        ui.Button(af, text=_("Rechner zurücksetzen"), command=self._calc_reset).pack(anchor="w", pady=(6, 0))

        ef = ui.LabelFrame(f, text=_("Was die gewählten Perks tun"), padding=8)
        ef.pack(fill="x", pady=(8, 0))
        self.calc_effects_var = ui.StringVar(value="")
        ui.Label(ef, textvariable=self.calc_effects_var, wraplength=640, justify="left").pack(anchor="w")

        rf = ui.LabelFrame(f, text=_("Ergebnis"), padding=8)
        rf.pack(fill="x", pady=(8, 0))
        t = ui.Treeview(rf, columns=("calm", "killer"), show="tree headings", height=6, selectmode="none")
        t.heading("#0", text=_("Situation"), anchor="w")
        t.heading("calm", text=_("ohne Killer"), anchor="e")
        t.heading("killer", text=_("mit Killer"), anchor="e")
        t.column("#0", width=300, stretch=False)
        t.column("calm", width=110, anchor="e", stretch=False)
        t.column("killer", width=110, anchor="e", stretch=True)
        t.pack(side="left", fill="x")
        self.calc_tree = t
        self.calc_rates_var = ui.StringVar(value="")
        ui.Label(f, textvariable=self.calc_rates_var, style="Big.TLabel", wraplength=640).pack(anchor="w", pady=(6, 0))
        self.calc_note_var = ui.StringVar(value="")
        ui.Label(f, textvariable=self.calc_note_var, style="Dim.TLabel", wraplength=640).pack(anchor="w", pady=(2, 0))
        ui.Label(f, text=_("Werte aus dem Dead by Daylight Wiki (deadbydaylight.wiki.gg, Stand {date}), nach jedem "
                            "Patch zu prüfen. Nicht berechnet: {names}.",
                            date=d.retrieved, names=", ".join(d.not_modelled)),
                 style="Dim.TLabel", wraplength=640).pack(anchor="w", pady=(6, 0))
        self._calc_render()
        return outer

    # ---------------------------------------------------------------- reading the page
    def _calc_inputs(self):
        d = self._calc_data()
        try:
            n = max(1, min(4, int(self.calc_n_var.get())))
        except ValueError:
            n = 4
        team = []
        for vars_, tv in self.calc_surv[:n]:
            perks = tuple(v.get() for v in vars_ if v.get() in d.survivor)
            team.append(gencalc.Survivor(perks, tv.get() if tv.get() in d.toolboxes else ""))
        names, counts = [], {}
        for v, nv, _mv in self.calc_kill:
            if v.get() in d.killer:
                names.append(v.get())
                try:
                    counts[v.get()] = int(nv.get())
                except ValueError:
                    pass
        opts = {}
        for key, (v, choices, labels) in self.calc_opts.items():
            opts[key] = choices[labels.index(v.get())] if v.get() in labels else CALC_DEFAULTS[key]
        scen = gencalc.Scenario(great=opts["great"] / 100, miss=opts["miss"] / 100,
                                diminishing=bool(self.calc_dr_var.get()), kicks=opts["kicks"],
                                kick_at=opts["kick_at"] / 100, away=float(opts["away"]), walk=float(opts["walk"]))
        return n, team, gencalc.Killer(tuple(names), counts), scen, opts

    def _calc_killer_picked(self, slot: int):
        d = self._calc_data()
        v, nv, _mv = self.calc_kill[slot]
        if v.get() in d.killer:
            nv.set(str(d.killer[v.get()].get("default", 1)))
        self._calc_changed()

    def _calc_changed(self):
        n, _team, _killer, _scen, opts = self._calc_inputs()
        self.settings.set("calc", {
            "n": n, "survivors": [[[v.get() for v in vars_ if v.get() != NONE], tv.get() if tv.get() != NONE else ""]
                                  for vars_, tv in self.calc_surv],
            "killer": [v.get() for v, _nv, _mv in self.calc_kill if v.get() != NONE],
            "counts": {v.get(): nv.get() for v, nv, _mv in self.calc_kill if v.get() != NONE},
            **opts, "diminishing": bool(self.calc_dr_var.get())})
        self._save_soon()
        self._calc_render()

    def _calc_reset(self):
        """All builds and assumptions back to the start values."""
        self.calc_n_var.set(str(CALC_DEFAULTS["n"]))
        for vars_, tv in self.calc_surv:
            for v in vars_:
                v.set(NONE)
            tv.set(NONE)
        for v, nv, _mv in self.calc_kill:
            v.set(NONE)
            nv.set("1")
        for key, (v, choices, labels) in self.calc_opts.items():
            v.set(labels[choices.index(CALC_DEFAULTS[key])])
        self.calc_dr_var.set(True)
        self._calc_changed()

    def _calc_effects(self, d, team, killer) -> str:
        """One line per chosen perk and toolbox (each once): what it does here."""
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
                                                   p=_pct(e["bonus"]), n=f"{e['charges']:g}"))
        for name in killer.perks:
            if name not in seen and name in d.killer:
                seen.add(name)
                lines.append(f"{name} – {effect_text(d.killer[name], d.mech)}")
        return "\n".join(lines) if lines else _("Noch kein Perk gewählt.")

    # ---------------------------------------------------------------- the result
    def _calc_render(self):
        d = self._calc_data()
        n, team, killer, scen, _opts = self._calc_inputs()
        for (v, nv, mv), box in zip(self.calc_kill, self.calc_count_boxes):
            what = COUNT_MEANS.get(v.get()) if v.get() in d.killer else None
            mv.set(_("Anzahl = {what}", what=_(what)) if what else "")
            box.state(["!disabled" if what else "disabled"])     # a perk without a count: nothing to choose
        self.calc_effects_var.set(self._calc_effects(d, team, killer))
        t = self.calc_tree
        t.delete(*t.get_children())
        sizes = gencalc.by_size(d, team, killer, scen)
        for k, calm, hard in sizes:
            t.insert("", "end", iid=f"k{k}", text=_("Ein Generator, {n} Survivor", n=k) if k > 1
                     else _("Ein Generator, Survivor 1 allein"),
                     values=(gencalc.fmt(calm.seconds), gencalc.fmt(hard.seconds)))
        calm_scen = gencalc.Scenario(**{**scen.__dict__, "kicks": 0})
        t.insert("", "end", iid="all", text=_("Fünf Generatoren, alle zusammen"),
                 values=(gencalc.fmt(gencalc.five_together(d, team, None, calm_scen)),
                         gencalc.fmt(gencalc.five_together(d, team, killer, scen))))
        t.insert("", "end", iid="split", text=_("Fünf Generatoren, jeder allein"),
                 values=(gencalc.fmt(gencalc.five_split(d, team, None, calm_scen)),
                         gencalc.fmt(gencalc.five_split(d, team, killer, scen))))
        last = sizes[-1][2] if sizes else None
        speeds = " · ".join(_("S{n}: {v} c/s", n=i + 1, v=f"{r:.2f}") for i, r in enumerate(last.rates)) \
            if last else ""
        self.calc_rates_var.set(_("Tempo am Generator (Ladungen pro Sekunde, Grundwert 1): {speeds}",
                                  speeds=speeds) if speeds else "")
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
