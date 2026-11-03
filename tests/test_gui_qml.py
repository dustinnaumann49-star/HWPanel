"""Interaktionstest für den Lüfterkurven-Editor (QML, offscreen, simulierte Mausereignisse)."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
HERE = Path(__file__).resolve().parent
QML_DIR = HERE.parent / "gui" / "qml"

try:
    from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QPoint, Qt, QUrl, Q_ARG
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

WRAPPER = """
import QtQuick
import QtQuick.Window
import "%s"

Window {
    id: w
    width: 800; height: 420; visible: true
    property var pts: [[30, 40], [50, 55], [80, 90]]
    property var lastEdit: null
    FanCurveEditor {
        id: ed
        objectName: "ed"
        anchors.fill: parent
        points: w.pts
        minPoints: 2
        maxPoints: 5
        onEdited: (p) => { w.pts = p; w.lastEdit = p }
    }
}
"""


def pump(sec=0.15):
    end = time.time() + sec
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class FanEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "wrapper.qml"
        path.write_text(WRAPPER % QUrl.fromLocalFile(str(QML_DIR)).toString(), encoding="utf-8")
        cls.engine = QQmlApplicationEngine()
        cls.engine.load(QUrl.fromLocalFile(str(path)))
        assert cls.engine.rootObjects(), "Wrapper-QML konnte nicht geladen werden"
        cls.win = cls.engine.rootObjects()[0]
        cls.ed = cls.win.findChild(QObject, "ed")
        pump(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.tmp.cleanup()

    def setUp(self):
        self.win.setProperty("pts", [[30, 40], [50, 55], [80, 90]])
        self.ed.setProperty("selected", -1)
        self.ed.setProperty("editable", True)
        pump(0.1)

    # ---- Hilfen

    def pts(self):
        return [[int(a), int(b)] for a, b in self.win.property("pts")]

    def pos(self, t, p):
        x = self.ed.property("pL") + (t - self.ed.property("tMin")) / (self.ed.property("tMax") - self.ed.property("tMin")) * self.ed.property("pw")
        y = self.ed.property("pT") + (1 - p / 100.0) * self.ed.property("ph")
        return QPoint(round(x), round(y))

    def drag(self, start, end, steps=6):
        w = self.win
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, start)
        for i in range(1, steps + 1):
            q = QPoint(start.x() + (end.x() - start.x()) * i // steps, start.y() + (end.y() - start.y()) * i // steps)
            QTest.mouseMove(w, q)
            pump(0.02)
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, end)
        pump(0.05)

    # ---- Tests

    def test_drag_moves_point(self):
        self.drag(self.pos(50, 55), self.pos(60, 70))
        pts = self.pts()
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(pts[1][0], 60, delta=1)
        self.assertAlmostEqual(pts[1][1], 70, delta=2)
        self.assertEqual(self.ed.property("selected"), 1)

    def test_drag_is_clamped_between_neighbours(self):
        # nach rechts über den Nachbarn (80 °C) und über dessen Prozentwert hinaus
        self.drag(self.pos(50, 55), self.pos(95, 100))
        pts = self.pts()
        self.assertEqual(pts[1][0], 79)
        self.assertEqual(pts[1][1], 90)
        # nach links/unten unter den Vorgänger (30 °C / 40 %)
        self.drag(self.pos(79, 90), self.pos(22, 0))
        pts = self.pts()
        self.assertEqual(pts[1][0], 31)
        self.assertEqual(pts[1][1], 40)
        # Kurve bleibt gültig: Temperaturen steigend, Prozent nicht fallend
        for a, b in zip(pts, pts[1:]):
            self.assertLess(a[0], b[0])
            self.assertLessEqual(a[1], b[1])

    def test_first_and_last_point_stay_in_range(self):
        self.drag(self.pos(30, 40), self.pos(20, 0))
        self.assertEqual(self.pts()[0], [20, 0])
        self.drag(self.pos(80, 90), self.pos(100, 100))
        self.assertEqual(self.pts()[2], [100, 100])
        # Werte außerhalb des Diagramms werden auch bei direktem Aufruf begrenzt
        for t, p in ((-50, -50), (500, 500)):
            QMetaObject.invokeMethod(self.ed, "moveTo", Qt.DirectConnection, Q_ARG("QVariant", 0),
                                     Q_ARG("QVariant", float(t)), Q_ARG("QVariant", float(p)))
            pts = self.pts()
            self.assertGreaterEqual(pts[0][0], 20)
            self.assertLess(pts[0][0], pts[1][0])
            self.assertGreaterEqual(pts[0][1], 0)
            self.assertLessEqual(pts[0][1], pts[1][1])

    def test_double_click_adds_and_delete_removes(self):
        p = self.pos(65, 20)  # leerer Bereich
        QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, p)
        pump(0.1)
        pts = self.pts()
        self.assertEqual(len(pts), 4)
        self.assertEqual([x[0] for x in pts], sorted(x[0] for x in pts))
        new = [x for x in pts if x not in ([30, 40], [50, 55], [80, 90])][0]
        self.assertAlmostEqual(new[0], 65, delta=1)
        self.assertAlmostEqual(new[1], 72, delta=2)  # auf der Kurve, nicht an der Klickhöhe
        self.assertGreaterEqual(self.ed.property("selected"), 0)
        QMetaObject.invokeMethod(self.ed, "removeSelected", Qt.DirectConnection)
        pump(0.05)
        self.assertEqual(len(self.pts()), 3)

    def test_point_limits(self):
        for t in (35, 40, 60, 70):
            QMetaObject.invokeMethod(self.ed, "addAt", Qt.DirectConnection, Q_ARG("QVariant", float(t)))
        self.assertEqual(len(self.pts()), 5)          # maxPoints = 5
        QMetaObject.invokeMethod(self.ed, "addAt", Qt.DirectConnection, Q_ARG("QVariant", 90.0))
        self.assertEqual(len(self.pts()), 5)
        for _ in range(6):                            # minPoints = 2
            self.ed.setProperty("selected", 0)
            QMetaObject.invokeMethod(self.ed, "removeSelected", Qt.DirectConnection)
            pump(0.02)
        self.assertEqual(len(self.pts()), 2)

    def test_keyboard_nudge_and_delete(self):
        self.drag(self.pos(50, 55), self.pos(50, 55), steps=1)  # Punkt wählen
        self.assertEqual(self.ed.property("selected"), 1)
        QTest.keyClick(self.win, Qt.Key_Right)
        QTest.keyClick(self.win, Qt.Key_Up)
        self.assertEqual(self.pts()[1], [51, 56])
        QTest.keyClick(self.win, Qt.Key_Left, Qt.ShiftModifier)
        self.assertEqual(self.pts()[1], [46, 56])
        QTest.keyClick(self.win, Qt.Key_Delete)
        self.assertEqual(len(self.pts()), 2)

    def test_not_editable_ignores_mouse(self):
        self.ed.setProperty("editable", False)
        pump(0.05)
        self.drag(self.pos(50, 55), self.pos(60, 70))
        self.assertEqual(self.pts(), [[30, 40], [50, 55], [80, 90]])

    def test_click_on_empty_area_deselects(self):
        self.ed.setProperty("selected", 1)
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, self.pos(65, 10))
        pump(0.05)
        self.assertEqual(self.ed.property("selected"), -1)


if __name__ == "__main__":
    unittest.main()
