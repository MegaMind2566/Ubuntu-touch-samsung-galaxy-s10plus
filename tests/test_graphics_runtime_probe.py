"""Exercise graphics-probe ABI and bounds without a handset or Android runtime.

The compiled C fixture checks real ctypes pointer widths and callback ordering.
Shell fixtures substitute only the private userdata path and process/ownership
boundaries; no actual system service, user identity or graphics device is used.
"""
import argparse
import configparser
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

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'tools/graphics-probe'
RESULTS = []
SPEC = importlib.util.spec_from_file_location('mapper_probe', ASSETS / 'mapper-probe.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

C_FIXTURE = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void (*logger)(const void *) = NULL;
static int priority = -1;
static const uintptr_t handle_value = UINT64_C(0x12345678abcdef01);
static const uintptr_t buffer_value = UINT64_C(0x23456789abcdef02);
static void stderr_logger(const void *message) {
  fprintf(stderr, "C_FIXTURE_LOGGER: %s\n", (const char *)message);
  fflush(stderr);
}
static void set_logger(void (*value)(const void *)) {
  if (value != stderr_logger) { fputs("BAD_LOGGER_POINTER\n", stderr); abort(); }
  logger = value;
}
static int set_priority(int value) { priority = value; return -1; }
static int log_write(int level, const char *tag, const char *message) {
  if (getenv("STUB_NEGATIVE_WRITE")) return -13;
  if (priority != 2 || level != 6 || !logger || strcmp(tag, "UTGraphicsProbe")) {
    fputs("BAD_LOGGER_ORDER_OR_ABI\n", stderr); abort();
  }
  logger(message);
  return 1;
}
void *android_dlopen(const char *name, int flags) {
  if (strcmp(name, "liblog.so") || flags != 2) abort();
  return getenv("STUB_OPEN_FAIL") ? NULL : (void *)handle_value;
}
void *android_dlsym(void *handle, const char *name) {
  if ((uintptr_t)handle != handle_value) { fputs("TRUNCATED_HANDLE\n", stderr); abort(); }
  const char *missing = getenv("STUB_MISSING_SYMBOL");
  if (missing && !strcmp(missing, name)) return NULL;
  if (!strcmp(name, "__android_log_set_logger")) return set_logger;
  if (!strcmp(name, "__android_log_stderr_logger")) return stderr_logger;
  if (!strcmp(name, "__android_log_set_minimum_priority")) return set_priority;
  if (!strcmp(name, "__android_log_write")) return log_write;
  return NULL;
}
void *graphic_buffer_new(void) {
  if (getenv("STUB_CONSTRUCTOR_ABORT")) { fputs("C_FIXTURE_MAPPER_FATAL\n", stderr); abort(); }
  if (getenv("STUB_CONSTRUCTOR_NULL")) return NULL;
  if (!logger || priority != 2) return NULL;
  fputs("C_FIXTURE_CONSTRUCTOR_REACHED\n", stderr);
  return (void *)buffer_value;
}
void graphic_buffer_free(void *buffer) {
  if ((uintptr_t)buffer != buffer_value) { fputs("TRUNCATED_BUFFER\n", stderr); abort(); }
  fputs("C_FIXTURE_BUFFER_FREED\n", stderr);
}
'''


class ABI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if not compiler:
            raise unittest.SkipTest('host C compiler unavailable')
        cls.workspace = tempfile.TemporaryDirectory(prefix='ut-graphics-abi-')
        cls.folder = Path(cls.workspace.name)
        source = cls.folder / 'fixture.c'
        source.write_text(C_FIXTURE)
        subprocess.run([compiler, '-shared', '-fPIC', '-O2', str(source), '-o',
                        str(cls.folder / 'libhybris-common.so.1')], check=True, capture_output=True)
        (cls.folder / 'libui.so.1').symlink_to('libhybris-common.so.1')

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def run_probe(self, **settings):
        environment = dict(os.environ, LD_LIBRARY_PATH=str(self.folder), **settings)
        environment.pop('LD_PRELOAD', None)
        result = subprocess.run([sys.executable, '-I', str(ASSETS / 'mapper-probe.py')],
                                env=environment, capture_output=True, timeout=5)
        events = [json.loads(line) for line in result.stdout.decode().splitlines()]
        RESULTS.append({'case': self.id().split('.')[-1], 'settings': settings,
                        'exit_code': result.returncode, 'events': [item['event'] for item in events],
                        'stderr_bytes': len(result.stderr)})
        return result, events

    def test_real_ctypes_callbacks_marker_order_and_64bit_pointers(self):
        result, events = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [event['event'] for event in events]
        self.assertLess(names.index('bionic_stderr_logger_installed'),
                        names.index('calling_graphic_buffer_default_constructor'))
        self.assertIn(b'C_FIXTURE_LOGGER: Bionic stderr route verified', result.stderr)
        self.assertIn(b'C_FIXTURE_CONSTRUCTOR_REACHED', result.stderr)
        self.assertIn(b'C_FIXTURE_BUFFER_FREED', result.stderr)
        self.assertNotIn(b'TRUNCATED_', result.stderr)
        self.assertEqual(next(e for e in events if e['event'] == 'bionic_stderr_logger_installed')
                         ['marker_write_return'], 1)

    def test_missing_library_or_symbol_is_explicit(self):
        for settings in ({'STUB_OPEN_FAIL': '1'}, {'STUB_MISSING_SYMBOL': '__android_log_set_logger'},
                         {'STUB_MISSING_SYMBOL': '__android_log_stderr_logger'}):
            with self.subTest(settings=settings):
                result, events = self.run_probe(**settings)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(any(e['event'] == 'bionic_stderr_logger_unavailable' for e in events))
                self.assertFalse(next(e for e in events if e['event'] == 'calling_graphic_buffer_default_constructor')
                                 ['logger_installed'])

    def test_negative_marker_write_cannot_claim_logger_success(self):
        result, events = self.run_probe(STUB_NEGATIVE_WRITE='1')
        self.assertNotIn('bionic_stderr_logger_installed', [e['event'] for e in events])
        self.assertIn('bionic_stderr_logger_unavailable', [e['event'] for e in events])

    def test_null_and_aborting_constructor_remain_bounded_children(self):
        result, events = self.run_probe(STUB_CONSTRUCTOR_NULL='1')
        self.assertEqual(result.returncode, 2)
        self.assertIn('graphic_buffer_constructor_returned_null', [e['event'] for e in events])
        self.assertNotIn(b'C_FIXTURE_BUFFER_FREED', result.stderr)
        result, events = self.run_probe(STUB_CONSTRUCTOR_ABORT='1')
        self.assertLess(result.returncode, 0)
        self.assertIn(b'Bionic stderr route verified', result.stderr)
        self.assertIn(b'C_FIXTURE_MAPPER_FATAL', result.stderr)
        self.assertNotIn('graphic_buffer_default_constructor_returned', [e['event'] for e in events])


BOUNDARY = r'''import json,os,pathlib,subprocess,sys,time
root=pathlib.Path(os.environ.get('UT_FIXTURE',sys.argv[0])).resolve()
if root.is_file():root=root.parent
name=pathlib.Path(sys.argv[0]).name;args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as f:f.write(json.dumps([name,*args])+'\n')
scenario=(root/'scenario').read_text()
if name=='id':print('0');sys.exit(0)
if name=='stat':
 import stat
 value=os.lstat(args[-1]);fmt=args[1]
 fields={'%u':'999' if scenario=='bad-owner' else '0','%g':'0','%a':oct(stat.S_IMODE(value.st_mode))[2:],'%h':str(value.st_nlink),'%s':str(value.st_size)}
 for key,value in fields.items():fmt=fmt.replace(key,value)
 print(fmt);sys.exit(0)
if name=='env':
 environment={};index=1
 while index<len(args) and '=' in args[index]:
  key,value=args[index].split('=',1);environment[key]=value;index+=1
 # Record the intended Android preload without injecting an ARM64 .so into
 # host fixture executables. This is an explicit fixture boundary only.
 environment.pop('LD_PRELOAD',None);environment['UT_FIXTURE']=str(root)
 os.execvpe(args[index],args[index:],environment)
if name=='runuser':os.execv(args[3],args[3:])
if name=='strace':
 index=args.index('-u')-1
 os.execv(args[index],args[index:])
if name=='timeout':
 seconds=args[2]
 if scenario=='timeout' and seconds=='15':seconds='0.1'
 os.execv('/usr/bin/timeout',['timeout','-k','1',seconds,*args[3:]])
if name=='python3':
 if '--inventory' in args:print('{"fixture_inventory":true}');sys.exit(0)
 if scenario=='overflow':
  try:
   for _ in range(300):os.write(1,b'x'*8192)
  except OSError:sys.exit(25)
 elif scenario=='timeout':time.sleep(2)
 else:print('fixture mapper child complete')
 sys.exit(0)
if name=='systemctl':print('ActiveState=active');sys.exit(0)
if name=='lxc-attach':print('fixture filtered Android graphics logs');sys.exit(0)
if name=='journalctl':print('fixture selected unit journal');sys.exit(0)
raise SystemExit('unexpected boundary '+name)
'''


class Runtime(unittest.TestCase):
    def fixture(self, scenario='success'):
        workspace = tempfile.TemporaryDirectory(prefix='ut-graphics-runtime-')
        self.addCleanup(workspace.cleanup)
        folder = Path(workspace.name)
        (folder / 'scenario').write_text(scenario)
        binaries = folder / 'bin'
        binaries.mkdir()
        boundary = folder / 'boundary.py'
        boundary.write_text('#!' + sys.executable + '\n' + BOUNDARY)
        boundary.chmod(0o700)
        for name in ('id', 'stat', 'python3', 'timeout', 'runuser', 'strace', 'env', 'systemctl', 'lxc-attach', 'journalctl'):
            (binaries / name).symlink_to(boundary)
        base = folder / 'userdata/ubuntu-touch-graphics-probe-1'
        assets = base / 'assets'
        assets.mkdir(parents=True)
        base.chmod(0o755)
        assets.chmod(0o755)
        for name in ('probe.sh', 'mapper-probe.py'):
            shutil.copyfile(ASSETS / name, assets / name)
            (assets / name).chmod(0o644)
        armed = base / 'armed'
        armed.write_text('UT_GRAPHICS_PROBE_1_ARMED\n')
        armed.chmod(0o600)
        (folder / 'mir_ready').touch()
        script = (ASSETS / 'probe.sh').read_text()
        script = script.replace('BASE=/userdata/ubuntu-touch-graphics-probe-1', 'BASE=' + str(base))
        script = script.replace('PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'PATH=' + str(binaries) + ':/usr/sbin:/usr/bin:/sbin:/bin')
        # Unix socket creation is unavailable in the test sandbox. Substitute
        # only this readiness boundary; runtime still tests the real socket.
        script = script.replace('[ ! -S /run/mir_socket ]', '[ ! -f ' + str(folder / 'mir_ready') + ' ]')
        for name in ('python3', 'timeout', 'env', 'strace', 'systemctl', 'lxc-attach', 'journalctl'):
            script = script.replace('/usr/bin/' + name, str(binaries / name))
        script = script.replace('/usr/sbin/runuser', str(binaries / 'runuser'))
        target = folder / 'fixture-probe.sh'
        target.write_text(script)
        environment = dict(os.environ, UT_FIXTURE=str(folder))
        return folder, base, target, environment

    def execute(self, scenario='success'):
        folder, base, target, environment = self.fixture(scenario)
        result = subprocess.run(['/bin/sh', str(target)], env=environment, capture_output=True, timeout=20)
        calls = [json.loads(line) for line in (folder / 'calls.jsonl').read_text().splitlines()]
        RESULTS.append({'case': self.id().split('.')[-1], 'scenario': scenario, 'exit_code': result.returncode,
                        'log_bytes': {f.name:f.stat().st_size for f in (base / 'run-1').glob('*') if f.is_file()}})
        return result, calls, base, target, environment

    def test_private_one_shot_and_only_owned_children(self):
        result, calls, base, target, environment = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((base / 'armed').exists())
        self.assertEqual((base / 'run-1').stat().st_mode & 0o777, 0o700)
        self.assertTrue((base / 'run-1/11-complete.txt').is_file())
        self.assertFalse((base / 'run-1/.capture.tmp').exists())
        usernames = [args[2] for args in calls if args[0] == 'runuser']
        self.assertEqual(usernames, ['root', 'phablet', 'lightdm'])
        traces = [args for args in calls if args[0] == 'strace']
        self.assertEqual(len(traces), 3)
        self.assertFalse(any('-p' in args or '--attach' in args for args in traces))
        environments = [args for args in calls if args[0] == 'env']
        self.assertEqual(len(environments), 3)
        for args in environments:
            self.assertEqual(args[1], '-i')
            self.assertIn('LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libtls-padding.so', args)
            self.assertIn('-I', args)
            self.assertFalse(any('HYBRIS_LOGGING_TARGET=' in argument for argument in args))
        logcat_calls = [args for args in calls if args[0] == 'lxc-attach']
        self.assertEqual(len(logcat_calls), 2)
        for args in logcat_calls:
            for tag in ('HidlServiceManagement:V', 'vndksupport:V', 'libvndksupport:V',
                        'GrallocPassthrough:V', 'UTGraphicsProbe:V'):
                self.assertIn(tag, args)
        before = {path.name:path.read_bytes() for path in (base / 'run-1').iterdir()}
        rerun = subprocess.run(['/bin/sh', str(target)], env=environment, capture_output=True, timeout=5)
        self.assertNotEqual(rerun.returncode, 0)
        self.assertEqual(before, {path.name:path.read_bytes() for path in (base / 'run-1').iterdir()})

    def test_real_capture_overflow_and_timeout_keep_finite_reports(self):
        for scenario in ('overflow', 'timeout'):
            with self.subTest(scenario=scenario):
                result, calls, base, _, _ = self.execute(scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                logs = base / 'run-1'
                for name in ('05-root-probe.txt', '06-phablet-probe.txt', '07-lightdm-probe.txt'):
                    self.assertLessEqual((logs / name).stat().st_size, 524288)
                    if scenario == 'overflow':
                        data = (logs / name).read_bytes()
                        self.assertGreater(len(data), 524000)
                        self.assertIn(b'[output truncated; tail follows]', data)
                self.assertFalse((logs / '.capture.tmp').exists())
                summary = (logs / '01-summary.txt').read_text()
                if scenario == 'timeout':
                    self.assertIn('05-root-probe.txt exit=124', summary)
                self.assertIn('complete', summary)

    def test_unsafe_asset_refused_before_log_write(self):
        folder, base, target, environment = self.fixture()
        asset = base / 'assets/mapper-probe.py'
        asset.unlink()
        asset.symlink_to(ASSETS / 'mapper-probe.py')
        result = subprocess.run(['/bin/sh', str(target)], env=environment, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((base / 'run-1').exists())
        self.assertTrue((base / 'armed').is_file())

    def test_unit_cannot_order_graphical_boot_after_probe(self):
        unit = configparser.ConfigParser(interpolation=None)
        unit.read(ASSETS / 'ubuntu-touch-graphics-probe.service')
        self.assertEqual(unit['Service']['Type'], 'simple')
        self.assertEqual(unit['Service']['RuntimeMaxSec'], '150')
        self.assertEqual(unit['Service']['KillMode'], 'control-group')
        self.assertEqual(unit['Service']['Restart'], 'no')
        self.assertEqual(unit['Service']['LimitCORE'], '0')
        self.assertEqual(unit['Service']['LimitFSIZE'], '1M')
        self.assertNotIn('Before', unit['Unit'])
        self.assertNotIn('Requires', unit['Unit'])
        self.assertNotIn('lightdm', unit['Unit'].get('After', ''))
        self.assertEqual(unit['Unit']['After'], 'lxc-android-config.service')
        self.assertEqual(unit['Unit']['Wants'], 'lxc-android-config.service')
        self.assertEqual(unit['Unit']['ConditionPathExists'], '/userdata/ubuntu-touch-graphics-probe-1/armed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args, remaining = parser.parse_known_args()
    source_pins = {name:hashlib.sha256((ASSETS/name).read_bytes()).hexdigest()
                   for name in ('mapper-probe.py', 'probe.sh', 'ubuntu-touch-graphics-probe.service')}
    suite = unittest.main(argv=[sys.argv[0], *remaining], exit=False)
    stable = all(hashlib.sha256((ASSETS/name).read_bytes()).hexdigest() == value
                 for name, value in source_pins.items())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'schema': 1, 'success': suite.result.wasSuccessful() and stable,
            'tests_run': suite.result.testsRun, 'failures': len(suite.result.failures),
            'errors': len(suite.result.errors), 'host_compiled_ctypes_fixture': True,
            'actual_android_or_handset_executed': False, 'fixture_only_userdata_and_process_boundaries': True,
            'fixture_socket_readiness_boundary': 'private ordinary file; no Unix socket syscall available',
            'sources_unchanged_during_tests': stable, 'source_sha256': source_pins,
            'cases': RESULTS}, indent=2) + '\n')
    raise SystemExit(0 if suite.result.wasSuccessful() and stable else 1)
