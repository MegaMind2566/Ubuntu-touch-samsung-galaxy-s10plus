import importlib.util
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assembly = load("graphics_assembly", ROOT / "scripts/graphics_assembly.py")
validator = load("graphics_system_validator", ROOT / "scripts/validate_system.py")
SOURCE = ROOT / "tools/graphics-permissions" / assembly.RULE_FILENAME
ORIGINAL_EXCERPT = ('#!/bin/bash\nHERE=$(pwd)\nOUTPUT="$2"\nfile=fixture.tar.gz\n'
                    'print_header() { :; }\n' + assembly.EXTRACTION + '\n'
                    + assembly.DEVELOPMENT_DEFAULTS + ', for debugging in devel-flashable builds\n'
                    'echo unsafe > system/etc/default/adbd\n\n' + assembly.REPACK + '\n')


class GraphicsAssembly(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="graphics fixture ")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.root = self.work / "ota/rootfs/system"
        self.directory = self.root / "usr/lib/udev/rules.d"
        self.directory.mkdir(parents=True)

    def link_directory(self, link, target):
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                                    capture_output=True)
            if result.returncode:
                self.skipTest("Host does not permit symlink or junction fixtures")
        self.addCleanup(lambda: link.rmdir() if getattr(link, "is_junction", lambda: False)() else link.unlink())

    def test_exact_payload_is_installed_without_touching_other_rules_and_is_idempotent(self):
        other = self.directory / "70-other.rules"
        other.write_bytes(b"existing rule\n")
        first = assembly.install_rules(self.root, SOURCE)
        self.assertTrue(first["created"])
        target = self.directory / assembly.RULE_FILENAME
        self.assertEqual(target.read_bytes(), SOURCE.read_bytes())
        self.assertEqual(other.read_bytes(), b"existing rule\n")
        before = target.stat().st_mtime_ns
        self.assertFalse(assembly.install_rules(self.root, SOURCE)["created"])
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertFalse((self.directory / "70-exynos7904.rules").exists())

    def test_conflicting_rule_is_preserved(self):
        target = self.directory / assembly.RULE_FILENAME
        target.write_bytes(b"unknown rule\n")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            assembly.install_rules(self.root, SOURCE)
        self.assertEqual(target.read_bytes(), b"unknown rule\n")

    def test_crlf_or_modified_source_is_rejected(self):
        source = self.work / "changed.rules"
        for data in (SOURCE.read_bytes().replace(b"\n", b"\r\n"), SOURCE.read_bytes() + b"# changed\n"):
            source.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "canonical LF"):
                assembly.install_rules(self.root, source)
        self.assertFalse((self.directory / assembly.RULE_FILENAME).exists())

    def test_parent_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "traversal"):
            assembly.install_rules(self.root / ".." / "system", SOURCE)
        self.assertFalse((self.directory / assembly.RULE_FILENAME).exists())

    def test_symlink_or_junction_root_is_rejected(self):
        link = self.work / "linked-root"
        self.link_directory(link, self.root)
        with self.assertRaisesRegex(ValueError, "symlink|junction"):
            assembly.install_rules(link, SOURCE)
        self.assertFalse((self.directory / assembly.RULE_FILENAME).exists())

    def test_symlink_or_junction_nested_directory_cannot_escape_rootfs(self):
        outside = self.work / "outside"
        outside.mkdir()
        self.directory.rmdir()
        self.link_directory(self.directory, outside)
        with self.assertRaisesRegex(ValueError, "symlink|junction"):
            assembly.install_rules(self.root, SOURCE)
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_hardlink_is_rejected_without_altering_its_external_file(self):
        outside = self.work / "outside.rules"
        outside.write_bytes(SOURCE.read_bytes())
        os.link(outside, self.directory / assembly.RULE_FILENAME)
        with self.assertRaisesRegex(ValueError, "regular file"):
            assembly.install_rules(self.root, SOURCE)
        self.assertEqual(outside.read_bytes(), SOURCE.read_bytes())

    def test_changed_or_duplicate_upstream_context_is_rejected(self):
        for text in (ORIGINAL_EXCERPT.replace('cd "$OUTPUT/rootfs"', 'cd elsewhere'),
                     ORIGINAL_EXCERPT + '\n' + assembly.REPACK,
                     ORIGINAL_EXCERPT.replace('HERE=$(pwd)', 'HERE=/'),
                     ORIGINAL_EXCERPT.replace(assembly.EXTRACTION, '') + assembly.EXTRACTION):
            with self.assertRaisesRegex(ValueError, "Upstream preparation"):
                assembly.patch_preparation(text)

    def shell(self):
        candidate = Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else None
        bash = str(candidate) if candidate and candidate.is_file() else shutil.which("bash")
        if not bash:
            self.skipTest("bash required for the real preparation-hook fixture")
        return bash

    def prepare_shell_fixture(self, conflict=False):
        # A real, tiny gzip rootfs archive exercises extraction, helper execution
        # and repacking. It is not an ext4 image and contains no handset data.
        build = self.work / "build"
        build.mkdir()
        shutil.copy2(ROOT / "scripts/graphics_assembly.py", build / "graphics_assembly.py")
        shutil.copy2(SOURCE, build / assembly.RULE_FILENAME)
        with tarfile.open(self.work / "ota/fixture.tar.gz", "w:gz") as archive:
            entry = tarfile.TarInfo("usr/lib/udev/rules.d")
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o755
            archive.addfile(entry)
            if conflict:
                data = b"conflicting fixture\n"
                entry = tarfile.TarInfo("usr/lib/udev/rules.d/" + assembly.RULE_FILENAME)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        shim = self.work / "bin"
        shim.mkdir()
        # Use the test interpreter rather than whichever python3 an interactive
        # shell happens to find; the production hook still calls python3.
        launcher = shim / "python3"
        launcher.write_bytes(("#!/bin/sh\nexec " + shlex.quote(sys.executable.replace("\\", "/")) + ' "$@"\n').encode())
        launcher.chmod(0o755)
        script = self.work / "prepare.sh"
        script.write_bytes(assembly.patch_preparation(ORIGINAL_EXCERPT).encode())
        environment = dict(os.environ)
        environment["PATH"] = str(shim) + os.pathsep + environment.get("PATH", "")
        return script, environment

    def test_generated_hook_executes_in_real_shell_before_real_tar_repack(self):
        script, environment = self.prepare_shell_fixture()
        result = subprocess.run([self.shell(), script.name, "unused", "ota"], cwd=self.work,
                                env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.work / "ota/rootfs.tar.xz") as archive:
            data = archive.extractfile("system" + assembly.RULE_PATH).read()
            self.assertEqual(data, SOURCE.read_bytes())
            self.assertNotIn("system/usr/lib/udev/rules.d/70-exynos7904.rules", archive.getnames())
        self.assertFalse((self.root / "etc/default/adbd").exists())

    def test_hook_failure_stops_upstream_even_without_global_errexit(self):
        script, environment = self.prepare_shell_fixture(conflict=True)
        result = subprocess.run([self.shell(), script.name, "unused", "ota"], cwd=self.work,
                                env=environment, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "ota/rootfs.tar.xz").exists())
        self.assertEqual((self.directory / assembly.RULE_FILENAME).read_bytes(), b"conflicting fixture\n")

    def test_validator_requires_exact_rules_and_rejects_missing_or_changed_content(self):
        self.assertEqual(assembly.RULE_SHA256, validator.GRAPHICS_RULE_SHA256)
        self.assertEqual(assembly.RULE_PATH, validator.GRAPHICS_RULE_PATH)
        with mock.patch.object(validator, "image_read", return_value=SOURCE.read_bytes()):
            self.assertTrue(validator.validate_graphics_rules(Path("fixture.img"))["content_verified"])
        with mock.patch.object(validator, "image_read", return_value=SOURCE.read_bytes() + b"\n"):
            with self.assertRaisesRegex(ValueError, "graphics rules differ"):
                validator.validate_graphics_rules(Path("fixture.img"))
        with mock.patch.object(validator, "image_read", side_effect=ValueError("Missing filesystem path")):
            with self.assertRaisesRegex(ValueError, "Missing filesystem path"):
                validator.validate_graphics_rules(Path("fixture.img"))


if __name__ == "__main__":
    unittest.main()
