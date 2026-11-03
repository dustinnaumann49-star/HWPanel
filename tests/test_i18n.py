"""Tests für hwpanel_i18n: Sprachwahl, Kataloge, Übersetzen und die echten Kataloge in locales/."""

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hwpanel_i18n as i18n  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        dump = lambda o: json.dumps(o, ensure_ascii=False)  # noqa: E731
        (d / "de.json").write_text(dump({
            "_name": "Deutsch", "Overview": "Übersicht",
            "Profile {name} applied": "Profil {name} angewendet",
            "Broken {x}": "Kaputt {y}", "Empty": "", "Number": 5}), encoding="utf-8")
        (d / "fr.json").write_text(dump({"Overview": "Aperçu"}), encoding="utf-8")   # ohne _name
        (d / "en.json").write_text(dump({"_name": "English"}), encoding="utf-8")
        (d / "xx.json").write_text("{kaputt", encoding="utf-8")                      # defekt
        self.dir = d

    def tearDown(self):
        self.tmp.cleanup()
        i18n.set_language("en")


class TestAvailable(Fixture):
    def test_lists_valid_catalogs_with_native_names(self):
        self.assertEqual(i18n.available(self.dir), {"de": "Deutsch", "en": "English", "fr": "fr"})

    def test_english_is_always_there(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(i18n.available(empty), {"en": "English"})
        self.assertIn("en", i18n.available(self.dir / "gibt-es-nicht"))


class TestSystemLanguages(unittest.TestCase):
    def test_parses_locale_names(self):
        for value, want in (("de_DE.UTF-8", ["de"]), ("de_DE@euro", ["de"]), ("de", ["de"]),
                            ("pt_BR.UTF-8", ["pt"]), ("en_US.UTF-8", ["en"])):
            self.assertEqual(i18n.system_languages({"LANG": value}), want, value)

    def test_c_and_posix_and_empty_mean_english(self):
        for env in ({}, {"LANG": ""}, {"LANG": "C"}, {"LANG": "POSIX"}, {"LANG": "C.UTF-8"},
                    {"LC_ALL": "C", "LANG": "de_DE.UTF-8"},
                    {"LC_ALL": "C", "LANGUAGE": "de", "LANG": "de_DE.UTF-8"}):
            self.assertEqual(i18n.system_languages(env), [], env)

    def test_priority_like_gettext(self):
        self.assertEqual(i18n.system_languages({"LC_ALL": "fr_FR.UTF-8", "LANG": "de_DE.UTF-8"}), ["fr"])
        self.assertEqual(i18n.system_languages({"LC_MESSAGES": "fr_FR", "LANG": "de_DE"}), ["fr"])
        self.assertEqual(i18n.system_languages({"LANGUAGE": "fr:de", "LANG": "de_DE.UTF-8"}), ["fr", "de"])


class TestResolve(Fixture):
    def resolve(self, pref=None, **env):
        return i18n.resolve(pref, env, self.dir)

    def test_auto_follows_system_language(self):
        self.assertEqual(self.resolve(LANG="de_DE.UTF-8"), "de")
        self.assertEqual(self.resolve("auto", LANG="de_DE.UTF-8"), "de")
        self.assertEqual(self.resolve("", LANG="de_AT.UTF-8"), "de")

    def test_auto_falls_back_to_english(self):
        self.assertEqual(self.resolve(LANG="ja_JP.UTF-8"), "en")   # Sprache ohne Katalog
        self.assertEqual(self.resolve(LANG="C"), "en")
        self.assertEqual(self.resolve(), "en")

    def test_auto_skips_unavailable_language_for_next_one(self):
        self.assertEqual(self.resolve(LANGUAGE="ja:de", LANG="ja_JP.UTF-8"), "de")

    def test_explicit_choice_beats_system_language(self):
        self.assertEqual(self.resolve("en", LANG="de_DE.UTF-8"), "en")
        self.assertEqual(self.resolve("DE", LANG="en_US.UTF-8"), "de")
        self.assertEqual(self.resolve("de_DE", LANG="en_US.UTF-8"), "de")

    def test_unknown_explicit_choice_is_english(self):
        self.assertEqual(self.resolve("klingon", LANG="de_DE.UTF-8"), "en")
        self.assertEqual(self.resolve("ja", LANG="de_DE.UTF-8"), "en")


class TestLoadAndTranslate(Fixture):
    def test_load_drops_meta_and_invalid_entries(self):
        self.assertEqual(i18n.load("de", self.dir), {
            "Overview": "Übersicht", "Profile {name} applied": "Profil {name} angewendet", "Broken {x}": "Kaputt {y}"})

    def test_load_unknown_or_broken_gives_empty(self):
        self.assertEqual(i18n.load("ja", self.dir), {})
        self.assertEqual(i18n.load("xx", self.dir), {})
        self.assertEqual(i18n.load("en", self.dir), {})

    def test_default_language_is_english_source(self):
        self.assertEqual(i18n.language(), "en")
        self.assertEqual(i18n.tr("Overview"), "Overview")

    def test_translates_and_falls_back_to_source(self):
        self.assertEqual(i18n.set_language("de", self.dir), "de")
        self.assertEqual(i18n.language(), "de")
        self.assertEqual(i18n.tr("Overview"), "Übersicht")
        self.assertEqual(i18n.tr("Not in catalog"), "Not in catalog")

    def test_placeholders(self):
        i18n.set_language("de", self.dir)
        self.assertEqual(i18n.tr("Profile {name} applied", name="KI"), "Profil KI angewendet")
        self.assertEqual(i18n.tr("Not in catalog {n}", n=3), "Not in catalog 3")

    def test_bad_placeholder_in_translation_falls_back_to_source(self):
        i18n.set_language("de", self.dir)
        self.assertEqual(i18n.tr("Broken {x}", x=1), "Broken 1")

    def test_literal_braces_without_arguments_stay_untouched(self):
        self.assertEqual(i18n.tr('{"a": 1}'), '{"a": 1}')

    def test_unknown_language_selects_english(self):
        i18n.set_language("de", self.dir)
        self.assertEqual(i18n.set_language("ja", self.dir), "en")
        self.assertEqual(i18n.tr("Overview"), "Overview")

    def test_current_catalog_is_exposed(self):
        i18n.set_language("de", self.dir)
        self.assertEqual(i18n.catalog()["Overview"], "Übersicht")


def _tokens(text):
    """Platzhalter ({name}, %1) und HTML-Marken einer Meldung, sortiert."""
    return sorted(re.findall(r"\{[A-Za-z_0-9]*\}|%\d|</?[a-z]+>", text))


class TestRealCatalogs(unittest.TestCase):
    """Die mitgelieferten Dateien in locales/ müssen für alle Sprachen dieselben Regeln einhalten."""

    @classmethod
    def setUpClass(cls):
        cls.files = sorted((ROOT / "locales").glob("*.json"))

    def read(self, path):
        def no_duplicates(pairs):
            keys = [k for k, _ in pairs]
            dup = {k for k in keys if keys.count(k) > 1}
            self.assertFalse(dup, f"{path.name}: doppelte Schlüssel {sorted(dup)}")
            return dict(pairs)
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)

    def test_german_and_english_are_shipped(self):
        names = {f.stem for f in self.files}
        self.assertTrue({"de", "en"} <= names, names)

    def test_every_catalog_names_its_language(self):
        for f in self.files:
            self.assertTrue(str(self.read(f).get("_name", "")).strip(), f.name)

    def test_entries_are_nonempty_strings(self):
        for f in self.files:
            for k, v in self.read(f).items():
                self.assertIsInstance(v, str, f"{f.name}: {k!r}")
                self.assertTrue(v.strip(), f"{f.name}: leere Übersetzung für {k!r}")

    def test_placeholders_and_markup_match_source_text(self):
        for f in self.files:
            for k, v in self.read(f).items():
                if k == "_name":
                    continue
                self.assertEqual(_tokens(k), _tokens(v), f"{f.name}: {k!r} -> {v!r}")

    def test_no_translation_equals_its_key(self):
        # Ein Eintrag, der dem Quelltext gleicht, ist überflüssig: Fehlt er, erscheint derselbe Text.
        for f in self.files:
            if f.stem == "en":
                continue
            for k, v in self.read(f).items():
                if k != "_name":
                    self.assertNotEqual(k, v, f"{f.name}: {k!r} ist unübersetzt (Eintrag streichen)")


