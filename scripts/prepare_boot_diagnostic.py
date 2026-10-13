"""Build a controlled ramdisk test with the byte-identical handset BOOT 2 kernel."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import zipfile

from inspect_stock_firmware import aligned, boot_header

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_SHA256 = 'cad81022329d1effb50d1ed421148b5c1741e41ae2eb0414d75ac06ec64ecda0'
PREVIOUS_BYTES = 53215232
ORIGINAL_RAM_SHA256 = '439b535193a8e6315e3da3884755db49b04794c28d5e06686fc595dfab8f5a4c'
PARTITION_BYTES = 57671680


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entries(data):
    result = []
    pos = 0
    while pos + 110 <= len(data):
        if data[pos:pos+6] != b'070701':
            raise ValueError('cpio_header')
        values = [int(data[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        end = pos + 110 + values[11]
        if not 1 <= values[11] <= 1024 or end > len(data) or data[end-1] != 0:
            raise ValueError('cpio_name')
        name = data[pos+110:end-1].decode('utf-8')
        start = aligned(end, 4)
        if name == 'TRAILER!!!':
            if values[6]: raise ValueError('cpio_trailer')
            return result
        if (name.startswith('/') or '..' in name.split('/') or
                any(item['name'] == name for item in result) or start+values[6] > len(data)):
            raise ValueError('cpio_entry')
        result.append({'name': name, 'values': values, 'data': data[start:start+values[6]]})
        pos = aligned(start+values[6], 4)
    raise ValueError('cpio_trailer_missing')


def encode(items):
    output = bytearray()
    for item in items + [{'name':'TRAILER!!!', 'values':[0,0,0,0,1,0,0,0,0,0,0,11,0], 'data':b''}]:
        name = item['name'].encode() + b'\0'
        values = list(item['values']); values[6]=len(item['data']); values[11]=len(name)
        output.extend(b'070701'+''.join(f'{v:08x}' for v in values).encode()+name)
        output.extend(b'\0' * (aligned(len(output),4)-len(output)))
        output.extend(item['data'])
        output.extend(b'\0' * (aligned(len(output),4)-len(output)))
    output.extend(b'\0' * (aligned(len(output),512)-len(output)))
    return bytes(output)


def elf_static_arm64(data):
    if (len(data)<64 or data[:6]!=b'\x7fELF\x02\x01' or
            struct.unpack_from('<H',data,18)[0]!=183):
        raise ValueError('diagnostic_helper_architecture')
    offset=struct.unpack_from('<Q',data,32)[0]
    size,count=struct.unpack_from('<HH',data,54)
    if size<56 or count>100 or offset+size*count>len(data):
        raise ValueError('diagnostic_helper_header')
    if any(struct.unpack_from('<I',data,offset+i*size)[0]==3 for i in range(count)):
        raise ValueError('diagnostic_helper_not_static')


def compose(previous, init, helper):
    if len(previous)!=PREVIOUS_BYTES or sha(previous)!=PREVIOUS_SHA256:
        raise ValueError('current_boot_2_not_pinned')
    if not init.startswith(b'#!/bin/sh\n') or len(init)>65536 or b'\r' in init:
        raise ValueError('diagnostic_init_invalid')
    elf_static_arm64(helper)
    if len(helper)>2*1024*1024: raise ValueError('diagnostic_helper_too_large')
    h=boot_header(previous)
    ram=previous[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]
    if sha(ram)!=ORIGINAL_RAM_SHA256 or h['boot_id_variant']!='lineage-empty-legacy-dt':
        raise ValueError('boot_2_ramdisk_layout')
    original=entries(gzip.decompress(ram))
    by_name={i['name']:i for i in original}
    if 'init' not in by_name or not stat.S_ISREG(by_name['init']['values'][1]):
        raise ValueError('original_init_layout')
    if any(n in by_name for n in ('ut-diag-display','ut-diag-original-init')):
        raise ValueError('diagnostic_path_exists')
    items=[{'name':i['name'],'values':list(i['values']),'data':i['data']} for i in original]
    next_inode=max(i['values'][0] for i in original)+1
    for name,data in [('ut-diag-original-init',by_name['init']['data']),('ut-diag-display',helper)]:
        items.append({'name':name,'values':[next_inode,0o100755,0,0,1,0,len(data),0,0,0,0,len(name)+1,0],'data':data})
        next_inode+=1
    next(i for i in items if i['name']=='init')['data']=init
    new_ram=gzip.compress(encode(items),compresslevel=9,mtime=0)
    kernel=previous[h['page_bytes']:h['page_bytes']+h['kernel_bytes']]
    header=bytearray(previous[:h['page_bytes']])
    struct.pack_into('<I',header,16,len(new_ram))
    boot_id=hashlib.sha1()
    for payload in (kernel,new_ram,b'',b'',b''):
        boot_id.update(payload);boot_id.update(struct.pack('<I',len(payload)))
    header[576:608]=boot_id.digest()+b'\0'*12
    image=bytes(header)+kernel+b'\0'*(aligned(len(kernel),h['page_bytes'])-len(kernel))
    image+=new_ram+b'\0'*(aligned(len(new_ram),h['page_bytes'])-len(new_ram))
    if len(image)>PARTITION_BYTES: raise ValueError('diagnostic_boot_overflow')
    changed={i for i,(a,b) in enumerate(zip(previous[:h['page_bytes']],header)) if a!=b}
    if changed-set(range(16,20))-set(range(576,608)):
        raise ValueError('unrelated_header_changed')
    check={i['name']:i for i in entries(gzip.decompress(new_ram))}
    for name,item in by_name.items():
        got=check[name]
        if got['values']!=item['values'] or (name!='init' and got['data']!=item['data']):
            # Only init's filesize is deliberately different in the encoded header.
            expected=list(item['values'])
            if name=='init': expected[6]=len(init)
            if got['values']!=expected or (name!='init' and got['data']!=item['data']):
                raise ValueError('unrelated_ramdisk_entry_changed')
    report={'schema':1,'diagnostic_version':1,'purpose':'controlled_pid1_ramdisk_test',
            'previous_boot_sha256':PREVIOUS_SHA256,'previous_boot_bytes':PREVIOUS_BYTES,
            'boot_sha256':sha(image),'boot_bytes':len(image),'target_device':'/dev/block/sda14',
            'kernel_sha256':sha(kernel),'kernel_bytes':len(kernel),'kernel_byte_identical_to_boot_2':True,
            'ramdisk_sha256':sha(new_ram),'ramdisk_bytes':len(new_ram),
            'original_ramdisk_sha256':sha(ram),'init_sha256':sha(init),'display_helper_sha256':sha(helper),
            'original_init_retained':True,'other_original_ramdisk_entries_preserved':True,
            'original_entry_count':len(original),'unrelated_header_fields_preserved':True,
            'diagnostic_log_directory':'/data/ubuntu-touch-boot-diagnostic-1',
            'runtime_system_vendor_mount_options':'ro,noload,nosuid,nodev,noexec',
            'runtime_raw_block_writes':False,'runtime_fsck_resize_format':False,
            'runtime_original_ubuntu_init_executed':False,'runtime_automatic_reboot':False,
            'runtime_usb_function':'ACM enumeration only; no shell/network service',
            'hardware_tested':False,'ubuntu_touch_boot_verified':False}
    return image,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous-archive',type=Path,required=True)
    p.add_argument('--helper',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ROOT/'out/boot-diagnostic-images')
    a=p.parse_args()
    with zipfile.ZipFile(a.previous_archive) as z: previous=z.read('boot.img')
    image,report=compose(previous,(ROOT/'tools/boot-diagnostic/init').read_bytes(),a.helper.read_bytes())
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'diagnostic-boot.img').write_bytes(image)
    (a.out/'previous-boot-2.img').write_bytes(previous)
    (a.out/'boot-diagnostic.lock.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
