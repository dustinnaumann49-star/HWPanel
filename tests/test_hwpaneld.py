"""Tests gegen eine nachgebaute sysfs-Struktur (Werte aus den echten Ausgaben des Nutzers)."""

import collections
import contextlib
import copy
import errno
import fnmatch
import io
import itertools
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hwpaneld  # noqa: E402
import hwpanelctl  # noqa: E402
import hwpanel_i18n as i18n  # noqa: E402
from hwpaneld import HW, parse_dmidecode, parse_od  # noqa: E402

OD = "/sys/class/drm/card1/device/pp_od_clk_voltage"
DEV = "/sys/class/drm/card1/device"
HWMON = DEV + "/hwmon/hwmon3"
CPU = "/sys/devices/system/cpu"

REAL_OD_TEXT = """OD_SCLK:
0: 500Mhz
1: 2679Mhz
OD_MCLK:
0: 97Mhz
1: 1124MHz
OD_VDDGFX_OFFSET:
0mV
OD_RANGE:
SCLK:     500Mhz       2950Mhz
MCLK:     674Mhz       1156Mhz
"""

DMI_SAMPLE = """Handle 0x0031, DMI type 17, 40 bytes
Memory Device
\tSize: 8 GiB
\tLocator: DIMM_A1
\tType: DDR4
\tType Detail: Synchronous
\tSpeed: 2133 MT/s
\tConfigured Memory Speed: 2133 MT/s

Handle 0x0032, DMI type 17, 40 bytes
Memory Device
\tSize: No Module Installed
\tLocator: DIMM_A2
\tType: Unknown

Handle 0x0033, DMI type 17, 40 bytes
Memory Device
\tSize: 8 GiB
\tLocator: DIMM_B1
\tType: DDR4
\tSpeed: 2133 MT/s
\tConfigured Memory Speed: 2133 MT/s
"""


class FakeIO:
    """Emuliert sysfs inklusive der OD-Semantik (r / s / m / c) des amdgpu-Treibers."""

    def __init__(self, committed_sclk=2679, pad=False):
        self.pad = pad
        self.default ={"sclk": {0: 500, 1: 2679}, "mclk": {0: 97, 1: 1124}, "vo": 0}
        self.committed = copy.deepcopy(self.default)
        self.committed["sclk"][1] = committed_sclk
        self.staged = copy.deepcopy(self.committed)
        self.writes = []
        f = self.files = {}
        f["/sys/class/drm/card0/device/vendor"] = "0x8086"
        f[DEV + "/vendor"] = "0x1002"
        f[DEV + "/device"] = "0x73df"
        f["/sys/class/drm/card1-DP-1/status"] = "disconnected"
        f[DEV + "/gpu_busy_percent"] = "4"
        f[DEV + "/mem_info_vram_used"] = str(700 * 2 ** 20)
        f[DEV + "/mem_info_vram_total"] = str(12272 * 2 ** 20)
        f[DEV + "/mem_info_gtt_used"] = str(100 * 2 ** 20)
        f[DEV + "/power_dpm_force_performance_level"] = "auto"
        f[DEV + "/pp_dpm_sclk"] = "0: 500Mhz *\n1: 2880Mhz \n"
        f[HWMON + "/freq1_input"] = "500000000"
        f[HWMON + "/freq2_input"] = "96000000"
        f[HWMON + "/temp1_input"] = "41000"
        f[HWMON + "/temp2_input"] = "43000"
        f[HWMON + "/temp3_input"] = "44000"
        f[HWMON + "/power1_average"] = "11000000"
        f[HWMON + "/power1_cap"] = "210000000"
        f[HWMON + "/power1_cap_max"] = "210000000"
        f[HWMON + "/power1_cap_default"] = "210000000"
        f[HWMON + "/power1_cap_min"] = "0"
        f[HWMON + "/fan1_input"] = "1872"
        f[HWMON + "/pwm1"] = "125"
        f[HWMON + "/pwm1_enable"] = "2"
        f[HWMON + "/pwm1_max"] = "255"
        f[HWMON + "/pwm1_min"] = "0"
        f[HWMON + "/in0_input"] = "800"
        for i in range(8):
            d = f"{CPU}/cpu{i}/cpufreq"
            f[d + "/cpuinfo_min_freq"] = "800000"
            f[d + "/cpuinfo_max_freq"] = "4200000"
            f[d + "/scaling_max_freq"] = "4200000"
            f[d + "/scaling_cur_freq"] = "800000"
            f[d + "/scaling_governor"] = "powersave"
            f[d + "/scaling_driver"] = "intel_pstate"
            f[d + "/scaling_available_governors"] = "performance powersave"
            f[d + "/energy_performance_preference"] = "balance_performance"
            f[d + "/energy_performance_available_preferences"] = \
                "default performance balance_performance balance_power power"
        f[CPU + "/intel_pstate/no_turbo"] = "0"
        f["/sys/class/powercap/intel-rapl:0/name"] = "package-0"
        f["/sys/class/powercap/intel-rapl:0/energy_uj"] = "5000000"
        f["/sys/class/powercap/intel-rapl:0/max_energy_range_uj"] = "262143328850"
        f["/sys/class/hwmon/hwmon1/name"] = "coretemp"
        f["/sys/class/hwmon/hwmon1/temp1_label"] = "Package id 0"
        f["/sys/class/hwmon/hwmon1/temp1_input"] = "35000"
        f["/proc/stat"] = ("cpu  1000 0 500 8000 0 0 0 0\n"
                           + "".join(f"cpu{i} 125 0 62 1000 0 0 0 0\n" for i in range(8)))
        f["/proc/meminfo"] = ("MemTotal:       16384000 kB\nMemAvailable:   11264000 kB\n"
                              "Cached:          5324800 kB\nBuffers:           10240 kB\n"
                              "SwapTotal:       4096000 kB\nSwapFree:        4096000 kB\n")
        f["/proc/cpuinfo"] = "processor\t: 0\nmodel name\t: Intel(R) Core(TM) i7-6700K CPU @ 4.00GHz\n"

    # --- Treiber-Emulation
    def _od_text(self):
        c = self.committed
        gap = "\x00" * 400 if self.pad else ""  # echter Treiber füllt mit NUL-Bytes auf
        return (f"OD_SCLK:\n0: {c['sclk'][0]}Mhz\n1: {c['sclk'][1]}Mhz\n"
                f"OD_MCLK:\n0: {c['mclk'][0]}Mhz\n1: {c['mclk'][1]}MHz\n{gap}"
                f"OD_VDDGFX_OFFSET:\n{c['vo']}mV\n{gap}"
                "OD_RANGE:\nSCLK:     500Mhz       2950Mhz\nMCLK:     674Mhz       1156Mhz\n" + gap)

    def _od_write(self, cmd):
        parts = cmd.split()
        if parts == ["r"]:
            self.staged = copy.deepcopy(self.default)
        elif parts == ["c"]:
            self.committed = copy.deepcopy(self.staged)
        elif len(parts) == 3 and parts[0] in ("s", "m"):
            tbl = "sclk" if parts[0] == "s" else "mclk"
            lo, hi = (500, 2950) if tbl == "sclk" else (674, 1156)
            if not lo <= int(parts[2]) <= hi:
                raise OSError(errno.EINVAL, "Invalid argument")
            self.staged[tbl][int(parts[1])] = int(parts[2])
        else:
            raise OSError(errno.EINVAL, "Invalid argument")

    # --- IO-Schnittstelle
    def read(self, path):
        if path == OD:
            return self._od_text().strip()
        if path in self.files:
            return self.files[path]
        raise FileNotFoundError(path)

    def write(self, path, value):
        self.writes.append((path, value))
        if path == OD:
            return self._od_write(value.strip())
        if path.endswith("/energy_performance_preference"):
            if self.files[path.replace("energy_performance_preference", "scaling_governor")] == "performance":
                raise OSError(errno.EBUSY, "Device or resource busy")
        if path.endswith("/power1_cap") and int(value) > int(self.files[HWMON + "/power1_cap_max"]):
            raise OSError(errno.EINVAL, "Invalid argument")
        if path.endswith("/pwm1") and self.files[HWMON + "/pwm1_enable"] != "1":
            raise OSError(errno.EINVAL, "Invalid argument")  # amdgpu: erst manuellen Modus aktivieren
        if path.endswith("/pwm1_enable") and value.strip() not in ("0", "1", "2"):
            raise OSError(errno.EINVAL, "Invalid argument")
        if path not in self.files:
            raise FileNotFoundError(path)
        self.files[path] = value.strip()

    def exists(self, path):
        return path == OD or path in self.files or any(k.startswith(path + "/") for k in self.files)

    def glob(self, pattern):
        n = pattern.count("/")
        nodes = set()
        for k in list(self.files) + [OD]:
            parts = k.split("/")
            for i in range(2, len(parts) + 1):
                nodes.add("/".join(parts[:i]))
        return sorted(p for p in nodes if p.count("/") == n and fnmatch.fnmatchcase(p, pattern))


