import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_recovery_test as verifier


class RecoveryTestGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = {'prepared_directory': str(self.root / ('prepared-recovery-' + 'a' * 32)),
                      'stock_firmware_path': str(self.root / 'firmware.zip'),
                      'report': {'schema': 1, 'preparer_version': 1, 'model': 'SM-G975F',
                                 'pda': 'G975FXXSGHWC1', 'success': True, 'backup_verified': True,
                                 'expected_pit_sha256': verifier.PIT_SHA256,
                                 'recovery': {'prepared_sha256': verifier.RECOVERY_SHA256},
                                 'vbmeta': {'sha256': verifier.VBMETA_SHA256},
                                 'stock_firmware': {'sha256': verifier.STOCK_SHA256}}}

    def write_state(self):
        (self.root / 'recovery-local-state.json').write_text(json.dumps(self.state))

    def test_missing_state(self):
        with self.assertRaisesRegex(verifier.VerificationError, 'state_missing'):
            verifier.verify_files(self.root)

    def test_unverified_or_different_preparation(self):
        for field, value in (('backup_verified', False), ('success', False), ('model', 'SM-G975U'),
                             ('pda', 'G975FXXU9DTJA'), ('expected_pit_sha256', '0' * 64)):
            with self.subTest(field=field):
                original = self.state['report'][field]
                self.state['report'][field] = value
                self.write_state()
                with patch.object(verifier, 'verify_images') as images:
                    with self.assertRaisesRegex(verifier.VerificationError, 'preparation_state_not_verified'):
                        verifier.verify_files(self.root)
                    images.assert_not_called()
                self.state['report'][field] = original

    def test_editable_manifest_cannot_replace_pinned_image_hash(self):
        self.state['report']['recovery']['prepared_sha256'] = '0' * 64
        self.write_state()
        with self.assertRaisesRegex(verifier.VerificationError, 'preparation_state_hash_mismatch'):
            verifier.verify_files(self.root)

    def test_outside_directory(self):
        self.state['prepared_directory'] = str(self.root.parent / 'prepared-recovery-outside')
        self.write_state()
        with self.assertRaisesRegex(verifier.VerificationError, 'prepared_directory_outside_package'):
            verifier.verify_files(self.root)

    def test_file_size_and_content_pins(self):
        (self.root / 'recovery-test.img').write_bytes(b'ANDROID!')
        with self.assertRaisesRegex(verifier.VerificationError, 'prepared_image_size_mismatch'):
            verifier.verify_images(self.root)
        # Same-size changed bytes must also fail; a reported hash is insufficient.
        with (self.root / 'recovery-test.img').open('wb') as output:
            output.truncate(verifier.RECOVERY_BYTES)
        with self.assertRaisesRegex(verifier.VerificationError, 'prepared_image_sha256_mismatch'):
            verifier.verify_images(self.root)

    def test_missing_and_short_stock_archive(self):
        path = self.root / 'firmware.zip'
        for exists in (False, True):
            if exists:
                path.write_bytes(b'not Samsung firmware')
            with self.assertRaisesRegex(verifier.VerificationError, 'stock_firmware_missing_or_size_mismatch'):
                verifier.verify_stock(path)

    def test_backup_is_checked_even_if_images_pass(self):
        self.write_state()
        with patch.object(verifier, 'verify_images', return_value={'recovery_path': 'r', 'vbmeta_path': 'v'}):
            with self.assertRaisesRegex(verifier.VerificationError, 'stock_firmware_missing_or_size_mismatch'):
                verifier.verify_files(self.root)


if __name__ == '__main__':
    unittest.main()
