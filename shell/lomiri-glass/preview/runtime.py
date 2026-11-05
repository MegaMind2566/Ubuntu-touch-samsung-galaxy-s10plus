#!/usr/bin/env python3
"""Isolated Qt 5 preview fixture; never talks to the session/system D-Bus."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QSG_RENDER_LOOP", "basic")

from PyQt5.QtCore import QObject, QUrl, QEventLoop, QTimer, QCoreApplication, QEvent, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt5 import sip
from PyQt5.QtGui import QGuiApplication, QFontDatabase, QFont
from PyQt5.QtQuick import QQuickView
from PyQt5.QtTest import QTest


DEFAULTS = {
    "actionsAllowed": True,
    "wifiAvailable": True,
    "wifiEnabled": True,
    "bluetoothAvailable": True,
    "bluetoothEnabled": True,
    "airplaneAvailable": True,
    "airplaneEnabled": False,
    "mobileDataAvailable": True,
    "mobileDataEnabled": False,
    "silentAvailable": True,
    "silentEnabled": False,
    "rotationAvailable": True,
    "rotationLocked": False,
    "brightnessAvailable": True,
    "brightnessAutomatic": False,
    "automaticBrightnessAvailable": False,
    "automaticBrightnessSupportKnown": False,
    "ambientLuxAvailable": False,
    "brightnessValue": 0.64,
    "volumeAvailable": True,
    "volumeValue": 0.42,
}


def fixture_property(name: str, notify):
    return pyqtProperty(
        bool if isinstance(DEFAULTS[name], bool) else float,
        lambda self, key=name: self.values[key],
        notify=notify,
    )


class MockBackend(QObject):
    """Action requests deliberately do not mutate server-authoritative state."""

    changed = pyqtSignal()
    actionError = pyqtSignal(str)
    volumePolicyChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = dict(DEFAULTS)
        self.calls: list[tuple] = []

    for _key in DEFAULTS:
        locals()[_key] = fixture_property(_key, changed)
    del _key

    def set_state(self, **values):
        unknown = set(values) - set(DEFAULTS)
        if unknown:
            raise KeyError(unknown)
        self.values.update(values)
        self.changed.emit()

    def reset(self):
        self.calls.clear()
        self.values = dict(DEFAULTS)
        self.changed.emit()

    @pyqtSlot()
    def toggleWifi(self):
        self.calls.append(("wifi",))

    @pyqtSlot()
    def toggleBluetooth(self):
        self.calls.append(("bluetooth",))

    @pyqtSlot()
    def toggleAirplane(self):
        self.calls.append(("airplane",))

    @pyqtSlot()
    def toggleMobileData(self):
        self.calls.append(("mobileData",))

    @pyqtSlot()
    def toggleSilent(self):
        self.calls.append(("silent",))

    @pyqtSlot()
    def toggleRotation(self):
        self.calls.append(("rotation",))

    @pyqtSlot(float)
    def setBrightness(self, value):
        self.calls.append(("brightness", value))

    @pyqtSlot(float)
    def setVolume(self, value):
        self.calls.append(("volume", value))

    @pyqtSlot(bool)
    def setAutomaticBrightness(self, value):
        self.calls.append(("automaticBrightness", value))


def create_view(width=412, height=915):
    app = QGuiApplication.instance() or QGuiApplication([])
    # Qt's Windows offscreen plugin may expose no system fonts. Load the
    # installed font for this process only; never copy or redistribute it.
    if not QFontDatabase().families() and os.name == "nt":
        font_file = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
        if font_file.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_file))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0]))
    if not QFontDatabase().families():
        raise RuntimeError("No fonts available: install a free system font before rendering")
    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    backend = MockBackend(view)
    view.rootContext().setContextProperty("mockBackend", backend)
    view.setSource(QUrl.fromLocalFile(str(Path(__file__).with_name("Preview.qml"))))
    if view.status() == QQuickView.Error:
        raise RuntimeError("\n".join(error.toString() for error in view.errors()))
    view.resize(width, height)
    view.show()
    QTest.qWait(150)
    return app, view, backend


def save_screenshot(view, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    QTest.qWait(100)
    shot = view.grabWindow()
    if shot.isNull():
        # Qt's offscreen platform can expose the QQuickWindow while not providing
        # a platform-window screenshot. Item grabbing still renders the actual
        # QML scene and delivers its frame asynchronously.
        grab = view.rootObject().grabToImage()
        if grab is None:
            raise RuntimeError("Qt could not schedule a QQuickItem frame grab")
        loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        grab.ready.connect(loop.quit)
        timeout.start(3000)
        loop.exec_()
        timeout.stop()
        shot = grab.image()
    if shot.isNull() or not shot.save(str(destination)):
        raise RuntimeError(f"Could not capture actual Qt frame to {destination}")
    return {"path": str(destination), "width": shot.width(), "height": shot.height()}


def dispose_view(view):
    """Destroy window and QQmlEngine while their application/models still live.

    Closing a QWindow only hides it. Letting Python's frame/interpreter teardown
    destroy QGuiApplication first can leave QQmlThread and SIP wrappers alive.
    Explicit deferred deletion preserves Qt's ordinary GUI-thread lifecycle.
    """
    view.close()
    view.setSource(QUrl())
    view.engine().collectGarbage()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    if not sip.isdeleted(view):
        raise RuntimeError("The fixture window/engine was not destroyed before application teardown")
