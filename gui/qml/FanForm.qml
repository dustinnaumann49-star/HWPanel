import QtQuick
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

// Fan settings: automatic (driver) or custom curve with graphical editor.
Item {
    id: f
    property bool curveOn: false
    property string sensor: "edge"
    property var pts: []

    readonly property var info: Fmt.get(backend.info, ["fan"], ({}))
    readonly property bool supported: Fmt.get(info, ["supported"], false)
    readonly property var example: Fmt.get(info, ["example_curve"], [[30, 40], [40, 50], [50, 60], [60, 70], [70, 80], [80, 90]])
    readonly property var rules: Fmt.get(info, ["rules"], [[60, 30], [80, 50]])
    readonly property real safetyC: Fmt.get(info, ["safety_junction_c"], 100)
    readonly property string ruleError: (curveOn && supported) ? Fmt.ruleError(pts, rules) : ""
    readonly property var gpu: Fmt.get(backend.status, ["gpu"], ({}))
    readonly property real tempNow: {
        var v = sensor === "junction" ? gpu.temp_junction_c : (sensor === "mem" ? gpu.temp_mem_c : gpu.temp_edge_c)
        return (v === null || v === undefined) ? NaN : v
    }

    function copy(c) {
        var out = []
        for (var i = 0; i < c.length; i++) out.push([c[i][0], c[i][1]])
        return out
    }
    function setFan(fan) {
        if (fan && fan.curve && fan.curve.length) {
            curveOn = true
            sensor = fan.sensor || "edge"
            pts = copy(fan.curve)
        } else {
            curveOn = false
            sensor = "edge"
            pts = copy(example)
        }
        editor.selected = -1
    }
    function loadDefaults() { setFan(null) }
    function loadProfile(p) { setFan(p ? p.fan : null) }
    function loadCurrent() { setFan(Fmt.get(backend.status, ["settings", "fan"], null)) }
    // Empty object = automatic
    function fanValue() { return curveOn ? { sensor: sensor, curve: copy(pts) } : ({}) }

    implicitHeight: 360

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            Text { text: qsTr("Fan"); color: Theme.redSoft; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 2; font.capitalization: Font.AllUppercase }
            Item { Layout.fillWidth: true }
            Text {
                text: f.curveOn ? qsTr("Custom curve") : qsTr("Automatic (driver)")
                color: f.curveOn ? "white" : Theme.textDim
                font.pixelSize: Theme.fsSmall; font.weight: Font.DemiBold
            }
            GlowSwitch {
                enabled: f.supported
                checked: f.curveOn
                onToggled: (v) => f.curveOn = v
            }
        }

        Text {
            Layout.fillWidth: true
            visible: !f.supported
            text: qsTr("Fan control is not available on this system (pwm1 is missing).")
            color: Theme.redError; font.pixelSize: Theme.fsSmall; wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            visible: f.supported
            spacing: 12
            HelpLabel {
                text: qsTr("Sensor")
                hint: qsTr("<b>Which temperature the fan curve uses.</b> Hover over the options for details.")
            }
            ChoiceRow {
                enabled: f.curveOn
                opacity: enabled ? 1 : 0.45
                kind: "sensor"
                options: Fmt.get(f.info, ["sensors"], ["edge", "junction", "mem"])
                current: f.sensor
                onPicked: (v) => f.sensor = v
            }
            Item { Layout.fillWidth: true }
            GlowButton {
                compact: true; text: qsTr("Remove point")
                enabled: f.curveOn && editor.selected >= 0 && f.pts.length > editor.minPoints
                onClicked: editor.removeSelected()
            }
            GlowButton {
                compact: true; text: qsTr("Starting curve")
                enabled: f.curveOn
                onClicked: { f.pts = f.copy(f.example); editor.selected = -1 }
            }
        }

        FanCurveEditor {
            id: editor
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 190
            visible: f.supported
            editable: f.curveOn
            points: f.pts
            tempNow: f.tempNow
            minPoints: Fmt.get(f.info, ["points", 0], 2)
            maxPoints: Fmt.get(f.info, ["points", 1], 10)
            onEdited: (p) => f.pts = p
        }

        Text {
            Layout.fillWidth: true
            visible: f.supported
            text: f.ruleError !== "" ? f.ruleError
                  : (f.curveOn ? qsTr("Drag points, double-click adds one, Del removes the selected point. From %1 °C junction the fan always runs at 100 %.").arg(f.safetyC)
                               : qsTr("The driver controls the fan itself (quiet, usually off when idle)."))
            color: f.ruleError !== "" ? Theme.redError : Theme.textFaint
            font.pixelSize: Theme.fsSmall; wrapMode: Text.WordWrap
        }
    }
}
