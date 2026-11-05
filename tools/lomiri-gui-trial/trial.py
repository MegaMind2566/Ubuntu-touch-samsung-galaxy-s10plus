#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One timed QML bind mount; original packages/authentication stay installed.

No unit is installed/enabled here. A reviewed root handoff is required. The
first trial ALWAYS restores after 600 seconds; there is no accept/commit mode.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

LIVE = Path('/usr/share/lomiri')
RUN = Path('/run/ut-s10-gui-trial-20261105')
PUBLIC_STATUS = Path('/run/ut-s10-gui-trial-status.json')
KERNEL = '4.14.280-gb9b70b29c94c-dirty'
VERSION = '0.5.0+0~20260910085057.5+ubports24.04.2~1.gbp0bd07c'
UPSTREAM = '0bd07c68b7ab8dee5720516c7549dff8992995c6'
SECONDS = 600
MAX_BYTES = 128 * 1024 * 1024


class Refused(RuntimeError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(*argv, timeout=15):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if result.returncode:
        raise Refused('command-failed: ' + Path(argv[0]).name)
    return result.stdout.decode('utf-8').strip()


def safe_path(path, *, trusted=False):
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            raise Refused('missing-path: ' + str(current))
        if stat.S_ISLNK(info.st_mode):
            raise Refused('symbolic-link: ' + str(current))
        if trusted and (info.st_uid != 0 or info.st_mode & 0o022):
            raise Refused('untrusted-owner-or-mode: ' + str(current))
    return path


def read_regular(path, *, trusted=False):
    path = safe_path(path, trusted=trusted)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        raise Refused('not-bounded-regular-file')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Refused('file-size-limit')
    return data


def relative(name):
    path = PurePosixPath(name)
    if (not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or path.is_absolute()
            or '..' in path.parts or str(path) != name):
        raise Refused('unsafe-relative-path')
    return path


def inventory(root):
    root = safe_path(root)
    files, total = {}, 0
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            path = Path(parent) / name
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise Refused('linked-or-special-directory')
        for name in names:
            path = Path(parent) / name
            data = read_regular(path)
            total += len(data)
            if total > MAX_BYTES:
                raise Refused('qml-tree-size-limit')
            files[path.relative_to(root).as_posix()] = digest(data)
    return files, total


def mountpoints(text=None):
    if text is None:
        text = Path('/proc/self/mountinfo').read_text(encoding='ascii')
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 10 or ' - ' not in line:
            raise Refused('malformed-mountinfo')
        target = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
        result[target] = {'id': fields[0], 'options': fields[5].split(',')}
    return result


def reject_live_mounts(points):
    live = LIVE.as_posix()
    if any(name == live or name.startswith(live + '/') for name in points):
        raise Refused('preexisting-live-or-nested-mount')


def environment(*, require_lightdm=True):
    if os.geteuid() != 0 or platform.system() != 'Linux' or platform.release() != KERNEL:
        raise Refused('normal-boot6-root-required')
    if Path('/proc/1/comm').read_text().strip() != 'systemd':
        raise Refused('normal-systemd-required-not-recovery')
    if command('/usr/bin/dpkg', '--print-architecture') != 'arm64':
        raise Refused('architecture-mismatch')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
        raise Refused('os-mismatch')
    for package in ('lomiri', 'lomiri-common'):
        value = command('/usr/bin/dpkg-query', '-W', '-f=${Version}', package)
        if value != VERSION:
            raise Refused('native-package-version-mismatch: ' + package)
    own = os.stat('/proc/self/ns/mnt').st_ino
    if own != os.stat('/proc/1/ns/mnt').st_ino:
        raise Refused('mount-namespace-mismatch')
    if require_lightdm:
        if command('/usr/bin/systemctl', 'is-active', 'lightdm.service') != 'active':
            raise Refused('original-lightdm-not-active')
        pid = command('/usr/bin/systemctl', 'show', '-p', 'MainPID', '--value', 'lightdm.service')
        if not pid.isdecimal() or int(pid) <= 1:
            raise Refused('invalid-lightdm-pid')
        if own != os.stat('/proc/' + pid + '/ns/mnt').st_ino:
            raise Refused('lightdm-mount-namespace-mismatch')
    safe_path(LIVE, trusted=True)
    safe_path('/etc/deviceinfo/devices/beyond2lte.yaml', trusted=True)
    return {'kernel': KERNEL, 'architecture': 'arm64', 'lomiri_version': VERSION,
            'lightdm_active': True, 'mount_namespace_shared': True}


def load_candidate(package, expected):
    if not re.fullmatch(r'[0-9a-f]{64}', expected or ''):
        raise Refused('external-manifest-sha256-required')
    package = safe_path(package, trusted=True)
    data = read_regular(package / 'candidate-manifest.json', trusted=True)
    if digest(data) != expected:
        raise Refused('candidate-manifest-mismatch')
    manifest = json.loads(data)
    if (manifest.get('schema') != 1 or manifest.get('upstream_commit') != UPSTREAM
            or manifest.get('kernel') != KERNEL or manifest.get('architecture') != 'arm64'
            or manifest.get('qml_root') != str(LIVE) or manifest.get('trial_seconds') != SECONDS
            or manifest.get('package_versions') != {'lomiri': VERSION, 'lomiri-common': VERSION}):
        raise Refused('candidate-contract-mismatch')
    files = manifest.get('files', {})
    if len(files) != 39:
        raise Refused('expected-exactly-39-candidate-files')
    for name, info in files.items():
        rel = relative(name)
        if rel.parts[0] != 'qml':
            raise Refused('non-qml-payload')
        payload = read_regular(package / 'candidate' / rel, trusted=True)
        if len(payload) != info['bytes'] or digest(payload) != info['sha256']:
            raise Refused('candidate-payload-mismatch: ' + name)
    for name, info in manifest.get('support_files', {}).items():
        payload = read_regular(package / relative(name), trusted=True)
        if len(payload) != info['bytes'] or digest(payload) != info['sha256']:
            raise Refused('candidate-support-mismatch: ' + name)
    required = {'scripts/lomiri_glass.py', 'tools/lomiri-gui-trial/trial.py',
                'shell/lomiri-glass/upstream.lock.json', 'shell/lomiri-glass/integration.patch'}
    if not required.issubset(manifest.get('support_files', {})):
        raise Refused('unbound-executable-support-files')
    if digest(read_regular(Path(__file__))) != manifest['support_files']['tools/lomiri-gui-trial/trial.py']['sha256']:
        raise Refused('entrypoint-version-mismatch')
    helper_file = package / 'scripts/lomiri_glass.py'
    spec = importlib.util.spec_from_file_location('reviewed_lomiri_preparation', helper_file)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    _, lock, _, _ = helper.load_package(package / 'shell/lomiri-glass')
    if lock['patch_sha256'] != manifest['patch_sha256']:
        raise Refused('patch-identity-mismatch')
    for name, expected_hash in lock['files'].items():
        info = files.get(name, {})
        if info.get('kind') != 'modified' or info.get('original_sha256') != expected_hash:
            raise Refused('original-source-contract-mismatch')
    for name, expected_hash in lock['module_files'].items():
        info = files.get('qml/Panel/Glass/' + name, {})
        if info.get('kind') != 'new' or info.get('sha256') != expected_hash or info.get('original_sha256') is not None:
            raise Refused('module-contract-mismatch')
    return package, manifest, helper


def inspect_live(manifest):
    reject_live_mounts(mountpoints())
    if (LIVE / 'Panel/Glass').exists():
        raise Refused('existing-glass-module')
    for name, info in manifest['files'].items():
        if info['kind'] == 'modified':
            path = LIVE.joinpath(*PurePosixPath(name).parts[1:])
            if digest(read_regular(path, trusted=True)) != info['original_sha256']:
                raise Refused('installed-source-mismatch: ' + name)
    original, size = inventory(LIVE)
    free = shutil.disk_usage('/run').free
    if free < size * 3 + 16 * 1024 * 1024:
        raise Refused('insufficient-volatile-space')
    return original, size


def state_read():
    safe_path(RUN, trusted=True)
    data = json.loads(read_regular(RUN / 'state.json', trusted=True))
    if data.get('schema') != 1 or data.get('run_path') != str(RUN):
        raise Refused('invalid-private-state')
    return data


def state_write(state):
    path = RUN / 'state.json'
    new = RUN / 'state.new'
    fd = os.open(new, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(state, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(new, path)
    publish_state(state)


def publish_state(state):
    """Fixed read-only public progress, with no paths, user data or controls."""
    safe_path(PUBLIC_STATUS.parent, trusted=True)
    if PUBLIC_STATUS.exists() or PUBLIC_STATUS.is_symlink():
        read_regular(PUBLIC_STATUS, trusted=True)
    public = {'schema': 1, 'kind': 'timed-native-gui-trial-status',
              'phase': state['phase'], 'trial_seconds': SECONDS,
              'rollback_was_armed': state.get('rollback_was_armed', False),
              'deadline_epoch_advisory': state.get('deadline_epoch'),
              'original_tree_verified': state.get('original_tree_verified', False),
              'lightdm_active': state.get('lightdm_active'),
              'rollback_commands_verified': state.get('rollback_commands_verified', False),
              'visual_recovery_pending': True, 'handset_gui_accepted': False,
              'failure': bool(state.get('failure'))}
    fd, name = tempfile.mkstemp(prefix='ut-s10-gui-status-', dir=PUBLIC_STATUS.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(public, stream, sort_keys=True)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, PUBLIC_STATUS)
    finally:
        if os.path.exists(name):os.unlink(name)


def stage(package, expected):
    identity = environment()
    package, manifest, helper = load_candidate(package, expected)
    original, size = inspect_live(manifest)
    if RUN.exists() or RUN.is_symlink():
        raise Refused('previous-run-must-be-reviewed-and-cleaned')
    RUN.mkdir(mode=0o700)
    state = {'schema': 1, 'run_path': str(RUN), 'phase': 'staging',
             'manifest_sha256': expected, 'identity': identity,
             'original_tree': original, 'original_qml_bytes': size,
             'originals': {n: i['original_sha256'] for n, i in manifest['files'].items() if i['kind'] == 'modified'}}
    state_write(state)
    # Preserve exact affected originals; the package originals themselves are
    # never overwritten. A bind mount is the only change to the live view.
    for name, expected_hash in state['originals'].items():
        source = LIVE.joinpath(*PurePosixPath(name).parts[1:])
        target = RUN / 'originals' / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(read_regular(source, trusted=True))
        target.chmod(0o600)
        if digest(target.read_bytes()) != expected_hash:
            raise Refused('original-backup-changed')
    helper.prepare(LIVE, RUN / 'stage', package / 'shell/lomiri-glass')
    qml = RUN / 'stage/qml'
    for name, info in manifest['files'].items():
        path = RUN / 'stage' / name
        if digest(read_regular(path)) != info['sha256']:
            raise Refused('prepared-candidate-mismatch')
    if inventory(LIVE)[0] != original:
        raise Refused('live-tree-changed-during-stage')
    candidate_tree, _ = inventory(qml)
    for parent, dirs, names in os.walk(qml):
        Path(parent).chmod(0o755)
        for name in names:
            (Path(parent) / name).chmod(0o644)
    rollback = RUN / 'rollback.py'
    script = read_regular(package / 'tools/lomiri-gui-trial/trial.py', trusted=True)
    rollback.write_bytes(script)
    rollback.chmod(0o700)
    info = qml.stat()
    state.update({'phase': 'staged', 'candidate_tree': candidate_tree,
                  'candidate_dev': info.st_dev, 'candidate_ino': info.st_ino,
                  'rollback_sha256': digest(script)})
    state_write(state)
    return state


def schedule(unit, seconds, *argv):
    command('/usr/bin/systemd-run', '--unit=' + unit, '--on-active=' + str(seconds) + 's',
            '--timer-property=AccuracySec=100ms', '--collect', '--property=Type=oneshot',
            '--property=TimeoutStartSec=180', *argv)
    if command('/usr/bin/systemctl', 'is-active', unit + '.timer') != 'active':
        raise Refused('timer-not-active')


def own_mount(state):
    points = mountpoints()
    if any(name.startswith(LIVE.as_posix() + '/') for name in points):
        raise Refused('foreign-nested-mount-refuse-recovery')
    current = points.get(str(LIVE))
    if not current:
        return False
    info = LIVE.stat()
    if (info.st_dev, info.st_ino) != (state['candidate_dev'], state['candidate_ino']):
        raise Refused('foreign-mount-refuse-unmount')
    if state.get('mount_id') and current['id'] != state['mount_id']:
        raise Refused('mount-identity-changed')
    return True


@contextmanager
def restore_lock():
    import fcntl
    safe_path(RUN, trusted=True)
    fd = os.open(RUN / 'restore.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
            raise Refused('invalid-recovery-lock')
        # Only root callers can reach this lock. A timer waits for an early
        # restore, then rechecks its result; it never treats contention as success.
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def lightdm_state():
    # is-active returns rc3/4 for the very failure recovery must handle.
    return command('/usr/bin/systemctl', 'show', '-p', 'ActiveState', '--value', 'lightdm.service')


def stop_activation(state):
    activation = state.get('activation_unit')
    if not activation:return
    if not re.fullmatch(r'ut-s10-gui-\d+-\d+-activate', activation):
        raise Refused('invalid-activation-unit')
    for suffix in ('.timer', '.service'):
        unit = activation + suffix
        loaded = command('/usr/bin/systemctl', 'show', '-p', 'LoadState', '--value', unit)
        if loaded != 'not-found':command('/usr/bin/systemctl', 'stop', unit)


def restore_unlocked():
    # A failed candidate may have left LightDM inactive; that must never block
    # revealing the original QML and restarting the original display manager.
    environment(require_lightdm=False)
    state = state_read()
    # Refuse a foreign mount BEFORE stopping any unrelated graphical session.
    was_mounted = own_mount(state)
    activation = state.get('activation_unit')
    if activation and not re.fullmatch(r'ut-s10-gui-\d+-\d+-activate', activation):
        raise Refused('invalid-activation-unit')
    failures=[]
    try:stop_activation(state)
    except (Refused,OSError,subprocess.TimeoutExpired):failures.append('activation-stop-failed')
    marker = RUN / 'ROLLBACK_OK'
    if state['phase'] == 'restored' and marker.exists():
        read_regular(marker, trusted=True)
        if inventory(LIVE)[0] == state['original_tree'] and lightdm_state() == 'active':
            return {'rollback': 'already-confirmed', 'visual_recovery_pending': True}
    needs_display_recovery = was_mounted or state['phase'] in ('mounted', 'restore-failed')
    state.update({'phase':'restoring','original_tree_verified':False,'rollback_commands_verified':False})
    try:state_write(state)
    except (Refused,OSError):failures.append('recovery-record-failed')
    try:
        if needs_display_recovery:
            try:command('/usr/bin/systemctl', 'stop', 'lightdm.service', timeout=45)
            except (Refused,OSError,subprocess.TimeoutExpired):failures.append('display-stop-failed')
        if own_mount(state):
            try:command('/usr/bin/umount', str(LIVE))
            except (Refused,OSError,subprocess.TimeoutExpired):failures.append('owned-unmount-failed')
        try:
            reject_live_mounts(mountpoints())
            state['original_tree_verified'] = inventory(LIVE)[0] == state['original_tree']
            if not state['original_tree_verified']:failures.append('original-hash-mismatch')
        except (Refused,OSError,ValueError):failures.append('original-verification-failed')
    finally:
        # Stop/start, rather than coalescing a restart job, ensures an old
        # activation cannot leave a process retaining the candidate's QML.
        try:
            if needs_display_recovery or lightdm_state() != 'active':
                command('/usr/bin/systemctl', 'start', 'lightdm.service', timeout=45)
            state['lightdm_active'] = lightdm_state() == 'active'
        except (Refused,OSError,subprocess.TimeoutExpired):
            state['lightdm_active']=False
        if not state['lightdm_active']:failures.append('display-start-failed')
    if failures:
        state.update({'phase':'restore-failed','failure':True})
        try:state_write(state)
        except (Refused,OSError):pass
        raise Refused('rollback-incomplete: ' + ','.join(failures))
    state['phase'] = 'restored'
    state.update({'rollback_commands_verified':True,'failure':False})
    state_write(state)
    if not marker.exists():
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('ORIGINAL_HASHES_AND_LIGHTDM_ACTIVE\n')
    # A marker certifies commands/hash readback, not visual recovery or unlock.
    return {'rollback': 'commands-and-hashes-confirmed', 'visual_recovery_pending': True}


def restore():
    with restore_lock():return restore_unlocked()


def trial(package, expected):
    if not RUN.exists():
        state = stage(package, expected)
    else:
        environment()
        _, manifest, _ = load_candidate(package, expected)
        inspect_live(manifest)
        state = state_read()
    if state['phase'] != 'staged' or state['manifest_sha256'] != expected:
        raise Refused('run-not-staged-for-this-manifest')
    if inventory(RUN / 'stage/qml')[0] != state['candidate_tree']:
        raise Refused('private-stage-changed')
    if digest(read_regular(RUN / 'rollback.py', trusted=True)) != state['rollback_sha256']:
        raise Refused('private-rollback-changed')
    identifier = 'ut-s10-gui-' + str(os.getpid()) + '-' + str(int(time.time()))
    rollback_unit = identifier + '-rollback'
    state.update({'phase': 'arming', 'rollback_unit': rollback_unit,
                  'activation_unit': identifier + '-activate',
                  'deadline_epoch':int(time.time())+SECONDS})
    state_write(state)
    # PID1 recovery is armed and checked BEFORE the first mount. It is never
    # auto-cancelled, even after positive user feedback in this first trial.
    schedule(rollback_unit, SECONDS, '/usr/bin/python3', str(RUN / 'rollback.py'), 'restore')
    state['phase'] = 'armed'
    state['rollback_was_armed'] = True
    state_write(state)
    try:
        reject_live_mounts(mountpoints())
        command('/usr/bin/mount', '--bind', str(RUN / 'stage/qml'), str(LIVE))
        if not own_mount(state):
            raise Refused('bind-not-visible')
        command('/usr/bin/mount', '-o', 'remount,bind,ro', str(LIVE))
        point = mountpoints()[str(LIVE)]
        if 'ro' not in point['options']:
            raise Refused('bind-not-read-only')
        state.update({'phase': 'mounted', 'mount_id': point['id']})
        state_write(state)
        schedule(state['activation_unit'], 3, '/usr/bin/systemctl', 'restart', 'lightdm.service')
        return {'trial': 'armed', 'qml_files': 39, 'rollback_seconds': SECONDS,
                'automatic_acceptance': False, 'permanent_system_changes': False}
    except BaseException:
        # A failed immediate restore leaves PID1's independent retry armed.
        try:
            restore()
        except Exception:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'stage', 'trial', 'restore'))
    parser.add_argument('--package', type=Path)
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args()
    try:
        if args.action == 'restore':
            result = restore()
        else:
            if args.package is None:
                raise Refused('explicit-root-owned-package-required')
            if args.action == 'check':
                identity = environment()
                _, manifest, _ = load_candidate(args.package, args.manifest_sha256)
                _, size = inspect_live(manifest)
                if RUN.exists():
                    raise Refused('previous-run-exists')
                result = {'preflight': 'pass', 'identity': identity, 'qml_bytes': size,
                          'source_match_only': True, 'installed': False}
            elif args.action == 'stage':
                result = {'stage': stage(args.package, args.manifest_sha256)['phase'], 'installed': False}
            else:
                result = trial(args.package, args.manifest_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'refused': type(error).__name__, 'reason': str(error)}), file=sys.stderr)
        return 77


if __name__ == '__main__':
    raise SystemExit(main())
