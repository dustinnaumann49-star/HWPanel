import QtQuick
import "."
import "Fmt.js" as Fmt

Flow {
    id: root
    property var options: []
    property string current: ""
    property string kind: ""      // "epp", "governor" oder "sensor": welche Erklärungen beim Darüberfahren erscheinen
    property string driver: ""    // CPU-Treiber (für treiberabhängige Erklärungen)
    signal picked(string value)
    spacing: 8

    Repeater {
        model: root.options
        GlowButton {
            compact: true
            text: modelData
            hint: Fmt.optionHint(root.kind, modelData, root.driver)   // qsTr() steckt in Fmt.js
            active: modelData === root.current
            onClicked: root.picked(modelData)
        }
    }
}
