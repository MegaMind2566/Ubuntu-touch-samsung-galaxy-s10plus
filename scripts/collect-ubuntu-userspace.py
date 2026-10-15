"""Inspect the BOOT 4 handoff from TWRP without flashing or running SYSTEM code."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zipfile

SPEC = importlib.util.spec_from_file_location('first_boot_helpers', Path(__file__).with_name('collect-first-boot.py'))
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
BOOT_BYTES = 57337856
BOOT_SHA256 = 'f9264d385d4915157fbc16562683df7bdc0fad1517d55962884e194d1c5db3df'
BB = '/sbin/busybox '
HEAD_BYTES = 8388608
USER_LOGS = {'syslog': 'syslog', 'boot': 'boot.log', 'lightdm': 'lightdm/lightdm.log',
             'lomiri': 'lomiri/lomiri.log', 'android': 'lxc/android.log'}
SHELL = Path(__file__).with_name('inspect-ubuntu-userspace.sh')


def command_for(name):
    if name == 'boot-hash':
        return ['-d', 'shell', BB + 'head -c ' + str(BOOT_BYTES) + ' /dev/block/sda14 | ' + BB + 'sha256sum']
    if name == 'last-kmsg-size':
        return ['-d', 'shell', 'test -f /proc/last_kmsg && ' + BB + 'wc -c </proc/last_kmsg']
    if name == 'last-kmsg-head':
        return ['-d', 'shell', 'test -f /proc/last_kmsg && ' + BB + 'head -c ' + str(HEAD_BYTES) + ' /proc/last_kmsg']
    if name == 'last-kmsg-tail':
        return ['-d', 'shell', 'test -f /proc/last_kmsg && ' + BB + 'tail -c 1048576 /proc/last_kmsg']
    if name == 'system-inspection':
        return ['-d', 'shell', '/sbin/busybox sh -s']
    match = re.fullmatch(r'run-([1-5])-stage', name)
    if match:
        path = '/data/ubuntu-touch-boot-4/run-' + match[1] + '/stage.txt'
        return ['-d', 'shell', "p='" + path + "'; r=$(/sbin/busybox readlink -f \"$p\"); "
                'test "$r" = "$p" && test -f "$p" && /sbin/busybox head -c 65536 "$p"']
    if name in USER_LOGS:
        path = '/data/system-data/var/log/' + USER_LOGS[name]
        return ['-d', 'shell', "p='" + path + "'; r=$(/sbin/busybox readlink -f \"$p\"); "
                'test "$r" = "$p" && test -f "$p" && /sbin/busybox tail -c 524288 "$p"']
    if name == 'journal-inventory':
        return ['-d', 'shell', "p=/data/system-data/var/log/journal; r=$(/sbin/busybox readlink -f \"$p\"); "
                'test "$r" = "$p" && test -d "$p" && /sbin/busybox find "$p" -maxdepth 2 -type f '
                '-name "*.journal*" -exec /sbin/busybox stat -c "%s %n" {} \\; | /sbin/busybox head -c 32768']
    if name in ('version', 'state', 'uid', 'properties', 'recovery-hash', 'vbmeta-hash',
                'mounts', 'recovery-kernel', 'recovery-cmdline', 'reset-reason', 'pstore-list'):
        return legacy.command_for(name)
    if name.startswith('pstore:') and legacy.PSTORE_NAME.fullmatch(name[7:]):
        return legacy.command_for(name)
    raise ValueError('userspace_query_not_allowed')


def run_query(executable, name):
    arguments = command_for(name)
    payload = SHELL.read_bytes().replace(b'\r\n', b'\n') if name == 'system-inspection' else None
    try:
        result = subprocess.run([str(executable), *arguments], input=payload, capture_output=True,
                                timeout=55, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        limit = HEAD_BYTES if name == 'last-kmsg-head' else 1048576
        if len(result.stdout) > limit + 4096 or len(result.stderr) > 65536:
            return {'exit_code': None, 'timed_out': False, 'stdout': '', 'stderr': 'output_limit'}
        return {'exit_code': result.returncode, 'timed_out': False,
                'stdout': result.stdout.decode('utf-8', 'replace'),
                'stderr': result.stderr.decode('utf-8', 'replace'), 'raw_stdout_bytes': len(result.stdout)}
    except subprocess.TimeoutExpired:
        return {'exit_code': None, 'timed_out': True, 'stdout': '', 'stderr': 'read_timeout'}


def parse_inspection(text):
    markers = re.findall(r'^UT_INSPECT_4: ([a-z_]+)=(.*)$', text, re.M)
    values = {key: value.strip() for key, value in markers}
    return {'mount_requested': values.get('mount_requested') == 'true',
            'mount_options': values.get('mount_options'),
            'mount_verified_read_only': values.get('mount_verified_read_only') == 'true',
            'cleanup_confirmed': values.get('cleanup_confirmed') == 'true',
            'error': values.get('error'), 'status': values.get('status')}


def collect(root, runner=run_query, verifier=legacy.check_tools):
    root = Path(root).resolve()
    files = {}
    report = {'schema': 1, 'collector_version': 1, 'baseline_boot_version': 4,
              'date_utc': datetime.now(timezone.utc).isoformat(), 'success': False, 'error': None,
              'adb_usb_only': True, 'partition_writes': False, 'data_format_requested': False,
              'reboot_requested': False, 'system_code_executed': False,
              'temporary_read_only_system_mount_requested': False,
              'mount_options_requested': 'ro,noload,nosuid,nodev,noexec',
              'ubuntu_touch_boot_verified': False, 'steps': [], 'image_checks': {},
              'previous_boot': {'head_limit_bytes': HEAD_BYTES}, 'system_inspection': None}
    reason = 'local_tools_unavailable'

    def read(name, required=False):
        command_for(name)
        value = runner(root / 'platform-tools/adb.exe', name)
        report['steps'].append({'operation': name, 'exit_code': value['exit_code'],
                                'timed_out': value['timed_out'],
                                'raw_stdout_bytes': value.get('raw_stdout_bytes'),
                                'stderr': legacy.redact(value['stderr'][:4096], root)})
        # Keep partial inspection output: a failed mount or cleanup is evidence.
        if name == 'system-inspection':
            text = legacy.redact(value['stdout'], root)
            files['system-inspection.txt'] = text
            report['system_inspection'] = parse_inspection(text)
        if value['exit_code'] != 0 or value['timed_out']:
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
        if (props.get('ro.product.device') not in ('beyond2', 'beyond2lte') or
                props.get('ro.hardware') != 'exynos9820' or
                props.get('ro.twrp.version') not in ('3.7.0_9', '3.7.0_9-2') or
                'G975FXXSGHWC1' not in (props.get('ro.bootloader'), props.get('ro.boot.bootloader'))):
            raise ValueError(reason)
        report['recovery_confirmed'] = True
        print('Lettura estesa dei log conservati. Il telefono resta in TWRP.', flush=True)
        size = (read('last-kmsg-size') or '').strip()
        report['previous_boot']['source_bytes'] = int(size) if re.fullmatch(r'[0-9]{1,10}', size) else None
        for name in ('last-kmsg-head', 'last-kmsg-tail', 'reset-reason', 'recovery-kernel',
                     'recovery-cmdline', 'mounts', 'journal-inventory', *USER_LOGS):
            value = read(name)
            if value is not None:
                files[name + '.txt'] = value
        head_step = next(s for s in report['steps'] if s['operation'] == 'last-kmsg-head')
        source_bytes = report['previous_boot']['source_bytes']
        report['previous_boot']['head_contains_complete_source'] = (
            head_step['exit_code'] == 0 and source_bytes is not None and source_bytes <= HEAD_BYTES
            and head_step['raw_stdout_bytes'] == source_bytes)
        for run in range(1, 6):
            name = 'run-' + str(run) + '-stage'
            value = read(name)
            if value is not None:
                files[name + '.txt'] = value
        for name in sorted(set(n for n in (read('pstore-list') or '').splitlines()
                               if legacy.PSTORE_NAME.fullmatch(n)))[:16]:
            value = read('pstore:' + name)
            if value is not None:
                files['pstore-' + name + '.txt'] = value
        print('Verifica di BOOT 4, RECOVERY e VBMETA prima dell ispezione SYSTEM...', flush=True)
        expected = {'boot-hash': BOOT_SHA256, 'recovery-hash': legacy.EXPECTED_HASHES['recovery-hash'],
                    'vbmeta-hash': legacy.EXPECTED_HASHES['vbmeta-hash']}
        for name, pin in expected.items():
            reason = 'image_identity_unavailable'
            value = (read(name, True) or '').strip()
            match = re.fullmatch(r'([a-f0-9]{64})\s+-?', value)
            report['image_checks'][name] = {'sha256': match[1] if match else None,
                                           'matches_expected': bool(match and match[1] == pin)}
        if not all(v['matches_expected'] for v in report['image_checks'].values()):
            raise ValueError('image_identity_mismatch')
        print('Ispezione temporanea di SYSTEM in sola lettura, senza eseguire i suoi programmi...', flush=True)
        report['temporary_read_only_system_mount_requested'] = True
        reason = 'system_inspection_failed'
        value = read('system-inspection', True)
        inspection = report['system_inspection']
        if (inspection['status'] != 'complete' or not inspection['mount_verified_read_only']
                or not inspection['cleanup_confirmed'] or inspection['error']):
            raise ValueError('system_inspection_incomplete')
        report['success'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z_]+', str(error)) else reason
    report['note'] = ('Recovery metadata describes TWRP. The userspace-handoff marker precedes run-init; '
                      'neither this marker nor SYSTEM file inspection proves systemd or graphical execution. '
                      'A timeout may prevent confirming temporary-mount cleanup; read system_inspection.')
    path = root / 'ubuntu-userspace-4-report.zip'
    number = 1
    while path.exists():
        path = root / ('ubuntu-userspace-4-report-' + str(number) + '.zip')
        number += 1
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr('ubuntu-userspace-report.json', json.dumps(report, indent=2))
    print('Controllo completato.' if report['success'] else 'Controllo fermato: ' + str(report['error']))
    print('Invia questo rapporto: ' + str(path), flush=True)
    return report, path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    result, _ = collect(parser.parse_args().root)
    raise SystemExit(0 if result['success'] else 1)
