"""MTP event/reducer fixtures. Never access a bus, kernel event source or phone."""
import contextlib
import importlib.util
import io
from pathlib import Path
import socket
import unittest


PATH = Path(__file__).resolve().parents[1] / "tools/mtp-reconnect/mtp-usb-watcher.py"
SPEC = importlib.util.spec_from_file_location("mtp_watcher", PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.gate = mod.Gate(self.calls.append)
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def ready(self):
        self.gate.set_state("CONFIGURED")
        self.gate.set_mode("mtp_adb")

    def test_disconnected_boot_mtp_mode_never_starts(self):
        self.gate.set_state("DISCONNECTED")
        self.gate.set_mode("mtp_adb")
        self.assertEqual(self.calls, ["StopUnit"])

    def test_connected_not_configured_never_starts(self):
        self.gate.set_mode("mtp")
        self.gate.set_state("CONNECTED")
        self.assertEqual(self.calls, ["StopUnit"])

    def test_configured_mtp_clears_only_own_failure_then_reopens(self):
        self.ready()
        self.assertEqual(self.calls, ["StopUnit", "ResetFailedUnit", "RestartUnit"])

    def test_same_mode_reconnect_recovers_without_mode_flip(self):
        self.ready()
        self.calls.clear()
        self.gate.set_state("DISCONNECTED")
        self.gate.set_state("CONNECTED")
        self.gate.set_state("CONFIGURED")
        self.assertEqual(self.calls, ["StopUnit", "ResetFailedUnit", "RestartUnit"])

    def test_duplicates_do_not_restart_ongoing_transfer(self):
        self.ready()
        self.calls.clear()
        for _ in range(5):
            self.gate.set_state("CONFIGURED")
            self.gate.set_mode("mtp_adb")
        self.assertEqual(self.calls, [])

    def test_non_mtp_modes_are_never_started(self):
        self.gate.set_state("CONFIGURED")
        for mode in ("developer_mode", "rndis_adb", "charging_only", "undefined", "busy", None):
            self.gate.set_mode(mode)
        self.assertEqual(self.calls, ["StopUnit"])

    def test_busy_mode_stops_and_final_mode_restarts(self):
        self.ready()
        self.calls.clear()
        self.gate.set_mode("busy")
        self.gate.set_mode("mtp_adb")
        self.assertEqual(self.calls, ["StopUnit", "ResetFailedUnit", "RestartUnit"])

    def test_usb_moded_owner_loss_stops_until_fresh_mode(self):
        self.ready()
        self.calls.clear()
        self.gate.set_mode(None)
        self.assertEqual(self.calls, ["StopUnit"])
        self.gate.set_mode("mtp")
        self.assertEqual(self.calls[-2:], ["ResetFailedUnit", "RestartUnit"])

    def test_unit_error_is_not_retried_by_duplicate_event(self):
        self.gate.set_state("CONFIGURED")
        def fail(method):
            self.calls.append(method)
            raise RuntimeError("fixture error")
        self.gate.call = fail
        with self.assertRaises(RuntimeError):
            self.gate.set_mode("mtp_adb")
        self.gate.set_mode("mtp_adb")
        self.assertEqual(self.calls, ["StopUnit", "ResetFailedUnit"])

    def test_historical_configured_event_cannot_start_after_disconnect(self):
        self.gate.read_state = lambda: "DISCONNECTED"
        self.gate.set_mode("mtp_adb")
        self.gate.set_state("CONFIGURED")
        self.assertEqual(self.calls, ["StopUnit"])

    def test_disconnection_during_mode_query_blocks_stale_ready_state(self):
        self.gate.set_state("CONFIGURED")
        self.gate.read_state = lambda: "DISCONNECTED"
        self.gate.set_mode("mtp_adb")
        self.assertEqual(self.calls, ["StopUnit"])

    def test_disconnection_during_reset_never_requests_restart(self):
        states = iter(("CONFIGURED", "DISCONNECTED"))
        self.gate.read_state = lambda: next(states)
        self.gate.set_state("CONFIGURED")
        self.gate.set_mode("mtp_adb")
        self.assertEqual(self.calls, ["StopUnit", "ResetFailedUnit", "StopUnit"])

    def test_queued_configured_then_disconnected_never_starts_intermediate(self):
        self.gate.set_mode("mtp_adb")
        mod.apply_kernel_states(self.gate, ["CONFIGURED", "DISCONNECTED"])
        self.assertEqual(self.calls, ["StopUnit"])

    def test_queued_complete_cycle_reopens_descriptor_only_once(self):
        self.ready()
        self.calls.clear()
        mod.apply_kernel_states(self.gate, ["DISCONNECTED", "CONNECTED", "CONFIGURED"])
        self.assertEqual(self.calls, ["StopUnit", "ResetFailedUnit", "RestartUnit"])


class EventTests(unittest.TestCase):
    def event(self, **changes):
        properties = {"ACTION": "change", "DEVPATH": "/devices/virtual/android_usb/android0",
                      "SUBSYSTEM": "android_usb", "USB_STATE": "CONFIGURED", "SEQNUM": "123"}
        properties.update(changes)
        return ("change@/devices/virtual/android_usb/android0\0" +
                "\0".join(f"{k}={v}" for k, v in properties.items()) + "\0").encode("ascii")

    def test_exact_kernel_states(self):
        for state in ("CONFIGURED", "CONNECTED", "DISCONNECTED"):
            self.assertEqual(mod.parse_uevent(self.event(USB_STATE=state), (0, 1)), state)

    def test_userspace_and_truncated_messages_ignored(self):
        self.assertIsNone(mod.parse_uevent(self.event(), (1234, 1)))
        for flag in (socket.MSG_TRUNC, socket.MSG_CTRUNC):
            self.assertIsNone(mod.parse_uevent(self.event(), (0, 1), flag))

    def test_other_subsystem_device_action_state_ignored(self):
        for changes in ({"SUBSYSTEM": "udc"}, {"DEVPATH": "/devices/virtual/android_usb/android1"},
                        {"DEVPATH": "android0"}, {"ACTION": "remove"}, {"USB_STATE": "configured"}):
            self.assertIsNone(mod.parse_uevent(self.event(**changes), (0, 1)))

    def test_malformed_duplicate_or_oversized_messages_ignored(self):
        samples = (b"", self.event()[:-1], self.event() + b"USB_STATE=DISCONNECTED\0",
                   self.event().replace(b"SEQNUM=123", b"bad-field"),
                   self.event().replace(b"SEQNUM=123", b"SEQNUM=\xff"), b"x" * 65537)
        for data in samples:
            self.assertIsNone(mod.parse_uevent(data, (0, 1)))

    def test_native_binary_and_privacy_logic_are_not_overridden(self):
        source = PATH.read_text(encoding="utf-8")
        self.assertNotIn("set_mode", source.replace("def set_mode", "def receive_mode").replace("gate.set_mode", "gate.receive_mode"))
        self.assertNotIn("set_config", source)
        self.assertNotIn("IsActive", source)
        self.assertNotIn("forceSuspend", source)
        dropin = (PATH.parent / "mtp-server-reconnect.conf").read_text(encoding="utf-8")
        self.assertIn("Restart=no", dropin)
        self.assertNotIn("ExecStart", dropin)


if __name__ == "__main__":
    unittest.main()
