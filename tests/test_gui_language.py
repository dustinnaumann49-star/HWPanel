"""Tests für die Sprachwahl der GUI: Einstellung, Qt-Übersetzer und Umschalten zur Laufzeit in QML.

Benötigt PySide6, sonst werden die Tests übersprungen.
"""

import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "gui"))

try:
    import shiboken6
    from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QPoint, QPointF, Qt, QUrl, Q_ARG
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

import hwpanel_i18n as i18n  # noqa: E402

if HAVE_QT:   # Fehler in den Projektmodulen sollen auffallen und nicht als "übersprungen" enden
    import backend as be
    from demo_client import DemoClient
    from language import Language

DE = {"LANG": "de_DE.UTF-8"}
EN = {"LANG": "en_US.UTF-8"}
# Umlaute und typisch deutsche Wörter der Oberfläche: Auf Englisch darf nichts davon sichtbar sein
GERMAN = re.compile(r"[äöüÄÖÜß]|\b(Lüfter|Takt|Profil|Verlauf|Anwenden|Löschen|Bearbeiten|Standard|Einstellung\w*|Übersicht|"
                    r"Auslastung|Leistung|Temperatur|Speicher|Beenden|Sprache|Kurve|Punkt|Sicherung|Fehler|Belegt|"
                    r"Verfügbar|Abbrechen|Speichern|Aktiv|Last|Erneut|Neues|Eigene|Automatik|Regler|Treiber\w*|Warte|jetzt)\b")
TEXT_PROPERTIES = ("text", "label", "sub", "title", "note", "hint", "tip", "placeholderText", "waitText", "liveText")


