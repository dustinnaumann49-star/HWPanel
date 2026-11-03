// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root
    property string label: ""
    property string value: "–"
    property string unit: ""
    property string sub: ""
    property string tip: ""      // Hint text on hover
    property bool warn: false    // highlight subtitle in red
    implicitWidth: 120
    implicitHeight: col.implicitHeight

    ColumnLayout {
        id: col
        width: parent.width
        spacing: 1
        Text {
            text: root.label
            color: Theme.textDim
            font.pixelSize: Theme.fsTiny
            font.letterSpacing: 1.2
            font.capitalization: Font.AllUppercase
        }
        RowLayout {
            spacing: 5
            Text { text: root.value; color: "white"; font.pixelSize: Theme.fsBig; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignBaseline }
            Text { text: root.unit; color: Theme.redSoft; font.pixelSize: Theme.fsBase; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignBaseline }
        }
        Text {
            Layout.fillWidth: true
            text: root.sub
            color: root.warn ? Theme.redError : Theme.textFaint
            font.pixelSize: Theme.fsSmall
            elide: Text.ElideRight
            visible: root.sub !== ""
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.tip !== ""
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        ToolTip.visible: containsMouse && root.tip !== ""
        ToolTip.delay: 250
        ToolTip.text: root.tip
    }
}
