import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools/automatic-brightness/profile.py"
SPEC = importlib.util.spec_from_file_location("brightness_profile", TOOL)
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class AutomaticBrightnessProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uid_patch = patch.object(profile, "ROOT_UID", getattr(os, "geteuid", lambda: 0)())
        self.uid_patch.start()
        self.addCleanup(self.uid_patch.stop)
        original_info = profile.ownership_info
        def fixture_info(path):
            value = original_info(path)
            if os.name != "nt":
                return value
            # Windows cannot express POSIX ownership/mode; emulate fixture metadata.
            directory = path.is_dir()
            mode = 0o700 if path in {self.root, self.root / profile.STATE.parent} else 0o755
            if not directory:
                mode = 0o600 if path == self.root / profile.STATE else 0o644
            return SimpleNamespace(st_uid=0, st_gid=0, st_mode=(stat.S_IFDIR if directory else stat.S_IFREG) | mode)
        self.fixture_info = fixture_info
        self.metadata_patch = patch.object(profile, "ownership_info", side_effect=fixture_info)
        self.metadata_patch.start()
        self.addCleanup(self.metadata_patch.stop)
        self.write(profile.DEVICEINFO, b"Names: [beyond2]\n")
        self.write(Path("etc/os-release"), b'ID=ubuntu\nVERSION_ID="24.04"\nVARIANT_ID=touch\n')
        self.context = patch.object(profile, "check_context")
        self.context.start()
        self.addCleanup(self.context.stop)

    def write(self, relative, data):
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def test_profile_matches_pinned_original_arrays_and_normalized_range(self):
        data = profile.load_profile()
        self.assertIn(b"config_automatic_brightness_available", data)
        metadata = json.loads((TOOL.parent / "manifest.json").read_text())
        self.assertEqual(len(metadata["levels"]), 35)
        self.assertEqual(len(metadata["values"]), 36)
        self.assertEqual((metadata["levels"][0], metadata["levels"][-1]), (1, 100000))
        self.assertEqual((metadata["values"][0], metadata["values"][-1]), (22, 255))

    def test_install_new_profile_and_rollback_remove_only_added_file(self):
        result = profile.install(self.root)
        self.assertTrue(result["installed"])
        self.assertEqual((self.root / profile.TARGET).read_bytes(), profile.load_profile())
        self.assertTrue((self.root / profile.STATE).is_file())
        profile.rollback(self.root)
        self.assertFalse((self.root / profile.TARGET).exists())
        self.assertFalse((self.root / profile.STATE).exists())

    def test_install_preserves_existing_profile_and_rollback_exact_bytes(self):
        original = b"<?xml version='1.0'?><resources><!-- previous --></resources>\n"
        self.write(profile.TARGET, original)
        profile.install(self.root)
        profile.rollback(self.root)
        self.assertEqual((self.root / profile.TARGET).read_bytes(), original)

    def test_repeated_install_keeps_original_backup(self):
        original = b"previous profile\n"
        self.write(profile.TARGET, original)
        profile.install(self.root)
        saved = (self.root / profile.STATE).read_bytes()
        self.assertFalse(profile.install(self.root)["changed"])
        self.assertEqual((self.root / profile.STATE).read_bytes(), saved)
        profile.rollback(self.root)
        self.assertEqual((self.root / profile.TARGET).read_bytes(), original)

    def test_rollback_rejects_later_unrelated_changes(self):
        profile.install(self.root)
        self.write(profile.TARGET, b"later edit")
        with self.assertRaisesRegex(ValueError, "changed"):
            profile.rollback(self.root)
        self.assertEqual((self.root / profile.TARGET).read_bytes(), b"later edit")
        self.assertTrue((self.root / profile.STATE).exists())

    def test_interrupted_install_can_resume_using_saved_original(self):
        original = b"original"
        self.write(profile.TARGET, original)
        real_write = profile.atomic_write
        def interrupt(path, data, mode=0o644):
            if path == self.root / profile.TARGET:
                raise OSError("simulated read-only filesystem")
            return real_write(path, data, mode)
        with patch.object(profile, "atomic_write", side_effect=interrupt):
            with self.assertRaises(OSError):
                profile.install(self.root)
        self.assertEqual((self.root / profile.TARGET).read_bytes(), original)
        profile.install(self.root)
        profile.rollback(self.root)
        self.assertEqual((self.root / profile.TARGET).read_bytes(), original)

    def test_oversize_existing_profile_rejected_without_state(self):
        self.write(profile.TARGET, b"x" * 16385)
        with self.assertRaisesRegex(ValueError, "large"):
            profile.install(self.root)
        self.assertFalse((self.root / profile.STATE).exists())

    def test_malformed_state_is_visible_failure(self):
        self.write(profile.STATE, b"{bad")
        os.chmod((self.root / profile.STATE).parent, 0o700)
        os.chmod(self.root / profile.STATE, 0o600)
        with self.assertRaises(ValueError):
            profile.install(self.root)
        self.assertFalse((self.root / profile.TARGET).exists())

    def test_untrusted_owner_or_writable_parent_rejected_before_install(self):
        unsafe = self.root / "userdata"
        unsafe.mkdir()
        for owner, mode in ((profile.ROOT_UID + 1, 0o755), (profile.ROOT_UID, 0o777)):
            def metadata(path):
                if path == unsafe:
                    return SimpleNamespace(st_uid=owner, st_mode=stat.S_IFDIR | mode)
                return self.fixture_info(path)
            with self.subTest(owner=owner, mode=mode), patch.object(profile, "ownership_info", side_effect=metadata):
                with self.assertRaises(ValueError):
                    profile.install(self.root)
            self.assertFalse((self.root / profile.TARGET).exists())
            self.assertFalse((self.root / profile.STATE).exists())

    def test_private_directory_and_state_ownership_permissions_required(self):
        profile.install(self.root)
        for unsafe, owner, mode in ((profile.STATE.parent, profile.ROOT_UID, 0o755),
                                   (profile.STATE, profile.ROOT_UID + 1, 0o600),
                                   (profile.STATE, profile.ROOT_UID, 0o644)):
            def metadata(path):
                if path == self.root / unsafe:
                    kind = stat.S_IFDIR if path.is_dir() else stat.S_IFREG
                    return SimpleNamespace(st_uid=owner, st_mode=kind | mode)
                return self.fixture_info(path)
            with self.subTest(path=unsafe, owner=owner, mode=mode), patch.object(profile, "ownership_info", side_effect=metadata):
                with self.assertRaises(ValueError):
                    profile.rollback(self.root)
            self.assertEqual((self.root / profile.TARGET).read_bytes(), profile.load_profile())

    def test_invalid_saved_owner_group_or_mode_rejected_before_restore(self):
        self.write(profile.TARGET, b"previous")
        profile.install(self.root)
        state = self.root / profile.STATE
        original = json.loads(state.read_text())
        for field, value in (("uid", profile.ROOT_UID + 1), ("gid", 2**32),
                             ("mode", 0o4755), ("mode", 0o666), ("gid", True)):
            modified = dict(original, **{field: value})
            state.write_text(json.dumps(modified))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                profile.rollback(self.root)
            self.assertEqual((self.root / profile.TARGET).read_bytes(), profile.load_profile())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Linux FIFO fixture")
    def test_fifo_cannot_block_profile_read(self):
        path = self.root / profile.TARGET
        path.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "regular file"):
            profile.install(self.root)
        self.assertFalse((self.root / profile.STATE).exists())

    def test_symlink_target_is_rejected(self):
        path = self.root / profile.TARGET
        path.parent.mkdir(parents=True, exist_ok=True)
        other = self.root / "unrelated"
        other.write_bytes(b"untouched")
        try:
            path.symlink_to(other)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "symlink"):
            profile.install(self.root)
        self.assertEqual(other.read_bytes(), b"untouched")

    def test_context_guards_root_kernel_os_and_device(self):
        self.context.stop()
        profile.check_context(self.root, uid=0, release=profile.KERNEL)
        with self.assertRaisesRegex(ValueError, "root"):
            profile.check_context(self.root, uid=32011, release=profile.KERNEL)
        with self.assertRaisesRegex(ValueError, "kernel"):
            profile.check_context(self.root, uid=0, release="recovery")
        self.write(Path("etc/os-release"), b"ID=ubuntu\nVERSION_ID=22.04\n")
        with self.assertRaisesRegex(ValueError, "24.04"):
            profile.check_context(self.root, uid=0, release=profile.KERNEL)
        self.write(Path("etc/os-release"), b"ID=ubuntu\nVERSION_ID=24.04\n")
        with self.assertRaisesRegex(ValueError, "24.04"):
            profile.check_context(self.root, uid=0, release=profile.KERNEL)
        self.write(Path("etc/os-release"), b"ID=ubuntu\nVERSION_ID=24.04\nVARIANT_ID=touch\n")
        self.write(profile.DEVICEINFO, b"Names: [unrelated]\n")
        with self.assertRaisesRegex(ValueError, "device"):
            profile.check_context(self.root, uid=0, release=profile.KERNEL)

    def test_cli_status_can_read_fixture_and_bad_root_does_not_write(self):
        result = subprocess.run([sys.executable, str(TOOL), "--status", "--root", str(self.root)],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["profile_matches"])
        result = subprocess.run([sys.executable, str(TOOL), "--install", "--root", str(self.root)],
                                text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / profile.TARGET).exists())


if __name__ == "__main__":
    unittest.main()
