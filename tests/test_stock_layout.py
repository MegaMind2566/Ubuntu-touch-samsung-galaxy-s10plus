import gzip
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/inspect_stock_firmware.py"
SPEC = importlib.util.spec_from_file_location("inspect_stock_firmware", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def boot_fixture(legacy=False, ramdisk=b"ramdisk", recovery=b""):
    header = bytearray(2048)
    header[:8] = b"ANDROID!"
    kernel = bytearray(64)
    kernel[56:60] = b"ARM\x64"
    struct.pack_into("<10I", header, 8, len(kernel), 0x10008000, len(ramdisk),
                     0x11000000 if ramdisk else 0, 0, 0, 0x10000100, 2048, 1,
                     (12 << 25) | ((2023 - 2000) << 4) | 3)
    dtbo_offset = 2048 + 2048 + module.aligned(len(ramdisk), 2048) if recovery else 0
    struct.pack_into("<IQI", header, 1632, len(recovery), dtbo_offset, 1648)
    checksum = hashlib.sha1()
    for payload in (kernel, ramdisk, b""):
        checksum.update(payload)
        checksum.update(struct.pack("<I", len(payload)))
    if legacy:
        checksum.update(struct.pack("<I", 0))
    checksum.update(recovery)
    checksum.update(struct.pack("<I", len(recovery)))
    header[576:596] = checksum.digest()
    result = bytes(header)
    for payload in (kernel, ramdisk, recovery):
        result += payload + bytes(module.aligned(len(payload), 2048) - len(payload))
    return result


def cpio_entry(name, data=b""):
    name_bytes = name.encode() + b"\0"
    fields = [1, 0o100644, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name_bytes), 0]
    header = b"070701" + b"".join(f"{x:08x}".encode() for x in fields) + name_bytes
    header += bytes(module.aligned(len(header), 4) - len(header))
    return header + data + bytes(module.aligned(len(data), 4) - len(data))


class StockLayoutValidation(unittest.TestCase):
    def test_stock_boot_can_have_no_ramdisk(self):
        result = module.boot_header(boot_fixture(ramdisk=b""))
        self.assertEqual(result["ramdisk_address"], 0)
        self.assertEqual(result["os_version"], "12.0.0")
        self.assertEqual(result["security_patch"], "2023-03")
        self.assertEqual(result["boot_id_variant"], "aosp")

    def test_pinned_lineage_hash_variant_is_recognized(self):
        result = module.boot_header(boot_fixture(legacy=True))
        self.assertEqual(result["boot_id_variant"], "lineage-empty-legacy-dt")

    def test_changed_kernel_without_new_id_is_rejected(self):
        boot = bytearray(boot_fixture())
        boot[2048] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            module.boot_header(boot)

    def test_truncated_ramdisk_is_rejected(self):
        boot = boot_fixture()
        with self.assertRaisesRegex(ValueError, "Truncated boot payload"):
            module.boot_header(boot[:4097])

    def test_recovery_dtbo_is_covered_by_boot_id(self):
        boot = bytearray(boot_fixture(recovery=b"dtbo"))
        self.assertEqual(module.boot_header(boot)["recovery_dtbo_bytes"], 4)
        boot[6144] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            module.boot_header(boot)

    def test_dtbo_payload_outside_declared_table_is_rejected(self):
        data = struct.pack(">8I", 0xD7B7AB1E, 104, 32, 32, 1, 32, 2048, 0)
        data += struct.pack(">8I", 40, 1000, 0, 0, 4, 15, 0, 0) + bytes(40)
        with self.assertRaisesRegex(ValueError, "payload exceeds"):
            module.dtbo_table(data)

    def test_dtbo_contains_valid_sized_fdt(self):
        data = struct.pack(">8I", 0xD7B7AB1E, 104, 32, 32, 1, 32, 2048, 0)
        data += struct.pack(">8I", 40, 64, 0, 0, 4, 15, 0, 0)
        data += struct.pack(">2I", 0xD00DFEED, 40) + bytes(32)
        self.assertEqual(module.dtbo_table(data)["entries"][0]["custom"], [4, 15, 0, 0])

    def test_newc_requires_complete_content_and_trailer(self):
        archive = cpio_entry("prop.default", b"test=value\n") + cpio_entry("TRAILER!!!")
        self.assertEqual(module.recovery_ramdisk(gzip.compress(archive))["prop.default"], b"test=value\n")
        with self.assertRaisesRegex(ValueError, "Missing newc trailer"):
            module.newc_files(archive[:-112])

    def test_truncated_gzip_is_rejected(self):
        data = gzip.compress(cpio_entry("TRAILER!!!"))
        with self.assertRaisesRegex(ValueError, "recovery gzip"):
            module.recovery_ramdisk(data[:-1])


if __name__ == "__main__":
    unittest.main()
