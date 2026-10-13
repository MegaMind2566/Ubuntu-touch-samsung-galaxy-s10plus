"""Compile the actual pinned SAR loader against a file-only syscall fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ORIGINAL_SOURCE_SHA='4e0e305dab896293315ba7ce45ca34ba4d09baf2086dd103ae308cc8e01e9fae'
SHIM=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#define __init
#define GFP_KERNEL 0
#define pr_err(...) fprintf(stderr, __VA_ARGS__)
#define kmalloc(n, flags) malloc(n)
#define kfree(p) free(p)
int fixture_open(const char *, int, int);
long fixture_seek(int, unsigned int, int);
#define sys_open fixture_open
#define sys_read read
#define sys_lseek fixture_seek
#define sys_close close
void load_default_modules(void);
'''
HARNESS=r'''
#include "init/do_mounts.h"
#include <string.h>
static const char *boot_path;
static unsigned char *expected;
static size_t expected_size;
static long actual_seek = -1;
int mount_sar_ramdisk(char *);
int fixture_open(const char *name, int flags, int mode) {
    (void)name; (void)flags; (void)mode;
    return open(boot_path, O_RDONLY);
}
long fixture_seek(int fd, unsigned int offset, int whence) {
    actual_seek = offset;
    return lseek(fd, offset, whence);
}
void clean_rootfs(void) {}
void flush_delayed_fput(void) {}
void load_default_modules(void) {}
char *unpack_to_rootfs(char *buf, unsigned long len) {
    return len == expected_size && !memcmp(buf, expected, len) ? NULL : "wrong ramdisk bytes";
}
int main(int argc, char **argv) {
    FILE *file;
    int value;
    if (argc != 3) return 99;
    boot_path = argv[1];
    file = fopen(argv[2], "rb");
    if (!file) return 98;
    fseek(file, 0, SEEK_END); expected_size = ftell(file); fseek(file, 0, SEEK_SET);
    expected = malloc(expected_size);
    if (!expected || fread(expected, 1, expected_size, file) != expected_size) return 97;
    fclose(file);
    value = mount_sar_ramdisk("/dev/android_boot");
    printf("{\"loaded_exact_ramdisk\":%s,\"seek_offset\":%ld}\n", value ? "true" : "false", actual_seek);
    free(expected);
    return value ? 0 : 42;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--boot',type=Path,required=True)
    parser.add_argument('--ramdisk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=(args.source/'sar_ramdisk.c').read_bytes()
    if hashlib.sha256(source).hexdigest()!=ORIGINAL_SOURCE_SHA:raise ValueError('upstream_loader_mismatch')
    fixed=source.replace(b'unsigned int rd_offset;',b'unsigned int rd_offset = 0;')
    if fixed==source:raise ValueError('offset_declaration_missing')
    compiler=shutil.which('clang') or shutil.which('gcc')
    if not compiler:raise ValueError('C_compiler_unavailable')
    report={'schema':1,'source_sha256':ORIGINAL_SOURCE_SHA,'compiler':Path(compiler).name,
            'uses_actual_pinned_loader':True,'syscalls_are_file_only_mocks':True,'handset_accessed':False,'cases':{}}
    with tempfile.TemporaryDirectory(prefix='sar loader fixture ') as temporary:
        root=Path(temporary);(root/'init/sar_ramdisk').mkdir(parents=True);(root/'include/linux').mkdir(parents=True)
        (root/'init/sar_ramdisk/bootimg.h').write_bytes((args.source/'bootimg.h').read_bytes())
        (root/'init/do_mounts.h').write_text(SHIM)
        (root/'include/linux/types.h').write_text('#include <stdint.h>\n')
        (root/'include/linux/syscalls.h').write_text('/* syscall prototypes supplied by file-only shim */\n')
        (root/'harness.c').write_text(HARNESS)
        for name,content in (('original',source),('corrected',fixed)):
            c=root/'init/sar_ramdisk/sar_ramdisk.c';c.write_bytes(content);exe=root/name
            value=subprocess.run([compiler,'-O2','-Wall','-Wextra','-Wuninitialized','-I'+str(root/'include'),
                                  str(c),str(root/'harness.c'),'-o',str(exe)],capture_output=True,text=True)
            if value.returncode:raise ValueError('fixture_compile_failed: '+value.stderr)
            run=subprocess.run([str(exe),str(args.boot.resolve()),str(args.ramdisk.resolve())],capture_output=True,text=True)
            case=json.loads(run.stdout);case['exit_code']=run.returncode
            case['uninitialized_offset_warning']='uninitialized' in value.stderr and 'rd_offset' in value.stderr
            report['cases'][name]=case
            if name=='corrected' and (run.returncode or not case['loaded_exact_ramdisk'] or case['seek_offset']!=49106944):
                raise ValueError('corrected_loader_did_not_read_installed_ramdisk')
    if report['cases']['corrected']['uninitialized_offset_warning']:raise ValueError('offset_still_uninitialized')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
