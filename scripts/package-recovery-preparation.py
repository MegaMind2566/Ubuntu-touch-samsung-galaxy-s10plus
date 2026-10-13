"""Package an offline Windows preparer. Never bundle or mirror TWRP images."""
import argparse
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = 'https://www.python.org/ftp/python/3.14.4/python-3.14.4-embed-amd64.zip'
PYTHON_SHA256 = 'cda80a9b1e75c0f1b4f9872ca1b417f0d19bce32facc811aea9180e70fad5fb9'
AVB_URL = 'https://raw.githubusercontent.com/AndroidBootloader/platform_external_avb/b27a9aa53d2db7720e4d88d6950dcd979da97de3/avbtool.py'
AVB_SHA256 = '1183d0d19467b24b064e59191e3040260ede45f2bacaa8aa44f47be460909bb5'


def read_source(local, url, limit):
    if local:
        data = local.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Dependency size limit exceeded')
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python-archive', type=Path)
    parser.add_argument('--avbtool', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'out' / 'UbuntuTouch-S10plus-prepara-recovery-Windows.zip')
    args = parser.parse_args()
    runtime = read_source(args.python_archive, PYTHON_URL, 20_000_000)
    if len(runtime) != 12_034_740 or hashlib.sha256(runtime).hexdigest() != PYTHON_SHA256:
        raise ValueError('Official Python archive checksum/size mismatch')
    avbtool = read_source(args.avbtool, AVB_URL, 250_000)
    if hashlib.sha256(avbtool).hexdigest() != AVB_SHA256:
        raise ValueError('Pinned AOSP avbtool checksum mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        with zipfile.ZipFile(io.BytesIO(runtime)) as source:
            if source.testzip() or len(source.namelist()) != len(set(source.namelist())):
                raise ValueError('Invalid runtime archive')
            for name in source.namelist():
                if '/' in name or '\\' in name or name in ('.', '..'):
                    raise ValueError('Unexpected runtime path')
                output.writestr('tools/python/' + name, source.read(name))
        output.writestr('tools/avbtool.py', avbtool)
        for source, destination in [
            ('scripts/prepare_recovery.py', 'scripts/prepare_recovery.py'),
            ('scripts/prepare-recovery.ps1', 'scripts/prepare-recovery.ps1'),
            ('scripts/inspect_stock_firmware.py', 'scripts/inspect_stock_firmware.py'),
            ('tools/windows/PREPARA-RECOVERY.cmd', 'PREPARA-RECOVERY.cmd'),
            ('tools/windows/LEGGIMI-RECOVERY.txt', 'LEGGIMI-RECOVERY.txt'),
            ('tools/windows/licenses/samloader-LICENSE-APACHE.txt', 'licenses/avbtool-LICENSE-APACHE.txt'),
        ]:
            content = (ROOT / source).read_text()
            if not content.isascii():
                raise ValueError('Non-ASCII Windows source: ' + source)
            if destination.endswith(('.ps1', '.cmd', '.txt')):
                content = content.replace('\r\n', '\n').replace('\n', '\r\n')
            output.writestr(destination, content.encode('ascii'))
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
