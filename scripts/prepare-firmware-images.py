"""Verify and expand the alpha SYSTEM image locally; never access a phone."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

BLOCK = 1024 * 1024
PYTHON_SHA256 = '7ca24f26d6e3f463419ee4f537ddd3acd312c38fe45e678cce08572f26a8bd1a'
BOOT = {'bytes': 57344000, 'sha256': '2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad'}
SYSTEM = {'bytes': 5368709120, 'sha256': 'd23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3'}
COMPRESSED = {'bytes': 1114706918, 'sha256': '6729e58ca7924a7682a332c4a58a1e1ad1dc3b31437707fb49366b518da99928'}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            result.update(block)
    return result.hexdigest()


def verify(path, pin, reason):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != pin['bytes']:
        raise ValueError(reason + '_size_or_type')
    if digest(path) != pin['sha256']:
        raise ValueError(reason + '_hash')


def check_runtime(root):
    if sys.version_info[:3] != (3, 14, 4) or digest(Path(sys.executable)) != PYTHON_SHA256:
        raise ValueError('portable_python_mismatch')


def zstd_reader(path):
    # Standard library included in the pinned official Python 3.14.4 runtime.
    from compression import zstd
    return zstd.open(path, 'rb')


def prepare(root, reader=zstd_reader, runtime_check=check_runtime, progress=print):
    root = Path(root).resolve()
    runtime_check(root)
    images = root / 'images'
    if images.is_symlink() or not images.is_dir():
        raise ValueError('images_directory_unavailable_or_linked')
    verify(images / 'boot.img', BOOT, 'boot')
    destination = images / 'system.img'
    if destination.exists() or destination.is_symlink():
        verify(destination, SYSTEM, 'existing_system_conflict')
        return {'success': True, 'result': 'existing_system_verified', 'system_sha256': SYSTEM['sha256']}
    candidates = [p for p in (root / 'SYSTEM.img.zst', root.parent / 'SYSTEM.img.zst')
                  if p.exists() or p.is_symlink()]
    if len(candidates) != 1:
        raise ValueError('system_archive_missing_or_ambiguous')
    source = candidates[0]
    progress('Verifica di SYSTEM.img.zst...')
    verify(source, COMPRESSED, 'system_archive')
    descriptor, temporary_name = tempfile.mkstemp(prefix='.system-', suffix='.partial', dir=images)
    temporary = Path(temporary_name)
    result_hash = hashlib.sha256()
    total = 0
    next_percent = 10
    try:
        progress('Estrazione locale di SYSTEM. Nessun accesso al telefono.')
        with os.fdopen(descriptor, 'wb') as output, reader(source) as stream:
            while True:
                # One extra byte detects an oversized stream without allowing
                # an unbounded decompression result or oversized output file.
                block = stream.read(min(BLOCK, SYSTEM['bytes'] - total + 1))
                if not block:
                    break
                total += len(block)
                if total > SYSTEM['bytes']:
                    raise ValueError('expanded_system_oversized')
                result_hash.update(block)
                output.write(block)
                percent = total * 100 // SYSTEM['bytes']
                if percent >= next_percent:
                    progress('Estrazione: ' + str(percent) + '%')
                    next_percent = (percent // 10 + 1) * 10
            if total != SYSTEM['bytes']:
                raise ValueError('expanded_system_size_mismatch')
            if result_hash.hexdigest() != SYSTEM['sha256']:
                raise ValueError('expanded_system_hash_mismatch')
            output.flush()
            os.fsync(output.fileno())
        # An exclusive hard-link publication is atomic and cannot replace a
        # conflicting file created while decompression was running.
        try:
            os.link(temporary, destination)
            result = 'system_prepared_and_verified'
        except FileExistsError:
            verify(destination, SYSTEM, 'existing_system_conflict')
            result = 'existing_system_verified'
        return {'success': True, 'result': result, 'system_bytes': total,
                'system_sha256': result_hash.hexdigest(), 'phone_accessed': False}
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.root)
        print('Immagini pronte e verificate in images. Nessuna installazione eseguita.')
        print(json.dumps(result))
    except Exception as error:
        print('Preparazione fermata: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
