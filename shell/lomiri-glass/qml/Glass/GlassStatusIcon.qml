// SPDX-License-Identifier: GPL-3.0-only
// Compact original vector status glyphs. Classification uses the *native*
// Ayatana icon name: unknown/ambiguous states fall back to Lomiri's icon.
import QtQuick 2.15

Item {
    id: root
    property string iconSource: ""
    property color tint: "#ffffff"
    readonly property string canonical: String(iconSource).toLowerCase().split(",")[0]
    readonly property string kind: {
        var name = canonical;
        if (/indicator-messages(-new)?(?:\b|$)|messages-new/.test(name)) return "messages";
        if (/battery-(?:[0-9]{3}|empty|low|good|medium|full|caution|charging|fully-charged)/.test(name)) return "battery";
        // Lomiri's actual network indicator commonly supplies nm-signal-NN
        // names, not wifi-high. Missing this family hid real Wi-Fi on the S10+.
        if (/(?:wifi-(?:none|low|medium|high|full|excellent|good|weak|disconnected)|nm-signal-(?:00|25|50|75|100)(?:-secure)?|network-wireless-signal-(?:none|weak|ok|good|excellent))/.test(name)) return "wifi";
        if (/(?:cellular|mobile|gsm)-signal-(?:none|low|medium|high|excellent|good|weak|full)/.test(name)) return "cellular";
        if (/bluetooth-(?:active|enabled|disabled|inactive|symbolic)/.test(name)) return "bluetooth";
        if (/(?:airplane-mode|airplane-symbolic)/.test(name)) return "airplane";
        if (/audio-volume-(?:muted|low|medium|high|zero|off)/.test(name)) return "sound";
        return "native";
    }
    readonly property bool supported: kind !== "native"
    readonly property bool unread: kind === "messages" && /(?:indicator-messages-new|messages-new)/.test(canonical)
    readonly property bool charging: kind === "battery" && /charging/.test(canonical) && !/fully-charged/.test(canonical)
    readonly property int batteryLevel: {
        var match = canonical.match(/battery-([0-9]{3})/);
        if (match) return Math.max(0, Math.min(100, Number(match[1])));
        if (/empty/.test(canonical)) return 4;
        if (/low|caution/.test(canonical)) return 18;
        if (/medium/.test(canonical)) return 50;
        if (/good/.test(canonical)) return 75;
        return 100;
    }
    readonly property int strength: {
        var wifiLevel = canonical.match(/nm-signal-(00|25|50|75|100)/);
        if (wifiLevel) return wifiLevel[1] === "00" ? 0
            : wifiLevel[1] === "25" ? 1
            : wifiLevel[1] === "50" ? 2 : 3;
        if (/(?:none|disconnected|muted|off|zero)/.test(canonical)) return 0;
        if (/(?:low|weak)/.test(canonical)) return 1;
        if (/medium/.test(canonical)) return 2;
        return 3;
    }

    onKindChanged: drawing.requestPaint()
    onIconSourceChanged: drawing.requestPaint()
    onTintChanged: drawing.requestPaint()

    Canvas {
        id: drawing
        anchors.fill: parent
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext("2d");
            c.reset();
            c.scale(width / 24, height / 24);
            c.strokeStyle = root.tint;
            c.fillStyle = root.tint;
            c.lineWidth = 1.85;
            c.lineCap = "round";
            c.lineJoin = "round";
            function line(coords) {
                c.beginPath(); c.moveTo(coords[0][0], coords[0][1]);
                for (var n = 1; n < coords.length; n++) c.lineTo(coords[n][0], coords[n][1]);
                c.stroke();
            }
            function dot(x, y, r) {
                c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
            }
            if (root.kind === "messages") {
                c.beginPath(); c.moveTo(5, 17); c.lineTo(7, 14); c.lineTo(7, 9);
                c.bezierCurveTo(7, 2.4, 17, 2.4, 17, 9);
                c.lineTo(17, 14); c.lineTo(19, 17); c.closePath(); c.stroke();
                c.beginPath(); c.arc(12, 18.5, 2, 0, Math.PI); c.stroke();
                if (root.unread) {
                    c.fillStyle = "#59b9ff";
                    dot(19.8, 5.0, 3.3);
                }
            } else if (root.kind === "battery") {
                c.lineWidth = 1.45;
                c.strokeRect(2.1, 6, 18.6, 12);
                c.fillRect(21.5, 10, 1.7, 4);
                c.fillStyle = root.charging ? "#4ad987" : root.batteryLevel <= 20 ? "#ff6672" : root.tint;
                c.fillRect(4.1, 8, 14.6 * root.batteryLevel / 100, 8);
                if (root.charging) {
                    c.strokeStyle = "#142c2c";
                    c.lineWidth = 2;
                    line([[13, 7], [10, 12], [13.1, 12], [11, 17]]);
                }
            } else if (root.kind === "wifi") {
                for (var w = 3; w >= 1; w--) {
                    if (w > root.strength) continue;
                    var r = 3 + 4.4 * (w - 1);
                    c.beginPath(); c.arc(12, 20, r, Math.PI * 1.25, Math.PI * 1.75); c.stroke();
                }
                dot(12, 20, 1.2);
                if (root.strength === 0) line([[5, 4], [19, 20]]);
            } else if (root.kind === "cellular") {
                for (var b = 0; b < 4; b++) {
                    // "none" must never render a solid bar suggesting service.
                    var activeBars = root.strength === 3 ? 4 : root.strength;
                    c.globalAlpha = b < activeBars ? 1 : 0.22;
                    c.fillRect(2 + b * 5.3, 21 - (5 + b * 4), 3.5, 5 + b * 4);
                }
                c.globalAlpha = 1;
            } else if (root.kind === "bluetooth") {
                line([[6, 7], [17, 17], [12, 22], [12, 2], [17, 7], [6, 17]]);
                if (/disabled|inactive/.test(root.canonical)) line([[3, 3], [21, 21]]);
            } else if (root.kind === "airplane") {
                c.beginPath();
                c.moveTo(11, 2); c.lineTo(13, 2); c.lineTo(14, 9);
                c.lineTo(21, 14); c.lineTo(21, 16); c.lineTo(14, 13);
                c.lineTo(14, 18); c.lineTo(17, 20); c.lineTo(17, 22);
                c.lineTo(12, 20.5); c.lineTo(7, 22); c.lineTo(7, 20);
                c.lineTo(10, 18); c.lineTo(10, 13); c.lineTo(3, 16);
                c.lineTo(3, 14); c.lineTo(10, 9); c.closePath(); c.fill();
            } else if (root.kind === "sound") {
                c.beginPath(); c.moveTo(3, 9); c.lineTo(7, 9); c.lineTo(12, 5);
                c.lineTo(12, 19); c.lineTo(7, 15); c.lineTo(3, 15); c.closePath(); c.fill();
                if (root.strength === 0) line([[15, 7], [21, 17]]);
                else for (var s = 0; s < root.strength - 1; s++) {
                    c.beginPath(); c.arc(11, 12, 6 + s * 4, -0.8, 0.8); c.stroke();
                }
            }
        }
    }
}
