# Code-Review 1.57.68

Auftrag (Saru, 25.11.2026): „Mache einen tiefen Code Review.“ Umfang: der in den letzten Tagen entstandene Code –
Score-Tracker (`scoreevents`, `scorecount`, `scoreview`, `scoreicons`, `tools/score_*`), seine Anbindung an Worker,
App und Overlay, die Start-Härtung (`launch.restrict_dll_search`, Selbsttest) – und, ausgehend vom ersten Befund,
alle automatischen Schreiber in den Datenordner. Nicht geprüft: der übrige Bestand (Editor, OBS, Statistik, Qt-Seiten);
dieser Bericht behauptet nichts über ihn.

## Befunde

### CR-1 – MEDIUM – Icon-Cache schrieb durch einen verlinkten Ordner (behoben)

- **Ort:** `scoreicons.save` / `load` (neu in 1.57.67).
- **Beleg:** `os.makedirs` + `fsops.write_atomic` ohne `fsops.linked_root`; Test
  `test_a_cache_folder_swapped_for_a_link_is_neither_written_nor_read` (lokal übersprungen: kein Symlink-Recht, läuft
  in CI).
- **Ursache/Auswirkung:** Fog Scout läuft als Administrator, der Datenordner gehört dem Nutzer. Ersetzt ein Programm
  des Nutzers `cache/score_icons` (oder `cache`) durch eine Junction, landet die PNG dort, wohin sie zeigt.
- **Fix:** `scoreicons.folder` über `fsops.plain_dir`; `save` gibt dann `None` zurück (kein „score_icon“-Ereignis),
  `load` liest nicht durch einen verlinkten Ordner.

### CR-4 – MEDIUM – dieselbe Lücke in sechs älteren Cache-Schreibern (behoben)

- **Ort:** `thumbs.thumbnail` (cache/thumbs, shots, clipthumbs), `mapstyle.styled_path` (cache/maps_dark),
  `obsoverlay.Writer._write` (cache/obs-overlay.png), `corpus.save` (corpus/), `clipedit._analysis_write`
  (cache/analysis), `filehash.Cache._save_cache`.
- **Beleg:** Durchsicht aller `os.makedirs` in `fogscout/` auf eine Link-Prüfung in der Nähe; frühere Audits (RS-002,
  CR-001, CR-007) hatten in diesen Ordnern nur das **Löschen** abgesichert (`linked_root` vor `prune`), das Schreiben
  nicht. Test `test_a_cache_folder_behind_a_link_is_never_written_by_any_cache` (CI).
- **Auswirkung:** wie CR-1; die Dateinamen sind vorgegeben (Hash-Namen, `obs-overlay.png` + `.tmp`), der Inhalt ist
  ein Bild/JSON – also Dateien an fremdem Ort anlegen bzw. mit Bilddaten überschreiben, kein direkter Code. Nicht
  als Angriff nachgestellt.
- **Fix:** neue gemeinsame Prüfung `fsops.plain_dir(folder, levels)` (anlegen + vor und nach dem Anlegen
  `linked_root`); jeder Schreiber lässt bei einem verlinkten Ordner das Speichern aus (Kachel wird trotzdem
  gezeichnet, Kartenstil = Originalbild, Overlay-Bild = Fehlerzustand des Schreibers).
- **Restrisiko:** zwischen Prüfung und Schreiben bleibt ein kurzes Fenster (wie bei `_debug_dir`); ganz schliessen
  würde es nur Schreiben über ein Verzeichnis-Handle.

### CR-2 – LOW – Score-Ereignisse ohne Generationsprüfung, Generation mal Paar, mal Zahl (behoben)

- **Ort:** `worker._score_post`, `App._event`.
- **Beleg:** Blicke posteten `gen=(Nummer, Quelle)`, das Schlussereignis `gen=Nummer`; die App filterte nur
  `menu`/`match_end` nach Generation (Regel in CLAUDE.md: veraltete Ereignisse einer alten Map werden ignoriert).
- **Auswirkung:** ein spätes Score-Ereignis einer nicht mehr gezeigten Map konnte den Punktestand der neuen setzen
  (kein Fall beobachtet).
- **Fix:** immer die Nummer; `score` in der Generationsprüfung. Test
  `test_score_events_carry_the_maps_generation_as_a_number_and_stale_ones_are_dropped`.

### CR-3 – LOW – gelöschter Icon-Cache wurde erst nach Neustart neu gelernt (behoben)

- **Ort:** `worker._learn_icons` (Sammler lebte für die ganze Sitzung, Doku sagte „Ordner löschen = neu lernen“).
- **Fix:** jede neue Runde fragt den Cache neu ab (`_score_round` setzt den Sammler zurück). Test
  `test_the_worker_tells_nothing_when_the_icon_could_not_be_saved_and_looks_again_each_round`.

## Geprüft, kein Befund

| Bereich | Ergebnis |
|---|---|
| Warte-Schleife des Workers mit Score-Blicken | Befehle werden zurück in die Warteschlange gelegt (Reihenfolge kann sich drehen) – unkritisch: nur `stop`/`scan`/`catalog`, alle werden am Schleifenanfang abgearbeitet. |
| `scorecount.totals` (Ring-Regeln) | Sprung-/Abfall-Regeln konsistent; Nachmessung 6 Runden: Ø 46 Punkte je Kategorie neben den offiziellen Werten. |
| „+4“, „+0“, „+25“ bei CHASED/BOLD/PROTECTION | keine Fehllesung: wachsende Zähler, die klein enden. |
| `scoreview` (Caches, gelernte Icons) | Revision im Overlay-Wert → jeder Bild-Cache bekommt einen neuen Schlüssel; Zeichnen nur im GUI-Thread. |
| `launch.restrict_dll_search`, Selbsttest `DLL-Suche` | läuft vor allen Importen; der Selbsttest der gebauten und installierten .exe prüft es in CI. |
| `tools/score_*` | Zuschnitt nach `format=bgr24` (1.57.65), Regressionstest vorhanden. |

## Hinweise ohne Änderung

- `ScoreCounter.role()` wählt bei Gleichstand „killer“: ein einzelnes falsch erkanntes Icon ganz am Anfang kann
  kurz die Ringe der falschen Rolle zeigen, bis weitere Events kommen. Selten; die App kennt die Rolle aus der Lobby
  und könnte sie vorgeben.
- `scoreview.of` wird nur von Tests benutzt.

## Ausgeführt

- `pyflakes fogscout tests` – 0 Meldungen.
- `pytest` lokal: `test_scoreicons`, `test_scorecount`, `test_scoreevents`, `test_scoreview`, `test_fsops`,
  `test_thumbs`, `test_mapstyle`, `test_obsoverlay`, `test_corpus`, `test_filehash`, `test_clipedit` (Analyse) – grün
  bis auf `test_the_corpus_export_never_reads_through_a_linked_folder` (WinError 1314, kein Symlink-Recht auf diesem
  PC, auch ohne diese Änderung); die neuen Symlink-Tests werden lokal übersprungen und laufen in CI (Linux).
- Volle Suite und `test_windows.py`: nur CI.
