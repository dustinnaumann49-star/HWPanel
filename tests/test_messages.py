"""Messages of the daemon in the protocol: English text in the existing fields, plus template and arguments (*_msg),
neutral identifiers instead of German words. In German rendering the old texts must be reproduced."""

import errno
import json
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
from test_hwpaneld import CPU, CURVE, HWMON, Base, time_now_plus  # noqa: E402

GERMAN = re.compile(r"[äöüÄÖÜß]|\b(Lüfter\w*|Fehler|Befehl|Treiber|nicht|erwartet|außerhalb|Profil|existiert|Zurückgesetzt|"
                    r"Manuell|Aufwachen|gestartet|Sicherung|Schutzregel|abgelehnt|Hinweis|Kommando|ungültig)\b")


class MessageCase(Base):
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

    def de(self, data):
        i18n.set_language("de")
        return i18n.message(data)

    def events(self):
        return self.hw.history()["events"]

    def temps(self, edge=None, junc=None):
        if edge is not None:
            self.io.files[HWMON + "/temp1_input"] = str(int(edge * 1000))
        if junc is not None:
            self.io.files[HWMON + "/temp2_input"] = str(int(junc * 1000))


class TestErrorResponses(MessageCase):
    def test_validation_error_has_english_text_and_template(self):
        r = hwpanelctl.call({"cmd": "set_gpu", "values": {"sclk_max": 9999}})
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "sclk_max=9999 is outside the allowed range 500-2679")
        self.assertEqual(r["error_msg"], {"tpl": "{key}={value} is outside the allowed range {lo}-{hi}",
                                          "args": {"key": "sclk_max", "value": 9999, "lo": 500, "hi": 2679}})
        self.assertEqual(self.de(r["error_msg"]), "sclk_max=9999 außerhalb des erlaubten Bereichs 500-2679")
        self.assertEqual(i18n.message_field(r, "error"), "sclk_max=9999 außerhalb des erlaubten Bereichs 500-2679")

    def test_unknown_profile_and_command(self):
        r = hwpanelctl.call({"cmd": "apply_profile", "name": "Nope"})
        self.assertEqual(r["error"], "Profile 'Nope' does not exist")
        self.assertEqual(self.de(r["error_msg"]), "Profil 'Nope' existiert nicht")
        r = hwpanelctl.call({"cmd": "nope"})
        self.assertEqual(r["error"], "Unknown command: 'nope'")
        self.assertEqual(self.de(r["error_msg"]), "Unbekanntes Kommando: 'nope'")

    def test_fan_curve_protection_rule(self):
        r = hwpanelctl.call({"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 0], [90, 40]]}})
        self.assertEqual(r["error"], "fan.curve: at least 30 % required at 60 °C (protection rule, adjustable in config.json)")
        self.assertEqual(self.de(r["error_msg"]),
                         "fan.curve: bei 60 °C sind mindestens 30 % nötig (Schutzregel, einstellbar in config.json)")

    def test_user_text_in_arguments_stays_literal(self):
        name = "{0.__class__}"
        r = hwpanelctl.call({"cmd": "apply_profile", "name": name})
        self.assertEqual(r["error"], f"Profile '{name}' does not exist")
        self.assertEqual(self.de(r["error_msg"]), f"Profil '{name}' existiert nicht")

    def test_bad_json_and_non_object_requests(self):
        import socket
        s = socket.socket(socket.AF_UNIX)
        s.connect(self.path)
        s.sendall(b"kein json\n[1]\n")
        f = s.makefile("rb")
        bad_json, not_object = json.loads(f.readline()), json.loads(f.readline())
        s.close()
        self.assertFalse(bad_json["ok"])
        self.assertEqual(not_object["error"], "JSON object expected")
        self.assertEqual(self.de(not_object["error_msg"]), "JSON-Objekt erwartet")

    def test_legacy_clients_get_plain_english_text_only(self):
        r = hwpanelctl.call({"cmd": "set_gpu", "values": {"sclk_max": 9999}})
        self.assertIsInstance(r["error"], str)
        self.assertIsNone(GERMAN.search(r["error"]), r["error"])


class TestResultMessages(MessageCase):
    def test_errors_and_notes_have_parallel_templates(self):
        with mock.patch.object(self.io, "_od_write", side_effect=OSError(errno.EINVAL, "Invalid argument")):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertFalse(r["ok"])
        self.assertEqual(r["errors"], ["GPU clock: command 's 1 2300' rejected (Invalid argument)"])
        self.assertEqual(r["errors_msg"], [{"tpl": "GPU clock: command '{command}' rejected ({reason})",
                                            "args": {"command": "s 1 2300", "reason": "Invalid argument"}}])
        self.assertEqual(self.de(r["errors_msg"][0]), "GPU-Takt: Befehl 's 1 2300' abgelehnt (Invalid argument)")
        self.assertEqual(r["notes"], [])
        self.assertEqual(r["notes_msg"], [])

    def test_readback_mismatch(self):
        orig = self.io._od_write

        def ignore_commit(cmd):
            if cmd.split()[0] != "c":
                orig(cmd)

        with mock.patch.object(self.io, "_od_write", side_effect=ignore_commit):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertEqual(r["errors"][0], "sclk_max: expected 2300, driver reports 2679")
        self.assertEqual(r["errors_msg"][0]["tpl"], "{key}: expected {expected}, driver reports {actual}")
        self.assertEqual(self.de(r["errors_msg"][0]), "sclk_max: erwartet 2300, Treiber meldet 2679")

    def test_note_about_skipped_epp(self):
        for i in range(8):
            self.io.files[f"{CPU}/cpu{i}/cpufreq/scaling_governor"] = "performance"
        r = self.hw.set_cpu({"epp": "power"})
        self.assertEqual(r["notes"], ["EPP skipped: governor 'performance' ignores EPP"])
        self.assertEqual(self.de(r["notes_msg"][0]), "EPP übersprungen: Governor 'performance' ignoriert EPP")

    def test_error_fields_are_json(self):
        with mock.patch.object(self.io, "_od_write", side_effect=OSError(errno.EINVAL, "Invalid argument")):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertEqual(json.loads(json.dumps(r))["errors_msg"], r["errors_msg"])


class TestEvents(MessageCase):
    def test_events_carry_text_and_template(self):
        self.hw.apply_profile("KI")
        ev = self.events()[-1]
        self.assertEqual(ev["text"], "Profile KI")
        self.assertEqual(ev["msg"], {"tpl": "Profile {name}", "args": {"name": "KI"}})
        self.assertEqual(self.de(ev["msg"]), "Profil KI")

    def test_builtin_profile_name_is_a_nested_message(self):
        self.hw.apply_profile("Standard")
        ev = self.events()[-1]
        self.assertEqual(ev["text"], "Profile Default")
        self.assertEqual(ev["msg"]["args"]["name"], {"tpl": "Default", "args": {}})
        self.assertEqual(self.de(ev["msg"]), "Profil Standard")

    def test_german_rendering_matches_the_old_texts(self):
        self.hw.apply_profile("KI")
        self.hw.set_gpu({"power_cap_w": 200})
        self.hw.reset("gpu")
        self.hw.reset("all")
        self.hw.set_cpu({"max_mhz": 3000, "turbo": False})
        i18n.set_language("de")
        self.assertEqual([i18n.message(e["msg"]) for e in self.events()],
                         ["Profil KI", "Manuell: Power-Limit 200", "Zurückgesetzt (GPU)", "Zurückgesetzt",
                          "Manuell: CPU-Takt 3000, Turbo False"])
        i18n.set_language("en")
        self.assertEqual([e["text"] for e in self.events()],
                         ["Profile KI", "Manual: Power limit 200", "Reset (GPU)", "Reset",
                          "Manual: CPU clock 3000, Turbo False"])

    def test_failure_is_part_of_the_event(self):
        with mock.patch.object(self.io, "_od_write", side_effect=OSError(errno.EINVAL, "Invalid argument")):
            self.hw.set_gpu({"sclk_max": 2300})
        ev = self.events()[-1]
        self.assertEqual(ev["text"], "Manual: GPU clock 2300 (error: GPU clock: command 's 1 2300' rejected (Invalid argument))")
        self.assertEqual(self.de(ev["msg"]),
                         "Manuell: GPU-Takt 2300 (Fehler: GPU-Takt: Befehl 's 1 2300' abgelehnt (Invalid argument))")

    def test_fan_events(self):
        self.temps(41, 43)
        self.hw.set_fan({"sensor": "edge", "curve": CURVE})
        self.hw.set_fan({"mode": "auto"})
        i18n.set_language("de")
        self.assertEqual([i18n.message(e["msg"]) for e in self.events()],
                         ["Manuell: Lüfterkurve edge 30-80 °C, 40-90 %", "Manuell: Lüfter Automatik"])
        self.assertEqual([e["text"] for e in self.events()],
                         ["Manual: Fan curve edge 30-80 °C, 40-90 %", "Manual: Fan automatic"])

    def test_safety_events(self):
        self.temps(41, 43)
        self.hw.set_fan({"sensor": "edge", "curve": CURVE})
        self.temps(edge=60, junc=103)
        self.hw.fan_step(now=1000)
        self.temps(junc=90)
        self.hw.fan_step(now=1001)
        texts = [e["text"] for e in self.events()]
        self.assertIn("Fan: safety active (junction 103 °C), 100 %", texts)
        self.assertIn("Fan: safety ended", texts)
        self.assertEqual([self.de(e["msg"]) for e in self.events()][-2:],
                         ["Lüfter: Sicherung aktiv (Junction 103 °C), 100 %", "Lüfter: Sicherung beendet"])

    def test_sensor_failure_event_and_status(self):
        self.temps(50, 43)
        self.hw.set_fan({"sensor": "edge", "curve": CURVE})
        self.io.files.pop(HWMON + "/temp1_input")
        self.hw.fan_step(now=1000)
        st = self.hw.fan_status()
        self.assertEqual(st["error"], "sensor not readable")
        self.assertEqual(st["error_msg"], {"tpl": "sensor not readable", "args": {}})
        self.assertEqual(self.de(st["error_msg"]), "Sensor nicht lesbar")
        self.assertEqual(self.events()[-1]["text"], "Fan: edge sensor not readable, automatic")
        self.assertEqual(self.de(self.events()[-1]["msg"]), "Lüfter: edge-Sensor nicht lesbar, Automatik")

    def test_os_error_of_the_fan_is_a_plain_reason(self):
        orig = self.io.write

        def failing(path, value):
            if path.endswith("/pwm1"):
                raise OSError(errno.EIO, "Input/output error")
            return orig(path, value)

        with mock.patch.object(self.io, "write", side_effect=failing):
            r = self.hw.set_fan({"curve": CURVE})
            self.assertEqual(r["errors"], ["Fan: Input/output error"])
            self.assertEqual(self.de(r["errors_msg"][0]), "Lüfter: Input/output error")
            st = self.hw.fan_status()
            self.assertEqual((st["error"], st["error_msg"]["args"]["reason"]), ("Input/output error",) * 2)
            self.hw.fan_step(now=time_now_plus(5))

    def test_read_only_mode_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = hwpaneld.HW(self.io, tmp, readonly=True, probe_dmi=False)
            r = hw.set_fan({"curve": CURVE})
        self.assertEqual(r["errors"], ["Fan: read-only mode"])
        self.assertEqual(self.de(r["errors_msg"][0]), "Lüfter: Nur-Lese-Modus")

    def test_resume_and_start_events(self):
        self.hw.resume_delay = 0
        self.hw.set_gpu({"sclk_max": 2300})
        with mock.patch.object(hwpaneld.HW, "_susp_offset", staticmethod(lambda: self.hw._susp + 10.0)):
            self.hw._tick()
        self.assertEqual(self.events()[-1]["text"], "Woke up from standby")
        self.assertEqual(self.de(self.events()[-1]["msg"]), "Aufwachen aus Standby")


class TestFanMode(MessageCase):
    def test_hardware_mode_uses_neutral_codes(self):
        self.temps(41, 43)
        self.assertEqual(self.hw.fan_status()["hw_mode"], "automatic")
        self.hw.set_fan({"sensor": "edge", "curve": CURVE})
        self.assertEqual(self.hw.fan_status()["hw_mode"], "manual")
        self.io.files[HWMON + "/pwm1_enable"] = "0"
        self.assertEqual(self.hw.fan_status()["hw_mode"], "off")


class TestNothingGermanLeft(MessageCase):
    def test_all_plain_text_fields_are_english(self):
        """A run through errors, notes, events and fan state: no German word in the text fields."""
        texts = []

        def collect(r):
            if not isinstance(r, dict):
                return
            for k in ("error",):
                if r.get(k):
                    texts.append(r[k])
            texts.extend(r.get("errors", []))
            texts.extend(r.get("notes", []))
            if (r.get("fan") or {}).get("error"):
                texts.append(r["fan"]["error"])

        calls = [{"cmd": "set_gpu", "values": {"sclk_max": 9999}}, {"cmd": "set_gpu", "values": {"nope": 1}},
                 {"cmd": "set_gpu", "values": "x"}, {"cmd": "set_cpu", "values": {"max_mhz": 99999}},
                 {"cmd": "set_cpu", "values": {"turbo": "x"}}, {"cmd": "set_cpu", "values": {"governor": "xx"}},
                 {"cmd": "set_cpu", "values": {"epp": "xx"}}, {"cmd": "set_fan", "values": []},
                 {"cmd": "set_fan", "values": {"mode": "x"}}, {"cmd": "set_fan", "values": {"sensor": "x", "curve": CURVE}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 40]]}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 40], [30, 50]]}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 50], [40, 40]]}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 0], [90, 40]]}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 40], [200, 50]]}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30, 40], [40, 500]]}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": "x"}},
                 {"cmd": "set_fan", "values": {"sensor": "edge", "curve": [[30], [40, 50]]}},
                 {"cmd": "reset", "target": "x"}, {"cmd": "apply_profile", "name": "Nope"},
                 {"cmd": "delete_profile", "name": "Nope"}, {"cmd": "set_autostart", "profile": "Nope"},
                 {"cmd": "save_profile", "name": "Standard", "settings": {}},
                 {"cmd": "save_profile", "name": "a/b", "settings": {}},
                 {"cmd": "save_profile", "name": "ok", "settings": []},
                 {"cmd": "save_profile", "name": "ok", "settings": {"x": {}}}, {"cmd": "history", "since": "x"},
                 {"cmd": "nope"}]
        for req in calls:
            r = hwpanelctl.call(req)
            self.assertFalse(r["ok"], req)
            collect(r)
        with mock.patch.object(self.io, "_od_write", side_effect=OSError(errno.EINVAL, "Invalid argument")):
            collect(self.hw.set_gpu({"sclk_max": 2300}))
        for i in range(8):
            self.io.files[f"{CPU}/cpu{i}/cpufreq/scaling_governor"] = "performance"
        collect(self.hw.set_cpu({"epp": "power"}))
        self.temps(50, 43)
        self.hw.set_fan({"sensor": "edge", "curve": CURVE})
        self.io.files.pop(HWMON + "/temp1_input")
        self.hw.fan_step(now=1000)
        collect({"fan": self.hw.fan_status()})
        texts.extend(e["text"] for e in self.events())
        self.assertGreater(len(texts), 30)
        for t in texts:
            self.assertIsNone(GERMAN.search(t), f"German text in the English text field: {t!r}")

    def test_every_message_renders_in_german_without_losing_arguments(self):
        for req in ({"cmd": "set_gpu", "values": {"sclk_max": 9999}}, {"cmd": "set_cpu", "values": {"governor": "xx"}},
                    {"cmd": "set_cpu", "values": {"epp": "xx"}}, {"cmd": "apply_profile", "name": "Nope"}):
            r = hwpanelctl.call(req)
            plain, german = r["error"], self.de(r["error_msg"])
            for arg in r["error_msg"]["args"].values():
                text = ", ".join(map(str, arg)) if isinstance(arg, list) else str(arg)
                if isinstance(arg, dict):
                    continue   # nested message: gets translated, so it does not appear literally in the text
                self.assertIn(text, german, f"{req}: argument {arg!r} missing in {german!r}")
            self.assertNotEqual(plain, german)


if __name__ == "__main__":
    unittest.main()
