#!/usr/bin/env bash
# Installiert hwpaneld (Daemon), hwpanelctl (CLI) und hwpanel-gui (Fenster + Tray).
#   sudo ./install.sh                  installieren
#   sudo ./install.sh --disable-lact   installieren und lactd deaktivieren
#   sudo ./install.sh --uninstall      entfernen (Daten in /var/lib/hwpanel bleiben)
set -euo pipefail
cd "$(dirname "$0")"

LIB=/usr/local/lib/hwpanel
BIN=/usr/local/bin/hwpanelctl
GUI_BIN=/usr/local/bin/hwpanel-gui
DESKTOP=/usr/share/applications/hwpanel.desktop
ICON=/usr/share/icons/hicolor/scalable/apps/hwpanel.svg
UNIT=/etc/systemd/system/hwpanel.service
DATA=/var/lib/hwpanel

if [[ $EUID -ne 0 ]]; then
    echo "Bitte mit sudo ausführen: sudo ./install.sh" >&2
    exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
    systemctl disable --now hwpanel.service 2>/dev/null || true
    rm -f "$UNIT" "$BIN" "$GUI_BIN" "$DESKTOP" "$ICON"
    rm -rf "$LIB"
    systemctl daemon-reload
    echo "Entfernt. Einstellungen und Profile in $DATA bleiben erhalten."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 fehlt (sudo pacman -S python)" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "Python >= 3.8 nötig" >&2; exit 1; }

install -d -m 755 "$LIB" "$DATA"
install -m 755 hwpaneld.py "$LIB/hwpaneld.py"
install -m 755 hwpanelctl.py "$BIN"
install -m 644 hwpanel.service "$UNIT"
[[ -f "$DATA/profiles.json" ]] || install -m 644 profiles.json "$DATA/profiles.json"

# GUI (Fenster + Tray-Icon)
if [[ -d gui ]]; then
    rm -rf "$LIB/gui"
    cp -r gui "$LIB/gui"
    find "$LIB/gui" -name __pycache__ -type d -prune -exec rm -rf {} +
    chmod -R a+rX "$LIB/gui"
    printf '#!/bin/sh\nexec python3 %s/gui/hwpanel_gui.py "$@"\n' "$LIB" > "$GUI_BIN"
    chmod 755 "$GUI_BIN"
    install -D -m 644 gui/hwpanel.svg "$ICON"
    cat > "$DESKTOP" <<'DESKTOP_EOF'
[Desktop Entry]
Type=Application
Name=hwpanel
Comment=GPU/CPU-Überwachung und Taktbegrenzung
Exec=hwpanel-gui
Icon=hwpanel
Terminal=false
Categories=System;Monitor;
DESKTOP_EOF
    chmod 644 "$DESKTOP"
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
    fi
    if ! python3 -c 'import PySide6.QtQuick, PySide6.QtWidgets' 2>/dev/null; then
        echo
        echo "HINWEIS: PySide6 fehlt, die GUI startet erst danach:  sudo pacman -S --needed pyside6"
    fi
fi

# Socket-Gruppe: primäre Gruppe des aufrufenden Benutzers, damit hwpanelctl und GUI ohne sudo laufen
if [[ ! -f "$DATA/config.json" ]]; then
    GROUP_NAME=root
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
        GROUP_NAME=$(id -gn "$SUDO_USER")
    fi
    printf '{"autostart_profile": null, "socket_group": "%s", "gpu_card": null}\n' "$GROUP_NAME" > "$DATA/config.json"
fi

# lactd schreibt in dieselben sysfs-Dateien und würde die Werte überschreiben
if systemctl is-enabled --quiet lactd.service 2>/dev/null || systemctl is-active --quiet lactd.service 2>/dev/null; then
    if [[ "${1:-}" == "--disable-lact" ]]; then
        systemctl disable --now lactd.service
        echo "lactd deaktiviert."
    else
        systemctl daemon-reload
        echo
        echo "WARNUNG: lactd ist aktiv oder aktiviert. hwpanel wurde installiert, aber NICHT gestartet."
        echo "Zum Umschalten (LACT bleibt installiert):  sudo ./install.sh --disable-lact"
        exit 0
    fi
fi

systemctl daemon-reload
systemctl enable hwpanel.service
systemctl restart hwpanel.service

for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -S /run/hwpanel/hwpanel.sock ]] && break
    sleep 0.5
done

echo
echo "Installiert. GUI starten mit: hwpanel-gui"
echo "Test:"
"$BIN" status || { echo "Daemon antwortet nicht: journalctl -u hwpanel -e" >&2; exit 1; }
echo
echo "Hinweis: Wenn power-profiles-daemon aktiv ist, kann es CPU-EPP/Governor ebenfalls ändern."
