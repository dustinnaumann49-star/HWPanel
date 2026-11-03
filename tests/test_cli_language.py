"""Sprachwahl der Kommandozeile: --lang, HWPANEL_LANG und Systemsprache."""

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import hwpanel_i18n as i18n  # noqa: E402
import hwpanelctl  # noqa: E402

DAEMON_DOWN_EN = "Daemon is not running (socket missing). Check: systemctl status hwpanel"
DAEMON_DOWN_DE = "Daemon läuft nicht (Socket fehlt). Prüfen: systemctl status hwpanel"


class TestCliLanguage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._sock = hwpanelctl.SOCKET_PATH
        hwpanelctl.SOCKET_PATH = os.path.join(self.tmp.name, "gibt-es-nicht.sock")

    def tearDown(self):
        hwpanelctl.SOCKET_PATH = self._sock
        i18n.set_language("en")
        self.tmp.cleanup()

    def error_text(self, args, **env):
        """Text, mit dem 'hwpanelctl status' endet, wenn der Daemon fehlt (Umgebung: nur die übergebenen Variablen)."""
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "argv", ["hwpanelctl", *args, "status"]):
            with self.assertRaises(SystemExit) as cm:
                hwpanelctl.main()
        return cm.exception.code

    def test_system_language_is_used_by_default(self):
        self.assertEqual(self.error_text([], LANG="de_DE.UTF-8"), DAEMON_DOWN_DE)
        self.assertEqual(self.error_text([], LANG="en_US.UTF-8"), DAEMON_DOWN_EN)

    def test_unknown_system_language_and_c_locale_give_english(self):
        self.assertEqual(self.error_text([], LANG="ja_JP.UTF-8"), DAEMON_DOWN_EN)
        self.assertEqual(self.error_text([], LANG="C"), DAEMON_DOWN_EN)
        self.assertEqual(self.error_text([]), DAEMON_DOWN_EN)

    def test_lang_option_beats_system_language(self):
        self.assertEqual(self.error_text(["--lang", "en"], LANG="de_DE.UTF-8"), DAEMON_DOWN_EN)
        self.assertEqual(self.error_text(["--lang", "de"], LANG="en_US.UTF-8"), DAEMON_DOWN_DE)
        self.assertEqual(self.error_text(["--lang=de"], LANG="C"), DAEMON_DOWN_DE)

    def test_environment_variable_beats_system_language(self):
        self.assertEqual(self.error_text([], HWPANEL_LANG="de", LANG="en_US.UTF-8"), DAEMON_DOWN_DE)
        self.assertEqual(self.error_text([], HWPANEL_LANG="en", LANG="de_DE.UTF-8"), DAEMON_DOWN_EN)

    def test_lang_option_beats_environment_variable(self):
        self.assertEqual(self.error_text(["--lang", "en"], HWPANEL_LANG="de"), DAEMON_DOWN_EN)

    def test_auto_and_empty_follow_the_system(self):
        self.assertEqual(self.error_text(["--lang", "auto"], LANG="de_DE.UTF-8"), DAEMON_DOWN_DE)
        self.assertEqual(self.error_text([], HWPANEL_LANG="", LANG="de_DE.UTF-8"), DAEMON_DOWN_DE)

    def test_unknown_language_gives_english(self):
        self.assertEqual(self.error_text(["--lang", "klingon"], LANG="de_DE.UTF-8"), DAEMON_DOWN_EN)

    def test_help_mentions_the_option_in_the_chosen_language(self):
        import contextlib
        import io
        for lang, text in (("en", "Language of the output"), ("de", "Sprache der Ausgabe")):
            out = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(sys, "argv", ["hwpanelctl", "--lang", lang, "--help"]), \
                    contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                hwpanelctl.main()
            self.assertIn("--lang", out.getvalue(), lang)
            self.assertIn(text, out.getvalue(), lang)


if __name__ == "__main__":
    unittest.main()
