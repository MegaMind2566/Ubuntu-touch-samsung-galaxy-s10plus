"""Small add-on for the existing preparation folder; no TWRP/image mirror."""
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
    parser.add_argument('--output', type=Path, default=ROOT / 'out' / 'UbuntuTouch-S10plus-installa-recovery-test-Windows.zip')
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(5_000_001)
    if len(data) != 1_418_327 or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Publisher samloader archive mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist() != ['samloader.exe']:
            raise ValueError('Publisher samloader archive members mismatch')
        exe = archive.read('samloader.exe')
    if hashlib.sha256(exe).hexdigest() != EXE_SHA256:
        raise ValueError('Publisher samloader executable mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('tools/samloader/samloader.exe', exe)
        for source, destination in [
            ('scripts/flash-recovery-test.ps1', 'scripts/flash-recovery-test.ps1'),
            ('scripts/check-download-mode.ps1', 'scripts/check-download-mode.ps1'),
            ('scripts/verify_recovery_test.py', 'scripts/verify_recovery_test.py'),
            ('tools/windows/INSTALLA-RECOVERY-TEST.cmd', 'INSTALLA-RECOVERY-TEST.cmd'),
            ('tools/windows/LEGGIMI-RECOVERY-TEST.txt', 'LEGGIMI-RECOVERY-TEST.txt'),
            ('tools/windows/licenses/samloader-LICENSE-APACHE.txt', 'licenses/samloader-LICENSE-APACHE.txt'),
            ('tools/windows/licenses/samloader-LICENSE-MIT.txt', 'licenses/samloader-LICENSE-MIT.txt'),
        ]:
            content = (ROOT / source).read_text()
            if not content.isascii():
                raise ValueError('Non-ASCII Windows source: ' + source)
            if destination.endswith(('.ps1', '.cmd', '.txt')):
                content = content.replace('\r\n', '\n').replace('\n', '\r\n')
            archive.writestr(destination, content.encode('ascii'))
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
