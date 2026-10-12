import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("inspect_device", Path(__file__).resolve().parents[1] / "scripts/inspect_device.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class HandsetInventory(unittest.TestCase):
    def setUp(self):
        properties = {
            "ro.product.model": "SM-G975F", "ro.product.device": "beyond2",
            "ro.hardware": "exynos9820", "ro.board.platform": "universal9820",
            "ro.build.version.release": "12", "ro.vendor.build.version.release": "12",
            "ro.build.version.sdk": "31", "ro.vendor.build.version.sdk": "31",
            "ro.boot.flash.locked": "1", "ro.boot.vbmeta.device_state": "locked",
        }
        sizes = {"boot": 56320, "recovery": 66048, "system": 5836800, "vendor": 1126400,
                 "userdata": 116334592, "dtbo": 8192, "vbmeta": 64}
        self.report = {
            "read_only": True,
            "properties": {k: {"text": v, "exit_code": 0} for k, v in properties.items()},
            "partitions": {"text": "\n".join(f"{name}|/dev/block/sda{i}||" for i, name in enumerate(sizes, 1)), "exit_code": 0},
            "proc_partitions": {"text": "major minor  #blocks  name\n" + "\n".join(f"8 {i} {size} sda{i}" for i, size in enumerate(sizes.values(), 1)), "exit_code": 0},
        }

    def test_stock_alias_and_restricted_sysfs_use_correct_proc_units(self):
        result = module.inspect(self.report, 53215232)
        self.assertEqual(result["partitions"]["boot"]["bytes"], 57671680)
        self.assertEqual(result["boot_image"]["remaining_bytes"], 4456448)
        self.assertTrue(result["bootloader_locked"])
        self.assertFalse(result["vendor_runtime_compatibility_verified"])
        self.assertFalse(result["install_ready"])

    def test_ufs_logical_block_size_does_not_change_sector_units(self):
        report = copy.deepcopy(self.report)
        report["partitions"]["text"] = report["partitions"]["text"].replace("boot|/dev/block/sda1||", "boot|/dev/block/sda1|112640|4096")
        self.assertEqual(module.inspect(report, 53215232)["partitions"]["boot"]["bytes"], 57671680)

    def test_conflicting_size_readings_are_rejected(self):
        self.report["partitions"]["text"] = self.report["partitions"]["text"].replace("boot|/dev/block/sda1||", "boot|/dev/block/sda1|112641|4096")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            module.inspect(self.report, 53215232)

    def test_boot_overflow_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            module.inspect(self.report, 57671681)

    def test_missing_size_is_not_guessed(self):
        self.report["proc_partitions"]["exit_code"] = 1
        with self.assertRaisesRegex(ValueError, "No readable size"):
            module.inspect(self.report, 53215232)

    def test_vendor_version_mismatch_is_rejected(self):
        self.report["properties"]["ro.vendor.build.version.release"]["text"] = "10"
        with self.assertRaisesRegex(ValueError, "vendor must both"):
            module.inspect(self.report, 53215232)

    def test_other_phone_is_rejected(self):
        self.report["properties"]["ro.product.model"]["text"] = "SM-G973F"
        with self.assertRaisesRegex(ValueError, "Exynos S10"):
            module.inspect(self.report, 53215232)


if __name__ == "__main__":
    unittest.main()
