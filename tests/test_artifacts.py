import gzip
import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/validate-artifacts.py"
SPEC = importlib.util.spec_from_file_location("validate_artifacts", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ArtifactValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        # Tiny structural fixture, not a bootable kernel or real initramfs.
        header = bytearray(2048)
        header[:8] = b"ANDROID!"
        kernel = bytearray(128)
        kernel[56:60] = b"ARM\x64"
        ramdisk = gzip.compress(b"070701" + b"0" * 104)
        struct.pack_into("<10I", header, 8, len(kernel), 0x10008000,
                         len(ramdisk), 0x11000000, 0, 0, 0x10000100, 2048, 1, 0)
        cmdline = b"systempart=/dev/disk/by-partlabel/system"
        header[64:64 + len(cmdline)] = cmdline
        self.boot = bytes(header) + bytes(kernel) + bytes(2048 - len(kernel)) + ramdisk
        (self.out / "boot.img").write_bytes(self.boot)
        (self.out / "kernel.config").write_text((module.ROOT / "config/ubuntu-touch.config").read_text())
        (self.out / "source-manifest.json").write_text('{}\n')
        self.tarball(self.boot)

    def tarball(self, boot):
        with tarfile.open(self.out / "device_beyond2lte.tar.xz", "w:xz") as tar:
            entries = {
                "partitions/boot.img": boot,
                "system/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml": b"beyond2lte:\n",
                "system/opt/halium-overlay/lib/modules/.halium-override-dir": b"",
            }
            for name, content in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

    def test_structure_pass_never_claims_hardware_validation(self):
        report = module.validate(self.out)
        self.assertTrue(report["structure_valid"])
        self.assertFalse(report["hardware_tested"])
        self.assertFalse(report["complete_installation_image"])

    def test_truncated_boot_is_rejected(self):
        (self.out / "boot.img").write_bytes(self.boot[:-1])
        with self.assertRaisesRegex(ValueError, "truncated"):
            module.validate(self.out)

    def test_wrong_architecture_is_rejected(self):
        changed = bytearray(self.boot)
        changed[2048 + 56:2048 + 60] = b"x86!"
        (self.out / "boot.img").write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "ARM64"):
            module.validate(self.out)

    def test_disabled_apparmor_is_rejected(self):
        path = self.out / "kernel.config"
        path.write_text(path.read_text().replace("CONFIG_SECURITY_APPARMOR=y", "# CONFIG_SECURITY_APPARMOR is not set"))
        with self.assertRaisesRegex(ValueError, "CONFIG_SECURITY_APPARMOR"):
            module.validate(self.out)

    def test_different_tarball_boot_is_rejected(self):
        self.tarball(self.boot + b"stale")
        with self.assertRaisesRegex(ValueError, "differ"):
            module.validate(self.out)


if __name__ == "__main__":
    unittest.main()
