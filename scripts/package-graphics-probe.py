"""Package the BOOT 6 one-shot graphics probe for the original Windows folder."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('scripts/manage-graphics-probe.py', 'scripts/collect-first-boot.py',
           'tools/windows/PREPARA-TEST-GRAFICA-1.cmd', 'tools/windows/LEGGI-TEST-GRAFICA-1.cmd',
           'tools/windows/RIMUOVI-TEST-GRAFICA-1.cmd', 'tools/windows/LEGGIMI-TEST-GRAFICA-1.txt')


def package(output):
    spec = importlib.util.spec_from_file_location('graphics_probe_manager', ROOT / SOURCES[0])
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    if set(manager.PAYLOAD_SHA256) != set(manager.ASSET_NAMES):
        raise ValueError('payload_pins_unavailable')
    members = {}
    for name in SOURCES:
        value = (ROOT / name).read_text(encoding='ascii').replace('\r\n', '\n')
        if name.endswith(('.cmd', '.txt')):
            value = value.replace('\n', '\r\n')
        members[name.removeprefix('tools/windows/')] = value.encode('ascii')
    for name in manager.ASSET_NAMES:
        value = (ROOT / 'tools/graphics-probe' / name).read_bytes()
        if b'\r' in value or hashlib.sha256(value).hexdigest() != manager.PAYLOAD_SHA256[name]:
            raise ValueError('local_payload_hash_mismatch')
        members['graphics-probe-1/' + name] = value
    members['SHA256SUMS-graphics-probe-1'] = ''.join(
        hashlib.sha256(value).hexdigest() + '  ' + name + '\n'
        for name, value in sorted(members.items())).encode('ascii')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, value in sorted(members.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, value, compresslevel=9)
    result = {'filename': output.name, 'bytes': output.stat().st_size,
              'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'members': len(members), 'payload_sha256': dict(manager.PAYLOAD_SHA256)}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
        default=ROOT / 'out/UbuntuTouch-S10plus-test-grafica-1-Windows.zip')
    package(parser.parse_args().output)
