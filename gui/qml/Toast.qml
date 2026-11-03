// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."

Item {
    id: root
    property bool error: false
    property alias text: msg.text
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 28
    width: Math.min(parent.width - 80, msg.implicitWidth + 56)
    height: msg.implicitHeight + 28
    opacity: 0
    visible: opacity > 0
    z: 100

    function show(t, isError) {
        msg.text = t
        error = isError
        hideTimer.restart()
        fade.to = 1
        fade.restart()
    }

    NumberAnimation { id: fade; target: root; property: "opacity"; duration: 180 }
    Timer { id: hideTimer; interval: root.error ? 6000 : 3200; onTriggered: { fade.to = 0; fade.restart() } }

    Card {
        anchors.fill: parent
        padding: 0
        glow: root.error ? 0.6 : 0.4
        active: root.error
    }
    Text {
        id: msg
        anchors.centerIn: parent
        width: root.width - 40
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        color: root.error ? "#FFD0D0" : "white"
        font.pixelSize: Theme.fsBase
        font.weight: Font.DemiBold
    }
}
