#!/usr/bin/env python3
"""hwpanel-gui: Fenster und Tray-Icon für hwpaneld."""

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # hwpanel_i18n.py und locales/ liegen im Hauptordner
from backend import SOCKET_PATH, Backend, DaemonClient  # noqa: E402
from language import CONFIG_FILE, Language  # noqa: E402

HERE = Path(__file__).resolve().parent
QML_MAIN = HERE / "qml" / "Main.qml"
ICON_SVG = HERE / "hwpanel.svg"


def fallback_icon():
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QRadialGradient(32, 32, 30)
    g.setColorAt(0, QColor("#ff5a68"))
    g.setColorAt(1, QColor("#7a0b16"))
    p.setBrush(g)
    p.setPen(QColor("#ff2a3d"))
    p.drawEllipse(4, 4, 56, 56)
    p.end()
    return QIcon(pm)


def load_icon():
    icon = QIcon(str(ICON_SVG)) if ICON_SVG.exists() else QIcon()
    return icon if not icon.isNull() else fallback_icon()


class Tray:
    def __init__(self, window, backend, icon):
        self.window, self.backend = window, backend
        self.tray = QSystemTrayIcon(icon)
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self._sig = None
        backend.infoChanged.connect(self.rebuild)
        backend.statusChanged.connect(self.refresh)
        backend.connectedChanged.connect(self.refresh)
        self.rebuild()
        self.tray.show()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle()

    def toggle(self):
        if self.window.isVisible() and self.window.isActive():
            self.window.hide()
        else:
            self.show_window()

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def rebuild(self):
        self._sig = (tuple(self.backend.profileNames), self.backend.activeProfile)
        self.menu.clear()
        group = QActionGroup(self.menu)
        group.setExclusive(True)
        for name in self.backend.profileNames:
            act = QAction(name, self.menu)
            act.setCheckable(True)
            act.setChecked(name == self.backend.activeProfile)
            act.triggered.connect(lambda _=False, n=name: self.backend.applyProfile(n))
            group.addAction(act)
            self.menu.addAction(act)
        self.menu.addSeparator()
        self.menu.addAction("Fenster öffnen", self.show_window)
        self.menu.addAction("Beenden", self.backend.quit)
        self.refresh()

    def refresh(self):
        sig = (tuple(self.backend.profileNames), self.backend.activeProfile)
        if sig != self._sig:
            self.rebuild()
            return
        st = self.backend.status or {}
        if not self.backend.connected:
            self.tray.setToolTip("hwpanel: Daemon nicht erreichbar")
            return
        g, c = st.get("gpu") or {}, st.get("cpu") or {}

        def f(v, unit):
            return "–" if v is None else f"{v:g}{unit}"
        self.tray.setToolTip(
            f"hwpanel · Profil: {self.backend.activeProfile or 'manuell'}\n"
            f"GPU {f(g.get('temp_edge_c'), ' °C')} · {f(g.get('power_w'), ' W')} · Lüfter {f(g.get('fan_pct'), ' %')}\n"
            f"CPU {f(c.get('temp_c'), ' °C')} · {f(c.get('power_w'), ' W')}")


def notify_running_instance(name):
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description="hwpanel GUI")
    ap.add_argument("--minimized", action="store_true", help="nur im Tray starten")
    ap.add_argument("--page", type=int, default=0, help="Startseite (0 Übersicht, 1 Verlauf, 2 Profile, 3 Manuell)")
    ap.add_argument("--socket", default=SOCKET_PATH)
    args, qt_args = ap.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("hwpanel")
    app.setDesktopFileName("hwpanel")
    app.setQuitOnLastWindowClosed(False)

    instance = f"hwpanel-gui-{os.getuid()}"
    if notify_running_instance(instance):
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(instance)
    server.listen(instance)

    icon = load_icon()
    app.setWindowIcon(icon)
    backend = Backend(DaemonClient(args.socket), start_page=args.page, minimized=False,
                      language=Language(config_path=CONFIG_FILE))
    available = QSystemTrayIcon.isSystemTrayAvailable()
    app.setQuitOnLastWindowClosed(not available)  # ohne Tray beendet das Schließen des Fensters das Programm
    backend.trayAvailable = available
    backend._minimized = bool(args.minimized and available)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    window.setIcon(icon)

    tray = Tray(window, backend, icon) if available else None
    if tray:
        server.newConnection.connect(lambda: (server.nextPendingConnection(), tray.show_window()))
    else:
        server.newConnection.connect(lambda: (server.nextPendingConnection(), window.show(), window.raise_()))

    app.aboutToQuit.connect(backend.shutdown)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
