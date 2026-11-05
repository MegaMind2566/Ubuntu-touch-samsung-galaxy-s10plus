// SPDX-License-Identifier: GPL-3.0-only
// Desktop presentation fixture. The installed shell keeps its native LightDM
// challenge, AppDrawerModel, notification model and system-service backend.
import QtQuick 2.15
import "Glass" as Glass

Rectangle {
    id: root
    objectName: "uos27ShellPreview"
    width: 412; height: 870
    color: "#081c38"
    property string surface: "home"
    property bool challengeRequested: false
    property string launchRequest: ""
    property int _startY: 0
    property int _startX: 0
    readonly property real cameraReservedFraction: 0.27
    function requestUnlock() { challengeRequested = true; }
    function showSurface(value) {
        surface = value;
        challengeRequested = false;
    }

    // Original desktop-only wallpaper: production retains the real wallpaper.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#76c5ed" }
            GradientStop { position: 0.44; color: "#326ec1" }
            GradientStop { position: 1; color: "#092645" }
        }
    }
    Canvas {
        anchors.fill: parent
        onPaint: {
            var c = getContext("2d"); c.reset();
            c.scale(width / 412, height / 870);
            var g = c.createLinearGradient(0, 120, 330, 830);
            g.addColorStop(0, "#b5e1e7"); g.addColorStop(0.43, "#5baddc"); g.addColorStop(1, "#124c85");
            c.fillStyle = g; c.beginPath(); c.moveTo(-80, -90);
            c.bezierCurveTo(390, 45, 130, 405, 500, 610);
            c.bezierCurveTo(170, 900, -100, 700, -90, 900);
            c.closePath(); c.fill();
            c.strokeStyle = "#99d6ec"; c.lineWidth = 2;
            c.beginPath(); c.moveTo(-40, -30); c.bezierCurveTo(390, 65, 80, 390, 500, 600); c.stroke();
        }
    }

    // Common status line leaves space for the S10+ camera area.
    Item {
        id: status
        height: 48; width: parent.width; z: 10
        Text {
            x: 24; y: 17; text: "9:41"; color: "white"
            font.pixelSize: 16; font.weight: Font.DemiBold
        }
        Row {
            objectName: "previewStatusIcons"
            x: parent.width * (1 - root.cameraReservedFraction) - width - 10
            y: 18; spacing: 7
            Glass.GlassIcon { name: "mobile"; width: 18; height: 18 }
            Glass.GlassIcon { name: "wifi"; width: 18; height: 18 }
            Glass.GlassIcon { name: "battery"; width: 23; height: 18 }
        }
        MouseArea {
            anchors.fill: parent
            onPressed: { root._startY = mouse.y; root._startX = mouse.x; }
            onPositionChanged: {
                if (pressed && mouse.y - root._startY > 35)
                    root.showSurface(root._startX > width * 0.56 ? "controls" : "notifications");
            }
            onReleased: {
                if (mouse.y - root._startY > 35)
                    root.showSurface(root._startX > width * 0.56 ? "controls" : "notifications");
            }
        }
    }

    Glass.GlassHome {
        id: home
        objectName: "previewNativeHome"
        anchors { fill: parent; topMargin: status.height; bottomMargin: 26 }
        visible: root.surface === "home"
        language: "it_IT"
        reducedMotion: true
        onApplicationSelected: root.launchRequest = appId
    }

    Item {
        id: lockCover
        objectName: "previewLockCover"
        anchors { fill: parent; topMargin: status.height; bottomMargin: 26 }
        visible: root.surface === "lock"
        Glass.GlassIcon { name: "lock"; width: 25; height: 25; y: 29; anchors.horizontalCenter: parent.horizontalCenter }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter; y: 69
            text: "Giovedì 5 novembre"; color: "white"; font.pixelSize: 21; font.weight: Font.Medium
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter; y: 94
            text: "9:41"; color: "white"; font.pixelSize: Math.min(root.width * 0.23, 100)
            font.weight: Font.Light; font.letterSpacing: -4
        }
        Glass.GlassUnlockGesture {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: parent.height * 0.56
            onUnlockRequested: root.requestUnlock()
        }
        Text {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; bottomMargin: 54; margins: 27 }
            text: root.challengeRequested ? "Il prompt LightDM resta responsabile dello sblocco.\nNessun PIN viene richiesto nell’anteprima." : "Scorri verso l’alto per sbloccare"
            color: "white"; horizontalAlignment: Text.AlignHCenter
            font.pixelSize: 14; wrapMode: Text.WordWrap
        }
    }

    Glass.GlassCenter {
        id: center
        objectName: "previewNativeCenter"
        anchors { fill: parent; topMargin: status.height; bottomMargin: 26 }
        visible: root.surface === "controls" || root.surface === "notifications"
        mode: root.surface === "notifications" ? "notifications" : "controls"
        backend: mockBackend; language: "it_IT"; reducedMotion: true
        onViewSelected: root.surface = view
        onCloseRequested: root.showSurface("home")
        onNativePageRequested: { detailActive = true; detailTitle = identifier; }
    }
    Column {
        parent: center.nativeContentHost
        width: parent.width - 56; anchors.centerIn: parent
        spacing: 14
        Glass.GlassIcon { width: 40; height: 40; name: "bell"; anchors.horizontalCenter: parent.horizontalCenter }
        Text {
            width: parent.width; color: "white"; font.pixelSize: 22; font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            text: center.detailActive ? "Pannello nativo di sistema" : "Nessuna notifica nell’anteprima"
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width; color: "#d9e8f6"; font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            text: "Sul telefono viene riutilizzato il modello di Lomiri.\nNessun messaggio personale o stato hardware è inventato."
        }
    }

    Item {
        objectName: "previewNativeSwitcher"
        anchors.fill: parent; visible: root.surface === "switcher"
        Rectangle { anchors.fill: parent; color: "#b5192945" }
        Text { anchors.centerIn: parent; text: "Nessuna app aperta nell’anteprima"; color: "white"; font.pixelSize: 18 }
    }

    Rectangle {
        z: 20; width: 124; height: 5; radius: 3; color: "white"
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 37 }
        MouseArea {
            anchors { fill: parent; margins: -17 }
            onClicked: { if (root.surface === "lock") root.requestUnlock(); else root.showSurface("home"); }
            onPressAndHold: { if (root.surface !== "lock") root.showSurface("switcher"); }
        }
    }
    Rectangle {
        z: 30; height: 26; color: "#ed10243d"; anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        Text {
            anchors.centerIn: parent; text: "ANTEPRIMA QT · CATALOGO, ORA E SFONDO DIMOSTRATIVI"
            color: "#e1ecf9"; font.pixelSize: 9
        }
    }
}
