"""Audit the immutable existing system artifact; never access any handset."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from github_artifacts import REPO

ARTIFACT_ID = 11775595258
ARTIFACT_BYTES = 1_167_934_045
ARTIFACT_SHA256 = '8440d83ab7ddffc8d76d1f0894be89cf24b91396b447041a1ffc7e5177695f0d'
BOOT_SHA256 = '0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc'
SYSTEM_BYTES = 5_368_709_120


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def file_sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download_artifact(path):
    if path.exists():
        if path.stat().st_size == ARTIFACT_BYTES and file_sha256(path) == ARTIFACT_SHA256:
            return
        raise ValueError('Cached artifact differs from the immutable source')
    token = os.environ['UT_ARTIFACT_TOKEN']
    endpoint = f'https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip'
    request = urllib.request.Request(endpoint, headers={'Authorization': 'Bearer ' + token,
                                                      'Accept': 'application/vnd.github+json',
                                                      'X-GitHub-Api-Version': '2022-11-28'})
    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=30)
        raise ValueError('Expected GitHub artifact redirect')
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise ValueError('GitHub artifact request failed') from None
        location = error.headers['Location']
    # The signed storage request intentionally receives no API token/header.
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != 'https' or not parsed.hostname.endswith('.blob.core.windows.net'):
        raise ValueError('Unexpected GitHub artifact storage host')
    hasher = hashlib.sha256()
    with urllib.request.urlopen(location, timeout=60) as source, path.open('xb') as output:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            output.write(block)
            hasher.update(block)
            if output.tell() > ARTIFACT_BYTES:
                raise ValueError('Artifact oversized')
    if path.stat().st_size != ARTIFACT_BYTES or hasher.hexdigest() != ARTIFACT_SHA256:
        raise ValueError('Immutable GitHub artifact size/hash mismatch')


def audit(archive_path, work, output):
    download_artifact(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        targets = {}
        for basename in ('boot.img','rootfs.img.zst','SHA256SUMS','system-report.json','assembly-manifest.json'):
            matched = [n for n in names if Path(n).name == basename]
            if len(matched) != 1:
                raise ValueError('Missing or duplicate candidate member')
            targets[basename] = matched[0]
        sums = {}
        for line in archive.read(targets['SHA256SUMS']).decode('ascii').splitlines():
            digest, name = line.split(None, 1)
            sums[name.strip()] = digest
        boot = archive.read(targets['boot.img'])
        if len(boot) != 53_215_232 or hashlib.sha256(boot).hexdigest() != BOOT_SHA256:
            raise ValueError('Boot differs from verified adaptation')
        if boot[:8] != b'ANDROID!' or b'systempart=/dev/disk/by-partlabel/system' not in boot[64:576]:
            raise ValueError('Boot does not select the measured system partition')
        compressed = work / 'rootfs.img.zst'
        with archive.open(targets['rootfs.img.zst']) as source, compressed.open('xb') as destination:
            for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
                destination.write(block)
        compressed_hash = file_sha256(compressed)
        if compressed_hash != sums['rootfs.img.zst']:
            raise ValueError('Compressed system differs from original build checksums')
        system_hash = hashlib.sha256()
        first = bytearray()
        length = 0
        process = subprocess.Popen(['zstd','-d','-c',str(compressed)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            block = process.stdout.read(8 * 1024 * 1024)
            if not block:
                break
            system_hash.update(block)
            length += len(block)
            if len(first) < 4096:
                first.extend(block[:4096 - len(first)])
            if length > SYSTEM_BYTES:
                process.kill()
                raise ValueError('Expanded system oversized')
        _, error = process.communicate()
        if process.returncode != 0 or length != SYSTEM_BYTES or first[1080:1082] != b'\x53\xef':
            raise ValueError('Invalid expanded ext4 system')
        block_count = struct.unpack_from('<I', first, 1028)[0]
        block_size = 1024 << struct.unpack_from('<I', first, 1048)[0]
        if block_count * block_size != SYSTEM_BYTES:
            raise ValueError('System ext4 geometry mismatch')
        report = json.loads(archive.read(targets['system-report.json']))
        if not report['filesystem_check_passed'] or report['system_raw_bytes'] != SYSTEM_BYTES:
            raise ValueError('Original filesystem validation unavailable')
        result = {'schema':1,'model':'SM-G975F','pda':'G975FXXSGHWC1','artifact_id':ARTIFACT_ID,
                  'artifact_bytes':ARTIFACT_BYTES,'artifact_sha256':ARTIFACT_SHA256,'members':targets,
                  'boot_bytes':len(boot),'boot_sha256':BOOT_SHA256,'system_bytes':SYSTEM_BYTES,
                  'system_sha256':system_hash.hexdigest(),'system_zstd_bytes':compressed.stat().st_size,
                  'system_zstd_sha256':compressed_hash,'system_boot_cmdline':'systempart=/dev/disk/by-partlabel/system',
                  'ubuntu_touch_target':'24.04-2.x','halium':'12','raw_ext4_magic_and_geometry_valid':True,
                  'handset_accessed':False,'hardware_boot_verified':False}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    audit(args.work/'beyond2lte-ubuntu24-system-1.zip',args.work,args.output)


if __name__ == '__main__':
    main()
