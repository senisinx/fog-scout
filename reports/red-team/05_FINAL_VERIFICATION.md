# Red-Team-Audit Fog Scout – 05 Behebung und Gegenprüfung

Freigabe: Saru „Weiter“ (24.11.2026) nach dem Freigabepunkt in `04_REMEDIATION_PLAN.md`. Für RS-003 wurde keine Variante genannt – umgesetzt ist **Variante A** (die Empfehlung). Version **1.57.48**. Keine neuen Abhängigkeiten, Netzwerkzugriffe, Rechte, Telemetrie oder Datenformate; Installer und Workflows unverändert.

## Behebungen

| ID | Änderung | Dateien |
|---|---|---|
| RS-003 | Läuft Fog Scout erhöht, startet es OBS nicht selbst: `_launch_obs` meldet einmal je DBD-Start `OBS_ELEVATED` („OBS bitte selbst starten – Fog Scout läuft als Administrator …“) und setzt `_obs_late`, damit keine Folgemeldung „gestartet, aber nicht erreichbar“ kommt; `_start_obs_process` verweigert erhöht zusätzlich mit `PermissionError` (zweite Sperre). Nicht erhöht unverändert. | `obsrec.py`, `i18n_*.py` (7 Sprachen), `README.md`, `README.en.md`, `docs/regeln/obs.md` (Regel **verschärft**, nicht gelockert) |
| RS-002 | `fsops.linked_root(folder, levels)`: Aufräumen unterbleibt, wenn die Wurzel (bzw. bei `cache/<x>` auch `cache`) ein Link/Junction ist. Angewendet in `thumbs.prune`, `mapstyle.prune`, `corpus.prune` und dem Aufräumen in `backups.snapshot`. Der Aufnahmeordner darf weiterhin ein Link sein (gewollt). | `fsops.py`, `thumbs.py`, `mapstyle.py`, `corpus.py`, `backups.py` |
| RS-001 | `history.plausible(t, seconds)`: Start 0 … 2100-01-01 (`LATEST_T`), Dauer 0 … 7 Tage (`MAX_SECONDS`); NaN fällt durch. Zeilen ausserhalb werden wie kaputte übersprungen in `_round_line`, `_lost_lines`, `backups._plan` (verlorene Runden), `official._match_line`; die Dauer aus einer Match-Datei im Download-Ordner über 7 Tage gilt als unbekannt (0). | `history.py`, `backups.py`, `official.py` |
| RS-001b (neu in der Gegenprüfung) | Aufnahme- und Clip-Index: `t`/`end`/`source` ausserhalb von `plausible` werden 0 (Eintrag bleibt, seine Datei kann weiter aufgeräumt werden). | `recindex.py` |
| RS-008 | Ohne Endmarke gehören nur Leerzeilen, die eigenen Kommentarzeilen (`OWN_COMMENTS`) und reine GameLift-Einträge zum Abschnitt; der erste fremde Kommentar bleibt stehen. | `hostsedit.py` |

Doku: `HISTORY.md` (eine Zeile 1.57.48), `CLAUDE.md` (fsops-Zeile: `linked_root`), Version in `fogscout/__init__.py`.

## Red → Green je Angriff

Red-Nachweis: der Fix der jeweiligen Dateien kurz per `git stash` entfernt, Tests laufen lassen, Fix zurück.

| ID | Tests | ohne Fix | mit Fix |
|---|---|---|---|
| RS-003 | `test_rs_003_the_elevated_program_never_starts_obs_with_its_own_token`, `test_rs_003_dbd_starting_while_elevated_says_start_obs_yourself_and_starts_nothing` (neu, ganzer Ablauf), Gegenprobe `…_not_elevated_obs_is_started_as_before` | rot (Phase 3; der Ablauf-Test zeigte nach dem ersten Fix-Entwurf noch die Folgemeldung „OBS wurde gestartet, ist aber nicht erreichbar“ → `_obs_late` ergänzt) | grün |
| RS-002 | 6 Tests: Vorschaubilder (`leaf`, `parent`, **`cache_above_leaf`** neu = realistische Variante), Kartenstil, Korpus, **Sicherungen** (neu) | 6 failed | 7 passed (inkl. „verified“) |
| RS-001 | 5 Backup-Varianten, 3 offizielle Zeilen (neu), Download-Datei (neu), App-Test Statistik | 10 failed | grün |
| RS-001b | `test_rs_001_a_recordings_index_holds_only_showable_times[1e300, -1e300, 5e12]` | 2 failed, 1 passed (`5e12` ist unter Linux darstellbar – die Grenze zielt auf Windows, dessen `localtime` nur bis Jahr 3000 reicht) | 3 passed; App-Gegenprobe Seite Aufnahmen ohne Fehler |
| RS-008 | `…_keeps_the_users_own_comments`, Gegenprobe `…_our_own_section_without_its_end_marker_still_goes_completely` (neu) | 1 failed, 1 passed | 2 passed |

