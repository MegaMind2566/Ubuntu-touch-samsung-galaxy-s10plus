#!/usr/bin/env python3
"""Exercise NativeBackend.qml with the real Qt 5 QMenuModel DBus bindings.

Requires PyQt5, libgio, dbus-run-session and the QMenuModel 1.0 QML plugin.
Optional LOMIRI_TEST_QML_IMPORT_PATH points at an unpacked native plugin tree.
No package installation or real session services are used. A private DBus is
created and native GSimpleActionGroups simulate indicator services. Only the
GSettings QML module is substituted, so auto-brightness policy can be controlled.
This verifies binding/protocol behavior, not handset hardware or sound policy.
"""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    if "--private-session" not in sys.argv:
        return subprocess.run([
            "dbus-run-session", "--", sys.executable, __file__, "--private-session"
        ], check=False).returncode

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    from PyQt5.QtCore import (QObject, QUrl, QVariant, QMetaObject, Q_ARG, Qt,
                              pyqtProperty, pyqtSignal, qInstallMessageHandler)
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtQml import (QQmlComponent, QQmlEngine, qmlRegisterType,
                             qmlRegisterUncreatableType)

    gio = C.CDLL("libgio-2.0.so.0")
    glib = C.CDLL("libglib-2.0.so.0")
    gobject = C.CDLL("libgobject-2.0.so.0")
    ptr, uint, boolean, char = C.c_void_p, C.c_uint, C.c_int, C.c_char_p

    def bind(lib, name, result, *arguments):
        function = getattr(lib, name)
        function.restype = result
        function.argtypes = arguments
        return function

    bus_get = bind(gio, "g_bus_get_sync", ptr, C.c_int, ptr, ptr)
    own_name = bind(gio, "g_bus_own_name_on_connection", uint, ptr, char, uint,
                    ptr, ptr, ptr, ptr)
    unown_name = bind(gio, "g_bus_unown_name", None, uint)
    group_new = bind(gio, "g_simple_action_group_new", ptr)
    action_new = bind(gio, "g_simple_action_new_stateful", ptr, char, ptr, ptr)
    add_action = bind(gio, "g_action_map_add_action", None, ptr, ptr)
    set_enabled = bind(gio, "g_simple_action_set_enabled", None, ptr, boolean)
    set_state = bind(gio, "g_simple_action_set_state", None, ptr, ptr)
    export_group = bind(gio, "g_dbus_connection_export_action_group", uint,
                        ptr, char, ptr, ptr)
    menu_new = bind(gio, "g_menu_new", ptr)
    export_menu = bind(gio, "g_dbus_connection_export_menu_model", uint,
                       ptr, char, ptr, ptr)
    type_new = bind(glib, "g_variant_type_new", ptr, char)
    type_free = bind(glib, "g_variant_type_free", None, ptr)
    new_bool = bind(glib, "g_variant_new_boolean", ptr, boolean)
    new_double = bind(glib, "g_variant_new_double", ptr, C.c_double)
    new_uint64 = bind(glib, "g_variant_new_uint64", ptr, C.c_uint64)
    get_type = bind(glib, "g_variant_get_type_string", char, ptr)
    get_bool = bind(glib, "g_variant_get_boolean", boolean, ptr)
    get_double = bind(glib, "g_variant_get_double", C.c_double, ptr)
    get_uint64 = bind(glib, "g_variant_get_uint64", C.c_uint64, ptr)
    iterate = bind(glib, "g_main_context_iteration", boolean, ptr, boolean)
    connect = bind(gobject, "g_signal_connect_data", C.c_ulong, ptr, char,
                   ptr, ptr, ptr, C.c_int)
    callback_type = C.CFUNCTYPE(None, ptr, ptr, ptr)
    app = QGuiApplication([])

    warnings = []
    qInstallMessageHandler(lambda kind, context, message: warnings.append(message))

    def pump(seconds=0.05):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            while iterate(None, False):
                pass
            time.sleep(0.001)

    def wait(predicate, message):
        until = time.monotonic() + 4
        while not predicate():
            if time.monotonic() >= until:
                raise AssertionError(message + "; QML diagnostics: " + repr(warnings))
            pump(0.01)

    def variant(value, signature=None):
        if signature == "t":
            return new_uint64(value)
        if isinstance(value, bool):
            return new_bool(value)
        return new_double(value)

    def decode(value):
        if not value:
            return None
        signature = get_type(value)
        if signature == b"b":
            return bool(get_bool(value))
        if signature == b"d":
            return get_double(value)
        if signature == b"t":
            return get_uint64(value)
        raise AssertionError("Unexpected native variant signature: " + repr(signature))

    calls = []
    connection = bus_get(2, None, None)  # G_BUS_TYPE_SESSION, inside private DBus.
    assert connection

    class Service:
        def __init__(self, bus, path, specifications):
            self.bus = bus
            self.group = group_new()
            self.menu = menu_new()
            self.actions = {}
            self.callbacks = []
            for name, state, parameter in specifications:
                parameter_type = type_new(parameter.encode()) if parameter else None
                action = action_new(name.encode(), parameter_type,
                                    variant(state, "t" if name == "volume-sync" else None))
                if parameter_type:
                    type_free(parameter_type)
                self.actions[name] = action
                for event in ("activate", "change-state"):
                    def callback(_action, value, _data, n=name, e=event):
                        calls.append((self.bus, n, e, decode(value)))
                    native_callback = callback_type(callback)
                    self.callbacks.append(native_callback)
                    connect(action, event.encode(), C.cast(native_callback, ptr),
                            None, None, 0)
                add_action(self.group, action)
            assert export_group(connection, path.encode(), self.group, None)
            assert export_menu(connection, (path + "/phone").encode(), self.menu, None)
            self.owner = 0
            self.appear()

        def appear(self):
            self.owner = own_name(connection, self.bus.encode(), 0, None, None, None, None)

        def vanish(self):
            unown_name(self.owner)
            self.owner = 0

        def state(self, name, value):
            set_state(self.actions[name], variant(value, "t" if name == "volume-sync" else None))

        def enabled(self, name, value):
            set_enabled(self.actions[name], value)

    network = Service("com.lomiri.indicator.network", "/com/lomiri/indicator/network", [
        ("wifi.enable", True, None), ("airplane.enabled", False, None),
        ("mobiledata.enabled", False, None),
    ])
    bluetooth = Service("org.ayatana.indicator.bluetooth", "/org/ayatana/indicator/bluetooth", [
        ("bluetooth-enabled", False, "b"), ("bluetooth-supported", True, None),
    ])
    power = Service("org.ayatana.indicator.power", "/org/ayatana/indicator/power", [
        ("brightness", 0.6, None),
    ])
    sound = Service("org.ayatana.indicator.sound", "/org/ayatana/indicator/sound", [
        ("volume", 0.4, "i"), ("silent-mode", False, "b"),
        ("volume-sync", 0, "t"), ("high-volume", False, None),
    ])
    display = Service("org.ayatana.indicator.display", "/org/ayatana/indicator/display", [
        ("rotation-lock", False, "b"),
    ])

    class Schema(QObject):
        changed = pyqtSignal()
        def __init__(self, parent=None):
            super().__init__(parent)
            self._id = ""
        @pyqtProperty(str, notify=changed)
        def id(self):
            return self._id
        @id.setter
        def id(self, value):
            self._id = value
            self.changed.emit()

    class Settings(QObject):
        changed = pyqtSignal()
        instances = []
        def __init__(self, parent=None):
            super().__init__(parent)
            self._schema = Schema(self)
            self._automatic = False
            Settings.instances.append(self)
        @pyqtProperty(Schema, constant=True)
        def schema(self):
            return self._schema
        @pyqtProperty(QVariant, notify=changed)
        def autoBrightness(self):
            return self._automatic
        def set_automatic(self, value):
            self._automatic = value
            self.changed.emit()

    qmlRegisterUncreatableType(Schema, "GSettings", 1, 0, "Schema", "Owned by GSettings")
    qmlRegisterType(Settings, "GSettings", 1, 0, "GSettings")
    engine = QQmlEngine()
    import_path = os.environ.get("LOMIRI_TEST_QML_IMPORT_PATH")
    if import_path:
        # A qml-only substitute would invalidate this test's native-binding claim.
        module = Path(import_path) / "QMenuModel.1" / "qmldir"
        assert "plugin " in module.read_text(), "QMenuModel must be a native plugin"
        engine.addImportPath(import_path)
    source = Path(__file__).resolve().parents[1] / "qml" / "Glass" / "NativeBackend.qml"
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(source)))
    backend = component.create()
    assert backend is not None, [error.toString() for error in component.errors()]
    policy_events = []
    backend.volumePolicyChanged.connect(lambda: policy_events.append(True))
    action_errors = []
    backend.actionError.connect(action_errors.append)

    def prop(name):
        value = backend.property(name)
        return value.toVariant() if hasattr(value, "toVariant") else value

    def invoke(method, value=None):
        if value is None:
            QMetaObject.invokeMethod(backend, method, Qt.DirectConnection)
        else:
            QMetaObject.invokeMethod(backend, method, Qt.DirectConnection, Q_ARG(QVariant, value))
        pump()

    checks = []
    available = ("wifi", "bluetooth", "airplane", "mobileData", "silent", "rotation", "brightness", "volume")
    wait(lambda: all(prop(name + "Available") for name in available),
         "Native action discovery failed")
    assert prop("wifiEnabled") is True and prop("volumeValue") == 0.4
    assert prop("bluetoothDirectReady") is True
    assert prop("brightnessDirectReady") is True
    assert prop("brightnessValue") == 0.6, "Brightness must be correct before touch"
    assert not calls
    checks.append("Stock QDBusActionGroup reads initial brightness and Bluetooth without touch or writes")

    for method in ("toggleWifi", "toggleBluetooth", "toggleAirplane", "toggleMobileData", "toggleSilent", "toggleRotation"):
        invoke(method)
    invoke("setVolume", 0.9)
    invoke("setBrightness", 0.2)
    assert not calls
    checks.append("Closed host gate rejects every action")

    backend.setProperty("actionsAllowed", True)
    for method in ("toggleWifi", "toggleAirplane", "toggleMobileData"):
        invoke(method)
    assert [call[3] for call in calls] == [None, None, None]
    assert prop("wifiEnabled") is True  # No optimistic local state update.
    checks.append("Network toggles have no parameters and remain server-authoritative")
    calls.clear()

    # A private analogue of the temporary uOS27 BlueZ bridge must win over
    # an indicator whose rfkill-backed action reports contradictory state.
    bluetooth.state("bluetooth-enabled", True)
    bluez = Service("org.uos27.Control", "/org/uos27/Control", [
        ("bluetooth-enabled", False, "b"),
    ])
    wait(lambda: prop("bluezBridgeReady") is True and prop("bluetoothEnabled") is False,
         "The temporary BlueZ hardware observer did not override the indicator")
    invoke("toggleBluetooth")
    assert calls == [("org.uos27.Control", "bluetooth-enabled", "activate", True)], calls
    assert prop("bluetoothEnabled") is False
    bluez.state("bluetooth-enabled", True)
    wait(lambda: prop("bluetoothEnabled") is True and prop("_bluetoothAwaitingState") is False,
         "The actual hardware state did not acknowledge the requested Bluetooth change")
    calls.clear()
    checks.append("Unprivileged BlueZ bridge takes priority and waits for a true state readback")

    bluez.vanish()
    wait(lambda: prop("bluezBridgeReady") is False,
         "Vanished temporary hardware bridge was not removed from the UI")
    wait(lambda: prop("bluetoothEnabled") is True,
         "The original Bluetooth indicator did not resume observing after bridge expiry")
    checks.append("A bounded Bluetooth bridge disappears cleanly; native indicator remains as fallback")

    bluetooth.state("bluetooth-enabled", False)
    wait(lambda: prop("bluetoothEnabled") is False,
         "The original Bluetooth observer failed to update after bridge expiration")

    for method in ("toggleBluetooth", "toggleSilent", "toggleRotation"):
        invoke(method)
    assert [call[3] for call in calls] == [True, True, True]
    assert all(call[2] == "activate" for call in calls)
    checks.append("Bluetooth uses stock QDBusActionGroup and passes a typed Boolean activate parameter")
    calls.clear()

    network.enabled("wifi.enable", False)
    wait(lambda: not prop("wifiAvailable"), "Disabled action remained available")
    invoke("toggleWifi")
    assert not calls
    network.enabled("wifi.enable", True)
    bluetooth.state("bluetooth-supported", False)
    wait(lambda: not prop("bluetoothAvailable"), "Unsupported Bluetooth remained available")
    invoke("toggleBluetooth")
    assert not calls
    checks.append("Disabled native action and unsupported hardware are guarded")

    network.state("wifi.enable", False)
    sound.state("volume", 0.25)
    power.state("brightness", 0.37)
    wait(lambda: prop("wifiEnabled") is False and prop("volumeValue") == 0.25,
         "Server state failed to propagate")
    wait(lambda: abs(prop("brightnessValue") - 0.37) < 1e-8,
         "Brightness changed by service did not propagate to the slider")
    assert not calls
    checks.append("Inbound service changes update UI state without writeback")

    settings = Settings.instances[0]
    settings.set_automatic(True)
    wait(lambda: prop("brightnessAutomatic") and not prop("brightnessAvailable"),
         "Automatic brightness did not block manual control")
    invoke("setBrightness", 0.2)
    assert not calls and settings._automatic is True
    settings.set_automatic(None)
    pump()
    assert not prop("brightnessAvailable")
    settings.set_automatic(False)
    wait(lambda: prop("brightnessAvailable"), "Manual brightness did not recover")
    checks.append("Automatic and unknown brightness policies block writes without policy changes")

    invoke("setBrightness", 0.8)
    invoke("setVolume", 0.1)
    assert [(call[1], call[2], call[3]) for call in calls] == [
        ("brightness", "change-state", 0.8), ("volume", "change-state", 0.1)], (calls, action_errors, warnings)
    calls.clear()
    invoke("setBrightness", 2.0)
    invoke("setVolume", -0.5)
    assert [(call[1], call[2], call[3]) for call in calls] == [
        ("brightness", "change-state", 1.0), ("volume", "change-state", 0.0)], (calls, action_errors, warnings)
    calls.clear()
    invoke("setVolume", float("nan"))
    invoke("setVolume", "0.5")
    assert not calls
    checks.append("Sliders request normalized double change-state; invalid values are rejected")

    old_policy_events = len(policy_events)
    sound.state("volume-sync", 1)
    sound.state("high-volume", True)
    sound.state("volume", 0.2)
    wait(lambda: len(policy_events) > old_policy_events and prop("highVolumeWarning")
         and prop("volumeValue") == 0.2, "Native policy reset did not propagate")
    assert not calls
    checks.append("Native volume-sync and policy reset propagate without replaying rejected value")

    network.vanish()
    wait(lambda: not prop("wifiAvailable") and not prop("airplaneAvailable"),
         "Vanished service remained available")
    invoke("toggleWifi")
    assert not calls
    network.appear()
    wait(lambda: prop("wifiAvailable") and prop("airplaneAvailable"),
         "Reappearing service did not restore actions")
    assert not calls
    checks.append("Service disappearance is guarded and reconnection restores live state")

    backend.setProperty("actionsAllowed", False)
    invoke("setVolume", 0.8)
    assert not calls
    assert not warnings, warnings
    checks.append("Revoked host gate discards a pending UI request")
    print(json.dumps({
        "result": "pass", "checks": checks,
        "runtime": "Qt 5 / real native QMenuModel over a private DBus with GSimpleActionGroup services",
        "limits": ["GSettings QML module simulated", "No handset hardware validation",
                   "Sound service warning policy source-inspected; policy signals simulated"]
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
