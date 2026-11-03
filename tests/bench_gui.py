"""Misst die Zeichenzeit der GUI (Start, Seitenwechsel, Datenaktualisierung) offscreen.

Aufruf: python bench_gui.py   (Software-Rendering; zeigt Verhältnisse, nicht die absolute Zeit auf echter Hardware)
"""

import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "gui"))

from demo_client import DemoClient  # noqa: E402
from PySide6.QtCore import QCoreApplication, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from backend import Backend  # noqa: E402
import shiboken6  # noqa: E402


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def frame(win):
    """Verarbeitet Ereignisse und rendert einen Frame; liefert die benötigte Zeit in ms."""
    t0 = time.perf_counter()
    QCoreApplication.processEvents()
    win.grabWindow()
    QCoreApplication.processEvents()
    win.grabWindow()
    return (time.perf_counter() - t0) * 1000


def main():
    client = DemoClient()
    app = QApplication(sys.argv[:1])
    backend = Backend(client)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    t0 = time.perf_counter()
    engine.load(QUrl.fromLocalFile(str(HERE.parent / "gui" / "qml" / "Main.qml")))
    win = shiboken6.wrapInstance(shiboken6.getCppPointer(engine.rootObjects()[0])[0], QQuickWindow)
    first = frame(win)
    print(f"Start: Laden+erster Frame {1000 * (time.perf_counter() - t0):.0f} ms (erster Frame {first:.0f} ms)")
    pump(2.0)
    for _ in range(3):
        frame(win)
    backend.setHistoryWindow(3600)
    pump(0.5)
    frame(win)

    for name, order in (("Seitenwechsel", [1, 2, 3, 0, 1, 3, 0, 2, 1, 0]),):
        times = []
        for p in order:
            win.setProperty("page", p)
            times.append((p, frame(win)))
            pump(0.2)
            frame(win)
        print(name, " ".join(f"{p}:{t:.0f}" for p, t in times), "ms")
        print(f"  Median {statistics.median(t for _, t in times):.0f} ms, max {max(t for _, t in times):.0f} ms")

    # eine Sekunde Datenaktualisierung auf Verlauf bzw. Übersicht
    for p in (1, 0):
        win.setProperty("page", p)
        pump(0.5)
        frame(win)
        ts = []
        base = backend._samples[-1]["t"]
        for i in range(8):
            s = dict(backend._samples[-1])
            s["t"] = base + i + 1
            backend._on_history({"samples": [s], "events": []})
            ts.append(frame(win))
        print(f"Datenupdate auf Seite {p}: Median {statistics.median(ts):.0f} ms, max {max(ts):.0f} ms")
    # Update, während eine andere Seite sichtbar ist (soll fast nichts kosten)
    win.setProperty("page", 2)
    pump(0.5)
    frame(win)
    ts = []
    for i in range(8):
        s = dict(backend._samples[-1])
        s["t"] = base + 100 + i
        backend._on_history({"samples": [s], "events": []})
        ts.append(frame(win))
    print(f"Datenupdate auf Profile-Seite (Diagramme versteckt): Median {statistics.median(ts):.0f} ms")
    backend.shutdown()
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
