// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import "."

// Glassy card: black gradient, red glow, highlight at the top left, red border.
Item {
    id: root
    property real radius: Theme.radius
    property real glow: Theme.glowAlpha
    property bool active: false
    property int padding: Theme.pad
    default property alias content: inner.data

    readonly property real shown: active ? Math.min(1, glow * 1.9) : glow

    // Red glow: stacked, semi-transparent rectangles (runs in the scene graph, costs almost no time)
    Item {
        anchors.fill: parent
        anchors.topMargin: 6
        anchors.bottomMargin: -6
        Repeater {
            model: 9
            Rectangle {
                readonly property real d: 3.4 * (index + 1)
                anchors.fill: parent
                anchors.margins: -d
                radius: root.radius + d
                color: Theme.red
                opacity: root.shown * 0.075
            }
        }
    }

    Canvas {
        id: bg
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: root; function onActiveChanged() { bg.requestPaint() } function onRadiusChanged() { bg.requestPaint() } }
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = width, h = height, r = root.radius
            if (w < 4 || h < 4) return
            function rr(x, y, w2, h2, r2) {
                ctx.beginPath()
                ctx.moveTo(x + r2, y)
                ctx.arcTo(x + w2, y, x + w2, y + h2, r2)
                ctx.arcTo(x + w2, y + h2, x, y + h2, r2)
                ctx.arcTo(x, y + h2, x, y, r2)
                ctx.arcTo(x, y, x + w2, y, r2)
                ctx.closePath()
            }
            var m = 0
            // Body
            var body = ctx.createLinearGradient(0, m, 0, m + h)
            body.addColorStop(0, Theme.cardTop)
            body.addColorStop(1, Theme.cardBottom)
            rr(m, m, w, h, r)
            ctx.fillStyle = body
            ctx.fill()
            // Gloss (reflection) at the top left
            ctx.save()
            rr(m, m, w, h, r)
            ctx.clip()
            var sheen = ctx.createLinearGradient(m, m, m + w * 0.55, m + h * 0.95)
            sheen.addColorStop(0, Theme.rgba(Theme.gloss, Theme.glossAlpha))
            sheen.addColorStop(0.32, Theme.rgba(Theme.gloss, 0.035))
            sheen.addColorStop(0.33, Theme.rgba(Theme.gloss, 0))
            sheen.addColorStop(1, Theme.rgba(Theme.gloss, 0))
            ctx.fillStyle = sheen
            ctx.fillRect(m, m, w, h)
            var hl = ctx.createLinearGradient(m, 0, m + w, 0)
            hl.addColorStop(0, Theme.rgba(Theme.glossHi, 0))
            hl.addColorStop(0.5, Theme.rgba(Theme.glossHi, 0.6))
            hl.addColorStop(1, Theme.rgba(Theme.glossHi, 0))
            ctx.fillStyle = hl
            ctx.fillRect(m, m, w, 1.5)
            ctx.restore()
            // Border
            var edge = ctx.createLinearGradient(0, m, 0, m + h)
            edge.addColorStop(0, Theme.rgba(Theme.redSoft, 0.85))
            edge.addColorStop(1, Theme.rgba(Theme.red, root.active ? 0.7 : 0.3))
            ctx.strokeStyle = edge
            ctx.lineWidth = root.active ? 1.6 : 1
            rr(m + 0.5, m + 0.5, w - 1, h - 1, r)
            ctx.stroke()
        }
    }

    Item {
        id: inner
        anchors.fill: parent
        anchors.margins: root.padding
    }
}
