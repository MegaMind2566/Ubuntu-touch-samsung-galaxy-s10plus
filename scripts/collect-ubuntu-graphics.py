"""Read fixed, bounded BOOT 6 graphics logs from the pinned TWRP over USB.

No phone files are created or changed and no mount is requested. No SYSTEM or
retained user program is executed. Current RECOVERY and BOOT identities are
checked before any retained user log is opened.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zipfile

SPEC = importlib.util.spec_from_file_location('graphics_first_boot_helpers',
                                             Path(__file__).with_name('collect-first-boot.py'))
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
BOOT_BYTES = 57344000
BOOT_SHA256 = '2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad'
LOG_BYTES = 524288
INVENTORY_ENTRIES = 64
LOG_PATHS = {
    'usc': '/data/system-data/var/log/lightdm/unity-system-compositor.log',
    'usc-old': '/data/system-data/var/log/lightdm/unity-system-compositor.log.old',
    'greeter': '/data/system-data/var/log/lightdm/seat0-greeter.log',
    'greeter-old': '/data/system-data/var/log/lightdm/seat0-greeter.log.old',
    'lightdm': '/data/system-data/var/log/lightdm/lightdm.log',
    'lightdm-old': '/data/system-data/var/log/lightdm/lightdm.log.old',
    'xsession': '/data/user-data/phablet/.xsession-errors',
    'xsession-old': '/data/user-data/phablet/.xsession-errors.old',
    'lomiri-upstart': '/data/user-data/phablet/.cache/upstart/lomiri.log',
    'lomiri-upstart-old': '/data/user-data/phablet/.cache/upstart/lomiri.log.old',
}
INVENTORY_PATHS = {
    'lightdm-inventory': '/data/system-data/var/log/lightdm',
    'journal-inventory': '/data/system-data/var/log/journal',
}
IDENTITY_QUERIES = ('version', 'state', 'uid', 'properties', 'recovery-hash', 'boot-hash', 'data-state')

# All paths come from constants above, never from log contents or user input.
# Metadata is stderr so that log text cannot masquerade as guard results.
SHELL_COMMON = r'''#!/bin/sh
BB=/sbin/busybox
mark() { printf 'UT_GRAPHICS_6: %s\n' "$*" >&2; }
directory_chain() {
    directory=$1
    while :; do
        if [ ! -e "$directory" ] && [ ! -L "$directory" ]; then
            mark "missing_parent=$directory"; return 3
        fi
        [ -d "$directory" ] && [ ! -L "$directory" ] || { mark "unsafe_parent=$directory"; return 1; }
        canonical=$("$BB" readlink -f "$directory") || return 1
        [ "$canonical" = "$directory" ] || { mark "noncanonical_parent=$directory"; return 1; }
        [ "$directory" = / ] && break
        directory=${directory%/*}
        [ -n "$directory" ] || directory=/
    done
}
guard_data() {
    directory_chain /data || return 1
    found=0
    while read -r source target filesystem options rest; do
        [ "$target" = /data ] || continue
        found=$((found + 1))
        [ "$filesystem" = ext4 ] || { mark data_not_ext4; return 1; }
        canonical=$("$BB" readlink -f "$source") || return 1
        case "$canonical" in /dev/block/sda31|/dev/sda31) ;; *) mark data_not_raw_userdata; return 1 ;; esac
    done </proc/mounts
    [ "$found" = 1 ] || { mark data_mount_unavailable_or_ambiguous; return 1; }
}
guard_data || exit 33
'''

# The actual TWRP BusyBox advertises stat -t, but was built without stat -c.
# Keep metadata opaque; its terse format can vary with BusyBox compile options.
SHELL_PARENT = r'''
directory_chain "${path%/*}"
parent_status=$?
[ "$parent_status" = 0 ] || { [ "$parent_status" != 3 ] || exit 44; exit 34; }
mark parent_metadata
"$BB" stat -t "${path%/*}" >&2 || { mark metadata_unavailable; exit 37; }
'''


def script_for(name):
    if name == 'data-state':
        return SHELL_COMMON + "printf 'UT_GRAPHICS_6: data_ready=raw_ext4\n'\n"
    if name in LOG_PATHS:
        path = LOG_PATHS[name]
        return SHELL_COMMON + "path='" + path + "'\n" + SHELL_PARENT + r'''
[ -e "$path" ] || [ -L "$path" ] || { mark missing_file; exit 44; }
[ ! -L "$path" ] && [ -f "$path" ] || { mark missing_or_unsafe_file; exit 35; }
canonical=$("$BB" readlink -f "$path") || exit 35
[ "$canonical" = "$path" ] || { mark noncanonical_file; exit 35; }
mark file_metadata
"$BB" stat -t "$path" >&2 || { mark metadata_unavailable; exit 37; }
''' + '"$BB" tail -c ' + str(LOG_BYTES) + ' "$path"\n'
    if name in INVENTORY_PATHS:
        path = INVENTORY_PATHS[name]
        return SHELL_COMMON + "inventory_root='" + path + "'\n" + r'''
directory_chain "$inventory_root"
parent_status=$?
[ "$parent_status" = 0 ] || { [ "$parent_status" != 3 ] || exit 44; exit 34; }
mark inventory_maxdepth=2
mark inventory_entry_cap=64
# find never follows links; head bounds both enumeration and metadata output.
"$BB" find "$inventory_root" -mindepth 1 -maxdepth 2 | "$BB" head -n 64 |
while IFS= read -r path; do
    case "$path" in "$inventory_root"/*) ;; *) continue ;; esac
    case "$path" in *[!a-zA-Z0-9_./@:+-]*) continue ;; esac
    [ "${#path}" -le 512 ] || continue
    [ ! -L "$path" ] || continue
    [ -f "$path" ] || [ -d "$path" ] || continue
    directory_chain "${path%/*}" || continue
    canonical=$("$BB" readlink -f "$path") || continue
    [ "$canonical" = "$path" ] || continue
    "$BB" stat -t "$path" || { mark metadata_unavailable; exit 37; }
done
'''
    raise ValueError('graphics_query_not_allowed')


def command_for(name):
    if name == 'boot-hash':
        return ['-d', 'shell', '/sbin/busybox head -c ' + str(BOOT_BYTES)
                + ' /dev/block/sda14 | /sbin/busybox sha256sum']
    if name in ('version', 'state', 'uid', 'properties', 'recovery-hash'):
        return legacy.command_for(name)
    script_for(name)
    return ['-d', 'shell', '/sbin/busybox sh -s']


def run_query(executable, name):
    arguments = command_for(name)
    payload = script_for(name).encode('ascii') if name not in IDENTITY_QUERIES[:-1] else None
    try:
        result = subprocess.run([str(executable), *arguments], input=payload, capture_output=True,
                                timeout=90 if name.endswith('-hash') else 45,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if len(result.stdout) > (LOG_BYTES if name in LOG_PATHS else 65536) or len(result.stderr) > 16384:
            return {'exit_code': None, 'timed_out': False, 'stdout': '', 'stderr': 'output_limit',
                    'raw_stdout_bytes': len(result.stdout)}
        return {'exit_code': result.returncode, 'timed_out': False,
                'stdout': result.stdout.decode('utf-8', 'replace'),
                'stderr': result.stderr.decode('utf-8', 'replace'), 'raw_stdout_bytes': len(result.stdout)}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'timed_out': True, 'stdout': '', 'stderr': 'read_timeout'}


def collect(root, runner=run_query, verifier=legacy.check_tools):
    root = Path(root).resolve()
    files = {}
    report = {'schema': 1, 'collector_version': 2, 'boot_version': 6,
              'date_utc': datetime.now(timezone.utc).isoformat(), 'target_model': 'SM-G975F',
              'success': False, 'error': None, 'adb_usb_only': True,
              'partition_writes': False, 'phone_files_written': False, 'mount_changes_requested': False,
              'data_format_requested': False, 'reboot_requested': False, 'system_code_executed': False,
              'ubuntu_touch_graphical_boot_verified': False, 'steps': [], 'image_checks': {},
              'log_tail_limit_bytes': LOG_BYTES, 'inventory_entry_cap_per_directory': INVENTORY_ENTRIES,
              'inventory_maxdepth': 2, 'logs': {}, 'inventories': {}, 'collected_log_count': 0,
              'collection_errors': [], 'metadata_format': 'busybox_stat_terse',
              'note': 'Success means at least one fixed log was read without collection errors, not a graphical boot. Missing logs do not '
                      'prove a service was absent. Lomiri normally uses the user journal; only persistent '
                      'journal metadata is listed here. Current BOOT identity does not date retained logs.'}
    reason = 'local_tools_unavailable'

    def read(name, required=False):
        command_for(name)
        value = runner(root / 'platform-tools/adb.exe', name)
        okay = value['exit_code'] == 0 and not value['timed_out']
        # Keep the same limits with injected/test runners as with real ADB.
        if len(value['stdout'].encode('utf-8')) > (LOG_BYTES * 3 if name in LOG_PATHS else 196608):
            value = dict(value, exit_code=None, stdout='', stderr='output_limit')
            okay = False
        report['steps'].append({'operation': name, 'exit_code': value['exit_code'],
                                'timed_out': value['timed_out'],
                                'raw_stdout_bytes': value.get('raw_stdout_bytes'),
                                'stderr': legacy.redact(value['stderr'][:16384], root)})
        if not okay:
            if required:
                raise ValueError(reason)
            return None
        return legacy.redact(value['stdout'], root)

    try:
        verifier(root)
        reason = 'adb_version_mismatch'
        if 'Version 37.0.1' not in (read('version', True) or ''):
            raise ValueError(reason)
        reason = 'twrp_usb_unavailable'
        if (read('state', True) or '').strip() not in ('device', 'recovery'):
            raise ValueError(reason)
        reason = 'recovery_not_root'
        if (read('uid', True) or '').strip() != '0':
            raise ValueError(reason)
        reason = 'recovery_device_unconfirmed'
        props = dict(line.split('|', 1) for line in (read('properties', True) or '').splitlines() if '|' in line)
        report['properties'] = {key: value[:256] for key, value in props.items() if key in legacy.PROPERTIES}
        if (props.get('ro.product.model') not in ('Galaxy S10+', 'SM-G975F') or
                props.get('ro.product.device') not in ('beyond2', 'beyond2lte') or
                props.get('ro.hardware') != 'exynos9820' or
                props.get('ro.twrp.version') not in ('3.7.0_9', '3.7.0_9-2') or
                'G975FXXSGHWC1' not in (props.get('ro.bootloader'), props.get('ro.boot.bootloader'))):
            raise ValueError(reason)
        for name, expected in (('recovery-hash', legacy.EXPECTED_HASHES['recovery-hash']),
                               ('boot-hash', BOOT_SHA256)):
            reason = 'image_identity_unavailable'
            match = re.fullmatch(r'([a-f0-9]{64})\s+-?', (read(name, True) or '').strip())
            report['image_checks'][name] = {'sha256': match[1] if match else None,
                                           'matches_expected': bool(match and match[1] == expected)}
            if not match or match[1] != expected:
                raise ValueError('image_identity_mismatch')
        reason = 'raw_userdata_unavailable'
        if (read('data-state', True) or '').strip() != 'UT_GRAPHICS_6: data_ready=raw_ext4':
            raise ValueError(reason)
        report['recovery_confirmed'] = True
        print('Identita verificate. Lettura limitata dei soli log grafici conservati...', flush=True)
        for name, path in LOG_PATHS.items():
            value = read(name)
            step = report['steps'][-1]
            status = 'collected' if value is not None else (
                'missing' if step['exit_code'] == 44 and not step['timed_out'] else 'error')
            report['logs'][name] = {'phone_path': path, 'collected': value is not None, 'status': status}
            if value is not None:
                files[name + '.txt'] = value
                report['collected_log_count'] += 1
            elif status == 'error':
                report['collection_errors'].append(name)
        for name in INVENTORY_PATHS:
            value = read(name)
            step = report['steps'][-1]
            status = 'listed' if value is not None else (
                'missing' if step['exit_code'] == 44 and not step['timed_out'] else 'error')
            report['inventories'][name] = {'phone_path': INVENTORY_PATHS[name], 'status': status}
            if value is not None:
                files[name + '.txt'] = value
            elif status == 'error':
                report['collection_errors'].append(name)
        if report['collection_errors']:
            raise ValueError('graphics_collection_incomplete')
        if not report['collected_log_count']:
            raise ValueError('graphics_logs_unavailable')
        report['success'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z_]+', str(error)) else reason
    path = root / 'ubuntu-graphics-6-report.zip'
    number = 1
    while path.exists():
        path = root / ('ubuntu-graphics-6-report-' + str(number) + '.zip')
        number += 1
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr('ubuntu-graphics-report.json', json.dumps(report, indent=2))
    print('Lettura completata.' if report['success'] else 'Lettura fermata: ' + str(report['error']))
    print('Invia questo rapporto: ' + str(path), flush=True)
    return report, path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    result, _ = collect(parser.parse_args().root)
    raise SystemExit(0 if result['success'] else 1)
