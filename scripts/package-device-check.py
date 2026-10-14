#!/usr/bin/env python3
"""Package the Windows read-only inventory and verified official ADB binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip"
SHA256 = "45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "out/UbuntuTouch-S10plus-controllo-Windows.zip")
    args = parser.parse_args()
    archive = args.archive or ROOT / "out/platform-tools-r37.0.1-windows.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        with urllib.request.urlopen(URL, timeout=40) as response, archive.open("wb") as out:
            while block := response.read(1048576):
                out.write(block)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Official platform-tools archive checksum mismatch")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as upstream, zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        names = ["platform-tools/adb.exe", "platform-tools/NOTICE.txt", "platform-tools/source.properties"]
        names += [name for name in upstream.namelist() if name.startswith("platform-tools/") and name.endswith(".dll")]
        hashes = {}
        for name in names:
            contents = upstream.read(name)
            if name.endswith((".exe", ".dll")) and contents[:2] != b"MZ":
                raise ValueError("Invalid Windows executable: " + name)
            package.writestr(name, contents)
            hashes[name] = hashlib.sha256(contents).hexdigest()
        for name in ["AVVIA-CONTROLLO.cmd", "scripts/launch-device-check.ps1", "scripts/collect-device.ps1"]:
            source = ROOT / ('tools/windows/' + name if name == 'AVVIA-CONTROLLO.cmd' else name)
            contents = source.read_text().replace("\r\n", "\n").replace("\n", "\r\n").encode()
            package.writestr(name, contents)
            hashes[name] = hashlib.sha256(contents).hexdigest()
        package.write(ROOT / "tools/windows/LEGGIMI.txt", "LEGGIMI.txt")
        package.writestr("package-manifest.json", json.dumps({"adb_version": "37.0.1", "upstream_url": URL,
                         "upstream_sha256": SHA256, "files_sha256": hashes, "phone_tested": False}, indent=2) + "\n")
    with zipfile.ZipFile(args.output) as package:
        if package.testzip() is not None:
            raise ValueError("Package ZIP integrity check failed")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
