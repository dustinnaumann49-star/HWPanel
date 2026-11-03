# hwpanel

**Languages:** English · [Deutsch](README.de.md)

Monitoring, clock limits and fan curves for AMD GPUs (amdgpu) and CPUs (cpufreq/intel_pstate) on Linux. No overclocking:
all upper limits are the driver defaults, read when the daemon starts for the first time.

- `hwpaneld.py`: daemon (root, systemd). Writes only to a fixed whitelist of sysfs paths.
- `hwpanelctl.py`: command-line client.
- `gui/`: window and tray icon (PySide6/QML), same socket interface as the CLI.
- Socket: `/run/hwpanel/hwpanel.sock` (one JSON object per line), data: `/var/lib/hwpanel/`.

The GUI is available in English and German and follows the system language. The command-line output and the daemon's messages (errors, history events) are not translated yet and appear in German.

## Requirements

- Linux with systemd (the shipped unit only uses options available since systemd 245) and Python ≥ 3.8 for the daemon and the CLI. They need only the Python standard library and sysfs.
- GPU: AMD with the `amdgpu` kernel driver. Monitoring, power limit and fan control go through hwmon (`power1_cap`, `pwm1`, `pwm1_enable`). The clock limits need the Overdrive interface (`pp_od_clk_voltage`). On some systems it only exists with the kernel parameter `amdgpu.ppfeaturemask=0xffffffff`. Without it the clock limits are unavailable; monitoring, power limit and fan control should keep working (untested).
- CPU: cpufreq (`scaling_max_freq`, `scaling_governor`). Energy Performance Preference (EPP) needs `intel_pstate` or `amd-pstate` in active mode, turbo is switched via `intel_pstate/no_turbo` or `cpufreq/boost`.
- GUI (optional): PySide6 (Qt 6) with QtQuick. For the tray icon the desktop environment must support StatusNotifier.
- Optional: `dmidecode` (shows the RAM modules).

## Tested with

So far on one system only: CachyOS (Arch-based), kernel 6.18 LTS, systemd 262, Python 3.14, PySide6 6.12, KDE Plasma 6 (Wayland), AMD Radeon RX 6750 XT (RDNA 2), Intel Core i7-6700K (`intel_pstate`).
Other graphics cards (e.g. RDNA 3 and newer), `amd-pstate`, older Python and systemd versions and other distributions are untested. Reports from other hardware are welcome.

## Installation (fish/bash)

```
sudo bash install.sh --disable-lact
```

`--disable-lact` disables `lactd`, because both programs write to the same sysfs files.
LACT stays installed. To undo: `sudo systemctl disable --now hwpanel` and `sudo systemctl enable --now lactd`.
To remove: `sudo bash install.sh --uninstall`.

On the first start the daemon resets the GPU to the driver defaults once (`r` + `c`) and stores the values in
`/var/lib/hwpanel/defaults.json`. From then on these values act as the upper limit.

## GUI

```
sudo pacman -S --needed pyside6       # once (Arch/CachyOS; otherwise the PySide6 package of your distribution)
hwpanel-gui                           # window + tray icon
hwpanel-gui --minimized               # tray only
```

- Pages: Overview (live GPU/CPU/RAM, temperature and power chart), History (temperature, power, load incl. fan %, clock over 1 min to 1 h), Profiles (apply, create, edit, delete, "Apply at system start"), Manual (tabs "Clocks & CPU" and "Fan").
- Charts and cards are drawn without blur, and hidden pages do not draw. This keeps startup and page switches smooth.
- History: the daemon keeps the last hour in memory, even when the GUI is closed. Dashed lines mark profile changes and manual changes. Hovering over a chart shows the values.
- Hovering over a setting (the "?" next to a label, or an option such as an EPP value) shows a short explanation.
- Language: a German system shows German, everything else English. The buttons *Auto / DE / EN* at the bottom of the sidebar switch it immediately; the choice is saved in `~/.config/hwpanel/gui.json`. For the CLI use `--lang CODE` or `HWPANEL_LANG`.
- Tray: a left click opens/hides the window, the menu switches the profile. Closing the window only hides it; "Quit" in the menu or in the sidebar quits the GUI.
- GUI autostart: the switch "Start at login" in the sidebar creates `~/.config/autostart/hwpanel-gui.desktop`.
- Without tray support in the desktop environment (e.g. GNOME without the AppIndicator extension) closing the window quits the GUI.
- The daemon runs independently of the GUI. Profiles and settings apply even when the GUI is closed.

## Usage

```
hwpanelctl status -w                  # live view
hwpanelctl info                       # limits, defaults, profiles
hwpanelctl gpu --sclk 2300            # GPU maximum clock (MHz)
hwpanelctl gpu --mclk 1000 --power 180
hwpanelctl cpu --max-mhz 3500 --turbo off --epp power
hwpanelctl reset [gpu|cpu|fan|all]    # back to defaults
hwpanelctl fan curve 30:40,50:55,80:90        # custom fan curve (°C:%), sensor edge
hwpanelctl fan curve 40:35,70:70,90:100 --sensor junction
hwpanelctl fan auto                   # driver automatic
hwpanelctl apply Gaming               # apply a profile
hwpanelctl apply KI
hwpanelctl autostart KI               # apply when the daemon starts ('none' = off)
hwpanelctl save Leise --sclk 1800 --power 120
hwpanelctl save Gaming2 --fan-curve 30:40,50:55,65:70,80:90 --fan-sensor edge
hwpanelctl delete Leise
```

