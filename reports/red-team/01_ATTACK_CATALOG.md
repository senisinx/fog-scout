# Red-Team-Audit Fog Scout – 01 Angriffskatalog

Geprüfter Commit `1469fbf`. **Status:** *bestätigt* = per Test reproduziert (rot), *verifiziert behoben* = Angriff erneut versucht und abgewehrt (grüner Test), *Hypothese* = nur aus dem Code abgeleitet, nicht ausgeführt, *akzeptiert/dokumentiert* = bewusst so entschieden.

**CVSS 4.0:** Vektoren nach bestem Wissen gesetzt; **Zahlenwerte wurden nicht mit dem offiziellen Rechner ermittelt** und deshalb nicht angegeben. Massgeblich ist die begründete Priorität.

**Angreifermodelle:**
- **A1 lokal, gleicher Nutzer, mittlere Integrität** (Malware/Tool im Konto des Nutzers) gegen den **erhöht laufenden** installierten Fog Scout. Ziel: Admin-Rechte oder Schaden ausserhalb des eigenen Kontos.
- **A2 fremde Datei** (Sicherungs-ZIP, Projekt, Match-Datei per Drive-by-Download), die der Nutzer öffnet bzw. die das Programm von selbst einliest.
- **A3 lokale Gegenstelle** auf `127.0.0.1`/Named Pipe.
- **A4 kompromittierter externer Dienst/Konto** (GitHub, API-Antworten).

---

## Bestätigte Befunde

### RS-003 – Erhöhter Fog Scout startet OBS mit Administrator-Token (UAC-Umgehung über OBS-Skripte)
| | |
|---|---|
| Komponente | `obsrec.Recorder._start_obs_process` → `launch.start_program` → `subprocess.Popen` |
| Modell | A1; Vorbedingung: installierte Version (läuft per Aufgabe erhöht), Häkchen „OBS mit DBD starten, falls es noch nicht läuft“ (Standard **aus**), OBS installiert, OBS läuft beim DBD-Start nicht |
| Schritte | 1. Malware schreibt in `%APPDATA%\obs-studio\basic\scenes\<Sammlung>.json` unter `modules.scripts-tool` ein Lua/Python-Skript (Datei liegt im Nutzerprofil, ohne Rechte schreibbar). 2. Nutzer startet DBD. 3. Fog Scout (Admin) startet `obs64.exe` per `Popen` – OBS erbt den Admin-Token. 4. OBS lädt die Szenensammlung und führt das Skript **als Administrator** aus (`os.execute`/`subprocess`). |
| Wirkung | Codeausführung mit Admin-Rechten ohne UAC-Abfrage (Vertraulichkeit/Integrität/Verfügbarkeit hoch) |
| Vorhandene Schutzmassnahmen | `obs_exe` nimmt nur HKLM/`known_folder("ProgramFiles")` (die Exe ist echt); `clean_process` bereinigt DLL-Suche/Umgebung. **Der Token selbst wird nicht abgesenkt** – README sagt sogar „OBS läuft dann mit denselben Rechten wie das Programm (Administrator)“. Das ist genau das Muster, das 1.38.21 (SEC-1) für Browser/Dateien bereits behoben hat (`_through_users_shell`). |
| Beleg | `tests/test_red_team.py::test_rs_003_the_elevated_program_never_starts_obs_with_its_own_token` rot: `OBS started as a child of the elevated program: [['…/obs64.exe', '--minimize-to-tray']]`. Die OBS-Seite (Skript läuft) ist **Hypothese** (OBS-Verhalten, nicht ausgeführt). |
| CVSS 4.0 (Vektor) | `AV:L/AC:L/AT:P/PR:L/UI:P/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N` |
| Priorität | **High** im Bedrohungsmodell des Projekts (UAC gilt hier als Grenze, siehe 1.33.5/1.38.21); Microsoft betrachtet UAC nicht als formale Sicherheitsgrenze – absolut eher Medium. Opt-in senkt die Wahrscheinlichkeit. |
| Testidee | Elevated → kein `Popen` mit `obs64.exe` als argv[0] (Gegenprobe: nicht erhöht unverändert). |

