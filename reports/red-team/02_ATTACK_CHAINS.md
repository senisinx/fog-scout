# Red-Team-Audit Fog Scout – 02 Angriffsketten

Jede Kette nennt die Kontrolle, die den jeweiligen Schritt verhindern **müsste**, und ob sie heute greift (✔ greift, ✘ fehlt, ~ teilweise).

## K1 – Vom Benutzerkonto zum Administrator über OBS (RS-003) — bestätigt im Fog-Scout-Teil

Vorbedingungen: installierte Version (Aufgabe mit höchsten Rechten), „OBS mit DBD starten“ an, OBS nicht offen.

| # | Schritt | Kontrolle | Stand |
|---|---|---|---|
| 1 | Malware (mittlere Integrität) legt ein Skript in die OBS-Szenensammlung unter `%APPDATA%\obs-studio` | Profil des Nutzers ist sein eigenes – nicht verhinderbar | – |
| 2 | Nutzer startet DBD; Fog Scout erkennt das Fenster, OBS nicht erreichbar | – | – |
| 3 | Fog Scout startet `obs64.exe` | echtes Binary aus HKLM/Program Files (`obs_exe`) | ✔ |
| 4 | … **mit seinem Admin-Token** (`Popen`) | Start mit abgesenktem Token / über die Shell des Nutzers, wie 1.38.21 für Browser/Dateien | ✘ |
| 5 | OBS lädt das Skript als Administrator | OBS-eigene Sache (nicht ausgeführt) | Hypothese |

Wirkung: Admin-Codeausführung ohne Abfrage. Wirksamster Bruchpunkt: Schritt 4.

## K2 – Benutzerkonto löscht fremde Dateien mit Admin-Rechten (RS-002, RS-006)

| # | Schritt | Kontrolle | Stand |
|---|---|---|---|
| 1 | Malware ersetzt `…\FogScout\cache\clipthumbs` (oder `cache`, oder `FogScout`) durch eine Junction auf einen fremden Ordner | Ordner im eigenen Profil – nicht verhinderbar | – |
| 2 | Fog Scout (Admin) räumt Vorschaubilder/Analysen/Stile/Korpus auf | Wurzel des Aufräumens darf kein Link sein bzw. muss real unterhalb des Datenordners liegen | ✘ |
| 3 | `delete_inside` prüft Teile unterhalb der Wurzel und Reparse-Punkt der Datei | Links unterhalb werden nicht gefolgt | ✔ |
| 4 | Löschen per Handle (`FileDispositionInfo`) | – | (wirkt im Ziel) |

Wirkung: Admin-Löschung von `.png/.jpg/.json` (> 90 Tage) bzw. eigenen Namensmustern in beliebigen Ordnern. Bruchpunkt: Schritt 2.

## K3 – Präpariertes „Backup“ legt die Statistik lahm (RS-001)

| # | Schritt | Kontrolle | Stand |
|---|---|---|---|
| 1 | Angreifer verteilt ein „Backup mit Statistik“ (Forum/Discord) | Nutzerentscheidung; Vorschau `inspect` zeigt nur Zahlen | ~ |
| 2 | Restore übernimmt `{"lost": true, "t": Infinity}` bzw. `t/seconds = 1e300` | Wertebereich beim Import prüfen (1.46.4 nur `isfinite` für gezählte Runden) | ✘ |
| 3 | Statistik rendert `time.localtime(t)` | Darstellung robust gegen gespeicherte Werte | ✘ |
| 4 | Snapshot `backup/…restore` vor dem Zusammenführen | Wiederherstellung möglich | ✔ |

Wirkung: Statistik dauerhaft fehlerhaft, keine Rechteausweitung.

## K4 – Update-Austausch zwischen Prüfung und Start — verifiziert abgewehrt

Release-Metadaten (fremde URL, zweites Setup, fehlende Prüfsumme, Digest ≠ .sha256), HTTP-Weiterleitung, Junction auf `cache/update`, Austausch der Datei nach dem Download: alle durch `parse_release`, `SafeRedirect`, `_linked`, `staged_setup` (Kopie in Admin-Ordner, Hash unter Lese-Sperre bis `ShellExecute`) abgefangen; Tests grün (siehe 01, RS-014). Restrisiko: unsignierte Releases / GitHub-Konto (akzeptiert).

## K5 – Falsches OBS bewegt/löscht fremde Dateien — verifiziert abgewehrt

Lokaler Prozess belegt Port 4455 und antwortet mit `outputPath` auf eine fremde Datei: `obs_file(inside=, since=)` nimmt nur reguläre Videodateien ohne Reparse-Punkt, im Aufnahmeordner oder frisch geschrieben; Löschen nur über `delete_inside` und nur indexierte Videonamen. Rest: RS-005 (Junction-Wechsel am Aufnahmeordner, Hypothese).

## K6 – KI-Antwort löst unerlaubte Aktion aus — verifiziert abgewehrt

Manipulierte/injizierte Antwort → `parse` nimmt nur bekannte ids, `apply` nur `KINDS` mit geprüften Zahlen (NaN/∞/bool/Bereich), Ausführung erst auf „Übernehmen“; Texte werden als Bild gerendert. Kein Weg zu Pfad, URL, Shell oder Code gefunden.

## K7 – Diagnose/Log gibt Privates preis — stichprobenartig, ohne Befund

`HomeFilter` (`~`), Fenster nur Art+Klasse, Server-IP nur als Region, Titel/Keys nie ins Log (Code-Lesen; keine neue Probe ausgeführt).
