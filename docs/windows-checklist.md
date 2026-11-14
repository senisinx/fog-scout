# Offene Prüfungen am Windows-PC

Gesammelt aus den vier alten Abschlussberichten (seit 1.50.4 in `docs/archive/`). Diese Punkte liessen sich ohne Windows, DBD und OBS nicht prüfen; ob sie in späteren Versionen am PC geprüft wurden, steht nirgends. Beim Durchgehen erledigte Punkte hier löschen, Fehler als Issue oder Aufgabe festhalten.

## Aus `IMPROVEMENTS_REPORT.md` (1.22.3–1.23.1, Abschnitt F)

Ohne Windows-Rechner und Spiel nicht geprüft – bitte am PC durchgehen:

1. **Hell-Modus:** Statusanzeige oben rechts, Ping-Farben auf der Seite Server, Werte der Kacheln „Heute“, Abspielkopf und Marken im grossen Editor, Farbfelder im Bild-Editor.
2. **Primärknöpfe:** deaktiviert grau statt Akzentfarbe (z. B. Einrichtung, Editor „Exportieren“ ohne Clip); gedrückt sichtbar dunkler; Tab-Taste zeigt den Fokus auf ▶-Knöpfen in den Tabellen.
3. **Klicks:** Knöpfe und Häkchen reagieren spürbar sofort; Regler auf der Seite Overlay ziehen ohne Ruckeln und ohne mehr CPU als vorher (Task-Manager).
4. **Aufnahmen:** mit dem Aufnahme-Laufwerk als externem Datenträger (T7) abziehen und wieder anstecken – die Seite zeigt den Ordner nach dem Einstecken sofort wieder; eine Runde direkt danach wird aufgenommen.
5. **Doppelklick/Enter** auf eine Aufnahme und einen Clip spielt ihn ab; zwei markieren → „Als Montage öffnen …“ erscheint.
6. **Rückfragen:** „Aufnahme löschen“ – roter Knopf „Löschen“, Enter bricht ab; dasselbe mit DBD im Vordergrund (z. B. Beenden während einer hängenden Sicherung).
7. **Begriffe:** Hotkey Strg+Alt+M und Infobereich „Karte ein/aus“ blenden nur die Karte aus; „Overlay ausschalten“ in der Übersicht alles.
8. **Server:** eine Region abhaken – gelbe Zeile „Nicht angewendet – 1 Änderung“; alle abhaken – „Keine Region angehakt …“; „Auswahl anwenden“ (UAC) – Zeile verschwindet.
9. **Suche:** Strg+F „Debug“ → springt zu Log › Erweitert und klappt es auf.
10. **Übersicht bei 1280 px Breite** ohne Stats-Daten: der Knopf in der Kachel „Ø Kills“ endet auf „…“, Tooltip zeigt den vollen Text.
11. **Editor-Mediathek im Dunkelmodus:** die markierte Aufnahme ist deutlich hervorgehoben.

**Bekannte Einschränkungen:**

- „F8“ steht fest in einigen Texten, auch wenn die Clip-Taste umbelegt ist (D).
- Die Karte „Neu seit …“ zeigt die deutschen HISTORY-Sätze auch in der englischen Oberfläche (D).
- Alle Zeiten in Abschnitt B stammen aus Linux offscreen.

## Aus `IMPROVEMENTS_REPORT_1.25.md` (1.25–1.25.3, Abschnitt F)

1. **Am Windows-PC ansehen, bei 100/125/150 %:**
   - Scroll-Griffe und Kasten-Griffe sichtbar, aber nicht aufdringlich.
   - Platzhalter der Suche lesbar.
   - Reiter mit Linie.
   - Die Navigationsmarke gerade.
2. **Aufnahmen:** Statusspalte mit Stern/Fahne/Abspielzeichen; Tooltip beim Darüberfahren.
3. **OBS schliessen → Seite Aufnahmen:** Ursache in Worten.
4. **Einstellungen › Hotkeys:** drei Gruppen; eine Taste ändern und speichern.
5. **Kartenstil umschalten:** `cache/maps_dark` behält nur aktuelle Dateien. Die Log-Datei nennt einmal „Kartenstil-Cache: N alte Bilder entfernt“.
6. **Offen aus früheren Berichten:** CodeQL-Alert schliessen, Reglerkontrast in OLED, siehe D.

## Aus `PHASE2_REPORT.md` (1.24–1.24.7, Abschnitt 9)

1. **Navigation:** Markenzeile und Status unten in Dark, Light und OLED. Bei einem Fenster unter 960 px nur Kompass und Punkt, Tooltip mit Status.
   - Status wechselt beim DBD-Start („wartet auf das Map-Banner“), beim Banner (Map-Name) und nach der Runde.
   - Klick und Enter öffnen die Übersicht.
