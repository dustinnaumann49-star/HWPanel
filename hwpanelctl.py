#!/usr/bin/env python3
"""hwpanelctl: Kommandozeilen-Client für hwpaneld."""

import argparse
import json
import os
import socket
import sys
import time

SOCKET_PATH = os.environ.get("HWPANEL_SOCKET", "/run/hwpanel/hwpanel.sock")


def call(req):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(30)
    try:
        s.connect(SOCKET_PATH)
    except FileNotFoundError:
        sys.exit("Daemon läuft nicht (Socket fehlt). Prüfen: systemctl status hwpanel")
    except PermissionError:
        sys.exit("Kein Zugriff auf den Socket. Mit sudo ausführen oder Gruppe in "
                 "/var/lib/hwpanel/config.json (socket_group) prüfen.")
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    if not buf:
        sys.exit("Keine Antwort vom Daemon.")
    return json.loads(buf)


def v(x, fmt="{}", unit=""):
    return "-" if x is None else fmt.format(x) + unit


def parse_curve(text):
    """'30:40,50:60,80:90' -> [[30, 40], [50, 60], [80, 90]]"""
    try:
        return [[int(a), int(b)] for a, b in (pt.split(":") for pt in text.split(","))]
    except ValueError:
        sys.exit("Kurve im Format TEMP:PROZENT,TEMP:PROZENT,... angeben, z. B. 30:40,50:60,80:90")


def fan_text(f):
    if not f:
        return "-"
    if f.get("mode") != "curve":
        return "Automatik (Treiber)"
    pts = ", ".join(f"{t} °C:{p} %" for t, p in f["curve"])
    extra = " [Sicherung aktiv]" if f.get("override") else ""
    return f"Kurve ({f['sensor']}): {pts}{extra}"


def print_settings(st):
    g, c = st.get("gpu") or {}, st.get("cpu") or {}
    turbo = {True: "an", False: "aus", None: "-"}[c.get("turbo")]
    print(f"Einstellungen  GPU max {v(g.get('sclk_max'))} MHz, VRAM max {v(g.get('mclk_max'))} MHz "
          f"(LACT: {v(g.get('mclk_max') and g['mclk_max'] * 2)}), Power {v(g.get('power_cap_w'))} W")
    print(f"               CPU max {v(c.get('max_mhz'))} MHz, Turbo {turbo}, "
          f"EPP {v(c.get('epp'))}, Governor {v(c.get('governor'))}")
    fan = st.get("fan")
    print("               Lüfter " + ("Kurve (" + fan["sensor"] + "): " + ", ".join(f"{t} °C:{p} %" for t, p in fan["curve"])
                                   if fan else "Automatik (Treiber)"))


def print_status(s):
    g, c, r = s.get("gpu"), s["cpu"], s["ram"]
    if g:
        print(f"GPU   Auslastung {v(g['busy_pct'], '{:.0f}', ' %')}   "
              f"Takt {v(g['sclk_mhz'])} / {v(g['mclk_mhz'])} MHz (GPU / VRAM)   "
              f"Leistung {v(g['power_w'])} / {v(g['power_cap_w'])} W")
        print(f"      Temp Edge {v(g['temp_edge_c'])} / Junction {v(g['temp_junction_c'])} / "
              f"VRAM {v(g['temp_mem_c'])} °C   Lüfter {v(g['fan_rpm'])} RPM ({v(g['fan_pct'])} %)   "
              f"VRAM {v(g['vram_used_mib'])} / {v(g['vram_total_mib'])} MiB")
    else:
        print("GPU   keine AMD-GPU gefunden")
    print(f"CPU   Last {v(c['load_pct'], '{:.0f}', ' %')}   Takt Ø {v(c['freq_avg_mhz'])} / "
          f"max {v(c['freq_max_mhz'])} MHz   Temp {v(c['temp_c'])} °C   Leistung {v(c['power_w'])} W")
    print(f"RAM   {v(r['used_mib'])} / {v(r['total_mib'])} MiB belegt   "
          f"Swap {v(r['swap_used_mib'])} / {v(r['swap_total_mib'])} MiB")
    print_settings(s["settings"])
    f = s.get("fan") or {}
    if f.get("mode") == "curve":
        print(f"Lüfter-Regelung  Sensor {f['sensor']} {v(f['temp_c'])} °C -> Ziel {v(f['target_pct'])} %, "
              f"gesetzt {v(f['applied_pct'])} %, Modus {v(f['hw_mode'])}"
              + ("   SICHERUNG AKTIV (100 %)" if f.get("override") else "")
              + (f"   Fehler: {f['error']}" if f.get("error") else ""))
    print(f"Profil         {s.get('active_profile') or 'manuell / unbekannt'}")


