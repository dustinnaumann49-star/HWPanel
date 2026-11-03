import QtQuick
import QtQuick.Controls.Basic
import "."

Item {
    id: root
    property string title: ""
    property string unit: ""
    property string note: ""
    property real from: 0
    property real to: 100
    property real value: 0
    property real stepSize: 1
    signal moved(real v)

    implicitHeight: 62
    implicitWidth: 280
    opacity: enabled ? 1 : 0.4

    Text {
        id: head
        text: root.title
        color: Theme.textDim
        font.pixelSize: Theme.fsTiny
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
    }
    Text {
        anchors.right: parent.right
        text: Math.round(root.value) + " " + root.unit + (root.note ? "   " + root.note : "")
        color: Theme.text
        font.pixelSize: Theme.fsBase
        font.weight: Font.DemiBold
    }
    Slider {
        id: s
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: head.bottom; anchors.topMargin: 8
        height: 28
        from: root.from
        to: Math.max(root.to, root.from + 1)
        stepSize: root.stepSize
        snapMode: Slider.SnapAlways
        onMoved: root.moved(value)

        background: Item {
            x: s.leftPadding
            y: s.topPadding + s.availableHeight / 2 - 3
            width: s.availableWidth
            height: 6
            Rectangle { anchors.fill: parent; radius: 3; color: Theme.field; border.color: Theme.fieldBorder; border.width: 1 }
            Rectangle {
                width: Math.max(6, s.visualPosition * parent.width); height: parent.height; radius: 3
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.redDeep }
                    GradientStop { position: 1; color: Theme.red }
                }
            }
        }
        handle: Item {
            x: s.leftPadding + s.visualPosition * (s.availableWidth - width)
            y: s.topPadding + s.availableHeight / 2 - height / 2
            width: 22; height: 22
            Rectangle { anchors.fill: parent; anchors.margins: -6; radius: width / 2; color: Theme.red; opacity: s.pressed ? 0.38 : 0.2 }
            Rectangle { anchors.fill: parent; radius: width / 2; color: "#fff0f0"; border.color: Theme.red; border.width: 2 }
        }
    }
    Binding { target: s; property: "value"; value: root.value; when: !s.pressed }
}
