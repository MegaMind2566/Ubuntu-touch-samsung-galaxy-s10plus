"""Real Gio to a private mock user systemd; never connect to a real system bus."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import threading
import unittest

try:
    from gi.repository import Gio, GLib
except ImportError:
    Gio = GLib = None

SPEC = importlib.util.spec_from_file_location(
    "mtp_watcher", Path(__file__).resolve().parents[1] / "tools/mtp-reconnect/mtp-usb-watcher.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


@unittest.skipUnless(Gio is not None and os.environ.get("DBUS_SESSION_BUS_ADDRESS")
                     and os.environ.get("S10_MTP_PRIVATE_BUS") == "1",
                     "Requires Gio and a private dbus-run-session")
class PrivateUnitTests(unittest.TestCase):
    def setUp(self):
        self.calls, self.failure = [], None
        self.ready = threading.Event()
        self.context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.context, False)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        self.assertTrue(self.ready.wait(3), "private server did not become ready")
        flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        self.client = Gio.DBusConnection.new_for_address_sync(os.environ["DBUS_SESSION_BUS_ADDRESS"], flags, None, None)
        self.proxy = Gio.DBusProxy.new_sync(self.client,
            Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS,
            None, "org.freedesktop.systemd1", "/org/freedesktop/systemd1", "org.freedesktop.systemd1.Manager", None)
        self.control = mod.UnitControl(self.proxy, Gio, GLib)

    def serve(self):
        self.context.push_thread_default()
        flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        connection = Gio.DBusConnection.new_for_address_sync(os.environ["DBUS_SESSION_BUS_ADDRESS"], flags, None, None)
        xml = '''<node><interface name="org.freedesktop.systemd1.Manager">
          <method name="StopUnit"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
          <method name="RestartUnit"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
          <method name="ResetFailedUnit"><arg type="s" direction="in"/></method>
          </interface></node>'''
        node = Gio.DBusNodeInfo.new_for_xml(xml)
        def method(_connection, _sender, _path, _interface, name, parameters, invocation):
            self.calls.append((name, parameters.get_type_string(), parameters.unpack()))
            if name == self.failure:
                invocation.return_dbus_error("org.example.Fixture.Refused", "fixture error")
            elif name == "ResetFailedUnit":
                invocation.return_value(GLib.Variant("()", ()))
            else:
                invocation.return_value(GLib.Variant("(o)", ("/org/freedesktop/systemd1/job/1",)))
        registration = connection.register_object("/org/freedesktop/systemd1", node.interfaces[0], method, None, None)
        connection.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "RequestName", GLib.Variant("(su)", ("org.freedesktop.systemd1", 0)), None,
            Gio.DBusCallFlags.NONE, 1000, None)
        self.ready.set()
        self.loop.run()
        connection.unregister_object(registration)
        connection.close_sync(None)
        self.context.pop_thread_default()

    def tearDown(self):
        self.client.close_sync(None)
        self.loop.quit()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def test_actual_signatures_and_same_mode_reconnect(self):
        gate = mod.Gate(self.control)
        with contextlib.redirect_stdout(io.StringIO()):
            gate.set_state("DISCONNECTED")
            gate.set_mode("mtp_adb")
            gate.set_state("CONFIGURED")
            gate.set_state("DISCONNECTED")
            gate.set_state("CONFIGURED")
        self.assertEqual(self.calls, [
            ("StopUnit", "(ss)", (mod.UNIT, "replace")),
            ("ResetFailedUnit", "(s)", (mod.UNIT,)),
            ("RestartUnit", "(ss)", (mod.UNIT, "replace")),
            ("StopUnit", "(ss)", (mod.UNIT, "replace")),
            ("ResetFailedUnit", "(s)", (mod.UNIT,)),
            ("RestartUnit", "(ss)", (mod.UNIT, "replace"))])

    def test_real_bus_error_stops_sequence_without_start_or_retry(self):
        gate = mod.Gate(self.control)
        with contextlib.redirect_stdout(io.StringIO()):
            gate.set_state("CONFIGURED")
            self.failure = "ResetFailedUnit"
            with self.assertRaises(GLib.Error):
                gate.set_mode("mtp_adb")
            gate.set_mode("mtp_adb")
        self.assertEqual([call[0] for call in self.calls], ["StopUnit", "ResetFailedUnit"])


if __name__ == "__main__":
    unittest.main()
