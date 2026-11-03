// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

// Shared form for "Manual" and the profile editor.
// Upper limits are the driver defaults (no overclocking).
Item {
    id: f
    property real sclk: 0
    property real mclk: 0
    property real power: 0
    property real maxMhz: 0
    property bool turbo: true
    property string epp: ""
    property string gov: ""

    readonly property var lim: Fmt.get(backend.info, ["limits"], ({}))
    readonly property var cpuInfo: Fmt.get(backend.info, ["cpu"], ({}))
    readonly property string defEpp: Fmt.get(cpuInfo, ["defaults", "epp"], "")
    readonly property string defGov: Fmt.get(cpuInfo, ["defaults", "governor"], "")

    function limit(group, key) { return Fmt.get(lim, [group, key], null) }
    function lo(group, key) { var l = limit(group, key); return l ? l[0] : 0 }
    function hi(group, key) { var l = limit(group, key); return l ? l[1] : 0 }

    function loadDefaults() {
        sclk = hi("gpu", "sclk_max")
        mclk = hi("gpu", "mclk_max")
        power = hi("gpu", "power_cap_w")
        maxMhz = hi("cpu", "max_mhz")
        turbo = true
        epp = defEpp
        gov = defGov
    }
    function loadProfile(p) {
        loadDefaults()
        var g = (p && p.gpu) || {}, c = (p && p.cpu) || {}
        if (g.sclk_max !== undefined) sclk = g.sclk_max
        if (g.mclk_max !== undefined) mclk = g.mclk_max
        if (g.power_cap_w !== undefined) power = g.power_cap_w
        if (c.max_mhz !== undefined) maxMhz = c.max_mhz
        if (c.turbo !== undefined) turbo = c.turbo
        if (c.epp !== undefined) epp = c.epp
        if (c.governor !== undefined) gov = c.governor
    }
    function loadCurrent() {
        loadDefaults()
        var s = Fmt.get(backend.status, ["settings"], ({}))
        var g = s.gpu || {}, c = s.cpu || {}
        if (g.sclk_max) sclk = g.sclk_max
        if (g.mclk_max) mclk = g.mclk_max
        if (g.power_cap_w) power = g.power_cap_w
        if (c.max_mhz) maxMhz = c.max_mhz
        if (c.turbo !== undefined && c.turbo !== null) turbo = c.turbo
        if (c.epp) epp = c.epp
        if (c.governor) gov = c.governor
    }
    // all = true: all values; otherwise only deviations from the default (for profiles)
    function gpuValues(all) {
        var d = {}
        if (limit("gpu", "sclk_max") && (all || sclk < hi("gpu", "sclk_max"))) d.sclk_max = Math.round(sclk)
        if (limit("gpu", "mclk_max") && (all || mclk < hi("gpu", "mclk_max"))) d.mclk_max = Math.round(mclk)
        if (limit("gpu", "power_cap_w") && (all || power < hi("gpu", "power_cap_w"))) d.power_cap_w = Math.round(power)
        return d
    }
    function cpuValues(all) {
        var d = {}
        if (limit("cpu", "max_mhz") && (all || maxMhz < hi("cpu", "max_mhz"))) d.max_mhz = Math.round(maxMhz)
        if (Fmt.get(cpuInfo, ["turbo_supported"], false) && (all || !turbo)) d.turbo = turbo
        if (epp && (all || epp !== defEpp)) d.epp = epp
        if (gov && (all || gov !== defGov)) d.governor = gov
        return d
    }

    implicitHeight: row.implicitHeight

    RowLayout {
        id: row
        anchors.left: parent.left; anchors.right: parent.right
        spacing: 40

        ColumnLayout {
            Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop
            spacing: 14
            Text { text: "GPU"; color: Theme.redSoft; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 2 }
            GlowSlider {
                Layout.fillWidth: true
                title: qsTr("GPU max clock"); unit: "MHz"; stepSize: 10
                hint: qsTr("<b>Upper limit for the GPU clock.</b> Lower means less performance, power draw and heat. Above the default is not possible, hwpanel never overclocks.")
                from: f.lo("gpu", "sclk_max"); to: f.hi("gpu", "sclk_max"); value: f.sclk
                enabled: f.limit("gpu", "sclk_max") !== null
                note: f.sclk >= f.hi("gpu", "sclk_max") ? qsTr("Default") : ""
                onMoved: (v) => f.sclk = v
            }
            GlowSlider {
                Layout.fillWidth: true
                title: qsTr("VRAM max clock"); unit: "MHz"; stepSize: 1
                hint: qsTr("<b>Upper limit for the graphics memory clock.</b> Lower saves power but can slow games down. LACT shows double the value.")
                from: f.lo("gpu", "mclk_max"); to: f.hi("gpu", "mclk_max"); value: f.mclk
                enabled: f.limit("gpu", "mclk_max") !== null
                note: f.mclk >= f.hi("gpu", "mclk_max") ? qsTr("Default") : qsTr("LACT: %1").arg(Math.round(f.mclk * 2))
                onMoved: (v) => f.mclk = v
            }
            GlowSlider {
                Layout.fillWidth: true
                title: qsTr("Power limit"); unit: "W"; stepSize: 1
                hint: qsTr("<b>Maximum power draw of the graphics card in watts.</b> Less means quieter, cooler and slightly slower.")
                from: f.lo("gpu", "power_cap_w"); to: f.hi("gpu", "power_cap_w"); value: f.power
                enabled: f.limit("gpu", "power_cap_w") !== null
                note: f.power >= f.hi("gpu", "power_cap_w") ? qsTr("Default") : ""
                onMoved: (v) => f.power = v
            }
        }

        ColumnLayout {
            Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop
            spacing: 14
            Text { text: "CPU"; color: Theme.redSoft; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 2 }
            GlowSlider {
                Layout.fillWidth: true
                title: qsTr("CPU max clock"); unit: "MHz"; stepSize: 100
                hint: qsTr("<b>Upper limit for the CPU clock.</b> Lower means less performance, power draw and heat. Above the default is not possible.")
                from: f.lo("cpu", "max_mhz"); to: f.hi("cpu", "max_mhz"); value: f.maxMhz
                enabled: f.limit("cpu", "max_mhz") !== null
                note: f.maxMhz >= f.hi("cpu", "max_mhz") ? qsTr("Default") : ""
                onMoved: (v) => f.maxMhz = v
            }
            RowLayout {
                Layout.fillWidth: true
                enabled: Fmt.get(f.cpuInfo, ["turbo_supported"], false)
                opacity: enabled ? 1 : 0.4
                HelpLabel {
                    text: qsTr("Turbo Boost")
                    hint: qsTr("<b>Turbo Boost.</b> Allows the CPU to briefly clock above its base clock. Off: quieter and cooler, but noticeably less performance under load.")
                }
                Item { Layout.fillWidth: true }
                GlowSwitch { checked: f.turbo; onToggled: (v) => f.turbo = v }
            }
            HelpLabel {
                text: qsTr("Energy Performance Preference")
                hint: qsTr("<b>Energy preference (EPP).</b> Decides whether the CPU favors performance or efficiency. Only works with the governor “powersave”. Hover over the options for details.")
            }
            ChoiceRow {
                Layout.fillWidth: true
                kind: "epp"
                options: Fmt.get(f.cpuInfo, ["epp_options"], [])
                current: f.epp
                onPicked: (v) => f.epp = v
            }
            HelpLabel {
                text: qsTr("Governor")
                hint: qsTr("<b>Clock strategy.</b> Decides how the CPU chooses its clock. On Intel and AMD “powersave” with a suitable energy preference is usually right, with other drivers “schedutil”. Hover over the options for details.")
            }
            ChoiceRow {
                Layout.fillWidth: true
                kind: "governor"
                driver: Fmt.get(f.cpuInfo, ["driver"], "")
                options: Fmt.get(f.cpuInfo, ["governors"], [])
                current: f.gov
                onPicked: (v) => f.gov = v
            }
        }
    }
}
