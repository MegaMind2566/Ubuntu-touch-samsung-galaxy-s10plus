"""Manage the one-shot BOOT 6 graphics probe from the prepared Windows folder.

Only fixed files on already mounted raw userdata are written. Every operation
rechecks the pinned tools, root TWRP, handset, RECOVERY and installed BOOT 6.
No partition, mount, kernel, device permission or reboot change is requested.
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

SPEC = importlib.util.spec_from_file_location('probe_first_boot_helpers',
    Path(__file__).with_name('collect-first-boot.py'))
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
BOOT_BYTES = 57344000
BOOT_SHA256 = '2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad'
BASE = '/data/ubuntu-touch-graphics-probe-1'
UNIT = '/data/system-data/etc/systemd/system/ubuntu-touch-graphics-probe.service'
LINK = '/data/system-data/etc/systemd/system/multi-user.target.wants/ubuntu-touch-graphics-probe.service'
LINK_TARGET = '../ubuntu-touch-graphics-probe.service'
ARMED = b'UT_GRAPHICS_PROBE_1_ARMED\n'
ASSET_NAMES = ('probe.sh', 'mapper-probe.py', 'ubuntu-touch-graphics-probe.service')
# Frozen payload identities are filled after the runtime review; an empty pin
# never permits preparation, reading, or removal on a handset.
PAYLOAD_SHA256 = {
    'probe.sh': 'ba6b32d1a064658b7531bf45e07b0c3364bf3b84e37f22b257567a34278abc8b',
    'mapper-probe.py': 'e3ea2b3e551cf7f5a2d7622badba45d91ba8d6d37e0278a4bfa26025f2ce282f',
    'ubuntu-touch-graphics-probe.service': '3be86a804d7339c1dfa42cf24f4add499a77f292c8ef2c32a78c70ac57e5633c',
}
LOG_BYTES = 524288
LOG_NAMES = ('01-summary.txt', '02-inventory-start.json', '03-systemd.txt',
             '04-android-before.txt', '05-root-probe.txt', '06-phablet-probe.txt',
             '07-lightdm-probe.txt', '08-android-after.txt', '09-inventory-end.json',
             '10-journal.txt', '11-complete.txt')
IDENTITY_QUERIES = ('version', 'state', 'uid', 'properties', 'recovery-hash', 'boot-hash', 'data-state')

SHELL_COMMON = r'''#!/bin/sh
BB=/sbin/busybox
BASE=/data/ubuntu-touch-graphics-probe-1
UNIT=/data/system-data/etc/systemd/system/ubuntu-touch-graphics-probe.service
LINK=/data/system-data/etc/systemd/system/multi-user.target.wants/ubuntu-touch-graphics-probe.service
mark() { printf 'UT_GRAPHICS_PROBE_1: %s\n' "$*" >&2; }
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
            /data/ubuntu-touch-graphics-probe-1|/data/ubuntu-touch-graphics-probe-1/*|/data/system-data|/data/system-data/etc|/data/system-data/etc/systemd|/data/system-data/etc/systemd/*)
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
        path = Path(root) / 'graphics-probe-1' / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            raise ValueError('local_payload_unavailable')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != PAYLOAD_SHA256[name]:
            raise ValueError('local_payload_hash_mismatch')
        result[name] = data
    return result


def checks_for_installed():
    script = 'directory_chain "$BASE/assets" || exit 34\n'
    for name in ASSET_NAMES[:2]:
        script += 'hash_file "$BASE/assets/' + name + '" ' + PAYLOAD_SHA256[name] + ' || exit 35\n'
    script += 'hash_file "$UNIT" ' + PAYLOAD_SHA256[ASSET_NAMES[2]] + ' || exit 35\n'
    script += '[ -L "$LINK" ] && root_owned "$LINK" && [ "$("$BB" readlink "$LINK")" = ../ubuntu-touch-graphics-probe.service ] || exit 36\n'
    script += 'if exists "$BASE/armed"; then hash_file "$BASE/armed" ' + hashlib.sha256(ARMED).hexdigest() + ' || exit 35; fi\n'
    return script


def checks_for_removal():
    # Missing members are allowed after an interrupted preparation/removal.
    # Every member that exists is checked before the first unlink, including
    # the one bounded staging name used by preparation. Unknown files remain.
    script = 'if exists "$BASE"; then directory_chain "$BASE" || exit 34; fi\n'
    script += 'if exists "$BASE/assets"; then directory_chain "$BASE/assets" || exit 34; fi\n'
    for name in ASSET_NAMES[:2]:
        path = '"$BASE/assets/' + name + '"'
        script += 'if exists ' + path + '; then hash_file ' + path + ' ' + PAYLOAD_SHA256[name] + ' || exit 35; fi\n'
    for path in ('"$UNIT"', '"$BASE/unit.stage"'):
        script += 'if exists ' + path + '; then hash_file ' + path + ' ' + PAYLOAD_SHA256[ASSET_NAMES[2]] + ' || exit 35; fi\n'
    script += 'if exists "$LINK"; then [ -L "$LINK" ] && root_owned "$LINK" && [ "$("$BB" readlink "$LINK")" = ../ubuntu-touch-graphics-probe.service ] || exit 36; fi\n'
    script += 'if exists "$BASE/armed"; then hash_file "$BASE/armed" ' + hashlib.sha256(ARMED).hexdigest() + ' || exit 35; fi\n'
    return script


def script_for(operation, payload=None):
    if operation not in ('data-state', 'prepare', 'remove', *('log:' + n for n in LOG_NAMES)):
        raise ValueError('probe_operation_not_allowed')
    writes = operation in ('prepare', 'remove')
    script = 'WRITES=' + ('yes' if writes else 'no') + '\n' + SHELL_COMMON
    if operation == 'data-state':
        return script + "printf 'UT_GRAPHICS_PROBE_1: data_ready=raw_ext4\n'\n"
    if set(PAYLOAD_SHA256) != set(ASSET_NAMES):
        raise ValueError('payload_pins_unavailable')
    script += 'UNIT_SHA=' + PAYLOAD_SHA256[ASSET_NAMES[2]] + '\n'
    if operation.startswith('log:'):
        script += 'directory_chain "${UNIT%/*}" && directory_chain "${LINK%/*}" || exit 34\n'
    elif operation == 'remove':
        script += 'directory_chain /data/system-data/etc || exit 34\n'
        script += 'for directory in /data/system-data/etc/systemd /data/system-data/etc/systemd/system /data/system-data/etc/systemd/system/multi-user.target.wants; do if exists "$directory"; then directory_chain "$directory" || exit 34; fi; done\n'
    if operation.startswith('log:'):
        name = operation[4:]
        script += checks_for_installed()
        script += 'directory_chain "$BASE/run-1" || exit 44\n'
        script += 'path="$BASE/run-1/' + name + '"\n'
        script += 'exists "$path" || exit 44\nregular_root "$path" || exit 35\n'
        return script + '"$BB" tail -c ' + str(LOG_BYTES) + ' "$path"\n'
    if operation == 'remove':
        script += checks_for_removal()
        # Validate every identity before the first removal. Do not traverse logs.
        script += 'if exists "$LINK"; then "$BB" rm "$LINK" || exit 38; fi\n'
        script += 'if exists "$UNIT"; then "$BB" rm "$UNIT" || exit 38; fi\n'
        for name in ASSET_NAMES[:2]:
            script += 'if exists "$BASE/assets/' + name + '"; then "$BB" rm "$BASE/assets/' + name + '" || exit 38; fi\n'
        script += 'if exists "$BASE/armed"; then "$BB" rm "$BASE/armed" || exit 38; fi\n'
        script += 'if exists "$BASE/unit.stage"; then "$BB" rm "$BASE/unit.stage" || exit 38; fi\n'
        script += '"$BB" rmdir "$BASE/assets" 2>/dev/null || :\n'
        script += '"$BB" rmdir "$BASE" 2>/dev/null || :\n'
        return script + "printf 'UT_GRAPHICS_PROBE_1: removed_logs_retained\n'\n"
    if payload is None or set(payload) != set(ASSET_NAMES) or any(
            hashlib.sha256(payload[n]).hexdigest() != PAYLOAD_SHA256[n] for n in ASSET_NAMES):
        raise ValueError('local_payload_hash_mismatch')
    # Complete matching installations are idempotent, even after armed has
    # been consumed. They are never silently rearmed or overwritten.
    script += 'if exists "$BASE" || exists "$UNIT" || exists "$LINK"; then\n'
    script += 'directory_chain "${UNIT%/*}" && directory_chain "${LINK%/*}" || exit 34\n'
    script += checks_for_installed()
    script += "printf 'UT_GRAPHICS_PROBE_1: already_prepared_no_changes\n'; exit 0\nfi\n"
    script += r'''
umask 022
made_base=no
made_unit=no
made_link=no
made_systemd=no
made_system=no
made_wants=no
cleanup() {
    if [ "$made_link" = yes ] && [ -L "$LINK" ] && root_owned "$LINK" &&
       [ "$("$BB" readlink "$LINK")" = ../ubuntu-touch-graphics-probe.service ]; then
        "$BB" rm "$LINK"
    fi
    if [ "$made_unit" = yes ] && [ -f "$UNIT" ] && [ ! -L "$UNIT" ]; then
        candidate=$("$BB" sha256sum "$UNIT")
        [ "${candidate%% *}" != "$UNIT_SHA" ] || "$BB" rm "$UNIT"
    fi
    if [ "$made_base" = yes ]; then
        for own in probe.sh mapper-probe.py; do
            "$BB" rm "$BASE/assets/$own" 2>/dev/null || :
        done
        "$BB" rm "$BASE/armed" 2>/dev/null || :
        "$BB" rm "$BASE/unit.stage" 2>/dev/null || :
        "$BB" rmdir "$BASE/assets" 2>/dev/null || :
        "$BB" rmdir "$BASE" 2>/dev/null || :
    fi
    [ "$made_wants" != yes ] || "$BB" rmdir /data/system-data/etc/systemd/system/multi-user.target.wants 2>/dev/null || :
    [ "$made_system" != yes ] || "$BB" rmdir /data/system-data/etc/systemd/system 2>/dev/null || :
    [ "$made_systemd" != yes ] || "$BB" rmdir /data/system-data/etc/systemd 2>/dev/null || :
}
trap 'cleanup' 0
trap 'exit 39' 1 2 15
secure_directory /data/system-data/etc || exit 34
for directory in /data/system-data/etc/systemd /data/system-data/etc/systemd/system /data/system-data/etc/systemd/system/multi-user.target.wants; do
    if exists "$directory"; then
        secure_directory "$directory" || exit 34
    else
        "$BB" mkdir "$directory" || exit 38
        case "$directory" in
            /data/system-data/etc/systemd) made_systemd=yes ;;
            /data/system-data/etc/systemd/system) made_system=yes ;;
            /data/system-data/etc/systemd/system/multi-user.target.wants) made_wants=yes ;;
        esac
        "$BB" chmod 0755 "$directory" || exit 38
    fi
done
"$BB" mkdir "$BASE" || exit 38
made_base=yes
"$BB" chmod 0755 "$BASE" || exit 38
"$BB" mkdir "$BASE/assets" && "$BB" chmod 0755 "$BASE/assets" || exit 38
'''
    for name in ASSET_NAMES:
        target = '"$BASE/unit.stage"' if name.endswith('.service') else '"$BASE/assets/' + name + '"'
        # The local validated payload becomes only base64 data to a fixed
        # decoder; it is never interpolated as shell or executed in recovery.
        script += "\"$BB\" base64 -d >" + target + " <<'UT_PAYLOAD_DATA'\n"
        script += base64.b64encode(payload[name]).decode('ascii') + '\nUT_PAYLOAD_DATA\n'
        script += '[ "$?" = 0 ] || exit 38\n"$BB" chmod 0644 ' + target + ' || exit 38\n'
        script += 'hash_file ' + target + ' ' + PAYLOAD_SHA256[name] + ' || exit 35\n'
    script += 'umask 077\nprintf \'UT_GRAPHICS_PROBE_1_ARMED\\n\' >"$BASE/armed" || exit 38\n'
    script += 'hash_file "$BASE/armed" ' + hashlib.sha256(ARMED).hexdigest() + ' || exit 35\n'
    script += 'made_unit=yes\n"$BB" ln "$BASE/unit.stage" "$UNIT" || exit 38\n'
    script += '"$BB" rm "$BASE/unit.stage" || exit 38\n'
    # Enabling is the last write. An interrupted preparation cannot enable
    # a partial payload, and the unit is inactive until a normal Ubuntu boot.
    script += 'made_link=yes\n"$BB" ln -s ../ubuntu-touch-graphics-probe.service "$LINK" || exit 38\n'
    script += 'trap - 0 1 2 15\n'
    return script + "printf 'UT_GRAPHICS_PROBE_1: prepared_one_shot\n'\n"


def run_query(executable, name, payload=None):
    if name in IDENTITY_QUERIES[:-1]:
        arguments = legacy.command_for(name) if name != 'boot-hash' else [
            '-d', 'shell', '/sbin/busybox head -c ' + str(BOOT_BYTES) +
            ' /dev/block/sda14 | /sbin/busybox sha256sum']
        stdin = None
    else:
        arguments = ['-d', 'shell', '/sbin/busybox sh -s']
        stdin = script_for(name, payload).encode('ascii')
    limit = LOG_BYTES * 2 if name.startswith('log:') else 65536
    try:
        result = subprocess.run([str(executable), *arguments], input=stdin, capture_output=True,
            timeout=90 if name.endswith('-hash') else 60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if len(result.stdout) > limit or len(result.stderr) > 32768:
            return {'exit_code': None, 'timed_out': False, 'stdout': '', 'stderr': 'output_limit',
                    'raw_stdout_bytes': len(result.stdout)}
        return {'exit_code': result.returncode, 'timed_out': False,
                'stdout': result.stdout.decode('utf-8', 'replace'),
                'stderr': result.stderr.decode('utf-8', 'replace'), 'raw_stdout_bytes': len(result.stdout)}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'timed_out': True, 'stdout': '', 'stderr': 'operation_timeout'}


def manage(root, operation, runner=run_query, verifier=legacy.check_tools):
    root = Path(root).resolve()
    if operation not in ('prepare', 'read', 'remove'):
        raise ValueError('probe_operation_not_allowed')
    report = {'schema': 1, 'probe_version': 1, 'boot_version': 6, 'operation': operation,
              'date_utc': datetime.now(timezone.utc).isoformat(), 'success': False, 'error': None,
              'partition_writes': False, 'mount_changes_requested': False, 'reboot_requested': False,
              'data_format_requested': False, 'phone_files_written': operation in ('prepare', 'remove'),
              'phone_file_changes_requested': operation in ('prepare', 'remove'),
              'phone_file_changes_state': 'not_attempted',
              'phone_write_scope': 'fixed graphics probe files in userdata only',
              'raw_partition_writes': False, 'system_or_vendor_images_changed': False,
              'ubuntu_systemd_config_changed_in_userdata': operation in ('prepare', 'remove'),
              'ubuntu_touch_graphical_boot_verified': False,
              'adb_usb_only': True, 'steps': [], 'image_checks': {}, 'logs': {},
              'note': 'Preparing enables a single bounded diagnostic on the next Ubuntu boot. '
                      'Reading uses fixed logs only; removal disables the probe and retains its logs. '
                      'No operation confirms a graphical Ubuntu Touch boot.'}
    files = {}
    reason = 'local_tools_unavailable'
    def query(name, payload=None):
        result = runner(root / 'platform-tools/adb.exe', name, payload)
        result = dict(result)
        report['steps'].append({'name': name, 'exit_code': result.get('exit_code'),
            'timed_out': result.get('timed_out', False), 'stderr': legacy.redact(result.get('stderr', ''), root)[:32768]})
        if (result.get('timed_out') or result.get('exit_code') != 0 or
                not isinstance(result.get('stdout'), str) or len(result['stdout']) >
                (LOG_BYTES * 2 if name.startswith('log:') else 65536) or
                result.get('raw_stdout_bytes', 0) > (LOG_BYTES * 2 if name.startswith('log:') else 65536)):
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
        if query('data-state').strip() != 'UT_GRAPHICS_PROBE_1: data_ready=raw_ext4':
            raise ValueError(reason)
        reason = 'probe_operation_failed'
        if operation == 'read':
            for name in LOG_NAMES:
                try:
                    value = query('log:' + name)
                    files[name] = legacy.redact(value, root)
                    report['logs'][name] = 'collected'
                except ValueError:
                    step = report['steps'][-1]
                    report['logs'][name] = 'missing' if step['exit_code'] == 44 else 'error'
            if any(value == 'error' for value in report['logs'].values()):
                raise ValueError('probe_collection_incomplete')
            if not files:
                raise ValueError('probe_logs_unavailable')
        else:
            report['phone_file_changes_state'] = 'operation_attempted_result_pending'
            result = query(operation, payload if operation == 'prepare' else None).strip()
            allowed = ('UT_GRAPHICS_PROBE_1: prepared_one_shot', 'UT_GRAPHICS_PROBE_1: already_prepared_no_changes') if operation == 'prepare' else ('UT_GRAPHICS_PROBE_1: removed_logs_retained',)
            if result not in allowed:
                raise ValueError('probe_response_unexpected')
            report['result'] = result
            report['phone_file_changes_state'] = result.split(': ', 1)[1]
        report['success'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z_]+', str(error)) else reason
        if report['phone_file_changes_state'] == 'operation_attempted_result_pending':
            report['phone_file_changes_state'] = 'operation_failed_partial_changes_possible'
    path = root / ('ubuntu-graphics-probe-1-' + operation + '-report.zip')
    number = 1
    while path.exists():
        path = root / ('ubuntu-graphics-probe-1-' + operation + '-report-' + str(number) + '.zip')
        number += 1
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr('ubuntu-graphics-probe-report.json', json.dumps(report, indent=2))
    print('Operazione completata.' if report['success'] else 'Operazione fermata: ' + str(report['error']), flush=True)
    if report['success'] and operation == 'prepare':
        print('Ora in TWRP: Reboot > System. Attendi 4 minuti. Torna in TWRP e usa LEGGI-TEST-GRAFICA-1.cmd.', flush=True)
    print('Invia questo rapporto: ' + str(path), flush=True)
    return report, path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--operation', choices=('prepare', 'read', 'remove'), required=True)
    args = parser.parse_args()
    report, _ = manage(args.root, args.operation)
    raise SystemExit(0 if report['success'] else 1)
