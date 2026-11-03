# hwpanel

**Sprachen:** [English](README.md) · Deutsch

Überwachung, Taktbegrenzung und Lüfterkurven für AMD-GPU (amdgpu) und CPU (cpufreq/intel_pstate) unter Linux. Kein Übertakten:
Alle Obergrenzen sind die Treiber-Standardwerte, die beim ersten Start des Daemons ermittelt werden.

- `hwpaneld.py`: Daemon (root, systemd). Schreibt nur auf eine feste Whitelist von sysfs-Pfaden.
- `hwpanelctl.py`: CLI-Client.
- `gui/`: Fenster und Tray-Icon (PySide6/QML), gleiche Socket-Schnittstelle wie die CLI.
- Socket: `/run/hwpanel/hwpanel.sock` (JSON pro Zeile), Daten: `/var/lib/hwpanel/`.

Aktuell sind GUI und CLI-Ausgaben auf Deutsch. Eine englische Oberfläche ist geplant.

## Voraussetzungen

- Linux mit systemd (die mitgelieferte Unit nutzt nur Optionen ab systemd 245) und Python ≥ 3.8 für Daemon und CLI. Sie brauchen nur die Python-Standardbibliothek und sysfs.
- GPU: AMD mit dem Kernel-Treiber `amdgpu`. Überwachung, Power-Limit und Lüfter laufen über hwmon (`power1_cap`, `pwm1`, `pwm1_enable`). Die Takt-Obergrenzen brauchen die Overdrive-Schnittstelle (`pp_od_clk_voltage`). Auf manchen Systemen gibt es sie nur mit dem Kernel-Parameter `amdgpu.ppfeaturemask=0xffffffff`. Ohne sie fehlen die Takt-Obergrenzen, Überwachung, Power-Limit und Lüfter sollten weiter funktionieren (ungetestet).
- CPU: cpufreq (`scaling_max_freq`, `scaling_governor`). Energy Performance Preference (EPP) braucht `intel_pstate` oder `amd-pstate` im aktiven Modus, Turbo geht über `intel_pstate/no_turbo` oder `cpufreq/boost`.
- GUI (optional): PySide6 (Qt 6) mit QtQuick. Für das Tray-Icon muss die Desktopumgebung StatusNotifier unterstützen.
- Optional: `dmidecode` (zeigt die RAM-Module an).

## Getestet mit

Bisher nur auf einem System: CachyOS (Arch-basiert), Kernel 6.18 LTS, systemd 262, Python 3.14, PySide6 6.12, KDE Plasma 6 (Wayland), AMD Radeon RX 6750 XT (RDNA 2), Intel Core i7-6700K (`intel_pstate`).
Andere Grafikkarten (z. B. RDNA 3 und neuer), `amd-pstate`, ältere Python- und systemd-Versionen und andere Distributionen sind ungetestet. Berichte über andere Hardware sind willkommen.

## Installation (fish/bash)

```
sudo bash install.sh --disable-lact
```

`--disable-lact` deaktiviert `lactd`, weil beide Programme in dieselben sysfs-Dateien schreiben.
LACT bleibt installiert. Rückgängig: `sudo systemctl disable --now hwpanel` und `sudo systemctl enable --now lactd`.
Entfernen: `sudo bash install.sh --uninstall`.

Beim ersten Start setzt der Daemon die GPU einmal auf Treiberstandard zurück (`r` + `c`) und speichert
die Werte in `/var/lib/hwpanel/defaults.json`. Danach wirken diese Werte als Obergrenze.

## GUI

```
sudo pacman -S --needed pyside6       # einmalig (Arch/CachyOS; sonst das PySide6-Paket deiner Distribution)
hwpanel-gui                           # Fenster + Tray-Icon
hwpanel-gui --minimized               # nur Tray
```

