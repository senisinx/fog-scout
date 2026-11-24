# Red-Team-Audit Fog Scout – 04 Befunde und Behebungsplan

**Freigabepunkt:** Bis hier wurden nur Berichte und Angriffstests geschrieben. Produktionscode, Abhängigkeiten, Installer, Workflows und Produktregeln sind unverändert. Phase 5 beginnt erst nach ausdrücklicher Freigabe.

## Priorisierte Übersicht

| Prio | ID | Befund | Status | Kleinste sichere Behebung | Entscheidung nötig? |
|---|---|---|---|---|---|
| **High** (Projekt-Bedrohungsmodell) | RS-003 | Erhöhter Fog Scout startet OBS mit Admin-Token → OBS-Skripte aus `%APPDATA%` laufen als Admin | bestätigt (Fog-Scout-Teil), OBS-Teil Hypothese | **Variante A:** erhöht kein automatischer OBS-Start, stattdessen Hinweis „OBS bitte selbst starten“. **Variante B:** Start über die Shell des Nutzers (abgesenkter Token) – unter Windows zu prüfen (Arbeitsordner/Argumente von OBS) | **Ja** – Variante A nimmt dem erhöht laufenden Programm eine Komfortfunktion; Variante B ändert das Windows-Rechtemodell und ist hier nicht testbar |
| **Medium** | RS-002 | Aufräumen von `cache/*`/`corpus` löscht durch einen verlinkten Ordner ausserhalb des Datenordners | bestätigt (Linux), Windows im Code identisch | Vor dem Aufräumen prüfen, dass **kein Teil zwischen Datenordner und dem aufgeräumten Ordner** ein Link/Junction ist (`fsops.is_link` je Teil); sonst nichts löschen. Betroffen: `thumbs.prune`, `mapstyle.prune`, `corpus.prune` (+ Aufrufer mit `data_dir` als Basis). Der Aufnahmeordner bleibt wie gewollt linkfähig. | Nein (verhält sich für normale Nutzer gleich) |
| **Low** | RS-001 | Backup-ZIP speichert Zeiten/Dauern, an denen die Statistik dauerhaft scheitert (Umgehung von 1.46.4) | bestätigt | Beim Lesen (`history._round_line`, `history._lost_lines`, gleiche Regel in `official._match_line`) nur darstellbare Werte annehmen: Start in einem festen Bereich (z. B. 2000 … 2100), Dauer endlich und ≥ 0 mit Obergrenze; sonst die Zeile wie eine kaputte überspringen. Der Restore nutzt dieselben Funktionen und lässt solche Zeilen damit weg. | Nein |
| **Low** | RS-008 | hosts-Abschnitt ohne Endmarke: Helfer löscht folgende Kommentare des Nutzers | bestätigt | `_ours` ohne Endmarke nur noch für Leerzeilen, die **eigenen** Kommentarzeilen („# Written by Fog Scout…“, „# allowed: …“) und reine GameLift-Einträge; der erste fremde Kommentar beendet den Abschnitt. | Nein |
| Low | RS-006 | Datenordner selbst als Junction → erhöhte Schreibvorgänge mit festen Namen woanders | Hypothese | Nicht in diesem Auftrag; ggf. nach RS-002 entscheiden (ein Nutzer könnte den Datenordner absichtlich per Junction verlegt haben) | Ja |
| Low | RS-005, RS-007, RS-009 | Junction-Wechsel am Aufnahmeordner; erhöhtes Lesen nutzergewählter Ordner; Übernahme-Notiz | Hypothesen | keine Änderung vorgeschlagen; als Restrisiko führen | – |
| Info | RS-004, RS-018, RS-020 | `expandvars` auf HKLM-Wert; Drive-by-Match-Dateien; CI-Details | Info | keine | – |

Verifiziert behoben (kein Handlungsbedarf): RS-010 … RS-017, RS-019 (siehe `01_ATTACK_CATALOG.md`).

## Vorgeschlagene Reihenfolge (Phase 5, nach Freigabe)

1. **RS-003** – nach deiner Wahl A oder B. Empfehlung: **A sofort** (klein, sicher, unter Linux vollständig testbar), B später als eigene Aufgabe mit Windows-Test.
2. **RS-002** – Linkprüfung der Aufräum-Wurzeln unterhalb des Datenordners.
3. **RS-001** – Wertebereich beim Lesen.
4. **RS-008** – eigene Kommentare erkennen.

Je Fix: den zugehörigen `@_open(...)`-Marker entfernen (der Test wird grün), voller Testlauf, pyflakes, Gegenprüfung (Phase 6). Danach laut `CLAUDE.md`: Version in `fogscout/__init__.py`, Zeile in `HISTORY.md`, ggf. README (RS-003 ändert sichtbares Verhalten), neue Texte in allen sieben Sprachen (RS-003 Variante A braucht eine Meldung).

## Mögliche Regressionen

| Fix | Risiko | Gegenmassnahme |
|---|---|---|
| RS-003 A | Wer das Häkchen nutzt und Fog Scout über die Aufgabe startet, muss OBS selbst öffnen | klare Meldung; Häkchen-Tooltip anpassen; nicht erhöht unverändert (Test `…_not_elevated_obs_is_started_as_before`) |
| RS-003 B | OBS startet ohne richtigen Arbeitsordner („Failed to find locale“), `--minimize-to-tray` geht über die Shell verloren | nur mit Windows-Prüfung umsetzen |
| RS-002 | Nutzer mit absichtlich verlinktem `cache`-Ordner (z. B. auf eine andere Platte): Cache wächst, wird nicht mehr aufgeräumt | Log-Zeile; bewusst so (Löschen mit Admin-Rechten durch einen Link ist die Lücke) |
| RS-001 | Echte Runden ausserhalb des Bereichs gingen verloren | Programm schreibt nur `time.time()`-Werte; Bereich grosszügig wählen; Test mit alten Testdaten (`tests/data`) |
| RS-008 | Eigener Abschnitt ohne Endmarke mit unbekanntem eigenen Kommentar bleibt teilweise stehen | nur GameLift-Einträge wirken; `remove_foreign` entfernt sie ohnehin |

## Was diese Änderungen berühren

- **Windows-Rechtemodell:** RS-003 (B) – ja; RS-002 – nein (nur weniger löschen).
- **Nutzerfreigaben / Produktregeln (`CLAUDE.md`, `docs/regeln/obs.md`):** RS-003 ändert das Verhalten einer freigegebenen OBS-Funktion → deine Entscheidung. Keine Änderung an Netzwerk, Telemetrie, Claude, YouTube, Spotify, Match-Daten.
- **Datenformate:** keine (RS-001 liest strenger, schreibt nichts anders).
- **Abhängigkeiten, Installer, Workflows:** keine.

## Offene Restrisiken nach den Fixes

- Unsignierte Releases / GitHub-Konto (akzeptiert).
- `start.bat`-Betrieb mit „höchsten Rechten“ in nutzerbeschreibbarem Ordner (dokumentiert).
- RS-005/006/007/009 (Hypothesen, Low).
- Nicht unter Windows ausgeführt: alle Junction-/UAC-/OBS-Aussagen.
