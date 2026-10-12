import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("validate_system", Path(__file__).resolve().parents[1] / "scripts/validate_system.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SystemImageBounds(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "system.img"

    def sparse(self, kind=0xCAC3, declared_blocks=1310720, chunk_blocks=1310720, physical=12):
        self.path.write_bytes(struct.pack("<I4H4I", 0xED26FF3A, 1, 0, 28, 12, 4096, declared_blocks, 1, 0)
                              + struct.pack("<2H2I", kind, 0, chunk_blocks, physical))

    def test_tiny_sparse_file_still_occupies_five_gib(self):
        self.sparse()
        self.assertEqual(self.path.stat().st_size, 40)
        self.assertEqual(module.sparse_bytes(self.path), 5368709120)

    def test_truncated_raw_chunk_is_rejected(self):
        self.sparse(kind=0xCAC1, declared_blocks=1, chunk_blocks=1, physical=4108)
        with self.assertRaisesRegex(ValueError, "Truncated"):
            module.sparse_bytes(self.path)

    def test_wrong_expanded_block_count_is_rejected(self):
        self.sparse(chunk_blocks=1310719)
        with self.assertRaisesRegex(ValueError, "block count"):
            module.sparse_bytes(self.path)

    def test_x86_userspace_does_not_pass_arm64_check(self):
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, 62)
        self.assertFalse(module.elf_arm64(header))
        struct.pack_into("<H", header, 18, 183)
        self.assertTrue(module.elf_arm64(header))


if __name__ == "__main__":
    unittest.main()