- Seiten: Übersicht (GPU/CPU/RAM live, Temperatur- und Leistungsdiagramm), Verlauf (Temperatur, Leistung, Auslastung inkl. Lüfter-%, Takt über 1 Min bis 1 Std), Profile (anwenden, anlegen, bearbeiten, löschen, "Beim Systemstart anwenden"), Manuell (Reiter "Takt & CPU" und "Lüfter").
- Diagramme und Karten werden ohne Weichzeichner gezeichnet, versteckte Seiten zeichnen nicht mit. Das hält Start und Seitenwechsel flüssig.
- Verlauf: Der Daemon hält die letzte Stunde im Speicher, auch wenn die GUI geschlossen ist. Gestrichelte Linien markieren Profilwechsel und manuelle Änderungen. Mit der Maus über ein Diagramm fahren zeigt die Werte.
- Mit der Maus über eine Einstellung fahren (das "?" neben einer Beschriftung oder eine Option wie ein EPP-Wert) zeigt eine kurze Erklärung.
- Tray: Linksklick öffnet/versteckt das Fenster, das Menü wechselt das Profil. Fenster schließen versteckt es nur, Beenden im Menü oder in der Seitenleiste beendet die GUI.
- Autostart der GUI: Schalter "Beim Login starten" in der Seitenleiste (legt `~/.config/autostart/hwpanel-gui.desktop` an).
- Ohne Tray-Unterstützung der Desktopumgebung (z. B. GNOME ohne AppIndicator-Erweiterung) beendet das Schließen des Fensters die GUI.
- Der Daemon läuft unabhängig von der GUI. Profile und Einstellungen gelten auch bei geschlossener GUI.

## Benutzung

```
hwpanelctl status -w                  # Live-Anzeige
hwpanelctl info                       # Grenzen, Standardwerte, Profile
hwpanelctl gpu --sclk 2300            # GPU-Maximaltakt (MHz)
hwpanelctl gpu --mclk 1000 --power 180
hwpanelctl cpu --max-mhz 3500 --turbo off --epp power
hwpanelctl reset [gpu|cpu|fan|all]    # auf Standard
hwpanelctl fan curve 30:40,50:55,80:90        # eigene Lüfterkurve (°C:%), Sensor edge
hwpanelctl fan curve 40:35,70:70,90:100 --sensor junction
hwpanelctl fan auto                   # Treiberautomatik
hwpanelctl apply Gaming               # Profil anwenden
hwpanelctl apply KI
hwpanelctl autostart KI               # beim Start des Daemons anwenden ('none' = aus)
hwpanelctl save Leise --sclk 1800 --power 120
hwpanelctl save Gaming2 --fan-curve 30:40,50:55,65:70,80:90 --fan-sensor edge
hwpanelctl delete Leise
```

Hinweis zum VRAM-Takt: `--mclk` verwendet den sysfs-Wert (z. B. 1124). LACT zeigt das Doppelte (2248).

## Profile

Ein Profil legt den vollständigen Zustand fest: Alles, was nicht aufgeführt ist, wird auf Standard gesetzt.

- `Standard` (eingebaut): alles zurück auf Standard.
- `Gaming`: GPU und CPU auf Standardtakt, CPU-EPP `performance`.
- `KI`: GPU-Maximaltakt 2300 MHz, Rest Standard.

Profile liegen in `/var/lib/hwpanel/profiles.json`. Nach Suspend/Resume werden die zuletzt gesetzten Werte erneut angewendet.
Die mitgelieferten Profile `Gaming` und `KI` enthalten keine Lüfterkurve (Automatik). Eigene Kurven legst du in der GUI an: Profil bearbeiten, Reiter "Lüfter".

## Lüftersteuerung

- Pro Profil entweder Treiberautomatik (Standard, im Leerlauf meist aus und leise) oder eine eigene Kurve. Ohne Kurve im Profil gilt Automatik. Ein Profil wie "Desktop" ohne Kurve hält die Lüfter im normalen Betrieb leise.
- Kurve: 2 bis 10 Punkte (°C, %), Temperaturen aufsteigend, Prozentwerte nicht fallend, dazwischen linear. Unter dem ersten und über dem letzten Punkt gilt der jeweilige Endwert. Sensor: `edge`, `junction` oder `mem`.
- Im Editor: Punkte ziehen, Doppelklick fügt einen hinzu, Entf löscht den gewählten Punkt, Pfeiltasten verschieben (Umschalt = 5er-Schritte). Die gestrichelte Linie zeigt die aktuelle Temperatur und den dazugehörigen Zielwert.
- Verhalten: Steigt das Ziel, wird sofort geschrieben. Sinkt es, dauert es 5 s und mindestens 2 % Unterschied (verhindert Pendeln).
- Schutz: Die Kurve muss bei 60 °C mindestens 30 % und bei 80 °C mindestens 50 % liefern, sonst wird sie abgelehnt. Ab 100 °C Junction läuft der Lüfter mit 100 % (Aufhebung unter 95 °C), unabhängig von der Kurve.
- Fehlerfall: Sensor nicht lesbar oder Schreibfehler: Automatik, mit Wiederholung. Daemon-Ende, Absturz oder Hänger (systemd-Watchdog, 20 s): Lüfter geht zurück auf Automatik (`ExecStopPost`). Wird `pwm1_enable` von außen zurückgesetzt (z. B. nach Standby), setzt der Daemon die Kurve erneut.
- Die Lüfterkonfiguration wird nicht über einen Daemon-Neustart gespeichert. Nach dem Boot gilt Automatik, bis ein Profil angewendet wird. Für einen festen Start: Schalter "Beim Systemstart anwenden" am Profil oder `hwpanelctl autostart NAME`.
- `lactd` muss deaktiviert bleiben, sonst schreiben beide in `pwm1_enable`/`pwm1`.
- Anpassbar in `/var/lib/hwpanel/config.json` (nach Änderung `sudo systemctl restart hwpanel`): `fan_safety_junction_c` (100), `fan_min_rules` (`[[60, 30], [80, 50]]`), `fan_spindown_s` (5), `fan_threshold_pct` (2).
- 0 % ist im kühlen Bereich erlaubt (Lüfter steht). Die Schutzregeln greifen erst ab 60 °C bzw. 80 °C.

