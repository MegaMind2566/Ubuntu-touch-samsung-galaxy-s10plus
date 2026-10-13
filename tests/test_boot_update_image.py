"""Verify exact baseline preservation and image rejection boundaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'scripts'))
import prepare_boot_update as module


class BootUpdateImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=ROOT/'out/boot-baseline/boot.img'
        if not cls.path.exists():raise unittest.SkipTest('Immutable actual baseline supplied in build CI')
        cls.boot=cls.path.read_bytes()

    def test_same_kernel_preserves_entire_original_image(self):
        rebuilt,header=module.compose(self.boot,self.boot)
        self.assertEqual(rebuilt,self.boot)
        self.assertEqual(header['ramdisk_bytes'],module.RAMDISK_BYTES)

    def test_wrong_baseline_rejected(self):
        changed=bytearray(self.boot);changed[-1]^=1
        with self.assertRaisesRegex(ValueError,'original_boot_mismatch'):module.compose(bytes(changed),self.boot)

    def test_truncated_new_kernel_rejected(self):
        with self.assertRaises(ValueError):module.compose(self.boot,self.boot[:2048])


if __name__=='__main__':unittest.main()
