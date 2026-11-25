# DBD-Aufnahmen → Fog-Scout-Optimierungen (Bericht, 25.11.2026)

Auswertung der eigenen OBS-Aufnahmen des Nutzers (Aufnahmeordner `D:\DBD`) und was daraus in Fog Scout umgesetzt,
zurückgestellt oder verworfen wurde. Alle Messungen lasen die Originale nur (bundled ffmpeg von imageio-ffmpeg 0.6.0,
OpenCV, das eigene OCR-Modell); nichts wurde verändert, verschoben, umbenannt oder hochgeladen. Standbilder und
Kontaktbögen liegen in einem lokalen Analyseordner ausserhalb des Repos (nicht eingecheckt – zeigen Spielernamen).

Kennzeichnung: **sicher** = gemessen/angesehen und reproduziert · **wahrscheinlich** = Befund belegt, Ursache
plausibel, aber nicht bewiesen · **nicht zuverlässig** = aus den Aufnahmen nicht belegbar.

## 1 Bestand (Phase 1)

| | |
|---|---|
| Dateien | 1 040 MP4 (306 im Hauptordner, 711 in `Farming/`, 23 in `Clips/`), dazu Screenshots, Indexdateien, Montage-Sicherungen |
| Gesamtdauer | 111,7 h; Runde Median 430 s, 54 kürzer als 60 s |
| Abspielbar | 1 040/1 040: Kopf gelesen und an 3 Stellen je Datei ein Bild dekodiert |
| Format | H.264 (18 AV1), 60 fps (3 Dateien melden 161–178 fps – Container-Angabe, schwankende Bildrate) |
| Auflösung | 3440×1440: 796 · 1716×720: 244 (ältere Aufnahmen, kleinere OBS-Ausgabe) |
| Bitrate | Median 6,5 Mbit/s (4,9–17,1) → bei 3440×1440@60 nur 0,022 Bit/Pixel |
| Speicher | 328 GB Runden, davon 215 GB Farming; Clips 0,6 GB |
| Laufwerk | Samsung T7, **exFAT** |

Vollständig ausgewertet (ohne Sichtung jedes Bilds): Helligkeit der Bildmitte an 30/50/70 % jeder Datei (schwarze
Aufnahmen), Score-Event-Ecke von 34 Runden mit 4 Blicken/s (25 087 Ausschnitte), Zähler + Ring auf 14 Runden mit
offiziellem Match (`official.jsonl`), stehendes Overlay auf einer Zufallsstichprobe.

**Sampling für die Sichtung:** 15 Aufnahmen geschichtet (Zufall, Seed 42) nach Killer/Survivor × normal/Farming plus
Clips; je Runde ein Kontaktbogen mit 10 Bildern: 0:02, 0:15, 10/25/40/55/70/85 % der Länge, Ende −25 s, Ende −4 s.
Gezielte Nachsichtung an auffälligen Stellen (Einzelbilder ±10 s).

| Bogen | Ordner | Datei | Dauer | Auflösung | kbit/s |
|---|---|---|---|---|---|
| 00 | – | 2026-11-05 18-33 Blood Lodge – The Nurse.mp4 | 14:15 | 3440×1440 | 6644 |
| 01 | – | 2026-10-26 22-49 Greenville Square – The Hillbilly.mp4 | 8:07 | 1716×720 | 6444 |
| 02 | – | 2026-11-14 02-07 Garden of Joy – The Nurse.mp4 | 14:01 | 3440×1440 | 6512 |
| 03 | – | 2026-11-13 19-17 Dead Sands.mp4 | 8:21 | 3440×1440 | 6354 |
| 04 | – | 2026-11-08 19-44 Greenville Square – Survivor.mp4 | 7:54 | 3440×1440 | 6590 |
| 05 | – | 2026-11-01 21-32 Midwich Elementary School – Survivor.mp4 | 7:22 | 1716×720 | 6520 |
| 06 | – | 2026-10-31 02-05 Coal Tower I – Survivor.mp4 | 9:00 | 1716×720 | 6582 |
| 07 | – | 2026-11-21 20-25 Raccoon City Police Station East Wing – Survivor.mp4 | 9:03 | 3440×1440 | 6587 |
| 08 | Farming | 2026-11-01 11-01 Family Residence – The Hillbilly.mp4 | 8:51 | 1716×720 | 6473 |
| 09 | Farming | 2026-11-25 09-28 The Pale Rose – The Hillbilly.mp4 | 7:30 | 3440×1440 | 6497 |
| 10 | Farming | 2026-11-22 18-55 Midwich Elementary School – The Hillbilly.mp4 | 7:20 | 3440×1440 | 6508 |
| 11 | Farming | 2026-10-31 14-02 The Game – The Hillbilly.mp4 | 10:13 | 1716×720 | 6498 |
| 12 | Farming | 2026-10-31 13-42 Nostromo Wreckage – Survivor.mp4 | 7:15 | 1716×720 | 6506 |
| 13 | Clips | 2026-10-19 08-14 Clip (instant clip).mp4 | 0:02 | 1716×720 | 5808 |
| 14 | Clips | 2026-10-24 02-23 Clip (instant clip).mp4 | 0:28 | 1716×720 | 6066 |

