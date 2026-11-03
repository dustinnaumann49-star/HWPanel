#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 shadoweagle

"""hwpaneld: root daemon for monitoring and limiting GPU and CPU clocks.

No overclocking: the upper limits are the driver defaults, which are determined on the
first start and stored in defaults.json. Write access is restricted to a fixed
whitelist of sysfs paths.
"""

import argparse
import collections
import errno
import glob
import grp
import json
import math
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import traceback

from hwpanel_i18n import Msg, MsgError

VERSION = "0.1.0"
DATA_DIR = "/var/lib/hwpanel"
SOCKET_PATH = "/run/hwpanel/hwpanel.sock"

GPU_KEYS = ("sclk_max", "mclk_max", "power_cap_w")
CPU_KEYS = ("max_mhz", "turbo", "epp", "governor")
BUILTIN = "Standard"

# Fan: sensor choice, limits of the curve and control parameters
FAN_SENSORS = {"edge": "temp1_input", "junction": "temp2_input", "mem": "temp3_input"}
FAN_POINTS = (2, 10)           # allowed number of curve points
FAN_TEMP_RANGE = (0, 110)      # allowed temperatures of the curve points (°C)
FAN_RULES = [[60, 30], [80, 50]]   # minimum speed: at >= temperature, at least this percent
FAN_SAFETY_JUNCTION = 100      # from this junction temperature on, always 100 %
FAN_SAFETY_RELEASE = 5         # return to the curve only after cooling down by this much (°C)
FAN_SPINDOWN_S = 5.0           # lowering only after the lower target value has held for this many seconds
FAN_THRESHOLD = 2              # changes below this many percentage points are not written
FAN_INTERVAL_S = 0.5
FAN_EXAMPLE = [[30, 40], [40, 50], [50, 60], [60, 70], [70, 80], [80, 90]]

DEFAULT_PROFILES = {
    "Gaming": {"gpu": {}, "cpu": {"epp": "performance"}},
    "KI": {"gpu": {"sclk_max": 2300}, "cpu": {}},
}

ALLOWED_WRITE = [re.compile(p, re.ASCII) for p in (
    r"/sys/class/drm/card\d+/device/pp_od_clk_voltage",
    r"/sys/class/drm/card\d+/device/hwmon/hwmon\d+/power1_cap",
    r"/sys/class/drm/card\d+/device/hwmon/hwmon\d+/(pwm1|pwm1_enable)",
    r"/sys/devices/system/cpu/cpu\d+/cpufreq/(scaling_max_freq|scaling_governor|energy_performance_preference)",
    r"/sys/devices/system/cpu/intel_pstate/no_turbo",
    r"/sys/devices/system/cpu/cpufreq/boost",
)]


def write_allowed(path):
    """Only exactly these sysfs paths may be written.

    fullmatch instead of '^...$': '$' also matches before an appended newline.
    re.ASCII: '\\d' should only be 0-9, not digits of other scripts."""
    return any(r.fullmatch(path) for r in ALLOWED_WRITE)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _fmt(e):
    return e.strerror or str(e)


def _first_int(s):
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def _rnd(v, nd=1):
    if v is None:
        return None
    return round(v) if nd == 0 else round(v, nd)


