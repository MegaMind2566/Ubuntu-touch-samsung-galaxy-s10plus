import contextlib
import hashlib
import io
import json
import lzma
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_recovery


def record(name, content=b'', mode=0o100755, uid=0, magic=b'070701', checksum=None):
    encoded = name.encode() + b'\0'
    values = [7, mode, uid, 42, 1, 123456, len(content), 0, 0, 0, 0, len(encoded),
              (sum(content) & 0xffffffff) if checksum is None and magic == b'070702' else (checksum or 0)]
    header = magic + b''.join(f'{value:08x}'.encode() for value in values)
    return name, header, encoded, content


class RecoveryPreparationTests(unittest.TestCase):
    def test_rewrite_preserves_permissions_owners_links_and_other_contents(self):
        entries = [record('original', b'unchanged', mode=0o120777, uid=1000),
                   record('changed', b'old payload'), record('TRAILER!!!', mode=0)]
        encoded = prepare_recovery.encode_records(entries, {'changed': b'a much longer new payload'})
        decoded = prepare_recovery.cpio_records(encoded)
        self.assertEqual(decoded[0], entries[0])
        self.assertEqual(decoded[1][3], b'a much longer new payload')
        self.assertEqual(decoded[1][1][14:54], entries[1][1][14:54])

    def test_crc_newc_detects_corruption(self):
        entries = [record('file', b'payload', magic=b'070702'), record('TRAILER!!!', mode=0)]
        data = prepare_recovery.encode_records(entries, {})
        self.assertEqual(prepare_recovery.cpio_records(data)[0][3], b'payload')
        bad = data.replace(b'payload', b'payloae')
        with self.assertRaisesRegex(ValueError, 'cpio_crc_invalid'):
            prepare_recovery.cpio_records(bad)

    def test_truncation_and_missing_trailer_rejected(self):
        data = prepare_recovery.encode_records([record('file', b'content')], {})
        with self.assertRaises(ValueError):
            prepare_recovery.cpio_records(data[:116])
        with self.assertRaises(ValueError):
            prepare_recovery.cpio_records(data)

    def test_duplicate_and_traversal_rejected_without_extracting(self):
        for entries in ([record('../escape'), record('TRAILER!!!', mode=0)],
                        [record('same'), record('same'), record('TRAILER!!!', mode=0)]):
            with self.assertRaises(ValueError):
                prepare_recovery.cpio_records(prepare_recovery.encode_records(entries, {}))

    def test_lzma_rejects_trailing_or_truncated_stream(self):
        data = lzma.compress(b'test archive', format=lzma.FORMAT_ALONE)
        self.assertEqual(prepare_recovery.decode_ramdisk(data), b'test archive')
        for bad in (data[:-1], data + b'extra'):
            with self.assertRaises(ValueError):
                prepare_recovery.decode_ramdisk(bad)

    def test_wrong_recovery_rejected_before_parsing(self):
        with self.assertRaisesRegex(ValueError, 'recovery_source_mismatch'):
            prepare_recovery.patch_recovery(b'different device image')

    def test_stock_zip_requires_the_full_recovery_set_and_exact_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.zip'
            prefixes = ['BL_G975FXXSGHWC1_', 'AP_G975FXXSGHWC1_', 'CP_G975FXXSGHWB3_',
                        'CSC_OXM_G975FOXMGHWA3_', 'HOME_CSC_OXM_G975FOXMGHWA3_']
            with zipfile.ZipFile(path, 'w') as archive:
                for prefix in prefixes:
                    archive.writestr(prefix + 'fixture.tar.md5', b'fixture')
            size = path.stat().st_size
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(prepare_recovery, 'STOCK_BYTES', size), patch.object(prepare_recovery, 'STOCK_SHA256', digest):
                self.assertTrue(prepare_recovery.validate_stock(path)['full_recovery_set_retained'])
                with zipfile.ZipFile(path, 'a') as archive:
                    archive.writestr('changed', b'changed')
                with self.assertRaisesRegex(ValueError, 'stock_size_mismatch'):
                    prepare_recovery.validate_stock(path)

    def test_failure_retains_a_report_and_invalidates_previous_ready_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'recovery-local-state.json').write_text('old successful state')
            wrong = root / 'wrong-stock.zip'
            wrong.write_bytes(b'not the correct firmware')
            with patch.object(prepare_recovery, 'download_original', side_effect=AssertionError('must not download')), contextlib.redirect_stdout(io.StringIO()):
                result = prepare_recovery.prepare(root, wrong)
            self.assertFalse(result['success'])
            self.assertEqual(result['error'], 'stock_size_mismatch')
            self.assertFalse((root / 'recovery-local-state.json').exists())
            with zipfile.ZipFile(root / 'recovery-preparation-report.zip') as archive:
                report = json.loads(archive.read('recovery-preparation-report.json'))
                self.assertFalse(report['handset_accessed'])
                self.assertFalse(report['backup_verified'])
            self.assertFalse(list(root.glob('prepared-recovery-*/*.img')))


if __name__ == '__main__':
    unittest.main()
