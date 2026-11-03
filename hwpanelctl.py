#!/usr/bin/env python3
"""hwpanelctl: Kommandozeilen-Client für hwpaneld."""

import argparse
import json
import os
import socket
import sys
import time

import hwpanel_i18n as i18n

SOCKET_PATH = os.environ.get("HWPANEL_SOCKET", "/run/hwpanel/hwpanel.sock")
tr = i18n.tr


def setup_language(argv):
    """Legt die Sprache fest: --lang, dann HWPANEL_LANG, dann die Systemsprache.
    Geschieht vor dem Aufbau des Parsers, damit auch die Hilfetexte übersetzt sind."""
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang")
    known, _ = pre.parse_known_args(argv)
    i18n.set_language(i18n.resolve(known.lang or os.environ.get("HWPANEL_LANG")))


def call(req):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(30)
    try:
        s.connect(SOCKET_PATH)
    except FileNotFoundError:
        s.close()
        sys.exit(tr("Daemon is not running (socket missing). Check: systemctl status hwpanel"))
    except PermissionError:
        s.close()
        sys.exit(tr("No access to the socket. Run with sudo or check the group in "
                    "/var/lib/hwpanel/config.json (socket_group)."))
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    if not buf:
        sys.exit(tr("No response from the daemon."))
    return json.loads(buf)


def v(x, fmt="{}", unit=""):
    return "-" if x is None else fmt.format(x) + unit


def parse_curve(text):
    """'30:40,50:60,80:90' -> [[30, 40], [50, 60], [80, 90]]"""
    try:
        return [[int(a), int(b)] for a, b in (pt.split(":") for pt in text.split(","))]
    except ValueError:
        sys.exit(tr("Give the curve as TEMP:PERCENT,TEMP:PERCENT,..., e.g. 30:40,50:60,80:90"))


LABEL_WIDTH = 15   # Breite der Beschriftungsspalte in der Statusausgabe


def print_settings(st):
    g, c = st.get("gpu") or {}, st.get("cpu") or {}
    turbo = {True: tr("on"), False: tr("off"), None: "-"}[c.get("turbo")]
    pad = " " * LABEL_WIDTH
    print(tr("Settings").ljust(LABEL_WIDTH)
          + tr("GPU max {sclk} MHz, VRAM max {mclk} MHz (LACT: {lact}), power {power} W",
               sclk=v(g.get("sclk_max")), mclk=v(g.get("mclk_max")),
               lact=v(g.get("mclk_max") and g["mclk_max"] * 2), power=v(g.get("power_cap_w"))))
    print(pad + tr("CPU max {mhz} MHz, turbo {turbo}, EPP {epp}, governor {governor}",
                   mhz=v(c.get("max_mhz")), turbo=turbo, epp=v(c.get("epp")), governor=v(c.get("governor"))))
    fan = st.get("fan")
    print(pad + (tr("Fan curve ({sensor}): {points}", sensor=fan["sensor"],
                    points=", ".join(f"{t} °C:{p} %" for t, p in fan["curve"]))
                 if fan else tr("Fan automatic (driver)")))


def print_status(s):
    g, c, r = s.get("gpu"), s["cpu"], s["ram"]
    if g:
        print(tr("GPU   Load {busy}   Clock {sclk} / {mclk} MHz (GPU / VRAM)   Power {power} / {cap} W",
                 busy=v(g["busy_pct"], "{:.0f}", " %"), sclk=v(g["sclk_mhz"]), mclk=v(g["mclk_mhz"]),
                 power=v(g["power_w"]), cap=v(g["power_cap_w"])))
        print(tr("      Temp Edge {edge} / Junction {junction} / VRAM {mem} °C   "
                 "Fan {rpm} RPM ({pct} %)   VRAM {used} / {total} MiB",
                 edge=v(g["temp_edge_c"]), junction=v(g["temp_junction_c"]), mem=v(g["temp_mem_c"]),
                 rpm=v(g["fan_rpm"]), pct=v(g["fan_pct"]),
                 used=v(g["vram_used_mib"]), total=v(g["vram_total_mib"])))
    else:
        print(tr("GPU   no AMD GPU found"))
    print(tr("CPU   Load {load}   Clock Ø {avg} / max {max} MHz   Temp {temp} °C   Power {power} W",
             load=v(c["load_pct"], "{:.0f}", " %"), avg=v(c["freq_avg_mhz"]), max=v(c["freq_max_mhz"]),
             temp=v(c["temp_c"]), power=v(c["power_w"])))
    print(tr("RAM   {used} / {total} MiB used   Swap {swap_used} / {swap_total} MiB",
             used=v(r["used_mib"]), total=v(r["total_mib"]),
             swap_used=v(r["swap_used_mib"]), swap_total=v(r["swap_total_mib"])))
    print_settings(s["settings"])
    f = s.get("fan") or {}
    if f.get("mode") == "curve":
        line = tr("Fan control  sensor {sensor} {temp} °C -> target {target} %, set {applied} %, mode {mode}",
                  sensor=f["sensor"], temp=v(f["temp_c"]), target=v(f["target_pct"]),
                  applied=v(f["applied_pct"]), mode=v(f["hw_mode"]))
        if f.get("override"):
            line += "   " + tr("SAFETY ACTIVE (100 %)")
        if f.get("error"):
            line += "   " + tr("Error: {error}", error=f["error"])
        print(line)
    print(tr("Profile").ljust(LABEL_WIDTH) + (s.get("active_profile") or tr("manual / unknown")))


