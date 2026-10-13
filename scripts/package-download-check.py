"""Package the pinned Windows Download-mode inventory; no image is flashed."""
import argparse
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/topjohnwu/samloader-rs/releases/download/2.2.0/samloader-v2.2.0-windows-x86_64.zip'
ARCHIVE_SHA256 = '0132de1b79e208138f980c467f9a7eaa2ffcb72aae14afc3ed13799803c9b9ed'
EXE_SHA256 = 'b83b8244ecc86ecb4f5efc08e1604214d869838ca59b329e02a34e70832d175b'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'out' / 'UbuntuTouch-S10plus-controllo-Download-Windows.zip')
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(5_000_001)
    if len(data) != 1_418_327 or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Publisher archive size or SHA-256 mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist() != ['samloader.exe']:
            raise ValueError('Unexpected publisher archive contents')
        exe = archive.read('samloader.exe')
    if hashlib.sha256(exe).hexdigest() != EXE_SHA256:
        raise ValueError('Executable SHA-256 mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('tools/samloader/samloader.exe', exe)
        for source, destination in [
            ('scripts/check-download-mode.ps1', 'scripts/check-download-mode.ps1'),
            ('tools/windows/CONTROLLA-DOWNLOAD.cmd', 'CONTROLLA-DOWNLOAD.cmd'),
            ('tools/windows/LEGGIMI-DOWNLOAD.txt', 'LEGGIMI-DOWNLOAD.txt'),
            ('tools/windows/licenses/samloader-LICENSE-APACHE.txt', 'licenses/samloader-LICENSE-APACHE.txt'),
            ('tools/windows/licenses/samloader-LICENSE-MIT.txt', 'licenses/samloader-LICENSE-MIT.txt'),
        ]:
            content = (ROOT / source).read_text()
            # Windows PowerShell 5.1 reads BOM-less input with its legacy code page.
            if not content.isascii():
                raise ValueError(f'Windows source must be ASCII: {source}')
            archive.writestr(destination, content.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii'))
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
