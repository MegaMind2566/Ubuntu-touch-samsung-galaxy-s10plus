#!/usr/bin/env python3
"""Verify vector/status classification using real Qt 5 QML bindings.

No hardware state is invented. Unrecognised icon names retain a native fallback.
"""
import argparse
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PyQt5.QtCore import QUrl, QT_VERSION_STR
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtQml import QQmlComponent, QQmlEngine


SOURCE = Path(__file__).resolve().parents[1] / "qml/Glass/GlassStatusIcon.qml"


class IndicatorVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        cls.engine = QQmlEngine()
        cls.component = QQmlComponent(cls.engine, QUrl.fromLocalFile(str(SOURCE)))
        if cls.component.isError():
            raise AssertionError([error.toString() for error in cls.component.errors()])

    def setUp(self):
        self.icon = self.component.create()
        self.assertIsNotNone(self.icon)

    def tearDown(self):
        self.icon.deleteLater()

    def check(self, source, kind, **values):
        self.icon.setProperty("iconSource", source)
        self.assertEqual(self.icon.property("kind"), kind, source)
        self.assertEqual(self.icon.property("supported"), kind != "native", source)
        for name, expected in values.items():
            self.assertEqual(self.icon.property(name), expected, source)

    def test_notification_dot_uses_native_unread_signal(self):
        self.check("image://theme/indicator-messages", "messages", unread=False)
        self.check("indicator-messages-new", "messages", unread=True)
        self.check("image://theme/messages-new", "messages", unread=True)

    def test_battery_charge_and_level_follow_real_icon_name(self):
        self.check("image://theme/battery-020,unity-battery-020", "battery",
                   batteryLevel=20, charging=False)
        self.check("image://theme/battery-045-charging", "battery",
                   batteryLevel=45, charging=True)
        self.check("image://theme/battery-fully-charged", "battery",
                   batteryLevel=100, charging=False)

    def test_connectivity_sound_and_unknown_icons(self):
        self.check("image://theme/wifi-high", "wifi", strength=3)
        self.check("image://theme/wifi-low", "wifi", strength=1)
        self.check("image://theme/nm-signal-00", "wifi", strength=0)
        self.check("image://theme/nm-signal-25-secure", "wifi", strength=1)
        self.check("image://theme/nm-signal-50", "wifi", strength=2)
        self.check("image://theme/nm-signal-75", "wifi", strength=3)
        self.check("image://theme/nm-signal-100-secure", "wifi", strength=3)
        self.check("image://theme/network-wired-disabled", "native")
        self.check("image://theme/cellular-signal-none", "cellular", strength=0)
        self.check("image://theme/cellular-signal-medium", "cellular", strength=2)
        self.check("image://theme/bluetooth-active", "bluetooth")
        self.check("image://theme/audio-volume-muted", "sound", strength=0)
        self.check("image://theme/system-devices-panel", "native")
        self.check("image://theme/simcard-error", "native")
        self.check("unknown-service-state", "native")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IndicatorVectorTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schema": 1, "scope": "Native icon-name mapping tested in real Qt 5 QML with synthetic icon names",
        "qt": QT_VERSION_STR, "tests": result.testsRun, "successful": result.wasSuccessful(),
        "not_validated": ["live indicator names on handset", "physical cutout geometry", "panel tap gesture"],
    }
    if options.report:
        options.report.parent.mkdir(parents=True, exist_ok=True)
        options.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
