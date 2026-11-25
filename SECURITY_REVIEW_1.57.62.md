# Sicherheits-Review 1.57.62

Auftrag (Saru, 25.11.2026): „tiefe Code-Analyse, Schwachstellen suchen, denk wie ein Angreifer“. Nur lesende
Prüfungen auf dem eigenen PC; keine externen Systeme angegriffen. Dieser Bericht behauptet nicht, das Programm sei
„vollständig sicher“ – er nennt, was geprüft wurde und was offen ist.

## Bedrohungsmodell

Fog Scout läuft als **Administrator** (Aufgabe „Fog Scout“, `RunLevel Highest`; installiert unter
`C:\Program Files\Fog Scout`). Der wichtigste Angreifer ist darum **ein beliebiges Programm im Konto des Nutzers ohne
Adminrechte** (Malware aus einem Download, ein kompromittiertes Spiel-Tool, eine Browser-Erweiterung): Alles, was
Fog Scout aus Orten liest, die so ein Programm beschreiben kann (Datenordner `%LOCALAPPDATA%\FogScout`, Aufnahmeordner,
Download-Ordner, Benutzerumgebung, Benutzer-`PATH`), ist ein möglicher Weg zu Adminrechten. Die Aufgabe startet jeder
Prozess des Nutzers ohne UAC-Abfrage (`schtasks /run`), der Autostart bei jeder Anmeldung.

Daneben: Webseiten (können Dateien in den Download-Ordner legen), lokale Ports (OBS, OAuth-Rückruf), Update-Kette
und GitHub Actions (öffentliches Repo).

## Befunde

### SEC-62-1 – HIGH – OpenCV lädt eine DLL aus dem Benutzer-`PATH` in den Admin-Prozess (behoben)

- **Ort:** jede OpenCV-Operation, die parallel läuft (z. B. `cv2.resize` im Worker); Bibliothek
  `opencv-python-headless==5.0.0.93`.
- **Beleg (reproduziert):** Mit `OPENCV_LOG_LEVEL=DEBUG` zeigt OpenCV beim ersten parallelen Schritt, dass es
  `opencv_core_parallel_onetbb500_64.dll`, `…tbb…` und `…openmp…` erst im eigenen Ordner sucht und dann **per blossem
  Namen** über die normale DLL-Suche, die mit dem `PATH` endet. Eine umbenannte, harmlose System-DLL in einem
  `PATH`-Ordner wurde geladen (`libraryLoad … => OK`). Der Benutzer-`PATH` enthält
  `%LOCALAPPDATA%\Microsoft\WindowsApps` (geprüft: für das Benutzerkonto beschreibbar, ebenso zwei weitere Einträge).
  Die installierte .exe ändert daran nichts: Ihr Bootloader importiert nur `SetDllDirectoryW`, weder er noch
  `python312.dll` ruft `SetDefaultDllDirectories` auf (Importstrings geprüft) – der `PATH` bleibt in der Suche.
  Zusätzlich luden `OPENCV_CORE_PLUGIN_PATH` und `OPENCV_OPENCL_RUNTIME` (Benutzerumgebung, `HKCU\Environment`) eine
  DLL von einem beliebigen Pfad.
- **Auswirkung:** Ein Programm ohne Adminrechte legt eine DLL mit diesem Namen in `WindowsApps` und wartet auf den
  nächsten Start von Fog Scout (Autostart bei Anmeldung) oder startet die Aufgabe selbst → sein Code läuft mit
  Adminrechten (Rechteausweitung / UAC-Umgehung). Der Lauf in der .exe wurde nicht mit einer echten DLL
  nachgestellt; die Aussage für die .exe beruht auf dem Venv-Nachweis plus der Import-Analyse.
- **Ursache:** OpenCVs Plugin-Suche für optionale Parallel-Backends und OpenCL; die Umgebung wurde bisher nur von
  `SSL_CERT_*`, `PYTHON*`, `GIT_*`, `OPENSSL_*` bereinigt.
- **Fix:** `fogscout/__init__.py` (vor jedem `cv2`-Import): alle `OPENCV_*` ausser `OPENCV_LOG_LEVEL` werden entfernt,
  `OPENCV_PARALLEL_PRIORITY_{ONETBB,TBB,OPENMP}=0` (OpenCV versucht kein Plugin mehr; seine eingebauten Threads
  bleiben, die Plugins lagen ohnehin nie vor) und `OPENCV_OPENCL_RUNTIME=disabled` (Fog Scout nutzt kein OpenCL).
- **Prüfstatus:** Test `test_opencv_loads_no_plugin_dll_from_the_path_or_the_environment` – ohne Fix rot, mit Fix grün.

### SEC-62-2 – MEDIUM – andere fehlende DLLs könnten ebenso über den `PATH` kommen (offen, Empfehlung)

- **Ort:** ganzer Admin-Prozess; Ursache wie oben (keine prozessweite Einschränkung der DLL-Suche).
- **Beleg:** Nur für OpenCV nachgewiesen. Ob Qt, onnxruntime oder Windows-Komponenten im Prozess weitere fehlende DLLs
  per Namen suchen, ist **nicht geprüft** (braucht Process Monitor auf dem echten Programm).
- **Fix-Vorschlag:** In der .exe ganz am Anfang `SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS)` plus
  `AddDllDirectory` für `_internal` – dann sucht Windows nie mehr im `PATH`. Risiko: eine Bibliothek, die eine DLL
  über den `PATH` erwartet, bricht; nur zusammen mit dem Windows-CI-Selbsttest der .exe einführen. **Entscheidung
  des Nutzers nötig.**

### SEC-62-3 – MEDIUM – fremde Mediendateien werden mit Adminrechten zerlegt (offen, Architektur)