### RS-002 – Erhöhtes Cache-Aufräumen folgt einem verlinkten Cache-Ordner (Löschen ausserhalb des Datenordners)
| | |
|---|---|
| Komponente | `thumbs.prune` (Aufrufer: `qt_library.ThumbLoader` → `cache/clipthumbs` u. a., `clipedit._analysis_write` → `cache/analysis`, `.json`), `mapstyle.prune` (`cache/maps_dark`), `corpus.prune` (`corpus/`); Kern `fsops.delete_inside` |
| Modell | A1 gegen die erhöhte installierte Version |
| Schritte | 1. Malware ersetzt `%LOCALAPPDATA%\FogScout\cache\clipthumbs` (oder `cache`, oder den ganzen Datenordner) durch eine Junction auf einen fremden Ordner, z. B. `C:\Users\<anderer>\Pictures` oder einen Admin-Ordner. 2. Beim ersten Öffnen der Bibliothek je Sitzung ruft Fog Scout (Admin) `thumbs.prune` auf. 3. `delete_inside` löst den **Ordner selbst** auf (`_folder_final`), prüft nur die Teile *unterhalb* und löscht dort jede `.png`/`.jpg` (bzw. `.json` für die Analysen) älter als 90 Tage. |
| Wirkung | Löschen fremder Bild-/JSON-Dateien mit Admin-Rechten (Integrität/Verfügbarkeit, auch anderer Konten). Keine Ordner, keine beliebigen Endungen → kein direkter Weg zu SYSTEM (der bekannte „Config.Msi“-Trick braucht Ordner-Löschung). `mapstyle`/`corpus` nur mit eigenen Namensmustern (geringer). |
| Vorhandene Schutzmassnahmen | 1.38.57: Links **unterhalb** des Ordners werden nicht gefolgt (verifiziert, Test `…_a_link_below_the_pruned_folder_is_still_not_followed` grün). 1.55.4 (SEC-5) prüft `is_link` nur für `cache/update`. `delete_inside` lässt den Wurzelordner absichtlich ein Link sein („the folder itself may be a link the user chose“ – gedacht für den Aufnahmeordner). Für Cache-Ordner im Datenordner wählt der Nutzer aber nie einen Link. |
| Beleg | 4 rote Tests (`test_rs_002_*`), z. B. `AssertionError: a picture outside the data folder was deleted`. Unter Linux mit Symlinks nachgestellt; Windows-Junctions nicht ausgeführt (Code-Pfad identisch: `_folder_final` folgt der Junction). |
| CVSS 4.0 (Vektor) | `AV:L/AC:L/AT:N/PR:L/UI:N/VC:N/VI:N/VA:N/SC:N/SI:L/SA:L` |
| Priorität | **Medium** (konkrete Löschprimitive als Admin, aber eingeschränkte Endungen/Alter). |

### RS-001 – Sicherungs-ZIP schreibt Zeiten, an denen die Statistik dauerhaft scheitert (Umgehung des Fixes 1.46.4)
| | |
|---|---|
| Komponente | `backups._plan`/`restore`, `history._lost_lines`, `history._round_line`; Folge in `app_stats._stats_render` (`time.localtime`) |
| Modell | A2 (präpariertes „Backup“ wird geteilt, Nutzer wählt „Aus Sicherung wiederherstellen (ZIP) …“) |
| Schritte | ZIP mit `rounds.jsonl`, darin eine verlorene Runde `{"lost": true, "t": Infinity}` (oder `NaN`, `1e300`) oder eine gezählte Runde mit `t: 1e300` bzw. `seconds: 1e300`. |
| Wirkung | Jede Darstellung der Statistik wirft `OverflowError`/`ValueError` (Log „Ereignis: OverflowError …“), dauerhaft bis zur Handreparatur der Datei. Nur Verfügbarkeit, nur eigene Daten. |
| Vorhandene Schutzmassnahmen | 1.46.4 prüft `math.isfinite` nur für gezählte Runden (`_round_line`) und offizielle Matches – **nicht** für verlorene Runden und **nicht** auf einen darstellbaren Bereich (1e300 ist endlich). |
| Beleg | 6 rote Tests (`test_rs_001_*`), App-Test: `OverflowError: timestamp out of range for platform time_t` (`app_stats.py:903`). |
| CVSS 4.0 (Vektor) | `AV:L/AC:L/AT:N/PR:N/UI:A/VC:N/VI:L/VA:L/SC:N/SI:N/SA:N` |
| Priorität | **Low** (eigene Daten, Nutzeraktion nötig, Snapshot `backup/…restore` vorhanden). |

