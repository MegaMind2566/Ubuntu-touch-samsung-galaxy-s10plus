#!/usr/bin/env python3
"""Package a pinned, download-only Windows workflow for the exact stock target."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/topjohnwu/samloader-rs/releases/download/2.2.0/samloader-v2.2.0-windows-x86_64.zip"
DIGEST = "0132de1b79e208138f980c467f9a7eaa2ffcb72aae14afc3ed13799803c9b9ed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "out/UbuntuTouch-S10plus-scarica-firmware-ITV-Windows.zip")
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=30) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != DIGEST:
        raise ValueError("Publisher release archive checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as release:
        executables = [name for name in release.namelist() if Path(name).name == "samloader.exe"]
        if len(executables) != 1:
            raise ValueError("Expected exactly one Windows samloader executable")
        exe = release.read(executables[0])
    if exe[:2] != b"MZ":
        raise ValueError("Not a Windows executable")
    target = json.loads((ROOT / "docs/stock-firmware-target-2026-10-12.json").read_text())
    settings = {"target": target, "samloader_version": "2.2.0", "upstream_url": URL,
                "upstream_sha256": DIGEST, "samloader_exe_sha256": hashlib.sha256(exe).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("tools/samloader.exe", exe)
        for source, name in [
            ("tools/windows/SCARICA-FIRMWARE.cmd", "SCARICA-FIRMWARE.cmd"),
            ("scripts/download-stock-firmware.ps1", "scripts/download-stock-firmware.ps1"),
            ("tools/windows/LEGGIMI-FIRMWARE.txt", "LEGGIMI.txt"),
            ("third-party/samloader/LICENSE", "licenses/LICENSE-samloader"),
            ("third-party/samloader/LICENSE-MIT", "licenses/LICENSE-Heimdall"),
        ]:
            contents = (ROOT / source).read_text().replace("\r\n", "\n").replace("\n", "\r\n").encode()
            package.writestr(name, contents)
        package.writestr("package-settings.json", json.dumps(settings, indent=2) + "\n")
    with zipfile.ZipFile(args.output) as package:
        if package.testzip() is not None:
            raise ValueError("Package integrity check failed")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
