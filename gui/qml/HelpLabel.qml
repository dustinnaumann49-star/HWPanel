// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import QtQuick.Layouts
import "."

// Small label with an explanation on hover. A "?" shows that there is one.
Item {
    id: root
    property string text: ""
    property string hint: ""
    property color color: Theme.textDim
    implicitWidth: row.implicitWidth
    implicitHeight: row.implicitHeight

    RowLayout {
        id: row
        spacing: 6
        Text {
            text: root.text
            color: root.color
            font.pixelSize: Theme.fsTiny
            font.letterSpacing: 1.2
            font.capitalization: Font.AllUppercase
        }
        Rectangle {
            visible: root.hint !== ""
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: 14; implicitHeight: 14; radius: 7
            color: hover.hovered ? Theme.redMuted : "transparent"
            border.width: 1
            border.color: hover.hovered ? Theme.redSoft : Theme.textFaint
            Text {
                anchors.centerIn: parent
                text: "?"
                color: hover.hovered ? Theme.redSoft : Theme.textDim
                font.pixelSize: 10
                font.weight: Font.Bold
            }
        }
    }

    HoverHandler { id: hover; enabled: root.hint !== "" }
    Hint { wanted: hover.hovered && root.hint !== ""; text: root.hint }
}
