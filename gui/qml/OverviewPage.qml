import QtQuick
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

Item {
    id: page
    readonly property var g: Fmt.get(backend.status, ["gpu"], ({}))
    readonly property var c: Fmt.get(backend.status, ["cpu"], ({}))
    readonly property var r: Fmt.get(backend.status, ["ram"], ({}))
    readonly property var st: Fmt.get(backend.status, ["settings"], ({}))
    readonly property var mods: Fmt.get(backend.info, ["ram", "modules"], [])

    function cpuLimitText() {
        var cur = Fmt.get(st, ["cpu", "max_mhz"], null)
        var def = Fmt.get(backend.info, ["limits", "cpu", "max_mhz"], null)
        return (cur && def && cur < def[1]) ? qsTr("Max %1 MHz · ").arg(cur) : ""
    }
    function fanText() {
        var f = Fmt.get(backend.status, ["fan"], ({}))
        if (f.override) return qsTr("Safety")
        if (f.error) return qsTr("Error")
        return f.mode === "curve" ? qsTr("Curve") : qsTr("Auto")
    }
    function fanError() {
        var e = Fmt.get(backend.status, ["fan", "error"], "")
        return e ? qsTr("Fan: %1").arg(e) : ""
    }
    function ramText() {
        if (!mods.length) return ""
        var m = mods[0]
        return mods.length + "× " + m.size_gib + " GiB " + m.type + " @ " + (m.configured_mts || m.speed_mts) + " MT/s"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 22

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Text { text: qsTr("Overview"); color: "white"; font.pixelSize: Theme.fsBig; font.weight: Font.DemiBold }
            Item { Layout.fillWidth: true }
            Text { text: qsTr("Profile"); color: Theme.textFaint; font.pixelSize: Theme.fsTiny; font.letterSpacing: 1.5; font.capitalization: Font.AllUppercase; Layout.rightMargin: 6 }
            Repeater {
                model: backend.profileNames
                GlowButton {
                    text: Fmt.profileLabel(modelData, index === 0)
                    active: modelData === backend.activeProfile
                    onClicked: backend.applyProfile(modelData)
                }
            }
        }

        RowLayout {
            // Height follows the tallest card content so that nothing sticks out over the edge (font metrics differ per system)
            readonly property real fit: Math.max(292, 2 * Theme.pad + Math.max(gpuCol.implicitHeight, cpuCol.implicitHeight, ramCol.implicitHeight))
            Layout.fillWidth: true
            Layout.minimumHeight: fit
            Layout.preferredHeight: fit
            Layout.maximumHeight: fit
            spacing: 24

            // GPU
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100
                ColumnLayout {
                    id: gpuCol
                    anchors.fill: parent
                    spacing: 12
                    RowLayout {
                        Text { text: "GPU"; color: Theme.redSoft; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 2 }
                        Item { Layout.fillWidth: true }
                        Text { text: "AMD · " + (page.g.card || "–"); color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 14; rowSpacing: 10
                        StatTile { Layout.fillWidth: true; label: qsTr("Temperature"); value: Fmt.num(page.g.temp_edge_c); unit: "°C"
                            sub: qsTr("Junction %1 · Mem %2").arg(Fmt.num(page.g.temp_junction_c)).arg(Fmt.num(page.g.temp_mem_c)) }
                        StatTile { Layout.fillWidth: true; label: qsTr("Power"); value: Fmt.num(page.g.power_w, 0); unit: "W"
                            sub: qsTr("Limit %1 W").arg(Fmt.num(page.g.power_cap_w)) }
                        StatTile { Layout.fillWidth: true; label: qsTr("Clock"); value: Fmt.num(page.g.sclk_mhz); unit: "MHz"
                            sub: qsTr("VRAM %1 MHz").arg(Fmt.num(page.g.mclk_mhz)) }
                        StatTile { Layout.fillWidth: true; label: qsTr("Fan"); value: Fmt.num(page.g.fan_rpm); unit: "RPM"
                            sub: Fmt.num(page.g.fan_pct) + " % · " + page.fanText()
                            warn: page.fanError() !== ""
                            tip: page.fanError() }
                    }
                    Item { Layout.fillHeight: true }
                    BarMeter { Layout.fillWidth: true; label: qsTr("Utilization"); valueText: Fmt.num(page.g.busy_pct) + " %"; fraction: (page.g.busy_pct || 0) / 100 }
                    BarMeter { Layout.fillWidth: true; label: "VRAM"
                        valueText: Fmt.gib(page.g.vram_used_mib) + " / " + Fmt.gib(page.g.vram_total_mib) + " GiB"
                        fraction: (page.g.vram_used_mib || 0) / (page.g.vram_total_mib || 1) }
                }
            }

            // CPU
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100
                ColumnLayout {
                    id: cpuCol
                    anchors.fill: parent
                    spacing: 12
                    RowLayout {
                        Text { text: "CPU"; color: Theme.redSoft; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 2 }
                        Item { Layout.fillWidth: true }
                        Text { text: Fmt.get(backend.info, ["cpu", "threads"], "–") + " Threads"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 14; rowSpacing: 10
                        StatTile { Layout.fillWidth: true; label: qsTr("Temperature"); value: Fmt.num(page.c.temp_c); unit: "°C" }
                        StatTile { Layout.fillWidth: true; label: qsTr("Power"); value: Fmt.num(page.c.power_w, 0); unit: "W" }
                        StatTile { Layout.fillWidth: true; label: qsTr("Clock Ø"); value: Fmt.num(page.c.freq_avg_mhz); unit: "MHz"
                            sub: qsTr("max %1 MHz").arg(Fmt.num(page.c.freq_max_mhz)) }
                        StatTile { Layout.fillWidth: true; label: qsTr("Load"); value: Fmt.num(page.c.load_pct); unit: "%" }
                    }
                    Item { Layout.fillHeight: true }
                    BarMeter { Layout.fillWidth: true; label: qsTr("Utilization"); valueText: Fmt.num(page.c.load_pct) + " %"; fraction: (page.c.load_pct || 0) / 100 }
                    Text {
                        Layout.fillWidth: true
                        text: page.cpuLimitText() + (Fmt.get(page.st, ["cpu", "turbo"], true) ? qsTr("Turbo on · EPP %1") : qsTr("Turbo off · EPP %1"))
                              .arg(Fmt.get(page.st, ["cpu", "epp"], "–"))
                        color: Theme.textFaint; font.pixelSize: Theme.fsSmall; elide: Text.ElideRight
                    }
                }
            }

            // RAM
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100
                ColumnLayout {
                    id: ramCol
                    anchors.fill: parent
                    spacing: 12
                    RowLayout {
                        Text { text: "RAM"; color: Theme.redSoft; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 2 }
                        Item { Layout.fillWidth: true }
                        Text { text: Fmt.gib(page.r.total_mib) + " GiB"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 14; rowSpacing: 10
                        StatTile { Layout.fillWidth: true; label: qsTr("Used"); value: Fmt.gib(page.r.used_mib); unit: "GiB" }
                        StatTile { Layout.fillWidth: true; label: qsTr("Available"); value: Fmt.gib(page.r.available_mib); unit: "GiB" }
                    }
                    Item { Layout.fillHeight: true }
                    BarMeter { Layout.fillWidth: true; label: qsTr("Memory")
                        valueText: Fmt.gib(page.r.used_mib) + " / " + Fmt.gib(page.r.total_mib) + " GiB"
                        fraction: (page.r.used_mib || 0) / (page.r.total_mib || 1) }
                    BarMeter { Layout.fillWidth: true; label: "Swap"
                        valueText: Fmt.gib(page.r.swap_used_mib) + " / " + Fmt.gib(page.r.swap_total_mib) + " GiB"
                        fraction: (page.r.swap_used_mib || 0) / (page.r.swap_total_mib || 1) }
                    Text { Layout.fillWidth: true; text: page.ramText(); color: Theme.textFaint; font.pixelSize: Theme.fsSmall; elide: Text.ElideRight }
                }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 170
            RowLayout {
                anchors.fill: parent
                spacing: 30
                LineChart {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100
                    compact: true; legendRows: 2
                    unit: "°C"; minSpan: 20; fillKey: "g_junc"
                    hist: backend.history; windowSeconds: backend.historyWindow
                    series: [
                        { key: "g_junc", label: "GPU Junction", color: Theme.seriesGpuA },
                        { key: "g_edge", label: "GPU Edge", color: Theme.seriesGpuB },
                        { key: "c_temp", label: "CPU", color: Theme.seriesCpu }
                    ]
                }
                LineChart {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100
                    compact: true; legendRows: 2
                    unit: "W"; zeroBased: true; minSpan: 50; fillKey: "g_pow"
                    hist: backend.history; windowSeconds: backend.historyWindow
                    series: [
                        { key: "g_pow", label: "GPU", color: Theme.seriesGpuA },
                        { key: "c_pow", label: "CPU", color: Theme.seriesCpu }
                    ]
                }
            }
        }
    }
}