def print_info(i):
    L = i["limits"]
    g = L.get("gpu", {})
    if i["gpu"]:
        rng = lambda k, f=1: f"{g[k][0] * f}-{g[k][1] * f}" if k in g else "-"
        print(tr("GPU   {card}   Limits: GPU clock {sclk} MHz, VRAM clock {mclk} MHz (LACT: {lact}), power {power} W",
                 card=i["gpu"]["card"], sclk=rng("sclk_max"), mclk=rng("mclk_max"),
                 lact=rng("mclk_max", 2), power=rng("power_cap_w")))
    c = i["cpu"]
    cl = L.get("cpu", {}).get("max_mhz")
    if cl:
        print(tr("CPU   {model} ({threads} threads, {driver})   max clock {lo}-{hi} MHz",
                 model=c["model"], threads=c["threads"], driver=c["driver"], lo=cl[0], hi=cl[1]))
    else:
        print(tr("CPU   {model}", model=c["model"]))
    print(tr("      Governors: {governors}   EPP: {epp}   Turbo switchable: {switchable}",
             governors=", ".join(c["governors"]), epp=", ".join(c["epp_options"]),
             switchable=tr("yes") if c["turbo_supported"] else tr("no")))
    mods = i["ram"]["modules"]
    if mods:
        print("RAM   " + ", ".join(
            tr("{size} GiB {type} @ {configured} MT/s (module: {speed})", size=f"{m['size_gib']:g}", type=m["type"],
               configured=v(m["configured_mts"]), speed=v(m["speed_mts"])) for m in mods))
    fi = i.get("fan") or {}
    if fi.get("supported"):
        print(tr("Fan sensors: {sensors}   {lo}-{hi} points   "
                 "Protection: 100 % from {safety} °C junction, minimum values {rules}",
                 sensors=", ".join(fi["sensors"]), lo=fi["points"][0], hi=fi["points"][1],
                 safety=f"{fi['safety_junction_c']:g}", rules=", ".join(f"{t:g} °C: {p:g} %" for t, p in fi["rules"])))
    else:
        print(tr("Fan not controllable (pwm1/pwm1_enable missing)"))
    print(tr("Profiles: {builtin} (built in), {names}   Autostart: {autostart}",
             builtin=i["builtin_profile"], names=", ".join(i["profiles"]), autostart=i["autostart_profile"] or "-"))
    for name, s in i["profiles"].items():
        print(f"  {name}: {json.dumps(s, ensure_ascii=False)}")


def show_result(r):
    if "error" in r:
        print(tr("Error:"), r["error"])
        return 1
    for n in r.get("notes", []):
        print(tr("Note:"), n)
    for e in r.get("errors", []):
        print(tr("Error:"), e)
    if r.get("errors"):
        return 1
    if "settings" in r:
        print("OK")
        print_settings(r["settings"])
    else:
        print("OK")
    return 0


def gpu_flags(p):
    p.add_argument("--sclk", type=int, metavar="MHZ", help=tr("GPU maximum clock"))
    p.add_argument("--mclk", type=int, metavar="MHZ", help=tr("VRAM maximum clock (sysfs value, LACT shows double)"))
    p.add_argument("--power", type=int, metavar="W", help=tr("power limit"))


def cpu_flags(p):
    p.add_argument("--max-mhz", type=int, metavar="MHZ", help=tr("CPU maximum clock"))
    p.add_argument("--turbo", choices=["on", "off"])
    p.add_argument("--epp", metavar="NAME")
    p.add_argument("--governor", metavar="NAME")


def fan_flags(p, prefix=""):
    p.add_argument(f"--{prefix}fan-curve", metavar=tr("CURVE"),
                   help=tr("fan curve TEMP:PERCENT,... e.g. 30:40,50:60,80:90 (if omitted: automatic)"))
    p.add_argument(f"--{prefix}fan-sensor", choices=["edge", "junction", "mem"], default="edge",
                   help=tr("temperature sensor of the curve (default: edge)"))


