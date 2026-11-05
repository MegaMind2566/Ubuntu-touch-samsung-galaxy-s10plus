#!/usr/bin/env python3
"""Render patched native components with inert C++/bus boundary fixtures.

The production CoverPage, Clock and LightDM-facing PIN chain are copied from
the hash-checked prepared source. No service is contacted and successful
authentication is never simulated. Synthetic input is exclusively fixture data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from runtime import create_view, save_screenshot
from test_integrated_cover_host import (fixtures, write, TestLightDM, UnitsWithDp,
                                        Haptics, I18n, OneUser, MockGSettings, scene_item)
from test_greeter_flow_host import MockSettingsSchema
from PyQt5.QtCore import QObject, QUrl, QPointF, Qt, QAbstractListModel, QModelIndex, pyqtProperty, qInstallMessageHandler
from PyQt5.QtQml import qmlRegisterType, qmlRegisterUncreatableType
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest
from native_surfaces import add_surfaces


class Settings(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._schema = MockSettingsSchema()

    @pyqtProperty(MockSettingsSchema, constant=True)
    def schema(self):
        return self._schema

    @pyqtProperty(bool, constant=True)
    def showChargingInformationWhileLocked(self):
        return False


class WindowRows(QAbstractListModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._name="Note"
    @pyqtProperty(str)
    def fixtureName(self): return self._name
    @fixtureName.setter
    def fixtureName(self,value): self._name=value
    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else 1
    def roleNames(self): return {Qt.UserRole+1:b"window"}
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or role!=Qt.UserRole+1:return None
        return {"state":0,"position":{"x":0,"y":0},"surface":{"name":self._name,"fixtureColor":"#fff7d5" if self._name=="Note" else "#e1f1f7"}}


def module(root, name, types):
    base = root / "imports" / name.replace(".", "/")
    lines = ["module " + name]
    for key, source in types.items():
        prefix = "singleton " if key.startswith("singleton ") else ""
        key = key.removeprefix("singleton ")
        typ, version = key.split()
        lines.append(f"{prefix}{typ} {version} {typ}.qml")
        write(base / f"{typ}.qml", source)
    write(base / "qmldir", "\n".join(lines) + "\n")


def cover_fixture(target, source):
    harness = fixtures(target, source / "qml")
    actual = ["Greeter/CoverPage.qml", "Greeter/Clock.qml", "Components/Showable.qml",
              "Components/PinLockscreen.qml", "Components/PinPadButton.qml",
              "Panel/Glass/GlassPinPrompt.qml", "Panel/Glass/GlassUnlockGesture.qml"]
    for filename in actual:
        dest = target / "qml" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "qml" / filename, dest)
    shutil.copy2(source / "qml/Panel/Glass/GlassIcon.qml", target / "qml/Panel/Glass/GlassIcon.qml")
    write(target / "imports/Lomiri/Components/Icon.qml", '''import QtQuick 2.15
import "../../../qml/Panel/Glass" as Glass
Item { id:icon; property string name; property url source; property color keyColor:"white"; property color color:"white"
 Glass.GlassIcon { anchors.fill:parent; name:icon.name === "erase" ? "back" : icon.name; color:icon.color }
}
''')
    shutil.copytree(source / "qml/graphics", target / "qml/graphics", dirs_exist_ok=True)
    # Installed resources strip @scale suffixes. Supply the same immutable
    # resource bytes under their logical paths inside the fixture only.
    for resource in (target / "qml/graphics").glob("dropshadow*@*.*"):
        shutil.copy2(resource, resource.with_name(re.sub(r"@(20|30)(?=\.)", "", resource.name)))
    # Wallpaper's compiled image provider is replaced with an original gradient;
    # cover/clock/layout/gestures/authentication UI remain production QML.
    write(target / "qml/Components/Wallpaper.qml", '''import QtQuick 2.15
Rectangle { property url source; property real sourceSize
 gradient: Gradient { GradientStop {position:0;color:"#6c83a2"} GradientStop {position:0.5;color:"#294451"} GradientStop {position:1;color:"#171e38"} }
}
''')
    write(target / "qml/Components/Infographics.qml", 'import QtQuick 2.15\nItem { property var model }\n')
    write(target / "qml/Components/DragHandle.qml", 'import QtQuick 2.15\nItem { property bool pressed:false; property int direction }\n')
    write(target / "qml/Components/MathUtils.qml", '''pragma Singleton
import QtQuick 2.15
QtObject { function clamp(v,a,b) {return Math.min(b,Math.max(a,v))} }
''')
    write(target / "qml/Components/qmldir", "singleton MathUtils 1.0 MathUtils.qml\n")
    module(target, "QtGraphicalEffects", {"Unused 1.0": 'import QtQuick 2.15\nQtObject {}', "Unused 1.12": 'import QtQuick 2.15\nQtObject {}'})
    module(target, "Lomiri.Gestures", {"Unused 0.1": 'import QtQuick 2.15\nQtObject {}'})
    module(target, "BatteryMonitor", {"Unused 1.0": 'import QtQuick 2.15\nQtObject {}'})
    module(target, "Lomiri.Indicators", {
        "SharedLomiriMenuModel 0.1": '''import QtQuick 2.15
QtObject { property string busName; property var actions; property string menuObjectPath; readonly property var model:null }
''', "ModelActionRootState 0.1": '''import QtQuick 2.15
QtObject { property var menu; property string rightLabel:""; signal updated() }
'''})
    (target / "qml/Panel/Indicators").mkdir(parents=True, exist_ok=True)
    write(target / "qml/Panel/Indicators/qmldir", "# Native service boundary fixture\n")
    write(target / "imports/Lomiri/Components/Label.qml", '''import QtQuick 2.15
Text { property string fontSize:"medium"; font.pixelSize:fontSize === "large" ? 21 : fontSize === "small" ? 14 : 17 }
''')
    return harness, actual


def make_native_view(harness, target, lightdm, units, haptics, i18n, users):
    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.engine().addImportPath(str(target / "imports"))
    context = view.rootContext()
    for key, value in {"units": units, "Haptics": haptics, "i18n": i18n,
                       "TestUsers": users, "LightDMService": lightdm,
                       "TestPrompts": lightdm._prompts,
                       "LomiriAnimation": {"SlowDuration":250,"FastDuration":120,"BriskDuration":150,"SleepyDuration":200,"SnapDuration":120},
                       "Direction":{"Horizontal":0},
                       "BatteryMonitor":{"timeToFull":-1,"NO_BATTERY":-1,"NO_TIMETOFULL":-2,"charging":False,"fullyCharged":False},
                       "callManager":{"hasCalls":False},
                       "theme":{"palette":{"normal":{"focus":"white","raised":"white","raisedSecondaryText":"white"}}}}.items():
        context.setContextProperty(key, value)
    view.setSource(QUrl.fromLocalFile(str(harness)))
    if view.status() != QQuickView.Ready:
        raise AssertionError([e.toString() for e in view.errors()])
    return view


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app, font_view, _ = create_view()
    font_view.close()
    qmlRegisterUncreatableType(MockSettingsSchema,"GSettings",1,0,"Schema","Owned by GSettings")
    qmlRegisterType(Settings, "GSettings", 1, 0, "GSettings")
    qmlRegisterType(WindowRows,"Fixture",1,0,"FixtureWindowModel")
    messages=[]
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    lightdm, units, haptics, i18n, users = TestLightDM(), UnitsWithDp(), Haptics(), I18n(), OneUser()
    captures=[]
    with tempfile.TemporaryDirectory(prefix="uos27-native-render-", ignore_cleanup_errors=True) as scratch:
        target=Path(scratch)
        harness, actual = cover_fixture(target, args.source)
        identities={name:hashlib.sha256((target / "qml" / name).read_bytes()).hexdigest() for name in actual}
        for width,height in ((360,760),(412,870)):
            # Independent challenge fixtures per display size. Full greeter
            # authentication lifecycle is owned by the unavailable C++ service.
            view=make_native_view(harness,target,lightdm,units,haptics,i18n,users)
            view.resize(width,height)
            view.show()
            root=view.rootObject()
            greeter=root.property("greeter")
            QTest.qWait(200)
            cover=scene_item(root,"coverPage")
            assert cover and cover.property("phoneVerticalUnlock")
            assert scene_item(root,"uos27LockClock")
            assert not greeter.property("integratedPinVisible")
            captures.append(save_screenshot(view,args.output / f"native-lock-{width}x{height}.png"))
            # Real input to real CoverPage GlassUnlockGesture; no direct unlock.
            start=QPointF(width*.5,height*.8).toPoint()
            end=QPointF(width*.5,height*.55).toPoint()
            QTest.mousePress(view,Qt.LeftButton,Qt.NoModifier,start)
            QTest.mouseMove(view,end,80)
            QTest.mouseRelease(view,Qt.LeftButton,Qt.NoModifier,end)
            QTest.qWait(250)
            assert greeter.property("integratedPinVisible"), messages
            prompt=scene_item(root,"uos27NumericGreeterPrompt")
            assert prompt and scene_item(root,"uos27NativePinPad").isVisible()
            captures.append(save_screenshot(view,args.output / f"native-pin-{width}x{height}.png"))
            replies=[]
            root.authResponse.connect(replies.append)
            for number in (1,2,3,4):
                button=scene_item(root,"pinPadButton"+str(number))
                point=button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint()
                QTest.mouseClick(view,Qt.LeftButton,Qt.NoModifier,point)
                QTest.qWait(30)
            assert replies == ["1234"], replies
            root.authResponse.disconnect(replies.append)
            assert greeter.property("locked"), "A response must not grant fixture authentication"
            greeter.notifyAuthenticationFailed()
            QTest.qWait(650)
            assert prompt.property("enteredText") == "", (width,prompt.property("enteredText"), messages)
            prompt.canceled.emit()
            QTest.qWait(80)
            assert not greeter.property("integratedPinVisible") and cover.property("shown")
            view.close()
        identities.update(add_surfaces(target,args.source,write,module))
        for width,height in ((360,760),(412,870)):
            view=make_native_view(target/"NotificationsHarness.qml",target,lightdm,units,haptics,i18n,users)
            view.resize(width,height)
            view.show()
            QTest.qWait(200)
            root=view.rootObject()
            summary=scene_item(root,"summaryLabel")
            body=scene_item(root,"bodyLabel")
            assert summary and body and summary.isVisible() and body.isVisible()
            captures.append(save_screenshot(view,args.output/f"native-notifications-{width}x{height}.png"))
            root.setProperty("privateContent",True)
            QTest.qWait(80)
            assert not body.isVisible() and scene_item(root,"privacySummaryLabel").isVisible()
            captures.append(save_screenshot(view,args.output/f"native-notifications-private-{width}x{height}.png"))
            view.close()
            view=make_native_view(target/"SpreadHarness.qml",target,lightdm,units,haptics,i18n,users)
            view.resize(width,height)
            view.show()
            QTest.qWait(200)
            root=view.rootObject()
            spread=scene_item(root,"nativeSpread")
            assert spread and scene_item(root,"nativeWorkspace0")
            captures.append(save_screenshot(view,args.output/f"native-switcher-{width}x{height}.png"))
            spread.forceActiveFocus()
            QTest.keyClick(view,Qt.Key_Right)
            assert spread.property("highlightedIndex")==1 and root.property("snapIndex")==1
            QTest.keyClick(view,Qt.Key_Left)
            assert spread.property("highlightedIndex")==0
            QTest.keyClick(view,Qt.Key_Q)
            assert root.property("closeRequests")==1
            QTest.keyClick(view,Qt.Key_Escape)
            assert root.property("leaveRequests")==1
            view.close()
    errors=[m for m in messages if any(x in m for x in ("ReferenceError","TypeError","Binding loop","Cannot anchor","Unable to assign","Cannot assign","is not a type","failed to load"))]
    assert not errors,errors
    report={"result":"pass","source_prepared_only":True,"captures":captures,"exact_native_components":identities,
            "checks":["actual CoverPage upward gesture opens actual LightDM-facing PIN UI","real PIN buttons submit one fixture response","response never unlocks without authentication","failure clears PIN; cancel returns to locked cover","actual populated native Notification displays synthetic summary/body","native privacyMode hides body and shows generic message","actual Spread keyboard navigation calls snap; close and leave emit requests only"],
            "boundaries":["inert LightDM/GSettings/battery/indicator models","original fixture wallpaper provider","Lomiri C++ theme primitives and notification icon/blur","synthetic Mir app textures and window model","no real app closure, sound, notification service, PAM or handset compositor","full greeter multi-attempt lifecycle not exercised"],"qt_messages":messages}
    (args.output / "native-components.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"result":"pass","captures":len(captures),"checks":len(report["checks"])}))


if __name__ == "__main__":
    main()
