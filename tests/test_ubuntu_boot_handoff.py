"""Check BOOT 3 preservation, actual ARM64 shell logging and read-only collection."""
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
    PREVIOUS_SHA256,embedded_archive)
from test_early_boot_diagnostic import force_guard


def shell_checks(qemu,payload,folder):
    files={i['name']:i for i in entries(payload)};bb=files['bin/busybox']
    peers=[i['data'] for i in files.values() if i['values'][0]==bb['values'][0]
           and i['values'][7:9]==bb['values'][7:9] and i['data']]
    assert len(peers)==1
    binary=folder/'busybox';binary.write_bytes(peers[0]);binary.chmod(0o700)
    wrapper=folder/'bb'
    wrapper.write_text('#!/bin/sh\nexec '+shutil.which(qemu)+' '+str(binary)+' "$@"\n');wrapper.chmod(0o700)
    for name in ['init','scripts/halium','scripts/functions','ut-boot-functions']:
        path=folder/name.replace('/','-');path.write_bytes(files[name]['data'])
        subprocess.run([qemu,str(binary),'sh','-n',str(path)],check=True)
    helper=files['ut-boot-functions']['data'].decode()
    mounts=folder/'fixture-mounts';kmsg=folder/'fixture-kmsg'
    physical_data=folder/'physical-data';physical_data.write_text('regular-file fixture, not a block device')
    physical_system=folder/'physical-system';physical_system.write_text('different regular-file fixture')
    first=folder/'first';second=folder/'second';first.mkdir();second.symlink_to(first,target_is_directory=True)
    # Execute the real helper under ARM64 BusyBox with only device paths redirected
    # to temporary fixtures. No host mount or physical phone is accessed.
    helper=helper.replace('/bin/busybox',str(wrapper)).replace('/proc/mounts',str(mounts))
    helper=helper.replace('for candidate in /tmpmnt /root/userdata;',f'for candidate in {first} {second};')
    helper=helper.replace('/dev/kmsg',str(kmsg))
    # BusyBox readlink -f requires this final path to exist. A runner has no
    # phone /dev/sda31, so map the expected source and mount text consistently.
    helper=helper.replace('/dev/sda31',str(physical_data))
    script=folder/'fixture.sh'
    def invoke(extra):
        script.write_text(helper+'\n'+extra+'\n')
        subprocess.run([qemu,str(binary),'sh',str(script)],check=True)
    mounts.write_text(str(physical_data)+' '+str(first)+' ext4 rw 0 0\n')
    for _ in range(6):invoke('ut_boot_stage root-mounted')
    base=first/'ubuntu-touch-boot-3'
    assert sorted(p.name for p in base.iterdir())==['run-'+str(n) for n in range(1,6)]
    for n in range(1,6):
        assert (base/f'run-{n}/stage.txt').read_text()=='UT_BOOT_3: PID 1 STARTED\nUT_BOOT_3: stage=root-mounted\n'
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


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path);p.add_argument('--qemu')
    a=p.parse_args();payload=ubuntu_initramfs(original_image());files={i['name']:i for i in entries(payload)}
    assert len(files)==348 and b'UT_BOOT_3: PID 1 STARTED' in files['init']['data']
    original={i['name']:i for i in entries(gzip.decompress(original_image()[49106944:49106944+4108120]))}
    changed={n for n in original if original[n]['data']!=files[n]['data']}
    assert changed=={'init','scripts/halium','scripts/functions'}
    # The original mount/rootfs/container code remains. Only its automatic
    # repair/resize call block is removed; no replacement repair is introduced.
    halium=files['scripts/halium']['data']
    assert b'e2fsck -y $path' not in halium and b'resize_userdata_if_needed ${path}' not in halium
    assert b'mount -o discard,$OPTIONS $path /tmpmnt' in halium
    assert b'/halium-system/var/lib/lxc/android/$ANDROID_IMAGE' in halium
    assert b'UT_DIAG_' not in files['init']['data'] and 'ut-diag-display' not in files
    spec=importlib.util.spec_from_file_location('package_handoff',ROOT/'scripts/package-ubuntu-boot-handoff.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    lock={'boot_sha256':'a'*64,'boot_bytes':57000000}
    if a.images:
        image,previous,lock=package.validate(a.images)
        assert embedded_archive(image_kernel(image),payload)[1]<4500000
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d)
        if a.qemu:shell_checks(a.qemu,payload,folder)
        if a.images:
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
                    'run-1-stage':'UT_BOOT_3: PID 1 STARTED\nUT_BOOT_3: stage=userspace-handoff\nandroidboot.serialno=PRIVATE_TEST_SERIAL\n',
                    'run-1-kernel':'Linux version 4.14.280-boot3\n','boot-hash':lock['boot_sha256']+'  -\n'}
                v={'exit_code':0 if name in outputs else 1,'timed_out':False,'stdout':outputs.get(name,''),'stderr':''}
                if case=='missing-logs' and name.startswith('run-'):v.update(exit_code=1,stdout='')
                if case=='old-marker' and name=='run-1-stage':v['stdout']=v['stdout'].replace('UT_BOOT_3','UT_DIAG_2')
                if case=='wrong-boot' and name=='boot-hash':v['stdout']=PREVIOUS_SHA256+'  -\n'
                if case=='wrong-device' and name=='properties':v['stdout']=v['stdout'].replace('beyond2lte','wrong')
                if case=='usb-unavailable' and name=='state':v.update(exit_code=1,stdout='',stderr='no devices')
                return v
            report,z=collect.collect(target,runner,verifier)
            assert report['boot_version']==3 and not report['ubuntu_touch_boot_verified'] and not report['partition_writes']
            if case in ('wrong-device','tools-unavailable','usb-unavailable'):
                assert not report['success'] and not any(n.startswith('run-') for n in operations)
            else:
                assert report['success'] and report['boot_matches']==(case!='wrong-boot')
                assert bool(report['attempts'])==(case!='missing-logs')
                if report['attempts']:assert report['attempts'][0]['pid1_marker_found']==(case!='old-marker')
            with zipfile.ZipFile(z) as archive:
                assert 'PRIVATE_TEST_SERIAL' not in '\n'.join(archive.read(n).decode() for n in archive.namelist())
            assert z.name=='ubuntu-boot-3-log-report.zip'
    result={'schema':1,'boot_version':3,'boot_sha256':lock['boot_sha256'],
        'original_entries_preserved_except_three_instrumented_scripts':True,'embedded_external_cpio_equal':bool(a.images),
        'peripheral_configuration_preserved':bool(a.images),'actual_arm64_shell_syntax':bool(a.qemu),
        'actual_arm64_logging_guards_and_mount_move':bool(a.qemu),'actual_source_force_guard_cases':4 if a.images else 0,
        'corrupt_kernel_and_false_config_rejected':bool(a.images),'collector_mocked_cases':cases,
        'phone_accessed':False,'ubuntu_touch_boot_verified':False}
    if a.images:(a.images/'ubuntu-handoff-tests.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
