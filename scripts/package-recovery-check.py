"""Package a read-only TWRP collector with pinned official Google ADB."""
import argparse
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip'
SHA256 = '45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'out/UbuntuTouch-S10plus-controllo-recovery-Windows.zip')
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=45) as source:
            data = source.read(20_000_001)
    if len(data) > 20_000_000 or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Official Google platform-tools checksum mismatch')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as upstream, zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        names = ['platform-tools/adb.exe','platform-tools/AdbWinApi.dll','platform-tools/AdbWinUsbApi.dll',
                 'platform-tools/libwinpthread-1.dll','platform-tools/NOTICE.txt','platform-tools/source.properties']
        for name in names:
            content = upstream.read(name)
            if name.endswith(('.exe','.dll')) and content[:2] != b'MZ':
                raise ValueError('Invalid publisher executable')
            output.writestr(name, content)
        for source, destination in [
            ('scripts/check-recovery.ps1','scripts/check-recovery.ps1'),
            ('scripts/check-download-mode.ps1','scripts/check-download-mode.ps1'),
            ('tools/windows/CONTROLLA-RECOVERY.cmd','CONTROLLA-RECOVERY.cmd'),
            ('tools/windows/LEGGIMI-CONTROLLO-RECOVERY.txt','LEGGIMI-CONTROLLO-RECOVERY.txt'),
        ]:
            content = (ROOT / source).read_text()
            if not content.isascii():
                raise ValueError('Non-ASCII Windows source: ' + source)
            output.writestr(destination, content.replace('\r\n','\n').replace('\n','\r\n').encode('ascii'))
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
