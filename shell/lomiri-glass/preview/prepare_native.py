#!/usr/bin/env python3
"""Fetch immutable official Lomiri QML and prepare source only, never install it."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import lomiri_glass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package_dir = ROOT / "shell/lomiri-glass"
    _, lock, _, _ = lomiri_glass.load_package(package_dir)
    revision = lock["commit"]
    url = ("https://gitlab.com/api/v4/projects/25716028/repository/archive.tar.gz?sha="
           + revision)
    with tempfile.TemporaryDirectory(prefix="uos27-pinned-source-") as scratch:
        scratch = Path(scratch)
        archive = scratch / "source.tar.gz"
        request = urllib.request.Request(url, headers={"User-Agent": "uos27-source-preview/1"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as out:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 80 * 1024 * 1024:
                    raise RuntimeError("Unexpected upstream archive size")
                out.write(chunk)
        source = scratch / "source"
        with tarfile.open(archive, "r:gz") as tar:
            total = 0
            for member in tar:
                relative = PurePosixPath(member.name)
                parts = relative.parts
                if len(parts) < 3 or parts[1] != "qml" or not member.isfile():
                    continue
                if (relative.is_absolute() or "\\" in member.name
                        or any(part in ("..", "") or ":" in part for part in parts)
                        or member.size > 8 * 1024 * 1024):
                    raise RuntimeError("Unexpected upstream QML member")
                total += member.size
                if total > 80 * 1024 * 1024:
                    raise RuntimeError("Unexpected extracted QML size")
                target = source.joinpath(*parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as incoming, target.open("wb") as out:
                    shutil.copyfileobj(incoming, out)
        # The source preparation tool verifies every pinned upstream file and
        # the module/patch identities before applying to this disposable tree.
        result = lomiri_glass.prepare(source, args.output, package_dir)
        print(json.dumps({"result":"pass", "commit":revision,
                          "installed":False, "prepared_output":str(args.output)}))


if __name__ == "__main__":
    main()
