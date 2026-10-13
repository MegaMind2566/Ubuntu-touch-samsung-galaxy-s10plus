"""Validate real BOOT 2/diagnostic bytes, ARM64 programs and collector boundaries."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_boot_diagnostic import entries, elf_static_arm64, PREVIOUS_SHA256
from inspect_stock_firmware import boot_header


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path,required=True)
    p.add_argument('--qemu',required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('package_diag',ROOT/'scripts/package-boot-diagnostic.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    image,previous,lock=package.validate(a.images)
    h=boot_header(image);ram=image[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]
    files={i['name']:i for i in entries(gzip.decompress(ram))}
    bb=files['bin/busybox'];peers=[i['data'] for i in files.values() if i['values'][0]==bb['values'][0] and i['values'][7:9]==bb['values'][7:9] and i['data']]
    assert len(peers)==1
    elf_static_arm64(peers[0])
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d);(folder/'busybox').write_bytes(peers[0]);(folder/'init').write_bytes(files['init']['data'])
        (folder/'display').write_bytes(files['ut-diag-display']['data'])
        (folder/'busybox').chmod(0o700);(folder/'display').chmod(0o700)
        subprocess.run([a.qemu,str(folder/'busybox'),'sh','-n',str(folder/'init')],check=True)
        subprocess.run([a.qemu,str(folder/'display'),'--self-test'],check=True)
        init=files['init']['data'].decode()
        assert '-o ro,noload,nosuid,nodev,noexec /dev/sda25' in init
        assert '-o ro,noload,nosuid,nodev,noexec /dev/sda26' in init
        for forbidden in ('$BB dd ','$BB mkfs','e2fsck ','resize2fs ','exec /ut-diag-original-init','telnetd','adbd','getty'):
            assert forbidden not in init
        assert 'echo 10c00000.dwc3 >"$G/UDC"' in init
        assert '$BB mkdir -m 0700 /data/ubuntu-touch-boot-diagnostic-1' in init
        # Corrupt independently meaningful image regions, even with a matching outer lock.
        for offset in (2048+128,20):
            changed=bytearray(image);changed[offset]^=1
            scratch=folder/'bad';scratch.mkdir(exist_ok=True)
            (scratch/'previous-boot-2.img').write_bytes(previous)
            (scratch/'diagnostic-boot.img').write_bytes(changed)
            changed_lock=dict(lock);changed_lock['boot_sha256']=hashlib.sha256(changed).hexdigest()
            (scratch/'boot-diagnostic.lock.json').write_text(json.dumps(changed_lock))
            try: package.validate(scratch)
            except ValueError: pass
            else: raise AssertionError('corrupt kernel/header accepted')
        # Template verification uses the generated pins and installed raw image.
        verifier=package.render((ROOT/'scripts/verify_boot_update_2.py.in').read_text()
            .replace('439b535193a8e6315e3da3884755db49b04794c28d5e06686fc595dfab8f5a4c',lock['ramdisk_sha256'])
            .replace('rsize!=4108120','rsize!='+str(lock['ramdisk_bytes'])),lock)
        mod=types.ModuleType('verified_diagnostic');exec(compile(verifier,'verifier','exec'),mod.__dict__)
        (folder/'boot.img').write_bytes(image);assert mod.verify(folder/'boot.img')
        (folder/'previous.img').write_bytes(previous)
        try: mod.verify(folder/'previous.img')
        except ValueError: pass
        else: raise AssertionError('BOOT 2 misidentified as diagnostic')
        text=package.render((ROOT/'scripts/collect-boot-diagnostic.py').read_text(),lock)
        collect=types.ModuleType('diagnostic_collector');collect.__file__=str(ROOT/'scripts/collect-boot-diagnostic.py')
        exec(compile(text,'collector','exec'),collect.__dict__)
        cases=[]
        for case in ('success','missing-logs','wrong-device','usb-unavailable','tools-unavailable'):
            path=folder/case;path.mkdir();operations=[]
            def verifier_tools(root):
                if case=='tools-unavailable': raise ValueError('local_tools_unavailable')
            def runner(exe,name):
                operations.append(name);args=collect.command_for(name)
                assert args[0]=='-d'
                assert not any(v in ' '.join(args) for v in ('dd ','mkfs','reboot','mount ','umount ','rm ','resize','e2fsck'))
                outputs={'state':'device\n','uid':'0\n','properties':'ro.twrp.version|3.7.0_9-2\nro.product.device|beyond2lte\nro.hardware|exynos9820\nro.bootloader|G975FXXSGHWC1\n',
                         'diagnostic-init':'UT_DIAG_1: PID 1 STARTED\nandroidboot.serialno=PRIVATE_TEST_SERIAL\nUUID=deadbeef-1111-2222-3333-444444444444\n',
                         'diagnostic-kernel':'Linux version 4.14.280-test\nSAR_RD: Successfully loaded ramdisk\n',
                         'diagnostic-display':'fb0 diagnostic submitted\n','diagnostic-boot-hash':lock['boot_sha256']+'  -\n',
                         'last-kmsg':'S-Boot recovery boot\n','recovery-kernel':'Linux recovery 4.14.113\n'}
                value={'exit_code':0,'timed_out':False,'stdout':outputs.get(name,''),'stderr':''}
                if case=='missing-logs' and name.startswith('diagnostic-') and name!='diagnostic-boot-hash':
                    value.update(exit_code=1,stdout='')
                if case=='wrong-device' and name=='properties': value['stdout']=value['stdout'].replace('beyond2lte','wrong')
                if case=='usb-unavailable' and name=='state': value.update(exit_code=1,stdout='')
                return value
            report,z=collect.collect(path,runner,verifier_tools)
            if case in ('success','missing-logs'):
                assert report['success'] and report['diagnostic_boot_matches']
                assert report['diagnostic_pid1_marker_found']==(case=='success')
                assert report['diagnostic_kernel_version']==('4.14.280-test' if case=='success' else None)
            else:
                assert not report['success'] and not any(n.startswith('diagnostic-') for n in operations)
            assert not report['ubuntu_touch_boot_verified'] and not report['partition_writes'] and not report['mount_changes_requested']
            with zipfile.ZipFile(z) as archive:
                joined='\n'.join(archive.read(n).decode() for n in archive.namelist())
                assert 'PRIVATE_TEST_SERIAL' not in joined and 'deadbeef-1111' not in joined and str(path) not in joined
            cases.append(case)
        for forbidden in ('write-boot','vendor-fsck','system-magic','pstore:../../data'):
            try: collect.command_for(forbidden)
            except ValueError: pass
            else: raise AssertionError('collector query allowlist bypass')
        with patch('subprocess.run',return_value=types.SimpleNamespace(returncode=0,stdout=b'A'*(2097152+4097),stderr=b'')):
            assert collect.run_query(folder/'unused-adb','diagnostic-kernel')['exit_code'] is None
    record={'schema':1,'diagnostic_version':1,'boot_sha256':lock['boot_sha256'],
        'boot_bytes':len(image),'rollback_boot_2_sha256':PREVIOUS_SHA256,
        'kernel_byte_identical_to_boot_2':True,'other_ramdisk_entries_unchanged':True,
        'actual_arm64_display_self_test_under_qemu_passed':True,
        'actual_installed_arm64_busybox_init_syntax_check_passed':True,
        'collector_mocked_cases':cases,'collector_read_only_allowlist_and_bounds_verified':True,
        'corrupt_kernel_and_header_rejected':True,'diagnostic_boot_verifier_passed':True,
        'usb_or_phone_accessed':False,'hardware_boot_verified':False}
    (a.images/'diagnostic-tests.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PASS: real-image preservation and rollback, ARM64 helper and BusyBox syntax, five read-only collector cases, output bounds and identification limits. No phone accessed.')


if __name__=='__main__': main()