GERMAN_LETTERS = re.compile(r"[äöüÄÖÜß]")
# Quelltexte, die auf Deutsch genauso lauten: Sie brauchen keinen Eintrag in de.json.
SAME_IN_GERMAN = {
    "Auto", "Sensor", "Governor", "Turbo Boost", "Energy Performance Preference",
    "GPU max %1 MHz", "VRAM max %1 MHz", "CPU max %1 MHz", "Power %1 W", "EPP %1", "Governor %1",
    "Max %1 MHz · ", "max %1 MHz", "max %1", "Limit %1 W", "VRAM %1 MHz", "Junction %1 · Mem %2", "LACT: %1",
    "CPU   {model}",
}
QML_FILES = sorted((ROOT / "gui" / "qml").glob("*.qml")) + [ROOT / "gui" / "qml" / "Fmt.js"]
PY_FILES = sorted((ROOT / "gui").glob("*.py")) + [ROOT / "hwpanelctl.py"]   # der Daemon folgt in einem späteren Schritt
QSTR = re.compile(r'\bqsTr\(\s*"((?:[^"\\]|\\.)*)"')


def qml_texts():
    """Alle Quelltexte von qsTr() in QML und JS: Text -> Dateien."""
    out = {}
    for f in QML_FILES:
        for m in QSTR.finditer(f.read_text(encoding="utf-8")):
            out.setdefault(json.loads('"%s"' % m.group(1)), []).append(f.name)
    return out


