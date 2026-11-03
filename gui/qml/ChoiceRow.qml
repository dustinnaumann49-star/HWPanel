import QtQuick
import "."

Flow {
    id: root
    property var options: []
    property string current: ""
    signal picked(string value)
    spacing: 8

    Repeater {
        model: root.options
        GlowButton {
            compact: true
            text: modelData
            active: modelData === root.current
            onClicked: root.picked(modelData)
        }
    }
}
