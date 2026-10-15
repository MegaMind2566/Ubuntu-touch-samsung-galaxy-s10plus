"""Check the two-node permission transaction without touching host devices.

Device descriptors/stat/sysfs, controlled UID subprocesses and ownership are
explicit fixtures. Real writes are limited to a private temporary log file.
"""
import argparse
import configparser
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'tools/graphics-permissions'
SOURCE_NAMES = ('apply-permissions.py', 'ubuntu-touch-graphics-permissions.service',
                '99-ubuntu-touch-s10plus-graphics.rules', '50-ubuntu-touch-graphics-permissions.conf')
SPEC = importlib.util.spec_from_file_location('graphics_permissions_runtime', ASSETS / SOURCE_NAMES[0])
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
RESULTS = []


def metadata(**changes):
    values = dict(st_mode=stat.S_IFCHR | 0o600, st_uid=0, st_gid=0,
                  st_rdev=os.makedev(10, 96), st_dev=33, st_ino=77, st_nlink=1)
    values.update(changes)
    return SimpleNamespace(**values)


def fake_os(value):
    return SimpleNamespace(O_PATH=os.O_PATH, O_NOFOLLOW=os.O_NOFOLLOW, O_CLOEXEC=os.O_CLOEXEC,
        open=Mock(return_value=42), fstat=Mock(return_value=value), lstat=Mock(return_value=value),
        close=Mock(), chmod=Mock(), major=os.major, minor=os.minor)


