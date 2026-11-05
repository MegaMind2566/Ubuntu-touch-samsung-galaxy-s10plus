// SPDX-License-Identifier: GPL-3.0-only
// Desktop fixture only. No D-Bus services or handset notification history.
import QtQuick 2.15
import "../qml/Glass" as Glass

Rectangle {
    id: preview
    width: 412
    height: 915
    // Desktop fixture only: a contrasting fake Home wallpaper UNDER the
    // transparent panel. Production loads the real Lomiri scene behind it.
    color: "#071b49"
    gradient: Gradient {
        GradientStop { position: 0; color: "#194f99" }
        GradientStop { position: 0.48; color: "#102d6b" }
        GradientStop { position: 1; color: "#061634" }
    }

    Glass.GlassCenter {
        id: center
        objectName: "glassCenter"
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            bottom: previewLabel.top
        }
        backend: mockBackend
        gu: 8
        // This screenshot fixture uses Italian; production reads i18n.language.
        language: "it_IT"
        reducedMotion: true
        onViewSelected: {
            mode = view
            detailActive = false
        }
        onNativePageRequested: {
            detailTitle = identifier
            detailActive = true
        }
        onCloseRequested: preview.closeCount += 1
    }
    property int closeCount: 0

    // The production integration reparents Lomiri's existing MenuContent here.
    // This fixture intentionally does not invent notification history.
    Text {
        parent: center.nativeContentHost
        anchors.centerIn: parent
        width: parent.width - 48
        text: "Area riservata al pannello nativo di Lomiri.\nLe notifiche del telefono non sono caricate in questa anteprima."
        color: "#c4cede"
        font.pixelSize: 16
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        lineHeight: 1.35
    }
    Text {
        id: previewLabel
        objectName: "previewLabel"
        height: 28
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        text: "ANTEPRIMA QT · STATI E SFONDO SIMULATI"
        color: "#bcc9df"
        font.pixelSize: 10
        font.letterSpacing: 1
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
    }
}