Die `xfail`-Markierungen sind entfernt (der Helfer `_open` ebenso); alle Angriffstests laufen jetzt als normale Tests.

## Gegenprüfung (erneut angreifen)

| Versuch | Ergebnis |
|---|---|
| RS-003 über einen anderen Startweg | Alle Programmstarts gesucht (`start_program`, `Popen`, `startfile`, `ShellExecute`): ausser OBS nur eigene Programme (ffmpeg aus dem Bündel, Setup nach Hash-Prüfung, Neustart über `sys.executable`), Browser/Dateien über `explorer.exe` (1.38.21). Kein weiterer Start eines nutzersteuerbaren Programms mit Admin-Token gefunden. |
| RS-003 Umgehung über `self.start_obs` | Das Attribut setzen nur Tests; `_launch_obs` prüft vor dem Aufruf, `_start_obs_process` noch einmal. |
| RS-002 andere Aufräumstellen | Alle `delete_inside`-Aufrufer geprüft: Aufnahmeordner/Clips (`recindex`, `obsrec`) – Wurzel absichtlich linkfähig (Rest RS-005); `clipedit._analysis_read` löscht nur eine Datei mit aus SHA-256 berechnetem Namen, `imageedit._drop_stale_tmp` nur eigene Temp-Namen im gewählten Ausgabeordner – beides kein brauchbares Löschprimitiv; `relupdate` hat seine eigene Prüfung (1.55.4). |
| RS-002 Varianten | Link eine Ebene höher (`cache` statt `cache/clipthumbs`) – jetzt abgedeckt und getestet. Ganzer Datenordner als Junction (RS-006) bewusst **nicht** gesperrt (Nutzer kann ihn absichtlich verlegt haben); Aufräumen folgt dann – Ziel ist aber der eigene, verlegte Datenordner. |
| RS-001 weitere Leser | **Fund RS-001b** (Aufnahme-/Clip-Index) – behoben, siehe oben. `inputs.load` prüft `isfinite`, Zeiten dort sind Sekunden der Aufnahme (keine Datumsumrechnung). Offizielle Download-Dateien: Start schon vorher auf `EARLIEST … jetzt + 1 Tag` begrenzt. |
| RS-001 Grenzfälle | `-1e300`, `NaN`, `Infinity`, `1e300`, `seconds=1e300` getestet; `plausible` fängt `TypeError`/`OverflowError` (z. B. riesige Ganzzahl). Echte Daten liegen weit innerhalb (Programm schreibt nur `time.time()`); die vorhandenen Tests mit kleinen Zeiten (`t: 1000.0`) laufen weiter. |
| RS-008 Grenzfälle | Eigener Abschnitt ohne Endmarke wird weiter vollständig entfernt (Gegenprobe-Test). Rest: ein Nutzerkommentar, der wörtlich mit `# allowed: ` beginnt und direkt nach unserem Abschnitt steht, gilt als eigener – vernachlässigbar. |
| Tests nur Implementierung gespiegelt? | Die Tests prüfen Invarianten (Datum darstellbar; nichts ausserhalb gelöscht; kein OBS-Kind mit Admin-Token; Nutzerkommentare bleiben). Ein anderer korrekter Fix (z. B. OBS über abgesenkten Token) bestünde sie ebenfalls. |

## Ausgeführte Prüfungen

| Prüfung | Ergebnis |
|---|---|
| `pytest tests` nach RS-001/002/003/008 (vor RS-001b) | 2137 passed, 48 skipped, 0 failed |
| `pytest tests` abschliessend (mit RS-001b) | **2140 passed, 48 skipped, 0 failed** (554 s, Linux, Python 3.13.18) |
| `pyflakes fogscout tests tools` | sauber |
| `git diff --check` | sauber |
| Windows-CI | läuft erst im PR (nicht hier ausgeführt) |
| Offscreen-Screenshots | nicht nötig: keine Layout-Änderung, nur ein neuer Meldungstext |

## Offene Restrisiken

- **RS-003 Variante B** (OBS automatisch, aber mit abgesenkten Rechten) – nur mit Windows-Test; bis dahin startet die installierte Version OBS nicht mehr selbst. Das ist eine sichtbare Verhaltensänderung.
- **RS-005/006/007/009** – Hypothesen, Low, unverändert.
- Unter Windows nicht ausgeführt: Junction-Semantik von `linked_root`/`is_link` (der Code nutzt dieselbe Prüfung wie seit 1.55.4 für den Update-Ordner), OBS-Skriptverhalten.
- Unsignierte Releases, start.bat-Betrieb mit höchsten Rechten (akzeptiert).
