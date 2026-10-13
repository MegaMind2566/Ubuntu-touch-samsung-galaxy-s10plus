"""Real immutable images on embedded Windows Python; no USB access."""
import argparse
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    from compression import zstd
    import prepare_ubuntu_install as prep
except ImportError:
    zstd=None;prep=None
from verify_recovery_test import VerificationError

ROOT=None;SOURCE=None


class UbuntuPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ROOT is None or prep is None:raise unittest.SkipTest('Run with embedded Windows Python and the immutable source artifact')
        cls.directory=ROOT/('prepared-ubuntu-'+'a'*32);cls.directory.mkdir()
        # This is the original 1.17 GB artifact and actual 5 GiB image,
        # not a substitute image or an overridden digest.
        prep.expand_artifact(SOURCE,cls.directory)

    def test_embedded_zstd_stream_and_limits(self):
        import io
        payload=zstd.compress(b'actual embedded runtime')
        with zstd.ZstdFile(io.BytesIO(payload),'rb',options={zstd.DecompressionParameter.window_log_max:26}) as source:
            self.assertEqual(source.read(),b'actual embedded runtime')

    def test_wrong_source_rejected(self):
        path=ROOT/'invalid-source.zip';path.write_bytes(b'not an artifact')
        with self.assertRaisesRegex(prep.InstallPreparationError,'source_artifact_size_mismatch'):
            prep.expand_artifact(path,self.directory)

    def test_tampered_boot_rejected(self):
        path=self.directory/'boot.img'
        with path.open('r+b') as output:original=output.read(1);output.seek(0);output.write(b'X')
        try:
            with self.assertRaisesRegex(prep.InstallPreparationError,'prepared_image_sha256_mismatch'):
                prep.validate_images(self.directory)
        finally:
            with path.open('r+b') as output:output.write(original)

    def test_missing_stock_never_marks_ready(self):
        separate=ROOT/'failed-preparation';separate.mkdir()
        (separate/'ubuntu-local-state.json').write_text('{"success":true}')
        report=prep.prepare(separate,SOURCE,ROOT/'missing-stock.zip')
        self.assertFalse(report['success']);self.assertFalse(report['partition_writes'])
        self.assertEqual(report['error'],'stock_firmware_missing_or_size_mismatch')
        self.assertFalse((separate/'ubuntu-local-state.json').exists())
        self.assertFalse(list(separate.rglob('*.img')))
        with zipfile.ZipFile(separate/'ubuntu-preparation-report.zip') as archive:
            self.assertNotIn(str(ROOT),archive.read(archive.namelist()[0]).decode())

    def test_ready_state_requires_full_retained_stock(self):
        state={'schema':1,'model':'SM-G975F','pda':'G975FXXSGHWC1','success':True,'backup_verified':True,
               'prepared_directory':str(self.directory),'stock_firmware_path':str(ROOT/'missing-stock.zip')}
        (ROOT/'ubuntu-local-state.json').write_text(json.dumps(state))
        with self.assertRaisesRegex(VerificationError,'stock_firmware_missing_or_size_mismatch'):
            prep.verified_state(ROOT)

    def test_ready_state_cannot_reference_another_directory(self):
        (ROOT/'ubuntu-local-state.json').write_text(json.dumps({'prepared_directory':str(ROOT.parent/('prepared-ubuntu-'+'b'*32))}))
        with self.assertRaisesRegex(prep.InstallPreparationError,'prepared_directory_invalid'):
            prep.verified_state(ROOT)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args();ROOT=args.root.resolve();SOURCE=args.source.resolve()
    ROOT.mkdir(parents=True,exist_ok=True)
    unittest.main(argv=[sys.argv[0]],verbosity=2)
