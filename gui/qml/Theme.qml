pragma Singleton
import QtQuick

// The entire look lives in this file: colors, font sizes, spacing.
QtObject {
    // Red palette: rich, dark red instead of neon. All reds of the UI are defined here.
    readonly property color red: "#D50000"          // accent: active borders, handles, glows
    readonly property color redButtonTop: "#E00000" // buttons and sliders (gradient top)
    readonly property color redButtonBottom: "#A80000"
    readonly property color redSoft: "#FF5252"      // labels and units (bright enough for small text)
    readonly property color redLight: "#FF6060"     // light borders on red surfaces
    readonly property color redDeep: "#8A0000"      // scrollbars, active surfaces
    readonly property color redMuted: "#3A0000"     // muted, for surfaces
    readonly property color redMuted2: "#2A0000"
    readonly property color redError: "#FF8A8A"     // error texts
    readonly property color tint: "#FF4444"         // grid, guide lines (use only with transparency)
    readonly property color gloss: "#FF7070"        // card highlight
    readonly property color glossHi: "#FF9A9A"

    // Neutral surfaces with a slight red tint
    readonly property color bg: "#050303"
    readonly property color bgTop: "#080404"
    readonly property color bgBottom: "#030202"
    readonly property color sideTop: "#0d0505"
    readonly property color sideBottom: "#060303"
    readonly property color field: "#1a0808"        // input fields, slider tracks
    readonly property color fieldBorder: "#3a1212"
    readonly property color line: "#4a1414"
    readonly property color buttonTop: "#2a1010"    // buttons without emphasis
    readonly property color buttonBottom: "#120606"
    readonly property color buttonBorder: "#561616"
    readonly property color text: "#f7eeee"
    readonly property color textDim: "#a58f8f"
    readonly property color textFaint: "#6d5a5a"

    // Card surface (top/bottom), gloss and glow
    readonly property color cardTop: "#250707"
    readonly property color cardBottom: "#0b0303"
    readonly property real glowAlpha: 0.34
    readonly property real glossAlpha: 0.14

    // Chart colors
    readonly property color seriesGpuA: "#FF3B3B"
    readonly property color seriesGpuB: "#ff8a4d"
    readonly property color seriesGpuC: "#FFB3B3"
    readonly property color seriesCpu: "#ffffff"
    readonly property color seriesFan: "#6ec1ff"

    // Color with transparency as CSS text for canvas
    function rgba(c, a) {
        var col = Qt.color(c)
        return "rgba(" + Math.round(col.r * 255) + "," + Math.round(col.g * 255) + "," + Math.round(col.b * 255) + "," + a + ")"
    }

    // Dimensions
    readonly property int radius: 18
    readonly property int pad: 18
    readonly property int gap: 16
    readonly property int fsTiny: 11
    readonly property int fsSmall: 12
    readonly property int fsBase: 14
    readonly property int fsMed: 17
    readonly property int fsBig: 28
    readonly property int fsHuge: 40
}
