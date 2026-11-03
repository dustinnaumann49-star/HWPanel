# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle

"""Interaction test for the fan curve editor (QML, offscreen, simulated mouse events)."""

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
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "gui"))

try:
    from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QPoint, QPointF, Qt, QUrl, Q_ARG
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:   # Errors in the project modules should stand out and not end up as "skipped"
    import hwpanel_i18n as i18n
    from language import Language

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


HINT_WRAPPER = """
import QtQuick
import QtQuick.Window
import "%s"

Window {
    width: 760; height: 620; visible: true
    Column {
        x: 20; y: 20; spacing: 50
        ChoiceRow { objectName: "epp"; kind: "epp"
                    options: ["default", "performance", "balance_performance", "balance_power", "power"] }
        ChoiceRow { objectName: "gov"; kind: "governor"; driver: "intel_pstate"
                    options: ["performance", "powersave", "schedutil", "ondemand", "conservative", "userspace"] }
        ChoiceRow { objectName: "gov_acpi"; kind: "governor"; driver: "acpi-cpufreq"; options: ["powersave"] }
        ChoiceRow { objectName: "sensor"; kind: "sensor"; options: ["edge", "junction", "mem"] }
        ChoiceRow { objectName: "unknown"; kind: "epp"; options: ["gibtsnicht"] }
        HelpLabel { objectName: "help"; text: "Turbo Boost"; hint: "<b>Erklärung.</b> Text" }
        HelpLabel { objectName: "help_short"; text: "Kurz"; hint: "Deutsch" }
    }
}
"""


