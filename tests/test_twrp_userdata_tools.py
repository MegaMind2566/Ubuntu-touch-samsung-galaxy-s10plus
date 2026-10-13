"""Run the actual publisher TWRP BusyBox under ARM64 emulation; no USB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import hashlib

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
    # Exercise the exact recovery applets used by the TWRP route on disposable
    # ordinary files, never block devices. Include the final partial dd block.
    source=root/'copy-source.fixture';target=root/'copy-target.fixture'
    content=b'UT-copy-verification\n'*(600000);source.write_bytes(content)
    result=subprocess.run(prefix+['dd','if='+str(source),'of='+str(target),'bs=4194304'],capture_output=True,timeout=60)
    assert result.returncode==0 and target.read_bytes()==content,result.stderr.decode('utf-8','replace')
    result=subprocess.run(prefix+['sha256sum',str(target)],capture_output=True,timeout=60)
    assert result.returncode==0 and result.stdout.decode().split()[0]==hashlib.sha256(content).hexdigest()
    result=subprocess.run(prefix+['sync'],capture_output=True,timeout=30);assert result.returncode==0
    sparse=root/'large-size.fixture'
    with sparse.open('wb') as output:output.truncate(5368709120)
    result=subprocess.run(prefix+['stat','-t',str(sparse)],capture_output=True,timeout=30)
    assert result.returncode==0 and result.stdout.decode().split()[:2]==[str(sparse),'5368709120'],result.stderr
    # Small numeric count/bs fields avoid a >4 GiB head-count dependency.
    result=subprocess.run(prefix+['dd','if='+str(target),'bs=4194304','count=2'],capture_output=True,timeout=30)
    assert result.returncode==0 and result.stdout==content[:8388608]
    print('PASS: exact TWRP BusyBox dd/sync/stat/sha256sum applets, partial final copy block, 5 GiB size reporting and bounded readback. Only disposable local files modified; no hardware writes.')


if __name__=='__main__':main()
