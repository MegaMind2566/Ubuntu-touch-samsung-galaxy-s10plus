"""Check BOOT 6 preservation, actual ARM64 shell logging and read-only collection."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from ubuntu_boot_handoff import (ubuntu_initramfs,original_image,entries,image_kernel,
    PREVIOUS_SHA256,embedded_archive,BOOT_CMDLINE)
from test_early_boot_diagnostic import force_guard


def shell_checks(qemu,payload,folder):
    files={i['name']:i for i in entries(payload)};bb=files['bin/busybox']
    peers=[i['data'] for i in files.values() if i['values'][0]==bb['values'][0]
           and i['values'][7:9]==bb['values'][7:9] and i['data']]
    assert len(peers)==1
    binary=folder/'busybox';binary.write_bytes(peers[0]);binary.chmod(0o700)
    wrapper=folder/'bb'
    wrapper.write_text('#!/bin/sh\nexec '+shutil.which(qemu)+' '+str(binary)+' "$@"\n');wrapper.chmod(0o700)
    for name in ['init','scripts/halium','scripts/functions','scripts/init-bottom/udev','ut-boot-functions',
                 'ut-boot-post-watch','ut-boot-hwc-wait','ut-boot-android-profile-fix']:
        path=folder/name.replace('/','-');path.write_bytes(files[name]['data'])
        subprocess.run([qemu,str(binary),'sh','-n',str(path)],check=True)
    helper=files['ut-boot-functions']['data'].decode()
    original_helper=helper
    assert '/bin/busybox sync' not in helper
    # Real ARM64 awk must retain fragmented shell lines, flush each line and
    # continue consuming input after the exact 4 MiB file cap.
    awk=folder/'trace.awk';awk.write_bytes(files['ut-boot-trace.awk']['data'])
    source=b'UT_BOOT_6: + printf hello\n'+b'x'*511+b'\n'
    output=subprocess.run([qemu,str(binary),'awk','-f',str(awk)],input=source*9000,capture_output=True,check=True).stdout
    assert output.startswith(source) and len(output)<=4194304
    assert output.endswith(b'UT_BOOT_6: trace limit reached; remaining output discarded\n')
    mounts=folder/'fixture-mounts';kmsg=folder/'fixture-kmsg'
    physical_data=folder/'physical-data';physical_data.write_text('regular-file fixture, not a block device')
    moved_data=folder/'root-dev-data';moved_data.write_text('same permitted userdata path after the devtmpfs move')
    physical_system=folder/'physical-system';physical_system.write_text('different regular-file fixture')
    first=folder/'first';second=folder/'second';first.mkdir();second.symlink_to(first,target_is_directory=True)
    # Execute the real helper under ARM64 BusyBox with only device paths redirected
    # to temporary fixtures. No host mount or physical phone is accessed.
    helper=helper.replace('/bin/busybox',str(wrapper)).replace('/proc/mounts',str(mounts))
    helper=helper.replace('for candidate in /tmpmnt /root/userdata;',f'for candidate in {first} {second};')
    helper=helper.replace('/dev/kmsg',str(kmsg))
    # BusyBox readlink -f requires this final path to exist. A runner has no
    # phone /dev/sda31, so map the expected source and mount text consistently.
    helper=helper.replace('/root/dev/sda31',str(moved_data)).replace('/dev/sda31',str(physical_data))
    # Stage fixtures exercise the actual guards without starting timers.
    # The real passive timer is exercised separately below with regular files.
    helper+='\nut_boot_wait_watch() { :; }\n'
    script=folder/'fixture.sh'
    def invoke(extra):
        script.write_text(helper+'\n'+extra+'\n')
        subprocess.run([qemu,str(binary),'sh',str(script)],check=True)
    mounts.write_text(str(physical_data)+' '+str(first)+' ext4 rw 0 0\n')
    for _ in range(6):invoke('ut_boot_stage root-mounted')
    base=first/'ubuntu-touch-boot-6'
    assert sorted(p.name for p in base.iterdir())==['run-'+str(n) for n in range(1,6)]
    for n in range(1,6):
        assert (base/f'run-{n}/stage.txt').read_text()=='UT_BOOT_6: PID 1 STARTED\nUT_BOOT_6: stage=root-mounted\n'
    saved=(base/'run-1/stage.txt').read_bytes()
    invoke('ut_boot_stage should-not-overwrite')
    assert (base/'run-1/stage.txt').read_bytes()==saved
    shutil.rmtree(base)
    # An existing symlink cannot redirect log creation into an unrelated folder.
    outside=folder/'outside';outside.mkdir();base.symlink_to(outside,target_is_directory=True)
    invoke('ut_boot_stage symlink-refused');assert not list(outside.iterdir());base.unlink()
    mounts.write_text(str(physical_system)+' '+str(first)+' ext4 ro 0 0\n')
    invoke('ut_boot_stage wrong-partition');assert not base.exists()
    # A mount move retains the same owned run name and updates the same log set.
    mounts.write_text(str(physical_data)+' '+str(first)+' ext4 rw 0 0\n')
    invoke('ut_boot_stage userdata-mounted\nprintf "'+str(physical_data)+' '+str(second)+' ext4 rw 0 0\\n" >'+str(mounts)+'\nut_boot_stage userspace-handoff')
    assert (base/'run-1/stage.txt').read_text().endswith('stage=userspace-handoff\n')
    assert len(list(base.iterdir()))==1
    # Moving /dev changes the canonical node path as well as Data's mount path.
    # A matching raw node still records the post-udev and handoff stages.
    shutil.rmtree(base)
    mounts.write_text(str(physical_data)+' '+str(first)+' ext4 rw 0 0\n')
    invoke('ut_boot_stage root-mounted\n'+str(wrapper)+' rm '+str(physical_data)+'\n'+str(wrapper)+' ln -s '+str(moved_data)+' '+str(physical_data)+'\nprintf "'+str(physical_data)+' '+str(second)+' ext4 rw 0 0\\n" >'+str(mounts)+'\nut_boot_stage init-bottom-complete\nut_boot_stage userspace-handoff')
    assert (base/'run-1/stage.txt').read_text().endswith('stage=userspace-handoff\n')
    assert len(list(base.iterdir()))==1
    # Exercise the actual FIFO/awk bridge and descriptor-based trace reads.
    # /run is moved while both writer and reader stay open on the same file.
    run=folder/'run';run.mkdir();moved=folder/'moved-run';trace_target=folder/'traces';trace_target.mkdir()
    transport=original_helper.replace('/bin/busybox',str(wrapper)).replace('/dev/kmsg',str(kmsg))
    transport=transport.replace('/run/initramfs',str(run)).replace('/ut-boot-trace.awk',str(awk))
    script.write_text(transport+'\nut_boot_trace_start\nPS4="UT_BOOT_6: + "\nset -x\n'
        'echo full-line-retained\nprintf fragmented-\nprintf "line\\n"\n'
        'exec >'+str(kmsg)+' 2>&1\nut_boot_trace_resume\necho trace-survives-halium-redirection\n'
        +str(wrapper)+' mv '+str(run)+' '+str(moved)+'\n'+str(wrapper)+' sleep 0.1\n'
        'set +x\nut_boot_trace_copy '+str(trace_target)+'\nut_boot_trace_stop\n')
    subprocess.run([qemu,str(binary),'sh',str(script)],check=True,timeout=15)
    trace=(trace_target/'trace.log').read_text()
    assert 'UT_BOOT_6: + echo full-line-retained' in trace and 'fragmented-' in trace and 'line\n' in trace
    assert 'trace-survives-halium-redirection' in trace
    # The passive watcher uses a Data cwd even after its old path disappears.
    proc=folder/'proc';(proc/'1/task/1').mkdir(parents=True)
    for name,value in [('uptime','20.0 0.0\n'),('1/status','Name:\tinit\nState:\tS\n'),
                       ('1/wchan','fixture_wait\n'),('1/stack','fixture_stack\n'),('1/task/1/children','')]:
        (proc/name).write_text(value)
    watch=folder/'watch';watch.mkdir();newwatch=folder/'watch-moved'
    observer=transport.replace('/proc/1',str(proc/'1')).replace('/proc/uptime',str(proc/'uptime'))
    observer=observer.replace(str(wrapper)+' sleep 10',str(wrapper)+' sleep 0.05')
    script.write_text(observer+'\nexec 8<'+str(moved/'ubuntu-init.trace')+'\n'
        'ut_boot_wait_watch '+str(watch)+' &\npid=$!\n'+str(wrapper)+' sleep 0.02\n'
        +str(wrapper)+' mv '+str(watch)+' '+str(newwatch)+'\nwait "$pid"\n')
    subprocess.run([qemu,str(binary),'sh',str(script)],check=True,timeout=15)
    assert 'wait-sample=12' in (newwatch/'wait-tasks.log').read_text()
    assert 'fixture_wait' in (newwatch/'wait-tasks.log').read_text()
    assert 'full-line-retained' in (newwatch/'trace.log').read_text()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path);p.add_argument('--qemu')
    a=p.parse_args();payload=ubuntu_initramfs(original_image());files={i['name']:i for i in entries(payload)}
    assert len(files)==352 and b'UT_BOOT_6: PID 1 STARTED' in files['init']['data']
    original={i['name']:i for i in entries(gzip.decompress(original_image()[49106944:49106944+4108120]))}
    changed={n for n in original if original[n]['data']!=files[n]['data']}
    assert changed=={'init','scripts/halium','scripts/functions','scripts/init-bottom/udev'}
    # The original mount/rootfs/container code remains. Only its automatic
    # repair/resize call block is removed; no replacement repair is introduced.
    halium=files['scripts/halium']['data']
    assert b'e2fsck -y $path' not in halium and b'resize_userdata_if_needed ${path}' not in halium
    assert b'mount -o discard,$OPTIONS $path /tmpmnt' in halium
    assert b'/halium-system/var/lib/lxc/android/$ANDROID_IMAGE' in halium
    assert b'exec &>/dev/kmsg' not in halium and b'ut_boot_trace_resume' in halium
    assert b'</dev/null >/dev/kmsg 2>&1' in files['init']['data']
    assert b'<${rootmnt}/dev/console' not in files['init']['data']
    assert b'ut_boot_post_handoff_start "$UT_BOOT_LOG_NAME"' in files['init']['data']
    assert b'ut_boot_hwc_prepare' in files['init']['data']
    assert b'ut_boot_profiles_prepare "${UT_BOOT_LOG_NAME:-none}"' in files['init']['data']
    assert b'BOOT 6 RAM profiles could not be prepared' in files['init']['data']
    assert 'systemd.unified_cgroup_hierarchy=0' in BOOT_CMDLINE
    assert b'UT_DIAG_' not in files['init']['data'] and 'ut-diag-display' not in files
    spec=importlib.util.spec_from_file_location('package_handoff',ROOT/'scripts/package-ubuntu-boot-handoff.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    lock={'boot_sha256':'a'*64,'boot_bytes':57000000}
    if a.images:
        image,previous,lock=package.validate(a.images)
        assert embedded_archive(image_kernel(image),payload)[1]<4500000
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d)
        if a.qemu:
            shell_checks(a.qemu,payload,folder)
            cpio=folder/'source-check.cpio';cpio.write_bytes(payload)
            for test in ('test_post_observer.py','test_hwc_readiness.py','test_boot_profiles.py'):
                subprocess.run([sys.executable,str(ROOT/'tests'/test),'--qemu',a.qemu,
                    '--cpio',str(cpio),'--repository',str(ROOT)],check=True)
        if a.images:
            kernel_source=ROOT/'build/ubuntu-handoff/workdir/downloads/kernel-samsung-exynos9820'
            usb_original=folder/'original-configfs.c'
            usb_original.write_bytes(subprocess.check_output(['git','-C',str(kernel_source),
                'show','b9b70b29c94c41365704fcc2ed33be09b4617907:drivers/usb/gadget/configfs.c']))
            subprocess.run([sys.executable,str(ROOT/'tests/test_usb_configfs.py'),
                '--source',str(usb_original)],check=True)
            force_guard(ROOT/'build/ubuntu-handoff/workdir/downloads/kernel-samsung-exynos9820/init/initramfs.c',folder)
            bad=folder/'bad';shutil.copytree(a.images,bad)
            changed=bytearray(image);changed[2048+128]^=1
            (bad/'boot.img').write_bytes(changed)
            changed_lock=dict(lock);changed_lock['boot_sha256']=hashlib.sha256(changed).hexdigest()
            (bad/'ubuntu-boot-handoff.lock.json').write_text(json.dumps(changed_lock))
            try:package.validate(bad)
            except ValueError:pass
            else:raise AssertionError('corrupt kernel accepted')
            shutil.rmtree(bad);shutil.copytree(a.images,bad)
            (bad/'kernel.config').write_text((bad/'kernel.config').read_text().replace('CONFIG_INITRAMFS_FORCE=y','# CONFIG_INITRAMFS_FORCE is not set'))
            try:package.validate(bad)
            except ValueError:pass
            else:raise AssertionError('false compiled configuration accepted')
        collect=types.ModuleType('handoff_collector');collect.__file__=str(ROOT/'scripts/collect-ubuntu-handoff.py')
        exec(compile(package.collector(lock),'collector','exec'),collect.__dict__)
        cases=['success','missing-logs','old-marker','wrong-boot','wrong-device','tools-unavailable','usb-unavailable']
        for case in cases:
            target=folder/case;target.mkdir();operations=[]
            def verifier(root):
                if case=='tools-unavailable':raise ValueError('local_tools_unavailable')
            def runner(exe,name):
                operations.append(name);args=collect.command_for(name)
                assert args[0]=='-d' and not any(v in ' '.join(args) for v in ['dd ','mount ','umount ','mkfs','resize','reboot','rm '])
                outputs={'state':'device\n','uid':'0\n','properties':'ro.twrp.version|3.7.0_9-2\nro.product.device|beyond2lte\nro.hardware|exynos9820\nro.bootloader|G975FXXSGHWC1\n',
                    'run-1-stage':'UT_BOOT_6: PID 1 STARTED\nUT_BOOT_6: stage=userspace-handoff\nandroidboot.serialno=PRIVATE_TEST_SERIAL\n',
                    'run-1-kernel':'Linux version 4.14.280-boot3\n','boot-hash':lock['boot_sha256']+'  -\n'}
                v={'exit_code':0 if name in outputs else 1,'timed_out':False,'stdout':outputs.get(name,''),'stderr':''}
                if case=='missing-logs' and name.startswith('run-'):v.update(exit_code=1,stdout='')
                if case=='old-marker' and name=='run-1-stage':v['stdout']=v['stdout'].replace('UT_BOOT_6','UT_DIAG_2')
                if case=='wrong-boot' and name=='boot-hash':v['stdout']=PREVIOUS_SHA256+'  -\n'
                if case=='wrong-device' and name=='properties':v['stdout']=v['stdout'].replace('beyond2lte','wrong')
                if case=='usb-unavailable' and name=='state':v.update(exit_code=1,stdout='',stderr='no devices')
                return v
            report,z=collect.collect(target,runner,verifier)
            assert report['boot_version']==6 and not report['ubuntu_touch_boot_verified'] and not report['partition_writes']
            if case in ('wrong-device','tools-unavailable','usb-unavailable'):
                assert not report['success'] and not any(n.startswith('run-') for n in operations)
            else:
                assert report['success'] and report['boot_matches']==(case!='wrong-boot')
                assert bool(report['attempts'])==(case!='missing-logs')
                if report['attempts']:assert report['attempts'][0]['pid1_marker_found']==(case!='old-marker')
            with zipfile.ZipFile(z) as archive:
                assert 'PRIVATE_TEST_SERIAL' not in '\n'.join(archive.read(n).decode() for n in archive.namelist())
            assert z.name=='ubuntu-boot-6-log-report.zip'
    result={'schema':1,'boot_version':6,'boot_sha256':lock['boot_sha256'],
        'original_entries_preserved_except_four_instrumented_scripts':True,'embedded_external_cpio_equal':bool(a.images),
        'trace_bounded_and_drains_after_cap':bool(a.qemu),
        'actual_arm64_trace_transport_and_passive_wait_watch':bool(a.qemu),'pid1_global_sync_removed':True,
        'actual_arm64_post_devtmpfs_move_logging':bool(a.qemu),
        'actual_arm64_trace_survives_halium_redirect':bool(a.qemu),
        'post_handoff_observer_cases':8 if a.qemu else 0,
        'hwc_readiness_and_ram_override_cases':26 if a.qemu else 0,
        'ram_profile_and_android_prestart_fixtures':bool(a.qemu),
        'usb_null_guard_compiled_helper_cases':8 if a.images else 0,
        'console_redirection_removed_from_final_exec':True,
        'cgroup_v1_controller_compatibility_requested':True,
        'peripheral_configuration_preserved':bool(a.images),'actual_arm64_shell_syntax':bool(a.qemu),
        'actual_arm64_logging_guards_and_mount_move':bool(a.qemu),'actual_source_force_guard_cases':4 if a.images else 0,
        'corrupt_kernel_and_false_config_rejected':bool(a.images),'collector_mocked_cases':cases,
        'phone_accessed':False,'ubuntu_touch_boot_verified':False}
    if a.images:(a.images/'ubuntu-handoff-tests.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
