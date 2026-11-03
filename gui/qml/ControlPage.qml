// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

Item {
    id: page
    property bool loaded: false
    property int tab: 0

    function tryLoad() {
        if (loaded) return
        if (Fmt.get(backend.info, ["limits"], null) && Fmt.get(backend.status, ["settings"], null)) {
            form.loadCurrent()
            fanForm.loadCurrent()
            loaded = true
        }
    }
    Connections {
        target: backend
        function onInfoChanged() { page.tryLoad() }
        function onStatusChanged() { page.tryLoad() }
    }
    Component.onCompleted: tryLoad()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 22

        ColumnLayout {
            spacing: 2
            Text { text: qsTr("Manual"); color: "white"; font.pixelSize: Theme.fsBig; font.weight: Font.DemiBold }
            Text { text: qsTr("Set values directly. The sliders end at the driver default, overclocking is not possible.")
                   color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
        }

        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: 548
            padding: 28
            ColumnLayout {
                anchors.fill: parent
                spacing: 18
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    GlowButton { compact: true; text: qsTr("Clocks & CPU"); active: page.tab === 0; onClicked: page.tab = 0 }
                    GlowButton { compact: true; text: qsTr("Fan"); active: page.tab === 1; onClicked: page.tab = 1 }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: qsTr("Apply covers both tabs.")
                        color: Theme.textFaint; font.pixelSize: Theme.fsTiny
                    }
                }
                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: page.tab
                    SettingsForm { id: form; Layout.fillWidth: true; Layout.alignment: Qt.AlignTop }
                    FanForm { id: fanForm; Layout.fillWidth: true; Layout.fillHeight: true }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    GlowButton {
                        text: qsTr("Load current values")
                        onClicked: { form.loadCurrent(); fanForm.loadCurrent() }
                    }
                    Item { Layout.fillWidth: true }
                    GlowButton {
                        text: qsTr("Reset all to default")
                        onClicked: { backend.resetAll(); form.loadDefaults(); fanForm.loadDefaults() }
                    }
                    GlowButton {
                        primary: true
                        text: qsTr("Apply")
                        enabled: fanForm.ruleError === ""
                        onClicked: backend.setManual(form.gpuValues(true), form.cpuValues(true), fanForm.fanValue())
                    }
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
}
