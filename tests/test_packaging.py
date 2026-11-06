#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle
"""The Arch package files (packaging/arch) stay in step with the project: version, files, unit paths and socket group."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging" / "arch"


def read(path):
    return Path(path).read_text(encoding="utf-8")


class TestArchPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (PKG / "PKGBUILD").exists(), "packaging/arch/PKGBUILD is missing"
        cls.pkgbuild = read(PKG / "PKGBUILD")
        cls.message = read(PKG / "hwpanel.install")

    def test_the_package_version_is_the_version_of_the_daemon(self):
        daemon = re.search(r'^VERSION = "([^"]+)"', read(ROOT / "hwpaneld.py"), re.M).group(1)
        pkgver = re.search(r"^pkgver=(\S+)$", self.pkgbuild, re.M).group(1)
        self.assertEqual(pkgver, daemon, "bump pkgver (and the checksum) together with VERSION in hwpaneld.py")

    def test_the_source_is_pinned_by_a_checksum(self):
        self.assertRegex(self.pkgbuild, r"(?m)^sha256sums=\('[0-9a-f]{64}'\)$")
        self.assertNotRegex(self.pkgbuild, r"sha256sums=\('0{64}'\)", "the placeholder checksum is still there")

    def test_the_license_is_the_one_of_the_project(self):
        self.assertRegex(self.pkgbuild, r"(?m)^license=\('GPL-3\.0-or-later'\)$")

    def test_everything_install_sh_installs_is_packaged(self):
        # a new module that only install.sh knows about would be missing from the package
        installed = re.findall(r'install -m \d+ (\S+) "\$LIB/', read(ROOT / "install.sh"))
        self.assertIn("hwpaneld.py", installed)
        for name in installed + ["locales", "gui"]:
            self.assertIn(name, self.pkgbuild, name)

    def test_the_unit_has_no_usr_local_path_once_the_package_has_rewritten_it(self):
        unit = read(ROOT / "hwpanel.service")
        self.assertIn("/usr/local/lib/hwpanel", unit)   # otherwise the rewrite in the PKGBUILD does nothing
        self.assertNotIn("/usr/local", unit.replace("/usr/local/lib/hwpanel", "/usr/lib/hwpanel"))
        self.assertIn("s|/usr/local/lib/hwpanel|", self.pkgbuild)

    def test_the_socket_group_is_created_used_and_explained(self):
        group = re.search(r'"socket_group": "([^"]+)"', self.pkgbuild).group(1)
        self.assertIn(f"g {group} -", self.pkgbuild)           # sysusers.d creates it
        self.assertIn(f"usermod -aG {group}", self.message)    # and the user is told how to join it

    def test_the_default_config_has_the_same_keys_as_the_one_install_sh_writes(self):
        packaged = re.findall(r'"(\w+)":', re.search(r"f /var/lib/hwpanel/config\.json.*", self.pkgbuild).group(0))
        from_installer = re.findall(r'"(\w+)":', re.search(r"printf '\{.*socket_group.*", read(ROOT / "install.sh")).group(0))
        self.assertEqual(packaged, from_installer)

    def test_the_message_says_how_to_start_the_daemon_and_warns_about_lact(self):
        self.assertIn("systemctl enable --now hwpanel", self.message)
        self.assertIn("lactd", self.message)

    def test_the_gui_stays_optional(self):
        self.assertRegex(self.pkgbuild, r"(?s)optdepends=\([^)]*pyside6")
        # the package puts an icon into the hicolor theme, namcap demands the dependency for that
        self.assertRegex(self.pkgbuild, r"depends=\('python' 'systemd' 'hicolor-icon-theme'\)")

    def test_srcinfo_describes_the_same_package_as_the_pkgbuild(self):
        # the AUR reads .SRCINFO, not the PKGBUILD: a stale one is a classic mistake
        srcinfo = read(PKG / ".SRCINFO")
        expected = {
            "pkgver": re.search(r"(?m)^pkgver=(\S+)$", self.pkgbuild).group(1),
            "pkgrel": re.search(r"(?m)^pkgrel=(\S+)$", self.pkgbuild).group(1),
            "pkgdesc": re.search(r"(?m)^pkgdesc='([^']+)'", self.pkgbuild).group(1),
            "url": re.search(r"(?m)^url='([^']+)'", self.pkgbuild).group(1),
            "license": re.search(r"(?m)^license=\('([^']+)'\)", self.pkgbuild).group(1),
            "sha256sums": re.search(r"sha256sums=\('([0-9a-f]{64})'\)", self.pkgbuild).group(1),
        }
        for key, value in expected.items():
            self.assertRegex(srcinfo, rf"(?m)^\s*{key} = {re.escape(value)}$", key)
        for dependency in ("python", "systemd", "hicolor-icon-theme"):
            self.assertRegex(srcinfo, rf"(?m)^\s*depends = {dependency}$", dependency)

    def test_both_readmes_explain_how_to_build_and_use_the_package(self):
        for name in ("README.md", "README.de.md"):
            text = read(ROOT / name)
            for needle in ("packaging/arch", "makepkg -si", "usermod -aG hwpanel", "/usr/lib/hwpanel"):
                self.assertIn(needle, text, f"{name}: {needle}")

    @unittest.skipUnless(shutil.which("bash"), "bash is not installed")
    def test_the_scripts_are_valid_bash(self):
        for name in ("PKGBUILD", "hwpanel.install"):
            done = subprocess.run(["bash", "-n", str(PKG / name)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")


if __name__ == "__main__":
    unittest.main()
