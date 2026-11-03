.pragma library

function get(o, path, d) {
    var cur = o
    for (var i = 0; i < path.length; i++) {
        if (cur === null || cur === undefined) return d
        cur = cur[path[i]]
    }
    return (cur === undefined || cur === null) ? d : cur
}

function num(v, nd) {
    if (v === null || v === undefined || isNaN(v)) return "–"
    return Number(v).toFixed(nd === undefined ? 0 : nd)
}

function gib(mib) {
    if (mib === null || mib === undefined || isNaN(mib)) return "–"
    return (mib / 1024).toFixed(1)
}

function describeGpu(p) {
    var g = (p && p.gpu) || {}, parts = []
    if (g.sclk_max !== undefined) parts.push("GPU max " + g.sclk_max + " MHz")
    if (g.mclk_max !== undefined) parts.push("VRAM max " + g.mclk_max + " MHz")
    if (g.power_cap_w !== undefined) parts.push("Power " + g.power_cap_w + " W")
    return parts.length ? parts.join(" · ") : "GPU: Standard"
}

function describeCpu(p) {
    var c = (p && p.cpu) || {}, parts = []
    if (c.max_mhz !== undefined) parts.push("CPU max " + c.max_mhz + " MHz")
    if (c.turbo !== undefined) parts.push("Turbo " + (c.turbo ? "an" : "aus"))
    if (c.epp !== undefined) parts.push("EPP " + c.epp)
    if (c.governor !== undefined) parts.push("Governor " + c.governor)
    return parts.length ? parts.join(" · ") : "CPU: Standard"
}

// Erklärungen für Auswahlwerte beim Darüberfahren (kind: "epp", "governor" oder "sensor").
// Leerer Text, wenn der Wert unbekannt ist: Dann zeigt die Oberfläche nichts an.
var OPTION_HINTS = {
    epp: {
        "default": "<b>Vorgabe der CPU.</b> Der Wert, den der Hersteller eingestellt hat, meist ähnlich wie „balance_performance“.",
        "performance": "<b>Höchste Leistung.</b> Die CPU taktet sofort hoch und bleibt länger oben. Mehr Verbrauch, Wärme und Lüftergeräusch.",
        "balance_performance": "<b>Ausgewogen, Richtung Leistung.</b> Eine gute Wahl für den Alltag am Desktop-PC.",
        "balance_power": "<b>Ausgewogen, Richtung Sparsamkeit.</b> Die CPU taktet vorsichtiger hoch und braucht weniger Strom.",
        "power": "<b>Maximal sparsam.</b> Die CPU bleibt möglichst niedrig getaktet. Leiser und kühler, dafür träger."
    },
    governor: {
        "performance": "<b>Dauerhaft hoher Takt.</b> Die CPU läuft immer mit hohem Takt, auch im Leerlauf. Mehr Verbrauch und Wärme. Die Energie-Vorliebe (EPP) wird dabei ignoriert.",
        "powersave": "<b>Takt nach Bedarf.</b> Bei Intel und AMD der normale Modus: niedrig im Leerlauf, hoch unter Last. Trotz des Namens nicht langsamer, die Energie-Vorliebe (EPP) bestimmt, wie zügig die CPU hochtaktet.",
        "schedutil": "<b>Takt folgt der Last.</b> Der Kernel passt den Takt direkt an die Auslastung an. Ein guter Kompromiss aus Leistung und Verbrauch.",
        "ondemand": "<b>Takt nach Bedarf.</b> Hoch bei Last, niedrig im Leerlauf. Reagiert etwas langsamer als „schedutil“.",
        "conservative": "<b>Sanfte Taktwechsel.</b> Wie „ondemand“, aber der Takt steigt und sinkt in kleinen Schritten. Spart etwas Strom.",
        "userspace": "<b>Takt von Hand.</b> Ein Programm legt den Takt selbst fest. Für die normale Nutzung nicht gedacht."
    },
    sensor: {
        "edge": "<b>Edge (Kante).</b> Temperatur am Rand des GPU-Chips, der Wert, den die meisten Programme als GPU-Temperatur anzeigen. Steigt langsamer als Junction.",
        "junction": "<b>Junction (Hotspot).</b> Die heißeste Stelle im GPU-Chip. Reagiert am schnellsten und liegt höher als Edge. Gut, wenn der Lüfter früh reagieren soll.",
        "mem": "<b>VRAM.</b> Temperatur der Grafikspeicher-Chips. Sinnvoll, wenn bei dir der Speicher der heißeste Teil ist."
    }
}

// Bei diesen Treibern regelt "powersave" den Takt nach Bedarf; bei anderen hält er den niedrigsten Takt.
var PSTATE_DRIVERS = ["intel_pstate", "amd-pstate", "amd-pstate-epp"]

function optionHint(kind, value, driver) {
    if (kind === "governor" && value === "powersave" && driver && PSTATE_DRIVERS.indexOf(driver) < 0)
        return "<b>Niedrigster Takt.</b> Bei diesem Treiber hält „powersave“ die CPU dauerhaft auf dem niedrigsten Takt. Sehr sparsam, aber langsam."
    var group = OPTION_HINTS[kind]
    return (group && group[value]) || ""
}

function windowLabel(s) {
    if (s < 3600) return (s / 60) + " Min"
    return (s / 3600) + " Std"
}

function sensorLabel(s) {
    return ({ edge: "Edge", junction: "Junction", mem: "VRAM" })[s] || s
}

// Lineare Interpolation einer Lüfterkurve [[°C, %], ...], außerhalb konstant
function curveValue(pts, t) {
    if (!pts || !pts.length || t === null || t === undefined || isNaN(t)) return NaN
    if (t <= pts[0][0]) return pts[0][1]
    for (var i = 1; i < pts.length; i++) {
        if (t <= pts[i][0]) {
            var a = pts[i - 1], b = pts[i]
            return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])
        }
    }
    return pts[pts.length - 1][1]
}

// Schutzregeln des Daemons vorab prüfen; leerer String = in Ordnung
function ruleError(pts, rules) {
    if (!pts || pts.length < 2) return "Mindestens 2 Punkte nötig"
    for (var i = 0; i < (rules || []).length; i++) {
        var r = rules[i]
        if (curveValue(pts, r[0]) < r[1] - 1e-9)
            return "Schutzregel: bei " + r[0] + " °C mindestens " + r[1] + " %"
    }
    return ""
}

function describeFan(p) {
    var f = p && p.fan
    if (!f || !f.curve || !f.curve.length) return "Lüfter: Automatik"
    var c = f.curve, last = c[c.length - 1]
    return "Lüfter: " + c[0][1] + "–" + last[1] + " % (" + c[0][0] + "–" + last[0] + " °C, " + sensorLabel(f.sensor) + ")"
}
