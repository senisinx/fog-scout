# Fog Scout – Deep Code Review, Red Team & Performance Audit

Stand: 26.11.2026 · geprüft: Commit `ae858f6` (**1.57.67**) · `main` steht inzwischen auf 1.57.68 (PR #510) – der
Unterschied (17 Dateien, Caches/Score) berührt keinen der Befunde unten; die betroffenen Dateien sind dort unverändert.

Dieser Bericht ist reine Analyse. **Am Repository wurde nichts geändert, nichts committet, nichts gepusht.**

---

## 1. Executive Summary

Fog Scout ist für ein Ein-Personen-Projekt ungewöhnlich gut abgesichert: feste Paketversionen mit Hashes, eine
durchdachte Update-Kette, zentrale Datei-Primitive, rund 2 300 Tests, eigene Wächtertests für die harten Regeln.
Die offensichtlichen Lücken sind zu. Was übrig bleibt, sind drei Muster:

1. **Der Admin-Prozess fasst an einzelnen Stellen Dateien in nutzerbeschreibbaren Ordnern ohne die eigenen
   Schutz-Primitive an** (`fsops`): Löschen im Download-Ordner, Schreiben im Aufnahmeordner, Öffnen des Logs.
   Jede dieser Stellen ist ein Baustein für eine Rechteausweitung.
2. **Eingaben werden auf Form geprüft, nicht auf Typ und Wertebereich.** Eine lesbare, aber falsche
   `settings.json` verhindert jeden Start; eine Projektdatei mit `NaN` lässt den Editor stumm nicht mehr speichern;
   eine Zahl mit 400 Stellen in einer Sicherung bricht die Statistik dauerhaft.
3. **Die Wächter prüfen Schreibweisen, nicht Verhalten.** Die Tests für die harten Regeln lassen sich mit einem
   Alias-Import umgehen; `OpenProcess` steht auf keiner Verbotsliste.

Kein Befund ist „Critical“. Es gibt keine aus dem Netz ausnutzbare Lücke; alle Sicherheitsbefunde setzen ein
Programm voraus, das bereits im Benutzerkonto läuft. Performance ist im Leerlauf unauffällig (≈ 1 % eines Kerns);
der eine echte Engpass ist der Score-Blick während sichtbarer Score-Events.

| Schweregrad | Anzahl | Befunde |
|---|---|---|
| Critical | 0 | – |
| High | 3 | SEC-01, SEC-02, STAB-01 |
| Medium | 13 | SEC-03, SEC-04, STAB-02 … STAB-07, DATA-01, DATA-02, TEST-01, TEST-02, TEST-03 |
| Low / Info | ~25 | siehe Abschnitte 5–12 |

**Grenzen dieser Prüfung** (wichtig für die Einordnung):

- Ausgeführt in einem **Linux-Container**, nicht auf dem Windows-PC. Alles, was nur unter Windows läuft
  (natives Overlay, Aufgabenplanung, DPAPI, Junctions, Zertifikatsspeicher, Installer, hosts-Helfer, Hotkeys),
  ist **nur am Code geprüft** und so gekennzeichnet.
- Die Arbeit lief über acht parallele Prüfer je Bereich; die wichtigsten Befunde habe ich selbst erneut
  ausgeführt (in den Befunden als „selbst nachgestellt“ markiert). Der Rest stützt sich auf die Proben der Prüfer.
- Sechs Prüfer wurden durch ein Nutzungslimit unterbrochen und danach mit knappem Budget fortgesetzt. Mehrere
  geplante Prüfungen sind deshalb **nicht gelaufen** – Liste in Abschnitt 16.
- **Regelabweichung:** Ein Proxy-Test hat einmal real `api.github.com/repos/senisinx/fog-scout/releases/latest`
  abgefragt (lesend, ohne Anmeldung), weil die Proxy-Variable des Containers Vorrang hatte. Sonst gingen keine
  Anfragen an fremde Systeme.

---

## 2. Gesamtbewertung

| Bereich | Urteil | Begründung |
|---|---|---|
| Sicherheit | gut, mit Lücken | Update-Kette, Helfer, Parser solide; drei Dateioperationen und das TLS-Vertrauen offen |
| Stabilität | mittel | Erkennung robust; Start und Editor fallen bei falschen Werten ohne Rettungsweg um |
| Datenintegrität | gut | atomare Schreiber, Sperren, Sicherungen; Wiederherstellung hat zwei stille Verlustpfade |
| Performance | gut | Leerlauf ~1 %; ein Engpass (Score-Blick), ein Ausreißer (OCR-Breite) |
| Architektur | mittel | funktioniert, aber `App` ist eine Gott-Klasse aus 19 Mixins mit 736 Attributen |
| Tests | gut, aber überschätzt | viele und ernsthafte Tests; Wächter umgehbar, 15 von 56 Mutanten überleben |
| UX | mittel | funktional vollständig, aber dicht; Fehler landen nur im Log |
| Doku | mittel | CLAUDE.md präzise, aber an einigen Stellen veraltet; PRIVACY.md unvollständig; README als Handbuch unbrauchbar |

---

## 3. Architekturübersicht

- **Umfang:** 163 Module, 115 300 Zeilen in `fogscout/` (davon ~35 500 Übersetzungstabellen), 131 Testdateien
  mit 48 473 Zeilen, 4 856 Funktionen (25,5 % vollständig typisiert).
- **Schichten:** Erkennung (Worker-Thread: Aufnahme → OCR → Zustandsautomaten) → Ereigniswarteschlange →
  Controller `App` (GUI-Thread, `_poll` 50 ms, `_tick_overlay` 250 ms) → Overlay-Fenster und Steuerfenster.
  Daneben eigene Threads für OBS, Musik, Spotify, YouTube, Discord, Hashing.
- **Datenfluss:** Bildschirm → Worker → `events` → `_dispatch`/`_event` → Rundenverlauf (`rounds.jsonl`),
  Overlay, OBS. Offizielle Match-Daten kommen als Datei aus dem Download-Ordner und werden mit den Runden verknüpft.
- **Vertrauensgrenze:** Der Prozess läuft erhöht. Datenordner, Aufnahmeordner, Download-Ordner, Benutzerumgebung
  und HKCU sind für jedes Programm des Nutzers beschreibbar – alles, was von dort gelesen wird, ist Angreifer-Eingabe.

**Riskante Stellen für künftige Änderungen:**

| Stelle | Zeilen / Komplexität | Warum riskant |
|---|---|---|
| `worker._run` | 669 Zeilen, zyklomatisch 343 | eine Funktion steuert alle Erkennungszustände |
| `App` + 19 Mixins | 782 Methoden, 736 Attribute | 154 Attribute werden in mehreren Dateien benutzt, 213 `getattr(self, …, default)` verbergen die Reihenfolge |
| `clipedit.edit_graph` | 204 / 106 | baut den ffmpeg-Graphen für alle Modi |
| `preview.layers` | 232 / 101 | muss `_place_overlay` exakt spiegeln |
| `_qt_event`, `_place_overlay_map` | 170 / 87, 168 / 83 | lange Verzweigungsketten |

Keine Import-Zyklen auf Modulebene. Fünf Zyklen bestehen nur über Importe in Funktionen.

---

## 4. Red-Team-Ergebnisse (Überblick)

| Angriffsfläche | Ergebnis |
|---|---|
| Pfad-Traversal, ZIP-Slip, Windows-Sondernamen beim Wiederherstellen | **hält** (18 feindliche Namen, nichts landet außerhalb) |
| Manipulierter Aufnahme-Index (`..`, absolut, Links, NUL) | **hält** – nichts außerhalb des Ordners gelöscht |
| Links/Junctions in nutzerbeschreibbaren Ordnern | **drei Lücken:** SEC-02, SEC-03, SEC-04 |
| ffmpeg-Argumente und Filtergraph aus Projektdateien, Dateinamen, Texten | **hält** – Texte werden per Pillow gezeichnet, der Graph enthält nur Zahlen |
| Als `.mp4` getarnte HLS-/concat-/SDP-Dateien | **hält** (Linux-Build; Windows-Build nicht geprüft) |
| Command Injection, `eval`/`exec`, unsichere Deserialisierung | **nichts gefunden** |
| Prompt Injection und Datenabfluss zu Claude | **hält** – nur feste Programmtexte gehen raus; eine Rechen-Lücke (PRIV-01) |
| Feindliche API-/Modellantworten | **hält** (30 000 Fuzz-Runden über 11 Parser) |
| OAuth-Rückruf auf 127.0.0.1 | **hält** (State geprüft, nichts gespiegelt) |
| Falscher lokaler „OBS“-Server | zwei kleine Lücken (SEC-07, SEC-08), keine Dateioperation außerhalb |
| Update-Kette | Hash-Kette und Rollback-Schutz halten; **TLS-Vertrauen offen** (SEC-01) |
| Feindliche `settings.json` | **Startblockade** (STAB-01) |
| Feindliche Projektdatei | **Einfrieren und stiller Arbeitsverlust** (STAB-05, STAB-06) |
| Bilder als Speicherbombe | 50 000 × 50 000 wird abgelehnt; **89–179 Megapixel nicht** (STAB-08) |
| GitHub Actions | `pull_request` ohne Geheimnisse, Release nur von Hand – **hält**; zwei Härtungspunkte (Abschnitt 12) |

---

## 5. Sicherheitsbefunde

### SEC-01 – Update-Prüfung vertraut Proxy und Stammzertifikaten des Benutzerkontos
- **Schweregrad:** High · **Status:** wahrscheinlich (Proxy-Hälfte belegt; Zertifikats-Hälfte unter Windows nicht ausgeführt)
- **Ort:** `fogscout/net.py:36-39`, `fogscout/launch.py:61-69`, `fogscout/relupdate.py:181-270`
- **Ursache:** `net.opener()` benutzt den Standard-TLS-Kontext und den System-Proxy. `harden_start_environment`
  entfernt `SSL_CERT_*`, lässt Proxys aber bewusst stehen („a proxy alone cannot break TLS“). Unter Windows lädt
  Python nach meiner Kenntnis auch den Zertifikatsspeicher des aktuellen Benutzers; der erhöhte Prozess teilt
  sich HKCU mit jedem Programm des Nutzers. `.sha256`-Datei, GitHub-Digest und Setup kommen über denselben Kanal.
- **Szenario:** Ein Programm ohne Adminrechte trägt ein Stammzertifikat in HKCU ein und setzt einen Proxy. Es
  beantwortet die Release-Abfrage mit einem „neueren“ Build samt passender Prüfsumme. Der Nutzer sieht das
  gewohnte „Update verfügbar“ und bestätigt; das fremde Setup läuft als Administrator.
- **Voraussetzungen:** Code läuft bereits im Benutzerkonto; der Nutzer klickt das Update an.
- **Reproduktion:** Mit gesetztem `HTTPS_PROXY` zeigt `net.opener()` einen `ProxyHandler`;
  `clean_elevated_environment` behält die Variable; ein lokaler Proxy sah `api.github.com:443`.
- **Auswirkung:** Rechteausweitung auf Administrator; dieselbe Position sieht API-Schlüssel und Tokens im Transit.
- **Wahrscheinlichkeit:** gering (gezielter lokaler Angriff), Schaden hoch.
- **Lösung:** Das Setup gegen einen im Programm eingebauten öffentlichen Schlüssel prüfen (Signatur im
  `release`-Job). Kleiner: für `relupdate` einen TLS-Kontext nur aus einer mitgelieferten CA-Datei bauen und
  erhöht `ProxyHandler({})` verwenden.
- **Aufwand:** M · **Test:** `relupdate` hat erhöht keinen Umgebungs-Proxy und einen expliziten Kontext; ein
  Download mit falscher Signatur wird abgelehnt.
- **Offen:** der stille Registry-Eintrag und die ganze Kette auf einem echten Windows.

### SEC-02 – `official.take_downloads` löscht nach dem Lesen per Pfad
- **Schweregrad:** High · **Status:** unter Linux belegt, unter Windows wahrscheinlich
- **Ort:** `fogscout/official.py:419-456` (`os.remove(path)`), aufgerufen alle 20 s
- **Ursache:** Die Datei wird geöffnet, gelesen, zusammengeführt (dabei wird `official.jsonl` mit `fsync`
  geschrieben) und erst danach per Name gelöscht. Nichts bindet das Löschen an die gelesene Datei. Der Ordner
  kommt aus `official_dir` bzw. dem Download-Ordner.
- **Szenario:** Ein Programm legt eine gültige `fogscout-matches.json` ab und tauscht den Ordner während des
  Zusammenführens gegen eine Junction. Der Admin-Prozess löscht eine fremde Datei. Beliebiges Löschen als
  Administrator ist ein Standard-Baustein für Rechteausweitung.
- **Reproduktion:** Probe mit Ordner-Symlink: `victim still exists: False`, `attacker's file still exists: True`.
- **Lösung:** Datei mit `FILE_FLAG_OPEN_REPARSE_POINT` öffnen, aus diesem Handle lesen und über dasselbe Handle
  löschen – so wie `fsops.delete_inside` es schon tut. Verlinkte Ordner ablehnen.
- **Aufwand:** S · **Test:** Ordner in einem gepatchten `merge` tauschen; die fremde Datei muss überleben.

### SEC-03 – `obsrec.merge_files` schreibt und löscht unter vorhersagbarem Namen im Aufnahmeordner
- **Schweregrad:** Medium · **Status:** unter Linux belegt (zwei Prüfer unabhängig), unter Windows wahrscheinlich
- **Ort:** `fogscout/obsrec.py:751-777` – `open(out + ".txt", "w")`, `ffmpeg -y out`, `os.remove`
- **Ursache:** Der Name `<Runde> (zusammen).<ext>.txt` ist bekannt, sobald die Rundendatei im Ordner liegt.
  Das Öffnen folgt Links; `tests/test_fsops.py:237-238` führt die Stelle als „eigene Datei“.
- **Szenario:** Vorab gelegter Link (oder Unterordner `Farming` als Junction) → der Admin-Prozess überschreibt
  das Ziel mit zwei Textzeilen und löscht es. Braucht Aufnahme mit Vorlauf und Zusammenfügen.
- **Reproduktion:** Zieldatei enthielt danach `file '/…/… (Vorlauf).mkv'`.
- **Einschränkung:** Datei-Symlinks brauchen unter Windows den Entwicklermodus; die Junction-Variante nicht.
- **Lösung:** Liste mit `fsops.write_tmp` (Zufallsname, exklusiv) anlegen, ffmpeg mit `-n` und Zufallsnamen
  starten, über `fsops.delete_inside` löschen. · **Aufwand:** S

### SEC-04 – `fogscout.log` wird bei jedem Start durch einen Link hindurch geöffnet
- **Schweregrad:** Medium · **Status:** unter Linux belegt, Code selbst nachgelesen
- **Ort:** `fogscout/__main__.py:72-98`
- **Ursache:** `_keep_old_logs` kehrt bei einem Link nur zurück; `logging.basicConfig(filename=…, filemode="w")`
  öffnet danach denselben Pfad trotzdem.
- **Reproduktion:** `data/fogscout.log -> victim` angelegt, `_setup_logging(data)` aufgerufen: der Inhalt des
  Ziels war durch eine Logzeile ersetzt.
- **Auswirkung:** Abschneiden und Überschreiben einer Datei bei jeder Anmeldung. Der frühere Bericht (RS-006)
  stufte das als Low ein („feste Namen“); über eine Junction des Datenordners wäre der Zielname frei (theoretisch).
- **Gleiche Klasse:** `takeover.record`/`finish` mit einfachem `open(…, "w")`; `config.py:460` (`shutil.copy2`
  nach `settings.json.broken`).
- **Lösung:** Log über `fsops.open_plain_for_write` öffnen und dem Logging einen `StreamHandler` geben. · **Aufwand:** S

### SEC-05 – Admin-Helfer überschreibt jeden Pfad, den der Aufrufer nennt
- **Schweregrad:** Low · **Status:** wahrscheinlich (nur Windows)
- **Ort:** `fogscout/__main__.py:273`, `hostsedit.py:289`, `netwatch.py:199` (`_open_result`)
- `_open_result` prüft „einfache Datei, ein Link“, aber nicht, wo sie liegt. Nach einer UAC-Bestätigung wird
  eine vorhandene Datei zu einer Zeile JSON.
- **Lösung:** Nur Namen nach dem Muster `fogscout-(result|netres)-*.json` annehmen. · **Aufwand:** S

### SEC-06 – Pfadschutz `fsops.local_media_path` umgehbar
- **Schweregrad:** Low · **Status:** Prüfergebnis belegt, Windows-Folge nicht ausgeführt
- **Ort:** `fogscout/fsops.py:46-59`
- Als „lokal“ gelten u. a. `\??\UNC\srv\share\x.mp4`, `\Device\x.mp4`, `subfile,,start,0,end,100,,:/etc/passwd.mp4`,
  `C:\x.mp4:stream.mp4`, `CON.mp4`. Unter Windows würde die erste Form beim bloßen Öffnen einer Montage eine
  SMB-Anmeldung auslösen – genau das, was der Schutz verhindern sollte.
- **Lösung:** Laufwerksbuchstabe plus absoluten Pfad verlangen, `:` nur an Position 1. · **Aufwand:** S

### SEC-07 – Text eines falschen lokalen „OBS“ landet ungekürzt in Status und Log
- **Schweregrad:** Low · **Status:** belegt
- **Ort:** `fogscout/obsrec.py:1817-1820`, `:1877`
- Eine `StopRecord`-Antwort erzeugte 3 MB Statustext und Log, mit gefälschter Logzeile. Widerspricht der Angabe
  aus 1.38.57, fremde Texte würden gekürzt. · **Lösung:** jeden OBS-Text durch `ObsClient.clean`. · **Aufwand:** S

### SEC-08 – Tröpfelnde Gegenstelle hält den Recorder-Thread über seine Grenze hinaus fest
- **Schweregrad:** Low · **Status:** belegt
- **Ort:** `fogscout/obsrec.py:331-338` (`_recv_exact` ohne Frist); gleiche Form in `discordrpc.Ipc._read`
- Blockiert 15 s statt der dokumentierten 0,9 s. Eine laufende Aufnahme wird nicht beendet. · **Aufwand:** S

### SEC-09 – `update._git` härtet nur teilweise
- **Schweregrad:** Low · **Status:** unter Linux belegt (git 2.43)
- **Ort:** `fogscout/update.py:166-186`
- Filter-Treiber aus `.git/config`, `core.sshCommand` und `url.<x>.insteadOf` wirken weiterhin; der Ursprung
  wird nie mit `REPO_URL` verglichen. Hooks und `fsmonitor` sind blockiert.
- **Einordnung:** Betrifft nur die start.bat-Installation, deren Ordner ohnehin nutzerbeschreibbar ist
  (bekannte, akzeptierte Rechteausweitung; die installierte .exe schließt sie).
- **Lösung:** `REPO_URL` ausdrücklich abrufen statt `origin`. · **Aufwand:** S

### Weitere Punkte (je eine Zeile)
- **Mutex besetzbar (Info):** Ein Programm, das `Local\FogScout.SingleInstance` hält, verhindert jeden Start.
- **`DBDMS_UPDATED=1`** in der Benutzerumgebung schaltet Updates in `start.bat` still ab (`start.bat:34`).
- **Export-Temp-Ordner in `%TEMP%`** mit `-safe 0`-Liste (`clipedit.py:1683`) – theoretisch tauschbar.
- **`clipedit.cut(path, out=path)`** zerstört die Aufnahme; kein Aufrufer gefunden, der das tut. Ein
  `samefile`-Abbruch würde „nie eine Aufnahme anfassen“ konstruktiv absichern.
- **Qt-Labels:** CLAUDE.md sagt „nur `Qt.PlainText`“; es gibt 77 rohe `QLabel(`-Aufrufe in 13 Dateien, u. a.
  mit Dateinamen aus Projektdateien (`qt_clip.py:1129`, `editormusic.py:100,215`). Auswirkung klein, kein Wächter.

---

## 6. Stabilitätsprobleme

### STAB-01 – Lesbare, aber falsche `settings.json` verhindert jeden Start, ohne Rettungsweg
- **Schweregrad:** High · **Status:** belegt, selbst nachgestellt
- **Ort:** `fogscout/config.py` (`_load`, `_version` Z. 298-306, Z. 399-400), Absturzstellen u. a. `app.py:365`,
  `app.py:513`, `qt_window.py:1448`, `app_settings.py:129`; `__main__.py:434-440` zeigt nur „Start fehlgeschlagen“
- **Ursache:** `_merge` nimmt je Schlüssel jeden JSON-Typ an; nur JSON- und Formfehler setzen `load_error` und
  legen `settings.json.broken` an. `App.__init__` ruft danach ungeschützt `float()`, `set()` usw. auf.
- **Reproduktion (selbst ausgeführt):**
  `{"ui_zoom": 1e9}` → `OverflowError`; `{"overlay": {"opacity": []}}`, `{"languages": 5}`,
  `{"log_categories": 1}`, `{"youtube_queue": 7}` → `TypeError`; jeweils `load_error=''`, keine `.broken`.
  `{"settings_version": 1e999}` lässt schon `Settings()` abbrechen.
- **Umfang:** 1 980 Fuzz-Fälle: 156 Fälle über 45 Schlüssel brechen den Start ab, 45 weitere brechen die Vorschau.
- **Szenario:** Handbearbeitung, Synchronisationskonflikt, importierte Sicherung oder ein fremdes Programm. Auch
  der Autostart endet dann jedes Mal in der Fehlermeldung; der Nutzer muss die Datei selbst finden und löschen.
- **Lösung:** In `_load` jeden Wert, dessen Typ nicht zum `DEFAULTS`-Eintrag passt, durch den Standard ersetzen
  (Zahlen begrenzen) und die Schlüssel loggen. Zusätzlich in `__main__`: scheitert `App()`, Datei nach `.broken`
  kopieren und einmal mit Standardwerten neu versuchen. `ArithmeticError` in die beiden Except-Listen.
- **Aufwand:** S–M · **Test:** `DEFAULTS` × feindliche Werte – `App()` muss entstehen und ein Takt fehlerfrei laufen.

### STAB-02 – Flacher Banner-Ausschnitt wird auf ~50 000 Pixel OCR-Breite gestreckt
- **Schweregrad:** Medium (High, falls ein reales Bild den Auslöser trifft) · **Status:** Aufblähen belegt und
  selbst gemessen; realer Auslöser nur synthetisch gezeigt
- **Ort:** `fogscout/ocr.py:154-163` (`_prepare`: `new_w = ceil(48·w/h)` ohne Obergrenze), gespeist von
  `fogscout/detector.py:349-356` und `:371-374` (Rückfall-Ausschnitte)
- **Messung (selbst, direkt an `Recognizer.probs`):**

  | Ausschnitt (H × B) | Netzbreite | Dauer | Arbeitsspeicher danach |
  |---|---|---|---|
  | 48 × 300 | 320 | 21 ms | 106 MB |
  | 4 × 1100 | 13 200 | 931 ms | 428 MB |
  | 2 × 1100 | 26 400 | 2 027 ms | 1 303 MB |
  | 1 × 1103 | 52 944 | 5 669 ms | 4 262 MB |

  Der Speicher bleibt nach einem normalen Ausschnitt bei 4 262 MB – er wird bis zum Neustart nicht freigegeben.
- **Auslöser (Prüfer, synthetisch):** eine dünne helle waagerechte Linie knapp unter der Oberkante des
  Banner-Bereichs (y ≈ 0,526–0,535 der Höhe) auf einem echten 3440 × 1440-Bild. Ein echter Screenshot, der das
  Band trifft, liegt nicht vor.
- **Auswirkung:** Der Worker steht sekundenlang (kein Rundenende-Blick), zwei Kerne laufen neben dem Spiel voll,
  bis zu 4 GB bleiben belegt. Keine falsche Map (leerer Text fällt an `MIN_NAME_CHARS`).
- **Lösung:** In `Recognizer.probs` für Ausschnitte unter ~6 px Höhe oder `new_w` über ~2 000 leer zurückgeben.
- **Aufwand:** S · **Test:** `_prepare` ausspähen – keine Inferenz breiter als die Grenze.

### STAB-03 – Unlesbares Kartenbild öffnet eine Runde, die nie endet
- **Schweregrad:** Medium · **Status:** belegt, selbst nachgestellt
- **Ort:** `fogscout/app.py:1256-1262` (`_event` „detected“) und `app.py:561-565` (`show_map`)
- **Ursache:** `_hist_open` (startet auch die OBS-Aufnahme) läuft vor `show_map`. Scheitert `load_frames`, kehrt
  `show_map` vor `_watch()` zurück – `worker.map_on_screen` bleibt `False`, die Rundenende-Erkennung wird nie scharf.
- **Reproduktion:** 0-Byte- oder Müll-Bild: `hist=… hidden=True worker.map_on_screen=False calls=['start_round']`.
- **Auswirkung:** Overlay bleibt aus, die Runde wird beim nächsten Banner als „verloren“ geschrieben, die
  Aufnahme läuft durch die Lobby weiter – und das bei jedem Match auf dieser Map.
- **Lösung:** Bei Dekodierfehler in den vorhandenen Zweig „Map ohne Bild“ fallen (`frames = None`). · **Aufwand:** S

### STAB-04 – Falsches Rundenende auf 16:9-Monitoren durch fremde Einblendungen
- **Schweregrad:** Medium (nicht auf dem Ultrawide-Setup des Nutzers) · **Status:** mit synthetischen Einblendungen
  auf echtem HUD-Bild belegt
- **Ort:** `fogscout/detector.py:1031-1039`, `:1129-1142`, `matchend.py:153`
- **Ursache:** Die Regel „Regionen nie in die schwarzen Balken“ schützt nur Ultrawide. Ohne Balken werden
  Währungsleiste und CONTINUE-Zone bei jedem Blick gelesen; keiner der Hinweise prüft etwas DBD-Eigenes.
- **Reproduktion:** weißer Text `142   6.9   1234` oben rechts → nach zwei Blicken `match_end`; ein einzelnes
  `Continue` unten rechts (wo Windows-Benachrichtigungen sitzen) → `match_end` beim **ersten** Blick.
- **Lösung:** „Lobby/Menü“ nur zählen, wenn mindestens eine Zahlengruppe ein Währungssymbol links hat
  (`bp_icon` existiert); CONTINUE ohne Balken immer zwei Blicke. · **Aufwand:** S–M

### STAB-05 – Eine Form in einer Projektdatei friert die ganze Oberfläche ein
- **Schweregrad:** Medium · **Status:** belegt
- **Ort:** `fogscout/annotate.py:265-292`, `project.py:22`, `qt_clip.py:689-692, 832-842`
- Eine Freihand-Form mit 2 000 Punkten und Strichstärke 0,5 (die Oberfläche bietet höchstens 0,016) wird im
  Fenster-Thread gezeichnet: 9,2 s bei 960 × 540, 91,9 s bei 3440 × 1440; im echten Editor-Fenster stand die
  Hauptschleife 11,7 s. Der Editor teilt sich die Schleife mit `_poll` und `_tick_overlay` – das Overlay steht mit.
- **Lösung:** Größe in `annotate.from_dict` auf das begrenzen, was die Oberfläche anbietet. · **Aufwand:** S

### STAB-06 – Eine falsche Zahl im Projekt: Editor bleibt bei „Projekt wird gesucht …“, speichert nichts, warnt nicht
- **Schweregrad:** Medium (stiller Arbeitsverlust) · **Status:** belegt, Parser-Abstürze selbst nachgestellt
- **Ort:** `inputtrack.py:54`, `musictrack.py:68,143`, `shorts.py:53`, `annotate.py:281/287`, `project.py:113`;
  ungefangen in `editorproject.py:292`; `editorproject.py:774` gibt das Schließen frei
- **Reproduktion (selbst):** `{"inputs":{"size":NaN}}`, `{"music":{"duck":[]}}`, 400-stellige Zahlen in
  `game_vol`, Untertiteln, Formgröße → `OverflowError`/`ValueError`/`TypeError`. Im echten Fenster (Prüfer):
  Zustand `loading`, weiter bearbeitbar, Platte hält den alten Stand, `close()` fragt nicht.
- **Lösung:** `OverflowError` in die Hilfsfunktionen (oder `project._finite` wiederverwenden); `_apply_data` in
  `try/except` mit dem vorhandenen Hinweis „Projektdatei ist unlesbar“. · **Aufwand:** S

### STAB-07 – Zustand „zwei Blicke in Folge“ überlebt beliebig lange Pausen
- **Schweregrad:** Low–Medium · **Status:** belegt (Zustandsautomat)
- **Ort:** `fogscout/matchend.py:146-157`
- Ein „Lobby/Menü“-Blick, zehn Minuten verdeckt, ein weiterer Blick → `match_end` mit der Zeit des ersten Blicks.
- **Lösung:** Kandidat nach ~3 s ohne Bestätigung verwerfen. · **Aufwand:** S

### STAB-08 – Ein 21 KB großes PNG kostet 1,5 GB RAM je Vorschaubild
- **Schweregrad:** Low · **Status:** belegt
- **Ort:** `fogscout/thumbs.py:102-106`, `qt_image.py:72`
- 13 300 × 13 300 (1 Bit) wird mit bloßer Warnung dekodiert: 2,4 s, 1 542 MB. Erst über 179 Megapixel lehnt
  Pillow ab. · **Lösung:** ab ~50 Megapixel vor dem Dekodieren ablehnen (wie `backups.py:240`). · **Aufwand:** S

### Kleinere Punkte
- **Export-Dialog gibt sein Fenster nicht frei** (`app_qt._dialog`): +6 Fenster, +617 Objekte, +5,5 MB je Öffnen.
  Geschlossen wurde von der Modellseite; der Weg über × / Esc ist nicht geprüft.
- **Log ohne Größengrenze in einer Sitzung:** Die Begrenzung `_report_once` (`app.py:1452-1479`) schlüsselt auf
  die letzte Traceback-Zeile; ein Fehler mit wechselndem Text schrieb 11,3 MB/h.
- **Worker-Uhr ist `time.time()`** (`worker.py:453`): ein Rücksprung der Systemuhr hält Fenster-, Lobby- und
  Rundenende-Blick an, bis die Uhr aufholt (gelesen, nicht ausgeführt).
- **DBD-Fenster ≤ 100 px:** der Desktop wird wie das Spiel gelesen (`worker.py:518-527`, gelesen).
- **`RecursionError`** entkommt mehreren Lesern (`jsonlcache.py:71`, `history.py:266`, `project.py:172/436`,
  `corpus.py:128`, `filehash.py:119`) – nur bei direkter Dateimanipulation.
- **`diagnose.py:220`** iteriert ein Wörterbuch, das der Worker erweitert.

---

## 7. Performance-Analyse

Alle Zahlen aus dem Linux-Container (4 Kerne, Python 3.13), teils unter Last anderer Prüfer – als
Größenordnung zu lesen, nicht als Windows-Werte.

**Leerlauf** (kein DBD-Fenster, 20–30 s):

| Fensterzustand | CPU (Anteil eines Kerns) | `_tick_overlay` je Aufruf |
|---|---|---|
| versteckt oder Übersicht | 1,07 % | 1,05 ms |
| Statistik | 1,22 % | 1,36 ms |
| Overlay-Seite | 1,95 % | 3,49 ms |

Etwa 25 Aufwachvorgänge je Sekunde, alle im Hauptthread; die Hintergrund-Threads brauchten 0,00 s.

**Start:** `import fogscout.app` 0,58 s; `App()` 0,20 s leer, 0,81 s mit vollen Daten. onnxruntime wird dabei
nicht geladen.

**Erkennung je Blick** (Median aus 20 Läufen, 3440 × 1440):

| Schritt | Wand | CPU |
|---|---|---|
| Banner-Blick ohne Banner | 3,3 ms | 9,4 ms |
| Banner-Blick mit Banner | 150,6 ms | 584 ms |
| Lobby-Ecke unverändert | 1,7 ms | 6,5 ms |
| Rundenende-Blick im Match | 4,3 ms | 10,9 ms |
| Score-Blick, nichts sichtbar | 1,3 ms | 1,4 ms |
| **Score-Blick, 3 Events** | **144,5 ms** | **219 ms** |
| Loadouts-Menü | 331 ms | 1 154 ms |

**Einordnung:**

| Kategorie | Punkt |
|---|---|
| **Echter Engpass** | Score-Blick alle 0,25 s: bei sichtbaren Events ≈ 580 ms Wand je Sekunde. 75 % davon sind sechs OCR-Läufe je Blick; die Ausschnitte (67–206 px) werden auf 320 px aufgefüllt. Der Code-Kommentar nennt 29 ms, gemessen wurden 145 ms. Ansatz: kein Auffüllen kleiner Ausschnitte, Namen bereits verfolgter Zeilen nicht neu lesen. Gewinn nicht gemessen. |
| **Echter Ausreißer** | STAB-02 (OCR-Breite ohne Grenze). |
| **Prüfenswert** | CPU ist bei OCR-Schritten ~4× Wandzeit: OpenCV läuft mit 4 Threads, nichts ruft `cv2.setNumThreads`. Nicht weiter profiliert. |
| **Prüfenswert** | Erstes `detected` nach dem Start 2,0 s, erstes `match_end` 1,1 s im GUI-Thread (kalt, unter Last – Obergrenze). `history.set_balance` schreibt die ganze Datei neu (61–447 ms je nach Last). |
| **Kaum messbarer Nutzen** | `_poll` ereignisgesteuert statt alle 50 ms (≈ 0,2 % eines Kerns). |
| **Nicht lohnend** | Schwärzen (0,05 ms), Bereichskopien, `is_dark`, Blick ohne Banner, `totals()`. |

**Skalierung** (5 000 Runden + 5 000 Matches + 2 000 Aufnahmen; die Dateien sind auf 5 000 Einträge begrenzt):
Statistikseite erster Aufbau 153 ms, langsamste Reiter 98 und 81 ms, Aufnahmen-Seite 68–86 ms, Maps-Seite 178 ms.
Kein Speicherleck über 2 000 gemischte Blicke (228 → 229 MB).

**Editor:** Zeitleiste mit 500 Abschnitten zeichnet in 43,5 ms – über dem Budget eines 60-Hz-Bildes, falls bei
jedem Wiedergabebild neu gezeichnet wird.

---

## 8. Datenintegrität und Datenschutz

### DATA-01 – Wiederhergestellte Sicherung mit einer „verlorenen Runde“ bricht jede Statistik-Verknüpfung
- **Schweregrad:** Medium · **Status:** belegt, selbst nachgestellt
- **Ort:** `fogscout/history.py:294-298` (`_num`), `:278-291` (`load_lost_rounds`), `backups.py:274-279`
- `_num` ruft `math.isfinite` auf einer Ganzzahl auf; `10**400` wirft `OverflowError`. Normale Zeilen fängt
  `LineCache._parse` ab, `load_lost_rounds` nicht; die Wiederherstellung prüft nur `t`.
- **Folge:** `_official_join` und die Diagnose brechen bei jedem Aufruf ab, bis die Datei von Hand repariert ist.
- **Nebenwirkung (selbst bestätigt):** In einer normalen Rundenzeile verschwindet die Runde still, und das
  nächste Umschreiben (`set_balance`) **löscht ihre Zeile endgültig** – `_rewrite` verwirft alles Unlesbare.
- **Lösung:** `_num` total machen; `_rewrite` unlesbare Zeilen nach `rounds.jsonl.rejected` verschieben statt
  verwerfen. · **Aufwand:** S

### DATA-02 – Sichern → Wiederherstellen verliert still Runden mit U+2028, U+2029 oder U+0085 im Text
- **Schweregrad:** Low–Medium · **Status:** belegt
- **Ort:** `fogscout/backups.py:251-254` (`str.splitlines()`)
- Die Live-Leser trennen nur an `\n`; `splitlines()` trennt auch an diesen Zeichen. Die Zeile zerfällt in zwei
  ungültige Stücke, die ohne Zählung übersprungen werden. Probe: 3 Runden gesichert, 1 wiederhergestellt.
- **Lösung:** `.split("\n")` und eine Anzeige „übersprungene Zeilen“. · **Aufwand:** S

### DATA-03 – „Alle Einstellungen zurücksetzen“ löscht Notizen und Zugangsdaten ohne Sicherung
- **Schweregrad:** Medium (UX/Datenverlust) · **Status:** belegt, Code selbst nachgelesen
- **Ort:** `fogscout/config.py:340-351`, Dialog `app_settings.py:685`
- Behalten werden nur fünf Schlüssel. Map- und Killer-Notizen, Vorlagen, Hotkeys, Layouts und alle gespeicherten
  Zugangsdaten gehen verloren; der Dialog nennt nur „Runden, Match-Daten und eigene Bilder bleiben“. Die tägliche
  Sicherung enthält keine Einstellungen. „Standard“ im Hotkeys-Reiter setzt 14 Hotkeys ohne Rückfrage zurück.
- **Lösung:** vorher `backup/settings-<Datum>.json` schreiben; Notizen behalten oder im Dialog nennen. · **Aufwand:** S

### PRIV-01 – `statsclaude` unterdrückt kleine Gruppen, aber keine Differenzen
- **Schweregrad:** Low · **Status:** belegt
- **Ort:** `fogscout/statsclaude.py:92-95, 108-150`
- Bei 3 Runden ergab „alle“ (n = 3) minus eine Gruppe (n = 2) exakt die Blutpunkte der einen ausgelassenen Runde.
  Die Regel sagt „nie eine einzelne Runde“. · **Lösung:** kleinste Gruppe mit auslassen, wenn der Rest unter
  `MIN_GROUP` fällt. · **Aufwand:** S–M

### PRIV-02 – PRIVACY.md ist unvollständig
- **Schweregrad:** Low · **Status:** belegt
- Debug-Bilder: `worker.py:1425-1465` schreibt auch `debug/loadouts/` (Pausenmenü in voller Größe – zeigt die
  **Namen aller Spieler**) und `debug/score/`; die Datenschutzerklärung nennt nur Banner-Ausschnitte und
  verkleinerte Bilder.
- Zeile 23 liest sich vollständig, nennt aber die Eingaben-Karte (`<Video>.inputs.json`), die Mediensitzung, die
  Steam-Screenshots samt Registry-Lesen und die gelernten Score-Icons nicht. Alles lokal, aber unerwähnt.

### Weitere Punkte
- **Exportierte Einstellungen** enthalten Client-IDs und YouTube-Playlist-IDs (verweisen auf den Kanal), Notizen
  und `farming_opponents` – keine Geheimnisse, aber der Export gilt als weitergebbar.
- **Download-Ordner (bekannt, RS-018):** zehn untergeschobene Dateien mit je 500 erfundenen Matches verdrängten
  alle 300 echten ins Archiv. Namen daraus erreichen den Claude-Statistik-Prompt (nur als Text).
- **Eingaben-Karte:** Wird ein Rundenende verpasst, liest die Karte weiter, solange DBD vorn ist – also auch
  Buchstaben aus dem Chat nach der Runde. Im Wortlaut der Regel, vermutlich nicht in ihrem Sinn.
- **Platte voll beim Anhängen:** wird einmal gemeldet, die Runde aber nicht erneut versucht.

---

## 9. GUI- und UX-Analyse

Grundlage: sieben Bildschirmfoto-Sätze (Standard, 900 × 600, Zoom 1,5, hell, Russisch, Japanisch, mit 300 Runden).
Nicht jedes Bild wurde angesehen; Koreanisch und Chinesisch wurden nicht gerendert.

### UX-01 – Fehler angeklickter Aktionen landen nur im Log (Medium, aus dem Code)
80 Aufrufe `_log(…, "Fehler")` gegen 30 `_inform(`. Beispiele: Wiederherstellen aus ZIP gescheitert
(`app_settings.py:648`), „Sichern fehlgeschlagen“ (594), CSV-Export (`app_export.py:253`), „Aufnahme fehlt“
(`app_recordings.py:1116-1436`). Sichtbar ist nur die Marke „Log ⚠“; der Knopf tut scheinbar nichts.
**Lösung:** ein Helfer, der loggt und für angeklickte Aktionen ein Hinweisfenster zeigt. **Aufwand:** M

### UX-02 – Layout bricht bei Zoom, kleinem Fenster und Russisch (Medium bei Zoom 1,5)
- Zoom 1,5, Overlay-Seite: Elementliste abgeschnitten („Syste…“, „Einga…“, „autom…“), Inspektor aus dem Bild.
- 900 × 600: „automatisch · 36…“ schneidet den einzigen Wert der Zeile ab; im Rechner bricht das vierte Perk-Feld allein um.
- Russisch: „Системные данн…“, Knopf ohne Innenabstand, Statuszeile abgeschnitten.

### UX-03 – Kontrast (Low–Medium, berechnet über 69 Kombinationen)
- Deaktivierter Text auf Karte im hellen Thema 2,2–2,5 : 1 – das ist Informationstext, nicht nur ein inaktives Element.
- Rahmen von Textfeld und Auswahlliste gegen die Karte 1,25–1,34 : 1 (Ziel 3 : 1).
- `MIN_CONTRAST` wird nur für Akzent-Paare erzwungen.

### UX-04 – Barrierefreiheit (Low–Medium)
- Symbolknöpfe ohne zugänglichen Namen: 17 Übersicht, 20 Statistik, 13 Aufnahmen.
- Diagramme, Heatmap und Kacheln haben weder Namen noch Tastaturfokus – die Statistik ist für Screenreader unsichtbar.
- Trefferflächen unter 24 px: Schalter 34 × 18, Ankerzellen 30 × 20, Griffe 22 × 22.

### UX-05 – Dichte
Overlay-Seite: 41 Häkchen, 18 Auswahllisten, 6 Regler. Einstellungen: 159 Bedienelemente. Statistik: 4 Gruppen ×
17 Unter-Reiter plus 11 Filter. Der Reiter „Verbindungen“ verlangt drei Entwicklerkonsolen-Einrichtungen, erklärt
in Absätzen von 600–1 100 Zeichen. Der Assistent hat acht Schritte, vier davon sind optionale Anbindungen.

### UX-06 – Statistik: Definitionen statt Rechenfehler
Alle handgerechneten Werte stimmten. Fraglich sind die Definitionen:

| Punkt | Befund |
|---|---|
| Farming | zählt in Rekorden und BP/h mit (BP/h 248k statt 194k, +28 %); die Übersicht schließt es für dieselbe Woche aus (83 % gegen 80 %). Der Docstring von `history.normal()` behauptet das Gegenteil. |
| Kills | `official.py:515-528` zählt „dead“ und „abandoned“, einen Verbindungsabbruch nicht: 3 Opfer + 1 Abbruch = 3 Kills, die 4K-Serie reißt. |
| Wochenvergleich | Montag-bis-jetzt gegen die volle Vorwoche – Anfang der Woche immer „schlechter“. |
| „Heute“ / „Diese Woche“ | nebeneinander, zählen aber verschiedene Rundenmengen. |
| Stichprobe | Map-Balken zeigen „Ø 4.0 Kills“ aus einer einzigen Runde ohne n. |
| Dezimaltrennzeichen | „Ø Kills 3.63“ neben „5,3 h“ in der deutschen Oberfläche. |

### UX-07 – Suche
Keine Treffer für „csv“ und „korpus“; „rekord“ findet OBS-Einstellungen statt Statistik › Rekorde; die
Tippfehler-Toleranz erfindet Treffer („telemetrie“ → „Midwich Elementary School“).

### Kleinere Beobachtungen
- Rotes „Alle löschen“ ist neben „Keine.“ aktiv; „Verbindung trennen“ ist ohne Verbindung aktiv.
- Maps-Seite zeigt „Alle Maps 56“, das Log „46 Maps geladen“.
- Spielsprachen stehen als bloße Kürzel („ES-MX“, „ZH-TW“).
- Japanische Kartenüberschrift erscheint in der Vorschau als Kästchen – vermutlich nur im Container (die
  Ersatzschriften sind Windows-Schriften); unter Windows nicht geprüft.

---

## 10. Codequalitätsanalyse

- **Gott-Klasse:** `App` plus 19 Mixins = 15 680 Zeilen, 782 Methoden, 736 Attribute auf einem Objekt.
  1 284 Methodenaufrufe kreuzen Dateigrenzen. Die Mixins sind eine Dateiaufteilung, keine Trennung.
- **Ausnahmebehandlung:** 840 Handler, 233 fangen `Exception`, 39 sind stilles `pass`, 153 loggen weder noch
  werfen sie weiter. Fragwürdigste: `worker.py:1202` (verschluckt die ganze Vollbreiten-Prüfung),
  `spotify.py:602` (um den Token-Schutz).
- **Duplikate:** praktisch keine (nur die bewusste Kopie `_open_result` in beiden Admin-Helfern).
- **Toter Code:** `app_loadouts.py:183 _loadouts_killer` wird nie aufgerufen; `projectsave.adopt_leftovers`,
  `restore_copy`, `history.set_role`/`set_killer`, `official._next_bucket`, `spotify.can_protect`,
  `qt_theme.pill_style` nur aus Tests (8 von 15 Kandidaten von Hand geprüft).
- **Übersetzungen:** 3 087 Schlüssel × 6 Tabellen, keine fehlenden, keine Platzhalter-Abweichungen.
- **Marker:** kein TODO/FIXME im Code. pyflakes sauber.

**Refactorings mit konkretem Nutzen** (keine Schönheitsumbauten):

1. **Typisierter Einstellungszugriff** – ein geprüfter Lesepunkt je Schlüssel beseitigt alle Absturzstellen von STAB-01.
2. **Objekt für die laufende Runde** (`_hist`, `_sysrec`, `_queue`, `_watch_gen`, Aufnahme-Start/Stopp). Sieben
   Dateien fassen `_hist` an; STAB-03 ist genau ein Reihenfolgefehler dazwischen.
3. **Tabellen statt Verzweigungsketten** für `_dispatch`, `_event`, `_qt_event` – gibt dem vorhandenen Wächter
   etwas Prüfbares.
4. **Ein Zahlen-Leser für alle Parser** (`project._finite` existiert) – beseitigt STAB-06, DATA-01 und die
   Überlauf-Fälle in `config`.

---

## 11. Testabdeckung und Testlücken

**Ausgangslage (selbst ausgeführt):** 2 281 bestanden, 50 übersprungen, 1 fehlgeschlagen, 533 s; pyflakes sauber.
Alle 50 Auslassungen sind Windows-eigen (natives Overlay, Hotkeys, Dateisystem-Semantik, DLL-Suche).

### TEST-01 – Die Wächtertests sind mit gewöhnlichem Python umgehbar
- **Schweregrad:** Medium · **Status:** belegt (zwei Prüfer unabhängig)
- **Ort:** `tests/test_guards.py:10-80`, `test_elevated.py:176-248`, `test_fsops.py:185-268`, `test_launch.py:192`
- Jeder Wächter liest nur `fogscout/*.py` (nicht rekursiv) und sucht die wörtliche Form `Name.attr(…)`.
- **Probe:** In einer Kopie blieben mit eingebauten Verstößen 52 Wächtertests grün. Durchgerutscht:
  `getattr(u, "SendInput")`, `u["PostMessageW"]`, `SendMessageA`, `importlib.import_module("socket")`,
  `from os import remove`, `import subprocess as sp; sp.run(…, shell=True)`, alles in Unterpaketen, `tools/`
  und `installer/`.
- **`OpenProcess` und `ReadProcessMemory` stehen auf keiner Liste**, obwohl CLAUDE.md „nicht einmal
  `OpenProcess`“ sagt.
- **Lösung:** ein gemeinsamer AST-Helfer, der Aliase auflöst und als Erlaubnisliste arbeitet. · **Aufwand:** M

### TEST-02 – Der OpenCV-Plugin-Test schaut vermutlich in den falschen Kanal
- **Schweregrad:** Medium · **Status:** Fehlschlag und Kanal selbst belegt; Folge für Windows offen
- **Ort:** `tests/test_preview.py:363`
- Der eine Fehlschlag der Suite. OpenCV schreibt seine DEBUG-/INFO-Zeilen hier auf die **Standardausgabe**
  (selbst geprüft: Fehlerausgabe leer). Der Test sucht `libraryLoad` in `out.stderr` – er sähe einen
  Plugin-Ladevorgang dann nicht. In GitHub Actions ist er grün (dort kommt die Python-Zeile offenbar zuerst).
  Ob `libraryLoad` unter Windows auf der Fehlerausgabe landet, ist nicht geprüft.
- **Lösung:** `out.stdout + out.stderr` prüfen und die letzte Zeile der Standardausgabe auswerten. · **Aufwand:** S

### TEST-03 – 15 von 56 gezielten Mutanten überleben
- **Schweregrad:** Medium · **Status:** belegt
- 56 Einzeiler-Fehler in kritischer Logik; 41 erkannt. Die relevanten Überlebenden:

| Mutation | Fehlender Test |
|---|---|
| `relupdate.parse_release`: nur noch Präfix statt exakter URL | Asset mit richtigem Präfix, aber anderem Tag |
| `hostsedit._ours`: `all` → `any` | hosts-Zeile mit einem verwalteten und einem fremden Namen – der Mutant löscht die Nutzerzeile |
| `config._version`: `bool`-Schutz entfernt | `"settings_version": true` – alle Migrationen liefen erneut |
| `config`: Migrationsgrenze `< 7` → `< 6` | ein Fixture je Migrationsgrenze (nur v11→12 ist festgehalten) |
| `detector`: Ladebildschirm ohne „still“ | dunkles Bild mit Ladebalken, das sich bewegt |
| `detector`: Lobby mit 1 statt 2 Währungsgruppen | Leiste mit einer einzelnen sechsstelligen Gruppe |
| `Accumulator`: Map-Wechsel nach 2 statt 4 guten Bildern | Banner-Wechsel im 2./3. Bild |
| `official.link`: Rang nach `abs(off)` statt `abs(off − 38)` | zwei Matches bei +5 s und +38 s |
| `layout._resolve`: „keep“-Feld wird verschoben | `resolve(keep=…)` mit Überlappung |
| `relupdate.download`: Größenprüfung entfernt | Download größer als angekündigt |

  Einschränkung: Für zwei Mutanten (`config`, `backups`) wurde der breite Zweitlauf aus Zeitgründen abgebrochen.

### Weitere Beobachtungen
- **Nur Windows-CI deckt den produktiven Löschpfad ab** (`fsops.delete_inside`, `ExclusiveHandle`,
  `restrict_dll_search`).
- **Kein Höchstwert für Auslassungen in CI:** ohne `libEGL` wurden 461 Tests still übersprungen.
- **Fehlende Testarten:** keine eigenschaftsbasierten Tests, kein Parser-Fuzzing, kein Test, der einen
  Schreibvorgang mittendrin abbricht, keine Leistungs-Regressionstests (letzteres bewusst).
- **Kopplung:** 2 931 Zugriffe auf private Attribute in Tests (`test_uimodel` 729, `test_obsrec` 327).
- **Module ohne direkten Testimport:** `editorclaude` (970 Zeilen), `editorproject` (799), `qt_preview` (562),
  `editormontage`, `editormusic`, `app_server`.
- **Langsam:** `test_mapstyle` 108 s + 86 s + 56 s, `test_uimodel` 64 s.
- **Ein roter Lauf auf `main`** (Merge von #506, 1.57.64) steht in der Actions-Historie; Ursache nicht untersucht.

---

## 12. Abhängigkeiten und Supply Chain

**Solide:** alle 26 Einträge der vier gehashten Anforderungsdateien tragen Hashes; `--require-hashes`,
`--only-binary`; Actions auf Commit-SHA festgelegt; nur `pull_request` (kein `pull_request_target`); keine
`${{ }}` in Skripten; Release nur per Handstart auf `main`; jedes Paket wird benutzt.

| Punkt | Schweregrad | Status |
|---|---|---|
| **Lizenztexte im Setup unvollständig:** `licenses/` enthält nur Apache-2.0; ausgeliefert werden auch Qt/PySide6 und pystray (LGPL-3.0) sowie ffmpeg (Linux-Build GPL-3 laut THIRD_PARTY.md, Windows-Build dort „nicht geprüft“). | Low (rechtlich) | belegt |
| **Altes ffmpeg läuft erhöht auf nutzerbeschreibbaren Dateien:** imageio-ffmpeg 0.6.0 bringt ffmpeg 7.1 (Build von 2024). | Medium/Low | theoretisch – keine CVE-Datenbank verfügbar |
| **Unsignierte Releases**, Prüfsumme aus demselben Kanal wie das Setup (siehe SEC-01). | – | bekannt, vom Nutzer zurückgestellt |
| `requirements-dev.txt` ohne Hashes (nur Testjobs). | Low | belegt |
| Release-Job ohne Environment-Schutz: jeder mit Schreibrecht kann veröffentlichen. | Low | belegt |

**Nicht beurteilbar:** numpy 2.5.4, Pillow 13.0.0, opencv 5.0.0.93, protobuf 7.36.2, onnxruntime 1.31.0,
PySide6 6.11.2 und pip 26.2.1 sind neuer als mein Wissensstand; bekannte Lücken dieser Versionen konnte ich
nicht prüfen. Die Dependabot-Warnungen des Repos sind dafür die richtige Quelle.

---

## 13. Verifizierte Fehler mit Reproduktionsschritten

Die Proben liegen im Scratch-Ordner des Containers und verschwinden mit ihm. Die Kernfälle lassen sich so nachstellen:

| ID | Minimaler Auslöser | Beobachtung |
|---|---|---|
| STAB-01 | `settings.json` = `{"ui_zoom": 1e9}` bzw. `{"languages": 5}` | `App()` wirft `OverflowError`/`TypeError`, keine `.broken` |
| STAB-02 | `Recognizer.probs(np.full((1, 1103, 3), 128, np.uint8))` | 5,7 s, Arbeitsspeicher 106 → 4 262 MB, bleibt |
| STAB-03 | 0-Byte-Bild für eine Map, dann Ereignis `detected` | `start_round` gerufen, `worker.map_on_screen == False` |
| STAB-06 | Projekt mit `"inputs": {"size": NaN}` öffnen | Traceback, Zustand `loading`, kein Speichern, keine Warnung |
| DATA-01 | Zeile `{"lost": true, "t": …, "ping": 10**400}` in `rounds.jsonl` | `load_lost_rounds` wirft `OverflowError` |
| DATA-02 | Runde mit `map = "A\u2028B"` sichern und wiederherstellen | 3 gesichert, 1 wiederhergestellt |
| SEC-02 | Ordner während `merge` gegen Link tauschen | fremde Datei gelöscht |
| SEC-03 | Link bei `<Runde> (zusammen).mkv.txt` | Ziel mit Listentext überschrieben |
| SEC-04 | `fogscout.log` als Link, dann `_setup_logging` | Ziel abgeschnitten und überschrieben |
| TEST-02 | `pytest tests/test_preview.py -k opencv` | `assert '[DEBUG:0@0.007]' == 'False'` |

---

## 14. Priorisierte Maßnahmenliste

| # | Maßnahme | Befunde | Aufwand | Risiko der Änderung |
|---|---|---|---|---|
| 1 | Die drei Dateioperationen über `fsops` führen (Löschen per Handle, exklusive Temp-Namen, Log über sicheren Öffner) | SEC-02, SEC-03, SEC-04 | S | gering |
| 2 | Einstellungen beim Laden gegen `DEFAULTS` typprüfen; Startfehler → `.broken` + Neustart mit Standardwerten | STAB-01 | S–M | gering |
| 3 | OCR-Eingabebreite begrenzen | STAB-02 | S | gering – gegen den Banner-Korpus prüfen |
| 4 | Dekodierfehler im Kartenbild → Zweig „Map ohne Bild“ | STAB-03 | S | gering |
| 5 | Ein Zahlen-Leser für alle Parser; `_rewrite` verwirft nichts mehr; `splitlines` ersetzen | STAB-06, DATA-01, DATA-02 | S | gering |
| 6 | Formgrößen im Projekt begrenzen; Bilder ab ~50 Megapixel ablehnen | STAB-05, STAB-08 | S | gering |
| 7 | Update-Vertrauen: Signatur des Setups oder eigener TLS-Kontext ohne Benutzer-Proxy | SEC-01 | M | mittel – PCs, die einen Proxy brauchen |
| 8 | Sicherung vor „Zurücksetzen“; Notizen behalten | DATA-03 | S | gering |
| 9 | Wächtertests auf AST mit Alias-Auflösung umstellen; `OpenProcess` aufnehmen; OpenCV-Test korrigieren | TEST-01, TEST-02 | M | gering |
| 10 | Tests für die überlebenden Mutanten (zuerst Release-URL, hosts-Filter, `settings_version`) | TEST-03 | S–M | keins |
| 11 | Rundenende ohne Balken härten (Währungssymbol verlangen, CONTINUE zwei Blicke); Kandidat verfallen lassen | STAB-04, STAB-07 | S–M | **hoch** – nur gegen die Testbilder in `tests/data/end` und echte Screenshots |
| 12 | Fehler angeklickter Aktionen sichtbar machen | UX-01 | M | gering |
| 13 | Score-Blick entlasten | Abschnitt 7 | S–M | mittel – Lesegenauigkeit gegen den Korpus prüfen |
| 14 | Doku nachziehen (PRIVACY.md, Projektformat, Userscript-Version, Lizenztexte) | PRIV-02, Abschnitt 12 | S | keins |
| 15 | Farming-Regel und Kills-Definition einmal entscheiden | UX-06 | S | gering – Entscheidung des Nutzers |

---

## 15. Empfohlene langfristige Verbesserungen

1. **Signierte Releases** mit im Programm eingebautem öffentlichem Schlüssel – schließt SEC-01 auch für ein
   kompromittiertes Repository-Konto.
2. **ffmpeg mit eingeschränktem Token starten** oder nur die Container und Codecs annehmen, die OBS erzeugt.
3. **Zustand der Runde als eigenes Objekt** und **typisierter Einstellungszugriff** (Abschnitt 10).
4. **Parser-Fuzzing und eigenschaftsbasierte Tests** als feste Testart – die Prüfer fanden damit in Minuten,
   was 2 300 Beispieltests nicht fanden.
5. **„Basis / Alle Optionen“** auf Overlay- und Einstellungsseite (`fold` und `indent` existieren schon).
6. **README teilen:** kurze Anleitung für Nutzer; die „seit x.y“-Geschichte gehört nach `HISTORY.md`
   (die README ist 219 KB groß, mit Absätzen bis 16 KB).
7. **Versionszählung vereinheitlichen:** Die neue Reihe steht bei 1.57.x und überlappt mit der alten
   (1.25–1.66). 92 Code-Verweise auf 1.60–1.66.x sind dadurch mehrdeutig.

---

## 16. Nicht verifizierbare Risiken und nicht geprüfte Bereiche

**Nur unter Windows prüfbar (nicht ausgeführt):**
- Junction- und Objektmanager-Varianten von SEC-02, SEC-03, SEC-04; Rechte von `{app}\update`; die Aufgabenplanung.
- SEC-01 vollständig: Zertifikatsspeicher des Benutzers, stiller Registry-Eintrag.
- Ob der PyInstaller-Bootloader `_PYI_*`-Variablen aus der Benutzerumgebung ignoriert (läuft vor der Härtung).
- `GAME_GONE = 3 s`: Ob ein hängendes DBD-Fenster hinter Windows' „Ghost“-Fenster als geschlossen gilt und die Runde beendet.
- Natives Overlay, Hotkeys, Tray, DPAPI, WinRT-Medien, NVML/HWiNFO, Fensteraufnahme.

**Geplant, aber nicht gelaufen** (Nutzungslimit):
- OBS-Abbruch mitten in der Aufnahme, ffmpeg-Fehler oder volle Platte beim Zusammenfügen, `_watchdog`.
- Update-Installation während einer Runde; Ereignisse während des Beendens; offene Schreibvorgänge beim Beenden
  für Editor-Autosave und YouTube-Warteschlange.
- Zwei Editor-Fenster auf einem Projekt, fremde Änderung, Absturz zwischen Temp-Datei und Veröffentlichen.
- Falsche Map aus Beinahe-Namen (neue Maps, Text mit ≥ 3 Zeichen).
- Fenster-Lecks der Clip- und Bild-Editoren; Mediathek mit 2 000 Einträgen.
- `projectsave.py`, `thumbs`, `mapstyle`, `mapimage`, `steamshots`, `sysinfo`, `media`, `diagnose` nur überflogen.
- Durchsicht aller Logzeilen auf sensible Daten (Stichprobe: „Bild konnte nicht geladen werden: {path}“ loggt
  einen vollen Pfad; `HomeFilter` maskiert den Benutzerordner).
- Echte Tastaturbedienung, Screenreader, Windows-Hochkontrast.

**Theoretisch, ohne Beleg:**
- Werkzeugkasten-Verbrauch im Rechner (83,33 s gegen 80 s, je nach Lesart des Wikis).
- Bekannte Lücken in ffmpeg 7.1 und den festgelegten Paketversionen.

**Git-Historie:** Der Klon war flach (105 Commits ab 19.11.2026); ob frühere Korrekturen später abgeschwächt
wurden, ließ sich nicht per Historie prüfen – nur der heutige Code.

---

## 17. Bereits vorhandene Schutzmaßnahmen

- **Update-Kette:** Rollback-Schutz, exakte Asset-Prüfung, SHA-256 beim Kopieren und erneut unter gesperrtem
  Handle, Start nur aus dem Admin-Ordner, nur HTTPS-Weiterleitungen, Zugangs-Header nie an fremde Hosts.
- **Umgebung des Admin-Prozesses:** `SSL_CERT_*`, `PYTHON*`, `GIT_*`, `OPENSSL_*`, `OPENCV_*`, Qt-Pfade entfernt;
  DLL-Suche ohne `PATH`; Systemprogramme nur über API-Pfade; `DBDMS_DATA_DIR` erhöht ignoriert.
- **Datei-Primitive:** atomares Schreiben mit `fsync`, exklusives Anlegen, Löschen über Handle, Sperre um jedes
  Lesen-Ändern-Schreiben des Verlaufs.
- **Admin-Helfer:** hosts-Datei nur eigener Abschnitt, nur verwaltete Namen, feste Adresse; Mitschnitt nur `RCVALL_IPLEVEL`.
- **Externe Dienste:** OBS nur `127.0.0.1`; Tokens DPAPI-geschützt und nie im Klartext gespeichert; Claude erhält
  nur feste Programmtexte, Antworten nur aus festen Listen; alle Netzaufrufe mit Frist und begrenztem Lesen.
- **Erkennung:** eigene Fenster vor jeder Auswertung geschwärzt; Generationen an Ereignissen; jeder Takt in
  eigenem `try`; Ausfall wird sichtbar gemeldet und geht in die sichere Richtung (Overlay bleibt).
- **Lieferkette:** alles festgelegt und gehasht, Actions auf SHA, Telemetrie von onnxruntime abgeschaltet.

---

## 18. Bereiche ohne Befund

- **ffmpeg-Argumente und Filtergraphen** – keine Injektion möglich gefunden (alle vier Exportmodi mit feindlichen
  Namen und Texten).
- **Sequenzmodell des Editors** – 20 000 Zufallsfolgen, 0 Verletzungen; Undo/Redo identisch.
- **Export-Abbruch** – keine Kindprozesse, keine Reste, Aufnahme unverändert.
- **ZIP-Wiederherstellung** – kein Pfad nach außen; doppeltes Wiederherstellen fügt nichts doppelt hinzu.
- **Aufnahme-Index und Aufräumen** – kein Löschen außerhalb des Ordners.
- **Zustandsautomaten** – 60 000 Zufallsfolgen mit springenden Uhren ohne Ausnahme oder hängenden Zustand.
- **Gleichzeitiges Schreiben des Verlaufs** – 600 von 600 Runden, 1 200 von 1 200 verlorenen Zeilen.
- **Ereignisreihenfolge im Controller** – unerwartete und verstümmelte Ereignisse werden abgefangen.
- **Claude-Katalog, OAuth-Rückruf, Token-Speicherung, Antwort-Parser.**
- **Statistik-Arithmetik und Zeitbehandlung** (Sommerzeit, Wochenbeginn) sowie **Rechner** (acht Szenarien exakt).
- **Übersetzungen** – vollständig, keine Platzhalter-Fehler.
- **Harte Regeln in den gelesenen Modulen** – kein `OpenProcess`-Aufruf, keine Eingabe- oder Hook-API, keine
  Spieldateien; `GetAsyncKeyState` nur für die 13 Tasten und nur in `inputs.py`.
- **Speicher im Dauerlauf** – kein Leck über 2 000 Blicke; Timer bleiben konstant.
