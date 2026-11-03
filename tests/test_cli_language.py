"""Language choice of the command line: --lang, HWPANEL_LANG and system language."""

import contextlib
import io
import os
import re
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import hwpanel_i18n as i18n  # noqa: E402
import hwpaneld  # noqa: E402
import hwpanelctl  # noqa: E402
from test_hwpaneld import Base  # noqa: E402

# typically German words and umlauts of the CLI output: none of them may appear in English
GERMAN = re.compile(r"[äöüÄÖÜß]|\b(Auslastung|Takt|Leistung|Lüfter\w*|Kurve|Grenzen|Punkte|Einstellungen|belegt|Ziel|gesetzt|"
                    r"Modus|eingebaut|schaltbar|Mindestwerte|Sicherung|unbekannt|Messwerte|Fehler|Hinweis|"
                    r"Schutz|Maximaltakt|Profilname|Treiberautomatik|manuell|automatik|Schutzregel|abgelehnt|ja|nein)\b")

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
        """Text with which 'hwpanelctl status' ends when the daemon is missing (environment: only the variables passed)."""
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


class TestCliOutput(Base):
    """Output of the CLI against a daemon on fake hardware, in both languages."""

    def setUp(self):
        super().setUp()
        self.sock_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.sock_dir.name, "t.sock")
        self.srv = hwpaneld.make_server(self.hw, self.path)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self._sock = hwpanelctl.SOCKET_PATH
        hwpanelctl.SOCKET_PATH = self.path

    def tearDown(self):
        hwpanelctl.SOCKET_PATH = self._sock
        self.srv.shutdown()
        self.srv.server_close()
        self.sock_dir.cleanup()
        i18n.set_language("en")
        super().tearDown()

    def cli(self, lang, *args):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(sys, "argv", ["hwpanelctl", "--lang", lang, *args]), contextlib.redirect_stdout(out):
            rc = hwpanelctl.main()
        return rc, out.getvalue()

    def exit_text(self, lang, *args):
        with self.assertRaises(SystemExit) as cm:
            self.cli(lang, *args)
        return cm.exception.code

    # ---- Output

    def test_english_output_has_no_german_text(self):
        for args in (("status",), ("info",), ("gpu", "--sclk", "2300"), ("cpu", "--turbo", "off"),
                     ("fan", "curve", "30:40,50:55,80:90"), ("status",), ("fan", "auto"),
                     ("apply", "KI"), ("profiles",), ("autostart",), ("autostart", "KI"), ("autostart", "none"),
                     ("reset", "all")):
            rc, out = self.cli("en", *args)
            self.assertEqual(rc, 0, f"{args}: {out}")
            self.assertIsNone(GERMAN.search(out), f"{args}: deutscher Text in der englischen Ausgabe:\n{out}")

    def test_english_status_and_info_lines(self):
        _, out = self.cli("en", "status")
        for phrase in ("GPU   Load ", "(GPU / VRAM)", "Power ", " RPM (", "CPU   Load ", "Clock Ø ", " MiB used   Swap ",
                       "Settings       GPU max ", "power ", "turbo on", "governor ", "Fan automatic (driver)",
                       "Profile        "):
            self.assertIn(phrase, out)
        _, out = self.cli("en", "info")
        for phrase in ("Limits: GPU clock ", "VRAM clock ", "threads, ", "max clock ", "Governors: ", "Turbo switchable: yes",
                       "Fan sensors: edge, junction, mem", " points   Protection: 100 % from ", "minimum values ",
                       "Profiles: Standard (built in), "):
            self.assertIn(phrase, out)

    def test_german_output_is_unchanged(self):
        _, out = self.cli("de", "status")
        for phrase in ("GPU   Auslastung ", "Takt ", "(GPU / VRAM)   Leistung ", "Temp Edge ", "   Lüfter ", " RPM (",
                       "CPU   Last ", "Takt Ø ", " MiB belegt   Swap ", "Einstellungen  GPU max ", "), Power ",
                       "Turbo an, EPP ", "Governor ", "Lüfter Automatik (Treiber)", "Profil         "):
            self.assertIn(phrase, out)
        _, out = self.cli("de", "info")
        for phrase in ("Grenzen: GPU-Takt ", "VRAM-Takt ", "Threads, ", "Max-Takt ", "Governor: ", "Turbo schaltbar: ja",
                       "Lüfter Sensoren: edge, junction, mem", " Punkte   Schutz: 100 % ab ", "Mindestwerte ",
                       "Profile: Standard (eingebaut), "):
            self.assertIn(phrase, out)

    def test_curve_and_fan_state_lines_in_both_languages(self):
        self.io.files[hwpaneld_hwmon() + "/temp1_input"] = "41000"
        _, out = self.cli("en", "fan", "curve", "30:40,40:50,50:60,60:70,70:80,80:90")
        self.assertIn("Fan curve (edge): 30 °C:40 %", out)
        _, out = self.cli("en", "status")
        self.assertIn("Fan control  sensor edge ", out)
        self.assertIn("-> target ", out)
        _, out = self.cli("de", "status")
        self.assertIn("Lüfter-Regelung  Sensor edge ", out)
        self.assertIn("-> Ziel ", out)

    def test_daemon_errors_are_shown_in_the_chosen_language(self):
        rc, out = self.cli("en", "gpu", "--sclk", "9999")
        self.assertEqual((rc, out), (1, "Error: sclk_max=9999 is outside the allowed range 500-2679\n"))
        rc, out = self.cli("de", "gpu", "--sclk", "9999")
        self.assertEqual((rc, out), (1, "Fehler: sclk_max=9999 außerhalb des erlaubten Bereichs 500-2679\n"))
        rc, out = self.cli("de", "fan", "curve", "30:0,90:40")
        self.assertEqual(rc, 1)
        self.assertIn("Schutzregel", out)
        rc, out = self.cli("en", "fan", "curve", "30:0,90:40")
        self.assertIn("protection rule", out)

    def test_daemon_notes_are_shown_in_the_chosen_language(self):
        for i in range(8):
            self.io.files[f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_governor"] = "performance"
        rc, out = self.cli("en", "cpu", "--epp", "power")
        self.assertEqual(rc, 0)
        self.assertIn("Note: EPP skipped: governor 'performance' ignores EPP", out)
        rc, out = self.cli("de", "cpu", "--epp", "power")
        self.assertIn("Hinweis: EPP übersprungen: Governor 'performance' ignoriert EPP", out)

    def test_fan_state_and_fan_error_in_status(self):
        from test_hwpaneld import HWMON
        self.io.files[HWMON + "/temp1_input"] = "41000"
        self.cli("en", "fan", "curve", "30:40,40:50,50:60,60:70,70:80,80:90")
        self.assertIn("mode manual", self.cli("en", "status")[1])
        self.assertIn("Modus manuell", self.cli("de", "status")[1])
        self.io.files[HWMON + "/pwm1_enable"] = "2"
        self.assertIn("mode automatic", self.cli("en", "status")[1])
        self.assertIn("Modus automatik", self.cli("de", "status")[1])
        self.io.files.pop(HWMON + "/temp1_input")
        self.hw.fan_step(now=1000)
        self.assertIn("Error: sensor not readable", self.cli("en", "status")[1])
        self.assertIn("Fehler: Sensor nicht lesbar", self.cli("de", "status")[1])

    def test_fan_mode_names(self):
        i18n.set_language("de")
        self.assertEqual([hwpanelctl.fan_mode_text(c) for c in ("manual", "automatic", "off", None, "weird")],
                         ["manuell", "automatik", "aus", "-", "weird"])
        i18n.set_language("en")
        self.assertEqual([hwpanelctl.fan_mode_text(c) for c in ("manual", "automatic", "off")], ["manual", "automatic", "off"])

    def test_results_from_an_older_daemon_without_templates(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            i18n.set_language("en")
            rc = hwpanelctl.show_result({"ok": False, "errors": ["old plain text"], "notes": ["a note"]})
            rc2 = hwpanelctl.show_result({"ok": False, "error": "old error"})
        self.assertEqual((rc, rc2), (1, 1))
        self.assertEqual(out.getvalue(), "Note: a note\nError: old plain text\nError: old error\n")

    def test_result_prefixes_follow_the_language(self):
        rc, out = self.cli("en", "gpu", "--sclk", "9999")     # above the default: daemon rejects
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("Error:"), out)
        rc, out = self.cli("de", "gpu", "--sclk", "9999")
        self.assertTrue(out.startswith("Fehler:"), out)

    # ---- Help and input errors

    def test_help_texts_in_both_languages(self):
        for lang, main_help, gpu_help in (("en", "show measurements", "GPU maximum clock"),
                                          ("de", "Messwerte anzeigen", "GPU-Maximaltakt")):
            out = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(sys, "argv", ["hwpanelctl", "--lang", lang, "--help"]), \
                    contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                hwpanelctl.main()
            self.assertIn(main_help, out.getvalue(), lang)
            out = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(sys, "argv", ["hwpanelctl", "--lang", lang, "gpu", "--help"]), \
                    contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                hwpanelctl.main()
            self.assertIn(gpu_help, out.getvalue(), lang)

    def test_english_help_has_no_german_text(self):
        for args in ([], ["status"], ["gpu"], ["cpu"], ["fan"], ["save"], ["autostart"], ["apply"]):
            out = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(sys, "argv", ["hwpanelctl", "--lang", "en", *args, "--help"]), \
                    contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                hwpanelctl.main()
            self.assertIsNone(GERMAN.search(out.getvalue()), f"{args}:\n{out.getvalue()}")

    def test_input_errors_in_both_languages(self):
        self.assertIn("Give the curve as TEMP:PERCENT", self.exit_text("en", "fan", "curve", "kaputt"))
        self.assertIn("Kurve im Format TEMP:PROZENT", self.exit_text("de", "fan", "curve", "kaputt"))
        self.assertIn("needs a curve", self.exit_text("en", "fan", "curve"))
        self.assertIn("wird eine Kurve benötigt", self.exit_text("de", "fan", "curve"))


def hwpaneld_hwmon():
    from test_hwpaneld import HWMON
    return HWMON


if __name__ == "__main__":
    unittest.main()
