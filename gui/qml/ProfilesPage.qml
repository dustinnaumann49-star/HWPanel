import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."
import "Fmt.js" as Fmt

Item {
    id: page
    signal requestNew()
    signal requestEdit(string name)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 18

        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 2
                Text { text: "Profile"; color: "white"; font.pixelSize: Theme.fsBig; font.weight: Font.DemiBold }
                Text { text: "Ein Profil legt den vollständigen Zustand fest: Alles, was nicht aufgeführt ist, wird auf Standard gesetzt."
                       color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
            }
            Item { Layout.fillWidth: true }
            GlowButton { primary: true; text: "+  Neues Profil"; onClicked: page.requestNew() }
        }

        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: flow.height + 50
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                contentItem: Rectangle { implicitWidth: 5; radius: 3; color: Theme.redDeep }
                background: Item {}
            }

            Flow {
                id: flow
                x: 0; y: 22
                width: flick.width - 12
                spacing: 28
                readonly property int cols: width > 980 ? 3 : 2

                Repeater {
                    model: backend.profileNames
                    Card {
                        id: pc
                        readonly property bool builtin: index === 0
                        readonly property var prof: builtin ? null : Fmt.get(backend.info, ["profiles", modelData], null)
                        property bool confirm: false
                        width: Math.floor((flow.width - flow.spacing * (flow.cols - 1) - 2) / flow.cols)
                        height: 262
                        active: modelData === backend.activeProfile

                        Timer { id: confirmTimer; interval: 3000; onTriggered: pc.confirm = false }

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 8
                            RowLayout {
                                Text { text: modelData; color: "white"; font.pixelSize: Theme.fsBig - 4; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Rectangle {
                                    visible: pc.active
                                    implicitWidth: badge.implicitWidth + 18; implicitHeight: 22; radius: 11
                                    color: Theme.redDeep; border.color: Theme.redLight; border.width: 1
                                    Text { id: badge; anchors.centerIn: parent; text: "AKTIV"; color: "white"; font.pixelSize: Theme.fsTiny; font.letterSpacing: 1.5; font.weight: Font.Bold }
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: pc.builtin ? "Alles auf Treiberstandard" : Fmt.describeGpu(pc.prof)
                                color: Theme.textDim; font.pixelSize: Theme.fsSmall + 1; wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: !pc.builtin
                                text: Fmt.describeCpu(pc.prof)
                                color: Theme.textDim; font.pixelSize: Theme.fsSmall + 1; wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: pc.builtin ? "Lüfter: Automatik (leise)" : Fmt.describeFan(pc.prof)
                                color: Theme.textDim; font.pixelSize: Theme.fsSmall + 1; wrapMode: Text.WordWrap
                            }
                            Item { Layout.fillHeight: true }
                            RowLayout {
                                Layout.fillWidth: true
                                visible: !pc.builtin
                                Text { text: "Beim Systemstart anwenden"; color: Theme.textFaint; font.pixelSize: Theme.fsSmall }
                                Item { Layout.fillWidth: true }
                                GlowSwitch {
                                    scale: 0.8
                                    checked: backend.startupProfile === modelData
                                    onToggled: (v) => backend.setStartupProfile(v ? modelData : "")
                                }
                            }
                            RowLayout {
                                spacing: 8
                                GlowButton { primary: !pc.active; active: pc.active; compact: true; text: pc.active ? "Erneut anwenden" : "Anwenden"; onClicked: backend.applyProfile(modelData) }
                                GlowButton { visible: !pc.builtin; compact: true; text: "Bearbeiten"; onClicked: page.requestEdit(modelData) }
                                Item { Layout.fillWidth: true }
                                GlowButton {
                                    visible: !pc.builtin
                                    compact: true
                                    text: pc.confirm ? "Wirklich löschen?" : "Löschen"
                                    textColor: pc.confirm ? Theme.redError : Theme.text
                                    onClicked: {
                                        if (pc.confirm) { backend.deleteProfile(modelData); pc.confirm = false }
                                        else { pc.confirm = true; confirmTimer.restart() }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