## Grenzen und Verhalten

- Werte über dem Standard werden abgelehnt (GPU-Takt, VRAM-Takt, Power-Limit, CPU-Takt). Spannung wird nie verändert.
- Nach jedem Schreiben liest der Daemon zurück und meldet Abweichungen als Fehler.
- RAM: nur Anzeige.
- Lüfter: nur über Kurve mit Schutzregeln (siehe oben), nie `pwm1_enable=0` (Lüfter aus/Vollgas wird nicht geschrieben).
- Konflikte: `lactd` und `power-profiles-daemon` können dieselben Werte ändern.

## Sicherheit

- Der Daemon läuft als root, aber in einem systemd-Sandkasten (`hwpanel.service`): Dateisystem schreibgeschützt (außer `/sys` und `/var/lib/hwpanel`), kein Zugriff auf `/home`, kein Netzwerk (nur der Unix-Socket), nur die root-Rechte `CAP_CHOWN` und `CAP_DAC_OVERRIDE`, Syscall-Filter `@system-service`. `systemd-analyze security hwpanel.service` bewertet die Unit mit 1.9 (OK).
- Die Unit nutzt nur Optionen ab systemd 245. Macht eine Distribution oder ein Python-Build damit Probleme, lässt sich die Härtung per Drop-in lockern (`sudo systemctl edit hwpanel`, z. B. `SystemCallFilter=` leer setzen).
- `ProtectKernelTunables=yes` darf nicht gesetzt werden: `/sys` wäre dann schreibgeschützt, und der Daemon könnte nichts mehr setzen. `tests/test_service_unit.py` prüft das.
- Zugriff auf den Socket hat die Gruppe `socket_group` aus `config.json`. Wer darin ist, kann Takt, Lüfter und Profile ändern, aber nie über die oben genannten Grenzen hinaus.

## Diagnose

```
sudo python3 /usr/local/lib/hwpanel/hwpaneld.py --probe    # liest nur, schreibt nichts
journalctl -u hwpanel -e
```

Lüfter-Rückfall nach einem Absturz prüfen (erst eine Lüfterkurve setzen, dann den Hauptprozess killen; danach muss `pwm1_enable` 2 sein):

```
hwpanelctl fan curve 30:40,50:55,80:90
sudo systemctl kill --kill-whom=main -s KILL hwpanel
cat /sys/class/drm/card*/device/hwmon/hwmon*/pwm1_enable
```

Ohne `--kill-whom=main` tötet systemd auch den `ExecStopPost`-Prozess, der den Lüfter zurücksetzt. Der Test wäre dann wertlos.

## Tests

```
python3 -m unittest discover -s tests                 # alles (ohne PySide6 werden die GUI-Tests übersprungen)
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_gui_backend tests.test_gui_qml
python3 tests/render_gui.py /tmp/shots                # GUI mit Demo-Daten als PNG rendern
python3 tests/bench_gui.py                            # Zeichenzeiten (Start, Seitenwechsel, Updates) messen
```

## Lizenz

hwpanel steht unter der [GNU General Public License, Version 3 oder (nach deiner Wahl) jeder späteren Version](LICENSE) (GPL-3.0-or-later).
Daemon und CLI brauchen nur die Python-Standardbibliothek. Die GUI nutzt PySide6 (LGPL) als Bibliothek, `dmidecode` wird als eigenes Programm aufgerufen.
