# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle

"""Tests for hwpanel_i18n: language choice, catalogs, translating and the real catalogs in locales/."""

import ast
import io
import json
import re
import sys
import tempfile
import tokenize
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
        (d / "fr.json").write_text(dump({"Overview": "Aperçu"}), encoding="utf-8")   # without _name
        (d / "en.json").write_text(dump({"_name": "English"}), encoding="utf-8")
        (d / "xx.json").write_text("{kaputt", encoding="utf-8")                      # broken
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
        self.assertEqual(self.resolve(LANG="ja_JP.UTF-8"), "en")   # language without a catalog
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


class TestMessages(Fixture):
    """Messages of the daemon: English template plus arguments; the client renders them in its language."""

    def setUp(self):
        super().setUp()
        (self.dir / "de.json").write_text(json.dumps({
            "_name": "Deutsch", "Value {key} is too high": "Wert {key} ist zu hoch",
            "Manual: {what}": "Manuell: {what}", "GPU clock {value}": "GPU-Takt {value}",
            "Default": "Standard", "Profile {name}": "Profil {name}", "Bad {x}": "Kaputt {y}"}, ensure_ascii=False),
            encoding="utf-8")

    def render_de(self, data):
        i18n.set_language("de", self.dir)
        return i18n.message(data)

    def test_str_is_english_text(self):
        self.assertEqual(str(i18n.Msg("Value {key} is too high", key="sclk")), "Value sclk is too high")
        self.assertEqual(str(i18n.Msg("Plain text")), "Plain text")

    def test_to_json_has_template_and_arguments(self):
        m = i18n.Msg("Value {key} is too high", key="sclk")
        self.assertEqual(m.to_json(), {"tpl": "Value {key} is too high", "args": {"key": "sclk"}})
        json.dumps(m.to_json())   # must be JSON-serializable

    def test_client_renders_in_its_language_and_falls_back_to_english(self):
        data = i18n.Msg("Value {key} is too high", key="sclk").to_json()
        self.assertEqual(self.render_de(data), "Wert sclk ist zu hoch")
        i18n.set_language("en", self.dir)
        self.assertEqual(i18n.message(data), "Value sclk is too high")
        i18n.set_language("de", self.dir)
        self.assertEqual(i18n.message(i18n.Msg("Not in catalog {n}", n=3).to_json()), "Not in catalog 3")

    def test_nested_messages(self):
        inner = i18n.Msg("GPU clock {value}", value=2300)
        outer = i18n.Msg("Manual: {what}", what=inner)
        self.assertEqual(str(outer), "Manual: GPU clock 2300")
        self.assertEqual(self.render_de(outer.to_json()), "Manuell: GPU-Takt 2300")

    def test_lists_are_joined_with_comma(self):
        items = [i18n.Msg("GPU clock {value}", value=2300), i18n.Msg("GPU clock {value}", value=1000), "plain"]
        outer = i18n.Msg("Manual: {what}", what=items)
        self.assertEqual(str(outer), "Manual: GPU clock 2300, GPU clock 1000, plain")
        self.assertEqual(self.render_de(outer.to_json()), "Manuell: GPU-Takt 2300, GPU-Takt 1000, plain")
        self.assertEqual(str(i18n.Msg("Values {v}", v=["a", "b"])), "Values a, b")

    def test_builtin_profile_name_is_translatable(self):
        m = i18n.Msg("Profile {name}", name=i18n.Msg("Default"))
        self.assertEqual(str(m), "Profile Default")
        self.assertEqual(self.render_de(m.to_json()), "Profil Standard")
        self.assertEqual(self.render_de(i18n.Msg("Profile {name}", name="KI").to_json()), "Profil KI")

    def test_bad_translation_falls_back_to_english(self):
        self.assertEqual(self.render_de(i18n.Msg("Bad {x}", x=1).to_json()), "Bad 1")

    def test_message_accepts_plain_text_and_garbage(self):
        self.assertEqual(i18n.message("just text"), "just text")
        self.assertEqual(i18n.message(None), "")
        self.assertEqual(i18n.message({"no": "template"}), "{'no': 'template'}")
        self.assertEqual(i18n.message({"tpl": "Hello {x}"}), "Hello {x}")   # without arguments it stays as it is

    def test_user_text_is_never_used_as_format_string(self):
        evil = "{0.__class__}{key}"
        m = i18n.Msg("Value {key} is too high", key=evil)
        self.assertEqual(str(m), f"Value {evil} is too high")
        self.assertEqual(self.render_de(m.to_json()), f"Wert {evil} ist zu hoch")

    def test_msg_error_is_a_value_error_with_english_text(self):
        e = i18n.MsgError("Value {key} is too high", key="sclk")
        self.assertIsInstance(e, ValueError)
        self.assertEqual(str(e), "Value sclk is too high")
        self.assertEqual(e.msg.to_json()["tpl"], "Value {key} is too high")

    def test_field_helpers_prefer_structured_message(self):
        resp = {"error": "Value sclk is too high",
                "error_msg": i18n.Msg("Value {key} is too high", key="sclk").to_json(),
                "errors": ["a", "b"], "errors_msg": [i18n.Msg("GPU clock {value}", value=1).to_json(),
                                                      i18n.Msg("GPU clock {value}", value=2).to_json()]}
        i18n.set_language("de", self.dir)
        self.assertEqual(i18n.message_field(resp, "error"), "Wert sclk ist zu hoch")
        self.assertEqual(i18n.message_list(resp, "errors"), ["GPU-Takt 1", "GPU-Takt 2"])
        # old daemon without *_msg: the plain text
        self.assertEqual(i18n.message_field({"error": "old text"}, "error"), "old text")
        self.assertEqual(i18n.message_list({"errors": ["x", "y"]}, "errors"), ["x", "y"])
        self.assertEqual(i18n.message_field({}, "error"), "")
        self.assertEqual(i18n.message_list({}, "errors"), [])
        # lengths do not match: better the plain texts than a wrong assignment
        self.assertEqual(i18n.message_list({"errors": ["x", "y"], "errors_msg": [resp["errors_msg"][0]]}, "errors"), ["x", "y"])


