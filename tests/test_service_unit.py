"""Protection against accidentally weakening or over-hardening hwpanel.service."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def unit_settings():
    """All active 'key=value' lines of the unit (comments ignored), key -> list of values."""
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

    def test_description_is_english(self):
        # appears in "systemctl status" for all users and cannot be translated per language
        text = " ".join(self.u.get("Description", []))
        self.assertTrue(text)
        self.assertIsNone(re.search(r"[äöüÄÖÜß]", text), text)

    def test_sysfs_stays_writable(self):
        # ProtectKernelTunables (even with 'read-only') would mount /sys read-only
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
            self.assertIn("CAP_CHOWN", caps, "setting the socket group needs CAP_CHOWN")
            self.assertIn("@chown", filt, "setting the socket group needs the chown syscalls")
        self.assertIn("StateDirectory", self.u)
        self.assertIn("RuntimeDirectory", self.u)


if __name__ == "__main__":
    unittest.main()
