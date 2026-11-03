"""Renders the GUI pages offscreen with simulated data as PNG (for visual inspection).

Usage: python render_gui.py OUTPUT_DIR [page ...]
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "gui"))

from demo_client import DemoClient  # noqa: E402
from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, Q_ARG, Qt, QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from backend import Backend  # noqa: E402
import shiboken6  # noqa: E402

NAMES = ["uebersicht", "verlauf", "profile", "manuell"]


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.02)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    pages = [int(a) for a in sys.argv[2:]] or [0, 1, 2, 3]
    client = DemoClient()
    app = QApplication(sys.argv[:1])
    backend = Backend(client)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(HERE.parent / "gui" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("QML could not be loaded")
        return 1
    win = shiboken6.wrapInstance(shiboken6.getCppPointer(engine.rootObjects()[0])[0], QQuickWindow)
    pump(2.5)
    if os.environ.get("HWPANEL_WINDOW"):
        backend.setHistoryWindow(int(os.environ["HWPANEL_WINDOW"]))
        pump(0.5)
    print("connected:", backend.connected, "samples:", len(backend.history["t"]),
          "events:", backend.history["events"])
    for p in pages:
        win.setProperty("page", p)
        pump(0.6)
        win.grabWindow()  # forces rendering so that animations keep running
        pump(0.4)
        win.grabWindow()
        pump(0.4)
        img = win.grabWindow()
        path = out / f"{p}_{NAMES[p]}{os.environ.get('HWPANEL_WINDOW', '')}.png"
        img.save(str(path))
        print("written", path, img.width(), img.height())
    extra = os.environ.get("HWPANEL_EXTRA")
    if extra:
        # dialog-new | dialog-edit | dialog-fan (profile KI, fan tab) | dialog-new-fan | manual-fan | toast
        win.setProperty("page", 3 if extra == "manual-fan" else 2)
        pump(0.5)
        dlg = win.findChild(QObject, "profileDialog")
        if extra in ("dialog-new", "dialog-new-fan"):
            QMetaObject.invokeMethod(dlg, "openNew")
            if extra == "dialog-new-fan":
                dlg.setProperty("tab", 1)
        elif extra in ("dialog-edit", "dialog-fan"):
            QMetaObject.invokeMethod(dlg, "openEdit", Qt.DirectConnection,
                                     Q_ARG("QVariant", "KI"), Q_ARG("QVariant", 1 if extra == "dialog-fan" else 0))
        elif extra == "manual-fan":
            win.findChild(QObject, "controlPage").setProperty("tab", 1)
        if extra == "toast":
            backend.toast.emit("Profil KI angewendet", False)
        for _ in range(4):
            pump(0.4)
            win.grabWindow()
        win.grabWindow().save(str(out / f"x_{extra}.png"))
        print("written", out / f"x_{extra}.png")
    backend.shutdown()
    sys.stdout.flush()
    os._exit(0)  # avoid teardown messages from the QML bindings


if __name__ == "__main__":
    sys.exit(main())
