"""Apply the two verified graphics access corrections before LightDM starts.

Only /dev/hwbinder and /dev/ion mode bits can change. No allocation, filesystem
repair, service restart, device creation, reboot, or raw partition access occurs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import time

BASE = Path('/userdata/ubuntu-touch-graphics-permissions-1')
LOG_DIR = BASE / 'logs'
TARGETS = ('hwbinder', 'ion')
DESIRED_MODE = 0o666
ACCEPTED_MODES = (0o600, 0o666)
PROBE = Path('/userdata/ubuntu-touch-graphics-probe-1/assets/mapper-probe.py')
PROBE_SHA256 = 'e3ea2b3e551cf7f5a2d7622badba45d91ba8d6d37e0278a4bfa26025f2ce282f'
CAPTURE_BYTES = 524288
LOG_NAMES = ('permissions.json', 'root-mapper.txt', 'phablet-mapper.txt', 'lightdm-mapper.txt')


def error_text(error):
    return type(error).__name__ + ': ' + str(error)[:2048]


def read_node(name):
    if name not in TARGETS:
        raise ValueError('device_name_not_authorized')
    path = '/dev/' + name
    descriptor = os.open(path, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        value = os.fstat(descriptor)
        if not stat.S_ISCHR(value.st_mode):
            raise ValueError('not_character_device:' + name)
        if (value.st_uid, value.st_gid) != (0, 0):
            raise ValueError('unexpected_device_owner:' + name)
        mode = stat.S_IMODE(value.st_mode)
        if mode not in ACCEPTED_MODES:
            raise ValueError('unexpected_initial_mode:' + name + ':' + oct(mode))
        with open('/sys/class/misc/' + name + '/dev', 'r', encoding='ascii') as stream:
            registered = stream.read(64)
        match = re.fullmatch(r'10:([0-9]{1,7})\n?', registered)
        if not match or (os.major(value.st_rdev), os.minor(value.st_rdev)) != (10, int(match[1])):
            raise ValueError('sysfs_device_identity_mismatch:' + name)
        return {'name': name, 'path': path, 'descriptor': descriptor,
                'filesystem_device': value.st_dev, 'inode': value.st_ino,
                'rdev': value.st_rdev, 'major': os.major(value.st_rdev),
                'minor': os.minor(value.st_rdev), 'uid': value.st_uid,
                'gid': value.st_gid, 'original_mode': mode}
    except BaseException:
        os.close(descriptor)
        raise


def current_mode(node):
    value = os.lstat(node['path'])
    if (not stat.S_ISCHR(value.st_mode) or
            (value.st_dev, value.st_ino, value.st_rdev, value.st_uid, value.st_gid) !=
            (node['filesystem_device'], node['inode'], node['rdev'], 0, 0)):
        raise ValueError('device_changed_during_validation:' + node['name'])
    return stat.S_IMODE(value.st_mode)


def change_mode(node, mode):
    if mode not in ACCEPTED_MODES:
        raise ValueError('mode_not_authorized')
    current_mode(node)
    # O_PATH holds the validated inode without opening the binder/ION driver.
    # chmod through its proc fd cannot be redirected to a replacement symlink.
    os.chmod('/proc/self/fd/' + str(node['descriptor']), mode)
    if current_mode(node) != mode:
        raise ValueError('device_mode_readback_mismatch:' + node['name'])


def verify_user_access(user):
    if user not in ('phablet', 'lightdm'):
        raise ValueError('access_probe_user_not_authorized')
    code = ('import json,os; p=("/dev/hwbinder","/dev/ion"); '
            'a={x:os.access(x,os.R_OK|os.W_OK) for x in p}; '
            'print(json.dumps({"uid":os.getuid(),"gid":os.getgid(),'
            '"groups":os.getgroups(),"access":a})); '
            'raise SystemExit(0 if all(a.values()) else 1)')
    command = ['/usr/sbin/runuser', '-u', user, '--', '/usr/bin/env', '-i',
               'PATH=/usr/sbin:/usr/bin:/sbin:/bin', '/usr/bin/python3', '-I', '-c', code]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=4)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError('controlled_UID_access_timeout:' + user)
    if process.returncode != 0:
        raise RuntimeError('controlled_UID_access_failed:' + user + ':' +
                           stdout[:4096].decode('utf-8', 'replace') +
                           stderr[:4096].decode('utf-8', 'replace'))
    report = json.loads(stdout)
    if report.get('access') != {'/dev/hwbinder': True, '/dev/ion': True}:
        raise RuntimeError('controlled_UID_access_result_invalid:' + user)
    return report


def public_node(node):
    return {key: (oct(value) if key == 'original_mode' else value)
            for key, value in node.items() if key != 'descriptor'}


def interrupt_transaction(signum, frame):
    raise RuntimeError('permission_transaction_interrupted:' + str(signum))


def apply_permissions():
    report = {'schema': 1, 'success': False, 'target_names': list(TARGETS),
              'requested_mode': oct(DESIRED_MODE), 'preflight': [],
              'changed': [], 'verified': [], 'controlled_UID_access': {},
              'rollback': [], 'scope': 'hwbinder_and_ion_only'}
    nodes, changed, previous_handlers = [], [], {}
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, interrupt_transaction)
        # Finish every identity/mode check before the first chmod.
        for name in TARGETS:
            node = read_node(name)
            nodes.append(node)
            report['preflight'].append(public_node(node))
        for node in nodes:
            if node['original_mode'] != DESIRED_MODE:
                changed.append(node)
                change_mode(node, DESIRED_MODE)
                report['changed'].append(node['name'])
        for node in nodes:
            if current_mode(node) != DESIRED_MODE:
                raise RuntimeError('final_device_mode_mismatch:' + node['name'])
            report['verified'].append({'name': node['name'], 'mode': oct(DESIRED_MODE)})
        for user in ('phablet', 'lightdm'):
            report['controlled_UID_access'][user] = verify_user_access(user)
        report['success'] = True
    except Exception as error:
        report['error'] = error_text(error)
        for node in reversed(changed):
            entry = {'name': node['name'], 'restore_mode': oct(node['original_mode'])}
            try:
                change_mode(node, node['original_mode'])
                entry['success'] = True
            except Exception as rollback_error:
                entry.update(success=False, error=error_text(rollback_error))
            report['rollback'].append(entry)
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        for node in nodes:
            os.close(node['descriptor'])
    return report


def owned_directory(path, expected_mode):
    value = os.lstat(path)
    if (not stat.S_ISDIR(value.st_mode) or (value.st_uid, value.st_gid) != (0, 0)
            or stat.S_IMODE(value.st_mode) != expected_mode):
        raise RuntimeError('unsafe_directory:' + str(path))


def log_path(name):
    if name not in LOG_NAMES:
        raise ValueError('log_name_not_authorized')
    path = LOG_DIR / name
    try:
        value = path.lstat()
    except FileNotFoundError:
        return path
    if (not stat.S_ISREG(value.st_mode) or (value.st_uid, value.st_gid) != (0, 0)
            or stat.S_IMODE(value.st_mode) != 0o600 or value.st_nlink != 1):
        raise RuntimeError('unsafe_existing_log:' + name)
    return path


def write_log(name, data):
    path = log_path(name)
    if len(data) > CAPTURE_BYTES:
        data = data[:65536] + b'\n[output truncated; tail follows]\n' + data[-458688:]
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)


def optional_mapper_probes():
    report = {'diagnostic_only': True, 'controlled_UID_comparison_not_live_LightDM_session': True}
    try:
        for parent in (PROBE.parent.parent, PROBE.parent):
            owned_directory(parent, 0o755)
        value = PROBE.lstat()
        if (not stat.S_ISREG(value.st_mode) or (value.st_uid, value.st_gid) != (0, 0)
                or stat.S_IMODE(value.st_mode) != 0o644 or value.st_nlink != 1
                or hashlib.sha256(PROBE.read_bytes()).hexdigest() != PROBE_SHA256):
            raise RuntimeError('immutable_probe1_identity_mismatch')
    except (OSError, RuntimeError) as error:
        report.update(skipped=True, reason=error_text(error))
        for user in ('root', 'phablet', 'lightdm'):
            write_log(user + '-mapper.txt', (json.dumps(report) + '\n').encode())
        return report
    report['skipped'] = False
    for user, home in (('root', '/root'), ('phablet', '/home/phablet'), ('lightdm', '/var/lib/lightdm')):
        filename = user + '-mapper.txt'
        path = log_path(filename)
        command = ['/usr/sbin/runuser', '-u', user, '--', '/usr/bin/env', '-i',
                   'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'HOME=' + home,
                   'USER=' + user, 'LOGNAME=' + user,
                   'LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libtls-padding.so',
                   'HYBRIS_LOGGING_LEVEL=debug', 'HYBRIS_LD_DEBUG=1',
                   '/usr/bin/python3', '-I', str(PROBE)]
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                process.wait(timeout=8)
                report[user] = {'exit_code': process.returncode}
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                report[user] = {'exit_code': process.returncode, 'timeout': True}
        with path.open('rb') as stream:
            data = stream.read(1048576)
        write_log(filename, data)
    return report


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    if sys.argv[1:]:
        raise ValueError('no_runtime_arguments_supported')
    if os.geteuid() != 0:
        raise RuntimeError('root_required')
    owned_directory(BASE, 0o755)
    owned_directory(BASE / 'assets', 0o755)
    asset = (BASE / 'assets/apply-permissions.py').lstat()
    if (not stat.S_ISREG(asset.st_mode) or (asset.st_uid, asset.st_gid) != (0, 0)
            or stat.S_IMODE(asset.st_mode) != 0o644 or asset.st_nlink != 1):
        raise RuntimeError('unsafe_runtime_asset')
    try:
        LOG_DIR.mkdir(mode=0o700)
    except FileExistsError:
        pass
    owned_directory(LOG_DIR, 0o700)
    for name in LOG_NAMES:
        log_path(name)
    report = apply_permissions()
    report.update(kernel=os.uname().release, uptime_seconds=time.clock_gettime(time.CLOCK_BOOTTIME),
                  baseline_handset_modes={'hwbinder': '0o600', 'ion': '0o600'},
                  removal='Remove only the installed Data rules/unit/drop-in; reboot restores kernel defaults.',
                  hardware_graphical_boot_verified=False)
    write_log('permissions.json', (json.dumps(report, indent=2) + '\n').encode())
    if not report['success']:
        print('UT_GRAPHICS_PERMISSIONS_1: failed; LightDM remains blocked', flush=True)
        return 1
    try:
        report['optional_mapper_probes'] = optional_mapper_probes()
    except Exception as error:
        report['optional_mapper_probes'] = {'diagnostic_only': True, 'error': error_text(error)}
    write_log('permissions.json', (json.dumps(report, indent=2) + '\n').encode())
    print('UT_GRAPHICS_PERMISSIONS_1: hwbinder and ion validated; LightDM may start', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
