#!/usr/bin/env python3
"""Interpret production NativeBackend with inert QML service fixtures, no D-Bus.

Checks capability revocation and automatic-brightness gating. Does not test
the real QMenuModel plugin, GSettings backend, ALS, permissions or hardware.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PyQt5.QtCore import QObject, QUrl, QVariant, pyqtProperty, pyqtSignal, qInstallMessageHandler
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlComponent, QQmlEngine, qmlRegisterType, qmlRegisterUncreatableType
from PyQt5.QtTest import QTest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    app = QGuiApplication([])
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    checks = []
    with tempfile.TemporaryDirectory(prefix="uos27-capability-fixture-") as tmp:
        base = Path(tmp)
        def write(name, content):
            p = base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        write("imports/QMenuModel/qmldir", "module QMenuModel\nAyatanaMenuModel 1.0 AyatanaMenuModel.qml\nAyatanaMenuAction 1.0 AyatanaMenuAction.qml\nQDBusActionGroup 1.0 QDBusActionGroup.qml\nsingleton DBus 1.0 DBus.qml\n")
        write("imports/QMenuModel/AyatanaMenuModel.qml", '''import QtQml 2.15
QtObject { property string busName; property var actions; property string menuObjectPath; property string nameOwner: "fixture"; objectName: busName }
''')
        write("imports/QMenuModel/AyatanaMenuAction.qml", '''import QtQml 2.15
QtObject { property QtObject model; property int index; property string name; property bool valid: true; property bool enabled: true; property var state: name.indexOf("brightness") >= 0 || name.indexOf("volume") >= 0 ? 0.64 : false; function activate(value) {} function changeState(value) {} }
''')
        write("imports/QMenuModel/QDBusActionGroup.qml", '''import QtQml 2.15
QtObject {
 property int busType; property string busName; property string objectPath
 property QtObject observed: QtObject { property var state: 0.64; function activate(value) {} function updateState(value) {} }
 function start() {} function action(name) { return observed; }
}
''')
        write("imports/QMenuModel/DBus.qml", "pragma Singleton\nimport QtQml 2.15\nQtObject { enum BusType { SessionBus, SystemBus } }\n")
        class Schema(QObject):
            changed = pyqtSignal()
            def __init__(self, parent=None):
                super().__init__(parent)
                self._id = ""
            @pyqtProperty(str, notify=changed)
            def id(self): return self._id
            @id.setter
            def id(self, value):
                self._id = value
                self.changed.emit()
        class Settings(QObject):
            changed = pyqtSignal()
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setObjectName("fixtureSettings")
                self._schema = Schema(self)
                self._automatic = False
            @pyqtProperty(Schema, constant=True)
            def schema(self): return self._schema
            @pyqtProperty(QVariant, notify=changed)
            def autoBrightness(self): return self._automatic
            @autoBrightness.setter
            def autoBrightness(self, value):
                self._automatic = value
                self.changed.emit()
        qmlRegisterUncreatableType(Schema, "GSettings", 1, 0, "Schema", "Owned by GSettings")
        qmlRegisterType(Settings, "GSettings", 1, 0, "GSettings")
        source = Path(__file__).resolve().parents[1] / "qml/Glass"
        for name in ("NativeBackend.qml", "GlassStrings.js"):
            shutil.copyfile(source / name, base / name)
        engine = QQmlEngine()
        engine.addImportPath(str(base / "imports"))
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(base / "NativeBackend.qml")))
        backend = component.create()
        if backend is None:
            raise AssertionError([error.toString() for error in component.errors()])
        QTest.qWait(40)
        settings = backend.findChild(QObject, "fixtureSettings")
        assert settings is not None
        assert backend.property("automaticBrightnessCapability") == "needs-adaptation"
        assert not backend.property("automaticBrightnessAvailable")
        backend.setProperty("actionsAllowed", True)
        backend.setAutomaticBrightness(True)
        assert not settings.property("autoBrightness")
        checks.append("Unverified ALS profile rejects a toggle even when actions are allowed")
        backend.setProperty("automaticBrightnessProfileVerified", True)
        backend.setAutomaticBrightness(True)
        assert settings.property("autoBrightness") and backend.property("brightnessAutomatic")
        assert not backend.property("brightnessAvailable")
        checks.append("Verified-profile request follows GSettings readback and disables manual input in automatic mode")
        backend.setProperty("automaticBrightnessProfileVerified", False)
        backend.setAutomaticBrightness(False)
        assert settings.property("autoBrightness")
        checks.append("Revoked profile cannot silently disable the saved automatic preference")
        settings.setProperty("autoBrightness", False)
        power_model = backend.findChild(QObject, "org.ayatana.indicator.power")
        assert power_model is not None and backend.property("brightnessStateKnown")
        power_model.setProperty("nameOwner", "")
        assert not backend.property("brightnessDirectReady")
        assert not backend.property("brightnessStateKnown")
        assert not backend.property("brightnessAvailable")
        checks.append("Power service disappearance revokes stale brightness state and capability")
        backend.deleteLater()
        QTest.qWait(5)
    problems = [m for m in messages if any(token in m for token in ("ReferenceError", "TypeError", "Binding loop", "Cannot assign", "Unable to assign", "is not a type"))]
    assert not problems, problems
    report = {"result": "pass", "checks": checks, "scope": "Production QML with inert service fixtures; no real bus or hardware"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