class Base(unittest.TestCase):
    committed_sclk = 2679

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.io = FakeIO(self.committed_sclk)
        self.hw = HW(self.io, self.tmp.name, probe_dmi=False)

    def tearDown(self):
        self.tmp.cleanup()

    def cpu_files(self, name):
        return {self.io.files[f"{CPU}/cpu{i}/cpufreq/{name}"] for i in range(8)}


class TestParser(unittest.TestCase):
    def test_parse_od_real_output(self):
        od = parse_od(REAL_OD_TEXT)
        self.assertEqual(od["sclk"], {0: 500, 1: 2679})
        self.assertEqual(od["mclk"], {0: 97, 1: 1124})
        self.assertEqual(od["vo"], 0)
        self.assertEqual(od["range"], {"sclk": (500, 2950), "mclk": (674, 1156)})

    def test_parse_od_with_nul_padding(self):
        padded = (REAL_OD_TEXT.replace("OD_VDDGFX_OFFSET", "\x00" * 300 + "OD_VDDGFX_OFFSET")
                  .replace("OD_RANGE", "\x00" * 500 + "OD_RANGE") + "\x00" * 200)
        od = parse_od(padded)
        self.assertEqual(od["range"], {"sclk": (500, 2950), "mclk": (674, 1156)})
        self.assertEqual(od["vo"], 0)
        self.assertEqual(od["sclk"][1], 2679)

    def test_realio_strips_nul(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(root + "/sys/x")
            with open(root + "/sys/x/f", "w") as f:
                f.write("abc\n\x00\x00\x00def\n")
            self.assertEqual(hwpaneld.RealIO(root).read("/sys/x/f"), "abc\ndef")

    def test_parse_dmidecode(self):
        mods = parse_dmidecode(DMI_SAMPLE)
        self.assertEqual(len(mods), 2)
        self.assertEqual(mods[0]["size_gib"], 8)
        self.assertEqual(mods[0]["type"], "DDR4")
        self.assertEqual(mods[0]["configured_mts"], 2133)


class TestDiscovery(Base):
    def test_finds_amd_gpu_not_intel(self):
        self.assertEqual(self.hw.gpu.card, "card1")
        self.assertEqual(self.hw.gpu.hwmon, HWMON)

    def test_finds_cpu_rapl_temp(self):
        self.assertEqual(len(self.hw.cpu_dirs), 8)
        self.assertEqual(self.hw.rapl, "/sys/class/powercap/intel-rapl:0")
        self.assertEqual(self.hw.cpu_temp, "/sys/class/hwmon/hwmon1/temp1_input")

    def test_default_profiles_created(self):
        self.assertEqual(set(self.hw.profiles), {"Gaming", "KI"})
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "profiles.json")))


class TestDefaults(Base):
    def test_defaults_and_limits(self):
        d = self.hw.defaults
        self.assertEqual(d["gpu"]["sclk_max"], 2679)
        self.assertEqual(d["gpu"]["mclk_max"], 1124)
        self.assertEqual(d["gpu"]["power_cap_uw"], 210000000)
        self.assertEqual(d["cpu"]["max_khz"], 4200000)
        self.assertEqual(d["cpu"]["epp"], "balance_performance")
        L = self.hw.limits()
        self.assertEqual(L["gpu"]["sclk_max"], [500, 2679])
        self.assertEqual(L["gpu"]["mclk_max"], [674, 1124])
        self.assertEqual(L["gpu"]["power_cap_w"], [105, 210])
        self.assertEqual(L["cpu"]["max_mhz"], [800, 4200])


class TestNulPaddedOdFile(unittest.TestCase):
    """Regression: echte pp_od_clk_voltage enthält NUL-Padding, dadurch fehlten OD_RANGE und Grenzen."""

    def test_limits_and_set_with_padding(self):
        with tempfile.TemporaryDirectory() as tmp:
            io_ = FakeIO(pad=True)
            hw = HW(io_, tmp, probe_dmi=False)
            self.assertEqual(hw.limits()["gpu"]["sclk_max"], [500, 2679])
            self.assertEqual(hw.limits()["gpu"]["mclk_max"], [674, 1124])
            self.assertTrue(hw.set_gpu({"sclk_max": 2300})["ok"])
            self.assertEqual(io_.committed["sclk"][1], 2300)
            with self.assertRaises(ValueError):
                hw.set_gpu({"sclk_max": 2700})


