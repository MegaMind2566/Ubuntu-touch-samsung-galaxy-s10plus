import importlib.util
from pathlib import Path
import struct
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("inspect_stock_dtb", SCRIPTS / "inspect_stock_dtb.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture():
    strings = b"compatible\0dtb-hw_rev\0"
    compatible = b"samsung,armv8\0samsung,exynos9820\0"
    body = struct.pack(">I", 1) + bytes(4)
    body += struct.pack(">3I", 3, len(compatible), 0) + compatible
    body += bytes((-len(compatible)) % 4)
    body += struct.pack(">4I", 3, 4, 11, 0)
    body += struct.pack(">2I", 2, 9)
    total = 56 + len(body) + len(strings)
    return bytearray(struct.pack(">10I", 0xD00DFEED, total, 56, 56 + len(body),
                                 40, 17, 16, 0, len(strings), len(body)) + bytes(16) + body + strings)


class StockDtbParsing(unittest.TestCase):
    def test_exynos_root_properties(self):
        summary = module.fdt_summary(fixture())
        self.assertEqual(summary["root_properties"]["compatible"], ["samsung,armv8", "samsung,exynos9820"])
        self.assertEqual(summary["root_properties"]["dtb-hw_rev"], 0)
        self.assertEqual(summary["node_count"], 1)

    def test_truncated_blob_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "magic/size"):
            module.fdt_summary(fixture()[:-1])

    def test_property_overflow_is_rejected(self):
        blob = fixture()
        struct.pack_into(">I", blob, 68, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "property exceeds"):
            module.fdt_summary(blob)

    def test_name_offset_outside_string_table_is_rejected(self):
        blob = fixture()
        struct.pack_into(">I", blob, 72, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "property exceeds"):
            module.fdt_summary(blob)

    def test_unclosed_root_is_rejected(self):
        blob = fixture()
        strings_off = struct.unpack_from(">I", blob, 12)[0]
        struct.pack_into(">I", blob, strings_off - 8, 4)
        with self.assertRaisesRegex(ValueError, "Unclosed"):
            module.fdt_summary(blob)

    def test_block_overlap_is_rejected(self):
        blob = fixture()
        struct.pack_into(">I", blob, 12, 56)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            module.fdt_summary(blob)

    def test_unknown_token_is_rejected(self):
        blob = fixture()
        struct.pack_into(">I", blob, 56, 77)
        with self.assertRaisesRegex(ValueError, "Unknown FDT token"):
            module.fdt_summary(blob)


if __name__ == "__main__":
    unittest.main()
