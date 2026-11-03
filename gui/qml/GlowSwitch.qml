// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."

Item {
    id: root
    property bool checked: false
    signal toggled(bool value)
    implicitWidth: 52
    implicitHeight: 28
    opacity: enabled ? 1 : 0.4

    Rectangle {
        anchors.fill: parent; anchors.margins: -4; radius: height / 2; color: Theme.red
        opacity: root.checked ? 0.24 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
    }
    Rectangle {
        anchors.fill: parent
        radius: height / 2
        gradient: Gradient {
            GradientStop { position: 0; color: root.checked ? Theme.redButtonBottom : "#1f0e0e" }
            GradientStop { position: 1; color: root.checked ? "#5c0000" : "#120606" }
        }
        border.width: 1
        border.color: root.checked ? Theme.red : Theme.line
        Rectangle {
            width: parent.height - 6; height: width; radius: width / 2; y: 3
            x: root.checked ? parent.width - width - 3 : 3
            color: root.checked ? "#ffffff" : "#8c7777"
            Behavior on x { NumberAnimation { duration: 120 } }
        }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
