import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("build_resume_system", ROOT / "scripts/build-resume-system.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
PAYLOAD = module.canonical_rules(ROOT / "tools/graphics-permissions" / module.RULE_FILENAME)


def pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class FakeProcess:
    def __init__(self, contents, code=0):
        self.stdout = io.BytesIO(contents)
        self.code = code

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        pass


class ResumeSystem(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resume fixture ")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.system = self.work / "SYSTEM.img.zst"
        self.system.write_bytes(b"compressed immutable fixture")
        self.boot = b"boot6 fixture with its own strict test pin"
        self.raw = b"original ext4 fixture bytes\x00" * 256
        self.archive = self.work / "boot tools.zip"
        self.release = {"schema": 1, "tag": "v0.1.0-alpha.1", "system": {"name": "SYSTEM.img.zst", **pin(self.system.read_bytes())}}
        self.manifest = {
            "release": self.release["tag"], "firmware": "G975FXXSGHWC1", "images": {"boot.img": pin(self.boot)},
            "separate_asset": {**self.release["system"], "raw_bytes": len(self.raw), "raw_sha256": pin(self.raw)["sha256"]},
            "graphics_payload_sha256": {module.RULE_FILENAME: module.RULE_SHA256},
        }
        self.config = self.work / "release.json"
        self.save_archive()
        self.output = self.work / "new candidate"
        self.events = []
        self.rule = None
        self.mode, self.uid, self.gid = 0o644, 0, 0
        self.parent_kind = "directory"
        self.roundtrip = None
        self.bad_roundtrip = False
        self.decompressed = self.raw
        self.process_code = 0
        self.fsck_count = 0
        self.fail_fsck = None
        self.fail_write = False
        self.keep_bad_owner = False
        self.patches = [mock.patch.object(module, "RAW_PIN", pin(self.raw)),
                        mock.patch.object(module, "BOOT_PIN", pin(self.boot)),
                        mock.patch.object(module, "RELEASE_CONFIG", self.config)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def save_archive(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("config/firmware-release.json", json.dumps(self.manifest))
            archive.writestr("images/boot.img", self.boot)
            # An unrelated archive member must never be extracted.
            archive.writestr("../outside-file", "not extracted")
        self.release["boot_and_tools"] = {"name": self.archive.name, **pin(self.archive.read_bytes())}
        self.config.write_text(json.dumps(self.release))

    def popen(self, command, **kwargs):
        self.events.append(("stream", command))
        if Path(command[-1]) == self.system:
            return FakeProcess(self.decompressed, self.process_code)
        return FakeProcess(self.raw if self.bad_roundtrip else self.roundtrip)

    def stat_text(self, kind="regular", links=1):
        return f"Inode: 123 Type: {kind} Mode: {self.mode:04o} Flags: 0x80000\nUser: {self.uid} Group: {self.gid} Size: 260\nLinks: {links} Blockcount: 2\n"

    def external(self, command, cwd=None):
        self.events.append(("run", command))
        result = types.SimpleNamespace(stdout="", stderr="")
        if command[0] == "e2fsck":
            self.fsck_count += 1
            if self.fsck_count == self.fail_fsck:
                raise subprocess.CalledProcessError(4, command)
        elif command[0] == "debugfs":
            operation = command[command.index("-R") + 1]
            image = Path(command[-1])
            result.stderr = "debugfs 1.46.5 (30-Dec-2021)\n"
            if operation.startswith("stat "):
                if operation == "stat " + module.RULE_PATH:
                    if self.rule is None:
                        result.stderr += "File not found by ext2_lookup while trying to resolve filename\n"
                    else:
                        result.stdout = self.stat_text()
                else:
                    result.stdout = self.stat_text(self.parent_kind, 2)
            elif operation.startswith("write "):
                if self.fail_write:
                    result.stderr += "write: Could not allocate block in ext2 filesystem\n"
                    return result
                self.rule = (Path(cwd) / "graphics.rules").read_bytes()
                self.mode = 0o600
                data = bytearray(image.read_bytes())
                data[128:128 + len(self.rule)] = self.rule
                image.write_bytes(data)
            elif operation.startswith("set_inode_field "):
                field, value = operation.split()[-2:]
                if field == "mode":
                    self.mode = int(value, 8) & 0o7777
                elif field == "uid" and self.keep_bad_owner:
                    self.uid = 1000
                else:
                    setattr(self, field, int(value))
            elif operation.startswith("dump "):
                (Path(cwd) / "readback.rules").write_bytes(self.rule)
            else:
                self.fail("Unexpected debugfs command")
        elif command[0] == "zstd" and "-o" in command:
            self.roundtrip = Path(command[-1]).read_bytes()
            Path(command[command.index("-o") + 1]).write_bytes(b"candidate compressed fixture")
        elif command[:2] != ["zstd", "-t"]:
            self.fail("Unexpected executable")
        return result

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return module.build(self.system, self.archive, self.output, run=self.external, popen=self.popen)

    def mutations(self):
        return [command for kind, command in self.events if kind == "run" and command[0] == "debugfs" and "-w" in command]

    def test_complete_call_sequence_preserves_sources_boot_and_untrusted_zip_paths(self):
        original_system, original_archive = self.system.read_bytes(), self.archive.read_bytes()
        report = self.build()
        self.assertEqual(self.system.read_bytes(), original_system)
        self.assertEqual(self.archive.read_bytes(), original_archive)
        self.assertEqual((self.output / "BOOT6.img").read_bytes(), self.boot)
        self.assertEqual((self.output / "SYSTEM.img").stat().st_size, len(self.raw))
        self.assertNotEqual((self.output / "SYSTEM.img").read_bytes(), self.raw)
        self.assertEqual(report["graphics_rule"]["metadata"], {"type": "regular", "mode": 0o644, "uid": 0, "gid": 0, "links": 1})
        self.assertEqual(self.fsck_count, 2)
        self.assertEqual(len(self.mutations()), 4)
        first_write = next(i for i, (kind, command) in enumerate(self.events) if command[0] == "debugfs" and "-w" in command)
        self.assertTrue(any(command[0] == "e2fsck" for _, command in self.events[:first_write]))
        self.assertTrue((self.output / "SHA256SUMS").is_file())
        self.assertNotIn("  SYSTEM.img\n", (self.output / "SHA256SUMS").read_text())
        self.assertFalse((self.work / "outside-file").exists())
        for key in ("hardware_tested", "install_ready", "image_mounted", "phone_accessed", "current_handset_vendor_compatibility_verified"):
            self.assertFalse(report[key])

    def test_tampered_compressed_source_stops_before_any_external_command(self):
        self.system.write_bytes(b"changed compressed source")
        with self.assertRaisesRegex(ValueError, "input_size_mismatch|input_hash_mismatch"):
            self.build()
        self.assertEqual(self.events, [])

    def test_zip_manifest_cannot_substitute_boot_even_with_a_matching_outer_fixture_hash(self):
        self.manifest["images"]["boot.img"] = pin(b"wrong boot")
        self.save_archive()
        with self.assertRaisesRegex(ValueError, "release_zip_boot_pin_mismatch"):
            self.build()
        self.assertEqual(self.events, [])

    def test_oversized_decompression_stops_before_image_mutations(self):
        self.decompressed = self.raw + b"one extra byte"
        with self.assertRaisesRegex(ValueError, "oversized"):
            self.build()
        self.assertEqual(self.mutations(), [])
        self.assertFalse((self.output / "SYSTEM-working.img").exists())

    def test_same_size_wrong_raw_hash_stops_before_image_mutations(self):
        self.decompressed = b"x" * len(self.raw)
        with self.assertRaisesRegex(ValueError, "expanded_system_identity_mismatch"):
            self.build()
        self.assertEqual(self.mutations(), [])

    def test_decompressor_failure_is_not_accepted_even_if_bytes_match(self):
        self.process_code = 1
        with self.assertRaisesRegex(ValueError, "zstd_decompression_failed"):
            self.build()
        self.assertEqual(self.mutations(), [])

    def test_initial_filesystem_error_stops_before_image_mutations(self):
        self.fail_fsck = 1
        with self.assertRaises(subprocess.CalledProcessError):
            self.build()
        self.assertEqual(self.mutations(), [])

    def test_final_filesystem_error_prevents_compression_and_success_report(self):
        self.fail_fsck = 2
        with self.assertRaises(subprocess.CalledProcessError):
            self.build()
        self.assertFalse((self.output / "candidate-report.json").exists())
        self.assertFalse(any(command[0] == "zstd" and "-o" in command for _, command in self.events))

    def test_debugfs_zero_exit_with_error_text_is_rejected(self):
        self.fail_write = True
        with self.assertRaisesRegex(ValueError, "debugfs_command_failed"):
            self.build()

    def test_symlink_parent_is_rejected_before_any_write(self):
        self.parent_kind = "symlink"
        with self.assertRaisesRegex(ValueError, "graphics_parent_not_directory"):
            self.build()
        self.assertEqual(self.mutations(), [])

    def test_existing_conflicting_rule_is_rejected_without_write(self):
        self.rule = b"conflicting rules"
        with self.assertRaisesRegex(ValueError, "readback_mismatch"):
            self.build()
        self.assertEqual(self.mutations(), [])

    def test_existing_exact_rule_is_idempotent(self):
        self.rule = PAYLOAD
        report = self.build()
        self.assertFalse(report["graphics_rule"]["created"])
        self.assertEqual(self.mutations(), [])

    def test_wrong_readback_owner_rejects_the_candidate(self):
        self.keep_bad_owner = True
        with self.assertRaisesRegex(ValueError, "metadata_mismatch"):
            self.build()
        self.assertFalse((self.output / "candidate-report.json").exists())

    def test_compression_roundtrip_hash_is_verified(self):
        self.bad_roundtrip = True
        with self.assertRaisesRegex(ValueError, "expanded_system_identity_mismatch"):
            self.build()
        self.assertFalse((self.output / "SYSTEM-graphics-candidate.img.zst").exists())
        self.assertFalse((self.output / "SYSTEM.img").exists())

    def test_existing_output_directory_is_never_reused(self):
        self.output.mkdir()
        marker = self.output / "user-file"
        marker.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "output_must_be_fresh"):
            self.build()
        self.assertEqual(marker.read_bytes(), b"preserve")
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
