# Fog Scout – Deep Code Review: Kurzfassung

Geprüft: 1.57.67 (`ae858f6`), 26.11.2026. Volltext: `DEEP_CODE_REVIEW_REPORT.md`.
Am Repository wurde nichts geändert. Geprüft in einem Linux-Container – alles Windows-Eigene nur am Code.

## Ergebnis in drei Sätzen

Keine kritische und keine aus dem Netz ausnutzbare Lücke; alle Sicherheitsbefunde setzen ein Programm voraus,
das schon im Benutzerkonto läuft. Der Admin-Prozess fasst an drei Stellen Dateien in nutzerbeschreibbaren Ordnern
ohne die eigenen Schutz-Primitive an, und das Update vertraut dem TLS-Speicher und Proxy des Benutzers. Die
größte Alltagsgefahr ist nicht Sicherheit, sondern Robustheit: falsche Werte in `settings.json`, Projektdateien
und Sicherungen werden auf Form geprüft, nicht auf Typ und Bereich.

## Die größten Risiken

| ID | Befund | Schweregrad | Status |
|---|---|---|---|
| STAB-01 | Lesbare, aber falsche `settings.json` (z. B. `"ui_zoom": 1e9`) verhindert jeden Start, ohne Rettungsweg – 156 Fälle über 45 Schlüssel | High | belegt |
| SEC-02 | `official.take_downloads` löscht nach dem Lesen per Pfad – beliebiges Löschen als Administrator über Ordnertausch | High | Linux belegt, Windows wahrscheinlich |
| SEC-01 | Update-Prüfung vertraut Proxy und Stammzertifikaten des Benutzerkontos; Prüfsumme kommt über denselben Kanal | High | wahrscheinlich |
| SEC-03 / SEC-04 | `merge_files` und das Log schreiben durch vorab gelegte Links | Medium | Linux belegt |
| STAB-02 | 1 Pixel hoher Banner-Ausschnitt → OCR-Breite 52 944: 5,7 s, 4,2 GB RAM, bis zum Neustart belegt | Medium | Aufblähen belegt, realer Auslöser nur synthetisch |
| STAB-03 | Defektes Kartenbild öffnet eine Runde samt Aufnahme, die nie endet | Medium | belegt |
| STAB-06 | `NaN` in einer Projektdatei: Editor speichert nichts mehr und warnt beim Schließen nicht | Medium | belegt |
| DATA-01 | Eine überlaufende Zahl in einer Sicherung bricht die Statistik dauerhaft; in einer normalen Zeile wird die Runde beim nächsten Umschreiben gelöscht | Medium | belegt |
| STAB-04 | Auf 16:9 beendet ein fremdes „Continue“ unten rechts die Runde beim ersten Blick | Medium | synthetisch belegt |
| TEST-01 | Wächtertests der harten Regeln sind per Alias-Import umgehbar; `OpenProcess` steht auf keiner Liste | Medium | belegt |

## Die dringendsten Maßnahmen

1. **Drei Dateioperationen über `fsops` führen** (SEC-02, SEC-03, SEC-04) – klein, geringes Risiko.
2. **Einstellungen beim Laden typprüfen** und bei Startfehler mit Standardwerten neu versuchen (STAB-01).
3. **OCR-Eingabebreite begrenzen** (STAB-02).
4. **Dekodierfehler im Kartenbild** in den Zweig „Map ohne Bild“ leiten (STAB-03).
5. **Ein Zahlen-Leser für alle Parser**; `_rewrite` verwirft keine Zeilen mehr (STAB-06, DATA-01, DATA-02).
6. **Update-Vertrauen:** Setup signieren oder eigenen TLS-Kontext ohne Benutzer-Proxy (SEC-01).
7. **Sicherung vor „Alle Einstellungen zurücksetzen“** – heute gehen Notizen und Zugangsdaten still verloren.
8. **Wächtertests auf AST umstellen**, den OpenCV-Test korrigieren, Tests für die 15 überlebenden Mutanten.

Rundenende-Härtung (STAB-04) bewusst erst danach und nur gegen echte Screenshots: Fehlalarme sind dort der
schlimmste Fehler.

## Was gut ist

Update-Kette (Hash-Prüfung, Rollback-Schutz), ffmpeg-Aufrufe (keine Injektion gefunden), ZIP-Wiederherstellung,
Aufnahme-Index, Claude-/OAuth-/Token-Code, Zustandsautomaten der Erkennung, Statistik-Arithmetik, Übersetzungen.
Leerlauf ≈ 1 % eines Kerns, kein Speicherleck über 2 000 Blicke.

## Performance

Ein echter Engpass: der Score-Blick alle 0,25 s kostet bei sichtbaren Events ≈ 145 ms (Kommentar im Code: 29 ms),
also gut die Hälfte jeder Sekunde. Alles andere ist unauffällig oder nicht lohnend.

## Einschränkungen dieser Prüfung

- Windows-eigenes Verhalten ist nicht ausgeführt, nur gelesen.
- Ein Nutzungslimit hat sechs der acht Prüfer unterbrochen; mehrere geplante Prüfungen sind nicht gelaufen
  (Liste in Abschnitt 16 des Berichts).
- Ein Test hat einmal real `api.github.com` abgefragt (lesend, ohne Anmeldung) – gegen die Vorgabe.
- Bekannte Lücken der festgelegten Paketversionen konnte ich nicht prüfen (neuer als mein Wissensstand).
- Die Testsuite lief hier mit 1 Fehlschlag (OpenCV-Test, TEST-02), 2 281 bestanden, 50 nur unter Windows.
