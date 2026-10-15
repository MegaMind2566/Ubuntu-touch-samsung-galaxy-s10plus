#!/usr/bin/env python3
"""Recover the pinned SYSTEM artifact into bounded, independently verifiable parts.

The workflow token is used only for GitHub's artifact API. SYSTEM is not mounted,
inflated, executed, rebuilt, or published by this transport helper.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
import warnings
import zipfile

REPOSITORY = 'MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus'
ARTIFACT_ID = 11775595258
RUN_ID = 38311673964
SOURCE_COMMIT = 'c9e44ce3d38e86b51584a5e6ce05d0f8bb7f3e08'
ZIP_BYTES = 1167934045
ZIP_SHA256 = '8440d83ab7ddffc8d76d1f0894be89cf24b91396b447041a1ffc7e5177695f0d'
COMPRESSED_MEMBER = 'system-candidate/rootfs.img.zst'
COMPRESSED_BYTES = 1114706918
COMPRESSED_SHA256 = '6729e58ca7924a7682a332c4a58a1e1ad1dc3b31437707fb49366b518da99928'
RAW_BYTES = 5368709120
RAW_SHA256 = 'd23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3'
PART_BYTES = 400 * 1024 * 1024
BUFFER_BYTES = 4 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require(condition, code):
    if not condition:
        raise ValueError(code)


def copy_verified(source, destination, expected_bytes, expected_sha256):
    count = 0
    digest = hashlib.sha256()
    created = False
    try:
        with destination.open('xb') as target:
            created = True
            while block := source.read(BUFFER_BYTES):
                count += len(block)
                require(count <= expected_bytes, 'payload_oversized')
                digest.update(block)
                target.write(block)
        require(count == expected_bytes and digest.hexdigest() == expected_sha256,
                'payload_identity_mismatch')
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return {'bytes': count, 'sha256': digest.hexdigest()}


def validate_metadata(meta):
    require(meta['id'] == ARTIFACT_ID and meta['size_in_bytes'] == ZIP_BYTES and
            meta['digest'] == 'sha256:' + ZIP_SHA256 and not meta['expired'],
            'artifact_metadata_mismatch')
    require(meta['workflow_run']['id'] == RUN_ID and
            meta['workflow_run']['head_sha'] == SOURCE_COMMIT,
            'artifact_source_mismatch')


def validate_storage_location(location):
    parsed = urllib.parse.urlparse(location)
    host = parsed.hostname or ''
    require(parsed.scheme == 'https' and not parsed.username and not parsed.password and
            (host.endswith('.blob.core.windows.net') or
             host.endswith('.githubusercontent.com')), 'artifact_storage_host_mismatch')


def download_artifact(work):
    token = os.environ.get('GITHUB_TOKEN', '')
    require(bool(token), 'github_token_missing')
    endpoint = (f'https://api.github.com/repos/{REPOSITORY}'
                f'/actions/artifacts/{ARTIFACT_ID}')
    headers = {'Authorization': 'Bearer ' + token,
               'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'beyond2lte-immutable-system-transport'}
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(urllib.request.Request(endpoint, headers=headers), timeout=60) as response:
        data = response.read(1024 * 1024 + 1)
    require(len(data) <= 1024 * 1024, 'artifact_metadata_oversized')
    meta = json.loads(data)
    validate_metadata(meta)
    try:
        response = opener.open(urllib.request.Request(endpoint + '/zip', headers=headers),
                               timeout=60)
    except urllib.error.HTTPError as error:
        require(error.code in (301, 302, 303, 307, 308), 'artifact_redirect_status')
        location = error.headers['Location']
        error.close()
    else:
        response.close()
        raise ValueError('artifact_redirect_missing')
    validate_storage_location(location)
    # The signed storage URL stays in memory. It receives no Authorization header.
    request = urllib.request.Request(location, headers={
        'User-Agent': 'beyond2lte-immutable-system-transport'})
    archive = work / 'source-artifact.zip'
    with urllib.request.urlopen(request, timeout=120) as response:
        copy_verified(response, archive, ZIP_BYTES, ZIP_SHA256)
    return archive, meta


def extract_member(archive, destination, member, expected_bytes, expected_sha256):
    with zipfile.ZipFile(archive) as source:
        require(source.namelist().count(member) == 1, 'member_count_mismatch')
        index = source.getinfo(member)
        require(index.file_size == expected_bytes, 'member_size_mismatch')
        with source.open(index) as stream:
            return copy_verified(stream, destination, expected_bytes, expected_sha256)


def split_verified(source, destination, part_bytes=PART_BYTES):
    parts = []
    total = 0
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        while block := stream.read(part_bytes):
            target = destination / f'rootfs.img.zst.part{len(parts) + 1:02d}'
            with target.open('xb') as output:
                output.write(block)
            digest.update(block)
            total += len(block)
            parts.append({'name': target.name, 'bytes': len(block),
                          'sha256': hashlib.sha256(block).hexdigest()})
    return {'bytes': total, 'sha256': digest.hexdigest(), 'parts': parts}


def materialize(output):
    output.mkdir(parents=True, exist_ok=False)
    work = output / '_work'
    work.mkdir()
    archive, metadata = download_artifact(work)
    compressed = work / 'rootfs.img.zst'
    extract_member(archive, compressed, COMPRESSED_MEMBER, COMPRESSED_BYTES, COMPRESSED_SHA256)
    parts = split_verified(compressed, output)
    require(parts['bytes'] == COMPRESSED_BYTES and parts['sha256'] == COMPRESSED_SHA256,
            'split_identity_mismatch')
    require(len(parts['parts']) == 3 and all(p['bytes'] <= PART_BYTES for p in parts['parts']),
            'split_geometry_mismatch')
    ancillary = []
    with zipfile.ZipFile(archive) as source:
        for name in ('SHA256SUMS', 'system-report.json', 'assembly-manifest.json'):
            member = 'system-candidate/' + name
            require(source.namelist().count(member) == 1 and
                    source.getinfo(member).file_size <= 1024 * 1024,
                    'ancillary_member_mismatch')
            data = source.read(member)
            target = output / ('source-' + name)
            with target.open('xb') as stream:
                stream.write(data)
            ancillary.append({'name': target.name, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
    record = {'schema': 1, 'success': True, 'repository': REPOSITORY,
              'artifact_id': ARTIFACT_ID, 'run_id': RUN_ID, 'source_commit': SOURCE_COMMIT,
              'artifact_name': metadata['name'], 'artifact_bytes': ZIP_BYTES,
              'artifact_sha256': ZIP_SHA256, 'compressed_member': COMPRESSED_MEMBER,
              'compressed_bytes': COMPRESSED_BYTES, 'compressed_sha256': COMPRESSED_SHA256,
              'raw_bytes': RAW_BYTES, 'raw_sha256': RAW_SHA256,
              'raw_not_reinflated': True, 'raw_pin_source': 'config/install-images.lock.json',
              'part_bytes_limit': PART_BYTES, 'parts': parts['parts'], 'source_metadata': ancillary,
              'release_published': False, 'firmware_executed_or_mounted': False}
    (output / 'source-relay-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    shutil.rmtree(work)
    print(json.dumps(record))


class TransportFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = b'compressed-fixture\x00' * 37
        self.sha = hashlib.sha256(self.data).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, members):
        path = self.root / 'fixture.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, data in members:
                    archive.writestr(name, data)
        return path

    def test_extract_then_split_reconstructs_bytes_and_hashes(self):
        archive = self.archive([(COMPRESSED_MEMBER, self.data)])
        target = self.root / 'rootfs.img.zst'
        extract_member(archive, target, COMPRESSED_MEMBER, len(self.data), self.sha)
        result = split_verified(target, self.root, 29)
        restored = b''.join((self.root / p['name']).read_bytes() for p in result['parts'])
        self.assertEqual(restored, self.data)
        self.assertEqual(result['sha256'], self.sha)
        self.assertTrue(all(p['bytes'] <= 29 and
                            hashlib.sha256((self.root / p['name']).read_bytes()).hexdigest() == p['sha256']
                            for p in result['parts']))

    def test_wrong_missing_duplicate_or_bad_member_fails(self):
        for members in [[], [(COMPRESSED_MEMBER, b'bad')],
                        [(COMPRESSED_MEMBER, self.data), (COMPRESSED_MEMBER, self.data)]]:
            with self.subTest(members=len(members)):
                archive = self.archive(members)
                with self.assertRaises(ValueError):
                    extract_member(archive, self.root / 'target', COMPRESSED_MEMBER,
                                   len(self.data), self.sha)
                self.assertFalse((self.root / 'target').exists())

    def test_same_size_corruption_and_overrun_are_rejected(self):
        for payload in [b'X' + self.data[1:], self.data + b'X', self.data[:-1]]:
            with self.subTest(size=len(payload)):
                with self.assertRaises(ValueError):
                    copy_verified(io.BytesIO(payload), self.root / 'target', len(self.data), self.sha)
                self.assertFalse((self.root / 'target').exists())

    def test_existing_output_is_not_replaced(self):
        target = self.root / 'target'
        target.write_bytes(b'previous')
        with self.assertRaises(FileExistsError):
            copy_verified(io.BytesIO(self.data), target, len(self.data), self.sha)
        # copy_verified must not remove a preexisting file it did not create.
        self.assertEqual(target.read_bytes(), b'previous')

    def test_metadata_and_storage_origin_guards(self):
        meta = {'id': ARTIFACT_ID, 'size_in_bytes': ZIP_BYTES,
                'digest': 'sha256:' + ZIP_SHA256, 'expired': False,
                'workflow_run': {'id': RUN_ID, 'head_sha': SOURCE_COMMIT}}
        validate_metadata(meta)
        for key, value in [('id', 1), ('size_in_bytes', 1), ('digest', 'sha256:bad'), ('expired', True)]:
            changed = dict(meta, **{key: value})
            with self.assertRaises(ValueError):
                validate_metadata(changed)
        for key in ['id', 'head_sha']:
            changed = dict(meta, workflow_run=dict(meta['workflow_run'], **{key: 'bad'}))
            with self.assertRaises(ValueError):
                validate_metadata(changed)
        validate_storage_location('https://results.blob.core.windows.net/path?sig=fixture')
        for url in ['http://results.blob.core.windows.net/a', 'https://evil.example/a',
                    'https://user:secret@results.blob.core.windows.net/a',
                    'https://blob.core.windows.net.evil.example/a']:
            with self.assertRaises(ValueError):
                validate_storage_location(url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--output', type=Path)
    choice.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(TransportFixtureTests))
        return 0 if result.wasSuccessful() else 1
    materialize(args.output.resolve())
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # urllib exception text can contain a temporary signed URL.
        print('system_materialization_failed:' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
