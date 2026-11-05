// SPDX-License-Identifier: GPL-3.0-only
// Phone cover input only. Authentication is delegated to Lomiri's Greeter.
import QtQuick 2.15

MouseArea {
    id: root
    objectName: "uos27UnlockGesture"

    // A positive upward displacement is required. A tap also reveals the
    // native challenge for accessibility, just as the stock cover tap does.
    property real swipeDistance: 56
    property real tapSlop: 18
    property real startX: 0
    property real startY: 0
    property bool requestedDuringTouch: false

    signal unlockRequested()

    preventStealing: true

    onPressed: {
        startX = mouse.x;
        startY = mouse.y;
        requestedDuringTouch = false;
    }
    onPositionChanged: {
        if (!pressed || requestedDuringTouch)
            return;
        if (startY - mouse.y >= swipeDistance) {
            requestedDuringTouch = true;
            unlockRequested();
        }
    }
    onReleased: {
        // Short, fast gestures may not have delivered a position signal.
        if (!requestedDuringTouch && startY - mouse.y >= swipeDistance) {
            requestedDuringTouch = true;
            unlockRequested();
        }
    }
    onClicked: {
        if (!requestedDuringTouch && Math.abs(startX - mouse.x) <= tapSlop
                && Math.abs(startY - mouse.y) <= tapSlop) {
            requestedDuringTouch = true;
            unlockRequested();
        }
    }
}
