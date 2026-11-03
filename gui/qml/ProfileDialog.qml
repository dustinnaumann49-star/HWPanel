import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Popup {
    id: dlg
    property string editName: ""
    property int tab: 0
    readonly property string nameError: backend.profileNameError(nameField.text, editName)
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: Math.min(880, (parent ? parent.width : 900) - 80)
    height: Math.min(730, (parent ? parent.height : 760) - 40)
    padding: 30
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140 } }

    function openNew() {
        editName = ""
        tab = 0
        nameField.text = ""
        form.loadDefaults()
        fanForm.loadDefaults()
        open()
        nameField.forceActiveFocus()
    }
    function openEdit(name, startTab) {
        editName = name
        tab = startTab || 0
        nameField.text = name
        var p = backend.info.profiles[name]
        form.loadProfile(p)
        fanForm.loadProfile(p)
        open()
    }

    Overlay.modal: Rectangle { color: "#d8030202" }
    background: Card { glow: 0.5; padding: 0 }

    contentItem: ColumnLayout {
        spacing: 14

        Text {
            text: dlg.editName ? qsTr("Edit profile") : qsTr("New profile")
            color: "white"; font.pixelSize: Theme.fsBig; font.weight: Font.DemiBold
        }
        TextField {
            id: nameField
            Layout.fillWidth: true
            placeholderText: qsTr("Profile name (e.g. Gaming, Quiet, Desktop)")
            placeholderTextColor: Theme.textFaint
            color: "white"
            font.pixelSize: Theme.fsMed
            selectByMouse: true
            maximumLength: 32
            leftPadding: 16; topPadding: 10; bottomPadding: 10
            background: Rectangle {
                radius: 14; color: Theme.field
                border.width: 1
                border.color: dlg.nameError !== "" ? Theme.redError : (nameField.activeFocus ? Theme.red : Theme.line)
            }
        }
        Text {
            Layout.fillWidth: true
            visible: dlg.nameError !== ""
            text: dlg.nameError
            color: Theme.redError; font.pixelSize: Theme.fsSmall
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            GlowButton { compact: true; text: qsTr("Clocks & CPU"); active: dlg.tab === 0; onClicked: dlg.tab = 0 }
            GlowButton { compact: true; text: qsTr("Fan"); active: dlg.tab === 1; onClicked: dlg.tab = 1 }
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                text: dlg.tab === 0 ? qsTr("Only values below the default are saved, everything else is set to default.")
                                    : qsTr("Without a custom curve the driver automatic controls the fan.")
                color: Theme.textFaint; font.pixelSize: Theme.fsTiny
                elide: Text.ElideRight
            }
        }
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: dlg.tab
            SettingsForm { id: form; Layout.fillWidth: true; Layout.alignment: Qt.AlignTop }
            FanForm { id: fanForm; Layout.fillWidth: true; Layout.fillHeight: true }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Item { Layout.fillWidth: true }
            GlowButton { text: qsTr("Cancel"); onClicked: dlg.close() }
            GlowButton {
                primary: true
                text: qsTr("Save")
                enabled: nameField.text.trim().length > 0 && dlg.nameError === "" && fanForm.ruleError === ""
                onClicked: {
                    backend.saveProfile(nameField.text.trim(), form.gpuValues(false), form.cpuValues(false),
                                        fanForm.fanValue(), dlg.editName)
                    dlg.close()
                }
            }
        }
    }
}