class TestDefaultsFromOverclocked(Base):
    committed_sclk = 2800

    def test_capture_resets_existing_oc(self):
        self.assertEqual(self.hw.defaults["gpu"]["sclk_max"], 2679)
        self.assertEqual(self.hw.defaults["gpu"]["source"], "od-reset")
        self.assertEqual(self.io.committed["sclk"][1], 2679)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "defaults.json")))

    def test_defaults_not_recaptured_on_restart(self):
        self.hw.set_gpu({"sclk_max": 2300})
        hw2 = HW(self.io, self.tmp.name, probe_dmi=False)
        self.assertEqual(hw2.defaults["gpu"]["sclk_max"], 2679)
        self.assertEqual(self.io.committed["sclk"][1], 2300)


class TestValidation(Base):
    def test_rejects_gpu(self):
        for bad in ({"sclk_max": 2680}, {"sclk_max": 499}, {"mclk_max": 1125}, {"mclk_max": 673},
                    {"power_cap_w": 211}, {"power_cap_w": 104}, {"sclk_max": True},
                    {"sclk_max": "2300"}, {"sclk_max": 23.5}, {"voltage": 1}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.hw.set_gpu(bad)
        self.assertEqual(self.io.committed["sclk"][1], 2679)

    def test_rejects_cpu(self):
        for bad in ({"max_mhz": 4300}, {"max_mhz": 700}, {"turbo": "yes"}, {"epp": "turbo"},
                    {"governor": "ondemand"}, {"foo": 1}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.hw.set_cpu(bad)

    def test_accepts_boundaries(self):
        self.assertTrue(self.hw.set_gpu({"sclk_max": 2679, "mclk_max": 1124, "power_cap_w": 210})["ok"])
        self.assertTrue(self.hw.set_gpu({"sclk_max": 500})["ok"])
        self.assertTrue(self.hw.set_cpu({"max_mhz": 800})["ok"])

    def test_no_oc_nothing_written_on_rejection(self):
        before = len(self.io.writes)
        with self.assertRaises(ValueError):
            self.hw.set_gpu({"sclk_max": 2900})
        self.assertEqual(len(self.io.writes), before)


class TestApply(Base):
    def test_set_gpu(self):
        r = self.hw.set_gpu({"sclk_max": 2300, "power_cap_w": 150})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.io.committed["sclk"][1], 2300)
        self.assertEqual(self.io.files[HWMON + "/power1_cap"], "150000000")
        self.assertEqual(r["settings"]["gpu"]["sclk_max"], 2300)
        self.assertEqual(r["settings"]["gpu"]["power_cap_w"], 150)
        self.assertEqual(self.io.committed["mclk"][1], 1124)

    def test_partial_set_keeps_other_values(self):
        self.hw.set_gpu({"sclk_max": 2300})
        self.hw.set_gpu({"mclk_max": 900})
        self.assertEqual(self.io.committed["sclk"][1], 2300)
        self.assertEqual(self.io.committed["mclk"][1], 900)

    def test_set_cpu(self):
        r = self.hw.set_cpu({"max_mhz": 3000, "turbo": False, "epp": "power"})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.cpu_files("scaling_max_freq"), {"3000000"})
        self.assertEqual(self.cpu_files("energy_performance_preference"), {"power"})
        self.assertEqual(self.io.files[CPU + "/intel_pstate/no_turbo"], "1")
        self.assertIs(r["settings"]["cpu"]["turbo"], False)

    def test_profile_ki_resets_unlisted_values(self):
        self.hw.set_gpu({"mclk_max": 900, "power_cap_w": 150})
        r = self.hw.apply_profile("KI")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.io.committed["sclk"][1], 2300)
        self.assertEqual(self.io.committed["mclk"][1], 1124)
        self.assertEqual(self.io.files[HWMON + "/power1_cap"], "210000000")
        self.assertEqual(r["active_profile"], "KI")

    def test_profile_gaming(self):
        self.hw.set_gpu({"sclk_max": 2000})
        self.hw.set_cpu({"max_mhz": 2000, "turbo": False})
        r = self.hw.apply_profile("Gaming")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.io.committed["sclk"][1], 2679)
        self.assertEqual(self.cpu_files("energy_performance_preference"), {"performance"})
        self.assertEqual(self.cpu_files("scaling_max_freq"), {"4200000"})
        self.assertEqual(self.io.files[CPU + "/intel_pstate/no_turbo"], "0")

    def test_reset_all(self):
        self.hw.apply_profile("KI")
        self.hw.set_cpu({"max_mhz": 2000, "epp": "power"})
        r = self.hw.reset("all")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.io.committed["sclk"][1], 2679)
        self.assertEqual(self.cpu_files("scaling_max_freq"), {"4200000"})
        self.assertEqual(self.cpu_files("energy_performance_preference"), {"balance_performance"})
        self.assertEqual(r["active_profile"], "Standard")
        self.assertEqual(self.hw.desired, {"gpu": {}, "cpu": {}, "fan": None})

    def test_builtin_profile_standard(self):
        self.hw.set_gpu({"sclk_max": 2000})
        self.assertTrue(self.hw.apply_profile("Standard")["ok"])
        self.assertEqual(self.io.committed["sclk"][1], 2679)

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            self.hw.apply_profile("Gibtsnicht")

    def test_epp_skipped_with_performance_governor(self):
        for i in range(8):
            self.io.files[f"{CPU}/cpu{i}/cpufreq/scaling_governor"] = "performance"
        r = self.hw.set_cpu({"epp": "power"})
        self.assertTrue(r["ok"], r)
        self.assertTrue(any("EPP" in n for n in r["notes"]))
        self.assertEqual(self.cpu_files("energy_performance_preference"), {"balance_performance"})

    def test_driver_rejection_reported(self):
        with mock.patch.object(self.io, "_od_write", side_effect=OSError(errno.EINVAL, "Invalid argument")):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertFalse(r["ok"])
        self.assertIn("rejected", r["errors"][0])
        self.assertEqual(self.hw.desired["gpu"], {})

    def test_readback_mismatch_reported(self):
        orig = self.io._od_write

        def ignore_commit(cmd):
            if cmd.split()[0] != "c":
                orig(cmd)

        with mock.patch.object(self.io, "_od_write", side_effect=ignore_commit):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertFalse(r["ok"])
        self.assertIn("expected 2300", r["errors"][0])
        self.assertIn("(error: sclk_max: expected 2300", self.hw._events[-1]["text"])

    def test_driver_rounding_of_default_clock_is_not_an_error(self):
        """Reale Karte: Standard 2679 gespeichert, der Treiber meldet nach dem Reset 2674."""
        self.io.default["sclk"][1] = 2674
        r = self.hw.apply_profile("Standard")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.hw._events[-1]["text"], "Profile Default")
        self.assertEqual(r["active_profile"], "Standard")      # wird trotz Rundung als aktiv erkannt

    def test_changed_driver_default_is_only_a_note(self):
        self.io.default["sclk"][1] = 2500          # deutlich anderer Standard, nichts verlangt
        r = self.hw.reset("gpu")
        self.assertTrue(r["ok"], r)

    def test_requested_clock_rounded_by_driver_is_accepted(self):
        orig = self.io._od_write

        def rounding(cmd):
            orig(cmd)
            if cmd.split()[0] == "c":
                self.io.committed["sclk"][1] -= 4   # Treiber rundet 2300 -> 2296

        with mock.patch.object(self.io, "_od_write", side_effect=rounding):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.hw.desired["gpu"], {"sclk_max": 2300})

    def test_clock_far_off_is_still_an_error(self):
        orig = self.io._od_write

        def off(cmd):
            orig(cmd)
            if cmd.split()[0] == "c":
                self.io.committed["sclk"][1] = 2679   # Wunsch 2300, Treiber bleibt bei 2679

        with mock.patch.object(self.io, "_od_write", side_effect=off):
            r = self.hw.set_gpu({"sclk_max": 2300})
        self.assertFalse(r["ok"])


