"""Exercise read-only handoff guards, root-confined links and the Windows entry."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


c = module('userspace_collector', 'scripts/collect-ubuntu-userspace.py')
p = module('userspace_package', 'scripts/package-ubuntu-userspace-check.py')
OPERATIONS = []


def fixture(name, scenario='success'):
    values = {'version': 'Version 37.0.1', 'state': 'recovery', 'uid': '0',
              'properties': 'ro.product.device|beyond2lte\nro.hardware|exynos9820\n'
                            'ro.twrp.version|3.7.0_9-2\nro.bootloader|G975FXXSGHWC1\n',
              'last-kmsg-size': '200', 'last-kmsg-head': 'k' * 200,
              'boot-hash': c.BOOT_SHA256 + '  -',
              'recovery-hash': c.legacy.EXPECTED_HASHES['recovery-hash'] + '  -',
              'vbmeta-hash': c.legacy.EXPECTED_HASHES['vbmeta-hash'] + '  -',
              'system-inspection': 'UT_INSPECT_4: mount_options=ro,noload,nosuid,nodev,noexec\n'
                                   'UT_INSPECT_4: mount_requested=true\n'
                                   'UT_INSPECT_4: mount_verified_read_only=true\n'
                                   'UT_INSPECT_4: status=complete\nUT_INSPECT_4: cleanup_confirmed=true\n'}
    code = 0
    value = values.get(name, '')
    if name.startswith('run-') or name in c.USER_LOGS or name == 'journal-inventory':
        code = 1
    if scenario == 'wrong-device' and name == 'properties':
        value = value.replace('beyond2lte', 'other')
    if scenario == 'wrong-boot' and name == 'boot-hash':
        value = '0' * 64 + '  -'
    if scenario == 'missing-log' and name in ('last-kmsg-size', 'last-kmsg-head'):
        code, value = 1, ''
    if scenario == 'large-log' and name == 'last-kmsg-size':
        value = str(c.HEAD_BYTES + 1)
    if scenario == 'mount-failure' and name == 'system-inspection':
        code, value = 1, 'UT_INSPECT_4: error=read_only_mount_failed\nUT_INSPECT_4: cleanup_confirmed=true\n'
    if scenario == 'missing-cleanup' and name == 'system-inspection':
        value = value.replace('UT_INSPECT_4: cleanup_confirmed=true\n', '')
    return {'exit_code': code, 'timed_out': False, 'stdout': value, 'stderr': '',
            'raw_stdout_bytes': len(value.encode())}


class Collector(unittest.TestCase):
    def run_case(self, scenario):
        calls = []
        def runner(exe, name):
            calls.append(name)
            return fixture(name, scenario)
        with tempfile.TemporaryDirectory(prefix='UT inspection with spaces ') as folder:
            report, path = c.collect(Path(folder), runner=runner, verifier=lambda root: None)
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                files = {n: archive.read(n) for n in archive.namelist()}
        OPERATIONS.append({'scenario': scenario, 'operations': calls, 'success': report['success'],
                           'error': report['error']})
        return report, calls, files

    def test_complete_log_and_cleanup(self):
        result, calls, _ = self.run_case('success')
        self.assertTrue(result['success'])
        self.assertTrue(result['previous_boot']['head_contains_complete_source'])
        self.assertTrue(result['system_inspection']['cleanup_confirmed'])
        self.assertLess(calls.index('last-kmsg-head'), calls.index('boot-hash'))
        self.assertLess(calls.index('vbmeta-hash'), calls.index('system-inspection'))
        self.assertFalse(result['partition_writes'])
        self.assertFalse(result['system_code_executed'])
        self.assertFalse(result['ubuntu_touch_boot_verified'])

    def test_wrong_device_stops_before_logs_hashes_mounts(self):
        result, calls, _ = self.run_case('wrong-device')
        self.assertEqual(result['error'], 'recovery_device_unconfirmed')
        self.assertNotIn('last-kmsg-head', calls)
        self.assertNotIn('system-inspection', calls)

    def test_wrong_boot_keeps_logs_and_never_mounts(self):
        result, calls, files = self.run_case('wrong-boot')
        self.assertEqual(result['error'], 'image_identity_mismatch')
        self.assertIn('last-kmsg-head.txt', files)
        self.assertNotIn('system-inspection', calls)

    def test_absent_logs_do_not_prevent_system_inspection(self):
        result, _, _ = self.run_case('missing-log')
        self.assertTrue(result['success'])
        self.assertFalse(result['previous_boot']['head_contains_complete_source'])

    def test_truncation_is_explicit(self):
        result, _, _ = self.run_case('large-log')
        self.assertTrue(result['success'])
        self.assertFalse(result['previous_boot']['head_contains_complete_source'])

    def test_partial_mount_error_is_retained(self):
        result, _, files = self.run_case('mount-failure')
        self.assertEqual(result['error'], 'system_inspection_failed')
        self.assertIn(b'read_only_mount_failed', files['system-inspection.txt'])
        self.assertTrue(result['system_inspection']['cleanup_confirmed'])

    def test_missing_cleanup_cannot_report_success(self):
        result, _, _ = self.run_case('missing-cleanup')
        self.assertEqual(result['error'], 'system_inspection_incomplete')

    def test_tools_failure_never_uses_usb(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _ = c.collect(Path(directory), verifier=lambda root: (_ for _ in ()).throw(OSError()),
                                  runner=lambda *args: self.fail('unexpected USB access'))
            self.assertEqual(report['error'], 'local_tools_unavailable')
            self.assertEqual(report['steps'], [])

    def test_command_allowlist_and_stdin(self):
        for name in ['../system', 'pstore:../../data', 'run-6-stage', 'run-1-kernel', 'shell']:
            with self.assertRaisesRegex(ValueError, 'userspace_query_not_allowed'):
                c.command_for(name)
        seen = []
        def run(args, **kw):
            seen.append((args, kw))
            return subprocess.CompletedProcess(args, 0, b'UT_INSPECT_4: status=complete\n', b'')
        with patch.object(c.subprocess, 'run', side_effect=run):
            c.run_query(Path('adb.exe'), 'system-inspection')
        self.assertEqual(seen[0][0][-1], '/sbin/busybox sh -s')
        self.assertTrue(seen[0][1]['input'].startswith(b'#!/bin/sh\n'))
        self.assertNotIn(b'\r', seen[0][1]['input'])
        self.assertLessEqual(seen[0][1]['timeout'], 55)

    def test_package_has_no_flash_or_firmware_and_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = [Path(directory) / name for name in ('a.zip', 'b.zip')]
            p.package(first)
            p.package(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(len(archive.namelist()), 6)
                self.assertFalse(any(n.endswith(('.img', '.exe', '.dll', '.ps1')) for n in archive.namelist()))
                for line in archive.read('SHA256SUMS-userspace-4').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)


SHIM = r'''import json,os,pathlib,shutil,subprocess,sys
base=pathlib.Path(os.environ['UT_FIXTURE']);name,*args=sys.argv[1:];scenario=os.environ['UT_SCENARIO']
with (base/'calls.jsonl').open('a') as f:f.write(json.dumps([name,*args])+'\n')
if name=='id':print('0');sys.exit(0)
if name=='test' and args==['-b','/dev/block/sda25']:sys.exit(0)
if name=='blockdev':print('1' if scenario=='wrong-size' else '5976883200');sys.exit(0)
if name=='readlink' and args[-1] in ['/dev/block/sda25','/dev/sda25']:
 print('/dev/sda25');sys.exit(0)
if name=='mktemp':
 import tempfile
 print(tempfile.mkdtemp(prefix='root.',dir=base));sys.exit(0)
if name=='mount':
 if args[:-1]!=['-n','-t','ext4','-o','ro,noload,nosuid,nodev,noexec','/dev/block/sda25']:sys.exit(31)
 if scenario=='mount-failure':sys.exit(1)
 root=pathlib.Path(args[-1]);shutil.copytree(base/'system',root,symlinks=True,dirs_exist_ok=True)
 opts='rw,nosuid,nodev,noexec' if scenario=='bad-options' else ('ro,nosuid,nodev,noexec' if scenario=='no-noload' else 'ro,nosuid,nodev,noexec,norecovery')
 with (base/'mounts').open('a') as f:f.write('/dev/sda25 '+str(root)+' ext4 '+opts+' 0 0\n')
 sys.exit(1 if scenario=='partial-mount-failure' else 0)
if name=='umount':
 if scenario=='unmount-failure':sys.exit(1)
 root=pathlib.Path(args[0]);path=base/'mounts'
 path.write_text(''.join(l for l in path.read_text().splitlines(True) if l.split()[1]!=str(root)))
 for p in root.iterdir():
  if p.is_symlink() or p.is_file():p.unlink()
  else:shutil.rmtree(p)
 sys.exit(0)
args=[str(base/'mounts') if a=='/proc/mounts' else a for a in args]
sys.exit(subprocess.call([name,*args]))
'''


@unittest.skipIf(os.name == 'nt', 'POSIX shell exercised by the Linux job')
class Shell(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory(prefix='ut-shell-') as directory:
            folder = Path(directory)
            system = folder / 'system'
            (system / 'usr/lib/systemd').mkdir(parents=True)
            (system / 'usr/sbin').mkdir()
            (system / 'etc').mkdir()
            data = b'#!/bin/sh\nprintf own-system-fixture\n'
            (system / 'usr/lib/systemd/systemd').write_bytes(data)
            (system / 'sbin').symlink_to('/usr/sbin')
            (system / 'usr/sbin/init').symlink_to('../lib/systemd/systemd')
            (system / 'init').symlink_to('/sbin/init' if scenario != 'link-loop' else '/init')
            (folder / 'mounts').write_text('tmpfs /tmp tmpfs rw 0 0\n' +
                ('/dev/block/sda25 /existing ext4 ro 0 0\n' if scenario == 'already-mounted' else ''))
            shim = folder / 'shim.py'
            shim.write_text(SHIM)
            executable = folder / 'bb'
            executable.write_text('#!/bin/sh\nexec ' + shutil.which('python3') + ' ' + str(shim) + ' "$@"\n')
            executable.chmod(0o700)
            script = folder / 'inspect.sh'
            source = c.SHELL.read_text().replace('BB=/sbin/busybox', 'BB=' + str(executable))
            source = source.replace('done </proc/mounts', 'done <' + str(folder / 'mounts'))
            script.write_text(source)
            subprocess.run(['/bin/sh', '-n', str(script)], check=True)
            result = subprocess.run(['/bin/sh', str(script)], capture_output=True, text=True, timeout=20,
                                    env=dict(os.environ, UT_FIXTURE=directory, UT_SCENARIO=scenario))
            calls = [json.loads(l) for l in (folder / 'calls.jsonl').read_text().splitlines()]
            leftover = [p.name for p in folder.glob('root.*')]
        OPERATIONS.append({'shell_scenario': scenario, 'exit_code': result.returncode,
                           'shell_operations': [row for row in calls if row[0] in ('mount', 'umount')],
                           'leftover_fixture_directories': leftover})
        return result, calls, leftover, data

    def test_safe_symlinks_and_cleanup(self):
        result, calls, leftover, data = self.run_case('success')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RESOLVED /usr/lib/systemd/systemd', result.stdout)
        self.assertIn(hashlib.sha256(data).hexdigest(), result.stdout)
        self.assertEqual(sum(row[0] == 'mount' for row in calls), 1)
        self.assertIn('UT_INSPECT_4: cleanup_confirmed=true', result.stdout)
        self.assertFalse(leftover)

    def test_existing_mount_and_wrong_size_refused(self):
        for scenario in ('already-mounted', 'wrong-size'):
            result, calls, leftover, _ = self.run_case(scenario)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any(row[0] in ('mount', 'umount') for row in calls))
            self.assertFalse(leftover)

    def test_failed_mount_removes_only_own_ram_directory(self):
        result, calls, leftover, _ = self.run_case('mount-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(row[0] == 'umount' for row in calls))
        self.assertFalse(leftover)

    def test_unconfirmed_read_only_mount_is_cleaned(self):
        for scenario in ('bad-options', 'no-noload'):
            result, calls, leftover, _ = self.run_case(scenario)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('read_only_mount_unconfirmed', result.stdout)
            self.assertTrue(any(row[0] == 'umount' for row in calls))
            self.assertFalse(leftover)

    def test_error_after_mount_is_cleaned(self):
        result, calls, leftover, _ = self.run_case('partial-mount-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('read_only_mount_failed', result.stdout)
        self.assertTrue(any(row[0] == 'umount' for row in calls))
        self.assertFalse(leftover)

    def test_unmount_failure_is_reported_without_forcing(self):
        result, calls, leftover, _ = self.run_case('unmount-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cleanup_confirmed=false', result.stdout)
        self.assertTrue(leftover)
        self.assertEqual([row for row in calls if row[0] == 'umount'][0][1:2],
                         [next(row[-1] for row in calls if row[0] == 'mount')])

    def test_link_loop_is_bounded(self):
        result, _, leftover, _ = self.run_case('link-loop')
        self.assertEqual(result.returncode, 0)
        self.assertIn('RESOLUTION_FAILED', result.stdout)
        self.assertFalse(leftover)


def native_windows():
    dependency = module('portable_dependencies', 'scripts/package-ubuntu-install.py')
    with tempfile.TemporaryDirectory(prefix='UT native inspector with spaces ') as directory:
        folder = Path(directory)
        package = folder / 'addon.zip'
        p.package(package)
        with zipfile.ZipFile(package) as archive:
            archive.extractall(folder)
        runtime = folder / 'tools/python'
        runtime.mkdir(parents=True)
        with dependency.dependency('python', None) as archive:
            archive.extractall(runtime)
        # Native CMD uses the pinned embedded Python. ADB is deliberately absent:
        # the actual guard must stop before any USB query or phone mount.
        result = subprocess.run(['cmd.exe', '/d', '/c', str(folder / 'CONTROLLA-PASSAGGIO-UBUNTU-4.cmd')],
                                input='\n', text=True, capture_output=True, timeout=30)
        assert result.returncode == 1, result.stdout + result.stderr
        with zipfile.ZipFile(folder / 'ubuntu-userspace-4-report.zip') as archive:
            report = json.loads(archive.read('ubuntu-userspace-report.json'))
        assert report['error'] == 'local_tools_unavailable' and not report['steps']
        assert not report['temporary_read_only_system_mount_requested']
        OPERATIONS.append({'native_windows_cmd': True, 'pinned_embedded_python': True,
                           'path_with_spaces': True, 'usb_accessed': False, 'expected_tools_guard_passed': True})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-windows', action='store_true')
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.native_windows:
        native_windows()
    output = ROOT / 'out/ubuntu-userspace-check-tests.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({'schema': 1, 'host': sys.platform, 'tests_run': result.testsRun,
                                  'skipped': len(result.skipped), 'success': True,
                                  'physical_phone_accessed': False, 'mounts_simulated': True,
                                  'observations': OPERATIONS}, indent=2) + '\n')
