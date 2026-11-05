"""Verify recovered text identities without importing or executing payloads."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import unittest


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "tools/runtime-fixes"


class PreservedSourceTests(unittest.TestCase):
    def test_manifest_covers_exact_recovered_bytes_and_existing_trrs_source(self):
        manifest = json.loads((SNAPSHOTS / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["recovered_on"], "2026-11-05")
        entries = manifest["files"]
        self.assertEqual(len(entries), 12)
        paths = set()
        for entry in entries:
            relative = PurePosixPath(entry["repository_path"])
            with self.subTest(file=str(relative)):
                self.assertFalse(relative.is_absolute())
                self.assertNotIn("..", relative.parts)
                self.assertNotIn(str(relative), paths)
                paths.add(str(relative))
                data = (ROOT / relative).read_bytes()
                if str(relative) == "scripts/ut-s10-trrs-integrato.py":
                    data = data.replace(b"\r\n", b"\n")
                else:
                    self.assertTrue(str(relative).startswith("tools/runtime-fixes/"))
                    self.assertNotIn(b"\r\n", data)
                self.assertNotIn(b"\x00", data)
                data.decode("utf-8")
                self.assertEqual(len(data), entry["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                self.assertTrue(entry["normal_os_path"].startswith("/"))
                self.assertFalse(entry["normal_os_path"].startswith(("/system_root/", "/data/user-data/", "/data/system-data/")))
        actual = {p.relative_to(ROOT).as_posix() for p in SNAPSHOTS.rglob("*")
                  if p.is_file() and p.name not in {"manifest.json", "README.md"}}
        self.assertEqual(actual, paths - {"scripts/ut-s10-trrs-integrato.py"})


if __name__ == "__main__":
    unittest.main()