class TestWhitelist(Base):
    def test_blocked_paths(self):
        for p in (DEV + "/power_dpm_force_performance_level", "/etc/passwd",
                  DEV + "/pp_table", HWMON + "/fan1_target", CPU + "/cpu0/online",
                  HWMON + "/pwm1_max", HWMON + "/pwm1_min", HWMON + "/temp1_input", HWMON + "/pwm2",
                  "/sys/class/drm/card1/device/hwmon/hwmon3/../pp_table"):
            with self.assertRaises(PermissionError, msg=p):
                self.hw._write(p, "1")

    def test_paths_must_match_exactly(self):
        # '$' würde vor einem angehängten Zeilenumbruch noch passen, '\d' auch Ziffern anderer Schriften
        for p in (OD + "\n", HWMON + "/pwm1\n", HWMON + "/pwm1_enable\n", HWMON + "/power1_cap\n",
                  CPU + "/cpu3/cpufreq/scaling_max_freq\n", CPU + "/intel_pstate/no_turbo\n",
                  OD + " ", "\n" + OD,
                  "/sys/class/drm/card٣/device/pp_od_clk_voltage",
                  CPU + "/cpu٣/cpufreq/scaling_max_freq",
                  HWMON.replace("hwmon3", "hwmon٣") + "/pwm1"):
            self.assertFalse(hwpaneld.write_allowed(p), repr(p))
            with self.assertRaises(PermissionError, msg=repr(p)):
                self.hw._write(p, "1")

    def test_allowed_paths(self):
        for p in (OD, HWMON + "/power1_cap", CPU + "/cpu3/cpufreq/scaling_max_freq",
                  CPU + "/intel_pstate/no_turbo", HWMON + "/pwm1", HWMON + "/pwm1_enable"):
            self.assertTrue(hwpaneld.write_allowed(p), p)

    def test_readonly_mode_never_writes(self):
        io = FakeIO()
        with tempfile.TemporaryDirectory() as tmp:
            hw = HW(io, tmp, readonly=True, probe_dmi=False)
            r = hw.set_gpu({"sclk_max": 2300})
            self.assertFalse(r["ok"])
            self.assertEqual(io.writes, [])
            self.assertEqual(os.listdir(tmp), [])


class TestStatus(Base):
    def test_gpu_status(self):
        g = self.hw.status()["gpu"]
        self.assertEqual(g["card"], "card1")
        self.assertEqual(g["pci_id"], "1002:73df")
        self.assertEqual(g["busy_pct"], 4)
        self.assertEqual((g["sclk_mhz"], g["mclk_mhz"]), (500, 96))
        self.assertEqual((g["temp_edge_c"], g["temp_junction_c"], g["temp_mem_c"]), (41, 43, 44))
        self.assertEqual((g["power_w"], g["power_cap_w"]), (11.0, 210))
        self.assertEqual((g["fan_rpm"], g["fan_pct"]), (1872, 49))
        self.assertEqual((g["vram_used_mib"], g["vram_total_mib"]), (700, 12272))
        self.assertEqual(g["perf_level"], "auto")

    def test_cpu_load_and_power(self):
        self.io.files["/proc/stat"] = ("cpu  1000 0 500 8000 0 0 0 0\n"
                                       + "".join(f"cpu{i} 125 0 62 1000 0 0 0 0\n" for i in range(8)))
        with mock.patch("hwpaneld.time.monotonic", side_effect=[100.0, 101.0]):
            self.hw._tick()
            self.io.files["/proc/stat"] = ("cpu  1100 0 600 8100 0 0 0 0\n"
                                           + "".join(f"cpu{i} 137 0 74 1012 0 0 0 0\n" for i in range(8)))
            self.io.files["/sys/class/powercap/intel-rapl:0/energy_uj"] = "14000000"
            self.hw._tick()
        c = self.hw.status()["cpu"]
        self.assertEqual(c["load_pct"], 66.7)
        self.assertEqual(len(c["load_cores_pct"]), 8)
        self.assertEqual(c["power_w"], 9.0)
        self.assertEqual(c["temp_c"], 35.0)
        self.assertEqual(c["freq_avg_mhz"], 800)

    def test_rapl_wraparound(self):
        self.io.files["/sys/class/powercap/intel-rapl:0/energy_uj"] = "262143000000"
        with mock.patch("hwpaneld.time.monotonic", side_effect=[10.0, 11.0]):
            self.hw._tick()
            self.io.files["/sys/class/powercap/intel-rapl:0/energy_uj"] = "5000000"
            self.hw._tick()
        self.assertIsNotNone(self.hw.status()["cpu"]["power_w"])
        self.assertGreaterEqual(self.hw.status()["cpu"]["power_w"], 0)

    def test_ram(self):
        r = self.hw.status()["ram"]
        self.assertEqual((r["total_mib"], r["available_mib"], r["used_mib"]), (16000, 11000, 5000))
        self.assertEqual(r["swap_used_mib"], 0)

    def test_info(self):
        i = self.hw.info()
        self.assertIn("Intel", i["cpu"]["model"])
        self.assertEqual(i["cpu"]["threads"], 8)
        self.assertTrue(i["cpu"]["turbo_supported"])
        self.assertEqual(i["cpu"]["governors"], ["performance", "powersave"])
        self.assertEqual(i["limits"]["gpu"]["sclk_max"], [500, 2679])


