"""Tests für das GUI-Backend (ohne Anzeige, mit Demo-Daemon auf FakeIO).

Benötigt PySide6, sonst werden die Tests übersprungen.
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "gui"))

try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    import backend as be
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:
    from demo_client import DemoClient
    from test_hwpaneld import HWMON


def pump(cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        QCoreApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])

    def setUp(self):
        self.client = DemoClient(duration=300)
        self.be = be.Backend(self.client)
        self.toasts = []
        self.be.toast.connect(lambda t, e: self.toasts.append((t, e)))
        self.assertTrue(pump(lambda: self.be.connected and self.be.info and self.be.history["t"]))

    def tearDown(self):
        self.be.shutdown()
        self.client.close()

    # ---- Daten

    def test_initial_state(self):
        self.assertEqual(self.be.profileNames, ["Standard", "Gaming", "KI"])
        self.assertEqual(self.be.activeProfile, "Standard")
        self.assertIn("limits", self.be.info)
        self.assertEqual(self.be.historyWindow, 300)

    def test_history_view_window_and_downsampling(self):
        b = self.be
        b._samples.clear()
        base = 1_000_000.0
        samples = [{"t": base + i, **{k: 50.0 for k in be.KEYS}} for i in range(3600)]
        samples[1800]["g_junc"] = 99.0  # kurze Spitze
        b._on_history({"samples": samples, "events": []})
        b.setHistoryWindow(3600)
        v = b.history
        self.assertLessEqual(len(v["t"]), be.MAX_POINTS)
        self.assertEqual(max(v["g_junc"]), 99.0, "Spitzen müssen beim Verdichten erhalten bleiben")
        b.setHistoryWindow(60)
        v = b.history
        self.assertEqual(len(v["t"]), 61)
        self.assertEqual(v["t"][-1], base + 3599)

    def test_events_deduplicated_and_windowed(self):
        b = self.be
        b._samples.clear()
        b._events.clear()
        b._event_keys.clear()
        base = 2_000_000.0
        samples = [{"t": base + i, **{k: 1.0 for k in be.KEYS}} for i in range(100)]
        ev = [{"t": base + 10, "text": "Profil KI"}, {"t": base - 5000, "text": "alt"}]
        b._on_history({"samples": samples, "events": ev})
        b._on_history({"samples": [], "events": ev})
        texts = [e["text"] for e in b.history["events"]]
        self.assertEqual(texts, ["Profil KI"])

    def test_missing_values_stay_none(self):
        b = self.be
        b._samples.clear()
        base = 3_000_000.0
        samples = [{"t": base + i, "g_edge": None} for i in range(5)]
        b._on_history({"samples": samples, "events": []})
        self.assertEqual(b.history["g_edge"], [None] * 5)

    # ---- Aktionen

    def test_apply_profile_updates_status_and_toast(self):
        self.be.applyProfile("KI")
        self.assertTrue(pump(lambda: self.be.activeProfile == "KI"))
        self.assertTrue(any("Profil KI angewendet" in t and not e for t, e in self.toasts))
        self.be.applyProfile("Standard")
        self.assertTrue(pump(lambda: self.be.activeProfile == "Standard"))

    def test_manual_settings_and_error_toast(self):
        self.be.setManual({"sclk_max": 2200.0}, {"max_mhz": 3000.0}, {})
        self.assertTrue(pump(lambda: self.be.status.get("settings", {}).get("gpu", {}).get("sclk_max") == 2200))
        self.assertTrue(pump(lambda: self.be.status["settings"]["cpu"].get("max_mhz") == 3000))
        self.assertIsNone(self.be.activeProfile or None)
        self.toasts.clear()
        self.be.setManual({"sclk_max": 99999}, {}, {})  # über dem Standard: muss abgelehnt werden
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        self.assertEqual(self.be.status["settings"]["gpu"]["sclk_max"], 2200)

    def test_reset_all(self):
        self.be.setManual({"sclk_max": 2200}, {}, {"sensor": "edge", "curve": [[30, 40], [80, 90]]})
        self.assertTrue(pump(lambda: self.be.status["settings"]["gpu"]["sclk_max"] == 2200))
        self.assertTrue(pump(lambda: self.be.status["fan"]["mode"] == "curve"))
        self.be.resetAll()
        self.assertTrue(pump(lambda: self.be.status["settings"]["gpu"]["sclk_max"] == 2679))
        self.assertTrue(pump(lambda: self.be.status["fan"]["mode"] == "auto"))
        self.assertEqual(self.be.activeProfile, "Standard")

    def test_save_rename_delete_profile(self):
        self.be.saveProfile("Leise", {"sclk_max": 2000}, {"epp": "power"}, {}, "")
        self.assertTrue(pump(lambda: "Leise" in self.be.profileNames))
        self.assertNotIn("fan", self.be.info["profiles"]["Leise"])
        self.be.saveProfile("Ruhig", {"sclk_max": 2000}, {"epp": "power"}, {}, "Leise")
        self.assertTrue(pump(lambda: "Ruhig" in self.be.profileNames and "Leise" not in self.be.profileNames))
        self.be.deleteProfile("Ruhig")
        self.assertTrue(pump(lambda: "Ruhig" not in self.be.profileNames))

    def test_rename_to_rejected_name_keeps_original(self):
        profiles = self.client.hw.profiles
        before = dict(profiles["KI"])
        self.toasts.clear()
        self.be.saveProfile("Standard", {"sclk_max": 2000}, {}, {}, "KI")   # reservierter Name
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        pump(lambda: False, timeout=0.5)   # Zeit für einen (fälschlichen) Löschbefehl
        self.assertEqual(profiles.get("KI"), before)
        self.assertIn("KI", self.be.profileNames)

    def test_rename_moves_startup_profile(self):
        self.be.setStartupProfile("KI")
        self.assertTrue(pump(lambda: self.be.startupProfile == "KI"))
        self.be.saveProfile("KI2", {"sclk_max": 2300}, {}, {}, "KI")
        self.assertTrue(pump(lambda: self.be.startupProfile == "KI2"))
        self.assertNotIn("KI", self.client.hw.profiles)
        self.assertEqual(self.client.hw.cfg["autostart_profile"], "KI2")

    def test_rename_keeps_other_startup_profile(self):
        self.be.setStartupProfile("Gaming")
        self.assertTrue(pump(lambda: self.be.startupProfile == "Gaming"))
        self.be.saveProfile("KI2", {"sclk_max": 2300}, {}, {}, "KI")
        self.assertTrue(pump(lambda: "KI2" in self.be.profileNames and "KI" not in self.be.profileNames))
        self.assertEqual(self.be.startupProfile, "Gaming")

    def test_rename_shows_only_the_save_toast(self):
        self.toasts.clear()
        self.be.saveProfile("Ruhig", {}, {}, {}, "KI")
        self.assertTrue(pump(lambda: "Ruhig" in self.be.profileNames and "KI" not in self.be.profileNames))
        self.assertEqual(self.toasts, [("Profil Ruhig gespeichert", False)])

    def test_profile_name_error(self):
        err = self.be.profileNameError
        self.assertEqual(err("Leise", ""), "")
        self.assertEqual(err("Größe 2", ""), "", "Umlaute sind wie im Daemon erlaubt")
        self.assertEqual(err("", ""), "", "leer: Speichern ist ohnehin gesperrt")
        self.assertEqual(err("KI", "KI"), "", "Bearbeiten ohne Umbenennen")
        for bad, editing in (("Leise (Nacht)", ""), ("standard", ""), ("KI", ""),
                             ("KI", "Gaming"), ("x" * 33, ""), (".punkt", "")):
            self.assertNotEqual(err(bad, editing), "", bad)

    def test_profile_name_check_matches_daemon(self):
        hw = self.client.hw
        for name in ("Leise", "Größe 2", "a.b-c_d", "Leise (Nacht)", "-x", "x" * 32, "x" * 33,
                     "Standard", "standard", "a/b"):
            try:
                hw._check_name(name)
                daemon_ok = True
            except ValueError:
                daemon_ok = False
            self.assertEqual(self.be.profileNameError(name, "") == "", daemon_ok, name)

    def test_manual_fan_curve_and_auto(self):
        curve = {"sensor": "junction", "curve": [[40.0, 35.0], [70.0, 70.0], [90.0, 100.0]]}
        self.be.setManual({}, {}, curve)
        self.assertTrue(pump(lambda: self.be.status["fan"]["mode"] == "curve"))
        self.assertEqual(self.be.status["fan"]["sensor"], "junction")
        self.assertEqual(self.be.status["settings"]["fan"]["curve"], [[40, 35], [70, 70], [90, 100]])
        self.assertEqual(self.client.io.files[HWMON + "/pwm1_enable"], "1")
        # leere Fan-Angabe = Automatik
        self.be.setManual({}, {}, {})
        self.assertTrue(pump(lambda: self.be.status["fan"]["mode"] == "auto"))
        self.assertIsNone(self.be.status["settings"]["fan"])

    def test_invalid_fan_curve_is_rejected(self):
        self.toasts.clear()
        # bei 80 °C nur 40 %: verletzt die Schutzregel (mind. 50 %)
        self.be.setManual({}, {}, {"sensor": "edge", "curve": [[30, 20], [90, 40]]})
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        self.assertEqual(self.be.status["fan"]["mode"], "auto")

    def test_save_profile_with_fan(self):
        fan = {"sensor": "edge", "curve": [[30.0, 40.0], [60.0, 65.0], [80.0, 90.0]]}
        self.be.saveProfile("Kühl", {}, {}, fan, "")
        self.assertTrue(pump(lambda: "Kühl" in self.be.profileNames))
        self.assertEqual(self.be.info["profiles"]["Kühl"]["fan"],
                         {"sensor": "edge", "curve": [[30, 40], [60, 65], [80, 90]]})
        self.be.applyProfile("Kühl")
        self.assertTrue(pump(lambda: self.be.activeProfile == "Kühl"))
        self.assertEqual(self.be.status["fan"]["mode"], "curve")
        self.be.applyProfile("Standard")
        self.assertTrue(pump(lambda: self.be.activeProfile == "Standard"))
        self.assertEqual(self.be.status["fan"]["mode"], "auto")

    def test_startup_profile(self):
        self.assertEqual(self.be.startupProfile, "")
        self.be.setStartupProfile("KI")
        self.assertTrue(pump(lambda: self.be.startupProfile == "KI"))
        self.be.setStartupProfile("")
        self.assertTrue(pump(lambda: self.be.startupProfile == ""))

    def test_deep_clean_converts_nested_floats(self):
        self.assertEqual(be._clean({"curve": [[30.0, 40.0], [80.5, 90.0]], "n": 3.0}),
                         {"curve": [[30, 40], [80.5, 90]], "n": 3})

    def test_history_contains_fan_percent(self):
        self.assertIn("g_fanp", self.be.history)
        self.assertEqual(len(self.be.history["g_fanp"]), len(self.be.history["t"]))

    def test_connection_loss(self):
        class Broken:
            def call(self, req):
                raise ConnectionRefusedError("weg")
        self.be.shutdown()
        b2 = be.Backend(Broken())
        toasts = []
        b2.toast.connect(lambda t, e: toasts.append((t, e)))
        try:
            self.assertFalse(pump(lambda: b2.connected, timeout=1.5))
            self.assertEqual(toasts, [], "fehlgeschlagene Abfragen im Hintergrund dürfen nicht melden")
        finally:
            b2.shutdown()

    def test_command_connection_loss_shows_error_toast(self):
        class DropsCommands:
            def __init__(self, inner):
                self.inner = inner

            def call(self, req):
                if req["cmd"] == "apply_profile":
                    raise ConnectionRefusedError("Verbindung abgelehnt")
                return self.inner.call(req)

        self.be._worker.client = DropsCommands(self.client)
        self.toasts.clear()
        self.be.applyProfile("KI")
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        self.assertEqual(len(self.toasts), 1)
        text, is_error = self.toasts[0]
        self.assertTrue(is_error)
        self.assertIn("Verbindung abgelehnt", text)
        self.assertNotIn("angewendet", text)
        self.assertEqual(self.be.activeProfile, "Standard")

    def test_autostart_file(self):
        with tempfile.TemporaryDirectory() as d:
            old = be.AUTOSTART_FILE
            be.AUTOSTART_FILE = Path(d) / "autostart" / "hwpanel-gui.desktop"
            try:
                self.assertFalse(self.be.autostartEnabled)
                self.be.setAutostart(True)
                self.assertTrue(self.be.autostartEnabled)
                self.assertIn("Exec=hwpanel-gui --minimized", be.AUTOSTART_FILE.read_text(encoding="utf-8"))
                self.be.setAutostart(False)
                self.assertFalse(self.be.autostartEnabled)
            finally:
                be.AUTOSTART_FILE = old


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class RealSocketTests(unittest.TestCase):
    """Backend gegen den echten Daemon-Server über einen Unix-Socket."""

    def test_backend_over_unix_socket(self):
        import threading
        import hwpaneld
        app = QApplication.instance() or QApplication(sys.argv[:1])
        demo = DemoClient(duration=120)
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = os.path.join(d, "t.sock")
            srv = hwpaneld.make_server(demo.hw, path)
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            b = be.Backend(be.DaemonClient(path))
            try:
                self.assertTrue(pump(lambda: b.connected and b.info and len(b.history["t"]) >= 60))
                b.applyProfile("KI")
                self.assertTrue(pump(lambda: b.activeProfile == "KI"))
                # inkrementelles Nachladen: keine doppelten Zeitstempel
                ts = b.history["t"]
                self.assertEqual(len(ts), len(set(ts)))
            finally:
                b.shutdown()
                srv.shutdown()
                srv.server_close()
                demo.close()


@unittest.skipUnless(HAVE_QT, "PySide6 nicht installiert")
class TrayTests(unittest.TestCase):
    def test_menu_follows_profiles(self):
        app = QApplication.instance() or QApplication(sys.argv[:1])
        import hwpanel_gui
        client = DemoClient(duration=120)
        b = be.Backend(client)
        try:
            self.assertTrue(pump(lambda: b.connected and b.info))

            class Win:
                visible = False
                def isVisible(self): return self.visible
                def isActive(self): return self.visible
                def show(self): self.visible = True
                def hide(self): self.visible = False
                def raise_(self): pass
                def requestActivate(self): pass

            win = Win()
            tray = hwpanel_gui.Tray(win, b, hwpanel_gui.load_icon())
            names = [a.text() for a in tray.menu.actions() if a.isCheckable()]
            self.assertEqual(names, ["Standard", "Gaming", "KI"])
            checked = [a.text() for a in tray.menu.actions() if a.isChecked()]
            self.assertEqual(checked, ["Standard"])
            self.assertIn("Fenster öffnen", [a.text() for a in tray.menu.actions()])
            self.assertIn("GPU", tray.tray.toolTip())
            # Profilwechsel über das Menü
            ki = [a for a in tray.menu.actions() if a.text() == "KI"][0]
            ki.trigger()
            self.assertTrue(pump(lambda: b.activeProfile == "KI"))
            self.assertTrue(pump(lambda: [a.text() for a in tray.menu.actions() if a.isChecked()] == ["KI"]))
            tray.toggle()
            self.assertTrue(win.visible)
            tray.toggle()
            self.assertFalse(win.visible)
        finally:
            b.shutdown()
            client.close()


if __name__ == "__main__":
    unittest.main()
