import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fetch_sources.py"
SPEC = importlib.util.spec_from_file_location("fetch_sources", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


class PinnedSources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "source"
        self.repo.mkdir()
        git(self.repo, "init", "--quiet")
        git(self.repo, "config", "user.name", "Build test")
        git(self.repo, "config", "user.email", "build-test@example.invalid")
        self.file = self.repo / "file.txt"
        self.file.write_text("first\n")
        git(self.repo, "add", "file.txt")
        git(self.repo, "commit", "--quiet", "-m", "first")
        self.first = git(self.repo, "rev-parse", "HEAD")
        self.file.write_text("second\n")
        git(self.repo, "commit", "--quiet", "-am", "second")
        self.second = git(self.repo, "rev-parse", "HEAD")
        self.url = "https://example.invalid/locked-source.git"
        git(self.repo, "remote", "add", "origin", self.url)
        self.spec = {"commit": self.first, "url": self.url}

    def test_existing_checkout_uses_pin_instead_of_stale_fetch_head(self):
        # Original script could silently continue at an arbitrary HEAD.
        (self.repo / ".git/FETCH_HEAD").write_text(self.second + "\n")
        module.checkout(self.spec, self.repo)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.first)
        self.assertEqual(self.file.read_text(), "first\n")

    def test_dirty_checkout_is_preserved(self):
        self.file.write_text("local changes\n")
        with self.assertRaisesRegex(RuntimeError, "local changes"):
            module.checkout(self.spec, self.repo)
        self.assertEqual(self.file.read_text(), "local changes\n")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.second)

    def test_wrong_remote_is_rejected(self):
        git(self.repo, "remote", "set-url", "origin", "https://example.invalid/other.git")
        with self.assertRaisesRegex(RuntimeError, "Unexpected source remote"):
            module.checkout(self.spec, self.repo)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.second)

    def test_non_git_directory_is_preserved(self):
        destination = Path(self.tmp.name) / "not-git"
        destination.mkdir()
        (destination / "important.txt").write_text("keep")
        with self.assertRaisesRegex(RuntimeError, "nonempty, non-Git"):
            module.checkout(self.spec, destination)
        self.assertEqual((destination / "important.txt").read_text(), "keep")

    def test_fetch_failure_does_not_report_success(self):
        self.spec["commit"] = "0" * 40
        # No network: use a nonexistent local repository as the expected remote.
        self.spec["url"] = str(Path(self.tmp.name) / "missing.git")
        git(self.repo, "remote", "set-url", "origin", self.spec["url"])
        with self.assertRaises(subprocess.CalledProcessError):
            module.checkout(self.spec, self.repo)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.second)


if __name__ == "__main__":
    unittest.main()
