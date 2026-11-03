"""Tests for the GUI backend (without display, with the demo daemon on FakeIO).

Requires PySide6, otherwise the tests are skipped.
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
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:   # Errors in the project modules should stand out and not end up as "skipped"
    import backend as be
    from demo_client import DemoClient
    from language import Language
    from test_hwpaneld import HWMON

DE = {"LANG": "de_DE.UTF-8"}   # The texts of the tests are German: pin the language, independent of the environment


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
        self.be = be.Backend(self.client, language=Language(env=DE))
        self.toasts = []
        self.be.toast.connect(lambda t, e: self.toasts.append((t, e)))
        self.assertTrue(pump(lambda: self.be.connected and self.be.info and self.be.history["t"]))

    def tearDown(self):
        self.be.shutdown()
        self.client.close()

    # ---- Data

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
        samples[1800]["g_junc"] = 99.0  # short peak
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

    # ---- Actions

    def test_apply_profile_updates_status_and_toast(self):
        self.be.applyProfile("KI")
        self.assertTrue(pump(lambda: self.be.activeProfile == "KI"))
        self.assertTrue(any("Profil KI angewendet" in t and not e for t, e in self.toasts))
        self.be.applyProfile("Standard")
        self.assertTrue(pump(lambda: self.be.activeProfile == "Standard"))

    def test_toasts_follow_the_language(self):
        self.be.language.setLanguage("en")
        self.toasts.clear()
        self.be.applyProfile("KI")
        self.assertTrue(pump(lambda: any(t == "Profile KI applied" and not e for t, e in self.toasts)))
        self.toasts.clear()
        self.be.applyProfile("Standard")   # the built-in profile is called "Default" in English
        self.assertTrue(pump(lambda: any(t == "Profile Default applied" and not e for t, e in self.toasts)))
        self.be.language.setLanguage("de")
        self.toasts.clear()
        self.be.setManual({"sclk_max": 2200}, {}, {})
        self.assertTrue(pump(lambda: any(t == "GPU-Einstellungen angewendet" and not e for t, e in self.toasts)))

    def test_daemon_errors_in_toasts_follow_the_language(self):
        self.toasts.clear()
        self.be.setManual({"sclk_max": 99999}, {}, {})
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        self.assertIn(("sclk_max=99999 außerhalb des erlaubten Bereichs 500-2679", True), self.toasts)
        self.be.language.setLanguage("en")
        self.toasts.clear()
        self.be.setManual({"sclk_max": 99999}, {}, {})
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        self.assertIn(("sclk_max=99999 is outside the allowed range 500-2679", True), self.toasts)

    def test_history_events_follow_the_language_live(self):
        self.be.applyProfile("KI")
        self.assertTrue(pump(lambda: self.be.activeProfile == "KI"))
        self.client.hw._tick()   # the demo daemon creates no new samples; the chart only shows events up to the last sample
        self.assertTrue(pump(lambda: any(e["text"] == "Profil KI" for e in self.be.history["events"])))
        self.be.language.setLanguage("en")
        self.assertTrue(any(e["text"] == "Profile KI" for e in self.be.history["events"]))
        self.assertFalse(any(e["text"] == "Profil KI" for e in self.be.history["events"]))
        self.be.language.setLanguage("de")
        self.assertTrue(any(e["text"] == "Profil KI" for e in self.be.history["events"]))

    def test_builtin_profile_event_uses_the_gui_name(self):
        self.be.applyProfile("KI")
        self.assertTrue(pump(lambda: self.be.activeProfile == "KI"))
        self.be.applyProfile("Standard")
        self.assertTrue(pump(lambda: self.be.activeProfile == "Standard"))
        self.client.hw._tick()
        self.assertTrue(pump(lambda: any(e["text"] == "Profil Standard" for e in self.be.history["events"])))
        self.be.language.setLanguage("en")
        self.assertTrue(any(e["text"] == "Profile Default" for e in self.be.history["events"]))

    def test_fan_error_in_status_follows_the_language(self):
        hw = self.client.hw
        self.client.io.files[HWMON + "/temp1_input"] = "50000"
        self.be.setManual({}, {}, {"sensor": "edge", "curve": [[30, 40], [80, 90]]})
        self.assertTrue(pump(lambda: self.be.status["fan"]["mode"] == "curve"))
        self.client.io.files.pop(HWMON + "/temp1_input")
        hw.fan_step(now=1000)
        self.assertTrue(pump(lambda: self.be.status["fan"]["error"] == "Sensor nicht lesbar"))
        self.be.language.setLanguage("en")
        self.assertEqual(self.be.status["fan"]["error"], "sensor not readable")
        self.assertEqual(self.be.status["fan"]["error_msg"]["tpl"], "sensor not readable")   # raw data is kept

    def test_long_event_text_is_shortened(self):
        text = be.Backend._event_text({"t": 1, "text": "x" * 300})
        self.assertEqual((len(text), text[-1]), (110, "…"))
        self.assertEqual(be.Backend._event_text({"t": 1, "text": "short"}), "short")

    def test_events_and_errors_from_an_older_daemon_without_templates(self):
        self.assertEqual(be.Backend._event_text({"t": 1, "text": "Profil KI"}), "Profil KI")
        self.toasts.clear()
        self.be._on_result("label", {"ok": False, "errors": ["old a", "old b"]})
        self.be._on_result("label", {"ok": False, "error": "old error"})
        self.assertEqual(self.toasts, [("old a; old b", True), ("old error", True)])

    def test_name_check_messages_follow_the_language(self):
        self.be.language.setLanguage("en")
        self.assertEqual(self.be.profileNameError("Leise (Nacht)", ""), "Allowed: 1-32 characters, letters, digits, spaces, . _ -")
        self.assertEqual(self.be.profileNameError("KI", ""), "A profile with this name already exists")
        self.be.language.setLanguage("de")
        self.assertEqual(self.be.profileNameError("KI", ""), "Ein Profil mit diesem Namen gibt es schon")

    def test_manual_settings_and_error_toast(self):
        self.be.setManual({"sclk_max": 2200.0}, {"max_mhz": 3000.0}, {})
        self.assertTrue(pump(lambda: self.be.status.get("settings", {}).get("gpu", {}).get("sclk_max") == 2200))
        self.assertTrue(pump(lambda: self.be.status["settings"]["cpu"].get("max_mhz") == 3000))
        self.assertIsNone(self.be.activeProfile or None)
        self.toasts.clear()
        self.be.setManual({"sclk_max": 99999}, {}, {})  # above the default: must be rejected
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
        self.be.saveProfile("Standard", {"sclk_max": 2000}, {}, {}, "KI")   # reserved name
        self.assertTrue(pump(lambda: any(e for _, e in self.toasts)))
        pump(lambda: False, timeout=0.5)   # time for an (erroneous) delete command
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
                             ("KI", "Gaming"), ("x" * 33, ""), (".punkt", ""),
                             ("Default", ""), ("default", "")):   # this is what the built-in profile is called in English
            self.assertNotEqual(err(bad, editing), "", bad)
        self.assertEqual(err("Default", "Default"), "", "ein schon vorhandenes Profil lässt sich weiter bearbeiten")

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
        # empty fan setting = automatic
        self.be.setManual({}, {}, {})
        self.assertTrue(pump(lambda: self.be.status["fan"]["mode"] == "auto"))
        self.assertIsNone(self.be.status["settings"]["fan"])

    def test_invalid_fan_curve_is_rejected(self):
        self.toasts.clear()
        # at 80 °C only 40 %: violates the protection rule (min. 50 %)
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
    """Backend against the real daemon server over a Unix socket."""

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
            b = be.Backend(be.DaemonClient(path), language=Language(env=DE))
            try:
                self.assertTrue(pump(lambda: b.connected and b.info and len(b.history["t"]) >= 60))
                b.applyProfile("KI")
                self.assertTrue(pump(lambda: b.activeProfile == "KI"))
                # incremental reload: no duplicate timestamps
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
        b = be.Backend(client, language=Language(env=DE))
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
            # profile change via the menu
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

    def test_menu_and_tooltip_follow_the_language(self):
        app = QApplication.instance() or QApplication(sys.argv[:1])
        import hwpanel_gui
        client = DemoClient(duration=120)
        b = be.Backend(client, language=Language(env=DE))
        try:
            self.assertTrue(pump(lambda: b.connected and b.info and b.activeProfile))

            class Win:
                def isVisible(self): return False
                def isActive(self): return False
                def show(self): pass
                def hide(self): pass
                def raise_(self): pass
                def requestActivate(self): pass

            tray = hwpanel_gui.Tray(Win(), b, hwpanel_gui.load_icon())
            texts = lambda: [a.text() for a in tray.menu.actions()]  # noqa: E731
            self.assertEqual(texts()[:3], ["Standard", "Gaming", "KI"])
            self.assertIn("Profil: Standard", tray.tray.toolTip())
            b.language.setLanguage("en")
            # in the UI the built-in profile is called "Default", but "Standard" is still what gets applied
            self.assertEqual(texts()[:3], ["Default", "Gaming", "KI"])
            self.assertIn("Open window", texts())
            self.assertIn("Quit", texts())
            pump(lambda: False, timeout=1.3)   # next update of the tooltip
            self.assertIn("Profile: Default", tray.tray.toolTip())
            self.assertIn("Fan", tray.tray.toolTip())
            default = tray.menu.actions()[0]
            default.trigger()
            self.assertTrue(pump(lambda: b.activeProfile == "Standard"))
        finally:
            b.shutdown()
            client.close()


if __name__ == "__main__":
    unittest.main()
