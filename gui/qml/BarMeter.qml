// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."

Item {
    id: root
    property string label: ""
    property string valueText: ""
    property real fraction: 0
    readonly property real f: Math.max(0, Math.min(1, isNaN(fraction) ? 0 : fraction))
    implicitHeight: 34

    Text {
        id: l
        text: root.label
        color: Theme.textDim
        font.pixelSize: Theme.fsTiny
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
    }
    Text {
        anchors.right: parent.right
        text: root.valueText
        color: Theme.text
        font.pixelSize: Theme.fsSmall
        font.weight: Font.DemiBold
    }
    Item {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: l.bottom; anchors.topMargin: 6
        height: 8
        Rectangle { anchors.fill: parent; radius: 4; color: Theme.field; border.color: Theme.fieldBorder; border.width: 1 }
        Rectangle {
            width: Math.max(8, parent.width * root.f); height: parent.height + 6; y: -3; x: 0
            radius: 7; color: Theme.red; opacity: 0.16
            Behavior on width { NumberAnimation { duration: 300 } }
        }
        Rectangle {
            width: Math.max(8, parent.width * root.f); height: parent.height; radius: 4
            Behavior on width { NumberAnimation { duration: 300 } }
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.redDeep }
                GradientStop { position: 1; color: Theme.redSoft }
            }
            Rectangle {
                x: 3; y: 1; width: parent.width - 6; height: 2; radius: 1; color: "#55ffffff"
            }
        }
    }
}