def pump(sec=0.15):
    end = time.time() + sec
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def walk(item):
    for ch in item.childItems():
        yield ch
        yield from walk(ch)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class FanEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "wrapper.qml"
        path.write_text(WRAPPER % QUrl.fromLocalFile(str(QML_DIR)).toString(), encoding="utf-8")
        cls.engine = QQmlApplicationEngine()
        cls.engine.load(QUrl.fromLocalFile(str(path)))
        assert cls.engine.rootObjects(), "Wrapper QML could not be loaded"
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

    # ---- Helpers

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
        # to the right past the neighbor (80 °C) and beyond its percentage
        self.drag(self.pos(50, 55), self.pos(95, 100))
        pts = self.pts()
        self.assertEqual(pts[1][0], 79)
        self.assertEqual(pts[1][1], 90)
        # to the left/down below the predecessor (30 °C / 40 %)
        self.drag(self.pos(79, 90), self.pos(22, 0))
        pts = self.pts()
        self.assertEqual(pts[1][0], 31)
        self.assertEqual(pts[1][1], 40)
        # curve stays valid: temperatures ascending, percentages non-decreasing
        for a, b in zip(pts, pts[1:]):
            self.assertLess(a[0], b[0])
            self.assertLessEqual(a[1], b[1])

    def test_first_and_last_point_stay_in_range(self):
        self.drag(self.pos(30, 40), self.pos(20, 0))
        self.assertEqual(self.pts()[0], [20, 0])
        self.drag(self.pos(80, 90), self.pos(100, 100))
        self.assertEqual(self.pts()[2], [100, 100])
        # values outside the chart are clamped even on a direct call
        for t, p in ((-50, -50), (500, 500)):
            QMetaObject.invokeMethod(self.ed, "moveTo", Qt.DirectConnection, Q_ARG("QVariant", 0),
                                     Q_ARG("QVariant", float(t)), Q_ARG("QVariant", float(p)))
            pts = self.pts()
            self.assertGreaterEqual(pts[0][0], 20)
            self.assertLess(pts[0][0], pts[1][0])
            self.assertGreaterEqual(pts[0][1], 0)
            self.assertLessEqual(pts[0][1], pts[1][1])

    def test_double_click_adds_and_delete_removes(self):
        p = self.pos(65, 20)  # empty area
        QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, p)
        pump(0.1)
        pts = self.pts()
        self.assertEqual(len(pts), 4)
        self.assertEqual([x[0] for x in pts], sorted(x[0] for x in pts))
        new = [x for x in pts if x not in ([30, 40], [50, 55], [80, 90])][0]
        self.assertAlmostEqual(new[0], 65, delta=1)
        self.assertAlmostEqual(new[1], 72, delta=2)  # on the curve, not at the click height
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
        self.drag(self.pos(50, 55), self.pos(50, 55), steps=1)  # select point
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


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class HintTests(unittest.TestCase):
    """Explanations on hover (choice buttons and labels)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "hint_wrapper.qml"
        path.write_text(HINT_WRAPPER % QUrl.fromLocalFile(str(QML_DIR)).toString(), encoding="utf-8")
        cls.engine = QQmlApplicationEngine()
        cls.engine.load(QUrl.fromLocalFile(str(path)))
        assert cls.engine.rootObjects(), "Wrapper QML could not be loaded"
        cls.win = cls.engine.rootObjects()[0]
        cls.language = Language(env={"LANG": "de_DE.UTF-8"})   # the expectations below are German
        pump(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.language.close()
        i18n.set_language("en")
        cls.tmp.cleanup()

    def switch_language(self, code):
        self.language.setLanguage(code)
        self.language.retranslate(self.win)   # like Main.qml on a language change
        pump(0.2)

    def setUp(self):
        self.switch_language("de")
        QTest.mouseMove(self.win, QPoint(2, 2))
        pump(0.1)

    # ---- Helpers

    def row(self, name):
        return self.win.findChild(QObject, name)

    def buttons(self, name):
        """Choice buttons of a row: text -> element."""
        return {b.property("text"): b for b in walk(self.row(name)) if b.property("hint") is not None}

    def hints(self, name):
        return {text: b.property("hint") for text, b in self.buttons(name).items()}

    def tips(self, item):
        return [o for o in item.findChildren(QObject) if o.inherits("QQuickToolTip")]

    def hover(self, item, wait=0.8):
        c = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseMove(self.win, QPoint(round(c.x()), round(c.y())))
        pump(wait)
        return c

    # ---- Texts

    def test_every_epp_option_is_explained(self):
        hints = self.hints("epp")
        self.assertEqual(set(hints), {"default", "performance", "balance_performance", "balance_power", "power"})
        for text, hint in hints.items():
            self.assertIn("<b>", hint, text)
        self.assertEqual(len(set(hints.values())), 5, "each option needs its own text")

    def test_governor_hint_depends_on_driver(self):
        gov = self.hints("gov")
        self.assertIn("Takt nach Bedarf", gov["powersave"])
        self.assertIn("ignoriert", gov["performance"])
        for name in ("schedutil", "ondemand", "conservative", "userspace"):
            self.assertNotEqual(gov[name], "", name)
        self.assertIn("niedrigsten Takt", self.hints("gov_acpi")["powersave"])

    def test_fan_sensors_are_explained(self):
        hints = self.hints("sensor")
        self.assertEqual(set(hints), {"edge", "junction", "mem"})
        self.assertTrue(all(hints.values()))

    def test_hints_follow_the_language_live(self):
        btn = self.buttons("epp")["performance"]
        self.assertIn("Höchste Leistung", btn.property("hint"))
        self.switch_language("en")
        self.assertIn("Highest performance", btn.property("hint"))
        self.assertIn("Highest performance", self.tips(btn)[0].property("text"))
        self.assertIn("lowest clock", self.buttons("gov_acpi")["powersave"].property("hint").lower())
        self.switch_language("de")
        self.assertIn("Höchste Leistung", btn.property("hint"))

    def test_unknown_option_has_no_hint(self):
        self.assertEqual(self.hints("unknown"), {"gibtsnicht": ""})

    # ---- Behavior

    def test_hover_shows_hint_after_delay_and_hides_again(self):
        btn = self.buttons("epp")["performance"]
        tip = self.tips(btn)[0]
        self.assertFalse(tip.property("visible"))
        self.hover(btn, wait=0.1)
        self.assertFalse(tip.property("visible"), "must not flash up immediately")
        pump(0.7)
        self.assertTrue(tip.property("visible"))
        self.assertEqual(tip.property("text"), btn.property("hint"))
        QTest.mouseMove(self.win, QPoint(2, 2))
        pump(0.3)
        self.assertFalse(tip.property("visible"))

    def test_no_popup_for_option_without_hint(self):
        btn = self.buttons("unknown")["gibtsnicht"]
        self.hover(btn)
        self.assertFalse(self.tips(btn)[0].property("visible"))

    def test_click_hides_hint_until_mouse_leaves(self):
        btn = self.buttons("epp")["power"]
        tip = self.tips(btn)[0]
        c = self.hover(btn)
        self.assertTrue(tip.property("visible"))
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(round(c.x()), round(c.y())))
        pump(0.8)
        self.assertFalse(tip.property("visible"), "no explanation after the click")
        QTest.mouseMove(self.win, QPoint(2, 2))
        pump(0.2)
        self.hover(btn)
        self.assertTrue(tip.property("visible"), "again after hovering anew")

    def test_card_width_fits_short_text_and_is_capped_for_long_text(self):
        label = self.row("help_short")
        btn = self.buttons("epp")["performance"]
        short, long_ = self.tips(label)[0], self.tips(btn)[0]
        self.assertLess(short.property("contentWidth"), 120, "a single word needs no 300 px wide card")
        self.assertGreater(short.property("contentWidth"), 20)
        self.assertEqual(long_.property("contentWidth"), 300)

    def test_label_with_hint(self):
        label = self.row("help")
        self.hover(label)
        tips = self.tips(label)
        self.assertEqual(len(tips), 1)
        self.assertTrue(tips[0].property("visible"))
        self.assertIn("Erklärung", tips[0].property("text"))


if __name__ == "__main__":
    unittest.main()