### RS-008 – hosts-Abschnitt ohne Endmarke: Admin-Helfer löscht Kommentare des Nutzers
| | |
|---|---|
| Komponente | `hostsedit._section` (`_ours` zählt jede Kommentar-/Leerzeile als eigene), `build` |
| Modell | kein Angreifer nötig; beschädigte/gekürzte hosts-Datei (Editor, anderes Tool, Sync) |
| Schritte | `BEGIN` vorhanden, `END` fehlt; danach Kommentare/auskommentierte Einträge des Nutzers. „Region freigeben“/„anwenden“. |
| Wirkung | Alle direkt folgenden Kommentar- und Leerzeilen werden gelöscht (z. B. `#10.0.0.5 printer.local`). Aktive Fremdeinträge bleiben. Integrität einer Systemdatei, gering. |
| Beleg | `test_rs_008_…` rot (beide `remove_foreign`-Varianten). |
| CVSS 4.0 (Vektor) | `AV:L/AC:H/AT:P/PR:N/UI:A/VC:N/VI:L/VA:N/SC:N/SI:N/SA:N` |
| Priorität | **Low**. |

---

## Hypothesen (nicht ausgeführt, nicht als Lücke bestätigt)

| ID | Fläche | Idee | Warum (noch) kein Befund | Prio |
|---|---|---|---|---|
| RS-004 | `obsrec._obs_registry` | `os.path.expandvars` auf den HKLM-Wert nutzt die Prozessumgebung (aus `HKCU\Environment`). | Nur wirksam, wenn der HKLM-Wert `%VAR%` enthält; der OBS-Installer schreibt einen festen Pfad. Nicht unter Windows prüfbar. | Info |
| RS-005 | `recindex.prune`, Aufnahmeordner | Aufnahmeordner ist eine Junction; zwischen Lesen des Index (Junction → Angreiferordner) und `delete_inside` (Junction umgebogen) wechseln → Löschen von Videodateien mit indexierten Namen anderswo. | Windows-Race, nicht nachgestellt; auf Video-Endungen begrenzt (`deletable`). Gleiche Wurzel wie RS-002 (Ordner selbst darf Link sein – hier aber gewollt). | Low |
| RS-006 | Datenordner selbst | `%LOCALAPPDATA%\FogScout` als Junction → erhöhte Schreibvorgänge (`settings.json`, Log, Caches, `cache/update`) landen in fremden Ordnern. | Nur feste Namen/Endungen, Inhalte kaum steuerbar; kein Weg zu Codeausführung gefunden. `relupdate._linked` prüft nur `cache`/`cache/update`. Wird durch den Fix von RS-002 (Prüfung beim Start) mit abgedeckt. | Low |
| RS-007 | erhöhtes Lesen nutzergewählter Ordner | `SteamPath` aus HKCU, `shots_folder`, Aufnahmeordner → Admin liest fremde Bilder/Videos und legt Vorschaubilder im nutzerlesbaren `cache/` ab (Informationsabfluss über Kontogrenzen). | Braucht Öffnen der Seite; Vorschauen klein; designbedingt bei jeder „Ordner wählen“-Funktion eines erhöhten Programms. | Low |
| RS-009 | `takeover` | Übernahme-Notiz im Datenordner zeigt auf beliebigen Ordner → Admin kopiert dortige feste Dateinamen in den Datenordner. | Nur einmal angeboten (Marke), nur feste Namen, Kopie nie überschreibend; DPAPI-Geheimnisse anderer Konten unbrauchbar. | Low |
| RS-018 | offizielle Match-Dateien (Drive-by) | Jede Webseite kann `fogscout-matches.json` in „Downloads“ legen; Werte wie `seconds: 1e300` werden gespeichert. | Probe: Statistik blieb fehlerfrei (`seconds` ohne Verknüpfung nicht in Zeitrechnung). Datenvergiftung der Statistik ist in 1.38.57 als offen dokumentiert. | Info |

