"""Prepare an S10+ recovery test locally. No USB or partition-writing code."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct
import subprocess
import sys
import urllib.request
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_stock_firmware import aligned, boot_header, digest, dtbo_table, load_avbtool, newc_files

ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAME = 'twrp-3.7.0_9-2-beyond2lte.img'
IMAGE_PAGE = 'https://eu.dl.twrp.me/beyond2lte/' + IMAGE_NAME + '.html'
IMAGE_URL = IMAGE_PAGE.removesuffix('.html')
IMAGE_SHA256 = 'c61eafa9146d4b148648d1ab6a0d9d2d4a2456ef6b95ce17df9a4f413b2cb07d'
IMAGE_BYTES = 57_554_944
RECOVERY_BYTES = 67_633_152
RC_NAME = 'init.recovery.exynos9820.rc'
RC_SHA256 = '330121771846a40ee65ad8e179d943cf7f5f2a6fdebdf6386971464a9044d33b'
NUKER_NAME = 'sbin/nuker.sh'
NUKER_SHA256 = '9c86d61807d149359f3bb52055916b8e4bd6083e245f52f85d00526317933107'
STOCK_BYTES = 6_364_940_601
STOCK_SHA256 = 'c7d956cf40cc01b09fccc260540fb65a16ed5ff60fbed1d32abf7fd0f6c32a4d'
PIT_SHA256 = 'aa3555ff93ff568186d64aa0e71b6f50bcf2edf26aecec7c6d74410cf4e7b58a'


class PreparationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise PreparationError(code)


def file_sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_stock(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size == STOCK_BYTES, 'stock_size_mismatch')
    require(file_sha256(path) == STOCK_SHA256, 'stock_sha256_mismatch')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for prefix in ('BL_G975FXXSGHWC1_', 'AP_G975FXXSGHWC1_', 'CP_G975FXXSGHWB3_', 'CSC_OXM_G975FOXMGHWA3_', 'HOME_CSC_OXM_G975FOXMGHWA3_'):
            require(sum(Path(name).name.startswith(prefix) and name.endswith('.tar.md5') for name in names) == 1, 'stock_packages_mismatch')
    return {'size_bytes': STOCK_BYTES, 'sha256': STOCK_SHA256, 'full_recovery_set_retained': True}


def download_original(root):
    directory = root / 'inputs'
    directory.mkdir(exist_ok=True)
    target = directory / IMAGE_NAME
    if target.exists():
        require(target.stat().st_size == IMAGE_BYTES and file_sha256(target) == IMAGE_SHA256, 'cached_recovery_mismatch')
        return target
    temporary = directory / (IMAGE_NAME + '.' + uuid.uuid4().hex + '.tmp')
    try:
        # Fetch the publisher page, then download for this user's local use.
        with urllib.request.urlopen(IMAGE_PAGE, timeout=30) as response:
            require(IMAGE_NAME.encode() in response.read(1024 * 1024), 'publisher_page_invalid')
        request = urllib.request.Request(IMAGE_URL, headers={'Referer': IMAGE_PAGE, 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open('wb') as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                require(output.tell() <= IMAGE_BYTES, 'recovery_download_oversized')
        require(temporary.stat().st_size == IMAGE_BYTES and file_sha256(temporary) == IMAGE_SHA256, 'publisher_recovery_mismatch')
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def decode_ramdisk(ramdisk):
    require(len(ramdisk) >= 13, 'ramdisk_header_invalid')
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=128 * 1024 * 1024)
    raw = decoder.decompress(ramdisk, max_length=128 * 1024 * 1024 + 1)
    require(decoder.eof and not decoder.unused_data and len(raw) <= 128 * 1024 * 1024, 'ramdisk_bounds_invalid')
    return raw


def cpio_records(raw):
    """Keep all original metadata, hard links and file bytes; never extract paths."""
    records = []
    pos = 0
    seen = set()
    while pos + 110 <= len(raw):
        header = raw[pos:pos + 110]
        require(header[:6] in (b'070701', b'070702'), 'cpio_magic_invalid')
        try:
            values = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        except ValueError as error:
            raise PreparationError('cpio_fields_invalid') from error
        size, name_bytes = values[6], values[11]
        require(0 < name_bytes <= 4096 and pos + 110 + name_bytes <= len(raw), 'cpio_name_bounds')
        name = raw[pos + 110:pos + 110 + name_bytes]
        require(name.endswith(b'\0') and b'\0' not in name[:-1], 'cpio_name_invalid')
        decoded = name[:-1].decode('utf-8')
        require(not decoded.startswith('/') and '..' not in decoded.split('/'), 'cpio_path_invalid')
        require(decoded not in seen, 'cpio_duplicate')
        seen.add(decoded)
        start = aligned(pos + 110 + name_bytes, 4)
        require(start + size <= len(raw), 'cpio_file_bounds')
        content = raw[start:start + size]
        if header[:6] == b'070702':
            require(sum(content) & 0xffffffff == values[12], 'cpio_crc_invalid')
        records.append((decoded, header, name, content))
        pos = aligned(start + size, 4)
        if decoded == 'TRAILER!!!':
            require(size == 0 and not any(raw[pos:]), 'cpio_trailer_invalid')
            return records
        require(len(records) <= 20000, 'cpio_entry_limit')
    raise PreparationError('cpio_trailer_missing')


def encode_records(records, replacements):
    result = bytearray()
    for name, old_header, encoded_name, original in records:
        content = replacements.get(name, original)
        header = bytearray(old_header)
        header[54:62] = f'{len(content):08x}'.encode()
        if header[:6] == b'070702':
            header[102:110] = f'{sum(content) & 0xffffffff:08x}'.encode()
        result.extend(header)
        result.extend(encoded_name)
        result.extend(b'\0' * (aligned(len(result), 4) - len(result)))
        result.extend(content)
        result.extend(b'\0' * (aligned(len(result), 4) - len(result)))
    result.extend(b'\0' * (aligned(len(result), 512) - len(result)))
    return bytes(result)


def patch_recovery(original):
    require(len(original) == IMAGE_BYTES and digest(original) == IMAGE_SHA256, 'recovery_source_mismatch')
    old = boot_header(original)
    require(old['second_bytes'] == 0 and old['boot_id_variant'] == 'lineage-empty-legacy-dt', 'recovery_layout_unexpected')
    old_ramdisk = original[old['ramdisk_offset']:old['ramdisk_offset'] + old['ramdisk_bytes']]
    raw = decode_ramdisk(old_ramdisk)
    records = cpio_records(raw)
    files = newc_files(raw)
    require(digest(files[RC_NAME]) == RC_SHA256 and digest(files[NUKER_NAME]) == NUKER_SHA256, 'recovery_startup_mismatch')
    marker = b'on property:sys.usb.ffs.ready=1\n'
    require(files[RC_NAME].count(marker) == 1, 'recovery_trigger_mismatch')
    rc = files[RC_NAME].split(marker)[0]
    # Retain the original attribution/license header in the local modified file.
    attribution = files[NUKER_NAME].split(b'# Step 0')[0]
    no_op = attribution + b'# Local recovery test: automatic system/vendor changes disabled.\nexit 0\n'
    replacements = {RC_NAME: rc, NUKER_NAME: no_op}
    new_raw = encode_records(records, replacements)
    restored = cpio_records(new_raw)
    require(len(restored) == len(records), 'cpio_record_count_changed')
    for before, after in zip(records, restored):
        name, header, encoded_name, content = before
        require(name == after[0] and encoded_name == after[2], 'cpio_names_changed')
        masked_before, masked_after = bytearray(header), bytearray(after[1])
        for a, b in ((54, 62), (102, 110)):
            masked_before[a:b] = masked_after[a:b]
        require(masked_before == masked_after, 'cpio_metadata_changed')
        require(after[3] == replacements.get(name, content), 'cpio_content_changed')
    prop = old_ramdisk[0]
    lc, lp, pb = prop % 9, (prop // 9) % 5, prop // 45
    dictionary = struct.unpack_from('<I', old_ramdisk, 1)[0]
    require(dictionary == 8 * 1024 * 1024 and (lc, lp, pb) == (3, 0, 2), 'lzma_properties_unexpected')
    ramdisk = lzma.compress(new_raw, format=lzma.FORMAT_ALONE, filters=[{
        'id': lzma.FILTER_LZMA1, 'dict_size': dictionary, 'lc': lc, 'lp': lp, 'pb': pb,
    }])
    require(decode_ramdisk(ramdisk) == new_raw, 'lzma_roundtrip_failed')
    dtbo = original[old['recovery_dtbo_offset']:old['recovery_dtbo_offset'] + old['recovery_dtbo_bytes']]
    require(not any(original[old['recovery_dtbo_offset'] + len(dtbo):]), 'unexpected_recovery_tail')
    rebuilt = bytearray(original[:old['ramdisk_offset']])
    rebuilt.extend(ramdisk)
    rebuilt.extend(b'\0' * (aligned(len(rebuilt), 2048) - len(rebuilt)))
    new_dtbo_offset = len(rebuilt)
    rebuilt.extend(dtbo)
    rebuilt.extend(b'\0' * (aligned(len(rebuilt), 2048) - len(rebuilt)))
    struct.pack_into('<I', rebuilt, 16, len(ramdisk))
    struct.pack_into('<Q', rebuilt, 1636, new_dtbo_offset)
    kernel = original[2048:2048 + old['kernel_bytes']]
    checksum = hashlib.sha1()
    for payload in (kernel, ramdisk, b'', b'', dtbo):
        checksum.update(payload)
        checksum.update(struct.pack('<I', len(payload)))
    rebuilt[576:608] = checksum.digest() + bytes(12)
    rebuilt = bytes(rebuilt)
    new = boot_header(rebuilt)
    for key in ('header_version', 'header_bytes', 'page_bytes', 'kernel_address', 'ramdisk_address', 'second_address', 'tags_address', 'os_version', 'security_patch', 'cmdline', 'kernel_bytes'):
        require(new[key] == old[key], 'boot_header_changed_' + key)
    require(rebuilt[2048:2048 + len(kernel)] == kernel, 'kernel_changed')
    require(dtbo_table(dtbo)['table_bytes'] == len(dtbo), 'dtbo_invalid')
    require(len(rebuilt) <= RECOVERY_BYTES, 'recovery_does_not_fit')
    return rebuilt, {
        'original_sha256': IMAGE_SHA256, 'prepared_sha256': digest(rebuilt),
        'bytes': len(rebuilt), 'partition_bytes': RECOVERY_BYTES,
        'partition_margin_bytes': RECOVERY_BYTES - len(rebuilt),
        'kernel_sha256': digest(kernel), 'embedded_dtbo_sha256': digest(dtbo),
        'kernel_unchanged': True, 'embedded_dtbo_unchanged': True,
        'ramdisk_entries': len(records), 'modified_files': sorted(replacements),
        'automatic_nuker_trigger_removed': True, 'nuker_script_replaced_by_no_op': True,
        'all_other_ramdisk_contents_and_metadata_preserved': True,
        'header': new,
    }


def make_vbmeta(root, directory):
    path = root / 'tools' / 'avbtool.py'
    module = load_avbtool(path)
    output = directory / 'vbmeta-test.img'
    subprocess.run([sys.executable, '-I', str(path), 'make_vbmeta_image', '--output', str(output),
                    '--algorithm', 'NONE', '--flags', '3', '--padding_size', '65536', '--rollback_index', '0'],
                   check=True, timeout=30, capture_output=True)
    data = output.read_bytes()
    header = module.AvbVBMetaHeader(data[:256])
    require(len(data) == 65536 and header.algorithm_type == 0 and header.flags == 3 and
            header.rollback_index == 0 and header.rollback_index_location == 0 and
            header.authentication_data_block_size == 0 and header.auxiliary_data_block_size == 0,
            'vbmeta_layout_invalid')
    return {'sha256': digest(data), 'bytes': len(data), 'algorithm': 'NONE', 'flags': 3,
            'rollback_index': 0, 'required_libavb': '1.0', 'cryptographic_signature': False,
            'purpose': 'Disable verification/hashtree enforcement for an unlocked-device hardware test'}


def prepare(root, stock_path=None, audit_image=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = root / ('prepared-recovery-' + uuid.uuid4().hex)
    directory.mkdir()
    report = {'schema': 1, 'preparer_version': 1, 'model': 'SM-G975F', 'pda': 'G975FXXSGHWC1',
              'expected_pit_sha256': PIT_SHA256, 'hardware_tested': False, 'install_ready': False,
              'handset_accessed': False, 'partition_writes': False, 'success': False,
              'backup_verified': False, 'error': None}
    if not audit_image:
        (root / 'recovery-local-state.json').unlink(missing_ok=True)
    try:
        if not audit_image:
            require(stock_path is not None, 'stock_firmware_required')
            print('Verifico il firmware completo gia scaricato. Puo richiedere alcuni minuti.', flush=True)
            report['stock_firmware'] = validate_stock(stock_path)
            report['backup_verified'] = True
            print('Scarico e verifico la recovery dal sito ufficiale TWRP...', flush=True)
            image = download_original(root)
        else:
            image = Path(audit_image)
        print('Preparo la recovery per il test senza modifiche automatiche a system/vendor...', flush=True)
        recovery, details = patch_recovery(image.read_bytes())
        (directory / 'recovery-test.img').write_bytes(recovery)
        report['recovery'] = details
        report['vbmeta'] = make_vbmeta(root, directory)
        report['success'] = True
        if not audit_image:
            # This private local state contains a PC path; never include it in
            # the diagnostic ZIP sent to the assistant.
            state = {'prepared_directory': str(directory), 'stock_firmware_path': str(Path(stock_path).resolve()),
                     'report': report}
            (root / 'recovery-local-state.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    except Exception as error:
        report['error'] = str(error) if isinstance(error, PreparationError) else 'preparation_failed'
        for name in ('recovery-test.img', 'vbmeta-test.img'):
            (directory / name).unlink(missing_ok=True)
        print('Preparazione non completata. Invia il rapporto per il controllo.', flush=True)
    (directory / 'recovery-preparation-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    zip_path = root / 'recovery-preparation-report.zip'
    index = 1
    while zip_path.exists():
        zip_path = root / f'recovery-preparation-report-{index}.zip'
        index += 1
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(directory / 'recovery-preparation-report.json', 'recovery-preparation-report.json')
    if report['success']:
        print('File per il test preparati sul PC. Il telefono non e stato modificato.', flush=True)
    print('Invia questo file: ' + str(zip_path), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--stock-firmware', type=Path)
    group.add_argument('--audit-image', type=Path, help='Offline CI audit only; never sets backup_verified')
    args = parser.parse_args()
    report = prepare(args.root, args.stock_firmware, args.audit_image)
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
