"""Produce a small read-only add-on for the existing Windows installer."""
import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "out/UbuntuTouch-S10plus-controllo-primo-avvio-Windows.zip")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, destination in (
            ("scripts/collect-first-boot.py", "scripts/collect-first-boot.py"),
            ("tools/windows/CONTROLLA-PRIMO-AVVIO.cmd", "CONTROLLA-PRIMO-AVVIO.cmd"),
            ("tools/windows/LEGGIMI-PRIMO-AVVIO.txt", "LEGGIMI-PRIMO-AVVIO.txt"),
        ):
            text = (ROOT / source).read_text().replace("\r\n", "\n")
            if source.endswith((".cmd", ".txt")):
                text = text.replace("\n", "\r\n")
            archive.writestr(destination, text.encode("ascii"))
    print(str(args.output))


if __name__ == "__main__":
    main()