def pump(sec=0.15):
    end = time.time() + sec
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def walk(item):
    for ch in item.childItems():
        yield ch
        yield from walk(ch)


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "hwpanel" / "gui.json"
        self.made = []

    def tearDown(self):
        for lang in self.made:
            lang.close()
        i18n.set_language("en")
        self.tmp.cleanup()

    def make(self, env=DE, path="default"):
        lang = Language(config_path=self.cfg if path == "default" else path, env=env)
        self.made.append(lang)
        return lang

    # ---- Wahl der Sprache

    def test_auto_follows_system_language(self):
        lang = self.make(DE)
        self.assertEqual((lang.setting, lang.code), ("auto", "de"))
        lang2 = self.make({"LANG": "fr_FR.UTF-8"}, path=None)
        self.assertEqual((lang2.setting, lang2.code), ("auto", "en"))

    def test_lists_available_languages(self):
        langs = self.make().languages
        self.assertIn({"code": "de", "name": "Deutsch"}, langs)
        self.assertIn({"code": "en", "name": "English"}, langs)

    def test_explicit_choice_changes_language_and_emits_signal(self):
        lang = self.make(DE)
        seen = []
        lang.languageChanged.connect(lambda: seen.append((lang.setting, lang.code)))
        lang.setLanguage("en")
        self.assertEqual((lang.setting, lang.code, i18n.tr("Overview")), ("en", "en", "Overview"))
        lang.setLanguage("de")
        self.assertEqual((lang.setting, lang.code, i18n.tr("Overview")), ("de", "de", "Übersicht"))
        lang.setLanguage("auto")
        self.assertEqual((lang.setting, lang.code), ("auto", "de"))
        self.assertEqual(seen, [("en", "en"), ("de", "de"), ("auto", "de")])

    def test_invalid_or_unchanged_choice_is_ignored(self):
        lang = self.make(DE)
        seen = []
        lang.languageChanged.connect(lambda: seen.append(1))
        lang.setLanguage("klingon")
        lang.setLanguage("")
        lang.setLanguage("auto")   # ist schon so
        self.assertEqual((lang.setting, lang.code, seen), ("auto", "de", []))

    # ---- Speichern

    def test_choice_is_saved_and_restored(self):
        self.make(DE).setLanguage("en")
        self.assertEqual(json.loads(self.cfg.read_text(encoding="utf-8")), {"language": "en"})
        again = self.make(DE)
        self.assertEqual((again.setting, again.code), ("en", "en"))

    def test_auto_is_saved_too(self):
        lang = self.make(DE)
        lang.setLanguage("en")
        lang.setLanguage("auto")
        again = self.make(EN)
        self.assertEqual(again.setting, "auto")

    def test_broken_or_unknown_saved_value_means_auto(self):
        self.cfg.parent.mkdir(parents=True)
        for content in ("{kaputt", "[]", '{"language": 5}', '{"language": "klingon"}', "{}"):
            self.cfg.write_text(content, encoding="utf-8")
            self.assertEqual(self.make(DE).setting, "auto", content)

    def test_unwritable_config_does_not_break_switching(self):
        blocker = Path(self.tmp.name) / "datei"
        blocker.write_text("x")
        lang = self.make(DE, path=blocker / "gui.json")   # Verzeichnis kann nicht angelegt werden
        lang.setLanguage("en")
        self.assertEqual(lang.code, "en")

    def test_without_config_path_nothing_is_written(self):
        lang = self.make(DE, path=None)
        lang.setLanguage("en")
        self.assertFalse(self.cfg.exists())

    # ---- Qt-Übersetzer für qsTr()

    def test_qt_translator_translates_and_falls_back_to_source(self):
        lang = self.make(DE)
        tr = lambda s: QCoreApplication.translate("Sidebar", s)  # noqa: E731
        self.assertEqual(tr("Overview"), "Übersicht")
        self.assertEqual(tr("Text without translation"), "Text without translation")
        lang.setLanguage("en")
        self.assertEqual(tr("Overview"), "Overview")

    def test_close_removes_translator(self):
        lang = self.make(DE)
        lang.close()
        lang.close()   # zweimal ist erlaubt
        self.assertEqual(QCoreApplication.translate("Sidebar", "Overview"), "Overview")


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class SidebarSwitchTests(unittest.TestCase):
    """Die echte Hauptseite: Umschalten per Mausklick wirkt sofort auf alle sichtbaren Texte."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.client = DemoClient(duration=60)
        cls.language = Language(config_path=Path(cls.tmp.name) / "gui.json", env=DE)
        cls.backend = be.Backend(cls.client, language=cls.language)
        cls.engine = QQmlApplicationEngine()
        cls.engine.rootContext().setContextProperty("backend", cls.backend)
        cls.engine.load(QUrl.fromLocalFile(str(ROOT / "gui" / "qml" / "Main.qml")))
        assert cls.engine.rootObjects(), "Main.qml konnte nicht geladen werden"
        cls.win = shiboken6.wrapInstance(shiboken6.getCppPointer(cls.engine.rootObjects()[0])[0], QQuickWindow)
        pump(1.5)

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.backend.shutdown()
        cls.client.close()
        i18n.set_language("en")
        cls.tmp.cleanup()

    def setUp(self):
        self.language.setLanguage("de")
        pump(0.3)

    def nav_texts(self):
        return [it.property("text") for it in walk(self.win.contentItem())
                if it.isVisible() and it.property("text") is not None and it.property("active") is not None
                and it.metaObject().className().startswith("NavButton")]

    def button(self, text):
        for it in walk(self.win.contentItem()):
            if it.isVisible() and it.property("text") == text and it.property("hint") is not None \
                    and it.property("compact"):
                return it
        raise AssertionError(f"Knopf {text!r} nicht gefunden")

    def click(self, item):
        c = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, QPoint(round(c.x()), round(c.y())))
        pump(0.4)

    def test_sidebar_follows_language_setting(self):
        self.assertEqual(self.nav_texts(), ["Übersicht", "Verlauf", "Profile", "Manuell"])
        self.language.setLanguage("en")
        pump(0.4)
        self.assertEqual(self.nav_texts(), ["Overview", "History", "Profiles", "Manual"])

    def test_click_on_language_button_switches_live_and_back(self):
        self.click(self.button("EN"))
        self.assertEqual(self.nav_texts(), ["Overview", "History", "Profiles", "Manual"])
        self.assertEqual(self.language.setting, "en")
        self.click(self.button("DE"))
        self.assertEqual(self.nav_texts(), ["Übersicht", "Verlauf", "Profile", "Manuell"])

    def test_active_language_button_is_marked(self):
        self.language.setLanguage("en")
        pump(0.3)
        self.assertTrue(self.button("EN").property("active"))
        self.assertFalse(self.button("DE").property("active"))
        self.assertFalse(self.button("Auto").property("active"))
        self.language.setLanguage("auto")
        pump(0.3)
        self.assertTrue(self.button("Auto").property("active"))

    def visible_texts(self):
        """Alle sichtbaren Beschriftungen, Hinweise und Untertitel als (Klasse, Eigenschaft, Text)."""
        out = []
        for it in walk(self.win.contentItem()):
            if not it.isVisible():
                continue
            for name in TEXT_PROPERTIES:
                value = it.property(name)
                if isinstance(value, str) and value:
                    out.append((it.metaObject().className(), name, value))
        return out

    def german_leftovers(self):
        return sorted({(c, n, t) for c, n, t in self.visible_texts() if GERMAN.search(t)})

    def test_no_german_text_left_on_any_page_in_english(self):
        self.language.setLanguage("en")
        pump(0.4)
        dialog = self.win.findChild(QObject, "profileDialog")
        for page in range(4):
            self.win.setProperty("page", page)
            pump(0.5)
            self.assertEqual(self.german_leftovers(), [], f"Seite {page}")
        self.win.setProperty("page", 2)
        pump(0.3)
        QMetaObject.invokeMethod(dialog, "openEdit", Qt.DirectConnection, Q_ARG("QVariant", "KI"), Q_ARG("QVariant", 0))
        pump(0.6)
        self.assertEqual(self.german_leftovers(), [], "Profildialog, Reiter Takt & CPU")
        dialog.setProperty("tab", 1)
        pump(0.4)
        self.assertEqual(self.german_leftovers(), [], "Profildialog, Reiter Lüfter")
        QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
        pump(0.3)

    def test_the_check_itself_finds_german_text(self):
        # Gegenprobe: Auf Deutsch muss derselbe Test deutsche Texte finden, sonst prüft er nichts
        self.win.setProperty("page", 3)
        pump(0.5)
        self.assertGreater(len(self.german_leftovers()), 5)

    def test_connection_text_is_translated(self):
        def status_texts():
            return [it.property("text") for it in walk(self.win.contentItem())
                    if it.isVisible() and isinstance(it.property("text"), str)
                    and it.property("text").startswith("Daemon")]
        self.assertIn("Daemon verbunden", status_texts())
        self.language.setLanguage("en")
        pump(0.4)
        self.assertIn("Daemon connected", status_texts())


if __name__ == "__main__":
    unittest.main()
