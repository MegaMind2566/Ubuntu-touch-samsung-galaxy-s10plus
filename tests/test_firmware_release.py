"""Offline release state/transport fixtures; no GitHub calls or publication."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('firmware_release', ROOT / 'scripts/publish-firmware-release.py')
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)
TARGET = 'a' * 40


def spec_for(name, data):
    return {'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class FakeAPI:
    def __init__(self, config, notes, published=False):
        self.repository = config['repository']
        self.release = {'id': 17, 'tag_name': config['tag'], 'name': config['name'],
                        'body': notes.decode(), 'draft': not published,
                        'prerelease': True, 'target_commitish': TARGET}
        self.exists = False
        self.assets = {}
        self.content = {}
        self.mutations = []
        self.downloaded = []
        self.tag = TARGET if published else None

    def json(self, method, suffix, payload=None, missing=False):
        if method == 'GET' and suffix.startswith('/releases?'):
            return [copy.deepcopy(self.release)] if self.exists else []
        if method == 'GET' and suffix.startswith('/git/ref/tags/'):
            return {'object': {'type': 'commit', 'sha': self.tag}} if self.tag else None
        if method == 'GET' and '/assets?' in suffix:
            return copy.deepcopy(list(self.assets.values()))
        if method == 'GET' and suffix == '/releases/17':
            return copy.deepcopy(self.release)
        if method == 'POST' and suffix == '/releases':
            self.mutations.append((method, suffix, payload))
            self.exists = True
            self.release.update(payload)
            return copy.deepcopy(self.release)
        if method == 'PATCH' and suffix == '/releases/17':
            self.mutations.append((method, suffix, payload))
            self.release.update(payload)
            self.tag = self.release['target_commitish']
            return copy.deepcopy(self.release)
        raise AssertionError((method, suffix, payload))

    def add(self, name, data, metadata=None):
        asset = {'id': len(self.assets) + 30, 'name': name, 'size': len(data),
                 'state': 'uploaded', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
        asset.update(metadata or {})
        self.assets[name] = asset
        self.content[name] = data

    def upload(self, release_id, path, expected):
        assert release_id == 17 and expected['name'] not in self.assets
        assert r.identity(path) == expected
        self.mutations.append(('UPLOAD', expected['name']))
        self.add(expected['name'], path.read_bytes())
        return self.assets[expected['name']]

    def verify_download(self, asset, expected):
        self.downloaded.append(asset['name'])
        r.require(spec_for(asset['name'], self.content[asset['name']]) == expected,
                  'release_asset_download_hash_mismatch')


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.status = 200


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = self.root / 'out'
        self.system = b'compressed-SYSTEM-fixture\x00'
        self.zip = b'pinned-BOOT-tools-ZIP-fixture'
        self.notes = b'# Alpha firmware\nUser-reported boot, touch and basic Wi-Fi.\n'
        self.config = {'schema': 1, 'repository': 'owner/repo', 'tag': r.TAG,
                       'name': 'First development alpha',
                       'notes_path': 'docs/releases/v0.1.0-alpha.1.md',
                       'system': spec_for('SYSTEM.img.zst', self.system),
                       'boot_and_tools': spec_for(r.ZIP_NAME, self.zip)}
        self.raw = (json.dumps(self.config, indent=2) + '\n').encode()
        self.expected = r.prepare_metadata(self.work, self.raw, self.notes, self.config)
        self.api = FakeAPI(self.config, self.notes)

    def tearDown(self):
        self.temp.cleanup()

    def system_factory(self, work, expected):
        path = work / expected['name']
        path.write_bytes(self.system)
        return path

    def run_publish(self, **kwargs):
        return r.publish(self.api, self.config, self.notes, self.expected, self.work,
                         TARGET, system_factory=self.system_factory, **kwargs)

    def populate(self):
        self.api.exists = True
        for name in self.expected:
            data = self.system if name == 'SYSTEM.img.zst' else (
                self.zip if name == r.ZIP_NAME else (self.work / name).read_bytes())
            self.api.add(name, data)

    def test_metadata_is_exact_and_checksums_have_no_self_reference(self):
        self.assertEqual((self.work / 'release-manifest.json').read_bytes(), self.raw)
        self.assertEqual((self.work / 'release-notes.md').read_bytes(), self.notes)
        sums = (self.work / 'SHA256SUMS').read_text()
        self.assertEqual(len(sums.splitlines()), 4)
        self.assertNotIn('  SHA256SUMS\n', sums)
        self.assertIn(self.config['boot_and_tools']['sha256'] + '  ' + r.ZIP_NAME, sums)

    def test_success_waits_for_manual_zip_and_verifies_all_before_only_publish_patch(self):
        ticks = [0]
        def sleep(seconds):
            ticks[0] += seconds
            self.api.add(r.ZIP_NAME, self.zip)
        result = self.run_publish(wait_seconds=2, poll_seconds=1,
                                  clock=lambda: ticks[0], sleep=sleep)
        self.assertTrue(result['published'])
        self.assertEqual(set(self.api.downloaded), set(self.expected))
        patches = [v for v in self.api.mutations if v[0] == 'PATCH']
        self.assertEqual(patches, [('PATCH', '/releases/17', {'draft': False, 'prerelease': True})])
        self.assertFalse(any(v[0] in ('DELETE', 'PUT') for v in self.api.mutations))

    def test_missing_zip_leaves_draft_and_rerun_finishes_without_reupload(self):
        with self.assertRaisesRegex(r.ReleaseError, 'manual_zip_not_received_draft_retained'):
            self.run_publish(wait_seconds=0)
        self.assertTrue(self.api.release['draft'])
        self.assertEqual(len(self.api.assets), 4)
        uploads = sum(v[0] == 'UPLOAD' for v in self.api.mutations)
        self.api.add(r.ZIP_NAME, self.zip)
        self.assertTrue(self.run_publish(wait_seconds=0)['published'])
        self.assertEqual(sum(v[0] == 'UPLOAD' for v in self.api.mutations), uploads)

    def test_asset_conflicts_wrong_size_digest_extra_and_duplicate_fail_without_mutation(self):
        for change in ['size', 'digest', 'extra', 'duplicate']:
            with self.subTest(change=change):
                self.api = FakeAPI(self.config, self.notes)
                self.populate()
                if change == 'extra':
                    self.api.add('unreviewed.img', b'bad')
                elif change == 'duplicate':
                    self.api.assets['alias'] = dict(self.api.assets[r.ZIP_NAME])
                else:
                    self.api.assets[r.ZIP_NAME][change] = 1 if change == 'size' else 'sha256:' + '0' * 64
                with self.assertRaises(r.ReleaseError):
                    self.run_publish(wait_seconds=0)
                self.assertEqual(self.api.mutations, [])
                self.assertTrue(self.api.release['draft'])

    def test_matching_metadata_does_not_hide_corrupt_download(self):
        self.populate()
        self.api.content[r.ZIP_NAME] = b'X' + self.zip[1:]
        with self.assertRaisesRegex(r.ReleaseError, 'download_hash_mismatch'):
            self.run_publish(wait_seconds=0)
        self.assertFalse(any(v[0] == 'PATCH' for v in self.api.mutations))

    def test_published_release_is_read_only_and_requires_complete_expected_manifest(self):
        self.populate()
        self.api.release['draft'] = False
        self.api.tag = TARGET
        self.assertTrue(self.run_publish(wait_seconds=0)['already_published'])
        self.assertEqual(self.api.mutations, [])
        self.api.assets.pop('release-manifest.json')
        with self.assertRaisesRegex(r.ReleaseError, 'asset_set_incomplete'):
            self.run_publish(wait_seconds=0)
        self.assertEqual(self.api.mutations, [])

    def test_target_body_or_prerelease_conflict_never_repoints_or_changes_release(self):
        for change in ['target_commitish', 'body', 'prerelease']:
            with self.subTest(change=change):
                self.api = FakeAPI(self.config, self.notes)
                self.api.exists = True
                self.api.release[change] = {'target_commitish': 'b' * 40,
                                           'body': 'other notes', 'prerelease': False}[change]
                with self.assertRaises(r.ReleaseError):
                    self.run_publish(wait_seconds=0)
                self.assertEqual(self.api.mutations, [])
        self.api = FakeAPI(self.config, self.notes)
        self.api.tag = 'b' * 40
        with self.assertRaisesRegex(r.ReleaseError, 'tag_exists_without_matching_release'):
            self.run_publish(wait_seconds=0)
        self.assertEqual(self.api.mutations, [])

    def test_asset_identity_changed_after_verification_blocks_publication(self):
        self.populate()
        original = self.api.verify_download
        def change(asset, expected):
            original(asset, expected)
            if asset['name'] == sorted(self.expected)[-1]:
                self.api.assets[asset['name']]['id'] += 100
        self.api.verify_download = change
        with self.assertRaisesRegex(r.ReleaseError, 'assets_changed_during_verification'):
            self.run_publish(wait_seconds=0)
        self.assertFalse(any(v[0] == 'PATCH' for v in self.api.mutations))

    def test_system_reassembles_three_verified_parts_and_rejects_corruption(self):
        data = self.system
        helper = types.SimpleNamespace(COMPRESSED_BYTES=len(data),
                                       COMPRESSED_SHA256=hashlib.sha256(data).hexdigest())
        def materialize(output):
            output.mkdir()
            parts = []
            for i, block in enumerate([data[:7], data[7:17], data[17:]], 1):
                name = f'rootfs.img.zst.part{i:02d}'
                (output / name).write_bytes(block)
                parts.append(spec_for(name, block))
            (output / 'source-relay-manifest.json').write_text(json.dumps({
                'success': True, 'compressed_bytes': len(data),
                'compressed_sha256': helper.COMPRESSED_SHA256, 'parts': parts}))
        helper.materialize = materialize
        target = r.materialize_system(self.work, self.config['system'], helper)
        self.assertEqual(target.read_bytes(), data)
        other = self.root / 'corrupt';other.mkdir()
        def corrupt(output):
            materialize(output)
            (output / 'rootfs.img.zst.part02').write_bytes(b'X' * 10)
        helper.materialize = corrupt
        with self.assertRaisesRegex(r.ReleaseError, 'system_part_hash_mismatch'):
            r.materialize_system(other, self.config['system'], helper)
        self.assertFalse((other / 'SYSTEM.img.zst').exists())

    def test_api_download_redirect_never_forwards_token_and_streams_hash(self):
        calls = []
        def open_request(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 302, 'redirect', {
                    'Location': 'https://release-assets.githubusercontent.com/file?secret=fixture'}, None)
            return Response(self.zip)
        api = r.GitHub('owner/repo', 'PRIVATE_FIXTURE_TOKEN',
                       opener=types.SimpleNamespace(open=open_request))
        api.verify_download({'id': 42}, self.config['boot_and_tools'])
        self.assertEqual(calls[0].get_header('Authorization'), 'Bearer PRIVATE_FIXTURE_TOKEN')
        self.assertIsNone(calls[1].get_header('Authorization'))
        self.assertEqual(calls[1].full_url.split('?')[0],
                         'https://release-assets.githubusercontent.com/file')

    def test_bad_redirect_origin_no_token_leak_and_same_size_corrupt_stream_rejected(self):
        calls = []
        def redirect(request, timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url, 302, 'redirect', {
                'Location': 'https://evil.example/file?secret=fixture'}, None)
        api = r.GitHub('owner/repo', 'PRIVATE_FIXTURE_TOKEN',
                       opener=types.SimpleNamespace(open=redirect))
        with self.assertRaisesRegex(r.ReleaseError, 'download_storage_invalid'):
            api.verify_download({'id': 42}, self.config['boot_and_tools'])
        self.assertEqual(len(calls), 1)
        api.opener = types.SimpleNamespace(open=lambda request, timeout: Response(b'X' + self.zip[1:]))
        with self.assertRaisesRegex(r.ReleaseError, 'download_hash_mismatch'):
            api.verify_download({'id': 42}, self.config['boot_and_tools'])
        for url in ['https://api.github.com.evil.example/a', 'http://api.github.com/a',
                    'https://user:secret@api.github.com/a', 'https://uploads.github.com/a']:
            with self.subTest(url=url), self.assertRaises(r.ReleaseError):
                api.headers(url)
        with self.assertRaisesRegex(r.ReleaseError, 'authenticated_host_not_allowed'):
            api.headers('https://evil.example/a', host='evil.example')

    def test_upload_uses_stream_length_and_auth_only_on_uploads_host(self):
        path = self.work / 'SYSTEM.img.zst';path.write_bytes(self.system)
        calls = []
        def upload(request, timeout):
            calls.append(request)
            self.assertEqual(request.get_header('Authorization'), 'Bearer fixture-token')
            self.assertEqual(request.get_header('Content-length'), str(len(self.system)))
            self.assertEqual(request.data.read(), self.system)
            asset = {'id': 45, 'name': path.name, 'size': len(self.system),
                     'state': 'uploaded', 'digest': 'sha256:' + hashlib.sha256(self.system).hexdigest()}
            return Response(json.dumps(asset).encode())
        api = r.GitHub('owner/repo', 'fixture-token', opener=types.SimpleNamespace(open=upload))
        api.upload(17, path, self.config['system'])
        self.assertTrue(calls[0].full_url.startswith('https://uploads.github.com/repos/owner/repo/releases/17/assets?'))

    def test_config_path_and_fixed_asset_names_are_guarded(self):
        notes = self.root / self.config['notes_path'];notes.parent.mkdir(parents=True)
        notes.write_bytes(self.notes)
        path = self.root / 'release.json';path.write_bytes(self.raw)
        self.assertEqual(r.load_config(path, 'owner/repo', self.root)[1], self.raw)
        for change in [{'repository': 'other/repo'}, {'notes_path': '../secret'},
                       {'boot_and_tools': spec_for('other.zip', self.zip)}]:
            path.write_text(json.dumps(dict(self.config, **change)))
            with self.assertRaises(r.ReleaseError):
                r.load_config(path, 'owner/repo', self.root)

    def test_workflow_has_scoped_write_token_pinned_checkout_and_bounded_wait(self):
        workflow = (ROOT / '.github/workflows/firmware-release.yml').read_text()
        self.assertIn('contents: write', workflow)
        self.assertIn('actions: read', workflow)
        self.assertIn('actions/checkout@11d5960a326750d5838078e36cf38b85af677262', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('--wait-seconds 1500', workflow)
        self.assertIn('cancel-in-progress: false', workflow)
        self.assertNotIn('pull_request', workflow)


if __name__ == '__main__':
    unittest.main(verbosity=2)
