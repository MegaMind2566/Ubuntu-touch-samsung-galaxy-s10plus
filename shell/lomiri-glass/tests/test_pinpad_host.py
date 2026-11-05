#!/usr/bin/env python3
"""Qt5 smoke test for the modified, still-authentic Greeter PIN button.

The PIN transport, PAM/LightDM and lockscreen are not replaced or simulated as
authenticated. Only the visual button and its existing one-release signal are
loaded with graphical theme/Haptics fixtures.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PyQt5.QtCore import QObject, QPointF, Qt, QUrl, pyqtSlot, qInstallMessageHandler
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest


class Units(QObject):
    @pyqtSlot(float, result=float)
    def gu(self, value):
        return value * 8


class Haptics(QObject):
    def __init__(self):
        super().__init__()
        self.calls = 0

    @pyqtSlot()
    def play(self):
        self.calls += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    stage = args.source / "qml"
    with tempfile.TemporaryDirectory(prefix="uos27-greeter-pin-") as temporary:
        directory = Path(temporary)
        pin = directory / "qml/Components"
        theme = directory / "qml/Panel/Glass"
        pin.mkdir(parents=True)
        theme.mkdir(parents=True)
        shutil.copy2(stage / "Components/PinPadButton.qml", pin / "PinPadButton.qml")
        shutil.copy2(stage / "Panel/Glass/GlassTheme.js", theme / "GlassTheme.js")
        lomiri = directory / "imports/Lomiri/Components"
        lomiri.mkdir(parents=True)
        (lomiri / "qmldir").write_text(
            "module Lomiri.Components\nLomiriShape 1.3 LomiriShape.qml\n"
            "Label 1.3 Label.qml\nIcon 1.3 Icon.qml\n"
            "LomiriNumberAnimation 1.3 LomiriNumberAnimation.qml\n")
        (lomiri / "LomiriShape.qml").write_text('import QtQuick 2.15\nRectangle { property color backgroundColor: "transparent"; color: backgroundColor; radius: height/2 }\n')
        (lomiri / "Label.qml").write_text('import QtQuick 2.15\nText { property string fontSize: "medium" }\n')
        (lomiri / "Icon.qml").write_text('import QtQuick 2.15\nItem { property string name; property color color: "white" }\n')
        (lomiri / "LomiriNumberAnimation.qml").write_text('import QtQuick 2.15\nNumberAnimation { duration: 125 }\n')
        (directory / "Harness.qml").write_text('''import QtQuick 2.15
import "qml/Components"
Rectangle {
    width: 320; height: 400; color: "#111c34"
    PinPadButton {
        id: pin
        objectName: "realPinButton"
        width: 84; height: 84
        anchors.centerIn: parent
        text: "7"
        foregroundColor: "white"
    }
    property alias target: pin
}
''')
        messages = []
        qInstallMessageHandler(lambda kind, context, message: messages.append(message))
        app = QGuiApplication([])
        units, haptics = Units(), Haptics()
        view = QQuickView()
        view.engine().addImportPath(str(directory / "imports"))
        view.rootContext().setContextProperty("units", units)
        view.rootContext().setContextProperty("Haptics", haptics)
        view.rootContext().setContextProperty("LomiriAnimation", {"SlowDuration": 250})
        view.setSource(QUrl.fromLocalFile(str(directory / "Harness.qml")))
        assert view.status() == QQuickView.Ready, [str(x.toString()) for x in view.errors()]
        view.show()
        QTest.qWait(80)
        target = view.rootObject().property("target")
        assert target is not None
        clicked = []
        target.clicked.connect(lambda: clicked.append(True))
        location = target.mapToScene(QPointF(42, 42)).toPoint()
        QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, location)
        QTest.qWait(30)
        assert haptics.calls == 0 and not clicked, "PIN should activate only on release"
        QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, location)
        QTest.qWait(140)
        assert haptics.calls == 1 and len(clicked) == 1
        forbidden = [line for line in messages if any(marker in line for marker in
                     ("ReferenceError", "TypeError", "Cannot assign", "Binding loop", "is not a type"))]
        assert not forbidden, forbidden
        result = {"result": "pass", "scope": "Native Qt5 uOS27 PIN button with mock theme and haptics",
                  "checks": ["renders without QML binding errors", "press does not submit PIN",
                             "release emits original PIN signal and one haptic event"],
                  "not_validated": ["PAM authentication", "handset", "screen lock policy"]}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        view.close()


if __name__ == "__main__":
    main()
