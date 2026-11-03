"""Demo daemon for the GUI: real HW logic on FakeIO with a simulated history.

Only used for rendering and trying out the interface without hardware.
The history spans 3600 s with idle, gaming load, AI load and an
outlier under Standard, each with a cool-down phase.
"""

import random
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hwpaneld  # noqa: E402
from test_hwpaneld import CPU, DEV, HWMON, FakeIO  # noqa: E402

DMI = """Handle 0x0031, DMI type 17, 40 bytes
Memory Device
\tSize: 8 GiB
\tLocator: DIMM_A1
\tType: DDR4
\tSpeed: 2133 MT/s
\tConfigured Memory Speed: 2133 MT/s

Handle 0x0033, DMI type 17, 40 bytes
Memory Device
\tSize: 8 GiB
\tLocator: DIMM_B1
\tType: DDR4
\tSpeed: 2133 MT/s
\tConfigured Memory Speed: 2133 MT/s
"""

# (start, end, kind of load, profile event at the start)
SCHEDULE = [
    (0, 600, "idle", None),
    (600, 1260, "gaming", "Gaming"),
    (1260, 1700, "idle", None),
    (1700, 2500, "ki", "KI"),
    (2500, 3330, "idle", "Standard"),
    (3330, 3450, "burst", None),
    (3450, 3600, "idle", None),
]
LOADS = {
    #           GPU W, busy %, clock, CPU W, CPU %, CPU MHz
    "idle":   (11,   3,   30,   9,   4,   900),
    "gaming": (186,  97,  2640, 58,  58,  4100),
    "ki":     (142,  100, 2300, 24,  18,  2400),
    "burst":  (200,  99,  2700, 46,  38,  3800),
}


