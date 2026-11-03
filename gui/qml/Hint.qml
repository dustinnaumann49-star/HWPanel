import QtQuick
import QtQuick.Controls.Basic
import "."

// Erklärung beim Darüberfahren, im Stil der Oberfläche. Der Besitzer setzt `wanted`,
// gezeigt wird mit kurzer Verzögerung unter dem Elternelement (oder darüber, wenn unten kein Platz ist).
ToolTip {
    id: tip
    property bool wanted: false

    contentWidth: 300
    padding: 14
    margins: 12
    timeout: -1
    closePolicy: Popup.NoAutoClose

    onWantedChanged: {
        if (wanted) {
            delay.restart()
        } else {
            delay.stop()
            close()
        }
    }
    onAboutToShow: {
        x = Math.round((parent.width - width) / 2)
        var top = parent.mapToItem(Overlay.overlay, 0, 0).y
        y = (top + parent.height + 8 + height + margins > Overlay.overlay.height) ? -height - 8 : parent.height + 8
    }

    Timer { id: delay; interval: 350; onTriggered: if (tip.wanted && tip.text !== "") tip.open() }

    contentItem: Text {
        width: tip.availableWidth
        text: tip.text
        textFormat: Text.StyledText
        wrapMode: Text.WordWrap
        color: Theme.text
        font.pixelSize: Theme.fsSmall
        lineHeight: 1.12
    }
    background: Rectangle {
        radius: 12
        color: "#1c0a0a"
        border.width: 1
        border.color: Theme.redDeep
    }
}
