"""Preflight the exact locally prepared S10+ recovery. No USB/write code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

RECOVERY_SHA256 = 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e'
RECOVERY_BYTES = 57_556_992
VBMETA_SHA256 = '9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025'
STOCK_SHA256 = 'c7d956cf40cc01b09fccc260540fb65a16ed5ff60fbed1d32abf7fd0f6c32a4d'
STOCK_BYTES = 6_364_940_601
PIT_SHA256 = 'aa3555ff93ff568186d64aa0e71b6f50bcf2edf26aecec7c6d74410cf4e7b58a'


class VerificationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise VerificationError(code)


def file_sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def read_json(path):
    require(path.is_file() and path.stat().st_size <= 131072, 'state_missing_or_oversized')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify_images(directory):
    recovery = directory / 'recovery-test.img'
    vbmeta = directory / 'vbmeta-test.img'
    for path, length, expected in ((recovery, RECOVERY_BYTES, RECOVERY_SHA256),
                                   (vbmeta, 65536, VBMETA_SHA256)):
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == length,
                'prepared_image_size_mismatch')
        require(file_sha256(path) == expected, 'prepared_image_sha256_mismatch')
    header = recovery.open('rb')
    with header:
        data = header.read(2048)
    require(data[:8] == b'ANDROID!' and struct.unpack_from('<I', data, 40)[0] == 1,
            'recovery_header_mismatch')
    data = vbmeta.read_bytes()
    require(data[:4] == b'AVB0' and struct.unpack_from('>I', data, 28)[0] == 0
            and struct.unpack_from('>Q', data, 112)[0] == 0
            and struct.unpack_from('>I', data, 120)[0] == 3,
            'vbmeta_header_mismatch')
    return {'recovery_path': str(recovery), 'vbmeta_path': str(vbmeta)}


def verify_stock(path):
    require(path.is_file() and path.stat().st_size == STOCK_BYTES, 'stock_firmware_missing_or_size_mismatch')
    require(file_sha256(path) == STOCK_SHA256, 'stock_firmware_sha256_mismatch')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for prefix in ('BL_G975FXXSGHWC1_', 'AP_G975FXXSGHWC1_', 'CP_G975FXXSGHWB3_',
                       'CSC_OXM_G975FOXMGHWA3_', 'HOME_CSC_OXM_G975FOXMGHWA3_'):
            require(sum(Path(name).name.startswith(prefix) and name.endswith('.tar.md5')
                        for name in names) == 1, 'stock_firmware_packages_mismatch')


def verify_files(root):
    root = root.resolve()
    state = read_json(root / 'recovery-local-state.json')
    report = state.get('report', {})
    require(report.get('schema') == 1 and report.get('preparer_version') == 1
            and report.get('model') == 'SM-G975F' and report.get('pda') == 'G975FXXSGHWC1'
            and report.get('success') is True and report.get('backup_verified') is True
            and report.get('expected_pit_sha256') == PIT_SHA256, 'preparation_state_not_verified')
    require(report.get('recovery', {}).get('prepared_sha256') == RECOVERY_SHA256
            and report.get('vbmeta', {}).get('sha256') == VBMETA_SHA256
            and report.get('stock_firmware', {}).get('sha256') == STOCK_SHA256,
            'preparation_state_hash_mismatch')
    directory = Path(state['prepared_directory']).resolve()
    require(directory.parent == root and directory.name.startswith('prepared-recovery-'),
            'prepared_directory_outside_package')
    images = verify_images(directory)
    stock = Path(state['stock_firmware_path']).resolve()
    print('Ricontrollo il firmware di ripristino. Puo richiedere alcuni minuti.', flush=True)
    verify_stock(stock)
    return {**images, 'stock_firmware_path': str(stock), 'backup_verified': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # This private result contains PC paths and is never included in an upload.
    args.output.unlink(missing_ok=True)
    try:
        result = {'success': True, 'error': None, **verify_files(args.root)}
    except Exception as error:
        result = {'success': False,
                  'error': str(error) if isinstance(error, VerificationError) else 'local_verification_failed'}
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('Controllo dei file completato.' if result['success'] else 'Controllo dei file non superato.', flush=True)
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