Nicht in den Aufnahmen: Lobby (ausser einem Clip), Ladebildschirm, Menüs vor dem Match – OBS nimmt ab dem
Map-Banner auf. Was davon abhängt, ist unten als „nicht zuverlässig“ markiert.

## 2 Befunde mit Belegen

### Sicher

| # | Befund | Belege |
|---|---|---|
| S1 | **Score Events** oben rechts: Name weiss, Punkte rot (+N / MAX), Kategorie-Symbol im Ring; neue Zeilen oben, 2,5–3 s sichtbar; der **rote Ring zeigt, wie voll die Kategorie ist** | Bogen 00 07:50 (CHASE, PRECISE BLINK, SURVIVOR FOUND), 08 07:32 (HIT, BLEEDING, SURVIVOR FOUND), 10 06:14 (PROTECTION, LATE HOOK RESCUE); Ringfüllung Family Residence 21.11.: Objective 0:44 → 7:50 von wenig zu fast voll (offiziell 9 862/10 000) |
| S2 | **31 Aufnahmen nur Overlay auf Schwarz**, in Serien: 24.11. 17 in Folge (dann 6), 17.11. 4, 01.11. 2, 18.11. 2; eine Runde zeigt die ganze Zeit den **Epic Games Launcher** | z. B. `2026-11-24 22-30 Dead Sands – Survivor.mp4`; Launcher: `2026-10-25 15-40 Trickster's Delusion.mp4` (0:03–1:01, Timer steht auf 01:31) |
| S3 | **Löschen auf dem Aufnahmelaufwerk scheiterte immer** (exFAT kennt `FileAttributeTagInfo` nicht, WinError 87, still geschluckt): 532 Farming-Aufnahmen (~200 GB, ab 20.10.) trotz 7-Tage-Frist | Probe mit Testdatei auf dem Laufwerk; `Get-Volume D` = exFAT |
| S4 | **Warte-Karte liegt über DBD-UI**, sobald DBD die volle Breite nutzt (Scoreboard, Lobby) | Bogen 04 07:50 (Scoreboard, 4. Zeile), 06 08:56 (Scoreboard, 4. Zeile), Clip 14 0:04–0:27 (Lobby, über der linken Menü-Spalte) |
| S5 | **Rolle falsch im Dateinamen**: Survivor-Runden heissen „– The Hillbilly“ | Bogen 10, 11 (offiziell Survivor); über alle verknüpften Runden 94× Killer statt Survivor (82 davon Farming) – in der Statistik bereits korrigiert (`_official_join` übernimmt die offizielle Rolle) |
| S6 | **Overlay-Bild in der Aufnahme steht still**, während das Spiel weiterläuft (Timer und Systemwerte eingefroren) | Bogen 08: 04:35–06:20 (Timer 04:36, Uhr 11:06 bleibt; Generatoren laufen 3→1); `2026-11-06 18-20 Trickster's Delusion – The Hillbilly` 04:14–05:57 viele Stücke von 3–20 s |
| S7 | Map-Erkennung sehr zuverlässig: 21 Abweichungen in 1 961 mit offiziellem Match verknüpften Runden (1,1 %), alle automatisch, keine unsichere | `rounds.jsonl` × `official.jsonl` |
| S8 | HUD zeigt Generatoren übrig, Survivor-Status, Kraft-Ladungen, Endgame-Collapse-Balken, Tor-Öffnen | Bogen 00 (5→4→2 Gens), 04 06:43 (OPEN ESCAPE), 00 13:50 / 04 07:29 / 10 06:55 (EGC-Balken) |
| S9 | Ergebnisbildschirm „BLOODPOINTS EARNED“ zeigt die vier Kategorien mit Endwerten | Bogen 00 14:11, 08 08:47 (BRUTALITY/DEVIOUSNESS/HUNTER/SACRIFICE), Stichprobe Ironworks 23.11. Ende |
| S10 | Aufnahme beginnt beim Banner; die erste Sekunde ist das Spielbild noch verschoben (OBS passt die Fensterquelle an) | Bogen 04/06/08 0:02 |