2. **Übersicht › Funktionen:** Bei laufendem DBD „Automatische Erkennung – aktiv“, „Systemwerte – aktiv“ bzw. „HWiNFO fehlt“ ohne HWiNFO.
   - Ohne OBS und nach einem Besuch der Seite Aufnahmen: „OBS nicht erreichbar“. Nach dem Start von OBS verschwindet es spätestens nach 60 s.
   - Spotify bzw. YouTube ohne Anmeldung: „Anmeldung nötig“.
3. **Overlay-Seite** bei 1280×800, 100 % und 125 %: Vorschau links, Reiter rechts, nichts abgeschnitten (Windows-Schriften sind breiter als im Container).
4. **Aufnahmen:** OBS aus → rote Zeile und „Verbindung prüfen …“ führt zu Einstellungen › Aufnahmen. Aufnahme läuft → grüne Zeile; Pause → gelb.
5. **Server:** Kann die hosts-Datei nicht gelesen werden (z. B. gesperrt durch Virenscanner), ist der Status rot und „Auswahl anwenden“ gesperrt.
   - Danach normal: „Auswahl anwenden“ gold gefüllt.
   - UAC-Abbruch → Zeile nicht rot.
6. **Einstellungen › Aufnahmen › Verbindung testen:** grün bei Erfolg, rot ohne OBS.
7. **Log:** Suche ohne Treffer und „Leeren“ zeigen den Platzhalter.
8. **Heller Modus und Farbthemen:** In Hell, OLED und mit einer anderen Akzentfarbe sind die gezeichneten Zeichen auf Übersicht und Maps gut lesbar: „Zurück“, „Suche leeren“, das ✕ des Hinweises bei unbekannter Map, ▶ der letzten Runden. Ein Themenwechsel bei laufendem Programm zeichnet sie neu.
9. **Bildschirmwechsel:** Das Fenster auf einen Bildschirm mit anderer Skalierung ziehen (z. B. 100 % → 150 %). Kompass, Statuszeichen und Knopfzeichen bleiben scharf (`QEvent.DevicePixelRatioChange`).
10. **Schmales Fenster (< 960 px):** Unten in der Navigation nur das Zeichen, bei einem Fehler ein Warnzeichen. Die Übersicht zeigt den Zustand dann unter ihrem Titel in Worten.
11. **OBS beim DBD-Start nicht offen:** „Aufnahmen mit OBS“ zeigt „OBS nicht verbunden“. Nach dem Einrichten (spätestens nach 30 s, `RECHECK_S`) zeigt es „bereit“. Sind Aufnahmen ausgeschaltet, aber der Ordner bleibt gesetzt, ist die Aufnahme-Karte nicht rot.
12. **1.24.7 – Ausrichtung unter Windows:** Kompass, Statuszeichen und Navigationssymbole stehen auf einer Linie. `NAV_SIGN_X` ist offscreen gemessen (Rand 6 + 12 + 6 px des Qt-Stils). Unter Windows bei 100 %, 125 % und 150 % prüfen; weicht der Stil dort ab, ist es ein Wert.
    - Zustandswörter genau unter dem Text der Häkchen, auch bei grösserer Schrift (Einstellungen → Schriftgrösse).
    - Mit OBS geschlossen ist „Clip speichern (F8)“ gesperrt.
13. **Risiko:** Die Zustandswörter der Funktionen-Karte hängen an vorhandenen Attributen. Ein fehlendes Attribut ergibt keinen Zustand statt eines Fehlers – sichtbar falsch wäre höchstens ein fehlender Hinweis.

## Aus `STABILITY_AUDIT_REPORT.md` (1.33.1, Abschnitt 11)

1. **Neuinstallation** mit dem Setup aus dem Release, mit eigenem Admin-Konto: Aufgaben „Fog Scout“ und „(Autostart)“ sind da, Startmenü- und Desktop-Verknüpfung auch, der Start erfolgt ohne Windows-Abfrage.
2. **Übernahme:** Die Frage kommt beim ersten Start (nur wenn vorher die `start.bat`-Verknüpfung eingerichtet war). Danach Runden und Einstellungen prüfen.
3. **Standardkonto mit anderem Admin:** Installieren mit den Daten eines anderen Admin-Kontos → keine Aufgaben, aber „Fog Scout“ im Startmenü für alle; Programm starten, „Verbunden mit“ fragt per UAC.
4. **Update:** Nach dem nächsten Merge (Build 7): „Jetzt nach Updates suchen“ → „Aktualisieren und neu starten“ → Fog Scout schliesst sich, das Setup läuft, Fog Scout ist wieder da, `%LOCALAPPDATA%\FogScout\cache\update` ist nach dem Start leer.
5. **Update mit abgelehnter UAC-Abfrage** (falls Fog Scout ohne Admin läuft): Meldung erscheint, Fog Scout startet wieder.
6. **Deinstallation:** Aufgaben und Verknüpfungen sind weg, `%LOCALAPPDATA%\FogScout` bleibt.
