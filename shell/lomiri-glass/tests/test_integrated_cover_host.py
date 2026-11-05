#!/usr/bin/env python3
"""Qt5 portrait lock-cover integration; authentic GreeterView/LoginList/prompt QML.

Only Lomiri's unavailable C++ services and auxiliary theme/cover widgets are
mocked. This exercises the real reparenting and LightDM response signal chain,
but does not validate PAM, on-device greeter policy, or graphical rollback.
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

from PyQt5.QtCore import (QAbstractListModel, QModelIndex, QObject, Qt, QPointF,
                          QUrl, pyqtProperty, pyqtSlot, qInstallMessageHandler)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtTest import QTest
from PyQt5.QtQuick import QQuickItem
from PyQt5.QtQml import qmlRegisterType

from test_greeter_flow_host import (Units, Haptics, I18n, MockGSettings,
                                    MockLightDM, create_fixture, scene_item)


class UnitsWithDp(Units):
    @pyqtSlot(float, result=float)
    def dp(self, value):
        return value


class Roles(QObject):
    @pyqtProperty(int, constant=True)
    def SessionRole(self):
        return 1

    @pyqtProperty(int, constant=True)
    def LoggedInRole(self):
        return 2


class UserRows(QObject):
    @pyqtProperty(int, constant=True)
    def count(self):
        return 1

    @pyqtSlot(int, int, result=str)
    def data(self, index, role):
        return "test-session" if role == 1 else ""


class Sessions(QObject):
    @pyqtProperty(int, constant=True)
    def count(self):
        return 1

    @pyqtSlot(str, result=QUrl)
    def iconUrl(self, session):
        return QUrl()


class OneUser(QAbstractListModel):
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 1

    def roleNames(self):
        return {Qt.UserRole + 1: b"name", Qt.UserRole + 2: b"realName",
                Qt.UserRole + 3: b"loggedIn", Qt.UserRole + 4: b"session"}

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() != 0:
            return None
        return {Qt.UserRole + 1: "phablet", Qt.UserRole + 2: "Test",
                Qt.UserRole + 3: False, Qt.UserRole + 4: "test-session"}.get(role)


class TestLightDM(MockLightDM):
    def __init__(self):
        super().__init__()
        self._users = UserRows()
        self._roles = Roles()
        self._sessions = Sessions()

    @pyqtProperty(QObject, constant=True)
    def userRoles(self):
        return self._roles

    @pyqtProperty(QObject, constant=True)
    def sessions(self):
        return self._sessions


def write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def fixtures(target: Path, source: Path) -> Path:
    create_fixture(target, source)
    greeter = target / "qml/Greeter"
    shutil.copy2(source / "Greeter/GreeterView.qml", greeter / "GreeterView.qml")
    shutil.copy2(source / "Greeter/LoginList.qml", greeter / "LoginList.qml")
    write(greeter / "CoverPage.qml", '''import QtQuick 2.15
Item {
 id: cover
 property bool shown: true
 property bool required: shown
 property bool draggable: true
 property bool phoneVerticalUnlock: false
 property real showProgress: 1
 property bool showInfographic: false
 property var infographicModel
 property real panelHeight: 0
 property real backgroundSourceSize: 0
 property url background
 property bool hasCustomBackground: false
 property real backgroundShadeOpacity: 0
 property real dragHandleLeftMargin: 0
 property real launcherOffset: 0
 property real infographicsLeftMargin: 0
 property real infographicsTopMargin: 0
 property real infographicsBottomMargin: 0
 property real infographicsRightMargin: 0
 property Animation showAnimation: NumberAnimation { }
 property Animation hideAnimation: NumberAnimation { }
 signal tease()
 signal clicked()
 signal unlockRequested()
 function show() { shown = true; visible = true }
 function showNow() { show() }
 function hide() { shown = false; visible = false }
 function hideNow() { hide() }
 function hideRight() { hide() }
 function maybeShow() { if (!shown) showNow() }
 function showErrorMessage(message) { }
}
''')
    write(greeter / "Clock.qml", "import QtQuick 2.15\nItem { width: 220; height: 100 }\n")
    write(greeter / "LoginAreaContainer.qml", "import QtQuick 2.15\nItem {}\n")
    write(greeter / "DelayedLockscreen.qml", "import QtQuick 2.15\nItem {property int delayMinutes:0;property bool alphaNumeric:false}\n")
    write(target / "qml/Components/StandardAnimation.qml", "import QtQuick 2.15\nNumberAnimation { duration:110 }\n")
    write(target / "qml/Components/AbstractButton.qml", "import QtQuick 2.15\nMouseArea {}\n")
    imports = target / "imports"
    lomiri = imports / "Lomiri/Components"
    write(lomiri / "qmldir", (lomiri / "qmldir").read_text() + "ThemeSettings 1.3 ThemeSettings.qml\n")
    write(lomiri / "ThemeSettings.qml", '''import QtQuick 2.15
QtObject {
 property string name: "Fixture"
 property QtObject palette: QtObject {
  property QtObject normal: QtObject {
   property color focus: "white"
   property color raised: "white"
   property color raisedSecondaryText: "white"
   property color negative: "red"
  }
 }
}
''')
    write(lomiri / "StyledItem.qml", '''import QtQuick 2.15
Item { property QtObject theme: QtObject { } }
''')
    write(lomiri / "Icon.qml", '''import QtQuick 2.15
Item { property string name; property url source; property color keyColor: "white"; property color color: "white" }
''')
    write(imports / "Lomiri/Telephony/qmldir", "module Lomiri.Telephony\nUnused 0.1 Unused.qml\n")
    write(imports / "Lomiri/Telephony/Unused.qml", "import QtQuick 2.15\nQtObject {}\n")
    # Qt 5 shipped by pip lacks the optional GraphicalEffects QML module;
    # the actual GreeterView does not instantiate any of its types.
    view_file = greeter / "GreeterView.qml"
    view_file.write_text(view_file.read_text().replace(
        "import QtGraphicalEffects 1.12\n", ""), encoding="utf-8")
    harness = target / "IntegratedHarness.qml"
    write(harness, '''import QtQuick 2.15
import "qml/Greeter"
Rectangle {
 width: 380; height: 780; color: "#243449"
 GreeterView {
  id: greeter
  objectName: "actualGreeterView"
  anchors.fill: parent
  usageMode: "phone"
  orientation: Qt.PortraitOrientation
  locked: true
  alphanumeric: false
  userModel: TestUsers
  onResponded: parent.authResponse(response)
 }
 signal authResponse(string pin)
 property alias greeter: greeter
}
''')
    return harness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    app = QGuiApplication([])
    qmlRegisterType(MockGSettings, "GSettings", 1, 0, "GSettings")
    messages = []
    qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))
    lightdm, haptics = TestLightDM(), Haptics()
    units, i18n, users = UnitsWithDp(), I18n(), OneUser()
    with tempfile.TemporaryDirectory(prefix="uos27-cover-host-") as scratch:
        target = Path(scratch)
        harness = fixtures(target, args.source / "qml")
        from PyQt5.QtQuick import QQuickView
        view = QQuickView()
        view.engine().addImportPath(str(target / "imports"))
        context = view.rootContext()
        context.setContextProperty("units", units)
        context.setContextProperty("Haptics", haptics)
        context.setContextProperty("i18n", i18n)
        context.setContextProperty("TestUsers", users)
        context.setContextProperty("LightDMService", lightdm)
        context.setContextProperty("TestPrompts", lightdm._prompts)
        context.setContextProperty("LomiriAnimation", {"SlowDuration": 250, "FastDuration": 120})
        context.setContextProperty("callManager", {"hasCalls": False})
        context.setContextProperty("theme", {"palette": {"normal": {
            "focus": "white", "raised": "white", "raisedSecondaryText": "white"}}})
        view.setSource(QUrl.fromLocalFile(str(harness)))
        if view.status() != QQuickView.Ready:
            raise AssertionError([str(error.toString()) for error in view.errors()])
        view.show()
        QTest.qWait(140)
        root = view.rootObject()
        greeter = root.property("greeter")
        assert not greeter.property("integratedPinVisible"), messages
        greeter.tryToUnlock(False)
        QTest.qWait(180)
        assert greeter.property("integratedPinVisible"), messages
        cover = scene_item(root, "coverPage")
        login = scene_item(root, "loginList")
        assert cover and login and login.parentItem() == cover, messages
        assert cover.property("shown") and login.property("integratedPin"), messages
        assert login.property("usageMode") == "phone", messages
        pad = scene_item(root, "uos27NativePinPad")
        prompt = scene_item(root, "uos27NumericGreeterPrompt")
        assert pad and prompt and pad.isVisible(), messages
        if args.preview:
            args.preview.parent.mkdir(parents=True, exist_ok=True)
            QTest.qWait(220)
            frame = view.grabWindow()
            if not frame.isNull():
                assert frame.save(str(args.preview)), "Qt greeter screenshot failed"
        replies = []
        root.authResponse.connect(lambda pin: replies.append(pin))
        for number in (1, 2, 3, 4):
            button = scene_item(root, "pinPadButton" + str(number))
            assert button and button.isVisible(), (number, messages)
            point = button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint()
            QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(40)
        assert replies == ["1234"], (replies, messages)
        assert haptics.calls == 4, haptics.calls
        greeter.notifyAuthenticationFailed()
        QTest.qWait(50)
        assert prompt.property("enteredText") == "", messages
        assert greeter.property("integratedPinVisible"), messages
        prompt.canceled.emit()
        QTest.qWait(60)
        assert not greeter.property("integratedPinVisible"), messages
        assert login.parentItem() == scene_item(root, "lockscreen"), messages
        assert cover.property("shown"), "Cancel must return to the cover, not bypass the lock"
        view.close()
    errors = [message for message in messages if any(word in message for word in (
        "ReferenceError", "TypeError", "Binding loop", "Cannot anchor", "Unable to assign",
        "Cannot assign", "is not a type", "failed to load"))]
    assert not errors, errors
    report = {"result": "pass", "checks": ["real GreeterView opens embedded PIN without sliding away cover",
             "real LoginList is reparented onto cover wallpaper", "portrait phone route reaches GlassPinPrompt",
             "four physical-button events submit once via original LightDM response signal",
             "failed PIN clears digits without leaving integrated cover",
             "cancel returns to same locked cover without authenticating"],
             "mocked": ["C++ LightDM model", "CoverPage animation/mouse surface", "PAM authentication"],
             "qt_messages": messages}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