- **Ort:** ffmpeg (`imageio-ffmpeg==0.6.0` → ffmpeg **7.1**, Build von 2024), Pillow 13.0.0, OpenCV und Qt-Bildformate
  lesen Videos/Bilder aus Orten, die jedes Programm des Nutzers beschreiben kann (Aufnahmeordner, Steam-Screenshots,
  `user_maps/`, Mediathek-Import).
- **Beleg:** Codepfade gelesen. Der automatische Weg (`recindex.settle_parts` alle 60 s) zerlegt MP4/GIF in reinem
  Python ohne ffmpeg; ffmpeg auf fremden Dateien läuft nur nach einem Klick des Nutzers (Übernehmen, Editor,
  Vorschaubilder der Mediathek). Ein konkreter Fehler in diesen Bibliotheksversionen wurde **nicht** nachgewiesen.
- **Auswirkung:** Jeder künftige Speicherfehler in einem dieser Parser wäre eine Rechteausweitung, weil das ganze
  Programm als Admin läuft.
- **Fix-Vorschlag:** Langfristig nur die Teile mit Adminrechten laufen lassen, die sie brauchen (hosts-Datei,
  `RCVALL_IPLEVEL`-Mitschnitt) – z. B. der Hauptprozess ohne Admin, diese zwei als kurze Helfer. Größerer Umbau,
  **Entscheidung des Nutzers nötig.** Kurzfristig: ffmpeg-Version bei jedem imageio-ffmpeg-Release prüfen.

### SEC-62-4 – LOW – Qt-Labels zeigten Text als HTML (behoben)

- **Ort:** `qt_common._label`, `qt_pages.HintLabel`, `qt_layouts._ClickLabel`, NavStatus (`qt_window`), `toast`.
- **Beleg (reproduziert):** Qt rendert einen Text mit Tag automatisch als HTML (`Qt.AutoText`); `<img src="…">` lud
  das Bild vom angegebenen Pfad (geprüft mit lokaler Datei, offscreen). Ein Netzwerkpfad würde Windows eine Freigabe
  ansprechen lassen (nicht getestet). Ein Weg dorthin: Charakternamen aus einer `fogscout-matches.json` im
  Download-Ordner (die auch eine Webseite dort ablegen kann) im Label „Farming-Gegner“ – erst nach Rechtsklick des
  Nutzers. Kein Programmtext nutzt HTML (geprüft).
- **Fix:** alle diese Labels `Qt.PlainText` (wie schon `PlainLabel` für Claude und das Meldungsfenster).
- **Prüfstatus:** Test `test_the_labels_of_the_pages_never_show_html` – ohne Fix rot, mit Fix grün.

## Geprüft, kein Befund

| Bereich | Ergebnis |
|---|---|
| Update-Installation (`restart.staged_setup`) | Kopie in den Admin-Ordner, Hash beim Kopieren, Datei mit `FILE_SHARE_READ` gehalten und erneut gehasht – kein Tausch zwischen Prüfung und Start möglich. |
| Installationsordner | 85 Ordner geprüft: kein Schreibrecht für Benutzer; die Aufgaben zeigen auf `C:\Program Files\Fog Scout\FogScout.exe`. |
| Umgebung des Admin-Prozesses | `launch.harden_start_environment` entfernt `PYTHON*`, `SSL_CERT_*`, `GIT_*`, `OPENSSL_*`, fremde `QT_PLUGIN_PATH`; Kinder bekommen eine bereinigte Umgebung. |
| ctypes-DLLs | nur per Namen aus System-DLLs; Python lädt sie mit `LOAD_LIBRARY_SEARCH_DEFAULT_DIRS` (ohne `PATH`); `nvml.dll` nur absolut aus System32. |
| Löschen | fast überall `fsops.delete_inside` (keine Links/Junctions); die übrigen `os.remove` treffen eigene Dateien oder Downloads mit Kennung. |
| hosts-Helfer | als Admin direkt im Prozess (kein `runas` über `HKCU\Software\Classes`), nur `MANAGED`-Namen. |
| OAuth-Rückruf | nur während der Anmeldung, `state` geprüft, Fehlertext gekürzt/bereinigt. |
| OBS-Antworten | Pfade von OBS nur, wenn im Aufnahmeordner oder frisch geschrieben (`obs_file`), Umzug ohne Links. |
| Log | HTML-escaped (`LogView._row`). |
| GitHub Actions | keine `pull_request_target`, Actions per Commit-SHA, Standardrecht `contents: read`; schreiben darf nur der Release-Job, nur per `workflow_dispatch` auf `main`, ohne Token im Checkout; Eingaben im Skript geprüft. |
| Code-Muster | kein `shell=True`, `eval`, `pickle`, `os.system` im Programm. |

## Ausgeführte Befehle (Auszug)

- OpenCV-Nachweis: Python aus `.venv` mit `OPENCV_LOG_LEVEL=DEBUG`, Plugin-Variablen bzw. umbenannter
  `version.dll` in einem Test-`PATH` (nur für den Testprozess, nichts im System geändert).
- ACLs: `Get-Acl` auf Installationsordner und Benutzer-`PATH`; Aufgaben: `Get-ScheduledTask` (lesen).
- Tests: `pyflakes fogscout tests tools` (0 Meldungen); `pytest` auf `test_preview.py`, `test_plain_labels.py`,
  `test_qt.py`, `test_i18n.py`, `test_whatsnew.py`, `test_repo_hygiene.py` (211 bestanden, 2 übersprungen),
  `test_history.py`, `test_palette_app.py`, `test_frozen.py` (2 Fehler, beide auch ohne diese Änderung: installierte
  App auf diesem PC bzw. fehlendes Symlink-Recht). Die volle Suite und `test_windows.py` laufen nur in CI
  (öffnen Fenster).