def gpu_values(a):
    return {k: x for k, x in (("sclk_max", a.sclk), ("mclk_max", a.mclk),
                              ("power_cap_w", a.power)) if x is not None}


def cpu_values(a):
    d = {k: x for k, x in (("max_mhz", a.max_mhz), ("epp", a.epp),
                           ("governor", a.governor)) if x is not None}
    if a.turbo:
        d["turbo"] = a.turbo == "on"
    return d


def main():
    setup_language(sys.argv[1:])
    ap = argparse.ArgumentParser(prog="hwpanelctl", description=tr("Control hwpaneld"))
    ap.add_argument("--json", action="store_true", help=tr("raw output as JSON"))
    ap.add_argument("--lang", metavar="CODE",
                    help=tr("Language of the output, a code such as de or en (default: system language)"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help=tr("show measurements"))
    p.add_argument("-w", "--watch", action="store_true", help=tr("refresh every second"))
    sub.add_parser("info", help=tr("show limits, defaults and profiles"))
    p = sub.add_parser("gpu", help=tr("set GPU values"))
    gpu_flags(p)
    p = sub.add_parser("cpu", help=tr("set CPU values"))
    cpu_flags(p)
    p = sub.add_parser("fan", help=tr("fan: 'auto' or a custom curve"))
    p.add_argument("mode", choices=["auto", "curve"])
    p.add_argument("curve", nargs="?", metavar=tr("CURVE"), help=tr("TEMP:PERCENT,... e.g. 30:40,50:60,80:90"))
    p.add_argument("--sensor", choices=["edge", "junction", "mem"], default="edge")
    p = sub.add_parser("reset", help=tr("reset to default"))
    p.add_argument("target", nargs="?", default="all", choices=["gpu", "cpu", "fan", "all"])
    sub.add_parser("profiles", help=tr("list profiles"))
    p = sub.add_parser("apply", help=tr("apply a profile (Standard = reset everything)"))
    p.add_argument("name")
    p = sub.add_parser("save", help=tr("save or overwrite a profile"))
    p.add_argument("name")
    gpu_flags(p)
    cpu_flags(p)
    fan_flags(p)
    p = sub.add_parser("delete", help=tr("delete a profile"))
    p.add_argument("name")
    p = sub.add_parser("autostart", help=tr("apply a profile when the daemon starts"))
    p.add_argument("name", nargs="?", help=tr("profile name or 'none'; without argument: show"))
    a = ap.parse_args()

    if a.cmd == "status":
        while True:
            r = call({"cmd": "status"})
            if a.json:
                print(json.dumps(r, indent=2, ensure_ascii=False))
            else:
                if a.watch:
                    print("\033[H\033[J", end="")
                print_status(r)
            if not a.watch:
                return 0
            time.sleep(1)

    if a.cmd in ("info", "profiles"):
        r = call({"cmd": "info"})
        if a.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
        elif a.cmd == "info":
            print_info(r)
        else:
            for n, s in r["profiles"].items():
                print(f"{n}: {json.dumps(s, ensure_ascii=False)}")
        return 0

    if a.cmd == "gpu":
        req = {"cmd": "set_gpu", "values": gpu_values(a)}
    elif a.cmd == "cpu":
        req = {"cmd": "set_cpu", "values": cpu_values(a)}
    elif a.cmd == "fan":
        if a.mode == "auto":
            req = {"cmd": "set_fan", "values": {"mode": "auto"}}
        elif not a.curve:
            sys.exit(tr("'fan curve' needs a curve, e.g. 30:40,50:60,80:90"))
        else:
            req = {"cmd": "set_fan", "values": {"sensor": a.sensor, "curve": parse_curve(a.curve)}}
    elif a.cmd == "reset":
        req = {"cmd": "reset", "target": a.target}
    elif a.cmd == "apply":
        req = {"cmd": "apply_profile", "name": a.name}
    elif a.cmd == "save":
        settings = {"gpu": gpu_values(a), "cpu": cpu_values(a)}
        if a.fan_curve:
            settings["fan"] = {"sensor": a.fan_sensor, "curve": parse_curve(a.fan_curve)}
        req = {"cmd": "save_profile", "name": a.name, "settings": settings}
    elif a.cmd == "delete":
        req = {"cmd": "delete_profile", "name": a.name}
    else:
        if a.name is None:
            print("Autostart:", call({"cmd": "info"})["autostart_profile"] or "-")
            return 0
        req = {"cmd": "set_autostart", "profile": None if a.name.lower() == "none" else a.name}

    r = call(req)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0 if r.get("ok") else 1
    return show_result(r)


if __name__ == "__main__":
    sys.exit(main())
