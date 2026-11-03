import QtQuick
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

Item {
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 22

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            ColumnLayout {
                spacing: 2
                Text { text: "Verlauf"; color: "white"; font.pixelSize: Theme.fsBig; font.weight: Font.DemiBold }
                Text { text: "Gestrichelte Linien markieren Profilwechsel. Mit der Maus über das Diagramm fahren für Werte."
                       color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
            }
            Item { Layout.fillWidth: true }
            Repeater {
                model: [60, 300, 900, 3600]
                GlowButton {
                    compact: true
                    text: Fmt.windowLabel(modelData)
                    active: backend.historyWindow === modelData
                    onClicked: backend.setHistoryWindow(modelData)
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: 2
            columnSpacing: 24
            rowSpacing: 24

            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100; Layout.preferredHeight: 100
                LineChart {
                    anchors.fill: parent
                    unit: "°C"; minSpan: 20; fillKey: "g_junc"; legendRows: 2
                    hist: backend.history; windowSeconds: backend.historyWindow
                    series: [
                        { key: "g_junc", label: "GPU Junction", color: Theme.seriesGpuA },
                        { key: "g_edge", label: "GPU Edge", color: Theme.seriesGpuB },
                        { key: "g_mem", label: "VRAM", color: Theme.seriesGpuC },
                        { key: "c_temp", label: "CPU", color: Theme.seriesCpu }
                    ]
                }
            }
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100; Layout.preferredHeight: 100
                LineChart {
                    anchors.fill: parent
                    unit: "W"; zeroBased: true; minSpan: 50; fillKey: "g_pow"; legendRows: 2
                    hist: backend.history; windowSeconds: backend.historyWindow
                    series: [
                        { key: "g_pow", label: "GPU", color: Theme.seriesGpuA },
                        { key: "c_pow", label: "CPU", color: Theme.seriesCpu }
                    ]
                }
            }
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100; Layout.preferredHeight: 100
                LineChart {
                    anchors.fill: parent
                    unit: "%"; yMinFixed: 0; yMaxFixed: 100; fillKey: "g_busy"; legendRows: 2
                    hist: backend.history; windowSeconds: backend.historyWindow
                    series: [
                        { key: "g_busy", label: "GPU-Last", color: Theme.seriesGpuA },
                        { key: "c_load", label: "CPU-Last", color: Theme.seriesCpu },
                        { key: "g_fanp", label: "Lüfter", color: Theme.seriesFan }
                    ]
                }
            }
            Card {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 100; Layout.preferredHeight: 100
                LineChart {
                    anchors.fill: parent
                    unit: "MHz"; zeroBased: true; minSpan: 500; fillKey: "g_clk"; legendRows: 2
                    hist: backend.history; windowSeconds: backend.historyWindow
                    series: [
                        { key: "g_clk", label: "GPU-Takt", color: Theme.seriesGpuA },
                        { key: "c_clk", label: "CPU-Takt Ø", color: Theme.seriesCpu }
                    ]
                }
            }
        }
    }
}