def print_info(i):
    L = i["limits"]
    g = L.get("gpu", {})
    if i["gpu"]:
        rng = lambda k, f=1: f"{g[k][0] * f}-{g[k][1] * f}" if k in g else "-"
        print(f"GPU   {i['gpu']['card']}   Grenzen: GPU-Takt {rng('sclk_max')} MHz, "
              f"VRAM-Takt {rng('mclk_max')} MHz (LACT: {rng('mclk_max', 2)}), "
              f"Power {rng('power_cap_w')} W")
    c = i["cpu"]
    cl = L.get("cpu", {}).get("max_mhz")
    print(f"CPU   {c['model']} ({c['threads']} Threads, {c['driver']})   "
          f"Max-Takt {cl[0]}-{cl[1]} MHz" if cl else f"CPU   {c['model']}")
    print(f"      Governor: {', '.join(c['governors'])}   EPP: {', '.join(c['epp_options'])}   "
          f"Turbo schaltbar: {'ja' if c['turbo_supported'] else 'nein'}")
    mods = i["ram"]["modules"]
    if mods:
        print("RAM   " + ", ".join(f"{m['size_gib']:g} GiB {m['type']} @ {v(m['configured_mts'])} MT/s "
                                   f"(Modul: {v(m['speed_mts'])})" for m in mods))
    fi = i.get("fan") or {}
    if fi.get("supported"):
        print(f"Lüfter Sensoren: {', '.join(fi['sensors'])}   {fi['points'][0]}-{fi['points'][1]} Punkte   "
              f"Schutz: 100 % ab {fi['safety_junction_c']:g} °C Junction, Mindestwerte "
              + ", ".join(f"{t:g} °C: {p:g} %" for t, p in fi["rules"]))
    else:
        print("Lüfter nicht steuerbar (pwm1/pwm1_enable fehlen)")
    print(f"Profile: {i['builtin_profile']} (eingebaut), " + ", ".join(i["profiles"]) +
          f"   Autostart: {i['autostart_profile'] or '-'}")
    for name, s in i["profiles"].items():
        print(f"  {name}: {json.dumps(s, ensure_ascii=False)}")


def show_result(r):
    if "error" in r:
        print("Fehler:", r["error"])
        return 1
    for n in r.get("notes", []):
        print("Hinweis:", n)
    for e in r.get("errors", []):
        print("Fehler:", e)
    if r.get("errors"):
        return 1
    if "settings" in r:
        print("OK")
        print_settings(r["settings"])
    else:
        print("OK")
    return 0


def gpu_flags(p):
    p.add_argument("--sclk", type=int, metavar="MHZ", help="GPU-Maximaltakt")
    p.add_argument("--mclk", type=int, metavar="MHZ", help="VRAM-Maximaltakt (sysfs-Wert, LACT zeigt das Doppelte)")
    p.add_argument("--power", type=int, metavar="W", help="Power-Limit")


def cpu_flags(p):
    p.add_argument("--max-mhz", type=int, metavar="MHZ", help="CPU-Maximaltakt")
    p.add_argument("--turbo", choices=["on", "off"])
    p.add_argument("--epp", metavar="NAME")
    p.add_argument("--governor", metavar="NAME")


def fan_flags(p, prefix=""):
    p.add_argument(f"--{prefix}fan-curve", metavar="KURVE",
                   help="Lüfterkurve TEMP:PROZENT,... z. B. 30:40,50:60,80:90 (ohne Angabe: Automatik)")
    p.add_argument(f"--{prefix}fan-sensor", choices=["edge", "junction", "mem"], default="edge",
                   help="Temperatursensor der Kurve (Standard: edge)")


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
    ap = argparse.ArgumentParser(prog="hwpanelctl", description="Steuerung für hwpaneld")
    ap.add_argument("--json", action="store_true", help="Rohausgabe als JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="Messwerte anzeigen")
    p.add_argument("-w", "--watch", action="store_true", help="jede Sekunde aktualisieren")
    sub.add_parser("info", help="Grenzen, Standardwerte und Profile anzeigen")
    p = sub.add_parser("gpu", help="GPU-Werte setzen")
    gpu_flags(p)
    p = sub.add_parser("cpu", help="CPU-Werte setzen")
    cpu_flags(p)
    p = sub.add_parser("fan", help="Lüfter: 'auto' oder eigene Kurve")
    p.add_argument("mode", choices=["auto", "curve"])
    p.add_argument("curve", nargs="?", metavar="KURVE", help="TEMP:PROZENT,... z. B. 30:40,50:60,80:90")
    p.add_argument("--sensor", choices=["edge", "junction", "mem"], default="edge")
    p = sub.add_parser("reset", help="auf Standard zurücksetzen")
    p.add_argument("target", nargs="?", default="all", choices=["gpu", "cpu", "fan", "all"])
    sub.add_parser("profiles", help="Profile auflisten")
    p = sub.add_parser("apply", help="Profil anwenden (Standard = alles zurücksetzen)")
    p.add_argument("name")
    p = sub.add_parser("save", help="Profil speichern oder überschreiben")
    p.add_argument("name")
    gpu_flags(p)
    cpu_flags(p)
    fan_flags(p)
    p = sub.add_parser("delete", help="Profil löschen")
    p.add_argument("name")
    p = sub.add_parser("autostart", help="Profil beim Start des Daemons anwenden")
    p.add_argument("name", nargs="?", help="Profilname oder 'none'; ohne Angabe: anzeigen")
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
            sys.exit("Für 'fan curve' wird eine Kurve benötigt, z. B. 30:40,50:60,80:90")
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
