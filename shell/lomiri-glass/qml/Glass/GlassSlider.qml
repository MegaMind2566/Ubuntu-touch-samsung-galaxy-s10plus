// SPDX-License-Identifier: GPL-3.0-only
import QtQuick 2.15
import "GlassStrings.js" as Strings

FocusScope {
    id: root
    property real gu: 8
    property string title: ""
    property string iconName: "sun"
    property real value: 0
    property bool available: false
    property bool automatic: false
    property bool reducedMotion: true
    property bool highContrast: false
    property bool lightSurface: false
    property string language: "en"
    readonly property bool dragging: touch.pressed && interaction.gestureValid
    readonly property real displayedValue: dragging ? interaction.userValue : clamp(value)
    signal valueRequested(real value)
    signal detailRequested()
    implicitWidth: gu * 12
    implicitHeight: gu * 27
    activeFocusOnTab: true
    Accessible.role: Accessible.Slider
    Accessible.name: title
    Accessible.description: automatic ? Strings.tr("Automatic adjustment", root.language)
        : !available ? Strings.tr("Unavailable", root.language) : Math.round(displayedValue * 100) + "%"
    Accessible.onIncreaseAction: requestStep(0.05)
    Accessible.onDecreaseAction: requestStep(-0.05)
    Keys.onUpPressed: requestStep(0.05)
    Keys.onRightPressed: requestStep(0.05)
    Keys.onDownPressed: requestStep(-0.05)
    Keys.onLeftPressed: requestStep(-0.05)
    Keys.onMenuPressed: detailRequested()

    function clamp(v) {
        return typeof v === "number" && isFinite(v) ? Math.max(0, Math.min(1, v)) : 0;
    }
    function requestStep(delta) {
        if (root.available && !root.automatic && root.enabled)
            root.valueRequested(clamp(root.value + delta));
    }
    // A native policy decision (for example a rejected high-volume request)
    // terminates this gesture. Subsequent move/release events from the same
    // physical press must not resend its stale value.
    function cancelInteraction() {
        sendTimer.stop();
        interaction.gestureValid = false;
        interaction.userValue = clamp(root.value);
    }
    function updateFromTouch(y) {
        if (!interaction.gestureValid)
            return;
        interaction.userValue = clamp(1 - y / track.height);
        if (!sendTimer.running)
            sendTimer.start();
    }
    QtObject {
        id: interaction
        property real userValue: 0
        property bool gestureValid: false
    }
    Timer {
        id: sendTimer
        interval: 60
        repeat: false
        onTriggered: {
            if (root.available && !root.automatic && touch.pressed && root.enabled
                    && interaction.gestureValid)
                root.valueRequested(interaction.userValue);
        }
    }
    onAvailableChanged: { if (!available) cancelInteraction(); }
    onAutomaticChanged: { if (automatic) cancelInteraction(); }
    onEnabledChanged: { if (!enabled) cancelInteraction(); }
    onVisibleChanged: { if (!visible) cancelInteraction(); }

    Rectangle {
        id: track
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(root.gu * 6, root.width - root.gu * 0.55)
        height: root.height - root.gu * 0.6
        radius: root.gu * 3.3
        clip: true
        // Both controls have the same neutral glass treatment. Color alone
        // never suggests a different percentage or hardware state.
        color: root.highContrast ? "#233a60" : "#89526c95"
        opacity: root.available || root.automatic ? 1 : 0.55
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? "#a9d3ff" : "#b1acb8d2"

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 2
            height: Math.max(0, (parent.height - 4) * root.displayedValue)
            radius: Math.min(root.gu * 3.0, height / 2)
            color: root.highContrast ? "#f8faff" : "#dfe8f6"
            // Smooth external brightness/volume state changes, but track the
            // user's finger without lag and never invent a new value.
            Behavior on height {
                enabled: !root.reducedMotion && !root.dragging
                NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
            }
        }
        GlassIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: root.gu * 2.2
            width: root.gu * 3.0
            height: width
            name: root.iconName
            color: root.displayedValue > 0.22 ? "#26324e" : "#ffffff"
        }
        MouseArea {
            id: touch
            anchors.fill: parent
            enabled: root.available && !root.automatic
            preventStealing: true
            onPressed: {
                interaction.gestureValid = root.available && !root.automatic && root.enabled;
                root.forceActiveFocus();
                root.updateFromTouch(mouse.y);
            }
            onPositionChanged: { if (pressed && interaction.gestureValid) root.updateFromTouch(mouse.y); }
            onReleased: {
                sendTimer.stop();
                var requestedValue = interaction.userValue;
                var send = interaction.gestureValid && root.available
                        && !root.automatic && root.enabled;
                interaction.gestureValid = false;
                if (send)
                    root.valueRequested(requestedValue);
            }
            onCanceled: root.cancelInteraction()
        }
    }
}
