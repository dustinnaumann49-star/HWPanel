"""Schutz gegen versehentliches Aufweichen oder Überhärten von hwpanel.service."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def unit_settings():
    """Alle aktiven Zeilen 'Schlüssel=Wert' der Unit (Kommentare ignoriert), Schlüssel -> Liste der Werte."""
    out = {}
    for line in (ROOT / "hwpanel.service").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z]+)=(.*)$", line.strip())
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


class TestServiceUnit(unittest.TestCase):
    def setUp(self):
        self.u = unit_settings()

    def test_baseline_hardening_present(self):
        for key, value in (("NoNewPrivileges", "yes"), ("ProtectSystem", "strict"),
                           ("ProtectHome", "yes"), ("PrivateTmp", "yes"),
                           ("RestrictAddressFamilies", "AF_UNIX")):
            self.assertEqual(self.u.get(key), [value], key)

    def test_sysfs_stays_writable(self):
        # ProtectKernelTunables (auch mit 'read-only') würde /sys schreibgeschützt mounten
        self.assertNotIn("ProtectKernelTunables", self.u)

    def test_watchdog_and_fan_fallback(self):
        self.assertEqual(self.u.get("NotifyAccess"), ["main"])
        self.assertIn("WatchdogSec", self.u)
        stop = " ".join(self.u.get("ExecStopPost", []))
        self.assertIn("pwm1_enable", stop)
        self.assertRegex(stop, r"echo 2\b")

    def test_daemon_needs_are_allowed(self):
        src = (ROOT / "hwpaneld.py").read_text(encoding="utf-8")
        caps = " ".join(self.u.get("CapabilityBoundingSet", []))
        filt = " ".join(self.u.get("SystemCallFilter", []))
        if "os.chown(" in src:
            self.assertIn("CAP_CHOWN", caps, "Socket-Gruppe setzen braucht CAP_CHOWN")
            self.assertIn("@chown", filt, "Socket-Gruppe setzen braucht die chown-Syscalls")
        self.assertIn("StateDirectory", self.u)
        self.assertIn("RuntimeDirectory", self.u)


if __name__ == "__main__":
    unittest.main()
