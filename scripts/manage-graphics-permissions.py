"""Install, read or undo the BOOT 6 graphics permissions correction.

Only fixed configuration and payload files in already mounted raw userdata are
changed in TWRP. On the next normal Ubuntu boot the reviewed unit changes only
/dev/hwbinder and /dev/ion to mode 0666, before the display manager starts.
BOOT, SYSTEM and VENDOR images are never written by this program.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zipfile


def load_helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


legacy = load_helper('permissions_first_boot_helpers', 'collect-first-boot.py')
graphics = load_helper('permissions_stored_graphics_helpers', 'collect-ubuntu-graphics.py')
BOOT_BYTES = 57344000
BOOT_SHA256 = '2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad'
BASE = '/data/ubuntu-touch-graphics-permissions-1'
ASSET_NAMES = ('apply-permissions.py', 'ubuntu-touch-graphics-permissions.service',
               '99-ubuntu-touch-s10plus-graphics.rules', '50-ubuntu-touch-graphics-permissions.conf')
# The drop-in is published last: it is the only dependency which activates the
# correction. Each destination is a fixed name, never supplied by a log or CLI.
DESTINATIONS = {
    'ubuntu-touch-graphics-permissions.service': '/data/system-data/etc/systemd/system/ubuntu-touch-graphics-permissions.service',
    '99-ubuntu-touch-s10plus-graphics.rules': '/data/system-data/etc/udev/rules.d/99-ubuntu-touch-s10plus-graphics.rules',
    '50-ubuntu-touch-graphics-permissions.conf': '/data/system-data/etc/systemd/system/lightdm.service.d/50-ubuntu-touch-graphics-permissions.conf',
}
DROPIN_NAME = ASSET_NAMES[3]
PARENT_DIRECTORIES = ('/data/system-data/etc/systemd', '/data/system-data/etc/systemd/system',
                      '/data/system-data/etc/systemd/system/lightdm.service.d',
                      '/data/system-data/etc/udev', '/data/system-data/etc/udev/rules.d')
# Filled only after the reviewed runtime payload is frozen. Empty pins fail closed.
PAYLOAD_SHA256 = {
    'apply-permissions.py': 'f53e3432444691d86c099057bb81402cb395b3ded28d483951b7c8745001870c',
    'ubuntu-touch-graphics-permissions.service': '8d02903da053300c81ed8e6ee518ba0e5fb2e35e3deb2d86b0303e4ca0c4cd04',
    '99-ubuntu-touch-s10plus-graphics.rules': '2fa0e44d37bb3e71726b4099d1de124139bfcb8e17aab906cdaca1b8ee2a35da',
    '50-ubuntu-touch-graphics-permissions.conf': '44bcf2ac1ec140e3a4d86d854234944c7d0c5ab8c5419db815b5ed463415fcf8',
}
LOG_BYTES = 524288
LOG_NAMES = ('permissions.json', 'root-mapper.txt', 'phablet-mapper.txt', 'lightdm-mapper.txt')
RETAINED_LOGS = ('usc-head', 'usc', 'greeter', 'lightdm')
IDENTITY_QUERIES = ('version', 'state', 'uid', 'properties', 'recovery-hash', 'boot-hash', 'data-state')

SHELL_COMMON = r'''#!/bin/sh
BB=/sbin/busybox
BASE=/data/ubuntu-touch-graphics-permissions-1
mark() { printf 'UT_GRAPHICS_PERMISSIONS_1: %s\n' "$*" >&2; }
exists() { [ -e "$1" ] || [ -L "$1" ]; }
root_owned() {
    metadata=$("$BB" stat -t "$1") || return 1
    set -- $metadata
    [ "$#" -ge 6 ] && [ "$5" = 0 ] && [ "$6" = 0 ] || { mark nonroot_metadata; return 1; }
}
directory_chain() {
    directory=$1
    while :; do
        [ -d "$directory" ] && [ ! -L "$directory" ] || { mark unsafe_parent; return 1; }
        canonical=$("$BB" readlink -f "$directory") || return 1
        [ "$canonical" = "$directory" ] && root_owned "$directory" || return 1
        [ "$directory" = /data ] && break
        metadata=$("$BB" stat -t "$directory") || return 1
        set -- $metadata
        mode=$((0x$4))
        [ $((mode & 18)) = 0 ] || { mark writable_parent; return 1; }
        [ "$directory" = / ] && break
        directory=${directory%/*}
        [ -n "$directory" ] || directory=/
    done
}
regular_root() {
    [ -f "$1" ] && [ ! -L "$1" ] || { mark unsafe_file; return 1; }
    canonical=$("$BB" readlink -f "$1") || return 1
    [ "$canonical" = "$1" ] && root_owned "$1" || return 1
    metadata=$("$BB" stat -t "$1") || return 1
    set -- $metadata
    mode=$((0x$4))
    [ $((mode & 18)) = 0 ] || { mark writable_file; return 1; }
}
secure_directory() {
    directory_chain "$1" || return 1
    metadata=$("$BB" stat -t "$1") || return 1
    set -- $metadata
    mode=$((0x$4))
    [ $((mode & 18)) = 0 ] || { mark writable_directory; return 1; }
}
hash_file() {
    file=$1
    expected_hash=$2
    regular_root "$file" || return 1
    metadata=$("$BB" stat -t "$file") || return 1
    set -- $metadata
    [ "$2" -le 65536 ] || { mark payload_oversized; return 1; }
    result=$("$BB" sha256sum "$file") || return 1
    [ "${result%% *}" = "$expected_hash" ] || { mark payload_hash_mismatch; return 1; }
}
guard_data() {
    directory_chain /data || return 1
    found=0
    while read -r source target filesystem options rest; do
        case "$target" in
            /data/ubuntu-touch-graphics-permissions-1|/data/ubuntu-touch-graphics-permissions-1/*|/data/system-data|/data/system-data/etc|/data/system-data/etc/systemd|/data/system-data/etc/systemd/*|/data/system-data/etc/udev|/data/system-data/etc/udev/*)
                mark nested_mount_in_probe_scope; return 1 ;;
        esac
        [ "$target" = /data ] || continue
        found=$((found + 1))
        [ "$filesystem" = ext4 ] || { mark data_not_ext4; return 1; }
        canonical=$("$BB" readlink -f "$source") || return 1
        case "$canonical" in /dev/block/sda31|/dev/sda31) ;; *) mark data_not_raw_userdata; return 1 ;; esac
        if [ "$WRITES" = yes ]; then
            case ",$options," in *,rw,*) ;; *) mark data_not_writable; return 1 ;; esac
        fi
    done </proc/mounts
    [ "$found" = 1 ] || { mark ambiguous_data; return 1; }
}
guard_data || exit 33
'''


def validate_payload(root):
    if set(PAYLOAD_SHA256) != set(ASSET_NAMES):
        raise ValueError('payload_pins_unavailable')
    result = {}
    for name in ASSET_NAMES:
        path = Path(root) / 'graphics-permissions-1' / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError('local_payload_unavailable')
        value = path.read_bytes()
        if hashlib.sha256(value).hexdigest() != PAYLOAD_SHA256[name]:
            raise ValueError('local_payload_hash_mismatch')
        result[name] = value
    return result


def parent_checks(allow_missing=False):
    script = 'directory_chain /data/system-data/etc || exit 34\n'
    for directory in PARENT_DIRECTORIES:
        check = 'directory_chain ' + directory + ' || exit 34\n'
        script += ('if exists ' + directory + '; then\n' + check + 'fi\n') if allow_missing else check
    return script


def installed_checks(allow_missing=False):
    paths = [(BASE + '/assets/' + n, PAYLOAD_SHA256[n]) for n in ASSET_NAMES]
    paths += [(path, PAYLOAD_SHA256[name]) for name, path in DESTINATIONS.items()]
    script = ''
    for directory in (BASE, BASE + '/assets'):
        check = 'directory_chain ' + directory + ' || exit 34\n'
        script += ('if exists ' + directory + '; then\n' + check + 'fi\n') if allow_missing else check
    for path, digest in paths:
        check = 'hash_file ' + path + ' ' + digest + ' || exit 35\n'
        script += ('if exists ' + path + '; then\n' + check + 'fi\n') if allow_missing else check
    return script


def script_for(operation, payload=None):
    if operation not in ('data-state', 'apply', 'remove', *('log:' + n for n in LOG_NAMES)):
        raise ValueError('permissions_operation_not_allowed')
    script = 'WRITES=' + ('yes' if operation in ('apply', 'remove') else 'no') + '\n' + SHELL_COMMON
    if operation == 'data-state':
        return script + "printf 'UT_GRAPHICS_PERMISSIONS_1: data_ready=raw_ext4\n'\n"
    if set(PAYLOAD_SHA256) != set(ASSET_NAMES):
        raise ValueError('payload_pins_unavailable')
    if operation.startswith('log:'):
        script += parent_checks() + installed_checks()
        script += 'directory_chain "$BASE/logs" || exit 44\n'
        script += 'path="$BASE/logs/' + operation[4:] + '"\n'
        script += 'exists "$path" || exit 44\nregular_root "$path" || exit 35\n'
        return script + '"$BB" tail -c ' + str(LOG_BYTES) + ' "$path"\n'
    if operation == 'remove':
        # All present members must match before the activating drop-in is
        # removed. Missing members are permitted after a partial operation.
        script += parent_checks(allow_missing=True) + installed_checks(allow_missing=True)
        remove_paths = [DESTINATIONS[DROPIN_NAME]]
        remove_paths += [p for n, p in DESTINATIONS.items() if n != DROPIN_NAME]
        remove_paths += [BASE + '/assets/' + n for n in ASSET_NAMES]
        for path in remove_paths:
            script += 'if exists ' + path + '; then "$BB" rm ' + path + ' || exit 38; fi\n'
        script += '"$BB" rmdir "$BASE/assets" 2>/dev/null || :\n'
        script += '"$BB" rmdir "$BASE" 2>/dev/null || :\n'
        return script + "printf 'UT_GRAPHICS_PERMISSIONS_1: removed_reboot_restores_defaults\n'\n"
    if payload is None or set(payload) != set(ASSET_NAMES) or any(
            hashlib.sha256(payload[n]).hexdigest() != PAYLOAD_SHA256[n] for n in ASSET_NAMES):
        raise ValueError('local_payload_hash_mismatch')
    existing = ['"$BASE"', *DESTINATIONS.values()]
    script += 'if ' + ' || '.join('exists ' + p for p in existing) + '; then\n'
    script += parent_checks() + installed_checks()
    script += "printf 'UT_GRAPHICS_PERMISSIONS_1: already_applied_no_changes\n'; exit 0\nfi\n"
    script += 'umask 022\nmade_base=no\n'
    for index in range(len(PARENT_DIRECTORIES)):
        script += 'made_parent_' + str(index) + '=no\n'
    for index in range(len(DESTINATIONS)):
        script += 'made_target_' + str(index) + '=no\n'
    script += 'cleanup() {\n'
    # Cleanup uses only our exact expected files and never recursively walks
    # userdata. It cannot remove a conflicting target, even if creation failed.
    for index, (name, path) in reversed(list(enumerate(DESTINATIONS.items()))):
        script += 'if [ "$made_target_' + str(index) + '" = yes ] && hash_file ' + path + ' ' + PAYLOAD_SHA256[name] + '; then "$BB" rm ' + path + '; fi\n'
    script += 'if [ "$made_base" = yes ]; then\n'
    for name in ASSET_NAMES:
        script += '"$BB" rm "$BASE/assets/' + name + '" 2>/dev/null || :\n'
    script += '"$BB" rmdir "$BASE/assets" 2>/dev/null || :\n"$BB" rmdir "$BASE" 2>/dev/null || :\nfi\n'
    for index, directory in reversed(list(enumerate(PARENT_DIRECTORIES))):
        script += '[ "$made_parent_' + str(index) + '" != yes ] || "$BB" rmdir ' + directory + ' 2>/dev/null || :\n'
    script += "}\ntrap 'cleanup' 0\ntrap 'exit 39' 1 2 15\n"
    script += 'secure_directory /data/system-data/etc || exit 34\n'
    for index, directory in enumerate(PARENT_DIRECTORIES):
        script += 'if exists ' + directory + '; then secure_directory ' + directory + ' || exit 34\nelse\n'
        script += '"$BB" mkdir ' + directory + ' || exit 38\nmade_parent_' + str(index) + '=yes\n'
        script += '"$BB" chmod 0755 ' + directory + ' || exit 38\nfi\n'
    script += '"$BB" mkdir "$BASE" || exit 38\nmade_base=yes\n"$BB" chmod 0755 "$BASE" || exit 38\n'
    script += '"$BB" mkdir "$BASE/assets" && "$BB" chmod 0755 "$BASE/assets" || exit 38\n'
    for name in ASSET_NAMES:
        target = '"$BASE/assets/' + name + '"'
        script += '"$BB" base64 -d >' + target + " <<'UT_PERMISSIONS_PAYLOAD'\n"
        script += base64.b64encode(payload[name]).decode('ascii') + '\nUT_PERMISSIONS_PAYLOAD\n'
        script += '[ "$?" = 0 ] || exit 38\n"$BB" chmod 0644 ' + target + ' || exit 38\n'
        script += 'hash_file ' + target + ' ' + PAYLOAD_SHA256[name] + ' || exit 35\n'
    # Exact same-filesystem hard links publish verified payloads atomically.
    # The LightDM dependency drop-in is the final write, after the script,
    # service and udev rule have all been stored and verified.
    for index, (name, path) in enumerate(DESTINATIONS.items()):
        script += 'made_target_' + str(index) + '=yes\n'
        script += '"$BB" ln "$BASE/assets/' + name + '" ' + path + ' || exit 38\n'
    script += 'trap - 0 1 2 15\n'
    return script + "printf 'UT_GRAPHICS_PERMISSIONS_1: applied_for_next_ubuntu_boot\n'\n"


def output_limit(name):
    return LOG_BYTES * 2 if name.startswith(('log:', 'retained:')) else 65536


def run_query(executable, name, payload=None):
    if name.startswith('retained:'):
        key = name.split(':', 1)[1]
        if key not in RETAINED_LOGS:
            raise ValueError('permissions_operation_not_allowed')
        return graphics.run_query(executable, key)
    if name in IDENTITY_QUERIES[:-1]:
        arguments = legacy.command_for(name) if name != 'boot-hash' else [
            '-d', 'shell', '/sbin/busybox head -c ' + str(BOOT_BYTES) +
            ' /dev/block/sda14 | /sbin/busybox sha256sum']
        stdin = None
    else:
        arguments = ['-d', 'shell', '/sbin/busybox sh -s']
        stdin = script_for(name, payload).encode('ascii')
    try:
        result = subprocess.run([str(executable), *arguments], input=stdin, capture_output=True,
            timeout=90 if name.endswith('-hash') else 60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if len(result.stdout) > output_limit(name) or len(result.stderr) > 32768:
            return {'exit_code': None, 'timed_out': False, 'stdout': '', 'stderr': 'output_limit',
                    'raw_stdout_bytes': len(result.stdout)}
        return {'exit_code': result.returncode, 'timed_out': False,
                'stdout': result.stdout.decode('utf-8', 'replace'),
                'stderr': result.stderr.decode('utf-8', 'replace'), 'raw_stdout_bytes': len(result.stdout)}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'timed_out': True, 'stdout': '', 'stderr': 'operation_timeout'}


def manage(root, operation, runner=run_query, verifier=legacy.check_tools):
    root = Path(root).resolve()
    if operation not in ('apply', 'read', 'remove'):
        raise ValueError('permissions_operation_not_allowed')
    report = {'schema': 1, 'correction_version': 1, 'boot_version': 6, 'operation': operation,
              'date_utc': datetime.now(timezone.utc).isoformat(), 'success': False, 'error': None,
              'partition_writes': False, 'raw_partition_writes': False,
              'mount_changes_requested': False, 'reboot_requested': False, 'data_format_requested': False,
              'phone_file_changes_requested': operation in ('apply', 'remove'),
              'phone_file_changes_state': 'not_attempted',
              'phone_write_scope': 'fixed graphics permission configuration and assets in userdata only',
              'system_or_vendor_images_changed': False,
              'runtime_graphics_permission_correction_requested': operation == 'apply',
              'ubuntu_touch_graphical_boot_verified': False, 'adb_usb_only': True,
              'steps': [], 'image_checks': {}, 'logs': {},
              'own_log_tail_limit_bytes': LOG_BYTES, 'adb_text_expansion_allowance': 2,
              'note': 'Applying stores a persistent correction for hwbinder/ion permissions on the next '
                      'normal Ubuntu boot. TWRP device permissions are not changed. Removing disables '
                      'the correction for the next boot and retains logs. No operation confirms a graphical boot.'}
    files = {}
    reason = 'local_tools_unavailable'
    def query(name, payload=None):
        result = dict(runner(root / 'platform-tools/adb.exe', name, payload))
        report['steps'].append({'name': name, 'exit_code': result.get('exit_code'),
            'timed_out': result.get('timed_out', False), 'raw_stdout_bytes': result.get('raw_stdout_bytes'),
            'stderr': legacy.redact(result.get('stderr', ''), root)[:32768]})
        if (result.get('timed_out') or result.get('exit_code') != 0 or
                not isinstance(result.get('stdout'), str) or len(result['stdout']) > output_limit(name) or
                result.get('raw_stdout_bytes', 0) > output_limit(name)):
            raise ValueError(reason)
        return result['stdout']
    try:
        verifier(root)
        payload = validate_payload(root)
        report['local_payload_sha256'] = dict(PAYLOAD_SHA256)
        reason = 'recovery_identity_unavailable'
        if 'Version 37.0.1' not in query('version'):
            raise ValueError('adb_version_mismatch')
        if query('state').strip() != 'recovery' or query('uid').strip() != '0':
            raise ValueError(reason)
        props = dict(line.split('|', 1) for line in query('properties').splitlines() if '|' in line)
        report['properties'] = {key: value[:256] for key, value in props.items() if key in legacy.PROPERTIES}
        if (props.get('ro.product.model') not in ('Galaxy S10+', 'SM-G975F') or
                props.get('ro.product.device') not in ('beyond2', 'beyond2lte') or
                props.get('ro.hardware') != 'exynos9820' or
                props.get('ro.twrp.version') not in ('3.7.0_9', '3.7.0_9-2') or
                'G975FXXSGHWC1' not in (props.get('ro.bootloader'), props.get('ro.boot.bootloader'))):
            raise ValueError(reason)
        for name, expected in (('recovery-hash', legacy.EXPECTED_HASHES['recovery-hash']), ('boot-hash', BOOT_SHA256)):
            match = re.fullmatch(r'([a-f0-9]{64})\s+-?', query(name).strip())
            report['image_checks'][name] = {'sha256': match[1] if match else None,
                                           'matches_expected': bool(match and match[1] == expected)}
            if not match or match[1] != expected:
                raise ValueError('image_identity_mismatch')
        reason = 'raw_userdata_unavailable'
        if query('data-state').strip() != 'UT_GRAPHICS_PERMISSIONS_1: data_ready=raw_ext4':
            raise ValueError(reason)
        reason = 'permissions_operation_failed'
        if operation == 'read':
            own_collected = 0
            for name in [*('log:' + n for n in LOG_NAMES), *('retained:' + n for n in RETAINED_LOGS)]:
                filename = name[4:] if name.startswith('log:') else 'retained-' + name.split(':', 1)[1] + '.txt'
                try:
                    value = query(name)
                    files[filename] = legacy.redact(value, root)
                    report['logs'][name] = 'collected'
                    own_collected += int(name.startswith('log:'))
                except ValueError:
                    step = report['steps'][-1]
                    report['logs'][name] = 'missing' if step['exit_code'] == 44 else 'error'
            if any(value == 'error' for value in report['logs'].values()):
                raise ValueError('permissions_collection_incomplete')
            if not own_collected:
                raise ValueError('correction_runtime_logs_unavailable')
        else:
            report['phone_file_changes_state'] = 'operation_attempted_result_pending'
            result = query(operation, payload if operation == 'apply' else None).strip()
            allowed = ('UT_GRAPHICS_PERMISSIONS_1: applied_for_next_ubuntu_boot',
                       'UT_GRAPHICS_PERMISSIONS_1: already_applied_no_changes') if operation == 'apply' else (
                       'UT_GRAPHICS_PERMISSIONS_1: removed_reboot_restores_defaults',)
            if result not in allowed:
                raise ValueError('permissions_response_unexpected')
            report['result'] = result
            report['phone_file_changes_state'] = result.split(': ', 1)[1]
        report['success'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z_]+', str(error)) else reason
        if report['phone_file_changes_state'] == 'operation_attempted_result_pending':
            report['phone_file_changes_state'] = 'operation_failed_partial_changes_possible'
    path = root / ('ubuntu-graphics-permissions-1-' + operation + '-report.zip')
    number = 1
    while path.exists():
        path = root / ('ubuntu-graphics-permissions-1-' + operation + '-report-' + str(number) + '.zip')
        number += 1
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr('ubuntu-graphics-permissions-report.json', json.dumps(report, indent=2))
    print('Operazione completata.' if report['success'] else 'Operazione fermata: ' + str(report['error']), flush=True)
    if report['success'] and operation == 'apply':
        print('Ora in TWRP: Reboot > System. Attendi 4 minuti e controlla se appare la schermata iniziale.', flush=True)
        print('Per leggere il risultato, torna in TWRP e usa LEGGI-CORREZIONE-GRAFICA-1.cmd.', flush=True)
    print('Invia questo rapporto: ' + str(path), flush=True)
    return report, path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--operation', choices=('apply', 'read', 'remove'), required=True)
    args = parser.parse_args()
    report, _ = manage(args.root, args.operation)
    raise SystemExit(0 if report['success'] else 1)
