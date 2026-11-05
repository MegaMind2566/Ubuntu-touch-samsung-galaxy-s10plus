#!/usr/bin/env python3
"""Qt5 integration of the uOS27 swipe and original Greeter PIN response path.

The real PromptList, GreeterPrompt, native PinLockscreen and PinPadButton QML
are loaded. LightDM's prompt model and UI imports are fixtures; PAM, the
handset compositor and unlock success are intentionally NOT simulated.
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

from PyQt5.QtCore import (QAbstractListModel, QObject, QModelIndex, QPointF,
                          Qt, QUrl, pyqtProperty, pyqtSlot, qInstallMessageHandler)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQuick import QQuickItem, QQuickView
from PyQt5.QtTest import QTest
from PyQt5.QtQml import qmlRegisterType


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


class I18n(QObject):
    @pyqtSlot(str, result=str)
    def tr(self, source):
        return source


class MockPrompts(QAbstractListModel):
    PROMPT_TYPE = Qt.UserRole + 1
    PROMPT_TEXT = Qt.UserRole + 2
    PROMPT_INDEX = Qt.UserRole + 3

    @pyqtProperty(int, constant=True)
    def count(self):
        return 1

    @pyqtProperty(int, constant=True)
    def Message(self):
        return 0

    @pyqtProperty(int, constant=True)
    def Error(self):
        return 1

    @pyqtProperty(int, constant=True)
    def Button(self):
        return 2

    @pyqtProperty(int, constant=True)
    def Secret(self):
        return 3

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 1

    def roleNames(self):
        return {self.PROMPT_TYPE: b"type", self.PROMPT_TEXT: b"text",
                self.PROMPT_INDEX: b"index"}

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() != 0:
            return None
        return {self.PROMPT_TYPE: self.Secret, self.PROMPT_TEXT: "",
                self.PROMPT_INDEX: 0}.get(role)


class MockUsers(QObject):
    @pyqtProperty(int, constant=True)
    def count(self):
        return 1


class MockLightDM(QObject):
    def __init__(self):
        super().__init__()
        self._prompts = MockPrompts()
        self._users = MockUsers()

    @pyqtProperty(QAbstractListModel, constant=True)
    def prompts(self):
        return self._prompts

    @pyqtProperty(QObject, constant=True)
    def users(self):
        return self._users


class MockSettingsSchema(QObject):
    def __init__(self):
        super().__init__()
        self._id = ""

    @pyqtProperty(str)
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value


class MockGSettings(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._schema = MockSettingsSchema()
        self._show_osk = False

    @pyqtProperty(QObject, constant=True)
    def schema(self):
        return self._schema

    @pyqtProperty(bool)
    def alwaysShowOsk(self):
        return self._show_osk

    @alwaysShowOsk.setter
    def alwaysShowOsk(self, value):
        self._show_osk = value


def create_fixture(directory: Path, source: Path) -> tuple[Path, Path]:
    glass = directory / "qml/Panel/Glass"
    components = directory / "qml/Components"
    greeter = directory / "qml/Greeter"
    for path in (glass, components, greeter):
        path.mkdir(parents=True)
    for filename in ("GlassUnlockGesture.qml", "GlassPinPrompt.qml", "GlassTheme.js"):
        shutil.copy2(source / "Panel/Glass" / filename, glass / filename)
    for filename in ("PinLockscreen.qml", "PinPadButton.qml", "WrongPasswordAnimation.qml"):
        shutil.copy2(source / "Components" / filename, components / filename)
    (components / "FadingLabel.qml").write_text(
        'import Lomiri.Components 1.3\nLabel {}\n')
    for filename in ("GreeterPrompt.qml", "PromptList.qml"):
        shutil.copy2(source / "Greeter" / filename, greeter / filename)
    # GSettings is a native compiled Qt plugin on the phone. Replace only
    # its schema-owned fixture object; keep the GreeterPrompt loader and PIN
    # signal/response logic byte-for-byte otherwise.
    prompt_path = greeter / "GreeterPrompt.qml"
    prompt_source = prompt_path.read_text(encoding="utf-8")
    native_settings = '''    GSettings {
        id: lomiriSettings
        schema.id: "com.lomiri.Shell"
    }'''
    assert native_settings in prompt_source
    prompt_path.write_text(prompt_source.replace(native_settings,
        '    QtObject { id: lomiriSettings; property bool alwaysShowOsk: false }'), encoding="utf-8")
    prompt_list_path = greeter / "PromptList.qml"
    prompt_list_source = prompt_list_path.read_text(encoding="utf-8")
    assert "model: LightDMService.prompts" in prompt_list_source
    prompt_list_path.write_text(prompt_list_source.replace(
        "model: LightDMService.prompts", "model: TestPrompts"), encoding="utf-8")

    imports = directory / "imports"
    lomiri = imports / "Lomiri/Components"
    lomiri.mkdir(parents=True)
    (lomiri / "qmldir").write_text("module Lomiri.Components\n"
        "LomiriShape 1.3 LomiriShape.qml\nLabel 1.3 Label.qml\n"
        "Icon 1.3 Icon.qml\nLomiriNumberAnimation 1.3 LomiriNumberAnimation.qml\n"
        "AbstractButton 1.3 AbstractButton.qml\nStyledItem 1.3 StyledItem.qml\n")
    (lomiri / "LomiriShape.qml").write_text('import QtQuick 2.15\nRectangle { property color backgroundColor: "transparent"; color: backgroundColor; radius: height/2 }\n')
    (lomiri / "Label.qml").write_text('import QtQuick 2.15\nText { property string fontSize: "medium" }\n')
    (lomiri / "Icon.qml").write_text('import QtQuick 2.15\nItem { property string name; property color color: "white" }\n')
    (lomiri / "LomiriNumberAnimation.qml").write_text('import QtQuick 2.15\nNumberAnimation { duration: 110 }\n')
    (lomiri / "StyledItem.qml").write_text('import QtQuick 2.15\nItem {}\n')
    (lomiri / "AbstractButton.qml").write_text('import QtQuick 2.15\nMouseArea {}\n')
    submodule = lomiri / "ListItems"
    submodule.mkdir()
    (submodule / "qmldir").write_text(
        "module Lomiri.Components.ListItems\nUnused 1.3 Unused.qml\n")
    (submodule / "Unused.qml").write_text("import QtQuick 2.15\nQtObject {}\n")

    accounts = imports / "AccountsService"
    accounts.mkdir()
    (accounts / "qmldir").write_text(
        "module AccountsService\nsingleton AccountsService 0.1 AccountsService.qml\n")
    (accounts / "AccountsService.qml").write_text('''pragma Singleton
import QtQuick 2.15
QtObject {
    readonly property int pincodeLength: 4
    readonly property string defaultPinCodePromptManager: "PinPrompt.qml"
    readonly property string pinCodePromptManager: "ClockPinPrompt.qml"
    property int failedLogins: 0
}
''')
    gesture_harness = directory / "GestureHarness.qml"
    gesture_harness.write_text('''import QtQuick 2.15
import "qml/Panel/Glass" as Glass
Rectangle {
    width: 380; height: 720; color: "#161e31"
    Glass.GlassUnlockGesture {
        id: gesture
        objectName: "actualUnlockGesture"
        anchors.fill: parent
        swipeDistance: 60
    }
    property alias gesture: gesture
}
''')
    auth_harness = directory / "AuthenticationHarness.qml"
    auth_harness.write_text('''import QtQuick 2.15
import "qml/Greeter"
Rectangle {
    width: 400; height: 800; color: "#101b34"
    PromptList {
        id: challenge
        objectName: "actualPromptList"
        x: 0; y: 40; width: parent.width
        isLandscape: false
        usageMode: "phone"
        alphanumeric: false
        maxHeight: 640
    }
    property alias challenge: challenge
}
''')
    return gesture_harness, auth_harness


def make_view(path: Path, imports: Path, units: Units, haptics: Haptics,
              lightdm: MockLightDM, i18n: I18n) -> QQuickView:
    view = QQuickView()
    view.engine().addImportPath(str(imports))
    view.rootContext().setContextProperty("units", units)
    view.rootContext().setContextProperty("Haptics", haptics)
    view.rootContext().setContextProperty("LomiriAnimation", {"SlowDuration": 250})
    view.rootContext().setContextProperty("LightDMService", lightdm)
    view.rootContext().setContextProperty("TestPrompts", lightdm._prompts)
    view.rootContext().setContextProperty("i18n", i18n)
    view.setSource(QUrl.fromLocalFile(str(path)))
    if view.status() != QQuickView.Ready:
        raise AssertionError([str(error.toString()) for error in view.errors()])
    view.show()
    QTest.qWait(100)
    return view


def click(view: QQuickView, item: QObject) -> None:
    point = item.mapToScene(QPointF(item.width()/2, item.height()/2)).toPoint()
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, point)
    QTest.qWait(35)


def scene_item(root: QQuickItem, name: str):
    if root.objectName() == name:
        return root
    for child in root.childItems():
        found = scene_item(child, name)
        if found is not None:
            return found
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    stage = args.source / "qml"
    all_messages = []
    qInstallMessageHandler(lambda kind, context, message: all_messages.append(message))
    app = QGuiApplication([])
    qmlRegisterType(MockGSettings, "GSettings", 1, 0, "GSettings")
    units, haptics, lightdm, i18n = Units(), Haptics(), MockLightDM(), I18n()
    checks = []
    with tempfile.TemporaryDirectory(prefix="uos27-greeter-flow-") as temporary:
        directory = Path(temporary)
        gesture_path, auth_path = create_fixture(directory, stage)
        view = make_view(gesture_path, directory / "imports", units, haptics, lightdm, i18n)
        gesture = view.rootObject().property("gesture")
        assert gesture is not None
        unlocks = []
        gesture.unlockRequested.connect(lambda: unlocks.append(True))
        QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPointF(180, 600).toPoint())
        QTest.qWait(20)
        assert len(unlocks) == 1, (unlocks, all_messages)
        checks.append("tap provides an accessible native unlock request")
        unlocks.clear()
        QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, QPointF(180, 600).toPoint())
        QTest.mouseMove(view, QPointF(180, 515).toPoint(), delay=25)
        QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, QPointF(180, 500).toPoint())
        QTest.qWait(25)
        assert len(unlocks) == 1, (unlocks, all_messages)
        checks.append("upward 100px swipe emits exactly one unlock request")
        unlocks.clear()
        QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, QPointF(180, 600).toPoint())
        QTest.mouseMove(view, QPointF(300, 600).toPoint(), delay=25)
        QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, QPointF(300, 600).toPoint())
        QTest.qWait(25)
        assert len(unlocks) == 0, (unlocks, all_messages)
        checks.append("horizontal drag does not unlock")
        unlocks.clear()
        QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, QPointF(180, 500).toPoint())
        QTest.mouseMove(view, QPointF(180, 620).toPoint(), delay=25)
        QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, QPointF(180, 620).toPoint())
        QTest.qWait(25)
        assert len(unlocks) == 0, (unlocks, all_messages)
        checks.append("downward drag does not unlock")
        view.close()

        view = make_view(auth_path, directory / "imports", units, haptics, lightdm, i18n)
        prompt = scene_item(view.rootObject(), "uos27NumericGreeterPrompt")
        native_pad = scene_item(view.rootObject(), "uos27NativePinPad")
        assert prompt and native_pad, ("numeric PIN challenge not rendered", all_messages)
        assert prompt.property("pincodeLength") == 4
        checks.append("native LightDM PIN model creates visible in-shell numerical keypad")
        response = []
        challenge = view.rootObject().property("challenge")
        challenge.responded.connect(lambda value: response.append(value))
        for digit in (1, 2, 3):
            item = scene_item(view.rootObject(), "pinPadButton" + str(digit))
            assert item, (digit, all_messages)
            click(view, item)
            assert response == [], response
        fourth = scene_item(view.rootObject(), "pinPadButton4")
        assert fourth
        click(view, fourth)
        assert response == ["1234"], (response, all_messages)
        checks.append("four native keypad clicks send one original GreeterPrompt response")
        assert haptics.calls == 4, haptics.calls
        checks.append("native key release preserves one tactile callback per digit")
        challenge.setProperty("loginError", True)
        QTest.qWait(40)
        assert prompt.property("enteredText") == "", prompt.property("enteredText")
        checks.append("authentication error clears previously entered digits")
        view.close()

    problems = [message for message in all_messages if any(needle in message for needle in (
        "ReferenceError", "TypeError", "Binding loop", "Cannot assign", "is not a type",
        "Cannot anchor", "Cannot set property", "failed to load"))]
    assert not problems, problems
    report = {"result": "pass", "scope": "Qt5 actual swipe and native Greeter PIN QML with mocked LightDM and UI imports",
              "checks": checks, "warnings": all_messages,
              "not_validated": ["actual phone locked-session transition", "PAM acceptance",
                                "LightDM service responsiveness", "Maliit keyboard", "touchscreen driver"]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
