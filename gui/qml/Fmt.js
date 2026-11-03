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
