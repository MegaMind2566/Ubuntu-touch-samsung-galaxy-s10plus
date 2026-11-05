"""Host-only regressions for the read-only, bounded energy inventory."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ut-s10-energia-diagnosi-v2.py"
SPEC = importlib.util.spec_from_file_location("energy_inventory", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class SysfsTests(unittest.TestCase):
    def test_supply_allowlist_excludes_private_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            battery = Path(tmp) / "battery"
            battery.mkdir()
            for name, value in {"capacity": "56", "status": "Discharging",
                                "serial_number": "PRIVATE-SERIAL", "imei": "PRIVATE-IMEI",
                                "manufacturer": "unneeded"}.items():
                (battery / name).write_text(value)
            self.assertEqual(mod.supplies(Path(tmp)), [{"dispositivo": "battery", "valori": {
                "capacity": "56", "status": "Discharging"}}])

    def test_missing_supply_directory_is_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mod.supplies(Path(tmp) / "absent"), [])

    def test_short_single_line_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "value"
            for raw in (b"", b"a\x00b", b"one\ntwo\n", b"x" * 161):
                with self.subTest(raw=raw[:12]):
                    path.write_bytes(raw)
                    self.assertIsNone(mod.read_value(path))
            path.write_bytes(b"56\n")
            self.assertEqual(mod.read_value(path), "56")

    def test_suspend_never_reads_blocking_attributes(self):
        seen = []
        def read(path):
            seen.append(Path(path).name)
            if Path(path).name in ("wakeup_count", "autosleep"):
                self.fail("potentially blocking kernel attribute was read")
            return "0"
        with mock.patch.object(mod, "read_value", side_effect=read):
            values = mod.suspend_info()
        self.assertEqual(set(values), {"state", "mem_sleep", "suspend_stats_success",
                                       "suspend_stats_fail"})
        self.assertNotIn("wakeup_count", seen)
        self.assertNotIn("autosleep", seen)

    def test_thermal_invalid_and_unrelated_sensors_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index, (kind, value) in enumerate((("battery", "24700"), ("gpu", "bad"),
                                                    ("unrelated", "30000"))):
                zone = Path(tmp) / ("thermal_zone" + str(index))
                zone.mkdir()
                (zone / "type").write_text(kind)
                (zone / "temp").write_text(value)
            self.assertEqual(mod.thermal_zones(Path(tmp)), [{"sensore": "thermal_zone0",
                "tipo": "battery", "temperatura_mC": 24700, "temperatura_C": 24.7}])

    def test_upower_removes_private_fields_and_bounds_values(self):
        raw = "Device: /org/freedesktop/UPower/devices/battery_BAT0\n" + (
            "  percentage: 56%\n  serial: PRIVATE-SERIAL\n  vendor: private\n"
            "  energy-rate: 0 W\n  voltage: " + "x" * 81 + "\n")
        self.assertEqual(mod.upower_extract(raw), [{"dispositivo": "battery_BAT0", "valori": {
            "percentage": "56%", "energy-rate": "0 W"}}])


class ProcessTests(unittest.TestCase):
    def test_real_child_timeout_returns_promptly_and_reaps_child(self):
        children = []
        original_popen = subprocess.Popen
        def start(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child
        started = time.monotonic()
        with mock.patch.object(mod.subprocess, "Popen", side_effect=start):
            result = mod.bounded_subprocess([sys.executable, "-c", "import time; time.sleep(30)"], 0.1)
        self.assertEqual(result, (None, "limite_tempo"))
        self.assertLess(time.monotonic() - started, 3)
        self.assertIsNotNone(children[0].wait(timeout=2))
        self.assertTrue(children[0].stdout.closed)

    def test_uninterruptible_child_does_not_cause_unbounded_cleanup_wait(self):
        child = mock.Mock()
        child.stderr = None
        child.poll.return_value = None
        child.communicate.side_effect = subprocess.TimeoutExpired("fixture", 0.01)
        with mock.patch.object(mod.subprocess, "Popen", return_value=child):
            self.assertEqual(mod.bounded_subprocess(["fixture"], 0.01), (None, "limite_tempo"))
        self.assertEqual([call.kwargs["timeout"] for call in child.communicate.call_args_list],
                         [0.01, 0.15])
        child.wait.assert_not_called()
        child.stdout.close.assert_called_once()

    def test_child_output_and_failure_are_distinct(self):
        command = [sys.executable, "-c"]
        self.assertEqual(mod.bounded_subprocess(command + ["print('ok')"], 3), ("ok\r\n" if sys.platform == "win32" else "ok\n", None))
        self.assertEqual(mod.bounded_subprocess(command + ["raise SystemExit(7)"], 3),
                         (None, "sezione_non_disponibile"))

    def test_excessive_child_output_is_rejected(self):
        result = mod.bounded_subprocess([sys.executable, "-c", "print('x' * 250001)"], 3)
        self.assertEqual(result, (None, "output_eccessivo"))

    def test_optional_command_absence_failure_and_timeout(self):
        with mock.patch.object(mod.shutil, "which", return_value=None):
            self.assertIsNone(mod.run_optional(["optional"]))
        with mock.patch.object(mod.shutil, "which", return_value="/fixture/optional"):
            for response in (subprocess.CompletedProcess([], 1, "private", ""),
                             subprocess.TimeoutExpired("optional", 1), OSError("absent")):
                with self.subTest(response=type(response).__name__):
                    kwargs = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
                    with mock.patch.object(mod.subprocess, "run", **kwargs):
                        self.assertIsNone(mod.run_optional(["optional"]))


class ReportTests(unittest.TestCase):
    def test_timeout_preserves_other_sections(self):
        sections = {"alimentazione": 0.1, "termiche": 0.1}
        replies = [(None, "limite_tempo"), (json.dumps({"sezione": "termiche", "valore": []}), None)]
        with mock.patch.object(mod, "SECTION_SECONDS", sections), \
                mock.patch.object(mod, "bounded_subprocess", side_effect=replies), \
                contextlib.redirect_stderr(io.StringIO()):
            report = mod.collect()
        self.assertEqual(report["alimentazione"], "non_disponibile")
        self.assertEqual(report["termiche"], [])
        self.assertEqual(report["avvisi"], {"alimentazione": "limite_tempo"})
        self.assertTrue(report["lettura_sola"])
        self.assertFalse(report["sospensione_forzata"])

    def test_invalid_worker_envelopes_produce_warning_and_continue(self):
        for raw in ("not json", "[]", '{"sezione":"other","valore":0}', '{"sezione":"termiche"}'):
            with self.subTest(raw=raw), mock.patch.object(mod, "SECTION_SECONDS", {"termiche": 1}), \
                    mock.patch.object(mod, "bounded_subprocess", return_value=(raw, None)), \
                    contextlib.redirect_stderr(io.StringIO()):
                report = mod.collect()
                self.assertEqual(report["avvisi"], {"termiche": "risposta_non_valida"})

    def test_cli_requires_action_and_rejects_unknown_worker(self):
        for args in ([], ["--_worker", "unknown"], ["--inventario", "--_worker", "upower"]):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(b"UT_S10_ENERGIA", result.stdout)

    def test_main_inventory_emits_machine_readable_report(self):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", [str(SCRIPT), "--inventario"]), \
                mock.patch.object(mod, "collect", return_value={"lettura_sola": True}), \
                contextlib.redirect_stdout(output):
            self.assertEqual(mod.main(), 0)
        self.assertEqual(json.loads(output.getvalue().removeprefix("UT_S10_ENERGIA ")), {"lettura_sola": True})

    def test_main_error_and_interruption_emit_no_private_exception_text(self):
        for error, code, event in ((OSError("PRIVATE-PATH"), 1, "errore_inventario"),
                                   (KeyboardInterrupt(), 130, "interrotto")):
            output = io.StringIO()
            with self.subTest(event=event), mock.patch.object(sys, "argv", [str(SCRIPT), "--inventario"]), \
                    mock.patch.object(mod, "collect", side_effect=error), contextlib.redirect_stdout(output):
                self.assertEqual(mod.main(), code)
            self.assertNotIn("PRIVATE-PATH", output.getvalue())
            self.assertEqual(json.loads(output.getvalue().removeprefix("UT_S10_ENERGIA "))["evento"], event)


if __name__ == "__main__":
    unittest.main()
