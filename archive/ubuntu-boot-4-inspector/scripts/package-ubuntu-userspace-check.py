"""Package the read-only BOOT 4 handoff inspector for established Windows tools."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['scripts/collect-ubuntu-userspace.py', 'scripts/inspect-ubuntu-userspace.sh',
           'scripts/collect-first-boot.py', 'tools/windows/CONTROLLA-PASSAGGIO-UBUNTU-4.cmd',
           'tools/windows/LEGGIMI-PASSAGGIO-UBUNTU-4.txt']


def package(output):
    members = {}
    for name in SOURCES:
        data = (ROOT / name).read_bytes().decode('ascii').replace('\r\n', '\n')
        if name.endswith(('.cmd', '.txt')):
            data = data.replace('\n', '\r\n')
        target = name.removeprefix('tools/windows/')
        members[target] = data.encode('ascii')
    members['SHA256SUMS-userspace-4'] = ''.join(
        hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in sorted(members.items())).encode('ascii')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compresslevel=9)
    result = {'filename': output.name, 'bytes': output.stat().st_size,
              'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    print(result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'out/UbuntuTouch-S10plus-controllo-passaggio-Ubuntu-4-Windows.zip')
    package(parser.parse_args().output)
