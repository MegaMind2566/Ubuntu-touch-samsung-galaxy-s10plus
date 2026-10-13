"""Compile pinned kernel init selection with mocked namespace loading, no handset."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile

SOURCE_SHA256='2ede32b77f1e055a21d88caf393a71d35a027f85a00fbc1f9c6d73e1949e7f86'
RAMDISK_SHA256='439b535193a8e6315e3da3884755db49b04794c28d5e06686fc595dfab8f5a4c'

HARNESS=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __user
#define pr_err(...) do {} while (0)
#define pr_info(...) do {} while (0)
#define panic(...) abort()
static char *ramdisk_execute_command;
static char *execute_command;
static const char *selected;
static int phase, early_present, late_present, namespace_calls;
static const char *requested;
static int sys_access(const char *path, int mode) {
    (void)mode;
    return !strcmp(path, requested) && (phase ? late_present : early_present) ? 0 : -1;
}
static void prepare_namespace(void) { phase=1; namespace_calls++; }
static int run_init_process(const char *path) { selected=path; return 0; }
static int try_to_run_init_process(const char *path) { return run_init_process(path); }
static void namespace_selection(void) {
__NAMESPACE_SELECTION__
}
static int execute_selection(void) {
    int ret;
__EXECUTE_SELECTION__
}
int main(int argc, char **argv) {
    if (argc != 5) return 98;
    early_present=atoi(argv[1]);late_present=atoi(argv[2]);requested=argv[3];
    if (atoi(argv[4])) ramdisk_execute_command=argv[3];
    namespace_selection();execute_selection();
    printf("{\"selected_init\":\"%s\",\"namespace_calls\":%d}\n",selected,namespace_calls);
    return 0;
}
'''


def code_fragments(source):
    start=source.index('\tif (!ramdisk_execute_command)\n',source.index('static noinline void __init kernel_init_freeable(void)\n{'))
    end=source.index('\n\n\t/*\n\t * Ok, we have completed',start)
    init_start=source.index('\tif (ramdisk_execute_command) {',source.index('static int __ref kernel_init(void *unused)'))
    init_end=source.index('\n}\n',init_start)
    return source[start:end],source[init_start:init_end]


def ramdisk_evidence(path):
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=RAMDISK_SHA256:raise ValueError('installed_ramdisk_mismatch')
    data=gzip.decompress(content);pos=0;entries={}
    while pos+110<=len(data):
        if data[pos:pos+6]!=b'070701':raise ValueError('cpio_header_invalid')
        v=[int(data[pos+6+i*8:pos+14+i*8],16) for i in range(13)]
        name=data[pos+110:pos+110+v[11]-1].decode();start=(pos+110+v[11]+3)//4*4
        if name=='TRAILER!!!':break
        if name in entries or start+v[6]>len(data):raise ValueError('cpio_entry_invalid')
        entries[name]={'inode':v[0],'mode':v[1],'links':v[4],'device':(v[7],v[8]),'data':data[start:start+v[6]]}
        pos=(start+v[6]+3)//4*4
    else:raise ValueError('cpio_trailer_missing')
    init=entries['init'];fallback=entries['sbin/init']
    peers=[e for e in entries.values() if e['inode']==fallback['inode'] and e['device']==fallback['device'] and e['data']]
    if len(peers)!=1:raise ValueError('busybox_hardlink_unresolved')
    binary=peers[0]['data']
    if (not stat.S_ISREG(init['mode']) or not init['mode']&stat.S_IXUSR or not init['data'].startswith(b'#!/bin/sh\n')
            or binary[:4]!=b'\x7fELF' or binary[4]!=2 or struct.unpack_from('<H',binary,18)[0]!=183
            or b'/etc/init.d/rcS' not in binary or 'etc/inittab' in entries or 'etc/init.d/rcS' in entries):
        raise ValueError('installed_init_layout_unexpected')
    return {'sha256':RAMDISK_SHA256,'init_script_sha256':hashlib.sha256(init['data']).hexdigest(),
            'init_script_executable':True,'sbin_init_is_arm64_busybox_hardlink':True,
            'busybox_sha256':hashlib.sha256(binary).hexdigest(),'busybox_inittab_present':False,
            'busybox_rcs_present':False,'halium_mount_script_present':'scripts/halium' in entries}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--patch',type=Path,required=True)
    p.add_argument('--ramdisk',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();original=args.source.read_bytes()
    if hashlib.sha256(original).hexdigest()!=SOURCE_SHA256:raise ValueError('pinned_kernel_init_source_mismatch')
    ramdisk=ramdisk_evidence(args.ramdisk)
    compiler=shutil.which('clang') or shutil.which('gcc')
    if not compiler:raise ValueError('compiler_unavailable')
    report={'schema':1,'source_sha256':SOURCE_SHA256,'patch_sha256':hashlib.sha256(args.patch.read_bytes()).hexdigest(),
            'compiler':Path(compiler).name,'actual_pinned_namespace_and_execute_selection_compiled':True,
            'namespace_and_syscalls_mocked':True,'handset_accessed':False,'installed_ramdisk':ramdisk,'cases':{}}
    with tempfile.TemporaryDirectory(prefix='sar init handoff ') as tmp:
        root=Path(tmp);(root/'init').mkdir();target=root/'init/main.c';target.write_bytes(original)
        subprocess.run(['git','apply','--check',str(args.patch.resolve())],cwd=root,check=True)
        subprocess.run(['git','apply',str(args.patch.resolve())],cwd=root,check=True)
        fixed=target.read_text();report['fixed_source_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        for variant,source,sar in [('original_sar',original.decode(),True),('corrected_sar',fixed,True),('corrected_without_sar',fixed,False)]:
            namespace,execute=code_fragments(source)
            code=HARNESS.replace('__NAMESPACE_SELECTION__',namespace).replace('__EXECUTE_SELECTION__',execute)
            src=root/(variant+'.c');src.write_text(code);exe=root/variant
            cmd=[compiler,'-std=gnu89','-O2','-Wall','-Wextra','-Werror']
            if sar:cmd+=['-DCONFIG_ANDROID_SAR_RAMDISK=1']
            subprocess.run(cmd+[str(src),'-o',str(exe)],check=True,capture_output=True,text=True)
            values={}
            for name,early,late,requested,explicit in [('late_init',0,1,'/init',0),('preloaded_init',1,1,'/init',0),
                    ('missing_init',0,0,'/init',0),('late_custom_rdinit',0,1,'/custom-init',1)]:
                run=subprocess.run([str(exe),str(early),str(late),requested,str(explicit)],check=True,capture_output=True,text=True)
                case=json.loads(run.stdout);values[name]=case
                expected=requested if early or (variant=='corrected_sar' and late) else '/sbin/init'
                if case['selected_init']!=expected or case['namespace_calls']!=(0 if early else 1):raise ValueError('init_handoff_regression')
            report['cases'][variant]=values
    report['confirmed_host_reproduction']='Original SAR path skips the newly loaded /init and selects the actual ramdisk BusyBox /sbin/init; correction selects /init while preserving preloaded/custom/non-SAR behavior.'
    report['handset_root_cause_confirmed']=False
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
