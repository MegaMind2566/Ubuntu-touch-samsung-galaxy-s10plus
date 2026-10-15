#!/usr/bin/env python3
"""Publish the pinned alpha only after its complete release assets verify.

SYSTEM comes from the immutable Actions artifact. The separately built local
BOOT/tools ZIP must be uploaded to the draft by its owner. No release asset is
ever deleted, overwritten or renamed, and no Git tag is created or repointed
directly. A timeout leaves the draft available for the same workflow to resume.

API contract: https://docs.github.com/en/rest/releases/releases and /assets.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v0.1.0-alpha.1'
ZIP_NAME = 'UbuntuTouch-S10plus-v0.1.0-alpha.1-boot-and-tools-Windows.zip'
JSON_LIMIT = 2 * 1024 * 1024
BUFFER_BYTES = 4 * 1024 * 1024


class ReleaseError(ValueError):
    """Only fixed, non-secret error codes may reach the workflow log."""


def require(condition, code):
    if not condition:
        raise ReleaseError(code)


def identity(path):
    digest = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        while block := stream.read(BUFFER_BYTES):
            digest.update(block)
            count += len(block)
    return {'name': path.name, 'bytes': count, 'sha256': digest.hexdigest()}


def validate_spec(spec, name):
    require(isinstance(spec, dict) and spec.get('name') == name,
            'asset_name_mismatch')
    require(type(spec.get('bytes')) is int and 0 < spec['bytes'] < 2 * 1024**3,
            'asset_size_invalid')
    require(isinstance(spec.get('sha256'), str) and
            re.fullmatch('[0-9a-f]{64}', spec['sha256']), 'asset_sha256_invalid')
    return {key: spec[key] for key in ('name', 'bytes', 'sha256')}


def load_config(path, repository, root=ROOT):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 262144,
            'release_config_missing_or_oversized')
    raw = path.read_bytes()
    config = json.loads(raw)
    require(config.get('schema') == 1 and config.get('tag') == TAG,
            'release_config_schema_or_tag')
    require(re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) and
            config.get('repository', '').lower() == repository.lower(),
            'release_repository_mismatch')
    require(isinstance(config.get('name'), str) and 0 < len(config['name']) <= 200,
            'release_name_invalid')
    relative = Path(config.get('notes_path', ''))
    require(not relative.is_absolute() and '..' not in relative.parts and
            relative.parts[:2] == ('docs', 'releases'), 'release_notes_path_invalid')
    notes = root / relative
    require(notes.is_file() and not notes.is_symlink() and
            notes.resolve().is_relative_to(root.resolve()) and
            0 < notes.stat().st_size <= 131072, 'release_notes_missing_or_oversized')
    notes_bytes = notes.read_bytes()
    config['system'] = validate_spec(config.get('system'), 'SYSTEM.img.zst')
    config['boot_and_tools'] = validate_spec(config.get('boot_and_tools'), ZIP_NAME)
    return config, raw, notes_bytes


def write_exact(path, data):
    if path.exists():
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                'local_asset_conflict')
    else:
        with path.open('xb') as stream:
            stream.write(data)
    return identity(path)


def prepare_metadata(work, raw_config, notes, config):
    work.mkdir(parents=True, exist_ok=True)
    require(not work.is_symlink(), 'work_directory_symlink')
    manifest = write_exact(work / 'release-manifest.json', raw_config)
    release_notes = write_exact(work / 'release-notes.md', notes)
    expected = {item['name']: item for item in
                (config['system'], config['boot_and_tools'], manifest, release_notes)}
    sums = ''.join(expected[name]['sha256'] + '  ' + name + '\n'
                   for name in sorted(expected)).encode('ascii')
    checksums = write_exact(work / 'SHA256SUMS', sums)
    expected[checksums['name']] = checksums
    return expected


def materialize_system(work, expected, helper=None):
    if helper is None:
        spec = importlib.util.spec_from_file_location(
            'release_system_transport', ROOT / 'scripts/materialize-release-system.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
    require(expected['name'] == 'SYSTEM.img.zst' and
            expected['bytes'] == helper.COMPRESSED_BYTES and
            expected['sha256'] == helper.COMPRESSED_SHA256,
            'system_pin_differs_from_immutable_transport')
    target = work / expected['name']
    if target.exists():
        require(not target.is_symlink() and identity(target) == expected,
                'local_system_conflict')
        return target
    parts_dir = work / 'system-parts'
    helper.materialize(parts_dir)
    record = json.loads((parts_dir / 'source-relay-manifest.json').read_bytes())
    require(record.get('success') is True and
            record.get('compressed_bytes') == expected['bytes'] and
            record.get('compressed_sha256') == expected['sha256'] and
            len(record.get('parts', [])) == 3, 'system_parts_manifest_mismatch')
    digest = hashlib.sha256()
    total = 0
    created = False
    try:
        with target.open('xb') as output:
            created = True
            for index, item in enumerate(record['parts'], 1):
                name = f'rootfs.img.zst.part{index:02d}'
                part = parts_dir / name
                require(item.get('name') == name and part.is_file() and
                        not part.is_symlink(), 'system_part_path_invalid')
                part_hash = hashlib.sha256()
                part_bytes = 0
                with part.open('rb') as source:
                    while block := source.read(BUFFER_BYTES):
                        part_bytes += len(block)
                        total += len(block)
                        require(part_bytes <= item['bytes'] and total <= expected['bytes'],
                                'system_part_oversized')
                        part_hash.update(block)
                        digest.update(block)
                        output.write(block)
                require(part_bytes == item['bytes'] and
                        part_hash.hexdigest() == item['sha256'], 'system_part_hash_mismatch')
        require(total == expected['bytes'] and digest.hexdigest() == expected['sha256'],
                'joined_system_identity_mismatch')
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise
    return target


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url, host=None):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and not parsed.username and not parsed.password and
            parsed.port in (None, 443) and not parsed.fragment, 'download_origin_invalid')
    if host:
        require(parsed.hostname == host, 'authenticated_origin_invalid')
    else:
        name = parsed.hostname or ''
        require(name.endswith('.githubusercontent.com') or
                name.endswith('.blob.core.windows.net'), 'download_storage_invalid')


class GitHub:
    def __init__(self, repository, token, opener=None):
        require(bool(token), 'github_token_missing')
        require(re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository),
                'github_repository_invalid')
        self.repository = repository
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def headers(self, url, host='api.github.com', accept='application/vnd.github+json'):
        require(host in ('api.github.com', 'uploads.github.com'),
                'authenticated_host_not_allowed')
        validate_url(url, host)
        return {'Authorization': 'Bearer ' + self.token, 'Accept': accept,
                'X-GitHub-Api-Version': '2022-11-28',
                'User-Agent': 'beyond2lte-verified-firmware-release'}

    def open(self, request):
        try:
            return self.opener.open(request, timeout=300)
        except urllib.error.HTTPError:
            raise
        except Exception:
            raise ReleaseError('github_transport_failed') from None

    def json(self, method, suffix, payload=None, missing=False):
        url = 'https://api.github.com/repos/' + self.repository + suffix
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        headers = self.headers(url)
        if data is not None:
            headers['Content-Type'] = 'application/json'
        try:
            response = self.open(urllib.request.Request(url, data=data, headers=headers,
                                                      method=method))
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code == 404 and missing:
                return None
            raise ReleaseError('github_api_status_' + str(code)) from None
        with response:
            raw = response.read(JSON_LIMIT + 1)
        require(len(raw) <= JSON_LIMIT, 'github_json_oversized')
        return json.loads(raw)

    def upload(self, release_id, path, expected):
        positive_id(release_id)
        require(identity(path) == expected and not path.is_symlink(),
                'upload_local_identity_mismatch')
        url = ('https://uploads.github.com/repos/' + self.repository +
               f'/releases/{release_id}/assets?name=' +
               urllib.parse.quote(expected['name'], safe=''))
        headers = self.headers(url, 'uploads.github.com')
        headers.update({'Content-Type': 'application/octet-stream',
                        'Content-Length': str(expected['bytes'])})
        try:
            with path.open('rb') as source:
                request = urllib.request.Request(url, data=source, headers=headers,
                                                 method='POST')
                with self.open(request) as response:
                    raw = response.read(JSON_LIMIT + 1)
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            raise ReleaseError('github_upload_status_' + str(code)) from None
        require(len(raw) <= JSON_LIMIT, 'github_upload_json_oversized')
        asset = json.loads(raw)
        validate_asset(asset, expected)
        return asset

    def verify_download(self, asset, expected):
        # An authenticated API request may stream bytes or return a signed
        # storage redirect. Authorization is never copied to storage requests.
        url = ('https://api.github.com/repos/' + self.repository +
               '/releases/assets/' + str(positive_id(asset.get('id'))))
        request = urllib.request.Request(
            url, headers=self.headers(url, accept='application/octet-stream'))
        response = None
        for attempt in range(4):
            try:
                response = self.open(request)
                break
            except urllib.error.HTTPError as error:
                code = error.code
                location = error.headers.get('Location', '')
                error.close()
                require(code in (301, 302, 303, 307, 308) and attempt < 3,
                        'github_asset_download_status_' + str(code))
                validate_url(location)
                request = urllib.request.Request(location, headers={
                    'User-Agent': 'beyond2lte-verified-firmware-release'})
        require(response is not None, 'github_asset_download_missing')
        digest = hashlib.sha256()
        count = 0
        with response:
            while block := response.read(min(BUFFER_BYTES, expected['bytes'] - count + 1)):
                count += len(block)
                require(count <= expected['bytes'], 'release_asset_download_oversized')
                digest.update(block)
        require(count == expected['bytes'] and digest.hexdigest() == expected['sha256'],
                'release_asset_download_hash_mismatch')


def positive_id(value):
    require(type(value) is int and value > 0, 'github_object_id_invalid')
    return value


def validate_asset(asset, expected, pending_manual=False):
    positive_id(asset.get('id'))
    require(asset.get('name') == expected['name'], 'release_asset_name_mismatch')
    if pending_manual and asset.get('state') != 'uploaded':
        return False
    require(asset.get('state') == 'uploaded' and type(asset.get('size')) is int and
            asset['size'] == expected['bytes'],
            'release_asset_size_or_state_conflict')
    # Older GitHub assets may omit digest; the mandatory streamed verification
    # before publication still authenticates their complete bytes.
    require(asset.get('digest') in (None, 'sha256:' + expected['sha256']),
            'release_asset_digest_conflict')
    return True


def assets_for(api, release_id, expected):
    values = api.json('GET', f'/releases/{release_id}/assets?per_page=100')
    require(isinstance(values, list) and len(values) < 100, 'release_asset_list_invalid')
    result = {}
    for asset in values:
        name = asset.get('name')
        require(name in expected and name not in result, 'unexpected_or_duplicate_release_asset')
        validate_asset(asset, expected[name], pending_manual=name == ZIP_NAME)
        result[name] = asset
    return result


def find_release(api, tag):
    matches = []
    for page in range(1, 11):
        values = api.json('GET', f'/releases?per_page=100&page={page}')
        require(isinstance(values, list), 'release_list_invalid')
        matches.extend(item for item in values if item.get('tag_name') == tag)
        if len(values) < 100:
            break
    else:
        raise ReleaseError('release_pagination_limit')
    require(len(matches) <= 1, 'duplicate_release_tag')
    return matches[0] if matches else None


def tag_target(api, tag):
    value = api.json('GET', '/git/ref/tags/' + urllib.parse.quote(tag, safe=''), missing=True)
    if value is None:
        return None
    obj = value.get('object', {})
    for _ in range(5):
        require(re.fullmatch('[0-9a-f]{40}', obj.get('sha', '')), 'tag_object_sha_invalid')
        if obj.get('type') == 'commit':
            return obj['sha']
        require(obj.get('type') == 'tag', 'tag_object_type_invalid')
        value = api.json('GET', '/git/tags/' + obj['sha'])
        obj = value.get('object', {})
    raise ReleaseError('annotated_tag_depth_limit')


def validate_release(release, config, notes, target, draft):
    positive_id(release.get('id'))
    require(release.get('tag_name') == config['tag'] and
            release.get('name') == config['name'] and release.get('body') == notes and
            release.get('prerelease') is True and release.get('draft') is draft,
            'release_metadata_conflict')
    require(re.fullmatch('[0-9a-f]{40}', release.get('target_commitish', '')),
            'release_target_not_pinned_commit')
    if draft:
        require(release['target_commitish'] == target, 'draft_target_commit_conflict')


def verify_complete(api, release_id, expected):
    assets = assets_for(api, release_id, expected)
    require(set(assets) == set(expected), 'release_asset_set_incomplete')
    for name in sorted(expected):
        validate_asset(assets[name], expected[name])
        api.verify_download(assets[name], expected[name])
    return assets


def fingerprint(assets):
    return {name: (item['id'], item.get('size'), item.get('digest'), item.get('state'))
            for name, item in assets.items()}


def publish(api, config, notes_bytes, expected, work, target,
            wait_seconds=1500, poll_seconds=15, clock=time.monotonic,
            sleep=time.sleep, system_factory=materialize_system):
    require(re.fullmatch('[0-9a-f]{40}', target), 'github_sha_invalid')
    require(0 <= wait_seconds <= 1500 and 0 < poll_seconds <= 30,
            'release_wait_budget_invalid')
    notes = notes_bytes.decode('utf-8')
    release = find_release(api, config['tag'])
    existing_tag = tag_target(api, config['tag'])
    if release is not None and release.get('draft') is False:
        validate_release(release, config, notes, target, draft=False)
        require(existing_tag == release['target_commitish'], 'published_tag_target_conflict')
        verify_complete(api, release['id'], expected)
        print('RELEASE_ALREADY_PUBLISHED_AND_VERIFIED tag=' + config['tag'])
        return {'published': True, 'already_published': True, 'release_id': release['id']}
    if release is None:
        require(existing_tag is None, 'tag_exists_without_matching_release')
        release = api.json('POST', '/releases', {
            'tag_name': config['tag'], 'target_commitish': target,
            'name': config['name'], 'body': notes, 'draft': True,
            'prerelease': True})
    validate_release(release, config, notes, target, draft=True)
    require(existing_tag in (None, target), 'draft_tag_target_conflict')
    release_id = release['id']
    assets = assets_for(api, release_id, expected)
    print('DRAFT_READY tag=' + config['tag'] + ' release_id=' + str(release_id) +
          ' manual_asset=' + ZIP_NAME, flush=True)
    for name in sorted(set(expected) - {ZIP_NAME}):
        if name in assets:
            api.verify_download(assets[name], expected[name])
            continue
        path = system_factory(work, expected[name]) if name == 'SYSTEM.img.zst' else work / name
        api.upload(release_id, path, expected[name])
    deadline = clock() + wait_seconds
    print('WAITING_FOR_VERIFIED_MANUAL_ZIP max_seconds=' + str(wait_seconds), flush=True)
    while True:
        current = api.json('GET', f'/releases/{release_id}')
        if current.get('draft') is False:
            validate_release(current, config, notes, target, draft=False)
            require(tag_target(api, config['tag']) == current['target_commitish'],
                    'published_tag_target_conflict')
            verify_complete(api, release_id, expected)
            return {'published': True, 'already_published': True, 'release_id': release_id}
        validate_release(current, config, notes, target, draft=True)
        assets = assets_for(api, release_id, expected)
        if ZIP_NAME in assets and assets[ZIP_NAME].get('state') == 'uploaded':
            verified = verify_complete(api, release_id, expected)
            # Re-read metadata after potentially large downloads. Refuse changes
            # or extra assets; only the draft/prerelease flags are mutated.
            current = api.json('GET', f'/releases/{release_id}')
            validate_release(current, config, notes, target, draft=True)
            require(tag_target(api, config['tag']) in (None, target),
                    'draft_tag_target_conflict')
            require(fingerprint(assets_for(api, release_id, expected)) == fingerprint(verified),
                    'release_assets_changed_during_verification')
            result = api.json('PATCH', f'/releases/{release_id}',
                              {'draft': False, 'prerelease': True})
            validate_release(result, config, notes, target, draft=False)
            require(tag_target(api, config['tag']) == target, 'published_tag_target_conflict')
            print('RELEASE_PUBLISHED_AND_VERIFIED tag=' + config['tag'], flush=True)
            return {'published': True, 'already_published': False, 'release_id': release_id}
        remaining = deadline - clock()
        require(remaining > 0, 'manual_zip_not_received_draft_retained')
        sleep(min(poll_seconds, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path,
                        default=ROOT / 'config/releases/v0.1.0-alpha.1.json')
    parser.add_argument('--work', type=Path, default=ROOT / 'out/firmware-release')
    parser.add_argument('--wait-seconds', type=int, default=1500)
    args = parser.parse_args()
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    config, raw, notes = load_config(args.manifest, repository)
    expected = prepare_metadata(args.work, raw, notes, config)
    api = GitHub(repository, os.environ.get('GITHUB_TOKEN', ''))
    result = publish(api, config, notes, expected, args.work,
                     os.environ.get('GITHUB_SHA', ''), wait_seconds=args.wait_seconds)
    (args.work / 'publication-result.json').write_text(json.dumps(result, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Never log urllib exception text, response bodies, tokens or signed URLs.
        code = str(error) if isinstance(error, ReleaseError) else type(error).__name__
        print('firmware_release_failed:' + code, file=sys.stderr)
        raise SystemExit(1)
