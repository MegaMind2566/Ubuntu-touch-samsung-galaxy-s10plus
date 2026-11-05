// SPDX-License-Identifier: GPL-3.0-only
// Original vector artwork; no Apple assets or font dependencies.
import QtQuick 2.15

Canvas {
    id: root
    property string name: "settings"
    property color color: "white"
    property real strokeWidth: 1.8
    implicitWidth: 24
    implicitHeight: 24
    antialiasing: true
    onNameChanged: requestPaint()
    onColorChanged: requestPaint()
    onStrokeWidthChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var c = getContext("2d");
        c.reset();
        c.scale(width / 24, height / 24);
        c.strokeStyle = root.color;
        c.fillStyle = root.color;
        c.lineWidth = root.strokeWidth;
        c.lineCap = "round";
        c.lineJoin = "round";
        function line(points) {
            c.beginPath();
            c.moveTo(points[0][0], points[0][1]);
            for (var i = 1; i < points.length; ++i)
                c.lineTo(points[i][0], points[i][1]);
            c.stroke();
        }
        function circle(x, y, r, fill) {
            c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI);
            if (fill) c.fill(); else c.stroke();
        }
        switch (root.name) {
        case "wifi":
            c.beginPath(); c.arc(12, 20, 15, Math.PI * 1.25, Math.PI * 1.75); c.stroke();
            c.beginPath(); c.arc(12, 20, 10, Math.PI * 1.25, Math.PI * 1.75); c.stroke();
            c.beginPath(); c.arc(12, 20, 5, Math.PI * 1.25, Math.PI * 1.75); c.stroke();
            circle(12, 20, 1.1, true); break;
        case "bluetooth":
            line([[6, 7], [17, 17], [12, 22], [12, 2], [17, 7], [6, 17]]); break;
        case "airplane":
            c.beginPath();
            c.moveTo(11, 2); c.lineTo(13, 2); c.lineTo(14, 9);
            c.lineTo(21, 14); c.lineTo(21, 16); c.lineTo(14, 13);
            c.lineTo(14, 18); c.lineTo(17, 20); c.lineTo(17, 22);
            c.lineTo(12, 20.5); c.lineTo(7, 22); c.lineTo(7, 20);
            c.lineTo(10, 18); c.lineTo(10, 13); c.lineTo(3, 16);
            c.lineTo(3, 14); c.lineTo(10, 9); c.closePath(); c.fill(); break;
        case "mobile":
            for (var b = 0; b < 4; ++b) {
                var barHeight = 4 + b * 4;
                c.fillRect(3 + b * 5, 21 - barHeight, 3, barHeight);
            }
            break;
        case "moon":
            c.beginPath(); c.moveTo(17.7, 4.1);
            c.bezierCurveTo(13, 2, 7.7, 4.6, 6, 9);
            c.bezierCurveTo(3, 17, 11, 24, 18.1, 19.2);
            c.bezierCurveTo(12.1, 18.6, 9.6, 11.2, 13.2, 6.7);
            c.bezierCurveTo(14.3, 5.4, 15.7, 4.5, 17.7, 4.1);
            c.closePath(); c.stroke(); break;
        case "lock":
            c.strokeRect(6, 10, 12, 11);
            c.beginPath(); c.arc(12, 10, 4, Math.PI, 2 * Math.PI); c.stroke();
            circle(12, 15, 1, true); line([[12, 15], [12, 17]]); break;
        case "rotation":
            c.beginPath(); c.arc(12, 12, 9, -1.1, 3.8); c.stroke();
            line([[2.3, 6.5], [4.1, 11], [7, 7]]);
            c.strokeRect(9, 11, 6, 6);
            c.beginPath(); c.arc(12, 11, 2, Math.PI, 2 * Math.PI); c.stroke(); break;
        case "sun":
            circle(12, 12, 4, false);
            for (var a = 0; a < 8; ++a) {
                var rad = a * Math.PI / 4;
                line([[12 + 7 * Math.cos(rad), 12 + 7 * Math.sin(rad)],
                      [12 + 10 * Math.cos(rad), 12 + 10 * Math.sin(rad)]]);
            }
            break;
        case "volume":
            c.beginPath(); c.moveTo(3, 9); c.lineTo(7, 9); c.lineTo(12, 5);
            c.lineTo(12, 19); c.lineTo(7, 15); c.lineTo(3, 15); c.closePath(); c.fill();
            c.beginPath(); c.arc(11, 12, 6, -0.8, 0.8); c.stroke();
            c.beginPath(); c.arc(11, 12, 10, -0.8, 0.8); c.stroke(); break;
        case "bell":
            c.beginPath(); c.moveTo(5, 17); c.lineTo(7, 14); c.lineTo(7, 9);
            c.bezierCurveTo(7, 2, 17, 2, 17, 9);
            c.lineTo(17, 14); c.lineTo(19, 17); c.closePath(); c.stroke();
            c.beginPath(); c.arc(12, 19, 2, 0, Math.PI); c.stroke(); break;
        case "sound":
            line([[9, 18], [9, 5], [20, 3], [20, 16]]);
            circle(6, 18, 3, true); circle(17, 16, 3, true); break;
        case "battery":
            c.strokeRect(2, 6, 18, 12);
            c.fillRect(21, 10, 2, 4);
            c.fillRect(5, 9, 10, 6); break;
        case "clock":
            circle(12, 12, 9, false); line([[12, 6], [12, 12], [16, 14]]); break;
        case "close":
            line([[6, 6], [18, 18]]); line([[18, 6], [6, 18]]); break;
        case "back":
            line([[14, 5], [7, 12], [14, 19]]); break;
        case "chevron":
            line([[9, 6], [15, 12], [9, 18]]); break;
        case "check":
            line([[5, 12], [10, 17], [20, 6]]); break;
        case "search":
            circle(10.3, 10.3, 6.4, false);
            line([[15, 15], [21, 21]]); break;
        case "settings":
        default:
            for (var s = 0; s < 3; ++s) {
                var yy = 6 + s * 6;
                var xx = s === 1 ? 8 : 16;
                line([[3, yy], [xx - 3, yy]]);
                line([[xx + 3, yy], [21, yy]]);
                circle(xx, yy, 2.4, false);
            }
            break;
        }
    }
}
