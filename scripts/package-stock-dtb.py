#!/usr/bin/env python3
"""Create the small Windows add-on that reads an already downloaded firmware."""
import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, name in [
            ("tools/windows/ESTRAI-DTB.cmd", "ESTRAI-DTB.cmd"),
            ("tools/windows/LEGGIMI-DTB.txt", "LEGGIMI-DTB.txt"),
            ("scripts/extract-stock-dtb.ps1", "scripts/extract-stock-dtb.ps1"),
        ]:
            contents = (ROOT / source).read_text().replace("\r\n", "\n").replace("\n", "\r\n").encode()
            archive.writestr(name, contents)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Package CRC failed")
    print(output.resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "out/UbuntuTouch-S10plus-controllo-DTB-Windows.zip")
    package(parser.parse_args().output)