def _tokens(text):
    """Placeholders ({name}, %1) and HTML tags of a message, sorted."""
    return sorted(re.findall(r"\{[A-Za-z_0-9]*\}|%\d|</?[a-z]+>", text))


class TestRealCatalogs(unittest.TestCase):
    """The bundled files in locales/ must follow the same rules for all languages."""

    @classmethod
    def setUpClass(cls):
        cls.files = sorted((ROOT / "locales").glob("*.json"))

    def read(self, path):
        def no_duplicates(pairs):
            keys = [k for k, _ in pairs]
            dup = {k for k in keys if keys.count(k) > 1}
            self.assertFalse(dup, f"{path.name}: duplicate keys {sorted(dup)}")
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
                self.assertTrue(v.strip(), f"{f.name}: empty translation for {k!r}")

    def test_placeholders_and_markup_match_source_text(self):
        for f in self.files:
            for k, v in self.read(f).items():
                if k == "_name":
                    continue
                self.assertEqual(_tokens(k), _tokens(v), f"{f.name}: {k!r} -> {v!r}")

    def test_no_translation_equals_its_key(self):
        # An entry equal to the source text is superfluous: if it is missing, the same text appears.
        for f in self.files:
            if f.stem == "en":
                continue
            for k, v in self.read(f).items():
                if k != "_name":
                    self.assertNotEqual(k, v, f"{f.name}: {k!r} is untranslated (remove the entry)")


GERMAN_LETTERS = re.compile(r"[äöüÄÖÜß]")
# Source texts that read the same in German: they need no entry in de.json.
SAME_IN_GERMAN = {
    "Auto", "Sensor", "Governor", "Turbo Boost", "Energy Performance Preference",
    "GPU max %1 MHz", "VRAM max %1 MHz", "CPU max %1 MHz", "Power %1 W", "EPP %1", "Governor %1",
    "Max %1 MHz · ", "max %1 MHz", "max %1", "Limit %1 W", "VRAM %1 MHz", "Junction %1 · Mem %2", "LACT: %1",
    "CPU   {model}",
    # Messages of the daemon that read the same in German
    "Turbo {value}", "EPP {value}", "Governor {value}", "Governor: {reason}", "EPP: {reason}", "Turbo: {reason}",
    "{reason}", "{key} {value}",
}
QML_FILES = sorted((ROOT / "gui" / "qml").glob("*.qml")) + [ROOT / "gui" / "qml" / "Fmt.js"]
PY_FILES = sorted((ROOT / "gui").glob("*.py")) + [ROOT / "hwpanelctl.py", ROOT / "hwpaneld.py"]
QSTR = re.compile(r'\bqsTr\(\s*"((?:[^"\\]|\\.)*)"')


def qml_texts():
    """All source texts of qsTr() in QML and JS: text -> files."""
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
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if name in ("tr", "Msg", "MsgError"):   # Msg/MsgError: messages of the daemon
                yield node.args[0]