def _tr_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == "tr") or (isinstance(fn, ast.Attribute) and fn.attr == "tr"):
                yield node.args[0]


def python_texts(files=None):
    """Alle Quelltexte von tr(...) in Python-Dateien: Text -> Dateien."""
    out = {}
    for f in files or PY_FILES + [ROOT / "hwpaneld.py"]:
        for arg in _tr_calls(ast.parse(f.read_text(encoding="utf-8"))):
            out.setdefault(arg.value, []).append(f.name)
    return out


class TestCatalogCoverage(unittest.TestCase):
    """Die deutschen Texte dürfen nicht im Quelltext stehen, und der Katalog muss genau die benutzten Texte enthalten."""

    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / "locales" / "de.json").read_text(encoding="utf-8"))
        cls.de = {k: v for k, v in data.items() if k != "_name"}
        cls.used = {**qml_texts(), **python_texts()}

    def test_every_source_text_has_a_german_translation(self):
        missing = sorted(t for t in self.used if t not in self.de and t not in SAME_IN_GERMAN)
        self.assertEqual(missing, [], "fehlt in locales/de.json (oder gehört in SAME_IN_GERMAN)")

    def test_same_in_german_list_is_current(self):
        self.assertEqual(sorted(t for t in SAME_IN_GERMAN if t not in self.used), [],
                         "kommt im Quelltext nicht mehr vor")
        self.assertEqual(sorted(t for t in SAME_IN_GERMAN if t in self.de), [],
                         "steht in der Liste und im Katalog: eines davon streichen")

    def test_catalog_has_no_unused_entries(self):
        unused = sorted(k for k in self.de if k not in self.used)
        self.assertEqual(unused, [], "kommt im Quelltext nicht mehr vor")

    def test_no_german_text_left_in_qml_outside_qstr(self):
        for f in QML_FILES:
            code = QSTR.sub('qsTr("")', f.read_text(encoding="utf-8"))
            code = re.sub(r"//.*", "", code)
            for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', code):
                self.assertIsNone(GERMAN_LETTERS.search(lit), f"{f.name}: {lit!r} gehört in qsTr()")

    def test_no_german_text_left_in_gui_python_outside_tr(self):
        allowed_prefix = "[Desktop Entry]"   # Vorlage der Autostart-Datei enthält absichtlich Comment[de]
        for f in PY_FILES:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            in_tr = {id(a) for a in _tr_calls(tree)}
            docstrings = {id(n.value) for n in ast.walk(tree)
                          if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and id(node) not in in_tr and id(node) not in docstrings \
                        and not node.value.startswith(allowed_prefix):
                    self.assertIsNone(GERMAN_LETTERS.search(node.value),
                                      f"{f.name}:{node.lineno}: {node.value!r} gehört in tr()")


if __name__ == "__main__":
    unittest.main()
