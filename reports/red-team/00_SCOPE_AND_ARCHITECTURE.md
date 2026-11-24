# Red-Team-Audit Fog Scout – 00 Scope und Architektur

Stand: 24.11.2026. Nur Linux-Container; **kein Windows, kein DBD, kein OBS**. Alles, was nur unter Windows gilt (Junctions, UAC, Aufgabenplanung, DPAPI, Named Pipes), ist im Code nachvollzogen und – wo möglich – mit POSIX-Symlinks bzw. Fakes nachgestellt, aber **nicht unter Windows ausgeführt**.

## Geprüfter Stand

| | |
|---|---|
| Repository | `senisinx/fog-scout` |
| Zweig | `claude/fog-scout-red-team-audit-j3ec8l` (beim Start = `main`) |
| HEAD beim Start | `1469fbf` (Merge PR #488, Version 1.57.47) |
| Arbeitsbaum beim Start | sauber, keine fremden Änderungen |
| Umgebung | Python 3.13.18, venv mit `requirements.txt` (Hashes, nur Wheels) + `requirements-dev.txt` + `imageio-ffmpeg==0.6.0`, Qt offscreen (libEGL nachinstalliert) |
| Geändert | nur `tests/test_red_team.py` (neu) und `reports/red-team/*` – **kein Produktionscode** |

## Gelesene Grundlagen

`CLAUDE.md`, `README.md` (Sicherheits-/Admin-Abschnitte), `SECURITY.md`, `docs/regeln/*` (Claude, OBS, YouTube, Spotify, offizielle Match-Daten), `docs/archive/STABILITY_AUDIT_REPORT.md`, die Sicherheitszeilen in `HISTORY.md` (1.8.38, 1.33.1, 1.33.5, 1.34, 1.38.20, 1.38.21, 1.38.57, 1.46.4, 1.55.4) und die zugehörigen Tests (`test_elevated`, `test_relupdate`, `test_backups`, `test_fsops`, `test_obsrec`, `test_spotify`, `test_net`, `test_editcommands`).

## Prozesse und Rechte

| Prozess | Rechte | Code von | Bemerkung |
|---|---|---|---|
| `FogScout.exe` (installiert) | **Administrator** ohne UAC-Abfrage (Aufgabe „Fog Scout“, `RunLevel Highest`) | `C:\Program Files\Fog Scout` (nur Admins schreiben) | liest/schreibt den **Datenordner `%LOCALAPPDATA%\FogScout`** – schreibbar für jedes Programm des Nutzers |
| `start.bat`-Betrieb | Administrator über dieselbe Aufgabe | Programmordner (oft nutzerbeschreibbar) | README nennt das bewusst als Entwicklerweg und akzeptiertes Risiko |
| UAC-Fall „anderer Admin“ | normal; Helfer per `runas` | Program Files | nur Startmenü-Verknüpfung |
| `--helper hostsedit` / `hostsedit.py -I -S` | Administrator (UAC) bzw. im Prozess, wenn schon erhöht | Program Files bzw. Programmordner | liest Job-JSON aus `%TEMP%`, schreibt hosts-Datei + Ergebnisdatei |
| `--helper netwatch` | Administrator | dito | Raw-Socket `RCVALL_IPLEVEL`, schreibt Ergebnisdatei |
| Setup (`/update=1`) | Administrator | Kopie in `<Programmordner>\update` | per SHA-256 doppelt geprüft, Handle gesperrt bis Start |
| Kinder: OBS, ffmpeg, Explorer, Browser | ffmpeg/OBS **erben den Admin-Token**, Browser/Dateien über `explorer.exe` (Shell des Nutzers) | | `launch.py` |

## Vertrauensgrenzen

1. **Nutzer-Programme (mittlere Integrität) → erhöhter Fog-Scout-Prozess.** Das zentrale Bedrohungsmodell der Härtungen 1.33.5/1.38.21/1.38.57/1.55.4: Alles im Datenordner, in `HKCU`, in `%TEMP%`, in Umgebungsvariablen und auf `127.0.0.1` ist vom Angreifer kontrollierbar.
2. **Fremde Dateien:** Sicherungs-ZIP, Einstellungs-Export, Kartenbilder, Editor-Projekte, `.inputs.json`, Match-Dateien im Download-Ordner (jede Webseite kann eine `fogscout-matches*.json` ablegen), Aufnahme-/Clip-Indizes im Aufnahmeordner, Steam-Screenshots.
3. **Lokale Gegenstellen:** OBS-WebSocket (`127.0.0.1`, jeder lokale Prozess kann den Port belegen), Discord-Pipe, OAuth-Rückruf `127.0.0.1:27831`.
4. **Externe Dienste:** GitHub (Update), PyPI (start.bat), Anthropic, Spotify, Google/YouTube, AWS GameLift (Ping/DNS).
5. **Lieferkette:** GitHub Actions (`tests.yml`, `build.yml`), gepinnte Actions-SHAs, Hash-gepinnte Wheels.

## Angriffsflächen (geprüft)

- Update: `relupdate.py`, `restart.py`, `app_settings` (Download, Staging, Start), `update.py` (start.bat).
- Admin-Helfer: `hostsedit.py`, `regions.run_job`, `netwatch.py`, `_open_result`.
- Dateiprimitive: `fsops.delete_inside`, `open_plain_for_write`, `write_new`, `write_atomic`, `rel_path`, `is_link`.
- Aufräumen: `recindex.prune*`, `thumbs.prune`, `mapstyle.prune`, `corpus.prune`, `relupdate.clean_update_folder`.
- Import: `backups.inspect/restore`, `official.take_downloads/parse/_match_line`, `history._round_line/_lost_lines`, `inputs.load`, `project.load`.
- Kindprozesse: `launch.py`, `obsrec._start_obs_process`/`obs_exe`, ffmpeg (`clipedit`, Concat-Listen).
- KI: `askclaude.parse`, `editcommands.apply`, Shorts-Texte (als Bild gerendert, kein `drawtext`).
- Lokale IPC: `discordrpc.Ipc.recv`, `spotify.LoginServer`, `obsrec.ObsClient`/`obs_file`.
- CI: `tests.yml`, `build.yml` (Rechte, Trigger, Release-Job).

## Ausgeschlossen / nicht prüfbar hier

- Echte Windows-Semantik (Junctions, Hardlink-Regeln, UAC, DPAPI, `explorer.exe`-Übergabe, Aufgabenplanung) – nur Code-Lesen und POSIX-Nachbau.
- Echtes OBS (Skripte/Plugins im Benutzerprofil) – RS-003 ist im Code belegt, die OBS-Seite der Kette nicht ausgeführt.
- Parser-Lücken in Drittbibliotheken (Pillow, OpenCV, onnxruntime, ffmpeg) – nur die eigenen Grenzen geprüft; `pip-audit` nicht erneut ausgeführt.
- Kein Angriff auf externe Systeme, keine echten Uploads/Updates/hosts-Änderungen.

## Bekannte Einschränkungen dieses Audits

- Zeitlich begrenzt: Schwerpunkt auf Pfaden, die seit den letzten Sicherheitsrunden neu sind oder deren Fixes Varianten zulassen. Viele Module (Overlay, Erkennung, Editor-UI) nur stichprobenartig.
- Die Basislauf-Testsuite lief vollständig (Ergebnis in `03_EXPLOIT_TESTS.md`).
