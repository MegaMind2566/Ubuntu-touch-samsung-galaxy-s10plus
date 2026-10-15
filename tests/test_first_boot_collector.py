"""Exercise evidence preservation and the read-only query boundaries."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("first_boot", SOURCE / "scripts/collect-first-boot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def result(stdout="", code=0):
    return {"exit_code": code, "stdout": stdout, "stderr": "", "timed_out": False}


class FirstBootCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="first boot with spaces ")
        self.root = Path(self.temp.name)
        self.calls = []
        self.overrides = {}

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, executable, name):
        self.calls.append(name)
        if name in self.overrides:
            return self.overrides[name]
        values = {
            "version": "Android Debug Bridge version 1.0.41\nVersion 37.0.1-14792107",
            "state": "recovery\n", "uid": "0\n",
            "properties": "ro.twrp.version|3.7.0_9\nro.product.model|Galaxy S10+\n"
                          "ro.product.device|beyond2lte\nro.hardware|exynos9820\n"
                          "ro.bootloader|G975FXXSGHWC1\n",
            "last-kmsg": "Linux version 4.14.280\ninitrd: error\nandroidboot.serialno=PRIVATE123\n",
            "last-kmsg-start": "Linux version 4.14.280\n",
            "pstore-list": "console-ramoops-0\n../secret\nconsole-ramoops-0;reboot\n",
            "pstore:console-ramoops-0": "Kernel panic - test fixture\n",
            "mounts": "/dev/block/sda31 /data ext4 rw 0 0\n",
            "system-magic": "53ef", "vendor-magic": "53ef", "vendor-size": "1153433600",
            "vendor-fsck": "Pass 1: Checking inodes\n",
        }
        values.update({name: digest + "  -\n" for name, digest in m.EXPECTED_HASHES.items()})
        return result(values.get(name, ""))

    def collect(self):
        return m.collect(self.root, runner=self.runner, verifier=lambda root: None)

    def test_previous_logs_before_hashes_and_report_inclusion(self):
        install = {"route": "root_twrp_adb", "success": True,
                   "system_readback_verified": True, "boot_readback_verified": True}
        original = self.root / "ubuntu-twrp-install-report.zip"
        with zipfile.ZipFile(original, "w") as z:
            z.writestr("ubuntu-twrp-install-report.json", json.dumps(install))
        old_hash = m.sha256(original)
        report, path = self.collect()
        self.assertTrue(report["success"])
        self.assertTrue(report["installation"]["system_readback_verified"])
        self.assertEqual(report["installation"]["source_zip_sha256"], old_hash)
        self.assertEqual(m.sha256(original), old_hash)
        self.assertLess(self.calls.index("last-kmsg"), self.calls.index("boot-hash"))
        self.assertEqual(report["prior_boot_log_files"], ["previous-boot-last-kmsg.txt", "previous-boot-last-kmsg-start.txt", "previous-boot-pstore-console-ramoops-0.txt"])
        with zipfile.ZipFile(path) as z:
            self.assertIn("installation-report.json", z.namelist())
            self.assertNotIn("PRIVATE123", z.read("previous-boot-last-kmsg.txt").decode())
        self.assertFalse(report["vendor_checks"]["stock_content_hash_verified"])
        self.assertFalse(report["ubuntu_touch_boot_verified"])

    def test_mounted_vendor_is_not_checked_or_unmounted(self):
        self.overrides["mounts"] = result("/dev/block/platform/13d60000.ufs/by-name/vendor /vendor ext4 ro 0 0\n")
        report, _ = self.collect()
        self.assertNotIn("vendor-fsck", self.calls)
        self.assertFalse(report["vendor_checks"]["fsck_read_only_requested"])

    def test_missing_logs_and_invalid_boot_hash_keep_report(self):
        self.overrides.update({"last-kmsg": result("", 1), "last-kmsg-start": result("", 1), "pstore-list": result(""), "boot-hash": result("0" * 64 + "  -\n")})
        report, path = self.collect()
        self.assertTrue(path.is_file())
        self.assertTrue(report["success"])
        self.assertEqual(report["prior_boot_log_files"], [])
        self.assertFalse(report["image_checks"]["boot-hash"]["matches_expected"])

    def test_wrong_recovery_stops_before_log_or_partition_reads(self):
        self.overrides["properties"] = result("ro.twrp.version|3.7.0_9\nro.product.device|wrong\n")
        report, _ = self.collect()
        self.assertFalse(report["success"])
        self.assertNotIn("last-kmsg", self.calls)
        self.assertNotIn("boot-hash", self.calls)

    def test_missing_usb_still_returns_local_installation_evidence(self):
        self.overrides["state"] = result("", 1)
        report, path = self.collect()
        self.assertEqual(report["error"], "twrp_usb_unavailable")
        with zipfile.ZipFile(path) as z:
            self.assertIn("first-boot-report.json", z.namelist())

    def test_readonly_allowlist_and_filename_injection(self):
        for key in ("pstore:../secret", "pstore:console-ramoops-0;reboot", "flash", "reboot", "vendor-fsck;-y"):
            with self.assertRaises(ValueError):
                m.command_for(key)
        for key in (*m.QUERIES, "pstore:console-ramoops-0"):
            arguments = m.command_for(key)
            joined = " ".join(arguments)
            self.assertIsNone(re.search(r"\b(?:push|reboot|mount|umount|flash|mkfs|wipe|rm|dd)\b", joined))
        self.assertEqual(m.command_for("vendor-fsck"), ["-d", "shell", "/sbin/e2fsck -f -n /dev/block/sda26"])

    def test_unsafe_install_zip_is_not_extracted_or_copied(self):
        with zipfile.ZipFile(self.root / "ubuntu-twrp-install-report.zip", "w") as z:
            z.writestr("../secret", "fixture")
        report, path = self.collect()
        self.assertEqual(report["installation"]["error"], "local_install_report_invalid")
        with zipfile.ZipFile(path) as z:
            self.assertNotIn("../secret", z.namelist())

    def test_bounded_native_read_and_timeout(self):
        with patch.object(m.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"x" * (m.LOG_BYTES + 4097), b"")) as call:
            value = m.run_query(Path("adb.exe"), "last-kmsg")
            self.assertEqual(value["stderr"], "output_limit")
            self.assertEqual(call.call_args.kwargs["timeout"], 45)
        with patch.object(m.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 45)):
            self.assertTrue(m.run_query(Path("adb.exe"), "last-kmsg")["timed_out"])

    def test_no_reports_overwritten(self):
        old = self.root / "ubuntu-first-boot-report.zip"
        old.write_bytes(b"keep this")
        _, path = self.collect()
        self.assertEqual(path.name, "ubuntu-first-boot-report-1.zip")
        self.assertEqual(old.read_bytes(), b"keep this")


if __name__ == "__main__":
    unittest.main()
