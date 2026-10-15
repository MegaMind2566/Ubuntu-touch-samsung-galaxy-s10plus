"""BOOT 6 HWC readiness and RAM-only overlay fixtures. No handset/mount access.

--qemu and --cpio exercise the exact static ARM64 BusyBox from BOOT 4.
Only filesystem-mount boundaries and Android getprop are fixtures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parents[1] / "tools/boot-observer"
ORIGINAL_SHA = 'b56435dc9766c4e8caa50ce8af95dfb369240ff0e33e90efc7f6d95e2dd00fcb'


def quote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', required=True)
    parser.add_argument('--cpio', type=Path, required=True)
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repository / 'scripts'))
    from prepare_boot_diagnostic import entries
    values = entries(args.cpio.read_bytes())
    entry = next(e for e in values if e['name'] == 'bin/busybox')
    peers = [e['data'] for e in values if e['data'] and e['values'][0] == entry['values'][0]
             and e['values'][7:9] == entry['values'][7:9]]
    assert len(peers) == 1
    original = (Path(__file__).resolve().parent / 'fixtures/wait-for-hwc-original.conf').read_bytes()
    assert hashlib.sha256(original).hexdigest() == ORIGINAL_SHA
    observations = []
    with tempfile.TemporaryDirectory(prefix='ut-hwc-') as temporary:
        folder = Path(temporary)
        binary = folder / 'busybox-arm64'
        binary.write_bytes(peers[0])
        binary.chmod(0o700)
        runtime = shutil.which(args.qemu)
        if runtime is None:
            raise ValueError('qemu_runtime_not_found')
        backend = [runtime, str(binary)]
        shell = [*backend, 'sh']
        ram = folder / 'ram'
        ram.mkdir(mode=0o700)
        bridge = ram / 'busybox'
        bridge.write_text('#!/bin/sh\nexec ' + ' '.join(quote(p) for p in backend) + ' "$@"\n')
        bridge.chmod(0o700)
        getprop = folder / 'getprop'
        properties = folder / 'properties'
        status = folder / 'getprop-status'
        getprop.write_text('#!/bin/sh\ncat ' + quote(properties) + '\nexit "$(cat ' + quote(status) + ')"\n')
        getprop.chmod(0o700)
        wait = ram / 'wait'
        source = (HERE / 'hwc-wait').read_text()
        wait.write_text(source.replace('/usr/bin/getprop', str(getprop)))
        subprocess.run([*shell, '-n', str(wait)], check=True)
        cases = [
            ('hidl-2-2', '[init.svc.vendor.hwcomposer-2-2]: [running]\n', 0, True),
            ('hidl-2-3', '[init.svc.vendor.hwcomposer-2-3]: [running]\n', 0, True),
            ('aidl-composer', '[init.svc.vendor.graphics.composer-default]: [running]\n', 0, True),
            ('aidl-qualified', '[init.svc.android.hardware.graphics.composer3-service]: [running]\n', 0, True),
            ('multiple-running', '[init.svc.vendor.hwcomposer-2-2]: [stopped]\n'
                                  '[init.svc.vendor.hwcomposer-2-3]: [running]\n', 0, True),
            ('no-service', '[ro.product.device]: [beyond2lte]\n', 0, False),
            ('stopped', '[init.svc.vendor.hwcomposer-2-3]: [stopped]\n', 0, False),
            ('restarting', '[init.svc.vendor.graphics.composer-default]: [restarting]\n', 0, False),
            ('unrelated-running', '[init.svc.vendor.surfaceflinger]: [running]\n', 0, False),
            ('pid-property', '[init.svc_debug_pid.vendor.hwcomposer-2-2]: [running]\n', 0, False),
            ('wrong-case', '[init.svc.vendor.hwcomposer-2-3]: [Running]\n', 0, False),
            ('trailing-junk', '[init.svc.vendor.hwcomposer-2-3]: [running]junk\n', 0, False),
            ('getprop-failure-with-running-output', '[init.svc.vendor.hwcomposer-2-2]: [running]\n', 1, False),
            ('empty', '', 0, False),
        ]
        for name, content, exit_code, expected in cases:
            properties.write_text(content)
            status.write_text(str(exit_code))
            result = subprocess.run([*shell, str(wait), '--ready'], capture_output=True, timeout=5)
            assert (result.returncode == 0) == expected, (name, result.returncode, result.stderr)
            observations.append({'readiness_case': name, 'ready': expected})
        # Actual wait must return with a running service and stay blocked otherwise.
        status.write_text('0')
        properties.write_text('[init.svc.vendor.hwcomposer-2-3]: [running]\n')
        subprocess.run([*shell, str(wait)], check=True, timeout=5)
        for name, content in [('unknown', ''), ('stopped', '[init.svc.vendor.hwcomposer-2-3]: [stopped]\n')]:
            properties.write_text(content)
            process = subprocess.Popen([*shell, str(wait)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                process.communicate(timeout=.25)
                raise AssertionError(name + ': readiness wait exited prematurely')
            except subprocess.TimeoutExpired:
                process.terminate()
                process.communicate(timeout=5)
            observations.append({'waiting_case': name, 'wait_not_bypassed': True})

        # Real ARM64 shell/awk/hash/copy/mode guards; mount itself is mocked.
        function = (HERE / 'hwc-functions').read_text()
        for scenario in ['success', 'wrong-hash', 'symlink-target', 'wrong-dev-fs',
                         'root-rw', 'already-mounted', 'copy-failure', 'bind-failure',
                         'readback-mismatch', 'unmount-failure']:
            case = folder / scenario
            dev = case / 'root/dev'
            dev.mkdir(parents=True)
            target = case / 'root/opt/halium-overlay/usr/lib/systemd/system/lightdm.service.d/wait-for-hwc.conf'
            target.parent.mkdir(parents=True)
            target.write_bytes(original if scenario != 'wrong-hash' else b'changed original\n')
            if scenario == 'symlink-target':
                target.unlink()
                saved = target.with_name('symlink-original')
                saved.write_bytes(original)
                target.symlink_to(saved)
            mounts = case / 'mounts'
            mounts.write_text(f'udev {dev} {"tmpfs" if scenario == "wrong-dev-fs" else "devtmpfs"} rw,nosuid 0 0\n'
                              f'/dev/sda25 {case}/root ext4 {"rw" if scenario == "root-rw" else "ro"} 0 0\n'
                              + (f'udev {target} devtmpfs rw 0 0\n' if scenario == 'already-mounted' else ''))
            calls = case / 'calls.jsonl'
            # Forward all real applets to the exact ARM64 BusyBox. Intercept only
            # copying failure and the mount/unmount operating-system boundaries.
            shim = case / 'shim.py'
            shim.write_text('import json,os,pathlib,shutil,subprocess,sys\n'
                'case=pathlib.Path(' + repr(str(case)) + ')\n'
                'scenario=' + repr(scenario) + '\n'
                'name,*args=sys.argv[1:]\n'
                'with (case/"calls.jsonl").open("a") as f:f.write(json.dumps([name,*args])+"\\n")\n'
                'if name=="cp" and scenario=="copy-failure":sys.exit(1)\n'
                'if name=="mount":\n'
                ' assert args[:3]==["-n","-o","bind"] and len(args)==5,args\n'
                ' if scenario=="bind-failure":sys.exit(1)\n'
                ' shutil.copyfile(args[3],args[4])\n'
                ' if scenario in ["readback-mismatch","unmount-failure"]:pathlib.Path(args[4]).write_text("bad readback\\n")\n'
                ' sys.exit(0)\n'
                'if name=="umount":\n'
                ' if scenario=="unmount-failure":sys.exit(1)\n'
                ' pathlib.Path(args[0]).write_bytes(bytes.fromhex(' + repr(original.hex()) + '));sys.exit(0)\n'
                'sys.exit(subprocess.call(' + repr(backend) + '+[name,*args]))\n')
            bb = case / 'bb'
            bb.write_text('#!/bin/sh\nexec ' + quote(sys.executable) + ' ' + quote(shim) + ' "$@"\n')
            bb.chmod(0o700)
            prepared = function.replace('/root', str(case / 'root')).replace('/bin/busybox', str(bb))
            prepared = prepared.replace('/proc/mounts', str(mounts))
            prepared = prepared.replace('/ut-boot-hwc-wait', str(HERE / 'hwc-wait'))
            prepared = prepared.replace('>/dev/kmsg', '>' + quote(case / 'markers'))
            script = case / 'prepare.sh'
            script.write_text(prepared + '\nut_boot_hwc_prepare\n')
            subprocess.run([*shell, '-n', str(script)], check=True)
            result = subprocess.run([*shell, str(script)], capture_output=True, timeout=10)
            actions = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            directories = list(dev.glob('.ut-boot-6-hwc.*'))
            successful = scenario == 'success'
            assert (result.returncode == 0) == successful, (scenario, result.returncode, result.stderr)
            if successful:
                assert len(directories) == 1
                private = directories[0]
                assert private.stat().st_mode & 0o777 == 0o700
                assert (private / 'wait').stat().st_mode & 0o777 == 0o700
                assert (private / 'wait-for-hwc.conf').stat().st_mode & 0o777 == 0o400
                runtime = '/dev/' + private.name
                expected = original.decode().splitlines()
                expected[2] = f'ExecStartPre={runtime}/busybox sh {runtime}/wait'
                assert target.read_text() == '\n'.join(expected) + '\n'
                assert not any(action[0] == 'umount' for action in actions)
            elif scenario == 'unmount-failure':
                assert len(directories) == 1
                assert 'unconfirmed' in (case / 'markers').read_text()
            else:
                assert not directories, (scenario, directories)
                if scenario != 'wrong-hash':
                    assert target.read_bytes() == original
            if scenario in ['wrong-hash', 'symlink-target', 'wrong-dev-fs', 'root-rw', 'already-mounted']:
                assert not any(action[0] in ['mktemp', 'cp', 'chmod', 'mount', 'umount', 'rm', 'rmdir'] for action in actions), actions
            observations.append({'prepare_case': scenario, 'success': successful,
                                 'mount_boundaries_mocked': True})
        result = {'schema': 1, 'actual_arm64_busybox': True, 'busybox_sha256': hashlib.sha256(peers[0]).hexdigest(),
                  'phone_accessed': False, 'mounts_simulated': True, 'getprop_simulated': True,
                  'original_overlay_sha256': ORIGINAL_SHA, 'observations': observations, 'success': True}
        output = args.repository / 'out/hwc-readiness-tests.json'
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))


if __name__ == '__main__':
    main()
