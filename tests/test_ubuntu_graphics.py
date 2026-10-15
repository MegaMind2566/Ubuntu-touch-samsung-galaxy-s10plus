"""Check BOOT 6 graphics identity gates and bounded, canonical read-only paths.

Optional --qemu with --recovery-image executes TWRP BusyBox and its exact
Android linker/libraries. --cpio instead tests normal-BOOT BusyBox compatibility.
Only the fixture mount table and raw-device readlink are substituted.
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
CPIO = None
RECOVERY_IMAGE = None
RESULTS = []


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


c = module('graphics_collector', 'scripts/collect-ubuntu-graphics.py')
p = module('graphics_package', 'scripts/package-ubuntu-graphics.py')


def fixture(name, scenario):
    values = {'version': 'Version 37.0.1', 'state': 'recovery', 'uid': '0',
              'properties': 'ro.product.model|Galaxy S10+\nro.product.device|beyond2lte\n'
                            'ro.hardware|exynos9820\nro.twrp.version|3.7.0_9-2\n'
                            'ro.bootloader|G975FXXSGHWC1\n',
              'recovery-hash': c.legacy.EXPECTED_HASHES['recovery-hash'] + '  -',
              'boot-hash': c.BOOT_SHA256 + '  -',
              'data-state': 'UT_GRAPHICS_6: data_ready=raw_ext4\n'}
    value, code = values.get(name, 'fixed log\n'), 0
    if name == scenario:
        value, code = '', 1
    if scenario == 'wrong-boot' and name == 'boot-hash':
        value = '0' * 64 + '  -'
    if scenario == 'wrong-recovery' and name == 'recovery-hash':
        value = '0' * 64 + '  -'
    if scenario == 'wrong-model' and name == 'properties':
        value = value.replace('Galaxy S10+', 'Galaxy S10')
    if scenario == 'missing-optional' and name not in c.IDENTITY_QUERIES:
        value, code = '', 44
    if scenario == 'missing-old' and (name.endswith('-old') or name.startswith('lomiri-')):
        value, code = '', 44
    if scenario == 'metadata-failed' and name == 'usc':
        value, code = '', 37
    if scenario == 'unsafe-parent' and name == 'usc':
        value, code = '', 34
    return {'exit_code': code, 'timed_out': False, 'stdout': value, 'stderr': '',
            'raw_stdout_bytes': len(value.encode())}


class Collector(unittest.TestCase):
    def collect_case(self, scenario):
        calls = []
        def runner(exe, name):
            self.assertEqual(exe.name, 'adb.exe')
            calls.append(name)
            return fixture(name, scenario)
        with tempfile.TemporaryDirectory(prefix='UT graphics with spaces ') as folder:
            report, path = c.collect(Path(folder), runner=runner, verifier=lambda root: None)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                members = {name: archive.read(name) for name in archive.namelist()}
        RESULTS.append({'scenario': scenario, 'operations': calls, 'success': report['success'],
                        'error': report['error']})
        return report, calls, members

    def test_identity_precedes_every_private_read(self):
        report, calls, members = self.collect_case('success')
        self.assertTrue(report['success'])
        self.assertEqual(calls[:7], list(c.IDENTITY_QUERIES))
        self.assertEqual(calls[7:], [*c.LOG_PATHS, *c.INVENTORY_PATHS])
        for key in ('partition_writes', 'phone_files_written', 'mount_changes_requested',
                    'data_format_requested', 'reboot_requested', 'system_code_executed',
                    'ubuntu_touch_graphical_boot_verified'):
            self.assertIs(report[key], False)
        self.assertIn('usc.txt', members)

    def test_identity_failures_stop_before_private_logs(self):
        for scenario in ('version', 'state', 'uid', 'properties', 'wrong-model',
                         'recovery-hash', 'wrong-recovery', 'boot-hash', 'wrong-boot', 'data-state'):
            with self.subTest(scenario=scenario):
                report, calls, members = self.collect_case(scenario)
                self.assertFalse(report['success'])
                self.assertFalse(set(calls) & (c.LOG_PATHS.keys() | c.INVENTORY_PATHS.keys()))
                self.assertEqual(set(members), {'ubuntu-graphics-report.json'})

    def test_optional_missing_logs_are_explicit(self):
        report, _, members = self.collect_case('missing-optional')
        self.assertFalse(report['success'])
        self.assertEqual(report['error'], 'graphics_logs_unavailable')
        self.assertEqual(report['collected_log_count'], 0)
        self.assertEqual(report['collection_errors'], [])
        self.assertTrue(all(value['status'] == 'missing' for value in report['logs'].values()))
        self.assertFalse(any(value['collected'] for value in report['logs'].values()))
        self.assertEqual(set(members), {'ubuntu-graphics-report.json'})

    def test_missing_old_and_upstart_do_not_hide_available_logs(self):
        report, _, members = self.collect_case('missing-old')
        self.assertTrue(report['success'])
        self.assertEqual(report['collected_log_count'], 4)
        self.assertIn('usc.txt', members)
        self.assertEqual(report['logs']['usc-old']['status'], 'missing')

    def test_real_read_errors_are_incomplete_and_preserve_other_logs(self):
        for scenario in ('metadata-failed', 'unsafe-parent'):
            with self.subTest(scenario=scenario):
                report, _, members = self.collect_case(scenario)
                self.assertFalse(report['success'])
                self.assertEqual(report['error'], 'graphics_collection_incomplete')
                self.assertEqual(report['collection_errors'], ['usc'])
                self.assertEqual(report['logs']['usc']['status'], 'error')
                self.assertEqual(report['collected_log_count'], 9)
                self.assertIn('xsession.txt', members)

    def test_local_tools_failure_never_uses_usb(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _ = c.collect(Path(directory),
                verifier=lambda root: (_ for _ in ()).throw(ValueError('adb_package_mismatch')),
                runner=lambda *args: self.fail('USB before tools pin'))
            self.assertEqual(report['error'], 'adb_package_mismatch')
            self.assertEqual(report['steps'], [])

    def test_command_allowlist_and_stdin(self):
        for name in ('shell', 'mount', 'reboot', '../log', 'pstore:x', 'usc; echo bad'):
            with self.assertRaisesRegex(ValueError, 'graphics_query_not_allowed'):
                c.command_for(name)
        seen = []
        def run(args, **kwargs):
            seen.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, b'log', b'file=regular file|0|0|600|3|0')
        with patch.object(c.subprocess, 'run', side_effect=run):
            c.run_query(Path('adb.exe'), 'usc')
        args, kwargs = seen[0]
        self.assertEqual(args[1:], ['-d', 'shell', '/sbin/busybox sh -s'])
        self.assertEqual(kwargs['input'], c.script_for('usc').encode('ascii'))
        self.assertNotIn(b'\r', kwargs['input'])
        self.assertEqual(kwargs['timeout'], 45)

    def test_output_limit_and_timeout_discard_content(self):
        for stdout, stderr in ((b'x' * (c.LOG_BYTES + 1), b''), (b'x', b'x' * 16385)):
            with patch.object(c.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout, stderr)):
                result = c.run_query(Path('adb.exe'), 'usc')
                self.assertEqual(result['stderr'], 'output_limit')
                self.assertEqual(result['stdout'], '')
                self.assertIsNone(result['exit_code'])
        with patch.object(c.subprocess, 'run', side_effect=subprocess.TimeoutExpired('adb', 45)):
            result = c.run_query(Path('adb.exe'), 'usc')
            self.assertTrue(result['timed_out'])
            self.assertEqual(result['stdout'], '')

    def test_existing_report_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / 'ubuntu-graphics-6-report.zip'
            first.write_bytes(b'old report')
            report, path = c.collect(Path(folder), runner=lambda exe, name: fixture(name, 'success'),
                                     verifier=lambda root: None)
            self.assertTrue(report['success'])
            self.assertEqual(path.name, 'ubuntu-graphics-6-report-1.zip')
            self.assertEqual(first.read_bytes(), b'old report')

    def test_package_exact_manifest_reproducibility_and_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = [Path(folder) / name for name in ('one.zip', 'two.zip')]
            p.package(first)
            p.package(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),
                    {'scripts/collect-ubuntu-graphics.py', 'scripts/collect-first-boot.py',
                     'LEGGI-GRAFICA-UBUNTU-6.cmd', 'LEGGIMI-GRAFICA-UBUNTU-6.txt', 'SHA256SUMS-graphics-6'})
                for line in archive.read('SHA256SUMS-graphics-6').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                self.assertFalse(any(name.endswith(('.exe', '.dll', '.img', '.ps1')) for name in archive.namelist()))
                launcher = archive.read('LEGGI-GRAFICA-UBUNTU-6.cmd')
                self.assertNotIn(b'\n', launcher.replace(b'\r\n', b''))
                self.assertIn(b'-I "%~dp0scripts\\collect-ubuntu-graphics.py" --root "%~dp0."', launcher)
                self.assertIn(b'exit /b %UT_GRAPHICS6_READ_EXIT%', launcher)
                self.assertNotIn(b'\r', archive.read('scripts/collect-ubuntu-graphics.py'))


class Shell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix='ut-graphics-shell-')
        cls.base = Path(cls.workspace.name)
        if QEMU and RECOVERY_IMAGE:
            sys.path.insert(0, str(ROOT / 'scripts'))
            import prepare_recovery as recovery
            image = RECOVERY_IMAGE.read_bytes()
            if hashlib.sha256(image).hexdigest() != recovery.IMAGE_SHA256:
                raise AssertionError('unexpected original recovery image')
            header = recovery.boot_header(image)
            files = recovery.newc_files(recovery.decode_ramdisk(image[header['ramdisk_offset']:
                header['ramdisk_offset'] + header['ramdisk_bytes']]))
            sysroot = cls.base / 'twrp-sysroot'
            for name, value in files.items():
                if name in ('sbin/linker64', 'sbin/busybox') or name.startswith('sbin/') and name.endswith('.so'):
                    destination = sysroot / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(value)
                    destination.chmod(0o700)
            cls.binary = sysroot / 'sbin/busybox'
            if hashlib.sha256(cls.binary.read_bytes()).hexdigest() != '5d053450c750048158e62b191997c0f58453a4648800dc1c9543724ba0663b87':
                raise AssertionError('unexpected recovery BusyBox')
            cls.shell = [str(QEMU), '-L', str(sysroot), '-E', 'LD_LIBRARY_PATH=' + str(sysroot / 'sbin'),
                         str(cls.binary), 'sh']
            backend = shlex.join(cls.shell[:-1])
        elif QEMU:
            sys.path.insert(0, str(ROOT / 'scripts'))
            from prepare_boot_diagnostic import entries
            items = entries(CPIO.read_bytes())
            item = next(item for item in items if item['name'] == 'bin/busybox')
            peers = [peer['data'] for peer in items if peer['data'] and peer['values'][0] == item['values'][0]
                     and peer['values'][7:9] == item['values'][7:9]]
            if len(peers) != 1:
                raise AssertionError('BusyBox hardlink ambiguous')
            cls.binary = cls.base / 'busybox-arm64'
            cls.binary.write_bytes(peers[0])
            cls.binary.chmod(0o700)
            if hashlib.sha256(peers[0]).hexdigest() != '27ba89e925a4d9cf0406c4daf4a4bfaca78f71dfc1ef11746c4a8a4f819621c8':
                raise AssertionError('unexpected BusyBox')
            cls.shell = [str(QEMU), str(cls.binary), 'sh']
            backend = shlex.join([str(QEMU), str(cls.binary)])
        else:
            cls.shell = ['/bin/sh']
            backend = ''
        cls.bridge = cls.base / 'bb'
        cls.bridge.write_text('#!/bin/sh\n'
            'if [ "$1" = readlink ] && [ "$3" = /dev/block/sda31 ]; then echo /dev/sda31; exit 0; fi\n'
            + ('exec ' + backend + ' "$@"\n' if backend else 'exec "$@"\n'))
        cls.bridge.chmod(0o700)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.base))
        self.data = self.folder / 'data'
        self.lightdm = self.data / 'system-data/var/log/lightdm'
        self.lightdm.mkdir(parents=True)
        self.log = self.lightdm / 'unity-system-compositor.log'
        self.mounts = self.folder / 'mounts'
        self.mounts.write_text('/dev/block/sda31 ' + str(self.data) + ' ext4 rw,relatime 0 0\n')

    def run_shell(self, name='usc', timeout=60):
        script = c.script_for(name).replace('BB=/sbin/busybox', 'BB=' + str(self.bridge))
        script = script.replace('/data', str(self.data)).replace('/proc/mounts', str(self.mounts))
        started = __import__('time').monotonic()
        result = subprocess.run([*self.shell, '-s'], input=script.encode(), capture_output=True, timeout=timeout)
        RESULTS.append({'shell_case': self.id().split('.')[-1], 'query': name,
                        'exit_code': result.returncode,
                        'elapsed_seconds': round(__import__('time').monotonic() - started, 3),
                        'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr)})
        return result

    def test_normal_log_tail_and_separate_metadata(self):
        self.log.write_bytes(b'a' * 400000 + b'b' * 200000)
        result = self.run_shell()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, self.log.read_bytes()[-c.LOG_BYTES:])
        self.assertIn(b'UT_GRAPHICS_6: file_metadata', result.stderr)
        self.assertIn(b' 600000 ', result.stderr)
        self.assertNotIn(b'parent_metadata', result.stdout)

    def test_actual_recovery_reproduces_unsupported_custom_stat(self):
        if not RECOVERY_IMAGE:
            self.skipTest('exact recovery fixture not selected')
        result = subprocess.run([*self.shell[:-1], 'stat', '-c', '%s', str(self.data)],
                                capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'invalid option', result.stderr)
        self.assertIn(b'v1.22.1', result.stderr)

    def test_missing_file_and_parent_are_distinct_from_unsafe(self):
        result = self.run_shell()
        self.assertEqual(result.returncode, 44)
        self.assertIn(b'missing_file', result.stderr)
        result = self.run_shell('lomiri-upstart')
        self.assertEqual(result.returncode, 44)
        self.assertIn(b'missing_parent=', result.stderr)
        self.assertEqual(result.stdout, b'')

    def test_final_symlink_is_never_read(self):
        secret = self.folder / 'secret'
        secret.write_bytes(b'private sentinel')
        self.log.symlink_to(secret)
        result = self.run_shell()
        self.assertEqual(result.returncode, 35)
        self.assertEqual(result.stdout, b'')

    def test_parent_symlink_is_never_read(self):
        actual = self.lightdm.with_name('actual')
        self.lightdm.rename(actual)
        (actual / self.log.name).write_bytes(b'private sentinel')
        self.lightdm.symlink_to(actual, target_is_directory=True)
        result = self.run_shell()
        self.assertEqual(result.returncode, 34)
        self.assertEqual(result.stdout, b'')

    def test_fifo_is_rejected_without_opening(self):
        os.mkfifo(self.log)
        result = self.run_shell(timeout=5)
        self.assertEqual(result.returncode, 35)
        self.assertEqual(result.stdout, b'')

    def test_directory_in_place_of_file_is_rejected(self):
        self.log.mkdir()
        result = self.run_shell()
        self.assertEqual(result.returncode, 35)
        self.assertEqual(result.stdout, b'')

    def test_wrong_data_mount_cannot_open_logs(self):
        self.log.write_bytes(b'private sentinel')
        for table in ('/dev/dm-0 ' + str(self.data) + ' ext4 rw 0 0\n',
                      '/dev/block/sda31 ' + str(self.data) + ' f2fs rw 0 0\n', '',
                      self.mounts.read_text() * 2):
            with self.subTest(table=table):
                self.mounts.write_text(table)
                result = self.run_shell()
                self.assertEqual(result.returncode, 33)
                self.assertEqual(result.stdout, b'')

    def test_inventory_cap_depth_and_no_follow(self):
        for number in range(80):
            (self.lightdm / ('log-' + str(number))).write_bytes(b'not copied')
        result = self.run_shell('lightdm-inventory')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout.splitlines()), 64)
        self.assertNotIn(b'not copied', result.stdout)
        for child in self.lightdm.iterdir():
            child.unlink()
        outside = self.folder / 'outside'
        outside.mkdir()
        (outside / 'private-file').write_bytes(b'private sentinel')
        (self.lightdm / 'linked').symlink_to(outside)
        deep = self.lightdm / 'one/two'
        deep.mkdir(parents=True)
        (deep / 'too-deep').write_bytes(b'not copied')
        os.mkfifo(self.lightdm / 'fifo')
        result = self.run_shell('lightdm-inventory')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b'private-file', result.stdout)
        self.assertNotIn(b'linked', result.stdout)
        self.assertNotIn(b'too-deep', result.stdout)
        self.assertNotIn(b'fifo', result.stdout)

    def test_journal_inventory_is_metadata_only(self):
        folder = self.data / 'system-data/var/log/journal/0123456789abcdef'
        folder.mkdir(parents=True)
        (folder / 'user-32011.journal').write_bytes(b'private binary content')
        result = self.run_shell('journal-inventory')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'user-32011.journal', result.stdout)
        self.assertNotIn(b'private binary content', result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path)
    parser.add_argument('--cpio', type=Path)
    parser.add_argument('--recovery-image', type=Path)
    parser.add_argument('--report', type=Path)
    args, remaining = parser.parse_known_args()
    if bool(args.qemu) != bool(args.cpio or args.recovery_image) or args.cpio and args.recovery_image:
        parser.error('--qemu requires exactly one of --cpio or --recovery-image')
    QEMU, CPIO, RECOVERY_IMAGE = args.qemu, args.cpio, args.recovery_image
    result = unittest.main(argv=[sys.argv[0], *remaining], exit=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'success': result.result.wasSuccessful(),
            'tests_run': result.result.testsRun, 'failures': len(result.result.failures),
            'errors': len(result.result.errors), 'actual_arm64_busybox_fixtures': bool(QEMU),
            'exact_recovery_busybox_tested': bool(RECOVERY_IMAGE),
            'normal_boot_busybox_compatibility_only': bool(CPIO),
            'recovery_image_sha256': hashlib.sha256(RECOVERY_IMAGE.read_bytes()).hexdigest() if RECOVERY_IMAGE else None,
            'recovery_busybox_sha256': '5d053450c750048158e62b191997c0f58453a4648800dc1c9543724ba0663b87' if RECOVERY_IMAGE else None,
            'native_windows_cmd_or_python_pe_tested': False,
            'raw_mount_boundary': 'fixture only; no handset, mount or writes',
            'cases': RESULTS}, indent=2) + '\n')
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
