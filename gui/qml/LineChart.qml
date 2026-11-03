// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 shadoweagle

import QtQuick
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

// History chart: glowing lines, area with reflection below the axis,
// markers for profile changes, maximum values in the legend and hover display.
Item {
    id: root
    property string title: ""
    property string unit: ""
    property var series: []          // [{key, label, color}]
    property var hist: ({})          // {t:[], <key>:[], events:[{t,text}]}
    property real windowSeconds: 300
    property bool zeroBased: false
    property real yMinFixed: NaN
    property real yMaxFixed: NaN
    property real minSpan: 10
    property string fillKey: ""
    property int decimals: 0
    property bool compact: false
    property int legendRows: 1

    readonly property var tArr: (hist && hist.t) ? hist.t : []
    readonly property var evs: (hist && hist.events) ? hist.events : []
    readonly property real tEnd: tArr.length ? tArr[tArr.length - 1] : 0
    readonly property real tStart: tEnd - windowSeconds

    readonly property real pL: 48
    readonly property real pR: cv.width - 12
    readonly property real pT: 6
    readonly property real reflH: compact ? 12 : 20
    readonly property real pB: cv.height - reflH - 22

    property real yLo: 0
    property real yHi: 1
    property int hoverIdx: -1

    // Hidden pages are not drawn; when shown again, it catches up once.
    function repaint() { if (visible) cv.requestPaint() }
    // text drawn directly on the canvas: a language change triggers a repaint
    readonly property string waitText: qsTr("Waiting for measurements …")
    onWaitTextChanged: cv.requestPaint()
    onHistChanged: repaint()
    onSeriesChanged: repaint()
    onWindowSecondsChanged: repaint()
    onVisibleChanged: repaint()

    function rgba(c, a) {
        var col = Qt.color(c)
        return "rgba(" + Math.round(col.r * 255) + "," + Math.round(col.g * 255) + "," + Math.round(col.b * 255) + "," + a + ")"
    }

    function valid(v) { return !(v === null || v === undefined || isNaN(v)) }

    function stat(key) {
        var a = hist ? hist[key] : null
        var mx = -Infinity, last = NaN
        if (a) {
            for (var i = 0; i < a.length; i++) {
                if (!valid(a[i])) continue
                if (a[i] > mx) mx = a[i]
                last = a[i]
            }
        }
        return { last: last, max: (mx === -Infinity) ? NaN : mx }
    }

    function fmtVal(v) { return valid(v) ? Number(v).toFixed(decimals) : "–" }

    function yOf(v) { return pT + (1 - (v - yLo) / (yHi - yLo)) * (pB - pT) }
    function xOf(t) { return pL + (t - tStart) / windowSeconds * (pR - pL) }

    function updateHover(mx) {
        if (!tArr.length || mx < pL || mx > pR) { hoverIdx = -1; return }
        var t = tStart + (mx - pL) / (pR - pL) * windowSeconds
        var lo = 0, hi = tArr.length - 1
        while (lo < hi) {
            var mid = (lo + hi) >> 1
            if (tArr[mid] < t) lo = mid + 1; else hi = mid
        }
        if (lo > 0 && Math.abs(tArr[lo - 1] - t) < Math.abs(tArr[lo] - t)) lo = lo - 1
        hoverIdx = lo
    }

    // Legend
    Flow {
        id: legend
        width: parent.width
        height: Math.max(childrenRect.height, root.legendRows * 22 - 8)
        spacing: 8
        Repeater {
            model: root.series
            Row {
                spacing: 7
                rightPadding: 14
                Rectangle {
                    width: 10; height: 10; radius: 5; color: modelData.color; anchors.verticalCenter: parent.verticalCenter
                    Rectangle { anchors.fill: parent; anchors.margins: -4; radius: width / 2; color: modelData.color; opacity: 0.25; z: -1 }
                }
                Text { text: modelData.label; color: Theme.textDim; font.pixelSize: Theme.fsSmall; anchors.verticalCenter: parent.verticalCenter }
                Text {
                    text: root.fmtVal(root.stat(modelData.key).last) + " " + root.unit
                    color: "white"; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: qsTr("max %1").arg(root.fmtVal(root.stat(modelData.key).max))
                    color: Theme.textFaint; font.pixelSize: Theme.fsSmall; anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    Canvas {
        id: cv
        renderStrategy: Canvas.Threaded
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: legend.bottom; anchors.topMargin: 6
        anchors.bottom: parent.bottom
        onWidthChanged: root.repaint()
        onHeightChanged: root.repaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var L = root.pL, R = root.pR, T = root.pT, B = root.pB
            var pw = R - L, ph = B - T
            if (pw < 20 || ph < 20) return

            // y range
            var lo = Infinity, hi = -Infinity, s, i
            for (s = 0; s < root.series.length; s++) {
                var arr = root.hist[root.series[s].key]
                if (!arr) continue
                for (i = 0; i < arr.length; i++) {
                    var v = arr[i]
                    if (!root.valid(v)) continue
                    if (v < lo) lo = v
                    if (v > hi) hi = v
                }
            }
            if (!isFinite(lo)) { lo = 0; hi = 1 }
            if (root.zeroBased) lo = 0
            if (!isNaN(root.yMinFixed)) lo = root.yMinFixed
            if (!isNaN(root.yMaxFixed)) hi = root.yMaxFixed
            if (hi - lo < root.minSpan) {
                if (root.zeroBased || !isNaN(root.yMinFixed)) hi = lo + root.minSpan
                else { var c = (hi + lo) / 2; lo = c - root.minSpan / 2; hi = c + root.minSpan / 2 }
            }
            if (isNaN(root.yMaxFixed)) hi += (hi - lo) * 0.08
            if (!root.zeroBased && isNaN(root.yMinFixed)) lo -= (hi - lo) * 0.06
            var rough = (hi - lo) / 4
            var mag = Math.pow(10, Math.floor(Math.log(rough) / Math.LN10))
            var norm = rough / mag
            var step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag
            lo = root.zeroBased || !isNaN(root.yMinFixed) ? lo : Math.floor(lo / step) * step
            if (isNaN(root.yMaxFixed)) hi = Math.ceil(hi / step) * step
            root.yLo = lo
            root.yHi = hi

            function X(t) { return L + (t - root.tStart) / root.windowSeconds * pw }
            function Y(val) { return T + (1 - (val - lo) / (hi - lo)) * ph }

            // Grid and y labels
            ctx.font = "11px sans-serif"
            ctx.textAlign = "right"
            ctx.textBaseline = "middle"
            var n = Math.round((hi - lo) / step)
            for (i = 0; i <= n; i++) {
                var gv = lo + i * step
                var gy = Math.round(Y(gv)) + 0.5
                ctx.strokeStyle = Theme.rgba(Theme.tint, 0.11)
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(L, gy); ctx.lineTo(R, gy); ctx.stroke()
                ctx.fillStyle = "#8c7777"
                ctx.fillText(gv.toFixed(root.decimals), L - 8, gy)
            }

            // x labels (time of day)
            var ts = root.windowSeconds <= 60 ? 10 : root.windowSeconds <= 300 ? 60 : root.windowSeconds <= 900 ? 180 : 600
            ctx.textAlign = "center"
            ctx.textBaseline = "alphabetic"
            if (root.tArr.length) {
                for (var tt = Math.ceil(root.tStart / ts) * ts; tt <= root.tEnd; tt += ts) {
                    var gx = Math.round(X(tt)) + 0.5
                    if (gx < L + 14 || gx > R - 14) continue
                    ctx.strokeStyle = Theme.rgba(Theme.tint, 0.06)
                    ctx.beginPath(); ctx.moveTo(gx, T); ctx.lineTo(gx, B); ctx.stroke()
                    ctx.fillStyle = "#8c7777"
                    ctx.fillText(Qt.formatTime(new Date(tt * 1000), ts < 60 ? "hh:mm:ss" : "hh:mm"), gx, B + root.reflH + 15)
                }
            } else {
                ctx.fillStyle = "#6d5a5a"
                ctx.textAlign = "center"
                ctx.fillText(root.waitText, (L + R) / 2, (T + B) / 2)
                return
            }

            // Profile events
            var rowEnd = [-1e9, -1e9, -1e9]
            var labels = []
            for (i = 0; i < root.evs.length; i++) {
                var e = root.evs[i]
                if (e.t < root.tStart || e.t > root.tEnd) continue
                var ex = Math.round(X(e.t)) + 0.5
                ctx.strokeStyle = "rgba(255,255,255,0.32)"
                ctx.lineWidth = 1
                for (var dy = T; dy < B; dy += 8) { ctx.beginPath(); ctx.moveTo(ex, dy); ctx.lineTo(ex, Math.min(dy + 4, B)); ctx.stroke() }
                ctx.fillStyle = "rgba(255,255,255,0.9)"
                ctx.beginPath(); ctx.moveTo(ex - 4, T); ctx.lineTo(ex + 4, T); ctx.lineTo(ex, T + 6); ctx.closePath(); ctx.fill()
                if (!root.compact) {
                    ctx.font = "10px sans-serif"
                    ctx.textAlign = "left"
                    var tw = ctx.measureText(e.text).width
                    var lx = Math.max(L + 2, Math.min(ex + 5, R - tw - 4))   // keep long texts inside the edge
                    for (var row = 0; row < 3; row++) {
                        if (lx >= rowEnd[row]) {
                            labels.push({ x: lx, y: T + 18 + row * 12, w: tw, text: e.text })
                            rowEnd[row] = lx + tw + 8
                            break
                        }
                    }
                    ctx.font = "11px sans-serif"
                }
            }

            // Segments (gaps for missing values)
            function segments(key) {
                var a = root.hist[key], t = root.tArr, out = [], cur = []
                if (!a) return out
                var gap = Math.max(5, root.windowSeconds / 600 * 3)
                for (var k = 0; k < a.length; k++) {
                    var bad = !root.valid(a[k])
                    if (bad || (cur.length && t[k] - t[k - 1] > gap)) { if (cur.length) out.push(cur); cur = [] }
                    if (!bad) cur.push([X(t[k]), Y(a[k])])
                }
                if (cur.length) out.push(cur)
                return out
            }

            // Area + reflection for the main series
            var fillS = null
            for (s = 0; s < root.series.length; s++) {
                if (root.series[s].key === root.fillKey) fillS = root.series[s]
            }
            if (fillS) {
                var segs = segments(fillS.key)
                var area = ctx.createLinearGradient(0, T, 0, B)
                area.addColorStop(0, root.rgba(fillS.color, 0.34))
                area.addColorStop(1, root.rgba(fillS.color, 0.02))
                ctx.fillStyle = area
                for (i = 0; i < segs.length; i++) {
                    var sg = segs[i]
                    if (sg.length < 2) continue
                    ctx.beginPath()
                    ctx.moveTo(sg[0][0], B)
                    for (var j = 0; j < sg.length; j++) ctx.lineTo(sg[j][0], sg[j][1])
                    ctx.lineTo(sg[sg.length - 1][0], B)
                    ctx.closePath()
                    ctx.fill()
                }
                // Reflection below the axis
                ctx.save()
                ctx.beginPath(); ctx.rect(L, B, pw, root.reflH); ctx.clip()
                ctx.translate(0, 2 * B)
                ctx.scale(1, -1)
                var refl = ctx.createLinearGradient(0, B, 0, B - root.reflH)
                refl.addColorStop(0, root.rgba(fillS.color, 0.30))
                refl.addColorStop(1, root.rgba(fillS.color, 0))
                ctx.fillStyle = refl
                for (i = 0; i < segs.length; i++) {
                    var sr = segs[i]
                    if (sr.length < 2) continue
                    ctx.beginPath()
                    ctx.moveTo(sr[0][0], B)
                    for (var jr = 0; jr < sr.length; jr++) ctx.lineTo(sr[jr][0], sr[jr][1])
                    ctx.lineTo(sr[sr.length - 1][0], B)
                    ctx.closePath()
                    ctx.fill()
                }
                ctx.restore()
            }

            // Axis line
            ctx.strokeStyle = Theme.rgba(Theme.redSoft, 0.45)
            ctx.lineWidth = 1
            ctx.beginPath(); ctx.moveTo(L, Math.round(B) + 0.5); ctx.lineTo(R, Math.round(B) + 0.5); ctx.stroke()

            // Lines with glow
            for (s = 0; s < root.series.length; s++) {
                var ss = segments(root.series[s].key)
                ctx.save()
                ctx.lineWidth = root.compact ? 1.8 : 2.2
                ctx.lineJoin = "round"
                ctx.lineCap = "round"
                var baseW = ctx.lineWidth, col = root.series[s].color
                for (i = 0; i < ss.length; i++) {
                    var p = ss[i]
                    if (p.length === 1) {
                        ctx.fillStyle = col
                        ctx.beginPath(); ctx.arc(p[0][0], p[0][1], 2, 0, 6.283); ctx.fill()
                        continue
                    }
                    ctx.beginPath()
                    ctx.moveTo(p[0][0], p[0][1])
                    for (var q = 1; q < p.length; q++) ctx.lineTo(p[q][0], p[q][1])
                    // Glow without blur: two wider, semi-transparent passes under the line
                    ctx.lineWidth = baseW + (root.compact ? 5 : 8)
                    ctx.strokeStyle = root.rgba(col, 0.10)
                    ctx.stroke()
                    ctx.lineWidth = baseW + (root.compact ? 2.5 : 4)
                    ctx.strokeStyle = root.rgba(col, 0.20)
                    ctx.stroke()
                    ctx.lineWidth = baseW
                    ctx.strokeStyle = col
                    ctx.stroke()
                }
                ctx.restore()
            }

            // Labels of the profile changes above the lines, with a dark background
            ctx.font = "10px sans-serif"
            ctx.textAlign = "left"
            for (i = 0; i < labels.length; i++) {
                var lb = labels[i]
                ctx.fillStyle = "rgba(6,3,5,0.78)"
                ctx.fillRect(lb.x - 3, lb.y - 10, lb.w + 6, 14)
                ctx.fillStyle = "rgba(255,235,238,0.95)"
                ctx.fillText(lb.text, lb.x, lb.y)
            }
        }
    }

    // Hover: crosshair, points and values
    MouseArea {
        anchors.fill: cv
        hoverEnabled: true
        onPositionChanged: (m) => root.updateHover(m.x)
        onExited: root.hoverIdx = -1
    }
    Rectangle {
        visible: root.hoverIdx >= 0
        x: cv.x + (root.hoverIdx >= 0 ? root.xOf(root.tArr[root.hoverIdx]) : 0)
        y: cv.y + root.pT
        width: 1; height: root.pB - root.pT
        color: "#77ffffff"
    }
    Repeater {
        model: root.series
        Rectangle {
            readonly property var arr: root.hist[modelData.key]
            readonly property real val: (root.hoverIdx >= 0 && arr) ? arr[root.hoverIdx] : NaN
            visible: root.hoverIdx >= 0 && root.valid(val)
            width: 9; height: 9; radius: 5
            x: cv.x + (root.hoverIdx >= 0 ? root.xOf(root.tArr[root.hoverIdx]) : 0) - 4
            y: cv.y + (root.valid(val) ? root.yOf(val) : 0) - 4
            color: modelData.color
            border.color: "white"; border.width: 1
        }
    }
    Rectangle {
        id: tip
        visible: root.hoverIdx >= 0
        readonly property real hx: root.hoverIdx >= 0 ? cv.x + root.xOf(root.tArr[root.hoverIdx]) : 0
        x: hx + 14 + width > root.width ? hx - 14 - width : hx + 14
        y: cv.y + root.pT + 4
        width: tipCol.implicitWidth + 24
        height: tipCol.implicitHeight + 18
        radius: 10
        color: "#ee0b0507"
        border.color: Theme.red; border.width: 1
        Column {
            id: tipCol
            anchors.centerIn: parent
            spacing: 3
            Text {
                text: root.hoverIdx >= 0 ? Qt.formatTime(new Date(root.tArr[root.hoverIdx] * 1000), "hh:mm:ss") : ""
                color: Theme.textDim; font.pixelSize: Theme.fsSmall
            }
            Repeater {
                model: root.series
                Text {
                    readonly property var arr: root.hist[modelData.key]
                    text: modelData.label + "  " + root.fmtVal((root.hoverIdx >= 0 && arr) ? arr[root.hoverIdx] : NaN) + " " + root.unit
                    color: modelData.color; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold
                }
            }
        }
    }
}