class DemoClient:
    def __init__(self, duration=3600, seed=7):
        self.rnd = random.Random(seed)
        self.tmp = tempfile.TemporaryDirectory()
        self.io = FakeIO()
        self.io.files["/sys/class/drm/card1/device/hwmon"] = ""  # unused
        self.hw = hwpaneld.HW(self.io, self.tmp.name, probe_dmi=False)
        self.hw.ram_modules = hwpaneld.parse_dmidecode(DMI)
        self.hw.resume_delay = 0
        # Example profiles for the demo only; in real operation the curves are created by the user
        self.hw.save_profile("Gaming", {"gpu": {}, "cpu": {"epp": "performance"},
                                        "fan": {"sensor": "edge", "curve": [[30, 40], [50, 55], [65, 70], [80, 90]]}})
        self.hw.save_profile("KI", {"gpu": {"sclk_max": 2300}, "cpu": {},
                                    "fan": {"sensor": "edge", "curve": [[30, 40], [50, 50], [70, 70], [80, 80]]}})
        self._simulate(duration)

    # ---- Simulation

    def _simulate(self, duration):
        f = self.io.files
        clock = [time.time() - duration]
        st = dict(edge=40.0, junc=42.0, mem=42.0, cpu=34.0, gp=11.0, cp=9.0,
                  busy=3.0, load=4.0, dip=0, jidx=0, user=0, idle=0)
        energy = [5_000_000]
        patches = [mock.patch("time.time", lambda: clock[0]),
                   mock.patch("time.monotonic", lambda: clock[0])]
        for p in patches:
            p.start()
        try:
            for sec in range(duration):
                clock[0] += 1.0
                kind = "idle"
                for a, b, k, ev in SCHEDULE:
                    if a <= sec < b:
                        kind = k
                        if sec == a and ev:
                            self.hw.apply_profile(ev)
                        break
                self._step(sec, kind, st, energy)
                self.hw.fan_step()
                self.hw._tick()
        finally:
            for p in patches:
                p.stop()

    def _step(self, sec, kind, st, energy):
        f, r = self.io.files, self.rnd
        gp, busy, clk, cp, load, cmhz = LOADS[kind]
        if kind not in ("idle",):
            # settling and occasional dips (loading screen, menu)
            if st["dip"] > 0:
                st["dip"] -= 1
                gp, busy, load = 70, 40, 15
            elif r.random() < 0.004:
                st["dip"] = r.randint(6, 14)
            gp += r.gauss(0, 7)
            busy = min(100, busy + r.gauss(0, 1.5))
            load = max(2, load + r.gauss(0, 6))
            cp = max(8, cp + r.gauss(0, 3))
        else:
            gp += r.gauss(0, 0.8)
            cp += r.gauss(0, 0.6)
            load = max(1, load + r.gauss(0, 2))
        cap = self.io.committed["sclk"][1]
        clk = min(clk, cap) + (r.gauss(0, 25) if kind != "idle" else 0)
        a = lambda cur, tgt, tau: cur + (tgt - cur) / tau
        st["gp"] = a(st["gp"], gp, 2.0)
        st["cp"] = a(st["cp"], cp, 2.0)
        st["busy"] = a(st["busy"], busy, 2.0)
        st["load"] = a(st["load"], load, 2.0)
        st["edge"] = a(st["edge"], 38 + 0.18 * st["gp"], 40.0)
        st["mem"] = a(st["mem"], 40 + 0.22 * st["gp"], 28.0)
        st["junc"] = a(st["junc"], st["edge"] + 4 + 0.09 * st["gp"], 7.0)
        st["cpu"] = a(st["cpu"], 33 + 0.55 * st["cp"], 18.0)

        edge, junc, mem = st["edge"], st["junc"], st["mem"]
        f[HWMON + "/temp1_input"] = str(int(edge * 1000))
        f[HWMON + "/temp2_input"] = str(int(junc * 1000))
        f[HWMON + "/temp3_input"] = str(int(mem * 1000))
        f[HWMON + "/power1_average"] = str(int(st["gp"] * 1e6))
        f[HWMON + "/freq1_input"] = str(int(max(0, clk) * 1e6))
        f[HWMON + "/freq2_input"] = str(int((562 if kind != "idle" else 48) * 1e6))
        f[DEV + "/gpu_busy_percent"] = str(int(st["busy"]))
        if f[HWMON + "/pwm1_enable"] == "1":
            pwm = int(f[HWMON + "/pwm1"])
            rpm = 0 if pwm < 38 else int(600 + pwm / 255 * 2400)
        else:  # driver automatic: the fan is off at idle and only starts up from about 47 °C
            rpm = 0 if edge < 47 else int(700 + (edge - 47) * 52)
            f[HWMON + "/pwm1"] = str(int(rpm / 3000 * 255))
        f[HWMON + "/fan1_input"] = str(rpm)
        f[DEV + "/mem_info_vram_used"] = str(int((900 if kind == "idle" else 7400) * 2 ** 20))
        f["/sys/class/hwmon/hwmon1/temp1_input"] = str(int(st["cpu"] * 1000))
        energy[0] += int(st["cp"] * 1e6)
        f["/sys/class/powercap/intel-rapl:0/energy_uj"] = str(energy[0])
        busy_j = st["load"] / 100 * 800
        st["user"] += int(busy_j)
        st["idle"] += int(800 - busy_j)
        lines = [f"cpu  {st['user']} 0 0 {st['idle']} 0 0 0 0"]
        for i in range(8):
            lines.append(f"cpu{i} {st['user'] // 8} 0 0 {st['idle'] // 8} 0 0 0 0")
        f["/proc/stat"] = "\n".join(lines) + "\n"
        for i in range(8):
            f[f"{CPU}/cpu{i}/cpufreq/scaling_cur_freq"] = str(int((cmhz + r.gauss(0, 80)) * 1000))
        used = 4400 if kind == "idle" else 9100
        f["/proc/meminfo"] = (f"MemTotal:       16384000 kB\nMemAvailable:   {16384000 - used * 1024} kB\n"
                              "Cached:          5324800 kB\nBuffers:           10240 kB\n"
                              "SwapTotal:       4096000 kB\nSwapFree:        4096000 kB\n")

    def close(self):
        self.tmp.cleanup()

    # ---- Interface like DaemonClient

    def call(self, req):
        try:
            return self.hw.handle(req)
        except (ValueError, TypeError) as e:
            return hwpaneld.error_response(e)   # like the real server: text and message


if __name__ == "__main__":
    import json
    c = DemoClient()
    st = c.call({"cmd": "status"})
    print(json.dumps(st["gpu"], indent=1))
    print(json.dumps(st["cpu"], indent=1)[:600])
    print(json.dumps(c.call({"cmd": "info"})["limits"], indent=1))
    h = c.call({"cmd": "history"})
    print(len(h["samples"]), h["events"])
    print(max(s["g_junc"] for s in h["samples"]), max(s["g_pow"] for s in h["samples"]))
