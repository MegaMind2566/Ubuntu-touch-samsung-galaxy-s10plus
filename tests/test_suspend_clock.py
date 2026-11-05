"""Clock fixtures and host CLI only; no handset or power controls."""
import contextlib
import hashlib
import hmac
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ut-s10-suspend-clock.py"
SPEC = importlib.util.spec_from_file_location("suspend_clock", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
SESSION = "ab" * 16


def fixture(boot=1000000000000, mono=900000000000):
    return {"schema": 1, "kind": "suspend-clock-snapshot", "session": SESSION,
            "boot_token": "cd" * 32, "device_time_utc": "2026-11-05T12:00:00+00:00",
            "kernel_release": "4.14.280-test", "errors": [],
            "clocks": {"boottime_ns": boot, "monotonic_ns": mono, "uncertainty_ns": 10}}


class ClockTests(unittest.TestCase):
    def test_bracket_uses_midpoint_and_uncertainty(self):
        with mock.patch.object(mod.time, "CLOCK_BOOTTIME", 10, create=True), \
                mock.patch.object(mod.time, "CLOCK_MONOTONIC", 11, create=True), \
                mock.patch.object(mod.time, "clock_gettime_ns", side_effect=[100, 70, 105], create=True) as clock:
            self.assertEqual(mod.sample_clocks(), {"boottime_ns": 102, "monotonic_ns": 70, "uncertainty_ns": 3})
        self.assertEqual([call.args[0] for call in clock.call_args_list], [10, 11, 10])

    def test_boot_token_is_session_hmac_without_raw_identity(self):
        raw = b"12345678-1234-1234-1234-123456789abc\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boot-id"
            path.write_bytes(raw)
            token = mod.read_boot_token(SESSION, path)
            self.assertEqual(token, hmac.new(bytes.fromhex(SESSION), raw.strip(), hashlib.sha256).hexdigest())
            self.assertNotEqual(token, mod.read_boot_token("01" * 16, path))
            for invalid in (b"x" * 129, b"private-invalid-id"):
                path.write_bytes(invalid)
                with self.assertRaises(mod.ClockError):
                    mod.read_boot_token(SESSION, path)

    def test_snapshot_reports_missing_clocks_and_boot_id_explicitly(self):
        with mock.patch.object(mod, "sample_clocks", side_effect=mod.ClockError("clocks-unavailable")), \
                mock.patch.object(mod, "read_boot_token", side_effect=mod.ClockError("boot-id-unavailable")):
            report = mod.snapshot(SESSION)
        self.assertIsNone(report["clocks"])
        self.assertIsNone(report["boot_token"])
        self.assertEqual(set(report["errors"]), {"clocks-unavailable", "boot-id-unavailable"})

    def test_suspend_interval_120_seconds(self):
        before = fixture()
        after = fixture(before["clocks"]["boottime_ns"] + 130000000000,
                        before["clocks"]["monotonic_ns"] + 10000000000)
        report = mod.compare(before, after)
        self.assertEqual(report["suspend_estimate_ns"], 120000000000)
        self.assertEqual(report["uncertainty_ns"], 20)
        self.assertEqual(report["suspend_interval_ns"], [119999999980, 120000000020])
        self.assertEqual(report["evidence"], "positive-suspend-time")

    def test_active_only_and_rounding_uncertainty_do_not_claim_suspend(self):
        before = fixture()
        for extra in (0, -5):
            after = fixture(before["clocks"]["boottime_ns"] + 1000000000 + extra,
                            before["clocks"]["monotonic_ns"] + 1000000000)
            self.assertEqual(mod.compare(before, after)["evidence"], "no-positive-suspend-time-resolved")

    def test_negative_estimate_backwards_or_no_progress_are_invalid(self):
        before = fixture()
        for boot_delta, mono_delta in ((10, 1000), (-10, 10), (10, -10), (0, 0)):
            with self.subTest(deltas=(boot_delta, mono_delta)), self.assertRaises(mod.ClockError):
                mod.compare(before, fixture(before["clocks"]["boottime_ns"] + boot_delta,
                                            before["clocks"]["monotonic_ns"] + mono_delta))

    def test_reboot_session_kernel_or_missing_clock_prevents_comparison(self):
        for key, value, reason in (("session", "00" * 16, "session-mismatch"),
                                  ("boot_token", "00" * 32, "boot-token-mismatch"),
                                  ("kernel_release", "other", "kernel-mismatch"),
                                  ("clocks", None, "clocks-unavailable")):
            after = fixture()
            after[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(mod.ClockError, reason):
                mod.compare(fixture(), after)

    def test_schema_rejects_unknown_private_fields_bool_float_or_negative_clocks(self):
        invalid = fixture()
        invalid["serial"] = "private"
        samples = [invalid]
        for value in (True, -1, 1.5, 2 ** 80):
            invalid = fixture()
            invalid["clocks"]["boottime_ns"] = value
            samples.append(invalid)
        for invalid in samples:
            with self.assertRaises(mod.ClockError):
                mod.compare(invalid, fixture())

    def test_bounded_json_rejects_malformed_duplicate_or_oversized_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            for raw in (b"not json", b'{"schema":1,"schema":1}', b"x" * 8193):
                path.write_bytes(raw)
                with self.assertRaises(mod.ClockError):
                    mod.load_snapshot(path)

    def test_snapshot_cli_fixture_has_no_raw_boot_identifier(self):
        output = io.StringIO()
        with mock.patch.object(mod, "read_boot_token", return_value="cd" * 32), \
                mock.patch.object(mod, "sample_clocks", return_value=fixture()["clocks"]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(mod.main(["--snapshot", "--session", SESSION]), 0)
        self.assertEqual(json.loads(output.getvalue())["boot_token"], "cd" * 32)
        self.assertNotIn("boot_id", output.getvalue())

    def test_compare_cli_uses_only_fixture_files_and_rejects_invalid_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before.json", Path(tmp) / "after.json"
            before.write_text(json.dumps(fixture()))
            after.write_text(json.dumps(fixture(1001000000000, 901000000000)))
            result = subprocess.run([sys.executable, str(SCRIPT), "--compare", str(before), str(after)],
                                    capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["suspend_estimate_ns"], 0)
        for args in (["--snapshot"], ["--snapshot", "--session", "invalid"]):
            result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
