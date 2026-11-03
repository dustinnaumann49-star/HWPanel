import QtQuick
import "."
import "Fmt.js" as Fmt

// Grafischer Editor für die Lüfterkurve: Punkte ziehen, Doppelklick fügt einen Punkt hinzu.
// Die Kurve bleibt dabei immer gültig (Temperaturen aufsteigend, Prozentwerte nicht fallend).
Item {
    id: root
    property var points: []            // [[°C, %], ...]
    property real tMin: 20
    property real tMax: 100
    property real tempNow: NaN         // aktuelle Sensortemperatur (Live-Marker)
    property int minPoints: 2
    property int maxPoints: 10
    property int selected: -1
    property int hovered: -1
    property bool editable: true
    signal edited(var pts)

    readonly property real pL: 44
    readonly property real pR: 18
    readonly property real pT: 14
    readonly property real pB: 30
    readonly property real pw: width - pL - pR
    readonly property real ph: height - pT - pB
    readonly property real liveTarget: Fmt.curveValue(points, tempNow)

    function xOf(t) { return pL + (t - tMin) / (tMax - tMin) * pw }
    function yOf(p) { return pT + (1 - p / 100) * ph }
    function tOf(x) { return tMin + (x - pL) / pw * (tMax - tMin) }
    function pOf(y) { return (1 - (y - pT) / ph) * 100 }

    function clonePts() {
        var out = []
        for (var i = 0; i < points.length; i++) out.push([points[i][0], points[i][1]])
        return out
    }

    function moveTo(i, t, p) {
        var pts = clonePts(), n = pts.length
        var tLo = i > 0 ? pts[i - 1][0] + 1 : tMin
        var tHi = i < n - 1 ? pts[i + 1][0] - 1 : tMax
        var pLo = i > 0 ? pts[i - 1][1] : 0
        var pHi = i < n - 1 ? pts[i + 1][1] : 100
        var nt = Math.max(tLo, Math.min(tHi, Math.round(t)))
        var np = Math.max(pLo, Math.min(pHi, Math.round(p)))
        if (nt === pts[i][0] && np === pts[i][1]) return
        pts[i] = [nt, np]
        edited(pts)
    }

    function addAt(t) {
        if (points.length >= maxPoints) return
        var nt = Math.max(tMin, Math.min(tMax, Math.round(t)))
        var pts = clonePts(), idx = 0
        for (var i = 0; i < pts.length; i++) {
            if (pts[i][0] === nt) return
            if (pts[i][0] < nt) idx = i + 1
        }
        pts.splice(idx, 0, [nt, Math.round(Fmt.curveValue(pts, nt))])
        selected = idx
        edited(pts)
    }

    function removeSelected() {
        if (selected < 0 || points.length <= minPoints) return
        var pts = clonePts()
        pts.splice(selected, 1)
        selected = -1
        edited(pts)
    }

    function nudge(dt, dp) {
        if (selected < 0) return
        moveTo(selected, points[selected][0] + dt, points[selected][1] + dp)
    }

    function hit(x, y) {
        var best = -1, bd = 18 * 18
        for (var i = 0; i < points.length; i++) {
            var dx = xOf(Math.max(tMin, Math.min(tMax, points[i][0]))) - x
            var dy = yOf(points[i][1]) - y
            var d = dx * dx + dy * dy
            if (d < bd) { bd = d; best = i }
        }
        return best
    }

    activeFocusOnTab: true
    Keys.onPressed: (e) => {
        if (!editable) return
        var step = (e.modifiers & Qt.ShiftModifier) ? 5 : 1
        if (e.key === Qt.Key_Left) nudge(-step, 0)
        else if (e.key === Qt.Key_Right) nudge(step, 0)
        else if (e.key === Qt.Key_Up) nudge(0, step)
        else if (e.key === Qt.Key_Down) nudge(0, -step)
        else if (e.key === Qt.Key_Delete || e.key === Qt.Key_Backspace) removeSelected()
        else return
        e.accepted = true
    }

    function repaint() { if (visible) cv.requestPaint() }
    // direkt auf die Leinwand gezeichneter Text: Änderung der Sprache löst ein Neuzeichnen aus
    readonly property string liveText: qsTr("now %1 °C → %2 %")
    onLiveTextChanged: cv.requestPaint()
    onPointsChanged: repaint()
    onTempNowChanged: repaint()
    onSelectedChanged: repaint()
    onEditableChanged: repaint()
    onWidthChanged: repaint()
    onHeightChanged: repaint()
    onVisibleChanged: repaint()

    Canvas {
        id: cv
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var L = root.pL, R = width - root.pR, T = root.pT, B = height - root.pB
            if (R - L < 40 || B - T < 40) return

            // Raster und Beschriftung
            ctx.font = "11px sans-serif"
            ctx.fillStyle = "#8a7777"
            ctx.strokeStyle = Theme.rgba(Theme.tint, 0.13)
            ctx.lineWidth = 1
            ctx.textAlign = "right"
            for (var p = 0; p <= 100; p += 25) {
                var gy = Math.round(root.yOf(p)) + 0.5
                ctx.beginPath(); ctx.moveTo(L, gy); ctx.lineTo(R, gy); ctx.stroke()
                ctx.fillText(p + " %", L - 8, gy + 4)
            }
            ctx.textAlign = "center"
            for (var t = Math.ceil(root.tMin / 10) * 10; t <= root.tMax; t += 10) {
                var gx = Math.round(root.xOf(t)) + 0.5
                ctx.beginPath(); ctx.moveTo(gx, T); ctx.lineTo(gx, B); ctx.stroke()
                ctx.fillText(t + "°", gx, B + 18)
            }
            var pts = root.points
            if (!pts || pts.length < 2) return

            function X(v) { return root.xOf(Math.max(root.tMin, Math.min(root.tMax, v))) }
            function Y(v) { return root.yOf(v) }

            // Kurvenpfad: links und rechts waagerecht bis zum Rand
            function path() {
                ctx.beginPath()
                ctx.moveTo(L, Y(pts[0][1]))
                for (var i = 0; i < pts.length; i++) ctx.lineTo(X(pts[i][0]), Y(pts[i][1]))
                ctx.lineTo(R, Y(pts[pts.length - 1][1]))
            }

            // Fläche unter der Kurve
            ctx.save()
            ctx.globalAlpha = root.editable ? 1 : 0.4
            path()
            ctx.lineTo(R, B); ctx.lineTo(L, B); ctx.closePath()
            var g = ctx.createLinearGradient(0, T, 0, B)
            g.addColorStop(0, Theme.rgba(Theme.seriesGpuA, 0.34))
            g.addColorStop(1, Theme.rgba(Theme.seriesGpuA, 0.02))
            ctx.fillStyle = g
            ctx.fill()

            // Leuchtende Linie
            path()
            ctx.lineJoin = "round"
            ctx.lineWidth = 9
            ctx.strokeStyle = Theme.rgba(Theme.seriesGpuA, 0.10)
            ctx.stroke()
            ctx.lineWidth = 5
            ctx.strokeStyle = Theme.rgba(Theme.seriesGpuA, 0.22)
            ctx.stroke()
            ctx.lineWidth = 2.6
            ctx.strokeStyle = Theme.seriesGpuA
            ctx.stroke()
            ctx.restore()

            // Live-Marker: aktuelle Temperatur und Zielwert der Kurve
            if (root.editable && root.tempNow > 0 && !isNaN(root.liveTarget)) {
                var lx = X(root.tempNow), ly = Y(root.liveTarget)
                ctx.save()
                ctx.setLineDash([4, 4])
                ctx.strokeStyle = "rgba(255,255,255,0.45)"
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(Math.round(lx) + 0.5, T); ctx.lineTo(Math.round(lx) + 0.5, B); ctx.stroke()
                ctx.restore()
                ctx.save()
                ctx.fillStyle = "rgba(255,255,255,0.22)"
                ctx.beginPath(); ctx.arc(lx, ly, 8, 0, 6.283); ctx.fill()
                ctx.fillStyle = "#ffffff"
                ctx.beginPath(); ctx.arc(lx, ly, 4, 0, 6.283); ctx.fill()
                ctx.restore()
                var txt = root.liveText.arg(Math.round(root.tempNow)).arg(Math.round(root.liveTarget))
                ctx.font = "11px sans-serif"
                var tw = ctx.measureText(txt).width
                var bx = (lx + 8 + tw + 8 > R) ? lx - tw - 12 : lx + 8
                var by = T + 4   // oben im Diagramm, damit Punkte und Kurve frei bleiben
                ctx.fillStyle = "rgba(6,3,5,0.82)"
                ctx.fillRect(bx - 4, by, tw + 8, 18)
                ctx.fillStyle = "#ffffff"
                ctx.textAlign = "left"
                ctx.fillText(txt, bx, by + 13)
            }
        }
    }

    // Anfasser
    Repeater {
        model: root.points.length
        Item {
            readonly property bool sel: index === root.selected
            readonly property bool hov: index === root.hovered
            x: root.xOf(Math.max(root.tMin, Math.min(root.tMax, root.points[index][0]))) - width / 2
            y: root.yOf(root.points[index][1]) - height / 2
            width: 22; height: 22
            opacity: root.editable ? 1 : 0.35
            Rectangle {
                anchors.centerIn: parent
                width: (sel || hov) ? 26 : 20; height: width; radius: width / 2
                color: Theme.red; opacity: sel ? 0.4 : (hov ? 0.28 : 0.16)
            }
            Rectangle {
                anchors.centerIn: parent
                width: sel ? 14 : 12; height: width; radius: width / 2
                color: sel ? "#ffffff" : Theme.seriesGpuC
                border.width: 2; border.color: Theme.red
            }
            // Wert am Punkt
            Rectangle {
                visible: sel || hov
                x: parent.width / 2 - width / 2
                y: root.points[index][1] > 82 ? 26 : -34
                width: tip.implicitWidth + 14; height: 22; radius: 8
                color: "#d9060304"; border.width: 1; border.color: "#7a1010"
                Text {
                    id: tip
                    anchors.centerIn: parent
                    text: root.points[index][0] + " °C · " + root.points[index][1] + " %"
                    color: "white"; font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold
                }
            }
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        enabled: root.editable
        hoverEnabled: true
        property int dragIdx: -1
        cursorShape: (dragIdx >= 0 || root.hovered >= 0) ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: (m) => {
            root.forceActiveFocus()
            dragIdx = root.hit(m.x, m.y)
            root.selected = dragIdx
        }
        onPositionChanged: (m) => {
            if (pressed && dragIdx >= 0) root.moveTo(dragIdx, root.tOf(m.x), root.pOf(m.y))
            else root.hovered = root.hit(m.x, m.y)
        }
        onReleased: dragIdx = -1
        onExited: root.hovered = -1
        onDoubleClicked: (m) => {
            if (root.hit(m.x, m.y) < 0 && m.x >= root.pL && m.x <= width - root.pR) root.addAt(root.tOf(m.x))
        }
    }
}
