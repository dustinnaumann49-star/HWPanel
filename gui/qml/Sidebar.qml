import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root
    property int current: 0
    signal navigate(int index)

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.sideTop }
            GradientStop { position: 1; color: Theme.sideBottom }
        }
    }
    // leuchtende Trennlinie
    Rectangle { anchors.right: parent.right; width: 6; height: parent.height; opacity: 0.10
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Theme.red } } }
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.rgba(Theme.red, 0.45) }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 8

        RowLayout {
            Layout.bottomMargin: 26
            spacing: 12
            Image { source: "../hwpanel.svg"; sourceSize.width: 44; sourceSize.height: 44; Layout.preferredWidth: 44; Layout.preferredHeight: 44 }
            ColumnLayout {
                spacing: 0
                Text { text: "HWPANEL"; color: "white"; font.pixelSize: Theme.fsMed; font.weight: Font.Bold; font.letterSpacing: 3
                    style: Text.Outline; styleColor: Theme.rgba(Theme.red, 0.35) }
                Text { text: "GPU · CPU · RAM"; color: Theme.textFaint; font.pixelSize: Theme.fsTiny; font.letterSpacing: 1 }
            }
        }

        Repeater {
            model: [qsTr("Overview"), qsTr("History"), qsTr("Profiles"), qsTr("Manual")]
            NavButton {
                Layout.fillWidth: true
                text: modelData
                active: root.current === index
                onClicked: root.navigate(index)
            }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Rectangle {
                width: 10; height: 10; radius: 5
                color: backend.connected ? "#ffffff" : Theme.red
                Rectangle { anchors.fill: parent; anchors.margins: -5; radius: width / 2; color: backend.connected ? "#ffffff" : Theme.red; opacity: 0.22; z: -1 }
            }
            Text {
                Layout.fillWidth: true
                text: backend.connected ? qsTr("Daemon connected") : qsTr("Daemon not reachable")
                color: backend.connected ? Theme.textDim : Theme.redError
                font.pixelSize: Theme.fsSmall
                elide: Text.ElideRight
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 6
            Text { text: qsTr("Language"); color: Theme.textDim; font.pixelSize: Theme.fsSmall }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: [{ code: "auto", label: qsTr("Auto"), hint: qsTr("Automatic (system language)") }].concat(
                        backend.language.languages.map(function (l) { return { code: l.code, label: l.code.toUpperCase(), hint: l.name } }))
                    GlowButton {
                        compact: true
                        text: modelData.label
                        hint: modelData.hint
                        active: backend.language.setting === modelData.code
                        onClicked: backend.language.setLanguage(modelData.code)
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Text { Layout.fillWidth: true; text: qsTr("Start at login"); color: Theme.textDim; font.pixelSize: Theme.fsSmall }
            GlowSwitch {
                implicitWidth: 42; implicitHeight: 22
                checked: backend.autostartEnabled
                onToggled: (v) => backend.setAutostart(v)
            }
        }
        GlowButton {
            Layout.fillWidth: true
            Layout.topMargin: 6
            compact: true
            text: qsTr("Quit")
            onClicked: backend.quit()
        }
    }
}
