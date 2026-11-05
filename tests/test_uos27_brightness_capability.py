import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SPEC = importlib.util.spec_from_file_location(
    "radio_bridge", Path(__file__).resolve().parents[1] / "scripts/uos27_radio_bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class Variant:
    def __init__(self, value, signature="((iiiib))"):
        self.value, self.signature = value, signature
    def unpack(self):
        return self.value
    def get_type_string(self):
        return self.signature


class Cancel:
    def __init__(self):
        self.cancelled = False
    def cancel(self):
        self.cancelled = True


class Connection:
    def __init__(self):
        self.calls, self.unsubscribed = [], []
    def signal_subscribe(self, *args):
        self.subscription = args
        return 19
    def signal_unsubscribe(self, identity):
        self.unsubscribed.append(identity)
    def call(self, *args):
        self.calls.append(args)
    def call_finish(self, result):
        if isinstance(result, Exception):
            raise result
        return result
    def finish(self, value, index=-1):
        call = self.calls[index]
        call[-2](self, value, call[-1])


class BrightnessCapabilityTests(unittest.TestCase):
    def test_native_false_is_known_and_true_is_supported(self):
        self.assertIs(bridge.brightness_supported(Variant(((10, 10, 255, 102, False),))), False)
        self.assertIs(bridge.brightness_supported(Variant(((10, 10, 255, 102, True),))), True)

    def test_malformed_signature_tuple_bool_or_range_is_unknown(self):
        invalid = [None, (), ((10, 10, 255, 102, 1),), ((10, 10, 255, 102, "false"),),
                   ((10, 10, 255, 102, False), False), ((10, 10, 255, False, True),),
                   ((10, -1, 255, 102, True),), ((10, 10, 0, 102, True),),
                   ((10, 100, 255, 99, True),), ((256, 10, 255, 102, True),),
                   ((10, 10, 2**31, 102, True),), [ [10, 10, 255, 102, True] ]]
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(bridge.brightness_supported(value))
        self.assertIsNone(bridge.brightness_supported(Variant(((10, 10, 255, 102, True),), "(v)")))

    def reader(self):
        connection, updates = Connection(), []
        gio = SimpleNamespace(Cancellable=SimpleNamespace(new=Cancel),
                              DBusCallFlags=SimpleNamespace(NO_AUTO_START=1),
                              DBusSignalFlags=SimpleNamespace(NONE=0))
        glib = SimpleNamespace(VariantType=SimpleNamespace(new=lambda text: text))
        reader = bridge.RepowerdCapabilityReader(connection, gio, glib, updates.append)
        reader.start()
        return reader, connection, updates

    def test_only_bounded_read_method_and_owner_signal_are_used(self):
        reader, connection, updates = self.reader()
        self.assertEqual(updates, [None])
        call = connection.calls[0]
        self.assertEqual(call[:6], (bridge.REPOWERD_NAME, bridge.REPOWERD_PATH,
                                   bridge.REPOWERD_NAME, "getBrightnessParams", None, "((iiiib))"))
        self.assertEqual(call[6:8], (1, 3000))
        self.assertEqual(connection.subscription[:5],
                         ("org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged",
                          "/org/freedesktop/DBus", bridge.REPOWERD_NAME))
        connection.finish(Variant(((10, 10, 255, 102, False),)))
        self.assertEqual(updates, [None, False])
        self.assertEqual(len(connection.calls), 1)
        reader.close()

    def test_owner_loss_invalidates_and_stale_success_is_ignored(self):
        reader, connection, updates = self.reader()
        old_cancel = connection.calls[0][-3]
        reader.owner_changed(None, None, None, None, None,
                             Variant((bridge.REPOWERD_NAME, ":1.2", "")), None)
        self.assertTrue(old_cancel.cancelled)
        connection.finish(Variant(((10, 10, 255, 102, True),)), 0)
        self.assertEqual(updates[-1], None)
        self.assertEqual(len(connection.calls), 1)
        reader.owner_changed(None, None, None, None, None,
                             Variant((bridge.REPOWERD_NAME, "", ":1.3")), None)
        self.assertEqual(len(connection.calls), 2)
        connection.finish(Variant(((10, 10, 255, 102, True),)))
        self.assertIs(updates[-1], True)
        reader.close()

    def test_timeout_malformed_and_closed_reader_fail_unavailable(self):
        for result in (TimeoutError(), Variant(((10, 10, 255, 102, 3),))):
            reader, connection, updates = self.reader()
            connection.finish(result)
            self.assertIsNone(updates[-1])
            reader.close()
            connection.finish(Variant(((10, 10, 255, 102, True),)))
            self.assertIsNone(updates[-1])
            self.assertEqual(connection.unsubscribed, [19])

    def test_existing_bluetooth_parser_contract_is_preserved(self):
        objects = {"/org/bluez/hci0": {bridge.BLUEZ_IFACE: {}},
                   "/org/bluez/hci0/dev_private": {"org.bluez.Device1": {}},
                   "/other": {bridge.BLUEZ_IFACE: {}}}
        self.assertEqual(bridge.adapter_paths(objects), ("/org/bluez/hci0",))
        self.assertEqual(bridge.ACTION_NAME, "bluetooth-enabled")
        self.assertEqual(bridge.SESSION_NAME, "org.uos27.Control")


if __name__ == "__main__":
    unittest.main()
