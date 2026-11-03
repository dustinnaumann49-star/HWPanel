// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."

Item {
    id: root
    property string text: ""
    property bool active: false
    signal clicked()
    implicitHeight: 44
    implicitWidth: 180

    Rectangle {
        anchors.fill: body; anchors.margins: -4; radius: body.radius + 4; color: Theme.red
        opacity: root.active ? 0.2 : (mouse.containsMouse ? 0.08 : 0)
        Behavior on opacity { NumberAnimation { duration: 140 } }
    }
    Rectangle {
        id: body
        anchors.fill: parent
        radius: 14
        border.width: root.active ? 1 : 0
        border.color: Theme.redLight
        gradient: Gradient {
            GradientStop { position: 0; color: root.active ? Theme.redDeep : (mouse.containsMouse ? "#1d0a0a" : "transparent") }
            GradientStop { position: 1; color: root.active ? Theme.redMuted : (mouse.containsMouse ? "#120606" : "transparent") }
        }
        Rectangle {
            visible: root.active
            x: 6; y: 2; width: parent.width - 12; height: parent.height / 2 - 2; radius: 10
            gradient: Gradient {
                GradientStop { position: 0; color: "#30ffffff" }
                GradientStop { position: 1; color: "#00ffffff" }
            }
        }
    }
    Rectangle {
        visible: root.active
        x: 0; anchors.verticalCenter: parent.verticalCenter
        width: 3; height: 22; radius: 2; color: Theme.red
    }
    Text {
        anchors.verticalCenter: parent.verticalCenter
        x: 20
        text: root.text
        color: root.active ? "white" : Theme.textDim
        font.pixelSize: Theme.fsBase + 1
        font.weight: root.active ? Font.DemiBold : Font.Normal
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