### Wahrscheinlich

| # | Befund | Begründung |
|---|---|---|
| W1 | S6 entsteht, wenn der Programm-Takt (`_tick_overlay`, auch OBS-Overlaybild) blockiert – z. B. während man im Fog-Scout-Fenster arbeitet, während DBD im Hintergrund läuft | Stillstand nur in Killer-Farming-Runden mit stehendem Killer (Alt-Tab); ein ausgeblendetes Element gäbe ein *leeres* Bild, kein stehendes (`_overlay_feed`). Das Log dieser Tage war überschrieben – Ursache nicht belegt |
| W2 | „Aufnahme ab Matchbeginn“ (`rec_early`) greift praktisch nie: Ende des Ladebildschirms nach bestätigter Lobby nur 4 von 547 Malen | `rounds.jsonl` `load` 4×, `wait` 547× |
| W3 | Bitrate zu niedrig: sichtbares Schmieren bei Bewegung; die Score-Ecke musste deshalb mit Mehrheit über Blicke gelesen werden | 0,022 Bit/Pixel; Kompressionsartefakte in den Score-Ausschnitten |

### Nicht zuverlässig erkennbar (aus diesen Aufnahmen)

- Lobby- und Ladebildschirm-Abläufe (nicht aufgenommen) – W2 lässt sich daher nicht an Bildern nachstellen.
- Positionen/Bewegung auf der Karte: kein Minimap-Element in DBD; aus dem Spielbild nicht robust ableitbar.
- Gegner-Aktionen ausserhalb des eigenen Bilds.

## 3 Abgleich mit Fog Scout (Phase 2)

| Befund | Bestand vorher | Lücke |
|---|---|---|
| S1 Score Events | nur Debug-Bilder (1.57.52) | Lesen, Kategorie, Zählen, Anzeige fehlten |
| S2 schwarze Aufnahmen | `check_file` (leer/zu klein/kein Video) | Bildinhalt nie geprüft |
| S3 Löschen exFAT | `fsops.delete_inside` nur NTFS-tauglich | Rückfall und Meldung fehlten |
| S4 Warte-Karte | Platz im Balken wie die Karte | volle Breite von DBD nicht berücksichtigt |
| S5 Rolle | Statistik übernimmt offizielle Rolle | nur Dateinamen/Index bleiben falsch (geringer Nutzen) |
| S6 stehendes Overlay | Lag-Liste in der Diagnose, Log bei jedem Start überschrieben | Ursache nach Neustart nicht mehr nachvollziehbar |
| S8 HUD-Werte | – | DBD zeigt sie selbst; ein Overlay würde nur doppeln |
| S9 Ergebnisbildschirm | Rolle wird dort gelesen (`result_role`) | Punkte je Kategorie dort nicht gelesen; offizielle Daten liefern sie, wenn exportiert |

## 4 Priorisierung (Phase 3)

