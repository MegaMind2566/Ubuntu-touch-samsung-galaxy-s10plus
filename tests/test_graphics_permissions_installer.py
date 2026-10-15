"""Exercise guarded graphics correction installation/removal using the exact TWRP BusyBox.

Only fixture userdata, the mount table and the sda31 readlink response differ
from production. No handset or Windows executable is used by these tests.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
QEMU = None
RECOVERY_IMAGE = None
RESULTS = []


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = module('graphics_permissions_manager_tests', 'scripts/manage-graphics-permissions.py')
p = module('graphics_permissions_package_tests', 'scripts/package-graphics-permissions.py')
fixture_module = module('graphics_busybox_fixture', 'tests/test_ubuntu_graphics.py')


def payload():
    return {name: (ROOT / 'tools/graphics-permissions' / name).read_bytes() for name in m.ASSET_NAMES}


def fixture(name):
    values = {'version': 'Android Debug Bridge Version 37.0.1', 'state': 'recovery', 'uid': '0',
              'properties': 'ro.product.model|Galaxy S10+\nro.product.device|beyond2lte\n'
                            'ro.hardware|exynos9820\nro.twrp.version|3.7.0_9-2\n'
                            'ro.bootloader|G975FXXSGHWC1\n',
              'recovery-hash': m.legacy.EXPECTED_HASHES['recovery-hash'] + '  -',
              'boot-hash': m.BOOT_SHA256 + '  -',
              'data-state': 'UT_GRAPHICS_PERMISSIONS_1: data_ready=raw_ext4\n',
              'apply': 'UT_GRAPHICS_PERMISSIONS_1: applied_for_next_ubuntu_boot\n',
              'remove': 'UT_GRAPHICS_PERMISSIONS_1: removed_reboot_restores_defaults\n'}
    value = values.get(name, 'test output\n')
    return {'exit_code': 0, 'timed_out': False, 'stdout': value, 'stderr': '',
            'raw_stdout_bytes': len(value.encode())}


class Host(unittest.TestCase):
    def run_case(self, operation, bad=None, missing_logs=False):
        calls = []
        with tempfile.TemporaryDirectory(prefix='UT graphics probe with spaces ') as folder:
            folder = Path(folder)
            assets = folder / 'graphics-permissions-1'
            assets.mkdir()
            for name, value in payload().items():
                (assets / name).write_bytes(value)
            def runner(exe, name, value=None):
                calls.append(name)
                if name == 'apply':
                    self.assertEqual(value, payload())
                result = fixture(name)
                if name == bad:
                    result['exit_code'] = 1
                if bad == 'wrong-boot' and name == 'boot-hash':
                    result['stdout'] = '0' * 64 + '  -'
                if bad == 'wrong-model' and name == 'properties':
                    result['stdout'] = result['stdout'].replace('Galaxy S10+', 'Galaxy S10')
                if name.startswith('log:') and missing_logs:
                    result['exit_code'] = 44
                return result
            report, path = m.manage(folder, operation, runner=runner, verifier=lambda root: None)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                members = {name: archive.read(name) for name in archive.namelist()}
        return report, calls, members

    def test_every_operation_has_identity_gates_before_private_access(self):
        for operation in ('apply', 'read', 'remove'):
            with self.subTest(operation=operation):
                report, calls, members = self.run_case(operation)
                self.assertTrue(report['success'], report)
                self.assertEqual(calls[:7], list(m.IDENTITY_QUERIES))
                self.assertEqual(calls[7:], [*('log:' + n for n in m.LOG_NAMES), *('retained:' + n for n in m.RETAINED_LOGS)] if operation == 'read' else [operation])
                for flag in ('partition_writes', 'mount_changes_requested', 'reboot_requested',
                             'data_format_requested', 'system_or_vendor_images_changed', 'raw_partition_writes',
                             'ubuntu_touch_graphical_boot_verified'):
                    self.assertIs(report[flag], False)

    def test_identity_failure_never_reaches_mutation_or_logs(self):
        for operation in ('apply', 'read', 'remove'):
            for bad in (*m.IDENTITY_QUERIES, 'wrong-boot', 'wrong-model'):
                with self.subTest(operation=operation, bad=bad):
                    report, calls, _ = self.run_case(operation, bad)
                    self.assertFalse(report['success'])
                    self.assertTrue(set(calls) <= set(m.IDENTITY_QUERIES))

    def test_payload_mismatch_or_local_tool_failure_never_uses_usb(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / 'graphics-permissions-1').mkdir()
            for name, value in payload().items():
                (directory / 'graphics-permissions-1' / name).write_bytes(value + b'changed')
            def nope(*args):
                self.fail('USB used before local pins')
            for operation in ('apply', 'read', 'remove'):
                report, _ = m.manage(directory, operation, runner=nope, verifier=lambda root: None)
                self.assertEqual(report['error'], 'local_payload_hash_mismatch')
            report, _ = m.manage(directory, 'apply', runner=nope,
                verifier=lambda root: (_ for _ in ()).throw(ValueError('adb_package_mismatch')))
            self.assertEqual(report['error'], 'adb_package_mismatch')

    def test_missing_logs_never_count_as_graphical_success(self):
        report, _, members = self.run_case('read', missing_logs=True)
        self.assertEqual(report['error'], 'correction_runtime_logs_unavailable')
        self.assertTrue(all(n.startswith('retained-') or n == 'ubuntu-graphics-permissions-report.json' for n in members))
        self.assertEqual(len(members), 5)

    def test_reader_accepts_worst_case_crlf_but_rejects_overflow(self):
        for length, expected in ((m.LOG_BYTES * 2, 0), (m.LOG_BYTES * 2 + 1, None)):
            with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'\n' * length, b'')):
                result = m.run_query(Path('adb.exe'), 'log:' + m.LOG_NAMES[0])
            self.assertEqual(result['exit_code'], expected)
            if expected == 0:
                self.assertEqual(result['stdout'], '\n' * length)
            else:
                self.assertEqual(result['stdout'], '')

    def test_operation_allowlist_and_stdin_no_argument_injection(self):
        for name in ('mount', 'reboot', '../log', 'log:../../secret', 'prepare;reboot'):
            with self.assertRaises(ValueError):
                m.script_for(name)
        with patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as run:
            m.run_query(Path('adb.exe'), 'apply', payload())
        self.assertEqual(run.call_args.args[0][1:], ['-d', 'shell', '/sbin/busybox sh -s'])
        self.assertEqual(run.call_args.kwargs['input'], m.script_for('apply', payload()).encode('ascii'))
        self.assertNotIn(b'\r', run.call_args.kwargs['input'])

    def test_preexisting_reports_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'graphics-permissions-1').mkdir()
            for name, value in payload().items():
                (root / 'graphics-permissions-1' / name).write_bytes(value)
            old = root / 'ubuntu-graphics-permissions-1-apply-report.zip'
            old.write_bytes(b'keep')
            _, path = m.manage(root, 'apply', runner=lambda exe, name, payload=None: fixture(name), verifier=lambda root: None)
            self.assertEqual(path.name, 'ubuntu-graphics-permissions-1-apply-report-1.zip')
            self.assertEqual(old.read_bytes(), b'keep')

    def test_deterministic_package_and_all_payload_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / 'a.zip', Path(folder) / 'b.zip'
            p.package(first)
            p.package(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), 12)
                for line in archive.read('SHA256SUMS-graphics-permissions-1').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                self.assertEqual({n.split('/')[-1] for n in archive.namelist() if n.startswith('graphics-permissions-1/')}, set(m.ASSET_NAMES))
                for name in ('APPLICA', 'LEGGI', 'ANNULLA'):
                    data = archive.read(name + '-CORREZIONE-GRAFICA-1.cmd')
                    self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
                    self.assertIn(b' -I ', data)
                self.assertFalse(any(n.endswith(('.img', '.exe', '.dll', '.ps1')) for n in archive.namelist()))

    def test_retained_reader_is_fixed_allowlist_and_preserves_transport(self):
        value = {'exit_code': 0, 'timed_out': False, 'stdout': 'A\r\nB\r\n', 'stderr': ''}
        with patch.object(m.graphics, 'run_query', return_value=value) as read:
            for name in m.RETAINED_LOGS:
                self.assertEqual(m.run_query(Path('adb.exe'), 'retained:' + name), value)
            for name in ('xsession', '../../secret', 'usc;reboot'):
                with self.assertRaises(ValueError):
                    m.run_query(Path('adb.exe'), 'retained:' + name)
        self.assertEqual(read.call_count, len(m.RETAINED_LOGS))

    def test_recovery_script_never_executes_payload_or_changes_device_permissions(self):
        for operation in ('apply', 'remove'):
            script = m.script_for(operation, payload() if operation == 'apply' else None)
            self.assertNotIn('chmod 0666', script)
            self.assertNotIn('chown ', script)
            self.assertNotIn('python3 ', script)
            self.assertNotIn('mount ', script)
            self.assertNotIn('rm -r', script)


class Shell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.QEMU, fixture_module.RECOVERY_IMAGE = QEMU, RECOVERY_IMAGE
        fixture_module.Shell.setUpClass()
        cls.hardware = fixture_module.Shell
        cls.shell = cls.hardware.shell
        cls.backend = shlex.join(cls.shell[:-1]) if QEMU else ''

    @classmethod
    def tearDownClass(cls):
        cls.hardware.tearDownClass()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.hardware.base))
        self.data = self.folder / 'data'
        self.unit_parent = self.data / 'system-data/etc/systemd/system'
        self.dropin_parent = self.unit_parent / 'lightdm.service.d'
        self.dropin_parent.mkdir(parents=True)
        self.rules_parent = self.data / 'system-data/etc/udev/rules.d'
        self.rules_parent.mkdir(parents=True)
        self.base = self.data / 'ubuntu-touch-graphics-permissions-1'
        self.unit = self.unit_parent / 'ubuntu-touch-graphics-permissions.service'
        self.dropin = self.dropin_parent / m.DROPIN_NAME
        self.rule = self.rules_parent / m.ASSET_NAMES[2]
        self.mounts = self.folder / 'mounts'
        self.mounts.write_text('/dev/block/sda31 ' + str(self.data) + ' ext4 rw,relatime 0 0\n')
        self.trace = self.folder / 'trace'
        self.failure = ''

    def run_shell(self, operation, timeout=120):
        bridge = self.folder / 'bb'
        bridge.write_text('#!/bin/sh\n'
            'printf "%s|%s\\n" "$1" "$2" >>' + shlex.quote(str(self.trace)) + '\n'
            'if [ "$1" = readlink ] && [ "$3" = /dev/block/sda31 ]; then echo /dev/sda31; exit 0; fi\n'
            + self.failure + '\n'
            + ('exec ' + self.backend + ' "$@"\n' if QEMU else 'exec "$@"\n'))
        bridge.chmod(0o700)
        script = m.script_for(operation, payload() if operation == 'apply' else None)
        script = script.replace('BB=/sbin/busybox', 'BB=' + str(bridge))
        script = script.replace('/data', str(self.data)).replace('/proc/mounts', str(self.mounts))
        started = __import__('time').monotonic()
        result = subprocess.run([*self.shell, '-s'], input=script.encode('ascii'), capture_output=True, timeout=timeout)
        RESULTS.append({'scenario': self.id().split('.')[-1], 'operation': operation,
            'exit_code': result.returncode, 'seconds': round(__import__('time').monotonic() - started, 3)})
        return result

    def applied(self):
        result = self.run_shell('apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'applied_for_next_ubuntu_boot', result.stdout)

    def test_apply_hashes_every_file_and_publishes_dropin_last(self):
        self.applied()
        for name in m.ASSET_NAMES:
            path = self.base / 'assets' / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), m.PAYLOAD_SHA256[name])
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        for name, destination in m.DESTINATIONS.items():
            path = Path(destination.replace('/data', str(self.data)))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), m.PAYLOAD_SHA256[name])
        trace = self.trace.read_text().splitlines()
        self.assertEqual(trace[-1], 'ln|' + str(self.base / 'assets' / m.DROPIN_NAME))

    def test_repeat_does_not_overwrite_logs_or_existing_config(self):
        self.applied()
        logs = self.base / 'logs'
        logs.mkdir(mode=0o700)
        (logs / m.LOG_NAMES[0]).write_text('keep')
        self.trace.write_text('')
        result = self.run_shell('apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'already_applied_no_changes', result.stdout)
        self.assertEqual((logs / m.LOG_NAMES[0]).read_text(), 'keep')
        self.assertFalse(any(line.split('|')[0] in ('rm', 'ln', 'mkdir', 'chmod', 'base64') for line in self.trace.read_text().splitlines()))

    def test_conflicting_file_symlink_or_fifo_blocks_prepare(self):
        for kind in ('file', 'symlink', 'fifo'):
            with self.subTest(kind=kind):
                if kind == 'file':
                    self.unit.write_text('unrelated')
                elif kind == 'symlink':
                    self.unit.symlink_to(self.folder / 'absent')
                else:
                    os.mkfifo(self.unit)
                result = self.run_shell('apply', timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.base.exists())
                self.assertTrue(self.unit.exists() or self.unit.is_symlink())
                self.unit.unlink()

    def test_missing_fixed_parent_directories_can_be_created(self):
        self.dropin_parent.rmdir()
        self.unit_parent.rmdir()
        self.unit_parent.parent.rmdir()
        self.rules_parent.rmdir()
        self.rules_parent.parent.rmdir()
        self.applied()
        self.assertTrue(self.dropin_parent.is_dir())
        self.assertEqual(self.rules_parent.stat().st_mode & 0o777, 0o755)

    def test_unsafe_parent_symlink_or_writable_dir_is_rejected(self):
        self.dropin_parent.rmdir()
        outside = self.folder / 'outside'
        outside.mkdir()
        self.dropin_parent.symlink_to(outside)
        result = self.run_shell('apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.base.exists())
        self.dropin_parent.unlink()
        self.dropin_parent.mkdir(mode=0o777)
        self.dropin_parent.chmod(0o777)
        result = self.run_shell('apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.base.exists())

    def test_wrong_raw_mount_readonly_and_nested_mounts_precede_writes(self):
        good = self.mounts.read_text()
        for value in (good.replace('/dev/block/sda31', '/dev/dm-0'), good.replace('ext4', 'f2fs'),
                      good * 2, '', good.replace('rw,', 'ro,'),
                      good + 'tmpfs ' + str(self.unit_parent) + ' tmpfs rw 0 0\n',
                      good + 'tmpfs ' + str(self.rules_parent) + ' tmpfs rw 0 0\n',
                      good + 'tmpfs ' + str(self.base) + ' tmpfs rw 0 0\n'):
            with self.subTest(mounts=value):
                self.mounts.write_text(value)
                result = self.run_shell('apply')
                self.assertEqual(result.returncode, 33, result.stderr)
                self.assertFalse(self.base.exists())
                self.assertFalse(self.unit.exists())

    def test_failure_before_enable_rolls_back_only_own_files(self):
        sentinel = self.unit_parent / 'unrelated.service'
        sentinel.write_text('keep')
        self.failure = 'if [ "$1" = ln ] && [ "$3" = ' + shlex.quote(str(self.dropin)) + ' ]; then exit 1; fi'
        result = self.run_shell('apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.base.exists())
        self.assertFalse(self.unit.exists())
        self.assertFalse(self.dropin.exists())
        self.assertFalse(self.rule.exists())
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_partial_parent_creation_is_cleaned_without_existing_parent_removal(self):
        self.dropin_parent.rmdir()
        self.unit_parent.rmdir()
        self.unit_parent.parent.rmdir()
        self.failure = 'if [ "$1" = mkdir ] && [ "$2" = ' + shlex.quote(str(self.unit_parent)) + ' ]; then exit 1; fi'
        result = self.run_shell('apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.data / 'system-data/etc').is_dir())
        self.assertFalse(self.unit_parent.parent.exists())

    def test_corrupt_phone_payload_readback_rolls_back(self):
        self.failure = 'if [ "$1" = sha256sum ] && [ "$2" = ' + shlex.quote(str(self.base / 'assets/apply-permissions.py')) + ' ]; then echo "' + ('0' * 64) + '  file"; exit 0; fi'
        result = self.run_shell('apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.base.exists())
        self.assertFalse(self.dropin.exists())

    def test_read_is_bounded_and_rejects_symlink_fifo_or_wrong_owner(self):
        self.applied()
        logs = self.base / 'logs'
        logs.mkdir(mode=0o700)
        log = logs / m.LOG_NAMES[0]
        data = b'head' * 200000 + b'tail\n' * 100000
        log.write_bytes(data)
        result = self.run_shell('log:' + log.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, data[-m.LOG_BYTES:])
        log.unlink()
        outside = self.folder / 'private'
        outside.write_text('private sentinel')
        log.symlink_to(outside)
        result = self.run_shell('log:' + log.name)
        self.assertEqual(result.returncode, 35)
        self.assertEqual(result.stdout, b'')
        log.unlink()
        os.mkfifo(log)
        result = self.run_shell('log:' + log.name, timeout=30)
        self.assertEqual(result.returncode, 35)
        log.unlink()
        log.write_text('private sentinel')
        # This host filesystem does not support assigning Android UIDs.
        # Substitute only the stat ownership fields for this negative case;
        # all positive metadata cases use the exact TWRP stat implementation.
        self.failure = 'if [ "$1" = stat ] && [ "$3" = ' + shlex.quote(str(log)) + ' ]; then ' + \
            'metadata=$(' + self.backend + ' "$@"); set -- $metadata; ' + \
            'printf "%s %s %s %s 32011 32011\\n" "$1" "$2" "$3" "$4"; exit 0; fi'
        result = self.run_shell('log:' + log.name)
        self.assertEqual(result.returncode, 35)

    def test_remove_validates_all_then_disables_first_and_preserves_logs_and_unknown_files(self):
        self.applied()
        logs = self.base / 'logs'
        logs.mkdir(mode=0o700)
        (logs / m.LOG_NAMES[0]).write_text('keep log')
        (self.base / 'unknown.txt').write_text('keep unknown')
        self.trace.write_text('')
        result = self.run_shell('remove')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.dropin.exists())
        self.assertFalse(self.rule.exists())
        self.assertFalse(self.unit.exists())
        self.assertFalse((self.base / 'assets').exists())
        self.assertEqual((logs / m.LOG_NAMES[0]).read_text(), 'keep log')
        self.assertEqual((self.base / 'unknown.txt').read_text(), 'keep unknown')
        removals = [line for line in self.trace.read_text().splitlines() if line.startswith('rm|')]
        self.assertEqual(removals[0], 'rm|' + str(self.dropin))

    def test_remove_conflicting_asset_never_disables_or_deletes_anything(self):
        self.applied()
        asset = self.base / 'assets/apply-permissions.py'
        asset.write_text('changed')
        result = self.run_shell('remove')
        self.assertEqual(result.returncode, 35)
        self.assertTrue(self.dropin.is_file())
        self.assertEqual(asset.read_text(), 'changed')

    def test_remove_matching_partial_installation(self):
        self.base.mkdir(mode=0o755)
        (self.base / 'assets').mkdir(mode=0o755)
        (self.base / 'assets/apply-permissions.py').write_bytes(payload()['apply-permissions.py'])
        self.unit.write_bytes(payload()[m.ASSET_NAMES[1]])
        result = self.run_shell('remove')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.base.exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path)
    parser.add_argument('--recovery-image', type=Path)
    parser.add_argument('--report', type=Path)
    args, remaining = parser.parse_known_args()
    if bool(args.qemu) != bool(args.recovery_image):
        parser.error('--qemu and --recovery-image must be supplied together')
    QEMU, RECOVERY_IMAGE = args.qemu, args.recovery_image
    result = unittest.main(argv=[sys.argv[0], *remaining], exit=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'success': result.result.wasSuccessful(),
            'tests_run': result.result.testsRun, 'failures': len(result.result.failures),
            'errors': len(result.result.errors), 'exact_recovery_busybox_tested': bool(RECOVERY_IMAGE),
            'recovery_image_sha256': hashlib.sha256(RECOVERY_IMAGE.read_bytes()).hexdigest() if RECOVERY_IMAGE else None,
            'recovery_busybox_sha256': '5d053450c750048158e62b191997c0f58453a4648800dc1c9543724ba0663b87' if RECOVERY_IMAGE else None,
            'negative_owner_fixture_substitutes_stat_uid_fields': True,
            'native_windows_cmd_or_python_pe_tested': False, 'cases': RESULTS}, indent=2) + '\n')
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