class TestHistory(Base):
    def test_samples_and_incremental_fetch(self):
        with mock.patch("hwpaneld.time.time", side_effect=itertools.count(1000.0, 1.0)):
            for _ in range(5):
                self.hw._tick()
            h = self.hw.history()
            self.assertEqual(len(h["samples"]), 5)
            s = h["samples"][-1]
            self.assertEqual((s["g_edge"], s["g_junc"], s["g_mem"], s["g_pow"]), (41, 43, 44, 11.0))
            self.assertEqual((s["g_busy"], s["g_clk"], s["g_fan"], s["c_temp"]), (4, 500, 1872, 35.0))
            cutoff = h["samples"][2]["t"]
            newer = self.hw.history(since=cutoff)["samples"]
            self.assertEqual([x["t"] for x in newer], [x["t"] for x in h["samples"][3:]])

    def test_event_in_the_same_tenth_as_the_last_sample_is_not_lost(self):
        """Der Client fragt mit dem Zeitstempel der letzten Probe nach Neuem. Zeitstempel sind auf 0,1 s gerundet:
        Ein Ereignis, das nach dieser Probe in dieselbe Zehntelsekunde fällt, darf dabei nicht verloren gehen."""
        with mock.patch("hwpaneld.time.time", return_value=1000.04):
            self.hw._tick()
            last = self.hw.history()["samples"][-1]["t"]
            self.hw._event(hwpaneld.Msg("Profile {name}", name="KI"))   # nach dem Abruf, gleiche Zehntelsekunde
        newer = self.hw.history(since=last)
        self.assertEqual([e["text"] for e in newer["events"]], ["Profile KI"])
        self.assertEqual(newer["samples"], [], "Proben bleiben streng neuer als since")

    def test_ring_buffer_limit(self):
        self.hw._hist = collections.deque(maxlen=60)
        for _ in range(100):
            self.hw._tick()
        self.assertEqual(len(self.hw.history()["samples"]), 60)

    def test_events_for_profile_reset_manual(self):
        self.hw.apply_profile("KI")
        self.hw.set_gpu({"power_cap_w": 200})
        self.hw.reset("gpu")
        texts = [e["text"] for e in self.hw.history()["events"]]
        self.assertEqual(texts, ["Profile KI", "Manual: Power limit 200", "Reset (GPU)"])

    def test_history_rejects_bad_since(self):
        for bad in ("x", True, [1]):
            with self.assertRaises(ValueError):
                self.hw.history(since=bad)


class TestDetectProfile(Base):
    def test_detection_follows_hardware(self):
        self.assertEqual(self.hw.status()["active_profile"], "Standard")
        self.hw.apply_profile("KI")
        self.assertEqual(self.hw.status()["active_profile"], "KI")
        self.hw.apply_profile("Gaming")
        self.assertEqual(self.hw.status()["active_profile"], "Gaming")
        self.hw.set_gpu({"sclk_max": 2000})
        self.assertIsNone(self.hw.status()["active_profile"])

    def test_detection_survives_daemon_restart(self):
        self.hw.apply_profile("KI")
        hw2 = HW(self.io, self.tmp.name, probe_dmi=False)
        self.assertEqual(hw2.status()["active_profile"], "KI")
        self.assertEqual(hw2.info()["active_profile"], "KI")

    def test_detection_after_external_change(self):
        self.hw.apply_profile("Gaming")
        for i in range(8):
            self.io.files[f"{CPU}/cpu{i}/cpufreq/energy_performance_preference"] = "power"
        self.assertIsNone(self.hw.status()["active_profile"])


class TestResume(Base):
    def test_reapply_after_resume(self):
        self.hw.resume_delay = 0
        self.hw.set_gpu({"sclk_max": 2300})
        self.io.committed = copy.deepcopy(self.io.default)
        self.io.staged = copy.deepcopy(self.io.default)
        with mock.patch.object(HW, "_susp_offset", staticmethod(lambda: self.hw._susp + 10.0)):
            self.hw._tick()
        self.assertEqual(self.io.committed["sclk"][1], 2300)

    def test_no_reapply_without_resume(self):
        self.hw.set_gpu({"sclk_max": 2300})
        self.io.committed = copy.deepcopy(self.io.default)
        self.hw._tick()
        self.assertEqual(self.io.committed["sclk"][1], 2679)


class TestProfilesAndConfig(Base):
    def test_save_delete_autostart(self):
        self.hw.save_profile("Leise", {"gpu": {"sclk_max": 1800, "power_cap_w": 120}, "cpu": {}})
        with open(os.path.join(self.tmp.name, "profiles.json")) as f:
            saved = json.load(f)
        self.assertEqual(saved["Leise"]["gpu"]["sclk_max"], 1800)
        self.hw.set_autostart("Leise")
        with open(os.path.join(self.tmp.name, "config.json")) as f:
            self.assertEqual(json.load(f)["autostart_profile"], "Leise")
        self.hw.delete_profile("Leise")
        self.assertIsNone(self.hw.cfg["autostart_profile"])
        self.assertNotIn("Leise", self.hw.profiles)

    def test_invalid_profiles_rejected(self):
        for name, s in (("Standard", {}), ("", {}), ("a/b", {}), ("x" * 40, {}),
                        ("Boost", {"gpu": {"sclk_max": 3000}})):
            with self.assertRaises(ValueError, msg=name):
                self.hw.save_profile(name, s)
        with self.assertRaises(ValueError):
            self.hw.set_autostart("Gibtsnicht")

    def test_autostart_applied_like_daemon_start(self):
        self.hw.set_autostart("KI")
        hw2 = HW(self.io, self.tmp.name, probe_dmi=False)
        r = hw2.apply_profile(hw2.cfg["autostart_profile"])
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.io.committed["sclk"][1], 2300)


CURVE = [[30, 40], [40, 50], [50, 60], [60, 70], [70, 80], [80, 90]]


