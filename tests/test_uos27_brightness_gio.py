"""Real Gio actions/async DBus against a private fake repowerd; never system bus."""
import importlib.util
import os
from pathlib import Path
import time
import unittest

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except ImportError:
    Gio = GLib = None

SPEC = importlib.util.spec_from_file_location(
    "radio_bridge", Path(__file__).resolve().parents[1] / "scripts/uos27_radio_bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


@unittest.skipUnless(Gio is not None and os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
                     "Requires Python Gio and a private dbus-run-session")
class BrightnessGioTests(unittest.TestCase):
    def wait(self, predicate, seconds=1.5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while self.context.pending():
                self.context.iteration(False)
            if predicate():
                return
            time.sleep(0.002)
        self.fail("private bus condition deadline exceeded")

    def name(self, method):
        args = GLib.Variant("(su)", (bridge.REPOWERD_NAME, 0)) if method == "RequestName" else GLib.Variant("(s)", (bridge.REPOWERD_NAME,))
        return self.server.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                     "org.freedesktop.DBus", method, args, None,
                                     Gio.DBusCallFlags.NONE, 1000, None)

    def setUp(self):
        self.context = GLib.MainContext.default()
        flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        self.server = Gio.DBusConnection.new_for_address_sync(os.environ["DBUS_SESSION_BUS_ADDRESS"], flags, None, None)
        self.client = Gio.DBusConnection.new_for_address_sync(os.environ["DBUS_SESSION_BUS_ADDRESS"], flags, None, None)
        self.supported, self.hold, self.calls = False, False, 0
        self.invocations = []
        node = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="com.lomiri.Repowerd">
          <method name="getBrightnessParams"><arg type="(iiiib)" direction="out"/></method>
          </interface></node>''')
        def method(connection, sender, path, interface, name, parameters, invocation):
            self.assertEqual(name, "getBrightnessParams")
            self.calls += 1
            if self.hold:
                self.invocations.append(invocation)
            else:
                invocation.return_value(GLib.Variant("((iiiib))", ((10, 10, 255, 102, self.supported),)))
        self.registration = self.server.register_object(bridge.REPOWERD_PATH, node.interfaces[0], method, None, None)
        self.name("RequestName")
        self.group = Gio.SimpleActionGroup.new()
        self.actions = bridge.BrightnessCapabilityActions(Gio, GLib, self.group)
        self.export = self.server.export_action_group(bridge.ACTION_PATH, self.group)
        self.remote = Gio.DBusActionGroup.get(self.client, self.server.get_unique_name(), bridge.ACTION_PATH)
        self.remote.list_actions()
        self.reader = bridge.RepowerdCapabilityReader(self.client, Gio, GLib, self.actions.publish)

    def tearDown(self):
        self.reader.close()
        for invocation in self.invocations:
            invocation.return_dbus_error("org.example.Test.Ended", "Private fixture finished")
        self.server.unexport_action_group(self.export)
        self.server.unregister_object(self.registration)
        self.server.close_sync(None)
        self.client.close_sync(None)

    def state(self, name):
        value = self.remote.get_action_state(name)
        return None if value is None else value.unpack()

    def test_real_action_readback_is_known_false_and_remote_mutation_is_ignored(self):
        self.reader.start()
        self.wait(lambda: self.state(bridge.BRIGHTNESS_KNOWN) is True)
        self.assertIs(self.state(bridge.BRIGHTNESS_SUPPORTED), False)
        self.assertFalse(self.remote.get_action_enabled(bridge.BRIGHTNESS_SUPPORTED))
        completed = []
        def done(connection, result, data):
            connection.call_finish(result)
            completed.append(True)
        # Wait for the real action server's reply, rather than assuming a queued
        # client mutation was delivered before asserting unchanged readback.
        self.client.call(self.server.get_unique_name(), bridge.ACTION_PATH,
                         "org.gtk.Actions", "SetState",
                         GLib.Variant("(sva{sv})", (bridge.BRIGHTNESS_SUPPORTED,
                                                  GLib.Variant("b", True), {})),
                         GLib.VariantType.new("()"), Gio.DBusCallFlags.NONE,
                         1000, None, done, None)
        self.wait(lambda: bool(completed))
        self.assertIs(self.actions.actions[bridge.BRIGHTNESS_SUPPORTED].get_state().unpack(), False)
        self.assertEqual(self.calls, 1)

    def test_name_owner_loss_then_return_refreshes_without_polling(self):
        self.reader.start()
        self.wait(lambda: self.state(bridge.BRIGHTNESS_KNOWN) is True)
        self.name("ReleaseName")
        self.wait(lambda: self.state(bridge.BRIGHTNESS_KNOWN) is False)
        self.assertIs(self.state(bridge.BRIGHTNESS_SUPPORTED), False)
        self.supported = True
        self.name("RequestName")
        self.wait(lambda: self.state(bridge.BRIGHTNESS_KNOWN) is True
                  and self.state(bridge.BRIGHTNESS_SUPPORTED) is True)
        self.assertEqual(self.calls, 2)

    def test_native_timeout_stays_unknown_and_does_not_retry(self):
        self.hold = True
        self.reader.start()
        self.wait(lambda: self.calls == 1)
        self.wait(lambda: self.reader.pending is None, seconds=3.8)
        self.assertFalse(self.actions.actions[bridge.BRIGHTNESS_KNOWN].get_state().unpack())
        self.assertFalse(self.actions.actions[bridge.BRIGHTNESS_SUPPORTED].get_state().unpack())
        self.assertEqual(self.calls, 1)


if __name__ == "__main__":
    unittest.main()
