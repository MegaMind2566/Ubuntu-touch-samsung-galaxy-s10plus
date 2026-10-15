"""Inspect the actual embedded initramfs, ARM64 tools and generated collector."""
import argparse
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
from early_boot_diagnostic import entries,image_kernel,PREVIOUS_SHA256


def force_guard(source,folder):
    text=source.read_text()
    begin=text.index('\tif (do_skip_initramfs && !IS_ENABLED(CONFIG_INITRAMFS_FORCE))')
    end=text.index('\t/* If available load the bootloader supplied initrd */',begin)
    body=text[begin:end]
    harness=r'''#include <stdlib.h>
#define IS_ENABLED(x) (x)
#define CONFIG_INITRAMFS_FORCE force_builtin
static int force_builtin,do_skip_initramfs,initrd_start=1;
static int freed,builtin,defaults;
static char __initramfs_start[1];
static unsigned long __initramfs_size=1;
static void free_initrd(void){freed++;}
static int default_rootfs(void){defaults++;return 17;}
static char *unpack_to_rootfs(char *data,unsigned long size){if(data!=__initramfs_start||size!=1)abort();builtin++;return 0;}
static void panic(char *format,char *error){abort();}
static int populate(void){char *err;
'''+body+r'''
return 7;}
int main(void){
 for(force_builtin=0;force_builtin<2;force_builtin++){
  for(do_skip_initramfs=0;do_skip_initramfs<2;do_skip_initramfs++){
   freed=builtin=defaults=0;
   int got=populate();
   if(do_skip_initramfs&&!force_builtin){if(got!=17||freed!=1||defaults!=1||builtin)abort();}
   else {if(got!=7||freed||defaults||builtin!=1)abort();}
  }
 }
 return 0;
}
'''
    path=folder/'force.c';path.write_text(harness)
    subprocess.run(['cc','-std=c11','-Werror',str(path),'-o',str(folder/'force-test')],check=True)
    subprocess.run([str(folder/'force-test')],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path,required=True)
    p.add_argument('--qemu',required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('package_early',ROOT/'scripts/package-early-boot-diagnostic.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    image,previous,lock=package.validate(a.images)
    payload=(a.images/'initramfs.cpio').read_bytes();files={i['name']:i for i in entries(payload)}
    assert image_kernel(image).count(payload)==1
    assert files['bin/sh']['data']==b'busybox' and files['init']['values'][1]==0o100755
    assert b'UT_DIAG_2: PID 1 STARTED' in files['init']['data'] and b'UT_DIAG_1' not in files['init']['data']
    assert b'-o ro,noload,nosuid,nodev,noexec /dev/sda25' in files['init']['data']
    assert b'-o ro,noload,nosuid,nodev,noexec /dev/sda26' in files['init']['data']
    assert 'ut-diag-original-init' not in files
    with tempfile.TemporaryDirectory() as d:
        folder=Path(d)
        for name,key in [('busybox','bin/busybox'),('display','ut-diag-display'),('init','init')]:
            (folder/name).write_bytes(files[key]['data']);(folder/name).chmod(0o700)
        subprocess.run([a.qemu,str(folder/'busybox'),'sh','-n',str(folder/'init')],check=True)
        subprocess.run([a.qemu,str(folder/'display'),'--self-test'],check=True)
        force_guard(ROOT/'build/early-diagnostic/workdir/downloads/kernel-samsung-exynos9820/init/initramfs.c',folder)
        # Recompute the outer image hash after corruption: inner preservation checks still reject it.
        bad=folder/'bad';shutil.copytree(a.images,bad)
        changed=bytearray(image);changed[2048+128]^=1
        (bad/'diagnostic-boot.img').write_bytes(changed)
        changed_lock=dict(lock);changed_lock['boot_sha256']=hashlib.sha256(changed).hexdigest()
        (bad/'early-boot-diagnostic.lock.json').write_text(json.dumps(changed_lock))
        try:package.validate(bad)
        except ValueError:pass
        else:raise AssertionError('corrupt kernel accepted')
        shutil.rmtree(bad);shutil.copytree(a.images,bad)
        (bad/'kernel.config').write_text((bad/'kernel.config').read_text().replace('CONFIG_INITRAMFS_FORCE=y','# CONFIG_INITRAMFS_FORCE is not set'))
        try:package.validate(bad)
        except ValueError:pass
        else:raise AssertionError('false compiled configuration accepted')
        collect=types.ModuleType('early_collector');collect.__file__=str(ROOT/'scripts/collect-boot-diagnostic.py')
        exec(compile(package.collector(lock),'collector','exec'),collect.__dict__)
        cases=['success','missing-logs','old-marker','wrong-boot','wrong-device','tools-unavailable']
        for case in cases:
            target=folder/case;target.mkdir();operations=[]
            def verifier(root):
                if case=='tools-unavailable':raise ValueError('local_tools_unavailable')
            def runner(exe,name):
                operations.append(name);args=collect.command_for(name)
                assert args[0]=='-d' and not any(v in ' '.join(args) for v in ['dd ','mount ','umount ','mkfs','resize','reboot','rm '])
                outputs={'state':'device\n','uid':'0\n','properties':'ro.twrp.version|3.7.0_9-2\nro.product.device|beyond2lte\nro.hardware|exynos9820\nro.bootloader|G975FXXSGHWC1\n',
                    'diagnostic-init':'UT_DIAG_2: PID 1 STARTED\nandroidboot.serialno=PRIVATE_TEST_SERIAL\n',
                    'diagnostic-kernel':'Linux version 4.14.280-diag2\n','diagnostic-boot-hash':lock['boot_sha256']+'  -\n'}
                v={'exit_code':0,'timed_out':False,'stdout':outputs.get(name,''),'stderr':''}
                if case=='missing-logs' and name in collect.NAMES:v.update(exit_code=1,stdout='')
                if case=='old-marker' and name=='diagnostic-init':v['stdout']=v['stdout'].replace('UT_DIAG_2','UT_DIAG_1')
                if case=='wrong-boot' and name=='diagnostic-boot-hash':v['stdout']=PREVIOUS_SHA256+'  -\n'
                if case=='wrong-device' and name=='properties':v['stdout']=v['stdout'].replace('beyond2lte','wrong')
                return v
            report,z=collect.collect(target,runner,verifier)
            assert report['diagnostic_version']==2 and not report['ubuntu_touch_boot_verified'] and not report['partition_writes']
            if case in ('wrong-device','tools-unavailable'):
                assert not report['success'] and not any(n.startswith('diagnostic-') for n in operations)
            else:
                assert report['success']
                assert report['diagnostic_pid1_marker_found']==(case not in ('missing-logs','old-marker'))
                assert report['diagnostic_boot_matches']==(case!='wrong-boot')
            with zipfile.ZipFile(z) as archive:
                assert 'PRIVATE_TEST_SERIAL' not in '\n'.join(archive.read(n).decode() for n in archive.namelist())
            assert z.name=='ubuntu-boot-diagnostic-2-log-report.zip'
    result={'schema':1,'diagnostic_version':2,'boot_sha256':lock['boot_sha256'],
        'embedded_cpio_exact_match':True,'peripheral_configuration_preserved':True,
        'actual_arm64_busybox_syntax_test':True,'actual_arm64_display_self_test':True,
        'actual_populate_rootfs_force_guard_cases':4,'corrupt_kernel_and_false_config_rejected':True,
        'collector_mocked_cases':cases,'phone_accessed':False,'ubuntu_touch_boot_verified':False}
    (a.images/'early-diagnostic-tests.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: built-in payload, actual ARM64 programs, four source force-guard cases, corruption checks and six read-only collector cases. Hardware boot unverified.')


if __name__=='__main__':main()
