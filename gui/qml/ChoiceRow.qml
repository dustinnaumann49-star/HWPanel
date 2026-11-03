// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."
import "Fmt.js" as Fmt

Flow {
    id: root
    property var options: []
    property string current: ""
    property string kind: ""      // "epp", "governor" or "sensor": which explanations appear on hover
    property string driver: ""    // CPU driver (for driver-dependent explanations)
    signal picked(string value)
    spacing: 8

    Repeater {
        model: root.options
        GlowButton {
            compact: true
            text: modelData
            hint: Fmt.optionHint(root.kind, modelData, root.driver)   // qsTr() lives in Fmt.js
            active: modelData === root.current
            onClicked: root.picked(modelData)
        }
    }
}
