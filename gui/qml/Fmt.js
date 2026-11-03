// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

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

// Display name of a profile: the built-in one is called "Standard" internally (that is how the daemon is addressed), the display is "Default"/"Standard".
function profileLabel(name, isBuiltin) {
    return isBuiltin ? qsTr("Default") : name
}

function describeGpu(p) {
    var g = (p && p.gpu) || {}, parts = []
    if (g.sclk_max !== undefined) parts.push(qsTr("GPU max %1 MHz").arg(g.sclk_max))
    if (g.mclk_max !== undefined) parts.push(qsTr("VRAM max %1 MHz").arg(g.mclk_max))
    if (g.power_cap_w !== undefined) parts.push(qsTr("Power %1 W").arg(g.power_cap_w))
    return parts.length ? parts.join(" · ") : qsTr("GPU: default")
}

function describeCpu(p) {
    var c = (p && p.cpu) || {}, parts = []
    if (c.max_mhz !== undefined) parts.push(qsTr("CPU max %1 MHz").arg(c.max_mhz))
    if (c.turbo !== undefined) parts.push(c.turbo ? qsTr("Turbo on") : qsTr("Turbo off"))
    if (c.epp !== undefined) parts.push(qsTr("EPP %1").arg(c.epp))
    if (c.governor !== undefined) parts.push(qsTr("Governor %1").arg(c.governor))
    return parts.length ? parts.join(" · ") : qsTr("CPU: default")
}

// Explanations for choice values on hover (kind: "epp", "governor" or "sensor").
// Empty text if the value is unknown: then the UI shows nothing.
// Every text appears as qsTr() in the call, so that it is re-evaluated on a language change.
function eppHint(value) {
    switch (value) {
    case "default": return qsTr("<b>CPU default.</b> The value set by the manufacturer, usually similar to “balance_performance”.")
    case "performance": return qsTr("<b>Highest performance.</b> The CPU clocks up immediately and stays up longer. More power draw, heat and fan noise.")
    case "balance_performance": return qsTr("<b>Balanced, leaning towards performance.</b> A good choice for everyday use on a desktop PC.")
    case "balance_power": return qsTr("<b>Balanced, leaning towards efficiency.</b> The CPU clocks up more cautiously and uses less power.")
    case "power": return qsTr("<b>Maximum efficiency.</b> The CPU stays at a low clock whenever possible. Quieter and cooler, but less responsive.")
    }
    return ""
}

function governorHint(value) {
    switch (value) {
    case "performance": return qsTr("<b>Permanently high clock.</b> The CPU always runs at a high clock, even when idle. More power draw and heat. The energy preference (EPP) is ignored.")
    case "powersave": return qsTr("<b>Clock on demand.</b> On Intel and AMD the normal mode: low when idle, high under load. Despite the name not slower: the energy preference (EPP) decides how quickly the CPU clocks up.")
    case "schedutil": return qsTr("<b>Clock follows the load.</b> The kernel adjusts the clock directly to the utilization. A good compromise between performance and power draw.")
    case "ondemand": return qsTr("<b>Clock on demand.</b> High under load, low when idle. Reacts a little slower than “schedutil”.")
    case "conservative": return qsTr("<b>Gentle clock changes.</b> Like “ondemand”, but the clock rises and falls in small steps. Saves a little power.")
    case "userspace": return qsTr("<b>Clock set manually.</b> A program sets the clock itself. Not meant for normal use.")
    }
    return ""
}

function sensorHint(value) {
    switch (value) {
    case "edge": return qsTr("<b>Edge.</b> Temperature at the edge of the GPU chip, the value most programs show as the GPU temperature. Rises more slowly than junction.")
    case "junction": return qsTr("<b>Junction (hotspot).</b> The hottest spot in the GPU chip. Reacts fastest and is higher than edge. Good if the fan should react early.")
    case "mem": return qsTr("<b>VRAM.</b> Temperature of the graphics memory chips. Useful if the memory is the hottest part in your system.")
    }
    return ""
}

// With these drivers "powersave" regulates the clock on demand; with others it holds the lowest clock.
var PSTATE_DRIVERS = ["intel_pstate", "amd-pstate", "amd-pstate-epp"]

function optionHint(kind, value, driver) {
    if (kind === "governor" && value === "powersave" && driver && PSTATE_DRIVERS.indexOf(driver) < 0)
        return qsTr("<b>Lowest clock.</b> With this driver “powersave” keeps the CPU permanently at the lowest clock. Very frugal, but slow.")
    if (kind === "epp") return eppHint(value)
    if (kind === "governor") return governorHint(value)
    if (kind === "sensor") return sensorHint(value)
    return ""
}

function windowLabel(s) {
    if (s < 3600) return qsTr("%1 min").arg(s / 60)
    return qsTr("%1 h").arg(s / 3600)
}

function sensorLabel(s) {
    return ({ edge: "Edge", junction: "Junction", mem: "VRAM" })[s] || s
}

// Linear interpolation of a fan curve [[°C, %], ...], constant outside
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

// Check the daemon's protection rules in advance; empty string = fine
function ruleError(pts, rules) {
    if (!pts || pts.length < 2) return qsTr("At least 2 points required")
    for (var i = 0; i < (rules || []).length; i++) {
        var r = rules[i]
        if (curveValue(pts, r[0]) < r[1] - 1e-9)
            return qsTr("Protection rule: at least %2 % at %1 °C").arg(r[0]).arg(r[1])
    }
    return ""
}

function describeFan(p) {
    var f = p && p.fan
    if (!f || !f.curve || !f.curve.length) return qsTr("Fan: automatic")
    var c = f.curve, last = c[c.length - 1]
    return qsTr("Fan: %1–%2 % (%3–%4 °C, %5)").arg(c[0][1]).arg(last[1]).arg(c[0][0]).arg(last[0]).arg(sensorLabel(f.sensor))
}