def sd_notify(msg):
    """Reports a sign of life to the systemd watchdog (no effect without NOTIFY_SOCKET)."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.connect(addr)
            s.sendall(msg.encode())
        finally:
            s.close()
    except OSError:
        pass


def fan_curve_value(curve, t):
    """Linear interpolation of the curve [[°C, %], ...]; constant outside the points."""
    if t <= curve[0][0]:
        return float(curve[0][1])
    for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
        if t <= t1:
            return p0 + (p1 - p0) * (t - t0) / (t1 - t0)
    return float(curve[-1][1])


def describe_fan(cfg):
    """Description of the fan configuration as a message (for events)."""
    if not cfg:
        return Msg("Fan automatic")
    c = cfg["curve"]
    return Msg("Fan curve {sensor} {tmin}-{tmax} °C, {pmin}-{pmax} %", sensor=cfg["sensor"],
               tmin=c[0][0], tmax=c[-1][0], pmin=min(p for _, p in c), pmax=max(p for _, p in c))


# ---------------------------------------------------------------- Parser

def parse_od(text):
    """Parses pp_od_clk_voltage (OD_SCLK, OD_MCLK, OD_VDDGFX_OFFSET, OD_RANGE).

    The driver pads the file with NUL bytes between the sections,
    so these are removed before parsing."""
    text = text.replace("\x00", "")
    res = {"sclk": {}, "mclk": {}, "range": {}, "vo": None}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        up = line.upper()
        if up.startswith("OD_SCLK"):
            section = "sclk"
        elif up.startswith("OD_MCLK"):
            section = "mclk"
        elif up.startswith("OD_VDDGFX_OFFSET"):
            section = "vo"
        elif up.startswith("OD_RANGE"):
            section = "range"
        elif up.startswith("OD_"):
            section = None
        elif section in ("sclk", "mclk"):
            m = re.match(r"(\d+):\s*(\d+)\s*mhz", line, re.I)
            if m:
                res[section][int(m.group(1))] = int(m.group(2))
        elif section == "vo":
            m = re.match(r"(-?\d+)\s*mv", line, re.I)
            if m:
                res["vo"] = int(m.group(1))
        elif section == "range":
            m = re.match(r"(SCLK|MCLK):\s*(\d+)\s*mhz\s+(\d+)\s*mhz", line, re.I)
            if m:
                res["range"][m.group(1).lower()] = (int(m.group(2)), int(m.group(3)))
    return res


def parse_dmidecode(text):
    """Reads the populated RAM slots from 'dmidecode -t memory'."""
    wanted = ("Size", "Type", "Speed", "Configured Memory Speed",
              "Configured Clock Speed", "Locator")
    mods, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            cur = None
        elif line == "Memory Device":
            cur = {}
            mods.append(cur)
        elif cur is not None and ":" in line:
            k, v = (x.strip() for x in line.split(":", 1))
            if k in wanted:
                cur[k] = v
    out = []
    for m in mods:
        mo = re.match(r"(\d+)\s*(GB|GiB|MB|MiB)", m.get("Size", ""))
        if not mo:
            continue
        n = int(mo.group(1))
        gib = n if mo.group(2) in ("GB", "GiB") else round(n / 1024, 2)
        cfg = m.get("Configured Memory Speed") or m.get("Configured Clock Speed")
        out.append({
            "locator": m.get("Locator"),
            "size_gib": gib,
            "type": m.get("Type"),
            "speed_mts": _first_int(m.get("Speed")),
            "configured_mts": _first_int(cfg),
        })
    return out


# ------------------------------------------------------------------- IO

class RealIO:
    def __init__(self, root="/"):
        self.root = root

    def _p(self, path):
        return path if self.root == "/" else self.root + path

    def read(self, path):
        with open(self._p(path), "r") as f:
            return f.read().replace("\x00", "").strip()

    def write(self, path, value):
        with open(self._p(path), "w") as f:
            f.write(value)

    def exists(self, path):
        return os.path.exists(self._p(path))

    def glob(self, pattern):
        res = glob.glob(self._p(pattern))
        if self.root != "/":
            res = [r[len(self.root):] for r in res]
        return sorted(res)


class Gpu:
    def __init__(self, dev, hwmon):
        self.dev = dev
        self.hwmon = hwmon
        self.od = dev + "/pp_od_clk_voltage"
        self.card = dev.split("/")[-2]

    def hw(self, name):
        return f"{self.hwmon or self.dev + '/hwmon/none'}/{name}"


# ------------------------------------------------------------------- HW

class HW:
    def __init__(self, io, data_dir, readonly=False, probe_dmi=True):
        self.io = io
        self.data_dir = data_dir
        self.readonly = readonly
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self.resume_delay = 3.0
        self.desired = {"gpu": {}, "cpu": {}, "fan": None}
        self._fan_lock = threading.RLock()
        self._fan_wake = threading.Event()
        self._fan = {"cfg": None, "manual": False, "pct": None, "lower_since": None,
                     "override": False, "error": None, "target": None, "temp": None,
                     "retry_at": 0.0, "logged": None}
        self._prev_stat = None
        self._loads = {}
        self._rapl_prev = None
        self._rapl_w = None
        self._susp = self._susp_offset()

        self.cfg = {"autostart_profile": None, "socket_group": "root", "gpu_card": None}
        self.cfg.update(self._load_json("config.json", {}))
        self.history_seconds = max(60, int(self.cfg.get("history_seconds", 3600)))
        self.fan_safety_c = float(self.cfg.get("fan_safety_junction_c", FAN_SAFETY_JUNCTION))
        self.fan_rules = [[float(a), float(b)] for a, b in self.cfg.get("fan_min_rules", FAN_RULES)]
        self.fan_spindown_s = float(self.cfg.get("fan_spindown_s", FAN_SPINDOWN_S))
        self.fan_threshold = float(self.cfg.get("fan_threshold_pct", FAN_THRESHOLD))
        self._hist = collections.deque(maxlen=self.history_seconds)
        self._events = collections.deque(maxlen=200)
        self._hist_lock = threading.Lock()
        self.gpu =self._find_gpu(self.cfg.get("gpu_card"))
        self.cpu_dirs = sorted(
            self.io.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq"),
            key=lambda p: int(re.search(r"cpu(\d+)/", p).group(1)))
        self.rapl = self._find_rapl()
        self.cpu_temp = self._find_cpu_temp()
        self.ram_modules = self._read_dmi() if probe_dmi else []
        self.defaults = self._load_defaults()
        self.profiles = self._load_profiles()

    # ---- Files / sysfs

    @staticmethod
    def _susp_offset():
        return time.clock_gettime(time.CLOCK_BOOTTIME) - time.clock_gettime(time.CLOCK_MONOTONIC)

    def _load_json(self, name, default):
        try:
            with open(os.path.join(self.data_dir, name), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (OSError, ValueError) as e:
            log(f"{name} not readable ({e}), using the default")
            return default

    def _save_json(self, name, obj):
        if self.readonly:
            return
        os.makedirs(self.data_dir, exist_ok=True)
        path = os.path.join(self.data_dir, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)

    def _read(self, path, default=None):
        try:
            return self.io.read(path)
        except (OSError, ValueError):
            return default

    def _num(self, path, div=1.0):
        v = self._read(path)
        if v is None:
            return None
        try:
            return float(v) / div
        except ValueError:
            return None

    def _write(self, path, value):
        if self.readonly:
            raise PermissionError("read-only mode")
        if not write_allowed(path):
            raise PermissionError(f"write access not allowed: {path!r}")
        self.io.write(path, value)

    # ---- Detection

    def _find_gpu(self, forced):
        if forced:
            devs = [f"/sys/class/drm/{forced}/device"]
        else:
            devs = [p + "/device" for p in self.io.glob("/sys/class/drm/card*")
                    if re.fullmatch(r"card\d+", os.path.basename(p))]
        amd = [d for d in devs if (self._read(d + "/vendor") or "").lower() == "0x1002"]
        if not amd:
            return None
        amd.sort(key=lambda d: (not self.io.exists(d + "/pp_od_clk_voltage"), d))
        hw = self.io.glob(amd[0] + "/hwmon/hwmon*")
        return Gpu(amd[0], hw[0] if hw else None)

    def _find_rapl(self):
        for p in self.io.glob("/sys/class/powercap/intel-rapl:[0-9]"):
            if (self._read(p + "/name") or "").startswith("package"):
                return p
        return None

    def _find_cpu_temp(self):
        for h in self.io.glob("/sys/class/hwmon/hwmon*"):
            if self._read(h + "/name") in ("coretemp", "k10temp"):
                for lab in self.io.glob(h + "/temp*_label"):
                    if re.search(r"Package|Tctl|Tdie", self._read(lab) or ""):
                        return lab.replace("_label", "_input")
                return h + "/temp1_input"
        return None

    def _read_dmi(self):
        exe = shutil.which("dmidecode")
        if not exe or os.geteuid() != 0:
            return []
        try:
            out = subprocess.run([exe, "-t", "memory"], capture_output=True,
                                 text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return []
        return parse_dmidecode(out.stdout) if out.returncode == 0 else []

    def _turbo_path(self):
        for p, inverted in (("/sys/devices/system/cpu/intel_pstate/no_turbo", True),
                            ("/sys/devices/system/cpu/cpufreq/boost", False)):
            if self.io.exists(p):
                return p, inverted
        return None

    # ---- Defaults / profiles

    def _load_defaults(self):
        d = self._load_json("defaults.json", None)
        if d:
            return d
        d = self._capture_defaults()
        self._save_json("defaults.json", d)
        return d

    def _capture_defaults(self):
        d = {}
        g = self.gpu
        if g:
            src = "current"
            if not self.readonly and self.io.exists(g.od):
                try:
                    self._write(g.od, "r\n")
                    self._write(g.od, "c\n")
                    src = "od-reset"
                except OSError as e:
                    log(f"OD reset failed while capturing the defaults: {_fmt(e)}")
            od = parse_od(self._read(g.od) or "")
            cap = None
            for n in ("power1_cap_default", "power1_cap_max", "power1_cap"):
                v = self._num(g.hw(n))
                if v:
                    cap = int(v)
                    break
            d["gpu"] = {"sclk_max": od["sclk"].get(1), "mclk_max": od["mclk"].get(1),
                        "power_cap_uw": cap, "source": src}
        if self.cpu_dirs:
            d0 = self.cpu_dirs[0]
            mx = self._num(d0 + "/cpuinfo_max_freq")
            d["cpu"] = {"governor": self._read(d0 + "/scaling_governor"),
                        "epp": self._read(d0 + "/energy_performance_preference"),
                        "max_khz": int(mx) if mx else None, "turbo": True}
        return d

    def _load_profiles(self):
        p = self._load_json("profiles.json", None)
        if p is None:
            p = json.loads(json.dumps(DEFAULT_PROFILES))
            self._save_json("profiles.json", p)
        clean = {}
        for name, s in p.items():
            if (isinstance(s, dict) and set(s) <= {"gpu", "cpu", "fan"}
                    and set(s.get("gpu") or {}) <= set(GPU_KEYS)
                    and set(s.get("cpu") or {}) <= set(CPU_KEYS)):
                try:
                    fan = self._validate_fan(s.get("fan"), check_hw=False)
                except ValueError as e:
                    log(f"Profile '{name}': invalid fan configuration ({e}), ignored")
                    continue
                clean[name] = {"gpu": dict(s.get("gpu") or {}), "cpu": dict(s.get("cpu") or {})}
                if fan:
                    clean[name]["fan"] = fan
            else:
                log(f"Profile '{name}' invalid, ignored")
        return clean

    # ---- Limits / validation

    def limits(self):
        L = {"gpu": {}, "cpu": {}}
        g = self.gpu
        if g:
            d = self.defaults.get("gpu", {})
            od = parse_od(self._read(g.od) or "")
            r = od["range"]
            if d.get("sclk_max") and "sclk" in r:
                lo = max(r["sclk"][0], od["sclk"].get(0, 0))
                L["gpu"]["sclk_max"] = [lo, min(d["sclk_max"], r["sclk"][1])]
            if d.get("mclk_max") and "mclk" in r:
                L["gpu"]["mclk_max"] = [r["mclk"][0], min(d["mclk_max"], r["mclk"][1])]
            cap = d.get("power_cap_uw")
            if cap and self._num(g.hw("power1_cap")) is not None:
                mn = self._num(g.hw("power1_cap_min")) or cap * 0.5
                L["gpu"]["power_cap_w"] = [math.ceil(mn / 1e6), int(cap // 1_000_000)]
        if self.cpu_dirs:
            d = self.defaults.get("cpu", {})
            lo = self._num(self.cpu_dirs[0] + "/cpuinfo_min_freq")
            if lo and d.get("max_khz"):
                L["cpu"]["max_mhz"] = [int(lo // 1000), int(d["max_khz"] // 1000)]
        return L

    def _options(self, name):
        if not self.cpu_dirs:
            return []
        return (self._read(f"{self.cpu_dirs[0]}/{name}") or "").split()

    @staticmethod
    def _as_int(val, key):
        if isinstance(val, bool):
            raise MsgError("{key}: number expected", key=key)
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        if not isinstance(val, int):
            raise MsgError("{key}: integer expected", key=key)
        return val

    def _validate_gpu(self, v):
        if not isinstance(v, dict):
            raise MsgError("gpu: object expected")
        bad = set(v) - set(GPU_KEYS)
        if bad:
            raise MsgError("gpu: unknown values {values}", values=sorted(bad))
        if v and not self.gpu:
            raise MsgError("No AMD GPU found")
        L = self.limits()["gpu"]
        out = {}
        for k, val in v.items():
            n = self._as_int(val, k)
            lim = L.get(k)
            if not lim:
                raise MsgError("{key}: not supported or limits (OD_RANGE) not readable", key=k)
            if not lim[0] <= n <= lim[1]:
                raise MsgError("{key}={value} is outside the allowed range {lo}-{hi}", key=k, value=n, lo=lim[0], hi=lim[1])
            out[k] = n
        return out

    def _validate_cpu(self, v):
        if not isinstance(v, dict):
            raise MsgError("cpu: object expected")
        bad = set(v) - set(CPU_KEYS)
        if bad:
            raise MsgError("cpu: unknown values {values}", values=sorted(bad))
        if v and not self.cpu_dirs:
            raise MsgError("No cpufreq interface found")
        L = self.limits()["cpu"]
        out = {}
        for k, val in v.items():
            if k == "max_mhz":
                n = self._as_int(val, k)
                lim = L.get(k)
                if not lim:
                    raise MsgError("{key}: not supported", key=k)
                if not lim[0] <= n <= lim[1]:
                    raise MsgError("{key}={value} is outside the allowed range {lo}-{hi}", key=k, value=n, lo=lim[0], hi=lim[1])
                out[k] = n
            elif k == "turbo":
                if not isinstance(val, bool):
                    raise MsgError("turbo: true/false expected")
                if not self._turbo_path():
                    raise MsgError("{key}: not supported", key=k)
                out[k] = val
            else:
                opts = self._options("scaling_available_governors" if k == "governor"
                                     else "energy_performance_available_preferences")
                if val not in opts:
                    raise MsgError("{key}='{value}' is invalid, allowed: {allowed}", key=k, value=val,
                                   allowed=opts or Msg("nothing"))
                out[k] = val
        return out

    def fan_supported(self):
        g = self.gpu
        return bool(g and self.io.exists(g.hw("pwm1")) and self.io.exists(g.hw("pwm1_enable")))

    def _validate_fan(self, v, check_hw=True):
        """Normalizes the fan configuration: None (automatic) or {'sensor', 'curve'}."""
        if v is None or v == {}:
            return None
        if not isinstance(v, dict):
            raise MsgError("fan: object expected")
        bad = set(v) - {"mode", "sensor", "curve"}
        if bad:
            raise MsgError("fan: unknown values {values}", values=sorted(bad))
        mode = v.get("mode", "curve")
        if mode not in ("auto", "curve"):
            raise MsgError("fan.mode must be 'auto' or 'curve'")
        if mode == "auto":
            return None
        if check_hw and not self.fan_supported():
            raise MsgError("Fan control not supported (pwm1/pwm1_enable missing)")
        sensor = v.get("sensor", "edge")
        if sensor not in FAN_SENSORS:
            raise MsgError("fan.sensor must be one of {sensors}", sensors=list(FAN_SENSORS))
        raw = v.get("curve")
        if not isinstance(raw, (list, tuple)) or not FAN_POINTS[0] <= len(raw) <= FAN_POINTS[1]:
            raise MsgError("fan.curve: {lo}-{hi} points [°C, %] expected", lo=FAN_POINTS[0], hi=FAN_POINTS[1])
        curve = []
        for pt in raw:
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise MsgError("fan.curve: points must be [°C, %]")
            t = self._as_int(pt[0], Msg("fan.curve temperature"))
            p = self._as_int(pt[1], Msg("fan.curve percent"))
            if not FAN_TEMP_RANGE[0] <= t <= FAN_TEMP_RANGE[1]:
                raise MsgError("fan.curve: temperature {temp} outside {lo}-{hi} °C", temp=t,
                               lo=FAN_TEMP_RANGE[0], hi=FAN_TEMP_RANGE[1])
            if not 0 <= p <= 100:
                raise MsgError("fan.curve: {percent} % outside 0-100", percent=p)
            curve.append([t, p])
        for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
            if t1 <= t0:
                raise MsgError("fan.curve: temperatures must be strictly ascending")
            if p1 < p0:
                raise MsgError("fan.curve: percentages must not decrease with rising temperature")
        for rt, rp in self.fan_rules:
            if fan_curve_value(curve, rt) < rp:
                raise MsgError("fan.curve: at least {percent} % required at {temp} °C "
                               "(protection rule, adjustable in config.json)", percent=f"{rp:g}", temp=f"{rt:g}")
        return {"sensor": sensor, "curve": curve}

    def validate_settings(self, s):
        if not isinstance(s, dict):
            raise MsgError("Settings must be an object")
        if set(s) - {"gpu", "cpu", "fan"}:
            raise MsgError("Unknown sections: {values}", values=sorted(set(s) - {"gpu", "cpu", "fan"}))
        out = {"gpu": self._validate_gpu(s.get("gpu") or {}),
               "cpu": self._validate_cpu(s.get("cpu") or {})}
        fan = self._validate_fan(s.get("fan"))
        if fan:
            out["fan"] = fan
        return out

    # ---- Applying

    def _apply_gpu(self, v, reset):
        errs = []
        g = self.gpu
        if not g:
            return errs
        d = self.defaults.get("gpu", {})
        cmds = (["r"] if reset else [])
        if "sclk_max" in v:
            cmds.append(f"s 1 {v['sclk_max']}")
        if "mclk_max" in v:
            cmds.append(f"m 1 {v['mclk_max']}")
        if cmds:
            cmds.append("c")
            for c in cmds:
                try:
                    self._write(g.od, c + "\n")
                except OSError as e:
                    errs.append(Msg("GPU clock: command '{command}' rejected ({reason})", command=c, reason=_fmt(e)))
                    break
            else:
                od = parse_od(self._read(g.od) or "")
                for key, tbl in (("sclk_max", "sclk"), ("mclk_max", "mclk")):
                    asked = key in v
                    want = v.get(key, d.get(key) if reset else None)
                    got = od[tbl].get(1)
                    if not want or got == want:
                        continue
                    # The driver rounds clocks (e.g. 2679 -> 2674). That is not an error.
                    if got is not None and abs(got - want) <= max(10, want * 0.01):
                        continue
                    if asked or got is None:
                        errs.append(Msg("{key}: expected {expected}, driver reports {actual}", key=key, expected=want, actual=got))
                    else:
                        # only reset, nothing requested: the driver default applies, even if it differs from the
                        # stored value (e.g. after a driver/kernel update)
                        log(f"Note: {key} after reset is {got}, stored default is {want}")
        if "power_cap_w" in v:
            want = v["power_cap_w"] * 1_000_000
        else:
            want = d.get("power_cap_uw") if reset else None
        if want and self._num(g.hw("power1_cap")) is not None:
            p = g.hw("power1_cap")
            try:
                self._write(p, f"{int(want)}\n")
                got = self._num(p)
                if got is not None and abs(int(got) - int(want)) > 1_000_000:   # 1 W tolerance
                    errs.append(Msg("{key}: expected {expected}, driver reports {actual}", key="power_cap_w",
                                    expected=int(want) // 1_000_000, actual=int(got) // 1_000_000))
            except OSError as e:
                errs.append(Msg("Power limit: {reason}", reason=_fmt(e)))
        return errs

    def _apply_cpu(self, v, reset):
        errs, notes = [], []
        if not self.cpu_dirs:
            return errs, notes
        d = self.defaults.get("cpu", {})
        full = dict(v)
        if reset:
            base = {"governor": d.get("governor"), "epp": d.get("epp"),
                    "max_mhz": (d.get("max_khz") or 0) // 1000 or None,
                    "turbo": True if self._turbo_path() else None}
            full = {**{k: x for k, x in base.items() if x is not None}, **v}

        def each(name, value):
            for dd in self.cpu_dirs:
                try:
                    self._write(f"{dd}/{name}", value)
                except OSError as e:
                    return _fmt(e)
            return None

        epp_skipped = False
        if "governor" in full:
            e = each("scaling_governor", full["governor"] + "\n")
            if e:
                errs.append(Msg("Governor: {reason}", reason=e))
        if "epp" in full:
            if self._read(self.cpu_dirs[0] + "/scaling_governor") == "performance":
                epp_skipped = True
                notes.append(Msg("EPP skipped: governor 'performance' ignores EPP"))
            else:
                e = each("energy_performance_preference", full["epp"] + "\n")
                if e:
                    errs.append(Msg("EPP: {reason}", reason=e))
        if "max_mhz" in full:
            e = each("scaling_max_freq", f"{full['max_mhz'] * 1000}\n")
            if e:
                errs.append(Msg("Max clock: {reason}", reason=e))
        if "turbo" in full:
            tp = self._turbo_path()
            if tp:
                path, inverted = tp
                on = full["turbo"]
                try:
                    self._write(path, ("0" if on else "1") if inverted else ("1" if on else "0"))
                except OSError as e:
                    errs.append(Msg("Turbo: {reason}", reason=_fmt(e)))

        snap = self.cpu_settings()
        if "max_mhz" in full and snap.get("max_mhz") is not None \
                and abs(snap["max_mhz"] - full["max_mhz"]) > 100:
            errs.append(Msg("{key}: expected {expected}, system reports {actual}", key="max_mhz",
                            expected=full["max_mhz"], actual=snap["max_mhz"]))
        if "governor" in full and snap.get("governor") != full["governor"] and not errs:
            errs.append(Msg("{key}: expected {expected}, system reports {actual}", key="governor",
                            expected=full["governor"], actual=snap.get("governor")))
        if "epp" in full and not epp_skipped and snap.get("epp") != full["epp"] and not errs:
            errs.append(Msg("{key}: expected {expected}, system reports {actual}", key="epp",
                            expected=full["epp"], actual=snap.get("epp")))
        if "turbo" in full and snap.get("turbo") is not None and snap["turbo"] != full["turbo"]:
            errs.append(Msg("{key}: expected {expected}, system reports {actual}", key="turbo",
                            expected=full["turbo"], actual=snap["turbo"]))
        return errs, notes

    def _apply_all(self, settings, reset):
        errs = self._apply_gpu(settings["gpu"], reset)
        e2, notes = self._apply_cpu(settings["cpu"], reset)
        return errs + e2, notes

    # ---- Fan control

    def _fan_event(self, msg):
        self._event(msg)
        log(str(msg))

    def _fan_release(self, why=None):
        """Returns the fan to the driver's automatic mode (pwm1_enable = 2)."""
        st, g = self._fan, self.gpu
        if g and st["manual"]:
            try:
                self._write(g.hw("pwm1_enable"), "2\n")
            except OSError as e:
                log(f"Fan: returning control to automatic failed ({_fmt(e)})")
        st["manual"] = False
        st["pct"] = None
        st["lower_since"] = None
        if why:
            self._fan_event(why)

    def _fan_write(self, pct):
        g, st = self.gpu, self._fan
        mx = int(self._num(g.hw("pwm1_max")) or 255)
        value = max(0, min(mx, round(pct / 100 * mx)))
        en = g.hw("pwm1_enable")
        if not st["manual"] or self._read(en) != "1":
            self._write(en, "1\n")
            if self._read(en) != "1":
                raise OSError(errno.EIO, "pwm1_enable cannot be set to manual")
            st["manual"] = True
        self._write(g.hw("pwm1"), f"{value}\n")
        # amdgpu computes in whole percent internally and sometimes reads back the current value instead of the
        # one that was set (rounding, start-up ramp). A deviation is therefore not an error, only a log note.
        got = self._num(g.hw("pwm1"))
        if got is not None and abs(got - value) > mx * 0.12 and not st.get("diff_logged"):
            st["diff_logged"] = True
            log(f"Fan: pwm1 set to {value}, driver reports {int(got)} (rounding or ramp-up, ignored)")
        st["pct"] = pct

    def fan_step(self, now=None):
        """One control step: evaluate the curve and write PWM (or restore automatic mode)."""
        now = time.monotonic() if now is None else now
        g = self.gpu
        with self._fan_lock:
            st = self._fan
            cfg = st["cfg"]
            if not g or not self.fan_supported():
                return
            if cfg is None:
                if st["manual"]:
                    self._fan_release()
                st["target"], st["override"], st["temp"] = None, False, None
                return
            if now < st["retry_at"]:
                return
            temp = self._num(g.hw(FAN_SENSORS[cfg["sensor"]]), 1000)
            junc = self._num(g.hw("temp2_input"), 1000)
            st["temp"] = temp
            if temp is None:
                st["target"] = None
                if not (st["error"] and st["error"].tpl == "sensor not readable"):
                    st["error"] = Msg("sensor not readable")
                    self._fan_release(Msg("Fan: {sensor} sensor not readable, automatic", sensor=cfg["sensor"]))
                else:
                    self._fan_release()
                return
            # Safety: at a critical junction temperature always full speed
            if junc is not None:
                if junc >= self.fan_safety_c and not st["override"]:
                    st["override"] = True
                    self._fan_event(Msg("Fan: safety active (junction {temp} °C), 100 %", temp=f"{junc:.0f}"))
                elif st["override"] and junc < self.fan_safety_c - FAN_SAFETY_RELEASE:
                    st["override"] = False
                    self._fan_event(Msg("Fan: safety ended"))
            target = 100 if st["override"] else round(fan_curve_value(cfg["curve"], temp))
            st["target"] = target
            cur = st["pct"]
            if st["manual"] and self._read(g.hw("pwm1_enable")) != "1":
                cur = None   # e.g. after standby or reset by another program
                st["manual"] = False
            write = False
            if cur is None:
                write = True
            elif target > cur:
                st["lower_since"] = None
                write = target - cur >= self.fan_threshold or target == 100
            elif target < cur:
                if st["lower_since"] is None:
                    st["lower_since"] = now
                write = (now - st["lower_since"] >= self.fan_spindown_s
                         and cur - target >= self.fan_threshold)
            else:
                st["lower_since"] = None
            if write:
                try:
                    self._fan_write(target)
                    st["lower_since"] = None
                    st["error"] = None
                    st["logged"] = None
                except OSError as e:
                    reason = _fmt(e)
                    st["error"] = Msg("{reason}", reason=reason)
                    st["retry_at"] = now + 10.0
                    if st["logged"] != reason:
                        st["logged"] = reason
                        self._fan_release(Msg("Fan: {reason}, automatic", reason=reason))
                    else:
                        self._fan_release()

    def _fan_apply(self, cfg):
        """Sets the fan configuration and immediately runs one control step."""
        with self._fan_lock:
            st = self._fan
            st["cfg"] = cfg
            st["error"] = None
            st["retry_at"] = 0.0
            st["override"] = False
            st["pct"] = None
            st["lower_since"] = None
            if cfg is None:
                self.fan_step()
                return []
            if self.readonly:
                return [Msg("Fan: read-only mode")]
            self.fan_step()
            return [Msg("Fan: {error}", error=st["error"])] if st["error"] else []

    def fan_shutdown(self):
        """When the daemon exits: fan back to automatic."""
        with self._fan_lock:
            self._fan["cfg"] = None
            if self._fan["manual"]:
                self._fan_release(Msg("Fan: daemon stopped, automatic"))

    def fan_status(self):
        st, g = self._fan, self.gpu
        cfg = st["cfg"]
        hw_mode = None
        if g:
            en = self._read(g.hw("pwm1_enable"))
            hw_mode = {"1": "manual", "2": "automatic", "0": "off"}.get(en)   # neutral identifiers that the clients translate
        err = st["error"]
        return {"supported": self.fan_supported(),
                "mode": "curve" if cfg else "auto",
                "sensor": cfg["sensor"] if cfg else None,
                "curve": cfg["curve"] if cfg else None,
                "temp_c": _rnd(st["temp"]), "target_pct": st["target"],
                "applied_pct": st["pct"], "override": st["override"],
                "error": str(err) if err else None, "error_msg": err.to_json() if err else None,
                "hw_mode": hw_mode}

    def run_fan(self):
        while not self._stop.is_set():
            try:
                self.fan_step()
            except Exception:
                log(traceback.format_exc())
                try:
                    with self._fan_lock:
                        self._fan_release()
                except Exception:
                    pass
            sd_notify("WATCHDOG=1")
            self._fan_wake.wait(FAN_INTERVAL_S)
            self._fan_wake.clear()

    def _expected(self, s):
        """Complete target state of a profile (values not given = default)."""
        dg, dc = self.defaults.get("gpu", {}), self.defaults.get("cpu", {})
        g, c = s.get("gpu") or {}, s.get("cpu") or {}
        gpu = {"sclk_max": g.get("sclk_max", dg.get("sclk_max")),
               "mclk_max": g.get("mclk_max", dg.get("mclk_max")),
               "power_cap_w": g.get("power_cap_w", (dg.get("power_cap_uw") or 0) // 1_000_000 or None)}
        cpu = {"max_mhz": c.get("max_mhz", (dc.get("max_khz") or 0) // 1000 or None),
               "turbo": c.get("turbo", True), "epp": c.get("epp", dc.get("epp")),
               "governor": c.get("governor", dc.get("governor"))}
        return gpu, cpu

    @staticmethod
    def _gpu_close(key, have, want):
        """Comparison with the driver's rounding tolerance (clock 1 %, at least 10 MHz; power limit 1 W)."""
        if have is None:
            return False
        tol = 1 if key == "power_cap_w" else max(10, want * 0.01)
        return abs(have - want) <= tol

    def _detect_profile(self):
        """Detects the active profile from the actual hardware state (also after a daemon restart)."""
        snap = self.settings_snapshot()
        candidates = [(BUILTIN, {})] + list(self.profiles.items())
        for name, s in candidates:
            eg, ec = self._expected(s)
            ok = all(want is None or self._gpu_close(k, snap["gpu"].get(k), want) for k, want in eg.items())
            for k, want in ec.items():
                have = snap["cpu"].get(k)
                if want is None or have is None:
                    continue
                ok = ok and (abs(have - want) <= 100 if k == "max_mhz" else have == want)
            want_fan = (s.get("fan") or None)
            if ok and want_fan != self._fan["cfg"]:
                ok = False
            if ok:
                return name
        return None

    def _result(self, errs, notes):
        for e in errs:
            log(f"Error: {e}")
        return {"ok": not errs,
                "errors": [str(e) for e in errs], "errors_msg": [e.to_json() for e in errs],
                "notes": [str(n) for n in notes], "notes_msg": [n.to_json() for n in notes],
                "settings": self.settings_snapshot(), "active_profile": self._detect_profile(),
                "fan": self.fan_status()}

    @staticmethod
    def _setting_msg(key, value):
        """One setting as a message for events (each template is its own catalog entry)."""
        return {"sclk_max": lambda: Msg("GPU clock {value}", value=value),
                "mclk_max": lambda: Msg("VRAM clock {value}", value=value),
                "power_cap_w": lambda: Msg("Power limit {value}", value=value),
                "max_mhz": lambda: Msg("CPU clock {value}", value=value),
                "turbo": lambda: Msg("Turbo {value}", value=value),
                "epp": lambda: Msg("EPP {value}", value=value),
                "governor": lambda: Msg("Governor {value}", value=value)}.get(
                    key, lambda: Msg("{key} {value}", key=key, value=value))()

    @staticmethod
    def _with_failure(msg, errs):
        """Event with the first error message appended."""
        return Msg("{event} (error: {error})", event=msg, error=errs[0]) if errs else msg

    def _event(self, msg):
        """Event for the history: plain English text and the message for translating clients."""
        with self._hist_lock:
            self._events.append({"t": round(time.time(), 1), "text": str(msg), "msg": msg.to_json()})

    @staticmethod
    def _profile_msg(name):
        """For humans the built-in profile is called "Default"/"Standard", but internally it is BUILTIN."""
        return Msg("Profile {name}", name=Msg("Default") if name == BUILTIN else name)

    def _describe(self, v):
        return Msg("Manual: {what}", what=[self._setting_msg(k, x) for k, x in v.items()])

    def set_gpu(self, values):
        with self.lock:
            v = self._validate_gpu(values or {})
            errs = self._apply_gpu(v, reset=False)
            if not errs:
                self.desired["gpu"].update(v)
            if v:
                self._event(self._with_failure(self._describe(v), errs))
            return self._result(errs, [])

    def set_cpu(self, values):
        with self.lock:
            v = self._validate_cpu(values or {})
            errs, notes = self._apply_cpu(v, reset=False)
            if not errs:
                self.desired["cpu"].update(v)
            if v:
                self._event(self._with_failure(self._describe(v), errs))
            return self._result(errs, notes)

    def set_fan(self, values):
        with self.lock:
            v = self._validate_fan(values)
            errs = self._fan_apply(v)
            self.desired["fan"] = v   # on error the fan stays on automatic and the daemon tries again
            self._event(self._with_failure(Msg("Manual: {what}", what=describe_fan(v)), errs))
            return self._result(errs, [])

    def reset(self, target="all"):
        if target not in ("gpu", "cpu", "fan", "all"):
            raise MsgError("target must be gpu, cpu, fan or all")
        with self.lock:
            errs, notes = [], []
            if target in ("gpu", "all"):
                errs += self._apply_gpu({}, reset=True)
                self.desired["gpu"] = {}
            if target in ("cpu", "all"):
                e, notes = self._apply_cpu({}, reset=True)
                errs += e
                self.desired["cpu"] = {}
            if target in ("fan", "all"):
                errs += self._fan_apply(None)
                self.desired["fan"] = None
            base = Msg("Reset") if target == "all" else Msg("Reset ({target})", target=target.upper())
            self._event(self._with_failure(base, errs))
            return self._result(errs, notes)

    def apply_profile(self, name):
        with self.lock:
            if name == BUILTIN:
                settings = {"gpu": {}, "cpu": {}}
            elif name in self.profiles:
                settings = self.validate_settings(self.profiles[name])
            else:
                raise MsgError("Profile '{name}' does not exist", name=name)
            errs, notes = self._apply_all(settings, reset=True)
            errs += self._fan_apply(settings.get("fan"))
            settings.setdefault("fan", None)
            self.desired = settings
            self._event(self._with_failure(self._profile_msg(name), errs))
            return self._result(errs, notes)

    def reapply(self):
        with self.lock:
            if not (self.desired["gpu"] or self.desired["cpu"]):
                return None
            errs, _ = self._apply_all(self.desired, reset=True)
            for e in errs:
                log(f"Reapply: {e}")
            return errs

    # ---- Managing profiles

    @staticmethod
    def _check_name(name):
        if not isinstance(name, str) or not re.fullmatch(r"\w[\w .\-]{0,31}", name):
            raise MsgError("Profile name: 1-32 characters (letters, digits, spaces, . _ -)")
        if name.lower() == BUILTIN.lower():
            raise MsgError("'{name}' is reserved", name=BUILTIN)

    def save_profile(self, name, settings):
        self._check_name(name)
        with self.lock:
            self.profiles[name] = self.validate_settings(settings)
            self._save_json("profiles.json", self.profiles)
        return {"ok": True, "profiles": self.profiles}

    def delete_profile(self, name):
        with self.lock:
            if name not in self.profiles:
                raise MsgError("Profile '{name}' does not exist", name=name)
            del self.profiles[name]
            self._save_json("profiles.json", self.profiles)
            if self.cfg.get("autostart_profile") == name:
                self.cfg["autostart_profile"] = None
                self._save_json("config.json", self.cfg)
        return {"ok": True, "profiles": self.profiles}

    def set_autostart(self, name):
        with self.lock:
            if name is not None and name != BUILTIN and name not in self.profiles:
                raise MsgError("Profile '{name}' does not exist", name=name)
            self.cfg["autostart_profile"] = None if name == BUILTIN else name
            self._save_json("config.json", self.cfg)
        return {"ok": True, "autostart_profile": self.cfg["autostart_profile"]}

    # ---- Reading

    def cpu_settings(self):
        if not self.cpu_dirs:
            return {}
        d0 = self.cpu_dirs[0]
        mx = self._num(d0 + "/scaling_max_freq")
        turbo = None
        tp = self._turbo_path()
        if tp:
            v = self._read(tp[0])
            if v in ("0", "1"):
                turbo = (v == "0") if tp[1] else (v == "1")
        return {"max_mhz": round(mx / 1000) if mx else None,
                "governor": self._read(d0 + "/scaling_governor"),
                "epp": self._read(d0 + "/energy_performance_preference"),
                "turbo": turbo}

    def gpu_settings(self):
        g = self.gpu
        if not g:
            return {}
        od = parse_od(self._read(g.od) or "")
        cap = self._num(g.hw("power1_cap"), 1e6)
        return {"sclk_max": od["sclk"].get(1), "mclk_max": od["mclk"].get(1),
                "power_cap_w": round(cap) if cap is not None else None}

    def settings_snapshot(self):
        return {"gpu": self.gpu_settings(), "cpu": self.cpu_settings(), "fan": self._fan["cfg"]}

    def _dpm_current(self, path):
        for line in (self._read(path) or "").splitlines():
            if line.rstrip().endswith("*"):
                m = re.search(r":\s*(\d+)\s*mhz", line, re.I)
                if m:
                    return int(m.group(1))
        return None

    def _status_gpu(self):
        g = self.gpu
        if not g:
            return None
        n = self._num
        sclk = n(g.hw("freq1_input"), 1e6)
        mclk = n(g.hw("freq2_input"), 1e6)
        if sclk is None:
            sclk = self._dpm_current(g.dev + "/pp_dpm_sclk")
        if mclk is None:
            mclk = self._dpm_current(g.dev + "/pp_dpm_mclk")
        power = n(g.hw("power1_average"), 1e6)
        if power is None:
            power = n(g.hw("power1_input"), 1e6)
        pwm, pwm_max = n(g.hw("pwm1")), n(g.hw("pwm1_max")) or 255
        mib = 2 ** 20
        vendor, device = self._read(g.dev + "/vendor"), self._read(g.dev + "/device")
        return {
            "card": g.card,
            "pci_id": f"{vendor[2:]}:{device[2:]}" if vendor and device else None,
            "busy_pct": n(g.dev + "/gpu_busy_percent"),
            "sclk_mhz": _rnd(sclk, 0), "mclk_mhz": _rnd(mclk, 0),
            "temp_edge_c": _rnd(n(g.hw("temp1_input"), 1000)),
            "temp_junction_c": _rnd(n(g.hw("temp2_input"), 1000)),
            "temp_mem_c": _rnd(n(g.hw("temp3_input"), 1000)),
            "power_w": _rnd(power), "power_cap_w": _rnd(n(g.hw("power1_cap"), 1e6), 0),
            "fan_rpm": _rnd(n(g.hw("fan1_input")), 0),
            "fan_pct": round(pwm / pwm_max * 100) if pwm is not None else None,
            "fan_mode": self._read(g.hw("pwm1_enable")),
            "volt_mv": _rnd(n(g.hw("in0_input")), 0),
            "vram_used_mib": _rnd(n(g.dev + "/mem_info_vram_used", mib), 0),
            "vram_total_mib": _rnd(n(g.dev + "/mem_info_vram_total", mib), 0),
            "gtt_used_mib": _rnd(n(g.dev + "/mem_info_gtt_used", mib), 0),
            "perf_level": self._read(g.dev + "/power_dpm_force_performance_level"),
        }

    def _status_cpu(self):
        freqs = [self._num(d + "/scaling_cur_freq", 1000) for d in self.cpu_dirs]
        freqs = [round(f) for f in freqs if f is not None]
        cores = sorted((int(k[3:]), v) for k, v in self._loads.items() if k != "cpu")
        return {
            "load_pct": self._loads.get("cpu"),
            "load_cores_pct": [v for _, v in cores],
            "freq_mhz": freqs,
            "freq_avg_mhz": round(sum(freqs) / len(freqs)) if freqs else None,
            "freq_max_mhz": max(freqs) if freqs else None,
            "temp_c": _rnd(self._num(self.cpu_temp, 1000)) if self.cpu_temp else None,
            "power_w": self._rapl_w,
            "driver": self._read(self.cpu_dirs[0] + "/scaling_driver") if self.cpu_dirs else None,
        }

    def _status_ram(self):
        mi = {}
        for line in (self._read("/proc/meminfo") or "").splitlines():
            k, _, v = line.partition(":")
            mi[k] = _first_int(v)

        def mib(key):
            return round(mi[key] / 1024) if mi.get(key) is not None else None

        total, avail = mib("MemTotal"), mib("MemAvailable")
        st, sf = mib("SwapTotal"), mib("SwapFree")
        return {"total_mib": total, "available_mib": avail,
                "used_mib": total - avail if total is not None and avail is not None else None,
                "cached_mib": mib("Cached"), "buffers_mib": mib("Buffers"),
                "swap_total_mib": st,
                "swap_used_mib": st - sf if st is not None and sf is not None else None}

    def status(self):
        return {"ts": time.time(), "active_profile": self._detect_profile(),
                "gpu": self._status_gpu(), "cpu": self._status_cpu(),
                "ram": self._status_ram(), "settings": self.settings_snapshot(),
                "fan": self.fan_status()}

    def info(self):
        model = None
        for line in (self._read("/proc/cpuinfo") or "").splitlines():
            if line.startswith("model name"):
                model = line.partition(":")[2].strip()
                break
        g = self.gpu
        return {
            "version": VERSION,
            "gpu": None if not g else {
                "card": g.card, "has_od": self.io.exists(g.od),
                "mclk_effective_factor": 2, "defaults": self.defaults.get("gpu")},
            "cpu": {"model": model, "threads": len(self.cpu_dirs),
                    "driver": self._read(self.cpu_dirs[0] + "/scaling_driver") if self.cpu_dirs else None,
                    "governors": self._options("scaling_available_governors"),
                    "epp_options": self._options("energy_performance_available_preferences"),
                    "turbo_supported": self._turbo_path() is not None,
                    "defaults": self.defaults.get("cpu")},
            "ram": {"modules": self.ram_modules},
            "fan": {"supported": self.fan_supported(), "sensors": list(FAN_SENSORS),
                    "points": list(FAN_POINTS), "temp_range": list(FAN_TEMP_RANGE),
                    "rules": self.fan_rules, "safety_junction_c": self.fan_safety_c,
                    "spindown_s": self.fan_spindown_s, "threshold_pct": self.fan_threshold,
                    "example_curve": FAN_EXAMPLE},
            "limits": self.limits(),
            "profiles": self.profiles, "builtin_profile": BUILTIN,
            "autostart_profile": self.cfg.get("autostart_profile"),
            "active_profile": self._detect_profile(),
        }

    # ---- Background sampling

    def _read_stat(self):
        out = {}
        for line in (self._read("/proc/stat") or "").splitlines():
            if not line.startswith("cpu"):
                continue
            parts = line.split()
            try:
                vals = [int(x) for x in parts[1:9]]
                out[parts[0]] = (vals[3] + vals[4], sum(vals))
            except (ValueError, IndexError):
                continue
        return out

    def _tick(self):
        cur = self._read_stat()
        if self._prev_stat:
            loads = {}
            for k, (idle, tot) in cur.items():
                pi, pt = self._prev_stat.get(k, (idle, tot))
                dt = tot - pt
                loads[k] = round(100.0 * (1 - (idle - pi) / dt), 1) if dt > 0 else 0.0
            self._loads = loads
        self._prev_stat = cur

        if self.rapl:
            e = self._num(self.rapl + "/energy_uj")
            now = time.monotonic()
            if e is not None:
                if self._rapl_prev:
                    de = e - self._rapl_prev[0]
                    if de < 0:
                        de += self._num(self.rapl + "/max_energy_range_uj") or 0
                    dt = now - self._rapl_prev[1]
                    if dt > 0 and de >= 0:
                        self._rapl_w = round(de / dt / 1e6, 1)
                self._rapl_prev = (e, now)

        sample = self._sample()
        with self._hist_lock:
            self._hist.append(sample)

        off = self._susp_offset()
        resumed = off - self._susp > 3.0
        self._susp = off
        if resumed:
            log("Resume detected, applying the settings again")
            self._event(Msg("Woke up from standby"))
            time.sleep(self.resume_delay)
            self.reapply()

    def _sample(self):
        g = self._status_gpu() or {}
        c = self._status_cpu()
        return {"t": round(time.time(), 1),
                "g_edge": g.get("temp_edge_c"), "g_junc": g.get("temp_junction_c"),
                "g_mem": g.get("temp_mem_c"), "g_pow": g.get("power_w"),
                "g_busy": g.get("busy_pct"), "g_clk": g.get("sclk_mhz"), "g_fan": g.get("fan_rpm"),
                "g_fanp": g.get("fan_pct"),
                "c_temp": c["temp_c"], "c_pow": c["power_w"], "c_load": c["load_pct"],
                "c_clk": c["freq_avg_mhz"]}

    def history(self, since=None):
        if since is not None and (isinstance(since, bool) or not isinstance(since, (int, float))):
            raise MsgError("since: number (Unix time) expected")
        with self._hist_lock:
            samples, events = list(self._hist), list(self._events)
        if since is not None:
            samples = [s for s in samples if s["t"] > since]
            # Events inclusive: the client asks with the timestamp of the last sample, and timestamps are rounded to 0.1 s.
            # An event after that sample can have the same value and would be lost with ">".
            # The client recognizes duplicates by the (time, text) pair.
            events = [e for e in events if e["t"] >= since]
        return {"ok": True, "now": round(time.time(), 1), "interval_s": 1,
                "retention_s": self.history_seconds, "samples": samples, "events": events}

    def run_sampler(self):
        while not self._stop.wait(1.0):
            try:
                self._tick()
            except Exception:
                log(traceback.format_exc())

    # ---- Commands

    def handle(self, req):
        cmd = req.get("cmd")
        if cmd == "ping":
            return {"ok": True, "version": VERSION}
        if cmd == "status":
            return {"ok": True, **self.status()}
        if cmd == "info":
            return {"ok": True, **self.info()}
        if cmd == "history":
            return self.history(req.get("since"))
        if cmd == "set_gpu":
            return self.set_gpu(req.get("values"))
        if cmd == "set_cpu":
            return self.set_cpu(req.get("values"))
        if cmd == "set_fan":
            return self.set_fan(req.get("values"))
        if cmd == "reset":
            return self.reset(req.get("target", "all"))
        if cmd == "apply_profile":
            return self.apply_profile(req.get("name"))
        if cmd == "save_profile":
            return self.save_profile(req.get("name"), req.get("settings"))
        if cmd == "delete_profile":
            return self.delete_profile(req.get("name"))
        if cmd == "set_autostart":
            return self.set_autostart(req.get("profile"))
        raise MsgError("Unknown command: {command}", command=repr(cmd))


# --------------------------------------------------------------- Server

def error_response(e):
    """Response to a failed command: plain English text; where there is a message, also its template."""
    msg = e.msg if isinstance(e, MsgError) else None if isinstance(e, ValueError) else Msg("Internal error: {error}", error=str(e))
    resp = {"ok": False, "error": str(msg) if msg else str(e)}
    if msg:
        resp["error_msg"] = msg.to_json()
    return resp


class Handler(socketserver.StreamRequestHandler):
    timeout = 60

    def handle(self):
        hw = self.server.hw
        while True:
            try:
                line = self.rfile.readline(65536)
            except OSError:
                return
            if not line:
                return
            try:
                req = json.loads(line)
                if not isinstance(req, dict):
                    raise MsgError("JSON object expected")
                resp = hw.handle(req)
            except ValueError as e:   # also MsgError and invalid JSON
                resp = error_response(e)
            except Exception as e:
                log(traceback.format_exc())
                resp = error_response(e)
            try:
                self.wfile.write((json.dumps(resp, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
            except OSError:
                return


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def make_server(hw, path, group="root"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.unlink(path)
    old = os.umask(0o117)
    try:
        srv = Server(path, Handler)
    finally:
        os.umask(old)
    try:
        os.chown(path, os.geteuid(), grp.getgrnam(group).gr_gid)
    except (KeyError, PermissionError) as e:
        log(f"Could not set the socket group '{group}': {e}")
    srv.hw = hw
    return srv


def main():
    ap = argparse.ArgumentParser(description="hwpaneld: root daemon that monitors and limits GPU and CPU clocks.")
    ap.add_argument("--probe", action="store_true",
                    help="only read the hardware and print it as JSON (no writing, no daemon)")
    args = ap.parse_args()

    if args.probe:
        hw = HW(RealIO(), DATA_DIR, readonly=True)
        hw._tick()
        time.sleep(1)
        hw._tick()
        print(json.dumps({"info": hw.info(), "status": hw.status()}, indent=2, ensure_ascii=False))
        return

    if os.geteuid() != 0:
        sys.exit("hwpaneld must run as root (for testing: --probe).")

    hw = HW(RealIO(), DATA_DIR)
    hw._event(Msg("Daemon started"))
    hw._tick()
    auto = hw.cfg.get("autostart_profile")
    if auto:
        try:
            r = hw.apply_profile(auto)
            log(f"Autostart profile '{auto}': {'ok' if r['ok'] else r['errors']}")
        except ValueError as e:
            log(f"Autostart profile '{auto}' not applicable: {e}")

    srv = make_server(hw, SOCKET_PATH, hw.cfg.get("socket_group", "root"))
    threading.Thread(target=hw.run_sampler, daemon=True).start()
    threading.Thread(target=hw.run_fan, daemon=True).start()

    def stop(*_):
        threading.Thread(target=srv.shutdown, daemon=True).start()

    import signal
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log(f"hwpaneld {VERSION} ready on {SOCKET_PATH}")
    try:
        srv.serve_forever()
    finally:
        hw._stop.set()
        hw.fan_shutdown()
        srv.server_close()
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main()
