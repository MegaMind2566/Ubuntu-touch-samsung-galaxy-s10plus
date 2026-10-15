"""Fixture checks for BOOT 6 observation; never access a handset or mount.

With --qemu and --cpio, execute the extracted, exact ARM64 BusyBox shell and
applets. Without these arguments, host POSIX-shell fixtures are explicit.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parents[1] / "tools/boot-observer"


def shquote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu')
    parser.add_argument('--cpio', type=Path)
    parser.add_argument('--repository', type=Path)
    args = parser.parse_args()
    assert bool(args.qemu) == bool(args.cpio)
    with tempfile.TemporaryDirectory(prefix='ut-post-observer-') as temp:
        root = Path(temp)
        backend = ''
        if args.qemu:
            import sys
            sys.path.insert(0, str(args.repository / 'scripts'))
            from prepare_boot_diagnostic import entries
            items = entries(args.cpio.read_bytes())
            entry = next(item for item in items if item['name'] == 'bin/busybox')
            peers = [item['data'] for item in items if item['data']
                     and item['values'][0] == entry['values'][0]
                     and item['values'][7:9] == entry['values'][7:9]]
            assert len(peers) == 1
            binary = root / 'busybox-arm64'
            binary.write_bytes(peers[0])
            binary.chmod(0o700)
            backend = shquote(shutil.which(args.qemu)) + ' ' + shquote(binary)
            shell = [shutil.which(args.qemu), str(binary), 'sh']
        else:
            shell = ['/bin/sh']
        bridge = root / 'bb'
        bridge.write_text('#!/bin/sh\n'
            'if [ "$1" = dmesg ]; then printf "fixture kernel retained\\n"; exit 0; fi\n'
            + ('exec ' + backend + ' "$@"\n' if backend else 'exec "$@"\n'))
        bridge.chmod(0o700)
        for name in ('post-handoff-functions', 'post-watch'):
            subprocess.run([*shell, '-n', str(HERE / name)], check=True)
        source = (HERE / 'post-watch').read_text()
        assert 'FIFO' not in source and 'sync' not in source
        assert 'kill -TERM "$observer_pid"' in source
        assert '$BB" mount' not in source and '$BB" reboot' not in source
        for case, late_proc, deadline in [('normal', False, False),
                                          ('late-proc', True, False),
                                          ('deadline', False, True)]:
            folder = root / case
            folder.mkdir()
            ram = folder / '.ut-boot-6.fixture'
            ram.mkdir(mode=0o700)
            (ram / 'busybox').write_bytes(bridge.read_bytes())
            (ram / 'busybox').chmod(0o700)
            target = folder / 'userdata/ubuntu-touch-boot-6/run-1'
            target.mkdir(parents=True, mode=0o700)
            proc = folder / 'proc'
            (proc / '1/task/1').mkdir(parents=True)
            (proc / 'uptime').write_text('10.5 8.0\n')
            (proc / 'cmdline').write_text('init=/init root=fixture\n')
            (proc / 'mounts').write_text('fixture / ext4 ro 0 0\n')
            (proc / '1/cmdline').write_bytes(b'/sbin/init\0')
            for name, value in [('wchan', 'fixture_wait\n'), ('stack', 'fixture_stack\n'),
                                ('cgroup', '1:name=systemd:/\n'), ('task/1/children', '')]:
                (proc / '1' / name).write_text(value)
            (proc / '1/exe').symlink_to('/usr/lib/systemd/systemd')
            status = proc / '1/status'
            if not late_proc:
                status.write_text('Name:\tsystemd\nState:\tS\n')
            journals = folder / 'journals/machine-id'
            journals.mkdir(parents=True)
            (journals / 'system.journal').write_bytes(b'journal header fixture')
            patched = source.replace('/dev/.ut-boot-6.', str(folder / '.ut-boot-6.'))
            # CI runs unprivileged; map only the fixture's expected owner.
            # The firmware helper retains its strict UID 0 guard unchanged.
            patched = patched.replace(' = 0:700 ]', f' = {os.getuid()}:700 ]')
            patched = patched.replace('/userdata/', str(folder / 'userdata') + '/')
            patched = patched.replace('/proc/', str(proc) + '/')
            patched = patched.replace('/run/log/journal', str(journals.parent))
            patched = patched.replace('/var/log/journal', str(folder / 'missing-journals'))
            # Exercise completion with five samples rather than repeating 33
            # expensive emulated process snapshots on a shared CI runner.
            # The firmware source and its 120-second deadline stay unchanged.
            patched = patched.replace('[ "$sample" -lt 33 ]', '[ "$sample" -lt 5 ]')
            patched = patched.replace('"$BB" sleep 120', '"$BB" sleep ' + ('3' if deadline else '60'))
            patched = patched.replace('"$BB" sleep "$delay"', '"$BB" sleep ' + ('10' if deadline else '0.01'))
            assert '[ "$sample" -lt 5 ]' in patched and '[ "$sample" -lt 33 ]' not in patched
            script = folder / 'watch'
            script.write_text(patched)
            proc_release = None
            proc_release_stop = threading.Event()
            proc_marker_seen = threading.Event()
            proc_release_errors = []
            if late_proc:
                def release_proc_after_wait_marker():
                    marker_deadline = time.monotonic() + 10
                    while not proc_release_stop.is_set():
                        try:
                            state = (target / 'observer-state.txt').read_text()
                        except FileNotFoundError:
                            state = ''
                        if 'awaiting moved proc' in state:
                            try:
                                status.write_text('Name:\tsystemd\nState:\tS\n')
                            except OSError as error:
                                proc_release_errors.append(str(error))
                            else:
                                proc_marker_seen.set()
                            return
                        if time.monotonic() >= marker_deadline:
                            break
                        proc_release_stop.wait(.005)
                    proc_release_errors.append('awaiting moved proc marker was not observed')
                proc_release = threading.Thread(target=release_proc_after_wait_marker)
                proc_release.start()
            started = time.monotonic()
            try:
                subprocess.run([*shell, str(script), str(ram), str(target)],
                               check=True, timeout=15 if deadline else 70)
            finally:
                proc_release_stop.set()
                if proc_release:
                    proc_release.join()
            if late_proc:
                assert proc_marker_seen.is_set() and not proc_release_errors, (
                    'late-proc did not resume after its wait marker', proc_release_errors)
            elapsed = time.monotonic() - started
            assert not ram.exists(), case + ': private RAM helper cleanup'
            state = (target / 'observer-state.txt').read_text()
            assert ('time-limit' if deadline else 'sample-limit') in state, (case, state)
            assert elapsed < 8 if deadline else elapsed < 70
            if deadline:
                # A deliberately tiny deadline can interrupt the first sample.
                # Its contract is timely observer exit and private RAM cleanup.
                continue
            assert 'fixture_wait' in (target / 'post-tasks.txt').read_text()
            assert '/usr/lib/systemd/systemd' in (target / 'post-timeline.txt').read_text()
            assert 'init=/init' in (target / 'post-cmdline.txt').read_text()
            assert 'fixture kernel retained' in (target / 'post-kernel.txt').read_text()
            assert 'system.journal' in (target / 'post-journal-inventory.txt').read_text()
            for name in ('post-tasks.txt', 'post-mounts.txt', 'post-journal-inventory.txt'):
                assert (target / name).stat().st_size <= 65536
            assert (target / 'post-timeline.txt').stat().st_size <= 33 * 1024
        # Exercise preparation guards, actual copies/modes, and closure of the
        # persistent trace descriptors. Only chroot itself is a mocked boundary.
        folder = root / 'prepare'
        dev = folder / 'root/dev'
        dev.mkdir(parents=True)
        (dev / 'sda31').write_bytes(b'fixture userdata node')
        (dev / 'null').symlink_to('/dev/null')
        target = folder / 'root/userdata/ubuntu-touch-boot-6/run-1'
        target.mkdir(parents=True, mode=0o700)
        target.parent.chmod(0o700)
        mounts = folder / 'mounts'
        mounts.write_text(f'{dev}/sda31 {folder}/root/userdata ext4 rw 0 0\n'
                          f'udev {dev} devtmpfs rw,nosuid 0 0\n')
        probe = folder / 'probe.py'
        probe.write_text('import json,os,sys\nfrom pathlib import Path\n'
                         'result={"arguments":sys.argv[1:],"fds":{}}\n'
                         'for fd in Path("/proc/self/fd").iterdir():\n'
                         ' try: result["fds"][fd.name]=os.readlink(fd)\n'
                         ' except OSError: pass\n'
                         'Path(os.environ["UT_POST_PROBE"]).write_text(json.dumps(result))\n')
        import sys
        launch_bridge = folder / 'bb'
        launch_bridge.write_text('#!/bin/sh\n'
            'if [ "$1" = chroot ]; then shift; exec ' + shquote(sys.executable)
            + ' ' + shquote(probe) + ' "$@"; fi\n'
            + ('exec ' + backend + ' "$@"\n' if backend else 'exec "$@"\n'))
        launch_bridge.chmod(0o700)
        prepare = (HERE / 'post-handoff-functions').read_text()
        prepare = prepare.replace(' = 0:700 ]', f' = {os.getuid()}:700 ]')
        prepare = prepare.replace('/root', str(folder / 'root'))
        prepare = prepare.replace('/bin/busybox', str(launch_bridge))
        prepare = prepare.replace('/proc/mounts', str(mounts))
        prepare = prepare.replace('/ut-boot-post-watch', str(HERE / 'post-watch'))
        script = folder / 'prepare.sh'
        environment = dict(os.environ, UT_POST_PROBE=str(folder / 'probe.json'))
        def prepare_run(run):
            script.write_text(prepare + '\nexec 8<' + shquote(mounts)
                              + '\nexec 9<' + shquote(mounts)
                              + '\nut_boot_post_handoff_start ' + shquote(run) + '\n')
            subprocess.run([*shell, str(script)], env=environment, check=True, timeout=10)
        prepare_run('run-6')
        assert not list(dev.glob('.ut-boot-6.*'))
        target.chmod(0o755)
        prepare_run('run-1')
        assert not list(dev.glob('.ut-boot-6.*'))
        target.chmod(0o700)
        prepare_run('run-1')
        for _ in range(100):
            if (folder / 'probe.json').is_file():
                break
            time.sleep(.02)
        result = json.loads((folder / 'probe.json').read_text())
        assert result['arguments'][0] == str(folder / 'root')
        assert result['arguments'][1].startswith('/dev/.ut-boot-6.')
        assert '8' not in result['fds'] and '9' not in result['fds']
        ram = next(dev.glob('.ut-boot-6.*'))
        assert (ram / 'busybox').read_bytes() == launch_bridge.read_bytes()
        assert (ram / 'watch').read_bytes() == (HERE / 'post-watch').read_bytes()
        assert (ram.stat().st_mode & 0o777) == 0o700
        print(json.dumps({'host_posix_fixtures': not bool(args.qemu),
                          'actual_arm64_busybox_fixtures': bool(args.qemu),
                          'sample_completion': True, 'late_proc_mount': True,
                          'independent_deadline': True, 'bounded_outputs': True,
                          'private_ram_cleanup': True, 'preparation_guards': True,
                          'old_trace_fds_closed_before_chroot': True,
                          'fixture_owner_uid': os.getuid(),
                          'firmware_owner_guard_uid': 0,
                          'chroot_boundary_in_test': 'mocked'}))


if __name__ == '__main__':
    main()
