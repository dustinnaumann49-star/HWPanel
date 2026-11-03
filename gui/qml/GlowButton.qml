// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."

Item {
    id: root
    property string text: ""
    property bool primary: false
    property bool active: false
    property bool compact: false
    property string hint: ""       // Explanation on hover (empty = none)
    property bool hintOff: false   // hidden after a click until the mouse leaves the button
    property color textColor: lit ? "white" : Theme.text
    signal clicked()

    readonly property bool lit: primary || active
    implicitWidth: label.implicitWidth + (compact ? 26 : 38)
    implicitHeight: compact ? 32 : 40
    opacity: enabled ? 1 : 0.4
    scale: mouse.pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: 80 } }

    // Glow
    Rectangle {
        anchors.fill: body; anchors.margins: -4; radius: body.radius + 4; color: Theme.red
        opacity: root.lit ? (mouse.containsMouse ? 0.32 : 0.22) : (mouse.containsMouse ? 0.14 : 0)
        Behavior on opacity { NumberAnimation { duration: 140 } }
    }
    Rectangle {
        anchors.fill: body; anchors.margins: -9; radius: body.radius + 9; color: Theme.red
        opacity: root.lit ? 0.08 : 0
    }
    Rectangle {
        id: body
        anchors.fill: parent
        radius: height / 2
        gradient: Gradient {
            GradientStop { position: 0; color: root.lit ? Theme.redButtonTop : Theme.buttonTop }
            GradientStop { position: 1; color: root.lit ? Theme.redButtonBottom : Theme.buttonBottom }
        }
        border.width: 1
        border.color: root.lit ? Theme.redLight : (mouse.containsMouse ? Theme.red : Theme.buttonBorder)
        // Gloss strip
        Rectangle {
            x: 7; y: 2; width: parent.width - 14; height: parent.height / 2 - 2; radius: height
            gradient: Gradient {
                GradientStop { position: 0; color: "#3cffffff" }
                GradientStop { position: 1; color: "#00ffffff" }
            }
        }
    }
    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.textColor
        font.pixelSize: root.compact ? Theme.fsSmall : Theme.fsBase
        font.weight: Font.DemiBold
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
        onPressed: root.hintOff = true
        onContainsMouseChanged: if (!containsMouse) root.hintOff = false
    }
    Hint { wanted: mouse.containsMouse && !root.hintOff && root.hint !== ""; text: root.hint }
}
