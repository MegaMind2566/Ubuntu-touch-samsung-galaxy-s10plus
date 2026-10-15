"""Build the alpha BOOT/tools ZIP from verified local inputs; no downloads."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.1.0-alpha.1'
PINS = {
    'boot.img': (57344000, '2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad'),
    'recovery.img': (57556992, 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e'),
    'vbmeta.img': (65536, '9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025'),
}
RUNTIMES = {
    'python': (12034740, 'cda80a9b1e75c0f1b4f9872ca1b417f0d19bce32facc811aea9180e70fad5fb9'),
    'adb': (8044989, '45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99'),
}
SOURCES = ('scripts/prepare-firmware-images.py', 'scripts/manage-graphics-permissions.py',
           'scripts/collect-first-boot.py', 'scripts/collect-ubuntu-graphics.py',
           'tools/windows/APPLICA-CORREZIONE-GRAFICA-1.cmd', 'tools/windows/LEGGI-CORREZIONE-GRAFICA-1.cmd',
           'tools/windows/ANNULLA-CORREZIONE-GRAFICA-1.cmd', 'tools/windows/LEGGIMI-CORREZIONE-GRAFICA-1.txt',
           'tools/windows/PREPARA-IMMAGINI-FIRMWARE.cmd', 'tools/windows/LEGGIMI-FIRMWARE-ALPHA.txt',
           'THIRD_PARTY.md')


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def validate(path, pin):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != pin[0] or sha256(path) != pin[1]:
        raise ValueError('release_input_identity_mismatch:' + path.name)


def safe_archive_files(path, prefix):
    members = {}
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('runtime_archive_crc_error')
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            parts = PurePosixPath(name).parts
            if ('\\' in name or name.startswith('/') or any(p in ('..', '.') for p in parts)
                    or ':' in name or ((entry.external_attr >> 16) & 0o170000) == 0o120000):
                raise ValueError('unsafe_runtime_member')
            target = prefix + name
            if target in members:
                raise ValueError('duplicate_runtime_member')
            members[target] = archive.read(entry)
    return members


def package(output, boot, python_archive, adb_archive, recovery=None, vbmeta=None):
    if bool(recovery) != bool(vbmeta):
        raise ValueError('recovery_vbmeta_pair_required')
    images = {'boot.img': Path(boot)}
    if recovery:
        images.update({'recovery.img': Path(recovery), 'vbmeta.img': Path(vbmeta)})
    for name, path in images.items():
        validate(path, PINS[name])
    validate(python_archive, RUNTIMES['python'])
    validate(adb_archive, RUNTIMES['adb'])
    members = safe_archive_files(python_archive, 'tools/python/')
    members.update(safe_archive_files(adb_archive, ''))
    required = ('tools/python/python.exe', 'tools/python/python314.zip', 'tools/python/_zstd.pyd',
                'platform-tools/adb.exe', 'platform-tools/NOTICE.txt')
    if not all(name in members for name in required):
        raise ValueError('incomplete_official_runtime')
    for name in SOURCES:
        value = (ROOT / name).read_bytes()
        if name.endswith(('.cmd', '.txt')):
            value = value.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        members[name.removeprefix('tools/windows/')] = value
    spec = importlib.util.spec_from_file_location('release_graphics_permissions', ROOT / 'scripts/manage-graphics-permissions.py')
    correction = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(correction)
    for name in correction.ASSET_NAMES:
        value = (ROOT / 'tools/graphics-permissions' / name).read_bytes()
        if hashlib.sha256(value).hexdigest() != correction.PAYLOAD_SHA256[name]:
            raise ValueError('graphics_payload_identity_mismatch')
        members['graphics-permissions-1/' + name] = value
    # Preserve the correction package manifest used by its standalone tools.
    correction_members = [n for n in members if n.startswith('graphics-permissions-1/')]
    members['SHA256SUMS-graphics-permissions-1'] = ''.join(
        hashlib.sha256(members[n]).hexdigest() + '  ' + n + '\n' for n in sorted(correction_members)).encode('ascii')
    install_pins = json.loads((ROOT / 'config/install-images.lock.json').read_text())
    manifest = {'schema': 1, 'release': VERSION, 'model': 'SM-G975F/DS', 'codename': 'beyond2lte',
                'firmware': 'G975FXXSGHWC1', 'ubuntu_touch': '24.04-2.x', 'halium': 12,
                'installation': 'manual advanced TWRP workflow; no phone image writer included',
                'images': {name: {'bytes': PINS[name][0], 'sha256': PINS[name][1]} for name in images},
                'separate_asset': {'name': 'SYSTEM.img.zst', 'bytes': install_pins['system_zstd_bytes'],
                                   'sha256': install_pins['system_zstd_sha256'],
                                   'raw_name': 'images/system.img', 'raw_bytes': install_pins['system_bytes'],
                                   'raw_sha256': install_pins['system_sha256']},
                'official_runtime_archives': {name: {'bytes': pin[0], 'sha256': pin[1]} for name, pin in RUNTIMES.items()},
                'graphics_payload_sha256': dict(correction.PAYLOAD_SHA256),
                'graphical_boot_touch_wifi': 'basic operation confirmed on one handset',
                'general_clean_install_validated': False, 'native_windows_runtime_executed_during_packaging': False}
    members['config/firmware-release.json'] = (json.dumps(manifest, indent=2) + '\n').encode('ascii')
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in members.items()}
    hashes.update({'images/' + name: pin[1] for name, pin in PINS.items() if name in images})
    members['SHA256SUMS'] = ''.join(value + '  ' + name + '\n' for name, value in sorted(hashes.items())).encode('ascii')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted([*members, *('images/' + name for name in images)]):
            entry = zipfile.ZipInfo(name, date_time=(2026, 10, 15, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            with archive.open(entry, 'w', force_zip64=True) as target:
                if name.startswith('images/'):
                    with images[name[7:]].open('rb') as source:
                        for block in iter(lambda: source.read(1024 * 1024), b''):
                            target.write(block)
                else:
                    target.write(members[name])
    result = {'filename': output.name, 'bytes': output.stat().st_size, 'sha256': sha256(output),
              'members': len(members) + len(images), 'images': manifest['images']}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, default=ROOT / 'out/ubuntu-boot-6-validated-images/boot.img')
    parser.add_argument('--python-archive', type=Path, required=True)
    parser.add_argument('--adb-archive', type=Path, required=True)
    parser.add_argument('--recovery', type=Path)
    parser.add_argument('--vbmeta', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / ('out/UbuntuTouch-S10plus-' + VERSION + '-boot-and-tools-Windows.zip'))
    args = parser.parse_args()
    package(args.output, args.boot, args.python_archive, args.adb_archive, args.recovery, args.vbmeta)