class Identity(unittest.TestCase):
    def read_fixture(self, value=None, sysfs='10:96\n', name='hwbinder'):
        boundary = fake_os(value or metadata())
        stream = io.StringIO(sysfs)
        read = Mock(wraps=stream.read)
        stream.read = read
        opener = Mock(return_value=stream)
        with patch.object(p, 'os', boundary), patch('builtins.open', opener):
            node = p.read_node(name)
        return node, boundary, opener, read

    def test_only_pinned_character_node_and_matching_sysfs_accepted(self):
        for mode in (0o600, 0o666):
            with self.subTest(mode=oct(mode)):
                node, boundary, opener, read = self.read_fixture(metadata(st_mode=stat.S_IFCHR | mode))
                self.assertEqual(node['original_mode'], mode)
                self.assertEqual(node['descriptor'], 42)
                boundary.open.assert_called_once_with('/dev/hwbinder', os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
                opener.assert_called_once_with('/sys/class/misc/hwbinder/dev', 'r', encoding='ascii')
                read.assert_called_once_with(64)
                boundary.close.assert_not_called()
        node, _, _, _ = self.read_fixture(metadata(st_rdev=os.makedev(10, 126)), '10:126\n', 'ion')
        self.assertEqual((node['major'], node['minor']), (10, 126))

    def test_unknown_name_rejected_before_device_open(self):
        boundary = fake_os(metadata())
        with patch.object(p, 'os', boundary):
            for name in ('vndbinder', 'binder', '../hwbinder', '/dev/ion'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    p.read_node(name)
        boundary.open.assert_not_called()

    def test_bad_type_owner_mode_or_sysfs_closes_descriptor(self):
        cases = [(metadata(st_mode=stat.S_IFLNK | 0o777), '10:96\n'),
                 (metadata(st_mode=stat.S_IFREG | 0o600), '10:96\n'),
                 (metadata(st_uid=1000), '10:96\n'), (metadata(st_gid=1000), '10:96\n'),
                 (metadata(st_mode=stat.S_IFCHR | 0o660), '10:96\n'),
                 (metadata(st_rdev=os.makedev(11, 96)), '10:96\n'),
                 (metadata(), '10:97\n'), (metadata(), '11:96\n'),
                 (metadata(), '10:96\nextra'), (metadata(), '10:12345678\n')]
        for value, text in cases:
            with self.subTest(value=value, sysfs=text):
                boundary = fake_os(value)
                with patch.object(p, 'os', boundary), patch('builtins.open', return_value=io.StringIO(text)):
                    with self.assertRaises(ValueError):
                        p.read_node('hwbinder')
                boundary.close.assert_called_once_with(42)
                boundary.chmod.assert_not_called()

    def test_chmod_uses_held_inode_and_verifies_live_path(self):
        node, _, _, _ = self.read_fixture()
        boundary = fake_os(metadata())
        with patch.object(p, 'os', boundary), patch.object(p, 'current_mode', side_effect=[0o600, 0o666]) as mode:
            p.change_mode(node, 0o666)
        self.assertEqual(mode.call_count, 2)
        boundary.chmod.assert_called_once_with('/proc/self/fd/42', 0o666)
        for replacement in (metadata(st_mode=stat.S_IFLNK | 0o777), metadata(st_ino=78),
                            metadata(st_rdev=os.makedev(10, 97)), metadata(st_uid=1000)):
            with self.subTest(replacement=replacement):
                boundary = fake_os(replacement)
                with patch.object(p, 'os', boundary), self.assertRaises(ValueError):
                    p.change_mode(node, 0o666)
                boundary.chmod.assert_not_called()
        with patch.object(p, 'os', fake_os(metadata())), self.assertRaises(ValueError):
            p.change_mode(node, 0o777)


class Transaction(unittest.TestCase):
    def transaction(self, scenario='success', initial=(0o600, 0o600)):
        calls, nodes = [], {}
        modes = dict(zip(p.TARGETS, initial))
        for index, name in enumerate(p.TARGETS):
            nodes[name] = dict(name=name, path='/dev/' + name, descriptor=100 + index,
                filesystem_device=33, inode=77 + index, rdev=os.makedev(10, 96 + index),
                major=10, minor=96 + index, uid=0, gid=0, original_mode=modes[name])
        failed_once = False

        def read(name):
            calls.append(('read', name))
            if scenario == 'preflight-ion' and name == 'ion':
                raise ValueError('fixture_invalid_ion')
            return nodes[name]

        def change(node, mode):
            nonlocal failed_once
            name = node['name']
            calls.append(('chmod', name, mode))
            if scenario == 'rollback-failure' and name == 'ion' and mode == 0o600:
                raise OSError('fixture_restore_failure')
            modes[name] = mode
            if scenario == 'chmod-ion' and name == 'ion' and mode == 0o666 and not failed_once:
                failed_once = True
                raise OSError('fixture_second_chmod_partial_failure')

        def current(node):
            calls.append(('mode', node['name']))
            if scenario == 'final-ion' and node['name'] == 'ion':
                return 0o600
            return modes[node['name']]

        def access(user):
            calls.append(('access', user))
            if scenario in ('access-phablet', 'rollback-failure') and user == 'phablet':
                raise RuntimeError('fixture_controlled_UID_failed')
            return {'access': {'/dev/hwbinder': True, '/dev/ion': True}}

        closer = Mock()
        with patch.object(p, 'read_node', side_effect=read), patch.object(p, 'change_mode', side_effect=change), \
                patch.object(p, 'current_mode', side_effect=current), patch.object(p, 'verify_user_access', side_effect=access), \
                patch.object(p, 'os', SimpleNamespace(close=closer)):
            report = p.apply_permissions()
        RESULTS.append({'scenario': scenario, 'initial_modes': [oct(value) for value in initial],
                        'success': report['success'], 'calls': calls, 'rollback': report['rollback']})
        return report, calls, modes, closer

    def test_both_preflights_complete_before_any_change_and_users_gate_success(self):
        report, calls, modes, closer = self.transaction()
        self.assertTrue(report['success'])
        self.assertEqual(calls[:2], [('read', 'hwbinder'), ('read', 'ion')])
        self.assertEqual([c for c in calls if c[0] == 'access'], [('access', 'phablet'), ('access', 'lightdm')])
        self.assertEqual(modes, {'hwbinder': 0o666, 'ion': 0o666})
        self.assertEqual(closer.call_args_list, [unittest.mock.call(100), unittest.mock.call(101)])

    def test_second_preflight_failure_never_changes_first(self):
        report, calls, modes, closer = self.transaction('preflight-ion')
        self.assertFalse(report['success'])
        self.assertFalse(any(c[0] in ('chmod', 'access') for c in calls))
        self.assertEqual(modes, {'hwbinder': 0o600, 'ion': 0o600})
        closer.assert_called_once_with(100)

    def test_second_change_readback_and_access_errors_restore_in_reverse(self):
        for scenario in ('chmod-ion', 'final-ion', 'access-phablet'):
            with self.subTest(scenario=scenario):
                report, calls, modes, closer = self.transaction(scenario)
                self.assertFalse(report['success'])
                self.assertEqual(modes, {'hwbinder': 0o600, 'ion': 0o600})
                self.assertEqual([item['name'] for item in report['rollback']], ['ion', 'hwbinder'])
                self.assertTrue(all(item['success'] for item in report['rollback']))
                self.assertEqual(closer.call_count, 2)

    def test_preexisting_good_mode_is_preserved_on_failure(self):
        report, calls, modes, _ = self.transaction('access-phablet', (0o666, 0o600))
        self.assertFalse(report['success'])
        self.assertEqual(modes, {'hwbinder': 0o666, 'ion': 0o600})
        self.assertFalse(any(c[0] == 'chmod' and c[1] == 'hwbinder' for c in calls))
        self.assertEqual([item['name'] for item in report['rollback']], ['ion'])

    def test_restore_failure_is_reported_and_other_restore_continues(self):
        report, _, modes, _ = self.transaction('rollback-failure')
        self.assertFalse(report['success'])
        self.assertEqual([item['success'] for item in report['rollback']], [False, True])
        self.assertEqual(modes['hwbinder'], 0o600)

    def test_real_sigterm_and_sigint_in_owned_child_roll_back_and_restore_handlers(self):
        source = ASSETS / 'apply-permissions.py'
        for signum in (signal.SIGTERM, signal.SIGINT):
            program = textwrap.dedent('''
                import importlib.util,json,os,signal
                from types import SimpleNamespace
                spec=importlib.util.spec_from_file_location('signal_fixture',SOURCE)
                p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
                modes={'hwbinder':0o600,'ion':0o600};closed=[]
                nodes={name:dict(name=name,path='/dev/'+name,descriptor=100+i,
                    original_mode=0o600) for i,name in enumerate(p.TARGETS)}
                p.read_node=lambda name:nodes[name]
                def change(node,mode):
                    modes[node['name']]=mode
                    if node['name']=='hwbinder' and mode==0o666:
                        os.kill(os.getpid(),SIGNUM)
                p.change_mode=change
                p.current_mode=lambda node:modes[node['name']]
                p.verify_user_access=lambda user:None
                p.os=SimpleNamespace(close=closed.append)
                previous={number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGINT)}
                report=p.apply_permissions()
                assert not report['success'],report
                assert modes=={'hwbinder':0o600,'ion':0o600},modes
                assert 'permission_transaction_interrupted' in report['error'],report
                assert report['rollback']==[{'name':'hwbinder','restore_mode':'0o600','success':True}],report
                assert all(signal.getsignal(number)==handler for number,handler in previous.items())
                assert closed==[100,101],closed
                print(json.dumps({'signal':SIGNUM,'rollback':report['rollback'],'handlers_restored':True}))
            ''').replace('SOURCE', repr(str(source))).replace('SIGNUM', str(int(signum)))
            with self.subTest(signal=signum):
                child = subprocess.run([sys.executable, '-I', '-c', program], capture_output=True, timeout=5)
                self.assertEqual(child.returncode, 0, child.stderr)
                result = json.loads(child.stdout)
                self.assertTrue(result['handlers_restored'])
                RESULTS.append({'scenario': 'real_signal_in_owned_fixture_child', **result})


class ControlledAccessAndBounds(unittest.TestCase):
    def test_access_uses_only_two_users_and_two_nodes(self):
        process = Mock(returncode=0)
        process.communicate.return_value = (json.dumps({'access': {'/dev/hwbinder': True, '/dev/ion': True}}).encode(), b'')
        with patch.object(p.subprocess, 'Popen', return_value=process) as popen:
            self.assertTrue(p.verify_user_access('phablet')['access']['/dev/hwbinder'])
            command = popen.call_args.args[0]
            self.assertEqual(command[:4], ['/usr/sbin/runuser', '-u', 'phablet', '--'])
            self.assertIn('-I', command)
            self.assertNotIn('vndbinder', command[-1])
            process.communicate.assert_called_once_with(timeout=4)
            with self.assertRaises(ValueError):
                p.verify_user_access('root')
            self.assertEqual(popen.call_count, 1)
        process.returncode = 1
        with patch.object(p.subprocess, 'Popen', return_value=process), self.assertRaises(RuntimeError):
            p.verify_user_access('lightdm')

    def test_access_timeout_kills_and_reaps_only_new_child_group(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired('fixture', 4), (b'', b'')]
        with patch.object(p.subprocess, 'Popen', return_value=process), patch.object(p.os, 'killpg') as kill:
            with self.assertRaises(RuntimeError):
                p.verify_user_access('phablet')
            kill.assert_called_once_with(12345, signal.SIGKILL)
            self.assertEqual(process.communicate.call_count, 2)

    def test_optional_mapper_requires_exact_preserved_probe_hash(self):
        fixture = MagicMock()
        fixture.lstat.return_value = metadata(st_mode=stat.S_IFREG | 0o644)
        fixture.read_bytes.return_value = b'incorrect probe'
        with patch.object(p, 'PROBE', fixture), patch.object(p, 'owned_directory'), \
                patch.object(p, 'write_log') as writer, patch.object(p.subprocess, 'Popen') as start:
            report = p.optional_mapper_probes()
        self.assertTrue(report['skipped'])
        self.assertIn('immutable_probe1_identity_mismatch', report['reason'])
        self.assertEqual(writer.call_count, 3)
        start.assert_not_called()
        original = ROOT / 'tools/graphics-probe/mapper-probe.py'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), p.PROBE_SHA256)

    def test_log_cap_retains_prefix_and_final_error(self):
        with tempfile.TemporaryDirectory(prefix='ut-graphics-permissions-log-') as folder:
            target = Path(folder) / 'private.log'
            content = b'prefix' * 20000 + b'middle' * 200000 + b'final loader error\n' * 20000
            with patch.object(p, 'log_path', return_value=target):
                p.write_log('permissions.json', content)
            data = target.read_bytes()
            self.assertLessEqual(len(data), p.CAPTURE_BYTES)
            self.assertEqual(data[:65536], content[:65536])
            self.assertEqual(data[-458688:], content[-458688:])
            self.assertIn(b'[output truncated; tail follows]', data)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_rules_and_lightdm_dependency_cover_only_authorized_fix(self):
        rules = (ASSETS / SOURCE_NAMES[2]).read_text()
        lines = [line for line in rules.splitlines() if line and not line.startswith('#')]
        self.assertEqual(len(lines), 2)
        for line, name in zip(lines, ('hwbinder', 'ion')):
            self.assertEqual(line, 'ACTION=="add|change", SUBSYSTEM=="misc", KERNEL=="' + name
                             + '", ENV{MAJOR}=="10", MODE:="0666"')
        service = configparser.ConfigParser(interpolation=None)
        service.read(ASSETS / SOURCE_NAMES[1])
        self.assertEqual(service['Service']['Type'], 'oneshot')
        self.assertEqual(service['Service']['TimeoutStartSec'], '45')
        self.assertEqual(service['Service']['KillMode'], 'control-group')
        self.assertEqual(service['Service']['RemainAfterExit'], 'yes')
        self.assertEqual(service['Unit']['Before'], 'lightdm.service')
        self.assertEqual(service['Unit']['Requires'], 'lxc-android-config.service')
        self.assertNotIn('lightdm', service['Unit']['After'])
        self.assertIn(' -I ', service['Service']['ExecStart'])
        dropin = configparser.ConfigParser(interpolation=None)
        dropin.read(ASSETS / SOURCE_NAMES[3])
        self.assertEqual(dropin['Unit']['Requires'], 'ubuntu-touch-graphics-permissions.service')
        self.assertEqual(dropin['Unit']['After'], 'ubuntu-touch-graphics-permissions.service')
        self.assertEqual(p.TARGETS, ('hwbinder', 'ion'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args, remaining = parser.parse_known_args()
    pins = {name:hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}
    suite = unittest.main(argv=[sys.argv[0], *remaining], exit=False)
    stable = all(hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() == pin for name, pin in pins.items())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'schema': 1, 'success': suite.result.wasSuccessful() and stable,
            'tests_run': suite.result.testsRun, 'failures': len(suite.result.failures), 'errors': len(suite.result.errors),
            'source_sha256': pins, 'sources_unchanged_during_tests': stable,
            'actual_device_sysfs_uid_pam_or_handset_tested': False,
            'boundaries': 'Device O_PATH/fstat/lstat/sysfs/ownership and UID subprocesses simulated; real writes only private temporary log.',
            'cases': RESULTS}, indent=2) + '\n')
    raise SystemExit(0 if suite.result.wasSuccessful() and stable else 1)
