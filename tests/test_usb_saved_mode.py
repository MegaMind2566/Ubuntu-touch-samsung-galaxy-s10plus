"""Fixture-only tests: no system bus, handset or hardware access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools/usb-mode-restore/restore-saved-mode.py"
SPEC = importlib.util.spec_from_file_location("usb_saved_mode", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.now = 0
        self.responses = {"mode_request": ["developer_mode", "mtp_adb"],
                          "get_config": ["mtp_adb"], "get_available_modes": ["mtp, mtp_adb, rndis, charging_only"],
                          "set_mode": ["mtp_adb"]}
        for target, kwargs in (("effective_uid", {"return_value": 0}),
                               ("kernel_release", {"return_value": mod.KERNEL_RELEASE}),
                               ("exists", {"side_effect": lambda path: path == mod.INIT_DONE})):
            patcher = mock.patch.object(mod, target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(mod.subprocess, "run", side_effect=self.gdbus)
        self.runner = patcher.start()
        self.addCleanup(patcher.stop)
        for target, effect in (("monotonic", lambda: self.now), ("sleep", self.advance)):
            patcher = mock.patch.object(mod, target, side_effect=effect, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def advance(self, seconds):
        self.now += seconds

    def gdbus(self, command, **kwargs):
        self.assertEqual(command[:2], ["/usr/bin/gdbus", "call"])
        self.assertIn("--system", command)
        self.assertGreater(kwargs["timeout"], 0)
        self.assertLessEqual(kwargs["timeout"], 3)
        method = command[command.index("--method") + 1].removeprefix("com.meego.usb_moded.")
        self.calls.append((method, command[command.index("--method") + 2:]))
        queue = self.responses[method]
        return subprocess.CompletedProcess(command, 0, repr((queue.pop(0) if len(queue) > 1 else queue[0],)).encode())

    def run_helper(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = mod.main()
        return status, json.loads(output.getvalue())

    def test_restores_saved_mode_once_and_verifies_current_mode(self):
        status, report = self.run_helper()
        self.assertEqual((status, report["event"], report["mode"]), (0, "restored", "mtp_adb"))
        self.assertEqual(self.calls, [("mode_request", []), ("get_config", []),
                         ("get_available_modes", []), ("set_mode", ["mtp_adb"]), ("mode_request", [])])

    def test_guard_skips_do_not_query_or_change_usb(self):
        cases = (("kernel_release", {"return_value": "different-kernel"}, "kernel-mismatch"),
                 ("exists", {"return_value": True}, "force-marker"),
                 ("exists", {"return_value": False}, "init-not-done"))
        for target, kwargs, reason in cases:
            with self.subTest(reason=reason), mock.patch.object(mod, target, **kwargs):
                status, report = self.run_helper()
                self.assertEqual((status, report["reason"]), (0, reason))
                self.assertEqual(self.calls, [])

    def test_busy_readback_waits_but_never_repeats_mutation(self):
        self.responses["mode_request"] = ["developer_mode", "busy", "busy", "mtp_adb"]
        self.assertEqual(self.run_helper()[1]["event"], "restored")
        self.assertAlmostEqual(self.now, 0.4)
        self.assertEqual(sum(name == "set_mode" for name, _ in self.calls), 1)

    def test_non_root_refuses_without_query(self):
        with mock.patch.object(mod, "effective_uid", return_value=32011):
            status, report = self.run_helper()
        self.assertEqual((status, report["reason"]), (1, "root-required"))
        self.assertEqual(self.calls, [])

    def test_each_force_marker_preserves_porter_override(self):
        for marker in mod.MARKERS:
            with self.subTest(marker=marker), mock.patch.object(mod, "exists", side_effect=lambda path: path in (marker, mod.INIT_DONE)):
                self.assertEqual(self.run_helper()[1]["reason"], "force-marker")
        self.assertEqual(self.calls, [])

    def test_intentional_developer_or_other_active_mode_is_preserved(self):
        for current, configured in (("developer_mode", "developer_mode"), ("mtp_adb", "mtp")):
            with self.subTest(current=current):
                self.responses["mode_request"] = [current]
                self.responses["get_config"] = [configured]
                self.assertEqual(self.run_helper()[1]["event"], "skipped")
                self.assertFalse(any(name == "set_mode" for name, _ in self.calls))

    def test_unsupported_or_unavailable_saved_mode_is_preserved(self):
        for configured in ("charging_only", "unknown_mode", "rndis_adb"):
            with self.subTest(configured=configured):
                self.responses["mode_request"] = ["developer_mode"]
                self.responses["get_config"] = [configured]
                self.responses["get_available_modes"] = ["mtp,mtp_adb,rndis"]
                self.assertEqual(self.run_helper()[1]["event"], "skipped")
                self.assertFalse(any(name == "set_mode" for name, _ in self.calls))

    def test_malformed_bus_responses_fail_before_mutation(self):
        for raw in (b"()", b"('mtp_adb', 'extra')", b"['mtp_adb']", b"('bad;command',)",
                    b"__import__('os').system('echo unsafe')", b"x" * 4097, b"\xff"):
            with self.subTest(raw=raw[:20]), mock.patch.object(mod.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0, raw)):
                self.assertEqual(self.run_helper()[0], 1)
        self.assertEqual(self.calls, [])

    def test_bus_timeout_failure_or_missing_tool_never_retries(self):
        for error in (subprocess.TimeoutExpired("private", 3), OSError("private")):
            with self.subTest(error=type(error).__name__), mock.patch.object(mod.subprocess, "run", side_effect=error) as runner:
                status, report = self.run_helper()
                self.assertEqual(status, 1)
                self.assertNotIn("private", json.dumps(report))
                self.assertEqual(runner.call_count, 1)
        with mock.patch.object(mod.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"private")):
            self.assertEqual(self.run_helper()[0], 1)

    def test_invalid_available_mode_list_does_not_mutate(self):
        self.responses["get_available_modes"] = ["mtp_adb,bad;command"]
        self.assertEqual(self.run_helper()[1]["reason"], "invalid-available-modes")
        self.assertFalse(any(name == "set_mode" for name, _ in self.calls))

    def test_timeout_during_set_mode_is_not_retried(self):
        def timeout_on_set(command, **kwargs):
            if "com.meego.usb_moded.set_mode" in command:
                self.calls.append(("set_mode", []))
                raise subprocess.TimeoutExpired(command, 3)
            return self.gdbus(command, **kwargs)
        with mock.patch.object(mod.subprocess, "run", side_effect=timeout_on_set):
            self.assertEqual(self.run_helper()[1]["reason"], "bus-timeout")
        self.assertEqual(sum(name == "set_mode" for name, _ in self.calls), 1)

    def test_poststate_mismatch_or_failed_mutation_is_visible_without_second_set(self):
        self.responses["mode_request"] = ["developer_mode", "developer_mode"]
        self.assertEqual(self.run_helper()[1]["reason"], "mode-readback-timeout")
        self.assertLessEqual(self.now, 5)
        self.assertLessEqual(sum(name == "mode_request" for name, _ in self.calls), 26)
        self.assertEqual(sum(name == "set_mode" for name, _ in self.calls), 1)
        self.calls.clear()
        self.responses.update(mode_request=["developer_mode"], get_config=["mtp_adb"],
                              get_available_modes=["mtp_adb"], set_mode=["undefined"])
        self.assertEqual(self.run_helper()[0], 1)
        self.assertEqual(sum(name == "set_mode" for name, _ in self.calls), 1)


if __name__ == "__main__":
    unittest.main()