## Verifiziert behoben / ohne Befund (Angriff erneut versucht)

| ID | Angriff | Beleg |
|---|---|---|
| RS-010 | ZIP-Slip (`../`, absolute/Windows-Pfade, `\`-Trenner, Unterordner, Gerätenamen, Endungen) | neu: `test_rs_010_verified_zip_member_names_never_leave_the_data_folder` (9 Varianten grün); bestehend: `test_device_names_odd_endings_and_foreign_kinds_are_never_taken`, `test_the_real_unpacked_bytes_count_…` |
| RS-011 | Manipulierte Claude-Antwort (NaN/∞/riesig/bool/unbekannte Operation) | neu: `test_rs_011_verified_claude_operations_with_non_numbers_change_nothing`; Texte für Shorts werden als Bild gerendert (kein `drawtext`, keine Filter-Injection) |
| RS-012 | Manipulierter hosts-Job in `%TEMP%` (fremde Namen, CRLF-Injection) | neu: `test_rs_012_verified_the_hosts_job_cannot_name_any_other_server` |
| RS-013 | YouTube-Warteschlange/Index zeigt aus dem Aufnahmeordner | neu: `test_rs_013_verified_…`; bestehend 1.38.20 |
| RS-014 | Update: fremde URL, fehlende/abweichende Prüfsumme, HTTP-Weiterleitung, verlinkter Update-Ordner, Austausch zwischen Prüfung und Start | bestehend: `test_a_setup_from_anywhere_else_or_without_checksum_is_refused`, `test_the_download_is_kept_only_when_its_sha256_matches`, `test_a_redirect_to_plain_http_is_refused`, `test_a_linked_update_folder_is_neither_written_nor_cleaned`, `test_a_changed_setup_is_never_staged_and_leaves_nothing`, `test_the_setup_is_checked_again_right_before_it_starts` (alle grün im Basislauf) |
| RS-015 | Falsches „OBS“ auf 127.0.0.1 nennt fremde Datei zum Verschieben/Löschen | bestehend: `test_an_old_video_elsewhere_is_never_taken_on_the_word_of_the_port`, Grössengrenzen `MAX_MESSAGE`/`MAX_HANDSHAKE` |
| RS-016 | Falscher Discord-Server auf der Pipe (Identitätsübernahme, Riesenrahmen, Nicht-Objekte) | Code: `SECURITY_IDENTIFICATION`, Rahmen ≤ 1 MiB, Nicht-Dict = Fehler; bestehende Tests 1.33.5/1.55.4 |
| RS-017 | OAuth-Rückruf: falscher `state`, fremder Pfad, Portübernahme | bestehend: `test_the_login_listener_takes_only_its_callback_with_the_right_state`, `test_the_login_listener_binds_exclusively_…` |
| RS-019 | Prompt-Injection über OCR/Map-Namen/Bilder | Antworten nur als ids/Operationen aus festen Listen, Ausführung erst nach Bestätigung (`askclaude.parse`, `editcommands.apply`) – Injection kann höchstens erlaubte, bestätigungspflichtige Operationen vorschlagen |
| RS-020 | CI/Lieferkette | Actions per SHA, `contents: read`, Release nur `workflow_dispatch` auf `main`, Wheels mit `--require-hashes --only-binary`. Rest-Info: `requirements-dev.txt` ohne Hashes nur in PR-Jobs mit Lesetoken; `cache: pip` durch Hashes abgesichert. |

## Akzeptiert/dokumentiert (kein neuer Befund)

- **start.bat-Betrieb mit Aufgabe „höchste Rechte“** in einem nutzerbeschreibbaren Ordner = UAC praktisch aus (README).
- **Releases unsigniert**; Konto-Übernahme = Code bei allen Nutzern (1.38.57 „Offen“, Nutzerentscheidung).
- **Match-Dateien ohne Kopplung** an das Userscript (1.38.57 „Offen“).
