// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import QtQuick.Controls.Basic
import "."

// Explanation on hover, in the style of the UI. The owner sets `wanted`,
// it is shown after a short delay below the parent element (or above it if there is no room below).
ToolTip {
    id: tip
    property bool wanted: false

    // as wide as the text, at most 300 px (longer texts wrap)
    contentWidth: Math.min(300, Math.ceil(metrics.advanceWidth) + 2)
    padding: 14
    margins: 12
    timeout: -1
    closePolicy: Popup.NoAutoClose

    onWantedChanged: {
        if (wanted) {
            delay.restart()
        } else {
            delay.stop()
            close()
        }
    }
    onAboutToShow: {
        x = Math.round((parent.width - width) / 2)
        var top = parent.mapToItem(Overlay.overlay, 0, 0).y
        y = (top + parent.height + 8 + height + margins > Overlay.overlay.height) ? -height - 8 : parent.height + 8
    }

    Timer { id: delay; interval: 350; onTriggered: if (tip.wanted && tip.text !== "") tip.open() }
    TextMetrics { id: metrics; text: tip.text; font.pixelSize: Theme.fsSmall }

    contentItem: Text {
        width: tip.availableWidth
        text: tip.text
        textFormat: Text.StyledText
        wrapMode: Text.WordWrap
        color: Theme.text
        font.pixelSize: Theme.fsSmall
        lineHeight: 1.12
    }
    background: Rectangle {
        radius: 12
        color: "#1c0a0a"
        border.width: 1
        border.color: Theme.redDeep
    }
}
