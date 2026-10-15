"""Small offline image/package fixtures; no handset or Windows execution.

Prefer Python 3.14's compression.zstd. On earlier Python versions, install
zstandard to run the two real-frame tests. Other checks have no third-party
dependency and remain available if both decompression modules are absent.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

try:
    from compression import zstd
    ZSTD_BACKEND = 'stdlib compression.zstd'
    ZSTD_ERROR = zstd.ZstdError
    compress = zstd.compress
    def frame_reader(path):
        return zstd.open(path, 'rb')
except ImportError:
    try:
        import zstandard
        ZSTD_BACKEND = 'zstandard'
        ZSTD_ERROR = zstandard.ZstdError
        def compress(data):
            return zstandard.ZstdCompressor().compress(data)
        def frame_reader(path):
            return zstandard.ZstdDecompressor().stream_reader(path.open('rb'))
    except ImportError:
        ZSTD_BACKEND = None
        ZSTD_ERROR = Exception
        def compress(data):
            return b'opaque compressed fixture'
        def frame_reader(path):
            raise AssertionError('unexpected decoder call without a Zstandard backend')

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = module('firmware_preparation_tests', 'prepare-firmware-images.py')
p = module('firmware_package_tests', 'package-firmware-release.py')


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class Images(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.folder = Path(self.workspace.name)
        self.root = self.folder / 'extracted release'
        self.images = self.root / 'images'
        self.images.mkdir(parents=True)
        self.boot = b'fixture BOOT'
        self.raw = b'ext4 fixture\n' * 8192
        self.compressed = compress(self.raw)
        (self.images / 'boot.img').write_bytes(self.boot)
        self.source = self.folder / 'SYSTEM.img.zst'
        self.source.write_bytes(self.compressed)
        self.patches = [patch.object(m, 'BOOT', pin(self.boot)), patch.object(m, 'SYSTEM', pin(self.raw)),
                        patch.object(m, 'COMPRESSED', pin(self.compressed)), patch.object(m, 'BLOCK', 1024)]
        for value in self.patches:
            value.start()

    def tearDown(self):
        for value in self.patches:
            value.stop()
        self.workspace.cleanup()

    def prepare(self, reader=None):
        return m.prepare(self.root, reader=reader or frame_reader,
                         runtime_check=lambda root: None, progress=lambda text: None)

    def assert_clean(self):
        self.assertFalse((self.images / 'system.img').exists())
        self.assertEqual(list(self.images.glob('*.partial')), [])

    @unittest.skipIf(ZSTD_BACKEND is None, 'requires compression.zstd (Python 3.14+) or optional zstandard')
    def test_verified_stream_is_published_and_source_is_preserved(self):
        result = self.prepare()
        self.assertEqual(result['result'], 'system_prepared_and_verified')
        self.assertEqual((self.images / 'system.img').read_bytes(), self.raw)
        self.assertEqual(self.source.read_bytes(), self.compressed)

    def test_existing_good_raw_does_not_need_archive_or_decoder(self):
        (self.images / 'system.img').write_bytes(self.raw)
        self.source.unlink()
        result = self.prepare(reader=lambda path: self.fail('decoded existing verified image'))
        self.assertEqual(result['result'], 'existing_system_verified')

    def test_existing_conflict_is_never_replaced(self):
        target = self.images / 'system.img'
        target.write_bytes(b'keep conflicting file')
        with self.assertRaisesRegex(ValueError, 'existing_system_conflict'):
            self.prepare()
        self.assertEqual(target.read_bytes(), b'keep conflicting file')

    def test_source_hash_size_and_boot_mismatch_stop_before_decompression(self):
        for bad in ('source-hash', 'source-size', 'boot'):
            with self.subTest(bad=bad):
                self.source.write_bytes(self.compressed)
                (self.images / 'boot.img').write_bytes(self.boot)
                if bad == 'source-hash':
                    self.source.write_bytes(bytes([self.compressed[0] ^ 1]) + self.compressed[1:])
                elif bad == 'source-size':
                    self.source.write_bytes(self.compressed[:-1])
                else:
                    (self.images / 'boot.img').write_bytes(b'wrong BOOT')
                with self.assertRaises(ValueError):
                    self.prepare(reader=lambda path: self.fail('decoder reached before pins'))
                self.assert_clean()

    def test_truncated_oversized_and_wrong_hash_raw_clean_partial_output(self):
        for value in (self.raw[:-1], self.raw + b'overflow', b'X' + self.raw[1:]):
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                self.prepare(reader=lambda path: io.BytesIO(value))
            self.assert_clean()

    @unittest.skipIf(ZSTD_BACKEND is None, 'requires compression.zstd (Python 3.14+) or optional zstandard')
    def test_corrupt_zstd_frame_cleans_output(self):
        damaged = b'not a zstd frame'
        self.source.write_bytes(damaged)
        with patch.object(m, 'COMPRESSED', pin(damaged)), self.assertRaises(ZSTD_ERROR):
            self.prepare()
        self.assert_clean()

    def test_ambiguous_archive_or_symlink_is_rejected(self):
        local = self.root / 'SYSTEM.img.zst'
        local.write_bytes(self.compressed)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.prepare()
        local.unlink()
        self.source.unlink()
        self.source.symlink_to(self.images / 'boot.img')
        with self.assertRaisesRegex(ValueError, 'size_or_type'):
            self.prepare()
        self.assert_clean()

    def test_concurrent_conflict_is_not_overwritten_at_publication(self):
        def reader(path):
            (self.images / 'system.img').write_bytes(b'concurrent file')
            return io.BytesIO(self.raw)
        with self.assertRaisesRegex(ValueError, 'existing_system_conflict'):
            self.prepare(reader)
        self.assertEqual((self.images / 'system.img').read_bytes(), b'concurrent file')
        self.assertEqual(list(self.images.glob('*.partial')), [])

    def test_runtime_failure_never_reads_or_writes_images(self):
        with self.assertRaisesRegex(ValueError, 'runtime'):
            m.prepare(self.root, runtime_check=lambda root: (_ for _ in ()).throw(ValueError('runtime')),
                      reader=lambda path: self.fail('decoder reached'))
        self.assert_clean()


class Package(unittest.TestCase):
    def test_small_package_is_deterministic_and_manifest_covers_every_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            boot = root / 'boot.img'
            boot.write_bytes(b'BOOT fixture')
            python = root / 'python.zip'
            adb = root / 'adb.zip'
            with zipfile.ZipFile(python, 'w') as archive:
                for name in ('python.exe', 'python314.zip', '_zstd.pyd', 'LICENSE.txt'):
                    archive.writestr(name, b'official runtime fixture')
            with zipfile.ZipFile(adb, 'w') as archive:
                for name in ('adb.exe', 'NOTICE.txt'):
                    archive.writestr('platform-tools/' + name, b'official tools fixture')
            runtimes = {name: (path.stat().st_size, p.sha256(path)) for name, path in (('python', python), ('adb', adb))}
            with patch.object(p, 'PINS', {'boot.img': (boot.stat().st_size, p.sha256(boot))}), patch.object(p, 'RUNTIMES', runtimes):
                first, second = root / 'a.zip', root / 'b.zip'
                p.package(first, boot, python, adb)
                p.package(second, boot, python, adb)
                self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                lines = archive.read('SHA256SUMS').decode().splitlines()
                names = []
                for line in lines:
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                    names.append(name)
                self.assertEqual(set(names), set(archive.namelist()) - {'SHA256SUMS'})
                self.assertEqual(archive.read('scripts/manage-graphics-permissions.py'), (ROOT / 'scripts/manage-graphics-permissions.py').read_bytes())
                launcher = archive.read('PREPARA-IMMAGINI-FIRMWARE.cmd')
                self.assertNotIn(b'\n', launcher.replace(b'\r\n', b''))
                manifest = json.loads(archive.read('config/firmware-release.json'))
                self.assertFalse(manifest['general_clean_install_validated'])

    def test_wrong_archive_and_partial_recovery_pair_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.zip'
            path.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
                p.validate(path, p.RUNTIMES['python'])
            with self.assertRaisesRegex(ValueError, 'pair_required'):
                p.package(path, path, path, path, recovery=path)

    def test_runtime_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('../escape', b'no')
            with self.assertRaisesRegex(ValueError, 'unsafe_runtime_member'):
                p.safe_archive_files(path, 'tools/python/')


if __name__ == '__main__':
    unittest.main()