def python_texts(files=None):
    """All source texts of tr(...) in Python files: text -> files."""
    out = {}
    for f in files or PY_FILES:
        for arg in _tr_calls(ast.parse(f.read_text(encoding="utf-8"))):
            out.setdefault(arg.value, []).append(f.name)
    return out


class TestCatalogCoverage(unittest.TestCase):
    """The German texts must not be in the source code, and the catalog must contain exactly the texts that are used."""

    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / "locales" / "de.json").read_text(encoding="utf-8"))
        cls.de = {k: v for k, v in data.items() if k != "_name"}
        cls.used = {**qml_texts(), **python_texts()}

    def test_every_source_text_has_a_german_translation(self):
        missing = sorted(t for t in self.used if t not in self.de and t not in SAME_IN_GERMAN)
        self.assertEqual(missing, [], "missing from locales/de.json (or belongs in SAME_IN_GERMAN)")

    def test_same_in_german_list_is_current(self):
        self.assertEqual(sorted(t for t in SAME_IN_GERMAN if t not in self.used), [],
                         "no longer occurs in the source")
        self.assertEqual(sorted(t for t in SAME_IN_GERMAN if t in self.de), [],
                         "in the list and in the catalog: remove one of the two")

    def test_catalog_has_no_unused_entries(self):
        unused = sorted(k for k in self.de if k not in self.used)
        self.assertEqual(unused, [], "no longer occurs in the source")

    def test_no_german_text_left_in_qml_outside_qstr(self):
        for f in QML_FILES:
            code = QSTR.sub('qsTr("")', f.read_text(encoding="utf-8"))
            code = re.sub(r"//.*", "", code)
            for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', code):
                self.assertIsNone(GERMAN_LETTERS.search(lit), f"{f.name}: {lit!r} belongs in qsTr()")

    def test_no_german_text_left_in_gui_python_outside_tr(self):
        allowed_prefix = "[Desktop Entry]"   # template of the autostart file deliberately contains Comment[de]
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
                                      f"{f.name}:{node.lineno}: {node.value!r} belongs in tr()")


# Words that exist only in German (case-sensitive on purpose: "MIT license" or "DES" must not match).
_GERMAN_WORDS = ("der das dem ein eine einen einem einer eines und oder nicht ist sind wird werden für mit zum zur bei beim "
                 "nach über auch nur noch kein keine wenn dann weil damit sonst aber jede jeder jedes dass ohne gibt gilt "
                 "muss darf kann soll steht gehört sich dieser diese dieses wieder immer").split()
GERMAN_WORDS = re.compile(r"\b(?:%s)\b" % "|".join(f"{w}|{w.capitalize()}" for w in _GERMAN_WORDS))
SOURCE_GLOBS = ("*.py", "gui/*.py", "tests/*.py", "gui/qml/*.qml", "gui/qml/*.js", "install.sh", "hwpanel.service")


def source_files():
    return [f for pattern in SOURCE_GLOBS for f in sorted(ROOT.glob(pattern))]