class TestFan(Base):
    def temps(self, edge=None, junc=None):
        if edge is not None:
            self.io.files[HWMON + "/temp1_input"] = str(int(edge * 1000))
        if junc is not None:
            self.io.files[HWMON + "/temp2_input"] = str(int(junc * 1000))

    def pwm(self):
        return int(self.io.files[HWMON + "/pwm1"])

    def enable(self):
        return self.io.files[HWMON + "/pwm1_enable"]

    def pwm_writes(self):
        return [w for w in self.io.writes if w[0] == HWMON + "/pwm1"]

    def start(self, edge=41, junc=43, curve=CURVE, sensor="edge"):
        self.temps(edge, junc)
        r = self.hw.set_fan({"sensor": sensor, "curve": curve})
        self.assertTrue(r["ok"], r)
        return r

    # ---- Kurve und Validierung

    def test_interpolation_and_clamping(self):
        f = hwpaneld.fan_curve_value
        self.assertEqual([f(CURVE, t) for t in (10, 30, 35, 55, 80, 95)], [40, 40, 45, 65, 90, 90])

    def test_validation_normalizes(self):
        v = self.hw._validate_fan({"curve": [[30.0, 40.0], [80, 90]]})
        self.assertEqual(v, {"sensor": "edge", "curve": [[30, 40], [80, 90]]})
        self.assertIsNone(self.hw._validate_fan(None))
        self.assertIsNone(self.hw._validate_fan({}))
        self.assertIsNone(self.hw._validate_fan({"mode": "auto", "curve": CURVE}))

    def test_validation_rejects_bad_curves(self):
        bad = [
            "x", {"curve": CURVE, "foo": 1}, {"mode": "static", "curve": CURVE},
            {"curve": CURVE, "sensor": "gpu"}, {"sensor": "edge"}, {"curve": [[30, 40]]},
            {"curve": [[t, 60] for t in range(20, 31)]},                   # 11 Punkte
            {"curve": [[30, 40], [30, 60]]},                               # gleiche Temperatur
            {"curve": [[50, 60], [40, 70]]},                               # Temperatur sinkt
            {"curve": [[30, 60], [80, 50]]},                               # Prozent sinkt
            {"curve": [[30, 40], [80, 101]]}, {"curve": [[30, -1], [80, 90]]},
            {"curve": [[30, 40], [111, 90]]}, {"curve": [[-1, 40], [80, 90]]},
            {"curve": [[30, True], [80, 90]]}, {"curve": [["30", 40], [80, 90]]},
            {"curve": [[30, 40, 1], [80, 90]]}, {"curve": [30, 80]},
            {"curve": [[30, 0], [90, 40]]},                                # bei 60 °C unter 30 %
            {"curve": [[30, 40], [90, 40]]},                               # bei 80 °C unter 50 %
        ]
        for b in bad:
            with self.assertRaises(ValueError, msg=str(b)):
                self.hw._validate_fan(b)

    def test_quiet_curve_with_zero_percent_is_allowed(self):
        v = self.hw._validate_fan({"curve": [[30, 0], [50, 0], [60, 30], [80, 50], [90, 70]]})
        self.assertEqual(v["curve"][0], [30, 0])

    def test_unsupported_hardware(self):
        del self.io.files[HWMON + "/pwm1"]
        self.assertFalse(self.hw.fan_supported())
        self.assertFalse(self.hw.info()["fan"]["supported"])
        with self.assertRaises(ValueError):
            self.hw.set_fan({"curve": CURVE})

    # ---- Regelung

    def test_set_fan_takes_manual_control(self):
        r = self.start(edge=41)
        self.assertEqual(self.enable(), "1")
        self.assertEqual(self.pwm(), round(51 * 255 / 100))
        f = r["fan"]
        self.assertEqual((f["mode"], f["target_pct"], f["applied_pct"], f["hw_mode"]),
                         ("curve", 51, 51, "manual"))
        self.assertEqual(r["settings"]["fan"]["sensor"], "edge")

    def test_rise_is_immediate(self):
        self.start(edge=41)
        self.temps(edge=65)
        self.hw.fan_step(now=1000)
        self.assertEqual(self.pwm(), round(75 * 255 / 100))

    def test_spindown_delay(self):
        self.start(edge=65)
        self.temps(edge=41)
        high = self.pwm()
        self.hw.fan_step(now=1000)
        self.hw.fan_step(now=1004.9)
        self.assertEqual(self.pwm(), high)
        self.hw.fan_step(now=1005.1)
        self.assertEqual(self.pwm(), round(51 * 255 / 100))

    def test_spindown_timer_resets_when_target_rises_again(self):
        self.start(edge=65)
        high = self.pwm()
        self.temps(edge=41)
        self.hw.fan_step(now=1000)
        self.temps(edge=66)             # Ziel wieder >= aktuell
        self.hw.fan_step(now=1003)
        self.temps(edge=41)
        self.hw.fan_step(now=1004)
        self.hw.fan_step(now=1008)      # nur 4 s seit dem neuen Absenken
        self.assertGreaterEqual(self.pwm(), high)

    def test_change_threshold_avoids_tiny_writes(self):
        self.start(edge=41)
        n = len(self.pwm_writes())
        self.temps(edge=42)             # Ziel 52, Differenz 1
        self.hw.fan_step(now=1000)
        self.assertEqual(len(self.pwm_writes()), n)
        self.temps(edge=43)             # Ziel 53, Differenz 2
        self.hw.fan_step(now=1001)
        self.assertEqual(len(self.pwm_writes()), n + 1)

    def test_other_sensor(self):
        self.start(edge=41, junc=65, curve=CURVE, sensor="junction")
        self.assertEqual(self.pwm(), round(75 * 255 / 100))

    def test_pwm_scaling_follows_pwm1_max(self):
        self.io.files[HWMON + "/pwm1_max"] = "100"
        self.start(edge=41)
        self.assertEqual(self.pwm(), 51)

    def test_safety_override_and_release(self):
        self.start(edge=60, junc=80)
        self.temps(junc=101)
        self.hw.fan_step(now=1000)
        self.assertEqual(self.pwm(), 255)
        self.assertTrue(self.hw.fan_status()["override"])
        self.temps(junc=96)             # noch nicht weit genug abgekühlt
        self.hw.fan_step(now=1001)
        self.assertTrue(self.hw.fan_status()["override"])
        self.temps(junc=94)
        self.hw.fan_step(now=1002)
        self.assertFalse(self.hw.fan_status()["override"])
        self.hw.fan_step(now=1008)      # Spindown abgelaufen
        self.assertEqual(self.pwm(), round(70 * 255 / 100))
        texts = [e["text"] for e in self.hw.history()["events"]]
        self.assertTrue(any("safety active" in t for t in texts))
        self.assertTrue(any("safety ended" in t for t in texts))

    def test_sensor_failure_falls_back_to_auto_and_recovers(self):
        self.start(edge=50)
        saved = self.io.files.pop(HWMON + "/temp1_input")
        self.hw.fan_step(now=1000)
        self.assertEqual(self.enable(), "2")
        self.assertEqual(self.hw.fan_status()["error"], "sensor not readable")
        self.io.files[HWMON + "/temp1_input"] = saved
        self.hw.fan_step(now=1001)
        self.assertEqual(self.enable(), "1")
        self.assertIsNone(self.hw.fan_status()["error"])

    def test_driver_rounding_and_ramp_are_not_errors(self):
        """amdgpu rechnet über ganze Prozent und liefert beim Lesen teils den aktuellen statt des gesetzten Werts."""
        orig = self.io.read
        mode = {"kind": "round"}

        def reading(path):
            v = orig(path)
            if path.endswith("/pwm1") and mode["kind"] == "round":
                return str(int(int(int(v) * 100 / 255) * 255 / 100))     # Hin- und Rückrechnung über ganze %
            if path.endswith("/pwm1") and mode["kind"] == "lag":
                return "0"                                               # Anlauf: Treiber meldet noch den alten Wert
            return v

        for kind in ("round", "lag"):
            mode["kind"] = kind
            self.hw._fan_release()
            with mock.patch.object(self.io, "read", side_effect=reading):
                self.temps(edge=30, junc=33)
                r = self.hw.set_fan({"curve": CURVE})
                self.assertTrue(r["ok"], (kind, r))
                for edge in range(30, 86, 1):
                    self.temps(edge=edge, junc=edge + 3)
                    self.hw.fan_step(now=time_now_plus(1000 + edge))
                    st = self.hw.fan_status()
                    self.assertIsNone(st["error"], (kind, edge, st))
                    self.assertEqual(self.enable(), "1", (kind, edge))
            self.assertEqual(self.pwm(), round(90 * 255 / 100))

    def test_write_error_falls_back_to_auto_and_retries(self):
        orig = self.io.write

        def failing(path, value):
            if path.endswith("/pwm1"):
                raise OSError(errno.EIO, "Input/output error")
            return orig(path, value)

        with mock.patch.object(self.io, "write", side_effect=failing):
            r = self.hw.set_fan({"curve": CURVE})
            self.assertFalse(r["ok"])
            self.assertIn("Fan", r["errors"][0])
            self.assertEqual(self.enable(), "2")
            self.hw.fan_step(now=time_now_plus(5))        # Wartezeit noch nicht abgelaufen
        self.hw.fan_step(now=time_now_plus(60))
        self.assertEqual(self.enable(), "1")
        self.assertIsNone(self.hw.fan_status()["error"])

    def test_external_reset_to_auto_is_taken_back(self):
        self.start(edge=41)
        self.io.files[HWMON + "/pwm1_enable"] = "2"      # z. B. nach Standby
        self.hw.fan_step(now=1000)
        self.assertEqual(self.enable(), "1")
        self.assertEqual(self.pwm(), round(51 * 255 / 100))

    def test_shutdown_returns_to_auto(self):
        self.start()
        self.hw.fan_shutdown()
        self.assertEqual(self.enable(), "2")
        self.assertIsNone(self.hw.fan_status()["curve"])

    # ---- Profile

    def test_profile_with_fan(self):
        self.temps(41, 43)
        self.hw.save_profile("Leise", {"gpu": {"sclk_max": 2000}, "fan": {"curve": CURVE}})
        r = self.hw.apply_profile("Leise")
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.enable(), r["active_profile"]), ("1", "Leise"))
        self.assertEqual(self.hw.info()["profiles"]["Leise"]["fan"]["curve"], CURVE)
        r = self.hw.apply_profile("KI")                  # Profil ohne Lüfter: Automatik
        self.assertEqual((self.enable(), r["active_profile"]), ("2", "KI"))
        self.hw.apply_profile("Leise")
        r = self.hw.apply_profile("Standard")
        self.assertEqual((self.enable(), r["active_profile"]), ("2", "Standard"))
        self.assertEqual(self.hw.desired["fan"], None)

    def test_detection_needs_matching_fan(self):
        self.temps(41, 43)
        self.hw.save_profile("Leise", {"fan": {"curve": CURVE}})
        self.hw.apply_profile("Leise")
        self.assertEqual(self.hw.status()["active_profile"], "Leise")
        self.hw.set_fan({"mode": "auto"})            # nur Lüfter-Profil: ohne Kurve entspricht es Standard
        self.assertEqual(self.hw.status()["active_profile"], "Standard")
        self.hw.set_fan({"curve": [[30, 40], [80, 90]]})
        self.assertIsNone(self.hw.status()["active_profile"])

    def test_profile_persistence_and_invalid_fan_ignored(self):
        self.hw.save_profile("Leise", {"fan": {"sensor": "junction", "curve": CURVE}})
        hw2 = HW(self.io, self.tmp.name, probe_dmi=False)
        self.assertEqual(hw2.profiles["Leise"]["fan"], {"sensor": "junction", "curve": CURVE})
        bad = dict(hw2.profiles)
        bad["Kaputt"] = {"gpu": {}, "cpu": {}, "fan": {"curve": [[30, 0], [90, 10]]}}
        with open(os.path.join(self.tmp.name, "profiles.json"), "w") as f:
            json.dump(bad, f)
        hw3 = HW(self.io, self.tmp.name, probe_dmi=False)
        self.assertIn("Leise", hw3.profiles)
        self.assertNotIn("Kaputt", hw3.profiles)

    def test_reset_targets(self):
        self.start()
        self.hw.reset("gpu")
        self.assertEqual(self.enable(), "1")
        self.hw.reset("fan")
        self.assertEqual(self.enable(), "2")
        self.start()
        self.hw.reset("all")
        self.assertEqual(self.enable(), "2")
        self.assertIsNone(self.hw.desired["fan"])

    def test_manual_set_fan_event_and_auto(self):
        self.start()
        self.hw.set_fan({"mode": "auto"})
        self.assertEqual(self.enable(), "2")
        texts = [e["text"] for e in self.hw.history()["events"]]
        self.assertEqual(texts[0], "Manual: Fan curve edge 30-80 °C, 40-90 %")
        self.assertEqual(texts[1], "Manual: Fan automatic")

    def test_config_overrides(self):
        with open(os.path.join(self.tmp.name, "config.json"), "w") as f:
            json.dump({"fan_safety_junction_c": 90, "fan_min_rules": [], "fan_spindown_s": 1}, f)
        hw = HW(self.io, self.tmp.name, probe_dmi=False)
        self.assertTrue(hw.set_fan({"curve": [[30, 10], [90, 20]]})["ok"])
        self.temps(junc=91)
        hw.fan_step(now=1000)
        self.assertEqual(self.pwm(), 255)
        self.assertEqual(hw.info()["fan"]["safety_junction_c"], 90)

    def test_status_history_and_info(self):
        self.start()
        st = self.hw.status()
        self.assertEqual(st["fan"]["mode"], "curve")
        self.assertEqual(st["gpu"]["fan_mode"], "1")
        self.hw._tick()
        self.assertIn("g_fanp", self.hw.history()["samples"][-1])
        i = self.hw.info()["fan"]
        self.assertEqual((i["supported"], i["sensors"], i["points"]), (True, ["edge", "junction", "mem"], [2, 10]))

    def test_readonly_never_writes_fan(self):
        io = FakeIO()
        with tempfile.TemporaryDirectory() as tmp:
            hw = HW(io, tmp, readonly=True, probe_dmi=False)
            r = hw.set_fan({"curve": CURVE})
            self.assertFalse(r["ok"])
            self.assertEqual(io.writes, [])

    def test_write_whitelist_for_fan(self):
        for p in (HWMON + "/pwm1", HWMON + "/pwm1_enable"):
            self.assertTrue(hwpaneld.write_allowed(p), p)
        for p in (HWMON + "/pwm1_max", HWMON + "/fan1_target", HWMON + "/temp1_input",
                  "/sys/class/hwmon/hwmon1/pwm1"):
            with self.assertRaises(PermissionError, msg=p):
                self.hw._write(p, "1")

    # ---- Schleife und Watchdog

    def test_fan_loop_thread(self):
        self.start(edge=41)
        self.temps(edge=65)
        with mock.patch.object(hwpaneld, "FAN_INTERVAL_S", 0.01):
            th = threading.Thread(target=self.hw.run_fan, daemon=True)
            th.start()
            for _ in range(200):
                if self.pwm() == round(75 * 255 / 100):
                    break
                threading.Event().wait(0.01)
            self.hw._stop.set()
            th.join(2)
        self.assertEqual(self.pwm(), round(75 * 255 / 100))
        self.assertFalse(th.is_alive())

    def test_sd_notify(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = os.path.join(d, "n.sock")
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            srv.bind(path)
            srv.settimeout(2)
            try:
                with mock.patch.dict(os.environ, {"NOTIFY_SOCKET": path}):
                    hwpaneld.sd_notify("WATCHDOG=1")
                self.assertEqual(srv.recv(64), b"WATCHDOG=1")
            finally:
                srv.close()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOTIFY_SOCKET", None)
            hwpaneld.sd_notify("WATCHDOG=1")      # ohne Socket: keine Wirkung, kein Fehler


def time_now_plus(seconds):
    import time as _t
    return _t.monotonic() + seconds


class TestSocketAndCli(Base):
    def setUp(self):
        super().setUp()
        self.sock_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.sock_dir.name, "t.sock")
        self.srv = hwpaneld.make_server(self.hw, self.path)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        self._old = hwpanelctl.SOCKET_PATH
        hwpanelctl.SOCKET_PATH = self.path
        # die Erwartungen dieser Tests sind deutsch: Sprache festnageln, unabhängig von der Umgebung
        self._env = mock.patch.dict(os.environ, {"HWPANEL_LANG": "de"})
        self._env.start()
        i18n.set_language("de")

    def tearDown(self):
        self._env.stop()
        i18n.set_language("en")
        hwpanelctl.SOCKET_PATH = self._old
        self.srv.shutdown()
        self.srv.server_close()
        self.sock_dir.cleanup()
        super().tearDown()

    def test_ping_and_persistent_connection(self):
        s = socket.socket(socket.AF_UNIX)
        s.connect(self.path)
        f = s.makefile("rwb")
        for _ in range(3):
            f.write(b'{"cmd": "ping"}\n')
            f.flush()
            self.assertTrue(json.loads(f.readline())["ok"])
        s.close()

    def test_bad_requests(self):
        self.assertFalse(hwpanelctl.call({"cmd": "nope"})["ok"])
        s = socket.socket(socket.AF_UNIX)
        s.connect(self.path)
        s.sendall(b"kein json\n[1]\n")
        f = s.makefile("rb")
        self.assertFalse(json.loads(f.readline())["ok"])
        self.assertFalse(json.loads(f.readline())["ok"])
        s.close()

    def test_oc_rejected_over_socket(self):
        r = hwpanelctl.call({"cmd": "set_gpu", "values": {"sclk_max": 2900}})
        self.assertFalse(r["ok"])
        self.assertIn("outside the allowed range", r["error"])
        self.assertEqual(self.io.committed["sclk"][1], 2679)

    def test_cli_roundtrip(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hwpanelctl.print_status(hwpanelctl.call({"cmd": "status"}))
            hwpanelctl.print_info(hwpanelctl.call({"cmd": "info"}))
            rc = hwpanelctl.show_result(hwpanelctl.call({"cmd": "apply_profile", "name": "KI"}))
            rc2 = hwpanelctl.show_result(hwpanelctl.call({"cmd": "set_gpu", "values": {"sclk_max": 9999}}))
        text = out.getvalue()
        self.assertEqual((rc, rc2), (0, 1))
        self.assertIn("KI", text)
        self.assertIn("2300", text)
        self.assertIn("Lüfter 1872 RPM", text)

    def test_cli_argument_parsing(self):
        for argv, expected in (
                (["hwpanelctl", "gpu", "--sclk", "2300"], {"sclk_max": 2300}),
                (["hwpanelctl", "gpu", "--mclk", "900", "--power", "150"], {"mclk_max": 900, "power_cap_w": 150}),
        ):
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(hwpanelctl.main(), 0)
            for k, v in expected.items():
                self.assertEqual(self.hw.desired["gpu"][k], v)
        with mock.patch.object(sys, "argv", ["hwpanelctl", "cpu", "--turbo", "off", "--max-mhz", "3000"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hwpanelctl.main(), 0)
        self.assertEqual(self.hw.desired["cpu"], {"turbo": False, "max_mhz": 3000})

    def run_cli(self, *args):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["hwpanelctl", *args]), contextlib.redirect_stdout(out):
            rc = hwpanelctl.main()
        return rc, out.getvalue()

    def test_cli_fan_commands(self):
        self.io.files[HWMON + "/temp1_input"] = "41000"
        rc, out = self.run_cli("fan", "curve", "30:40,40:50,50:60,60:70,70:80,80:90")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.io.files[HWMON + "/pwm1_enable"], "1")
        self.assertIn("Lüfter Kurve (edge)", out)
        rc, out = self.run_cli("status")
        self.assertIn("Lüfter-Regelung  Sensor edge", out)
        rc, out = self.run_cli("info")
        self.assertIn("Lüfter Sensoren: edge, junction, mem", out)
        rc, out = self.run_cli("fan", "curve", "30:0,90:40")           # verletzt die Schutzregeln
        self.assertEqual(rc, 1)
        self.assertIn("Schutzregel", out)
        rc, out = self.run_cli("fan", "auto")
        self.assertEqual(rc, 0)
        self.assertEqual(self.io.files[HWMON + "/pwm1_enable"], "2")
        with self.assertRaises(SystemExit):
            self.run_cli("fan", "curve")
        with self.assertRaises(SystemExit):
            self.run_cli("fan", "curve", "kaputt")

    def test_cli_save_profile_with_fan_and_reset(self):
        rc, out = self.run_cli("save", "Desktop", "--fan-curve", "30:0,50:0,60:30,80:50,90:70", "--fan-sensor", "junction")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.hw.profiles["Desktop"]["fan"],
                         {"sensor": "junction", "curve": [[30, 0], [50, 0], [60, 30], [80, 50], [90, 70]]})
        rc, out = self.run_cli("save", "Plain", "--sclk", "2000")
        self.assertNotIn("fan", self.hw.profiles["Plain"])
        self.run_cli("apply", "Desktop")
        self.assertEqual(self.io.files[HWMON + "/pwm1_enable"], "1")
        rc, out = self.run_cli("reset", "fan")
        self.assertEqual(rc, 0)
        self.assertEqual(self.io.files[HWMON + "/pwm1_enable"], "2")

    def test_set_fan_over_socket(self):
        r = hwpanelctl.call({"cmd": "set_fan", "values": {"curve": CURVE}})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["fan"]["mode"], "curve")
        r = hwpanelctl.call({"cmd": "set_fan", "values": {"curve": [[30, 40]]}})
        self.assertFalse(r["ok"])
        self.assertIn("points", r["error"])


if __name__ == "__main__":
    unittest.main()
