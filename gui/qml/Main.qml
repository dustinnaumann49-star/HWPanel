import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: win
    width: 1240
    height: 800
    minimumWidth: 1040
    minimumHeight: 700
    visible: !backend.startMinimized
    title: "hwpanel"
    color: Theme.bg

    property int page: backend.startPage

    onClosing: (close) => {
        if (backend.trayAvailable) {
            close.accepted = false
            win.hide()
        }
    }

    // Hintergrund: Schwarz mit rotem Schimmer oben rechts und unten links
    Canvas {
        anchors.fill: parent
        z: -1
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var base = ctx.createLinearGradient(0, 0, 0, height)
            base.addColorStop(0, Theme.bgTop)
            base.addColorStop(1, Theme.bgBottom)
            ctx.fillStyle = base
            ctx.fillRect(0, 0, width, height)
            var big = Math.max(width, height)
            var a = ctx.createRadialGradient(width * 0.86, -40, 10, width * 0.86, -40, big * 0.75)
            a.addColorStop(0, Theme.rgba(Theme.red, 0.22))
            a.addColorStop(1, Theme.rgba(Theme.red, 0))
            ctx.fillStyle = a
            ctx.fillRect(0, 0, width, height)
            var b = ctx.createRadialGradient(width * 0.3, height + 60, 10, width * 0.3, height + 60, big * 0.65)
            b.addColorStop(0, Theme.rgba(Theme.redButtonBottom, 0.18))
            b.addColorStop(1, Theme.rgba(Theme.redButtonBottom, 0))
            ctx.fillStyle = b
            ctx.fillRect(0, 0, width, height)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.preferredWidth: 236
            Layout.fillHeight: true
            current: win.page
            onNavigate: (i) => win.page = i
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: win.page

            OverviewPage {}
            HistoryPage {}
            ProfilesPage {
                onRequestNew: profileDialog.openNew()
                onRequestEdit: (name) => profileDialog.openEdit(name)
            }
            ControlPage { objectName: "controlPage" }
        }
    }

    ProfileDialog { id: profileDialog; objectName: "profileDialog" }
    Toast { id: toast; objectName: "toast" }

    Connections {
        target: backend
        function onToast(text, isError) { if (text) toast.show(text, isError) }
    }
    // Sprachwechsel: alle qsTr()-Texte neu auswerten
    Connections {
        target: backend.language
        function onLanguageChanged() { backend.language.retranslate(win) }
    }
}
