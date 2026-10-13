"""Run the actual publisher TWRP BusyBox under ARM64 emulation; no USB."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_recovery import download_original,decode_ramdisk,cpio_records
from inspect_stock_firmware import boot_header


def main():
    root=Path('out/twrp-metadata-emulation').resolve();root.mkdir(parents=True,exist_ok=True)
    data=download_original(root).read_bytes();header=boot_header(data)
    records=cpio_records(decode_ramdisk(data[header['ramdisk_offset']:header['ramdisk_offset']+header['ramdisk_bytes']]))
    runtime=root/'runtime'
    # All selected files are flat original regular files, not arbitrary CPIO
    # paths/symlinks. No recovery image is distributed in the tools package.
    for name,_,_,content in records:
        if name in ('sbin/busybox','sbin/linker64') or (name.startswith('sbin/') and name.count('/')==1 and name.endswith('.so')):
            path=runtime/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content);path.chmod(0o700)
    prefix=['qemu-aarch64','-L',str(runtime),'-E','LD_LIBRARY_PATH='+str(runtime/'sbin'),str(runtime/'sbin/busybox')]
    uuid=bytes(range(16));payload=bytearray(4096);payload[1080:1082]=b'\x53\xef';payload[1128:1144]=uuid
    fixture=root/'filesystem-metadata.fixture';fixture.write_bytes(payload)
    old=subprocess.run(prefix+['od','-An','-v','-tx1'],input=uuid,capture_output=True,timeout=30)
    print(json.dumps({'old_od_exit_code':old.returncode,'old_od_stderr':old.stderr.decode('utf-8','replace')[:2000]}))
    for offset,count,expected in ((1080,2,'53ef'),(1128,16,uuid.hex())):
        result=subprocess.run(prefix+['hexdump','-v','-s',str(offset),'-n',str(count),'-e','1/1 "%02x"',str(fixture)],capture_output=True,timeout=30)
        if result.returncode!=0 or result.stdout.decode('ascii').strip()!=expected:
            raise AssertionError(result.stderr.decode('utf-8','replace')+' unexpected metadata output: '+repr(result.stdout))
    assert fixture.read_bytes()==payload,'Read command changed fixture'
    print('PASS: exact installed-recovery BusyBox runtime reads ext4 magic and 16-byte UUID with bounded hexdump commands. ARM64 emulation only; no handset access.')


if __name__=='__main__':main()