Note on the VRAM clock: `--mclk` takes the sysfs value (e.g. 1124). LACT shows double (2248).

## Profiles

A profile defines the complete state: everything that is not listed is set to the default.

- `Standard` (built in; the English GUI shows it as "Default"): everything back to default.
- `Gaming`: GPU and CPU at default clocks, CPU EPP `performance`.
- `KI` (German for "AI"): GPU maximum clock 2300 MHz, the rest default.

Profiles are stored in `/var/lib/hwpanel/profiles.json`. After suspend/resume the last applied values are applied again.
The shipped profiles `Gaming` and `KI` contain no fan curve (automatic). Create your own curves in the GUI: edit a profile, tab "Fan".

## Fan control

- Per profile either the driver automatic (default, usually off and quiet when idle) or a custom curve. Without a curve in the profile the automatic applies. A profile like "Desktop" without a curve keeps the fans quiet in normal use.
- Curve: 2 to 10 points (°C, %), temperatures ascending, percentages non-decreasing, linear in between. Below the first and above the last point the respective end value applies. Sensor: `edge`, `junction` or `mem`.
- In the editor: drag points, double-click adds one, Del removes the selected point, arrow keys move it (Shift = steps of 5). The dashed line shows the current temperature and the matching target value.
- Behavior: when the target rises it is written immediately. When it falls, it takes 5 s and a difference of at least 2 % (prevents hunting).
- Protection: the curve must deliver at least 30 % at 60 °C and at least 50 % at 80 °C, otherwise it is rejected. From 100 °C junction the fan runs at 100 % (released below 95 °C), regardless of the curve.
- On failure: if the sensor cannot be read or a write fails, the fan goes to automatic, with retry. Daemon exit, crash or hang (systemd watchdog, 20 s): the fan returns to automatic (`ExecStopPost`). If `pwm1_enable` is reset from outside (e.g. after standby), the daemon sets the curve again.
- The fan configuration is not kept across a daemon restart. After boot the fan is on automatic until a profile is applied. For a fixed start use the switch "Apply at system start" on the profile or `hwpanelctl autostart NAME`.
- `lactd` must stay disabled, otherwise both write to `pwm1_enable`/`pwm1`.
- Adjustable in `/var/lib/hwpanel/config.json` (after a change: `sudo systemctl restart hwpanel`): `fan_safety_junction_c` (100), `fan_min_rules` (`[[60, 30], [80, 50]]`), `fan_spindown_s` (5), `fan_threshold_pct` (2).
- 0 % is allowed in the cool range (the fan stops). The protection rules only apply from 60 °C and 80 °C.

## Limits and behavior

- Values above the default are rejected (GPU clock, VRAM clock, power limit, CPU clock). The voltage is never changed.
- After every write the daemon reads the value back and reports deviations as errors.
- RAM: display only.
- Fan: only via a curve with protection rules (see above), never `pwm1_enable=0` (the fan-off/full-speed mode is never written).
- Conflicts: `lactd` and `power-profiles-daemon` can change the same values.

## Security

- The daemon runs as root, but inside a systemd sandbox (`hwpanel.service`): read-only file system (except `/sys` and `/var/lib/hwpanel`), no access to `/home`, no network (only the Unix socket), only the root capabilities `CAP_CHOWN` and `CAP_DAC_OVERRIDE`, syscall filter `@system-service`. `systemd-analyze security hwpanel.service` rates the unit 1.9 (OK).
- The unit only uses options available since systemd 245. If a distribution or a Python build has problems with it, the hardening can be relaxed with a drop-in (`sudo systemctl edit hwpanel`, e.g. set `SystemCallFilter=` to empty).
- Do not set `ProtectKernelTunables=yes`: `/sys` would become read-only and the daemon could no longer set anything. `tests/test_service_unit.py` checks this.
- Access to the socket is granted to the group `socket_group` from `config.json`. Members can change clocks, fan and profiles, but never beyond the limits above.

## Diagnostics

```
sudo python3 /usr/local/lib/hwpanel/hwpaneld.py --probe    # read-only, writes nothing
journalctl -u hwpanel -e
```

To check the fan fallback after a crash (set a fan curve first, then kill the main process; afterwards `pwm1_enable` must be 2):

```
hwpanelctl fan curve 30:40,50:55,80:90
sudo systemctl kill --kill-whom=main -s KILL hwpanel
cat /sys/class/drm/card*/device/hwmon/hwmon*/pwm1_enable
```

Without `--kill-whom=main` systemd also kills the `ExecStopPost` process that resets the fan, which makes the test worthless.

## Tests

```
python3 -m unittest discover -s tests                 # everything (without PySide6 the GUI tests are skipped)
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_gui_backend tests.test_gui_qml
python3 tests/render_gui.py /tmp/shots                # render the GUI with demo data as PNG
python3 tests/bench_gui.py                            # measure drawing times (startup, page switches, updates)
```

## Translations

The source texts are English. Each language is a plain JSON file `locales/<code>.json` that maps the English text to its translation; the key `_name` is the language's own name. There is no build step: add a file and the language appears in the GUI. Missing entries fall back to English. `tests/test_i18n.py` checks that every text in the source code is translated and that placeholders and markup match.

## License

hwpanel is released under the [GNU General Public License, version 3 or (at your option) any later version](LICENSE) (GPL-3.0-or-later).
The daemon and the CLI need only the Python standard library. The GUI uses PySide6 (LGPL) as a library; `dmidecode` is called as a separate program.
