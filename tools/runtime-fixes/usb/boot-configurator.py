#!/usr/bin/python3
"""Run the pinned configfs initialization once, from a fresh normal boot.

Installed by manage-live-usb-config.py. Never repairs/unlinks an existing gadget.
The only configfs writes are those of the hash-verified, minimally patched
UBports configurator, before usb-moded itself is allowed to start.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys

BASE = Path('/userdata/ubuntu-touch-usb-config-1')
ORIGINAL = Path('/usr/libexec/ubports-usb-moded-configurator')
ORIGINAL_SHA = '76059b53af8a12796e3c2908ad8934fa7ca32d65c678d6a97a47a1fce588006a'
KERNEL = '4.14.280-gb9b70b29c94c-dirty'
GADGET = Path('/sys/kernel/config/usb_gadget/g1')
ANDROID_USB = Path('/sys/class/android_usb/android0')
STATE = Path('/run/ut-s10plus-usb-config-1.json')
CONF = GADGET / 'configs/c.1/strings/0x409/configuration'
RUNTIME = Path('/run/ubports-usb-moded-conf/20-ubports-autodetected.ini')


def secure(path, directory=False):
    value = path.lstat()
    if (not (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode))
            or value.st_uid != 0 or value.st_gid != 0 or value.st_mode & 0o022):
        raise RuntimeError('unsafe_owned_path:' + str(path))


def digest(path):
    secure(path)
    if path.stat().st_size > 262144:
        raise RuntimeError('oversized_payload:' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess_boot(boot_id, installed_boot_id, old, gadget_exists, android_exists):
    """Pure eligibility check; visible empty links cannot prove a fresh gadget."""
    if boot_id == installed_boot_id:
        raise RuntimeError('normal_reboot_required_before_trial')
    if old is not None:
        raise RuntimeError('earlier_attempt_or_state_inconsistent_no_retry')
    if gadget_exists or android_exists:
        raise RuntimeError('gadget_already_exists_no_live_reconfiguration')
    return 'fresh'


def record(value, first=False):
    data = (json.dumps(value, sort_keys=True) + '\n').encode()
    if first:
        fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    else:
        secure(STATE)
        fd = os.open(STATE, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    print('S10PLUS_USB_CONFIG ' + json.dumps(value, sort_keys=True), flush=True)


def main():
    if os.geteuid() != 0 or platform.machine() != 'aarch64' or platform.release() != KERNEL:
        raise RuntimeError('only_verified_s10plus_boot6_supported')
    secure(Path('/userdata'), True)
    secure(BASE, True)
    secure(BASE / 'manifest.json')
    manifest = json.loads((BASE / 'manifest.json').read_text())
    if digest(ORIGINAL) != ORIGINAL_SHA:
        raise RuntimeError('installed_configurator_changed')
    for name in ('boot-configurator.py', 'configurator.sh'):
        if digest(BASE / name) != manifest['payloads'][name]:
            raise RuntimeError('payload_identity_changed:' + name)
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    old = None
    if STATE.exists() or STATE.is_symlink():
        secure(STATE)
        old = json.loads(STATE.read_text())
    assess_boot(boot_id, manifest['installed_boot_id'], old,
                GADGET.exists(), ANDROID_USB.exists())
    if not GADGET.parent.is_dir():
        raise RuntimeError('configfs_gadget_subsystem_unavailable')
    value = {'boot_id': boot_id, 'attempted': True, 'success': False,
             'configuration': 'Ubuntu Touch', 'version': manifest['version']}
    # Persist the attempt before creating anything: a partial failure is never
    # mistaken for a pristine gadget on a subsequent service start.
    record(value, first=True)
    process = subprocess.Popen(['/bin/sh', '-eu', str(BASE / 'configurator.sh')],
                               start_new_session=True)
    try:
        code = process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        value['error'] = 'configurator_timeout_no_retry'
        record(value)
        raise RuntimeError(value['error'])
    if code != 0:
        value.update(error='configurator_failed_no_retry', exit_code=code)
        record(value)
        raise RuntimeError(value['error'])
    if CONF.read_text().strip() != 'Ubuntu Touch' or not RUNTIME.is_file():
        value['error'] = 'postcondition_failed_no_retry'
        record(value)
        raise RuntimeError(value['error'])
    value['success'] = True
    record(value)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('S10PLUS_USB_CONFIG refused: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
