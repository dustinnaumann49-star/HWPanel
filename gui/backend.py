"""Backend der hwpanel-GUI: Daemon-Client im Hintergrundthread und Datenaufbereitung für QML."""

import collections
import json
import math
import os
import queue
import re
import socket
import time
from pathlib import Path

from PySide6.QtCore import Property, QCoreApplication, QObject, QThread, Signal, Slot

from language import Language

SOCKET_PATH = "/run/hwpanel/hwpanel.sock"
KEYS = ("g_edge", "g_junc", "g_mem", "g_pow", "g_busy", "g_clk", "g_fan", "g_fanp",
        "c_temp", "c_pow", "c_load", "c_clk")
MAX_POINTS = 480
WINDOWS = (60, 300, 900, 3600)
PROFILE_NAME = re.compile(r"\w[\w .\-]{0,31}")   # wie HW._check_name im Daemon
AUTOSTART_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "hwpanel-gui.desktop"
AUTOSTART_TEXT = """[Desktop Entry]
Type=Application
Name=hwpanel
Comment=GPU/CPU-Überwachung und Taktbegrenzung
Exec=hwpanel-gui --minimized
Icon=hwpanel
Terminal=false
X-GNOME-Autostart-enabled=true
"""


class DaemonClient:
    """Blockierender Client, eine Verbindung pro Aufruf."""

    def __init__(self, path=SOCKET_PATH):
        self.path = path

    def call(self, req):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10)
        try:
            s.connect(self.path)
            s.sendall((json.dumps(req) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(1 << 20)
                if not chunk:
                    break
                buf += chunk
        finally:
            s.close()
        if not buf:
            raise ConnectionError("Keine Antwort vom Daemon")
        return json.loads(buf)


class Worker(QThread):
    """Fragt den Daemon jede Sekunde ab und führt Befehle aus der Warteschlange aus."""

    status = Signal(object)
    info = Signal(object)
    history = Signal(object)
    failed = Signal(str)
    result = Signal(str, object)

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.q = queue.Queue()
        self._stop = False
        self._since = None
        self._need_info = True

    def submit(self, label, req, then=None):
        """then(resp) liefert Folgebefehle [(Text, Anfrage), ...], die erst nach der Antwort laufen."""
        self.q.put((label, req, then))

    def stop(self):
        self._stop = True
        self.q.put(None)

    def _poll(self):
        if self._need_info:
            info = self.client.call({"cmd": "info"})
            if not info.get("ok"):
                raise ValueError(info.get("error", "info fehlgeschlagen"))
            self.info.emit(info)
            self._need_info = False
        self.status.emit(self.client.call({"cmd": "status"}))
        req = {"cmd": "history"}
        if self._since is not None:
            req["since"] = self._since
        h = self.client.call(req)
        if h.get("ok"):
            if h["samples"]:
                self._since = h["samples"][-1]["t"]
            self.history.emit(h)

    def run(self):
        last = 0.0
        while not self._stop:
            wait = max(0.0, last + 1.0 - time.monotonic())
            try:
                item = self.q.get(timeout=wait)
            except queue.Empty:
                item = "poll"
            if item is None:
                break
            try:
                if item == "poll":
                    self._poll()
                    last = time.monotonic()
                else:
                    todo = collections.deque([item])
                    while todo:
                        label, req, then = todo.popleft()
                        try:
                            resp = self.client.call(req)
                        except (OSError, ValueError) as e:
                            # ohne Meldung sähe es aus, als wäre der Klick wirkungslos gewesen
                            self.result.emit(label, {"error": f"Daemon antwortet nicht ({e}). "
                                                              "Der Befehl wurde evtl. nicht ausgeführt."})
                            raise
                        self.result.emit(label, resp)
                        if then:
                            todo.extend((lb, rq, None) for lb, rq in then(resp))
                    self._need_info = True
                    self._poll()
            except (OSError, ValueError) as e:
                self._need_info = True
                self.failed.emit(str(e))
                last = time.monotonic()


def _deep(v):
    """QML liefert Zahlen als float: ganzzahlige Werte (auch in Listen) in int umwandeln."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, (list, tuple)):
        return [_deep(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _deep(x) for k, x in v.items()}
    return v


def _clean(d):
    return {str(k): _deep(v) for k, v in (d or {}).items()}


class Backend(QObject):
    statusChanged = Signal()
    infoChanged = Signal()
    historyChanged = Signal()
    connectedChanged = Signal()
    windowChanged = Signal()
    autostartChanged = Signal()
    trayChanged = Signal()
    toast = Signal(str, bool)
    showRequested = Signal()

    def __init__(self, client, start_page=0, minimized=False, parent=None, language=None):
        super().__init__(parent)
        self._language = language if language is not None else Language()
        self._language.setParent(self)
        self._status, self._info = {}, {}
        self._view = {"t": [], "events": []}
        self._connected = False
        self._window = 300
        self._tray = False
        self._start_page = start_page
        self._minimized = minimized
        self._samples = collections.deque(maxlen=4000)
        self._events = []
        self._event_keys = set()
        self._worker = Worker(client)
        self._worker.status.connect(self._on_status)
        self._worker.info.connect(self._on_info)
        self._worker.history.connect(self._on_history)
        self._worker.failed.connect(self._on_failed)
        self._worker.result.connect(self._on_result)
        self._worker.start()

    def shutdown(self):
        self._worker.stop()
        self._worker.wait(3000)
        self._language.close()

    # ---- Daten vom Worker

    def _set_connected(self, v):
        if v != self._connected:
            self._connected = v
            self.connectedChanged.emit()

    @Slot(object)
    def _on_status(self, st):
        self._status = st
        self._set_connected(True)
        self.statusChanged.emit()

    @Slot(object)
    def _on_info(self, info):
        self._info = info
        self.infoChanged.emit()

    @Slot(str)
    def _on_failed(self, msg):
        self._set_connected(False)

    @Slot(object)
    def _on_history(self, h):
        self._samples.extend(h.get("samples", []))
        for e in h.get("events", []):
            key = (e["t"], e["text"])
            if key not in self._event_keys:
                self._event_keys.add(key)
                self._events.append(e)
        self._events = self._events[-300:]
        self._rebuild_view()

    @Slot(str, object)
    def _on_result(self, label, resp):
        if resp.get("error"):
            self.toast.emit(resp["error"], True)
        elif resp.get("errors"):
            self.toast.emit("; ".join(resp["errors"]), True)
        elif label:   # Folgebefehle ohne Text (z. B. Aufräumen beim Umbenennen) melden nur Fehler
            notes = resp.get("notes") or []
            self.toast.emit(label + (" (" + "; ".join(notes) + ")" if notes else ""), False)

    def _rebuild_view(self):
        samples = list(self._samples)[-(self._window + 2):]
        view = {"t": [], "events": []}
        for k in KEYS:
            view[k] = []
        if samples:
            now = samples[-1]["t"]
            samples = [s for s in samples if s["t"] >= now - self._window]
            step = max(1, math.ceil(len(samples) / MAX_POINTS))
            for i in range(0, len(samples), step):
                chunk = samples[i:i + step]
                view["t"].append(chunk[-1]["t"])
                for k in KEYS:
                    vals = [s.get(k) for s in chunk if s.get(k) is not None]
                    view[k].append(max(vals) if vals else None)
            view["events"] = [e for e in self._events if now - self._window <= e["t"] <= now]
        self._view = view
        self.historyChanged.emit()

    # ---- Eigenschaften für QML

    @Property(QObject, constant=True)
    def language(self):
        return self._language

    @Property("QVariant", notify=statusChanged)
    def status(self):
        return self._status

    @Property("QVariant", notify=infoChanged)
    def info(self):
        return self._info

    @Property("QVariant", notify=historyChanged)
    def history(self):
        return self._view

    @Property(bool, notify=connectedChanged)
    def connected(self):
        return self._connected

    @Property(int, notify=windowChanged)
    def historyWindow(self):
        return self._window

    @Property(str, notify=statusChanged)
    def activeProfile(self):
        return self._status.get("active_profile") or ""

    @Property(str, notify=infoChanged)
    def startupProfile(self):
        return self._info.get("autostart_profile") or ""

    @Property("QStringList", notify=infoChanged)
    def profileNames(self):
        names = list(self._info.get("profiles", {}))
        return [self._info.get("builtin_profile", "Standard")] + names

    @Property(int, constant=True)
    def startPage(self):
        return self._start_page

    @Property(bool, constant=True)
    def startMinimized(self):
        return self._minimized

    def _get_tray(self):
        return self._tray

    def _set_tray(self, v):
        if v != self._tray:
            self._tray = v
            self.trayChanged.emit()

    trayAvailable = Property(bool, _get_tray, _set_tray, notify=trayChanged)

    @Property(bool, notify=autostartChanged)
    def autostartEnabled(self):
        return AUTOSTART_FILE.exists()

    # ---- Aktionen aus QML

    @Slot(int)
    def setHistoryWindow(self, seconds):
        if seconds != self._window:
            self._window = seconds
            self.windowChanged.emit()
            self._rebuild_view()

    @Slot(str)
    def applyProfile(self, name):
        self._worker.submit(f"Profil {name} angewendet", {"cmd": "apply_profile", "name": name})

    @Slot()
    def resetAll(self):
        self._worker.submit("Alles auf Standard zurückgesetzt", {"cmd": "reset", "target": "all"})

    @Slot("QVariantMap", "QVariantMap", "QVariantMap")
    def setManual(self, gpu, cpu, fan):
        gpu, cpu, fan = _clean(gpu), _clean(cpu), _clean(fan)
        if gpu:
            self._worker.submit("GPU-Einstellungen angewendet", {"cmd": "set_gpu", "values": gpu})
        if cpu:
            self._worker.submit("CPU-Einstellungen angewendet", {"cmd": "set_cpu", "values": cpu})
        if fan:
            self._worker.submit("Lüfterkurve angewendet", {"cmd": "set_fan", "values": fan})
        elif (self._info.get("fan") or {}).get("supported"):
            self._worker.submit("Lüfter auf Automatik gestellt", {"cmd": "set_fan", "values": {"mode": "auto"}})

    @Slot(str, "QVariantMap", "QVariantMap", "QVariantMap", str)
    def saveProfile(self, name, gpu, cpu, fan, replaces):
        name = name.strip()
        settings = {"gpu": _clean(gpu), "cpu": _clean(cpu)}
        fan = _clean(fan)
        if fan:
            settings["fan"] = fan
        follow_up = self._rename_follow_up(name, replaces) if replaces and replaces != name else None
        self._worker.submit(f"Profil {name} gespeichert",
                            {"cmd": "save_profile", "name": name, "settings": settings}, follow_up)

    def _rename_follow_up(self, name, old):
        """Folgebefehle beim Umbenennen: erst nach erfolgreichem Speichern, sonst bleibt das alte Profil."""
        moves_startup = self.startupProfile == old

        def after_save(resp):
            if not resp.get("ok"):
                return []
            # Der Daemon löscht beim Entfernen des alten Profils auch dessen Autostart-Eintrag.
            moved = [("", {"cmd": "set_autostart", "profile": name})] if moves_startup else []
            return moved + [("", {"cmd": "delete_profile", "name": old})]
        return after_save

    @Slot(str, str, result=str)
    def profileNameError(self, name, editing):
        """Grund, warum der Name nicht gespeichert werden kann; leer = in Ordnung (oder noch leer)."""
        name = name.strip()
        if not name:
            return ""
        if not PROFILE_NAME.fullmatch(name):
            return "Erlaubt: 1-32 Zeichen, Buchstaben, Ziffern, Leerzeichen, . _ -"
        builtin = self._info.get("builtin_profile", "Standard")
        if name.lower() == builtin.lower():
            return f"'{builtin}' ist reserviert"
        if name != editing and name in (self._info.get("profiles") or {}):
            return "Ein Profil mit diesem Namen gibt es schon"
        return ""

    @Slot(str)
    def deleteProfile(self, name):
        self._worker.submit(f"Profil {name} gelöscht", {"cmd": "delete_profile", "name": name})

    @Slot(str)
    def setStartupProfile(self, name):
        text = f"Profil {name} wird beim Systemstart angewendet" if name else "Kein Profil beim Systemstart"
        self._worker.submit(text, {"cmd": "set_autostart", "profile": name or None})

    @Slot(bool)
    def setAutostart(self, on):
        try:
            if on:
                AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
                AUTOSTART_FILE.write_text(AUTOSTART_TEXT, encoding="utf-8")
            elif AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()
        except OSError as e:
            self.toast.emit(f"Autostart nicht änderbar: {e}", True)
        self.autostartChanged.emit()

    @Slot()
    def quit(self):
        QCoreApplication.quit()
