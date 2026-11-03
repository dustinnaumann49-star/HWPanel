#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle

# Installs hwpaneld (daemon), hwpanelctl (CLI) and hwpanel-gui (window + tray).
#   sudo ./install.sh                  install
#   sudo ./install.sh --disable-lact   install and disable lactd
#   sudo ./install.sh --uninstall      remove (data in /var/lib/hwpanel stays)
set -euo pipefail
cd "$(dirname "$0")"

# Language of the messages: HWPANEL_LANG, otherwise the system language (same order of precedence as in hwpanel_i18n.py).
# German and English exist; everything else (and C/POSIX) gives English.
msg_lang=en
pick="${HWPANEL_LANG:-auto}"
if [[ "${pick,,}" == auto ]]; then
    locale_name="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
    case "$locale_name" in
        ""|C|C.*|POSIX|POSIX.*) candidates="" ;;
        *) candidates="${LANGUAGE:-}:$locale_name" ;;
    esac
    for part in ${candidates//:/ }; do
        case "${part,,}" in
            de|de_*|de.*|de@*) msg_lang=de; break ;;
            en|en_*|en.*|en@*) break ;;
        esac
    done
else
    case "${pick,,}" in de|de_*|de.*|de@*) msg_lang=de ;; esac
fi

# say "English text" "German text"
say() { if [[ $msg_lang == de ]]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
sayerr() { say "$@" >&2; }

LIB=/usr/local/lib/hwpanel
BIN=/usr/local/bin/hwpanelctl
GUI_BIN=/usr/local/bin/hwpanel-gui
DESKTOP=/usr/share/applications/hwpanel.desktop
ICON=/usr/share/icons/hicolor/scalable/apps/hwpanel.svg
UNIT=/etc/systemd/system/hwpanel.service
DATA=/var/lib/hwpanel

usage() {
    say "Usage: sudo ./install.sh [--disable-lact | --uninstall]" "Aufruf: sudo ./install.sh [--disable-lact | --uninstall]"
    say "  (no option)       install hwpanel (daemon, command line, GUI)" "  (ohne Option)     hwpanel installieren (Daemon, Kommandozeile, GUI)"
    say "  --disable-lact    install and disable lactd (both write to the same sysfs files)" "  --disable-lact    installieren und lactd deaktivieren (beide schreiben in dieselben sysfs-Dateien)"
    say "  --uninstall       remove hwpanel (data in $DATA stays)" "  --uninstall       hwpanel entfernen (Daten in $DATA bleiben)"
    say "  -h, --help        show this help" "  -h, --help        diese Hilfe anzeigen"
    say "The messages follow the system language; HWPANEL_LANG=de or en overrides it." "Die Meldungen folgen der Systemsprache; HWPANEL_LANG=de oder en überschreibt sie."
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac

if [[ $EUID -ne 0 ]]; then
    sayerr "Please run with sudo: sudo ./install.sh" "Bitte mit sudo ausführen: sudo ./install.sh"
    exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
    systemctl disable --now hwpanel.service 2>/dev/null || true
    rm -f "$UNIT" "$BIN" "$GUI_BIN" "$DESKTOP" "$ICON"
    rm -rf "$LIB"
    systemctl daemon-reload
    say "Removed. Settings and profiles in $DATA are kept." "Entfernt. Einstellungen und Profile in $DATA bleiben erhalten."
    exit 0
fi

if ! command -v python3 >/dev/null; then
    sayerr "python3 is missing (sudo pacman -S python)" "python3 fehlt (sudo pacman -S python)"
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))'; then
    sayerr "Python >= 3.8 is required" "Python >= 3.8 nötig"
    exit 1
fi

install -d -m 755 "$LIB" "$DATA"
install -m 755 hwpaneld.py "$LIB/hwpaneld.py"
install -m 755 hwpanelctl.py "$LIB/hwpanelctl.py"
install -m 644 hwpanel_i18n.py "$LIB/hwpanel_i18n.py"
rm -rf "$LIB/locales"
cp -r locales "$LIB/locales"
chmod -R a+rX "$LIB/locales"
# Through the link Python finds hwpanel_i18n.py next to the real script (also replaces an older, single file)
ln -sf "$LIB/hwpanelctl.py" "$BIN"
install -m 644 hwpanel.service "$UNIT"
[[ -f "$DATA/profiles.json" ]] || install -m 644 profiles.json "$DATA/profiles.json"

# GUI (window + tray icon)
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
Comment=GPU/CPU monitoring and clock limits
Comment[de]=GPU/CPU-Überwachung und Taktbegrenzung
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
        say "NOTE: PySide6 is missing, the GUI only starts after:  sudo pacman -S --needed pyside6  (Arch/CachyOS; otherwise your distribution's PySide6 package)" "HINWEIS: PySide6 fehlt, die GUI startet erst danach:  sudo pacman -S --needed pyside6  (Arch/CachyOS; sonst das PySide6-Paket deiner Distribution)"
    fi
fi

# Socket group: primary group of the calling user, so that hwpanelctl and the GUI run without sudo
if [[ ! -f "$DATA/config.json" ]]; then
    GROUP_NAME=root
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
        GROUP_NAME=$(id -gn "$SUDO_USER")
    fi
    printf '{"autostart_profile": null, "socket_group": "%s", "gpu_card": null}\n' "$GROUP_NAME" > "$DATA/config.json"
fi

# lactd writes to the same sysfs files and would overwrite the values
if systemctl is-enabled --quiet lactd.service 2>/dev/null || systemctl is-active --quiet lactd.service 2>/dev/null; then
    if [[ "${1:-}" == "--disable-lact" ]]; then
        systemctl disable --now lactd.service
        say "lactd disabled." "lactd deaktiviert."
    else
        systemctl daemon-reload
        echo
        say "WARNING: lactd is active or enabled. hwpanel was installed but NOT started." "WARNUNG: lactd ist aktiv oder aktiviert. hwpanel wurde installiert, aber NICHT gestartet."
        say "To switch over (LACT stays installed):  sudo ./install.sh --disable-lact" "Zum Umschalten (LACT bleibt installiert):  sudo ./install.sh --disable-lact"
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
say "Installed. Start the GUI with: hwpanel-gui" "Installiert. GUI starten mit: hwpanel-gui"
echo "Test:"
if ! "$BIN" status; then
    sayerr "Daemon is not responding: journalctl -u hwpanel -e" "Daemon antwortet nicht: journalctl -u hwpanel -e"
    exit 1
fi
echo
say "Note: if power-profiles-daemon is active, it can also change the CPU EPP/governor." "Hinweis: Wenn power-profiles-daemon aktiv ist, kann es CPU-EPP/Governor ebenfalls ändern."
