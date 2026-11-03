"""install.sh: Sprache der Meldungen und Hilfe. Nichts davon braucht root und nichts davon installiert etwas."""

import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "install.sh"
GERMAN_LETTERS = re.compile(r"[äöüÄÖÜß]")


def run(*args, **env):
    """install.sh mit genau der übergebenen Umgebung (außer PATH) ausführen."""
    full_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **env}
    return subprocess.run(["bash", str(SCRIPT), *args], env=full_env, capture_output=True, text=True,
                          timeout=30, cwd="/")


class TestHelp(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode, 0)

    def test_help_follows_system_language(self):
        en, de = run("--help", LANG="en_US.UTF-8"), run("--help", LANG="de_DE.UTF-8")
        for r in (en, de):
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--disable-lact", r.stdout)
            self.assertIn("--uninstall", r.stdout)
        self.assertIn("Usage:", en.stdout)
        self.assertIn("Aufruf:", de.stdout)
        self.assertIsNone(GERMAN_LETTERS.search(en.stdout))

    def test_c_locale_and_empty_environment_give_english(self):
        for env in ({}, {"LANG": "C"}, {"LANG": "C.UTF-8"}, {"LC_ALL": "C", "LANG": "de_DE.UTF-8"},
                    {"LANG": "fr_FR.UTF-8"}, {"LANG": "ja_JP.UTF-8"}):
            self.assertIn("Usage:", run("--help", **env).stdout, env)

    def test_priority_like_the_python_side(self):
        self.assertIn("Aufruf:", run("--help", LANGUAGE="de:en", LANG="en_US.UTF-8").stdout)
        self.assertIn("Usage:", run("--help", LANGUAGE="en:de", LANG="de_DE.UTF-8").stdout)
        self.assertIn("Aufruf:", run("--help", LANGUAGE="fr:de", LANG="fr_FR.UTF-8").stdout)    # fr gibt es nicht, de schon
        self.assertIn("Usage:", run("--help", LC_ALL="en_US.UTF-8", LANG="de_DE.UTF-8").stdout)  # LC_ALL gewinnt

    def test_hwpanel_lang_beats_system_language(self):
        self.assertIn("Usage:", run("--help", HWPANEL_LANG="en", LANG="de_DE.UTF-8").stdout)
        self.assertIn("Aufruf:", run("--help", HWPANEL_LANG="de", LANG="en_US.UTF-8").stdout)
        self.assertIn("Aufruf:", run("--help", HWPANEL_LANG="auto", LANG="de_DE.UTF-8").stdout)
        self.assertIn("Usage:", run("--help", HWPANEL_LANG="klingon", LANG="de_DE.UTF-8").stdout)

    def test_short_option(self):
        self.assertIn("Usage:", run("-h", LANG="en_US.UTF-8").stdout)


@unittest.skipIf(os.geteuid() == 0, "als root würde das Skript wirklich installieren")
class TestRootCheck(unittest.TestCase):
    """Ohne root bricht das Skript sofort ab und ändert nichts."""

    def test_message_follows_language(self):
        for args in ((), ("--uninstall",), ("--disable-lact",)):
            en, de = run(*args, LANG="en_US.UTF-8"), run(*args, LANG="de_DE.UTF-8")
            self.assertEqual((en.returncode, de.returncode), (1, 1), args)
            self.assertIn("Please run with sudo", en.stderr)
            self.assertIn("Bitte mit sudo ausführen", de.stderr)
            self.assertEqual((en.stdout, de.stdout), ("", ""))


class TestSource(unittest.TestCase):
    text = SCRIPT.read_text(encoding="utf-8")

    def test_german_text_only_in_second_argument_of_say_or_in_comments(self):
        for n, line in enumerate(self.text.splitlines(), 1):
            if not GERMAN_LETTERS.search(line):
                continue
            stripped = line.strip()
            ok = (stripped.startswith("#") or re.match(r"(say|sayerr)\s+\"", stripped) or stripped.startswith("Comment[de]="))
            self.assertTrue(ok, f"install.sh:{n}: deutscher Text außerhalb von say/sayerr: {line!r}")

    def test_desktop_entry_has_english_and_german_comment(self):
        self.assertIn("Comment=GPU/CPU monitoring and clock limits", self.text)
        self.assertIn("Comment[de]=GPU/CPU-Überwachung und Taktbegrenzung", self.text)


if __name__ == "__main__":
    unittest.main()