| Idee | Nutzen | Zuverlässigkeit | Aufwand/Risiko | Last | Urteil |
|---|---|---|---|---|---|
| Löschen auf exFAT reparieren + Fehlschläge melden | hoch (200 GB, Platzmachen) | sicher (Testdatei) | klein | keine | **P1 – umgesetzt (1.57.58)** |
| Schwarz-/Standbild-Wächter nach jeder Runde | hoch (17 Runden in Folge verloren) | 31/31 schwarz, 0 Fehlalarme auf den 30 dunkelsten | klein | ~0,6 s je Runde im Rekorder-Thread | **P1 – umgesetzt (1.57.59)** |
| Log der letzten Sitzungen + Warnungen der vorigen Sitzung in der Diagnose | mittel (S6/W1/W2 überhaupt erst belegbar) | sicher | klein | keine | **P1 – umgesetzt (1.57.60)** |
| Score Events lesen, Kategorie, zählen, Ring, live + Zeile in Infos | hoch (Fortschritt je Kategorie im Spiel) | 2,4 % neben offiziellen Punkten (13 Runden) | mittel | ~29 ms je Blick mit Events, 4 Blicke/s nur auf die Ecke | **P1 – umgesetzt (1.57.53–1.57.57)** |
| Warte-Karte bei voller DBD-Breite nicht über die UI legen | mittel | volle Breite messbar (`detector.fills_bars`) | mittel (Platzierung aller Layouts) | gering | **P1 – umgesetzt (1.57.61, #503; Nutzer: „Ausblenden“)** |
| Ursache des stehenden Overlays (W1) beheben | mittel | Ursache unbelegt | unklar | – | **P2 – erst mit dem neuen Log belegen** |
| Punkte je Kategorie vom Ergebnisbildschirm lesen | mittel (Abgleich ohne Export) | wahrscheinlich gut (grosse Ziffern) | mittel | gering | **P2** |
| Automatische Marken aus Score Events (Hook, Escape, Chase gewonnen) für Highlights | mittel–hoch (Clips ohne F8) | Score-Tracker liefert Zeiten | mittel (Marken schützen heute vor dem Farming-Aufräumen – eigenes Feld nötig) | keine | **P2** |
| Matchbeginn-Erkennung verbessern (W2) | mittel | ohne Ladebildschirm-Bilder nicht testbar | – | – | **P3 – erst Debug-Bilder des Ladebildschirms sammeln** |
| Generator-Timeline / Survivor-Status aus dem HUD | gering im Spiel (DBD zeigt es) | Symbol-OCR fragil | hoch | spürbar | **Verwerfen** |
| Endgame-Collapse-/Hook-Timer als Overlay | gering (Balken im Spiel sichtbar) | – | – | – | **Verwerfen** |
| Rolle in Dateinamen nachträglich korrigieren | gering (Statistik stimmt bereits) | sicher | Dateien umbenennen = Eingriff in Nutzerdaten | – | **Verwerfen** |
| Aufnahmequalität automatisch hochsetzen | hoch für Clips | – | ändert das OBS-Profil; Fog Scout hat dafür bereits „In OBS einstellen“ (Rückfrage) | – | **Verwerfen** (Nutzeraktion, Hinweis im Bericht) |

## 5 Umgesetzt (Phase 4)

Alle auf eigenen Zweigen, je ein PR, gemergt nach grünen Prüfungen (Linux, Windows, .exe, CodeQL):

| Version | PR | Inhalt | Wichtigste Dateien |
|---|---|---|---|
| 1.57.53 | #494 | Score Events lesen (Zeilen, Name, Punkte mit Viterbi für „+“) | `fogscout/scoreevents.py`, `tools/score_read.py`, `tests/data/score/` |
| 1.57.54 | #495 | Kategorie aus dem Symbol (Vorlagen aus eigenen Aufnahmen) | `scoreevents.py`, `fogscout/score_icons.png`, `tools/score_icons.py`, `installer/fogscout.spec`, `selftest.py` |
| 1.57.55 | #496 | Zählen über mehrere Blicke + Ring-Füllstand mit Plausibilitätsprüfung | `fogscout/scorecount.py`, `tools/score_round.py` |
| 1.57.56 | #497 | Live im Match (Ecke alle 0,25 s zwischen den Takten), Punkte je Kategorie an der Runde, Diagnose, Einstellung | `worker.py`, `app.py`, `app_stats.py`, `history.py`, `diagnose.py`, `config.py`, i18n |
| 1.57.57 | #498 | Zeile „Punkte“ im Element Infos (klassisch, glass, chips, Vorschau) | `overlay_render.py`, `overlay_win32.py`, `skin.py`, `preview.py`, `app_overlay.py` |
| 1.57.58 | #499 | Löschen auf exFAT, Fehlschläge im Log | `fsops.py`, `recindex.py`, `obsrec.py` |
| 1.57.59 | #500 | Schwarz-/Standbild-Wächter | `obsrec.py` (`picture_check`), i18n |
| 1.57.60 | #501 | Log der letzten 3 Sitzungen, Warnungen der vorigen Sitzung in „Diagnose kopieren“ | `__main__.py`, `diagnose.py`, `.gitignore` |
| 1.57.61 | #503 | Warte-Karte weg, solange DBD die ganze Breite nutzt; `fills_bars` lässt alle eigenen Fenster aus (sonst galt die Lobby mit den rechten Karten nicht als volle Breite – geprüft an Debug-Bildern: Lobby 3/3, Match 26/26) | `worker.py`, `detector.py`, `app_place.py` |

Nebenbei behoben: Zeitstempel der Debug-Bilder aus zwei Uhr-Abfragen (Sekundenwechsel → falsche Reihenfolge, CI rot).

## 6 Tests (Phase 5) – tatsächlich ausgeführt

- **Lokal (Windows, Python 3.14):** je PR die betroffenen Testdateien, u. a. `test_scoreevents.py`, `test_scorecount.py`,
  `test_fsops.py`, `test_recindex.py`, `test_obsrec.py`, `test_crashlog.py`, `test_diagnose_privacy.py`, `test_lobby.py`,
  `test_matchend.py`, `test_loadouts.py`, `test_qt.py`/`test_uimodel.py`/`test_preview.py` (offscreen), Overlay-Render-Tests,
  `test_i18n.py`, `test_repo_hygiene.py`, History-Tests – grün. `pyflakes` auf den geänderten Dateien sauber.
- **Lokal nicht grün, ohne Bezug zu den Änderungen:** Symlink-/Junction-Tests (Windows-Recht fehlt: WinError 1314).
- **Lokal bewusst nicht ausgeführt:** `tests/test_windows.py` und die volle Suite (öffnen echte Fenster auf dem
  Nutzer-PC) – laufen in GitHub Actions.
- **CI:** alle PRs #494–#501 mit grünem pytest (Linux 3.12–3.14), Windows (3.12, 3.14), .exe-Bau, CodeQL. Zwei
  CodeQL-Läufe scheiterten an einem GitHub-Serverfehler beim Hochladen und wurden neu angestossen.
- **Messungen auf echten Aufnahmen:** Score-Punkte 51/57 richtig, 1 falsch (Handlabel); Kategorie 98,2 % (99,8 % der
  sicheren) auf fremden Runden; Summen mit Ring 2,4 % neben offiziellen Punkten (13 Runden); Schwarz-Wächter
  31/31 schwarz erkannt, 0 der 30 dunkelsten echten Runden falsch, 1 Launcher-Runde als „eingefroren“ (angesehen).
- **Nicht geprüft:** Live-Betrieb in DBD (Score-Tracker, Punkte-Zeile, Wächter) – die Diagnose zeigt die Werte.

## 7 Einschränkungen, offene Fragen, nächste Schritte

1. **Warte-Karte (S4):** umgesetzt als „ausblenden“ (1.57.61) – live in Lobby/Ergebnisbildschirm noch zu bestätigen.
2. **Stehendes Overlay (S6/W1):** nach der nächsten betroffenen Runde „Diagnose kopieren“ – Lag-Liste und vorige Sitzung zeigen dann die Ursache.
3. **Release:** Releases entstehen nur per Handstart von *Build* (seit 1.50.7). Der Handstart am 25.11. 15:46 scheiterte an GitHub (HTTP 502) und hinterliess einen Entwurf 1.57.57.
4. **Nach dem Update:** das Farming-Aufräumen löscht die abgelaufenen Farming-Aufnahmen (~530, F8-markierte bleiben).
5. **Aufnahmequalität:** Seite Aufnahmen → „In OBS einstellen“ bzw. Encoder auf konstante Qualität (NVENC CQ) – ca. 3–4× grössere Dateien.
6. **P2 als nächstes:** automatische Marken aus Score Events; Punkte vom Ergebnisbildschirm.