def comments(path):
    """(line, text) of every comment and docstring in a source file."""
    src = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                yield tok.start[0], tok.string
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and ast.get_docstring(node, clean=False):
                yield node.body[0].lineno, ast.get_docstring(node, clean=False)
        return
    if path.suffix in (".qml", ".js"):   # strings are matched first, so a "//" inside one is not taken for a comment
        pattern = r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|(//[^\n]*|(?s:/\*.*?\*/))'
    else:   # shell and systemd unit: "#" starting a word, but not the "#!" of a shebang
        pattern = r"(?<!\S)(#(?!!)[^\n]*)"
    for m in re.finditer(pattern, src):
        if m.group(1):
            yield src.count("\n", 0, m.start(1)) + 1, m.group(1)


def looks_german(text):
    return bool(GERMAN_LETTERS.search(text) or GERMAN_WORDS.search(text))


# Number of required arguments of the assertion methods; the argument after them is the failure message.
ASSERT_ARITY = {"assertTrue": 1, "assertFalse": 1, "assertIsNone": 1, "assertIsNotNone": 1,
                "assertEqual": 2, "assertNotEqual": 2, "assertIn": 2, "assertNotIn": 2, "assertIs": 2, "assertIsNot": 2,
                "assertGreater": 2, "assertGreaterEqual": 2, "assertLess": 2, "assertLessEqual": 2,
                "assertIsInstance": 2, "assertNotIsInstance": 2, "assertCountEqual": 2, "assertRegex": 2,
                "assertNotRegex": 2, "assertAlmostEqual": 2, "skipIf": 1, "skipUnless": 1, "fail": 0, "skipTest": 0}


def messages(tree):
    """(line, text) of the texts that developers see: failure messages, skip reasons, AssertionError and print output.
    The expected values of the assertions are not included: tests may check German output on purpose."""
    for node in ast.walk(tree):
        found = []
        if isinstance(node, ast.Assert) and node.msg is not None:
            found.append(node.msg)
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ASSERT_ARITY:
                n = ASSERT_ARITY[name]
                found += node.args[n:n + 1] + [k.value for k in node.keywords if k.arg in ("msg", "reason")]
            elif name in ("print", "AssertionError"):
                found += node.args
        for m in found:
            for part in ast.walk(m):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    yield part.lineno, part.value


class TestSourceLanguage(unittest.TestCase):
    """Comments and docstrings are English, so that contributors from anywhere can read the code.
    German belongs in locales/de.json and in what the tests expect, not in comments.

    The detector finds umlauts and common German function words, so full sentences are caught;
    a lone German noun in a very short comment can slip through."""

    def test_comments_and_docstrings_are_english(self):
        found = [f"{f.relative_to(ROOT)}:{line}: {text.strip()[:70]!r}"
                 for f in source_files() for line, text in comments(f) if looks_german(text)]
        self.assertEqual(found, [], "German comments or docstrings (translate them to English)")

    def test_the_check_sees_every_kind_of_source_file(self):
        # a typo in a glob or a broken extractor must not turn the check above into a silent pass
        seen = {f.suffix: 0 for f in source_files()}
        for f in source_files():
            seen[f.suffix] += sum(1 for _ in comments(f))
        self.assertEqual(sorted(seen), [".js", ".py", ".qml", ".service", ".sh"])
        self.assertEqual([s for s, n in seen.items() if n == 0], [])
        names = {str(f.relative_to(ROOT)) for f in source_files()}
        self.assertLessEqual({"hwpaneld.py", "hwpanelctl.py", "hwpanel_i18n.py", "gui/backend.py", "gui/qml/Theme.qml",
                              "gui/qml/Fmt.js", "tests/test_i18n.py"}, names)

    def test_the_detector_recognizes_german(self):
        for text in ("# Lüfter zurück auf Automatik", "# wird nicht geschrieben", "// Der Rand", "# bei Fehler: sonst nichts",
                     '"""Fehlt ein Eintrag, erscheint der englische Text."""'):
            self.assertTrue(looks_german(text), text)
        for text in ("# fan back to automatic", "# MIT license, DES cipher", "// the border", "# Hardening: only options from systemd 245"):
            self.assertFalse(looks_german(text), text)

    def test_the_extractors_find_comments_in_every_syntax(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.py").write_text('"""doc"""\nx = "# not a comment"  # real\n', encoding="utf-8")
            (d / "a.qml").write_text('Item { text: "// not a comment"  // real\n    /* block\n comment */ }\n', encoding="utf-8")
            (d / "a.sh").write_text("#!/bin/sh\nprintf '#!/bin/sh'  # real\n# whole line\n", encoding="utf-8")
            self.assertEqual(list(comments(d / "a.py")), [(2, "# real"), (1, "doc")])
            self.assertEqual(list(comments(d / "a.qml")), [(1, "// real"), (2, "/* block\n comment */")])
            self.assertEqual(list(comments(d / "a.sh")), [(2, "# real"), (3, "# whole line")])

    def test_assertion_messages_and_script_output_are_english(self):
        found = [f"tests/{f.name}:{line}: {text.strip()[:70]!r}"
                 for f in sorted((ROOT / "tests").glob("*.py"))
                 for line, text in messages(ast.parse(f.read_text(encoding="utf-8"))) if looks_german(text)]
        self.assertEqual(found, [], "German texts in failure messages or script output (translate them to English)")

    def test_the_message_extractor_takes_messages_and_leaves_expected_values(self):
        sample = (
            'import unittest\n'
            '@unittest.skipIf(cond, "reason one")\n'
            'class T(unittest.TestCase):\n'
            '    def test(self):\n'
            '        self.assertEqual(a, "Übersicht", "message two")\n'
            '        self.assertTrue(a, msg=f"message {three!r}")\n'
            '        self.assertIn("Lüfter", a)\n'
            '        assert a, "message four"\n'
            '        raise AssertionError("message five")\n'
            '        print("output six")\n'
            '        self.fail("message seven")\n')
        self.assertEqual(sorted(t for _, t in messages(ast.parse(sample))),
                         sorted(["reason one", "message two", "message ", "message four", "message five", "output six",
                                 "message seven"]))   # the German expected values of the assertions are not messages


if __name__ == "__main__":
    unittest.main()
