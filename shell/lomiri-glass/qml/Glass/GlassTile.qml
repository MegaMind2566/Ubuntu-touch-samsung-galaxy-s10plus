// SPDX-License-Identifier: GPL-3.0-only
import QtQuick 2.15
import "GlassStrings.js" as Strings

FocusScope {
    id: root
    property real gu: 8
    property string title: ""
    property string subtitle: ""
    property string iconName: "settings"
    property color accent: "#2088ff"
    property bool checked: false
    property bool available: false
    property bool highContrast: false
    property bool lightSurface: false
    property string language: "en"
    property bool reducedMotion: true
    // Compact connectivity rows and small utility squares share one native
    // activation path. Their arrangement is purely presentational.
    property bool compact: true
    property bool iconOnly: false
    signal activated()
    signal detailRequested()
    implicitWidth: gu * (iconOnly ? 9 : compact ? 20 : 12)
    implicitHeight: gu * (iconOnly ? 9 : compact ? 11.5 : 12)
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: title + ", " + subtitle
    Accessible.description: available
        ? Strings.tr("Tap to toggle. Touch and hold for details.", root.language)
        : Strings.tr("Control unavailable. Touch and hold for details.", root.language)
    Accessible.onPressAction: requestActivation()
    Keys.onSpacePressed: requestActivation()
    Keys.onReturnPressed: requestActivation()
    Keys.onEnterPressed: requestActivation()
    Keys.onMenuPressed: detailRequested()

    function requestActivation() {
        if (root.available && root.enabled)
            root.activated();
    }

    // uOS27's tactile press feedback uses scale only. It avoids recursive
    // ShaderEffect blur or an additional offscreen layer on the Mali GPU.
    transform: Scale {
        origin.x: root.width / 2
        origin.y: root.height / 2
        xScale: mouse.pressed && !root.reducedMotion ? 0.968 : 1.0
        yScale: xScale
        Behavior on xScale {
            enabled: !root.reducedMotion
            NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
        }
        Behavior on yScale {
            enabled: !root.reducedMotion
            NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: root.iconOnly ? root.gu * 2.2 : root.gu * 3.2
        color: root.highContrast ? "#303c5c"
               : root.iconOnly ? (mouse.pressed ? "#38567ea6" : "transparent")
               : (mouse.pressed ? "#a03d649c" : "#76405e88")
        border.width: root.activeFocus ? 2 : root.iconOnly ? 0 : 1
        border.color: root.activeFocus ? "#b0dbff" : "#80929dc9"
    }

    Rectangle {
        id: iconDisc
        x: root.iconOnly ? (root.width - width) / 2 : root.compact ? root.gu * 1.4 : (root.width - width) / 2
        // Small Control Center tiles follow the icon-only treatment: captions
        // remain available to accessibility but do not consume visual space.
        y: root.iconOnly ? (root.height - height) / 2 : root.compact ? (root.height - height) / 2 : root.gu * 1.65
        width: root.iconOnly ? Math.min(root.width - root.gu * 1.6, root.gu * 6.2) : root.gu * 5.3
        height: width
        radius: width / 2
        color: root.checked ? root.accent : root.iconOnly ? "#64576d95" : "#5c4d688f"
        opacity: root.available ? 1 : 0.57
        Behavior on color { enabled: !root.reducedMotion; ColorAnimation { duration: 120 } }
        GlassIcon {
            anchors.centerIn: parent
            width: root.gu * (root.iconOnly ? 3.0 : 3.15)
            height: width
            name: root.iconName
            color: "#ffffff"
        }
    }

    GlassIcon {
        anchors.right: parent.right
        anchors.rightMargin: root.gu * 1.0
        anchors.verticalCenter: root.compact ? parent.verticalCenter : undefined
        anchors.top: root.compact ? undefined : parent.top
        anchors.topMargin: root.gu * 2.4
        width: root.gu * (root.compact ? 1.6 : 1.4)
        height: width
        name: "chevron"
        color: "#f1efff"
        opacity: root.iconOnly ? 0 : root.compact ? 0.75 : 0
    }

    Column {
        visible: !root.iconOnly
        anchors.left: root.iconOnly ? parent.left : root.compact ? iconDisc.right : parent.left
        anchors.right: parent.right
        anchors.verticalCenter: root.iconOnly ? undefined : root.compact ? parent.verticalCenter : undefined
        anchors.bottom: root.iconOnly || !root.compact ? parent.bottom : undefined
        anchors.leftMargin: root.iconOnly ? root.gu * 0.15 : root.compact ? root.gu * 0.85 : root.gu * 0.8
        anchors.rightMargin: root.iconOnly ? root.gu * 0.15 : root.compact ? root.gu * 2.6 : root.gu * 0.8
        anchors.bottomMargin: root.iconOnly ? root.gu * 0.6 : root.gu * 1.05
        spacing: root.gu * 0.38
        Text {
            width: parent.width
            text: root.title
            color: "#ffffff"
            font.pixelSize: root.gu * (root.iconOnly ? 1.30 : root.compact ? 1.65 : 1.55)
            font.weight: Font.DemiBold
            elide: Text.ElideRight
            textFormat: Text.PlainText
            horizontalAlignment: root.iconOnly ? Text.AlignHCenter : root.compact ? Text.AlignLeft : Text.AlignHCenter
        }
        Text {
            width: parent.width
            visible: !root.iconOnly
            text: root.subtitle
            color: root.available ? "#e3e1f4" : "#bbc5db"
            font.pixelSize: root.gu * (root.compact ? 1.45 : 1.25)
            elide: Text.ElideRight
            textFormat: Text.PlainText
            horizontalAlignment: root.compact ? Text.AlignLeft : Text.AlignHCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        property bool held: false
        onPressed: { held = false; root.forceActiveFocus(); }
        onPressAndHold: { held = true; root.detailRequested(); }
        onClicked: { if (!held) root.requestActivation(); }
    }
}
