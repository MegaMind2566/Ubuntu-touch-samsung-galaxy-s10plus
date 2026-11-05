#!/usr/bin/env python3
"""Exercise the real Qt 5 QML surface with controlled service states.

This suite covers UI input and bindings. It does not load Lomiri's D-Bus plugins,
test a handset, certify compositor performance, or validate notification storage.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "preview"))
from runtime import DEFAULTS, create_view

from PyQt5.QtCore import QPointF, Qt, QT_VERSION_STR, PYQT_VERSION_STR, qInstallMessageHandler, qVersion
from PyQt5.QtQuick import QQuickItem
from PyQt5.QtTest import QTest


MESSAGES: list[str] = []
APP = None


def capture_message(kind, context, message):
    MESSAGES.append(message)


class NativeQmlSurfaceTests(unittest.TestCase):
    def setUp(self):
        global APP
        MESSAGES.clear()
        APP, self.view, self.backend = create_view()
        self.root = self.view.rootObject()
        self.center = self.item("glassCenter")

    def tearDown(self):
        self.view.close()
        self.view.deleteLater()
        QTest.qWait(10)

    def item(self, name):
        value = self.view.rootObject().findChild(QQuickItem, name)
        self.assertIsNotNone(value, f"Expected QML test hook {name}")
        return value

    def click(self, item, local=None):
        if local is None:
            local = QPointF(item.width() / 2, item.height() / 2)
        QTest.mouseClick(self.view, Qt.LeftButton, Qt.NoModifier, item.mapToScene(local).toPoint())
        QTest.qWait(20)

    def reveal(self, item):
        ancestor = item.parentItem()
        while ancestor is not None:
            if ancestor.property("contentY") is not None and ancestor.property("contentHeight") is not None:
                center = item.mapToItem(ancestor, QPointF(item.width() / 2, item.height() / 2))
                old_y = float(ancestor.property("contentY"))
                max_y = max(0, float(ancestor.property("contentHeight")) - ancestor.height())
                ancestor.setProperty("contentY", max(0, min(max_y, old_y + center.y() - ancestor.height() / 2)))
                QTest.qWait(20)
            ancestor = ancestor.parentItem()

    def assert_no_qml_errors(self):
        problems = [message for message in MESSAGES if any(marker in message for marker in [
            "ReferenceError", "TypeError", "Binding loop", "Cannot assign", "is not a type",
            "Unable to assign", "Cannot read property", "is not a function",
        ])]
        self.assertEqual(problems, [], "\n".join(problems))

    def test_unverified_automatic_brightness_opens_native_settings_without_toggle(self):
        self.assertFalse(self.backend.property("automaticBrightnessAvailable"))
        tile = self.item("automaticBrightnessSettings")
        self.reveal(tile)
        self.click(tile)
        self.assertTrue(self.center.property("detailActive"))
        self.assertEqual(self.center.property("detailTitle"), "power")
        self.assertEqual(self.backend.calls, [])
        self.assert_no_qml_errors()

    def test_backend_updates_never_issue_actions(self):
        self.backend.set_state(wifiEnabled=False, bluetoothEnabled=False,
                               brightnessValue=0.2, volumeValue=0.7)
        QTest.qWait(100)
        self.assertEqual(self.backend.calls, [])
        self.assertFalse(self.item("wifiTile").property("checked"))
        self.assertFalse(self.item("bluetoothTile").property("checked"))
        self.assertAlmostEqual(self.item("brightnessSlider").property("value"), 0.2)
        self.assertAlmostEqual(self.item("volumeSlider").property("value"), 0.7)
        self.assertFalse(self.center.property("_feedbackVisible"),
                         "Unsolicited state updates must not create user-action popups")
        self.assert_no_qml_errors()

    def test_automatic_brightness_switch_waits_for_native_readback(self):
        self.backend.set_state(automaticBrightnessAvailable=True,
                               automaticBrightnessSupportKnown=True,
                               brightnessAutomatic=False)
        switch = self.item("automaticBrightnessSwitch")
        self.reveal(switch)
        self.click(switch)
        self.assertEqual(self.backend.calls, [("automaticBrightness", True)])
        self.assertFalse(switch.property("checked"))
        self.backend.set_state(brightnessAutomatic=True)
        QTest.qWait(30)
        self.assertTrue(switch.property("checked"))
        self.assertEqual(len(self.backend.calls), 1)
        self.backend.set_state(actionsAllowed=False)
        switch.requestToggle()
        self.assertEqual(len(self.backend.calls), 1)
        self.backend.set_state(actionsAllowed=True, automaticBrightnessAvailable=False)
        switch.requestToggle()
        self.assertEqual(len(self.backend.calls), 1)
        self.assert_no_qml_errors()

    def test_toggle_waits_for_authoritative_state(self):
        tile = self.item("wifiTile")
        self.click(tile)
        self.assertEqual(self.backend.calls, [("wifi",)])
        self.assertTrue(tile.property("checked"), "A request must not pretend the service accepted it")
        self.backend.set_state(wifiEnabled=False)
        QTest.qWait(20)
        self.assertFalse(tile.property("checked"))
        self.assertEqual(self.backend.calls, [("wifi",)])

    def test_bluetooth_tile_dispatches_a_real_request(self):
        tile = self.item("bluetoothTile")
        self.backend.set_state(bluetoothEnabled=False)
        self.click(tile)
        self.assertEqual(self.backend.calls, [("bluetooth",)])
        self.assertFalse(tile.property("checked"),
                         "Bluetooth must remain off until the service confirms a changed state")
        self.assertFalse(self.center.property("_feedbackVisible"),
                         "A submitted request cannot display a successful radio popup")
        self.backend.set_state(bluetoothEnabled=True)
        QTest.qWait(20)
        self.assertTrue(tile.property("checked"))
        self.assertTrue(self.item("uos27ControlFeedback").isVisible())
        self.assertIn("Bluetooth", self.center.property("_feedbackLabel"))

    def test_unavailable_and_disallowed_controls_are_inert(self):
        self.backend.set_state(wifiAvailable=False, bluetoothAvailable=False,
                               brightnessAvailable=False, volumeAvailable=False)
        QTest.qWait(20)
        self.click(self.item("wifiTile"))
        self.click(self.item("bluetoothTile"))
        self.assertEqual(self.backend.calls, [])
        self.backend.set_state(**DEFAULTS)
        self.backend.set_state(actionsAllowed=False)
        QTest.qWait(20)
        self.click(self.item("wifiTile"))
        self.assertEqual(self.backend.calls, [])

    def test_long_press_opens_details_without_toggle(self):
        tile = self.item("wifiTile")
        point = tile.mapToScene(QPointF(tile.width() / 2, tile.height() / 2)).toPoint()
        QTest.mousePress(self.view, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(1000)
        QTest.mouseRelease(self.view, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(20)
        self.assertEqual(self.backend.calls, [])
        self.assertTrue(self.center.property("detailActive"))

    def test_slider_requests_are_clamped_and_not_echoed(self):
        slider = self.item("brightnessSlider")
        self.reveal(slider)
        # The top half of the pill is a real pointer target, not a call to a
        # component helper function. The callback must carry a normalised value.
        self.click(slider, QPointF(slider.width() / 2, 6))
        sent = [call for call in self.backend.calls if call[0] == "brightness"]
        self.assertGreater(len(sent), 0)
        self.assertTrue(all(math.isfinite(call[1]) and 0 <= call[1] <= 1 for call in sent))
        before = len(self.backend.calls)
        self.backend.set_state(brightnessValue=sent[-1][1])
        QTest.qWait(100)
        self.assertEqual(len(self.backend.calls), before)

    def test_slider_feedback_is_acknowledged_not_optimistic(self):
        slider = self.item("brightnessSlider")
        self.reveal(slider)
        self.backend.set_state(brightnessValue=0.25)
        QTest.qWait(35)
        self.click(slider, QPointF(slider.width()/2, 6))
        self.assertTrue(self.center.property("_pendingBrightness"))
        self.assertFalse(self.center.property("_feedbackVisible"),
                         "A rejected brightness request must not be announced as successful")
        target = [call[1] for call in self.backend.calls if call[0] == "brightness"][-1]
        self.backend.set_state(brightnessValue=target)
        QTest.qWait(35)
        self.assertFalse(self.center.property("_pendingBrightness"))
        self.assertTrue(self.center.property("_feedbackVisible"))
        self.assert_no_qml_errors()

    def test_automatic_brightness_is_not_disabled_by_touch(self):
        slider = self.item("brightnessSlider")
        self.backend.set_state(brightnessAutomatic=True)
        QTest.qWait(20)
        self.reveal(slider)
        self.click(slider, QPointF(slider.width() / 2, 6))
        self.assertEqual(self.backend.calls, [])
        self.assertTrue(self.backend.brightnessAutomatic)

    def test_native_volume_policy_cancels_pending_and_release_replay(self):
        slider = self.item("volumeSlider")
        self.reveal(slider)
        top = slider.mapToScene(QPointF(slider.width() / 2, 6)).toPoint()
        moved = slider.mapToScene(QPointF(slider.width() / 2, 30)).toPoint()
        QTest.mousePress(self.view, Qt.LeftButton, Qt.NoModifier, top)
        QTest.qWait(90)
        self.assertTrue(slider.property("dragging"))
        self.assertGreater(len(self.backend.calls), 0)
        self.assertEqual(self.backend.calls[-1][0], "volume")
        # Queue another user value, then emulate the native indicator rejecting
        # the high-volume request and publishing its authoritative safe value.
        QTest.mouseMove(self.view, moved, 5)
        self.backend.set_state(volumeValue=0.23)
        self.backend.volumePolicyChanged.emit()
        before = len(self.backend.calls)
        QTest.qWait(90)
        self.assertFalse(slider.property("dragging"))
        self.assertAlmostEqual(slider.property("displayedValue"), 0.23)
        QTest.mouseMove(self.view, top, 5)
        QTest.qWait(90)
        QTest.mouseRelease(self.view, Qt.LeftButton, Qt.NoModifier, top)
        QTest.qWait(90)
        self.assertEqual(len(self.backend.calls), before,
                         "Neither the timer, a later move nor release may replay rejected volume")
        # A separate deliberate press remains possible after the policy event.
        self.click(slider, QPointF(slider.width() / 2, 90))
        self.assertGreater(len(self.backend.calls), before)
        self.assert_no_qml_errors()

    def test_permissions_and_automatic_changes_cancel_active_slider_gesture(self):
        slider = self.item("brightnessSlider")
        self.reveal(slider)
        point = slider.mapToScene(QPointF(slider.width() / 2, 6)).toPoint()
        for reason in ["actions-disallowed", "automatic", "disabled"]:
            with self.subTest(reason=reason):
                self.backend.reset()
                slider.setProperty("enabled", True)
                QTest.qWait(20)
                QTest.mousePress(self.view, Qt.LeftButton, Qt.NoModifier, point)
                self.assertTrue(slider.property("dragging"))
                if reason == "actions-disallowed":
                    self.backend.set_state(actionsAllowed=False)
                elif reason == "automatic":
                    self.backend.set_state(brightnessAutomatic=True)
                else:
                    slider.setProperty("enabled", False)
                QTest.qWait(90)
                self.assertFalse(slider.property("dragging"))
                self.assertAlmostEqual(slider.property("displayedValue"), self.backend.brightnessValue)
                QTest.mouseMove(self.view, point, 5)
                QTest.mouseRelease(self.view, Qt.LeftButton, Qt.NoModifier, point)
                QTest.qWait(90)
                self.assertEqual(self.backend.calls, [])
        self.assert_no_qml_errors()

    def test_supported_layouts_and_view_switch_are_loadable(self):
        for width, height in [(360, 780), (412, 915), (780, 360)]:
            with self.subTest(width=width, height=height):
                self.view.resize(width, height)
                QTest.qWait(40)
                self.assertAlmostEqual(self.center.width(), width)
                for name in ["wifiTile", "bluetoothTile", "airplaneTile", "mobileDataTile"]:
                    tile = self.item(name)
                    point = tile.mapToScene(QPointF(0, 0))
                    self.assertGreaterEqual(point.x(), -1)
                    self.assertLessEqual(point.x() + tile.width(), width + 1)
                    self.assertGreaterEqual(tile.height(), 48)
                self.center.setProperty("mode", "notifications")
                self.center.setProperty("nativePageAvailable", False)
                QTest.qWait(20)
                self.assert_no_qml_errors()
                self.center.setProperty("mode", "controls")
                self.center.setProperty("nativePageAvailable", True)

    def test_language_tracks_system_locale_and_light_surface(self):
        wifi = self.item("wifiTile")
        controls = self.item("airplaneTile")
        for locale, wifi_label, airplane_label in [
            ("it_IT", "Wi-Fi", "Aereo"),
            ("de_DE", "WLAN", "Flugmodus"),
            ("fr_FR", "Wi-Fi", "Avion"),
            ("es_ES", "Wi-Fi", "Avión"),
            ("pt_BR", "Wi-Fi", "Avião"),
            ("ja_JP", "Wi-Fi", "Airplane"),  # documented English fallback
        ]:
            with self.subTest(locale=locale):
                self.center.setProperty("language", locale)
                QTest.qWait(25)
                self.assertEqual(wifi.property("title"), wifi_label)
                self.assertEqual(controls.property("title"), airplane_label)
                self.assertEqual(wifi.property("language"), locale)
        self.center.setProperty("lightSurface", True)
        QTest.qWait(25)
        self.assertTrue(wifi.property("lightSurface"))
        self.assertTrue(self.item("brightnessSlider").property("lightSurface"))
        self.assert_no_qml_errors()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    qInstallMessageHandler(capture_message)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeQmlSurfaceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schema": 1,
        "scope": "Real Qt 5 QML input/binding/layout tests with simulated services",
        "not_validated": ["handset", "Lomiri D-Bus integration", "notification storage", "GPU performance"],
        "qt_compile_version": QT_VERSION_STR,
        "qt_runtime_version": qVersion(),
        "pyqt_version": PYQT_VERSION_STR,
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "successful": result.wasSuccessful(),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
