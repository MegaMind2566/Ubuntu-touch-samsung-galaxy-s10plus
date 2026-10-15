"""Build diagnostic 2 with a minimal initramfs inside the pinned Halium kernel."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile
import zlib

from github_artifacts import obtain_job
from inspect_stock_firmware import aligned, boot_header
from prepare_boot_diagnostic import entries, encode, elf_static_arm64

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/early-boot-diagnostic-images'
PREVIOUS_SHA256='2b51b9a0950744dc59d63f8847ff65549830e8c870d7f4f49a4d2ee7cc65fe25'
PREVIOUS_BYTES=53475328
KERNEL_COMMIT='b9b70b29c94c41365704fcc2ed33be09b4617907'
INITRAMFS_SOURCE_SHA256='d1cd2617e215e3e4b3f652785d2b5c432fb870f12590e7f23fc218c0e9021b52'
DIAGNOSTIC_PATCH=ROOT/'patches/diagnostic/0001-honor-force-for-builtin-initramfs.patch'
PINNED_RUN=38488933274
PINNED_COMMIT='a3d3933e9dd7da908021ee83a3fbfa1e82d71061'
PINNED_ARTIFACT=11860957188
PINNED_ZIP_SHA256='16c2790884ad3a6d3fd0e74882da18faa4f3858cd81ebc045f8f9e27c2b0f304'
PARTITION_BYTES=57671680


def sha(data):return hashlib.sha256(data).hexdigest()


def extract_zip(source,folder,expected):
    folder.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as z:
        if set(z.namelist())!=set(expected) or len(z.infolist())!=len(expected) or z.testzip() is not None:
            raise ValueError('diagnostic_archive_shape')
        for name in expected:
            if z.getinfo(name).file_size>64*1024*1024:raise ValueError('diagnostic_member_size')
            (folder/name).write_bytes(z.read(name))


def inputs():
    token=os.environ['UT_ARTIFACT_TOKEN']
    ref=obtain_job(PINNED_RUN,PINNED_COMMIT,'diagnostic-1-images.zip',
                   'beyond2lte-boot-diagnostic-images','images',token,PINNED_ARTIFACT)
    if ref['sha256']!=PINNED_ZIP_SHA256:raise ValueError('diagnostic_1_artifact_pin')
    extract_zip(ROOT/'out/diagnostic-1-images.zip',ROOT/'out/boot-diagnostic-images',
                ['diagnostic-boot.img','previous-boot-2.img','boot-diagnostic.lock.json','diagnostic-tests.json'])
    (ROOT/'out/diagnostic-1-artifact-reference.json').write_text(json.dumps(ref,indent=2)+'\n')


def previous_image():
    data=(ROOT/'out/boot-diagnostic-images/diagnostic-boot.img').read_bytes()
    if len(data)!=PREVIOUS_BYTES or sha(data)!=PREVIOUS_SHA256:raise ValueError('diagnostic_1_image_pin')
    return data


def image_kernel(data):
    h=boot_header(data)
    return data[h['page_bytes']:h['page_bytes']+h['kernel_bytes']]


def kernel_config(kernel):
    marker=b'IKCFG_ST';offset=kernel.find(marker)
    if offset<0 or kernel.count(marker)!=1:raise ValueError('embedded_kernel_config_missing')
    decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
    config=decoder.decompress(kernel[offset+len(marker):],1024*1024)
    if not decoder.eof or len(config)>=1024*1024:raise ValueError('embedded_kernel_config_invalid')
    return config.decode('ascii')


def config_values(text):
    found={}
    for line in text.splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key,value=line.split('=',1);found[key]=value
        elif re.fullmatch(r'# CONFIG_[A-Z0-9_]+ is not set',line):found[line[2:-11]]='n'
    return found


def minimal_initramfs(previous):
    h=boot_header(previous)
    original=entries(gzip.decompress(previous[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]))
    by_name={i['name']:i for i in original};bb=by_name['bin/busybox']
    peers=[i['data'] for i in original if i['values'][0]==bb['values'][0]
           and i['values'][7:9]==bb['values'][7:9] and i['data']]
    if len(peers)!=1:raise ValueError('busybox_hardlink_layout')
    busybox=peers[0];helper=by_name['ut-diag-display']['data']
    elf_static_arm64(busybox);elf_static_arm64(helper)
    init=by_name['init']['data']
    if init!=(ROOT/'tools/boot-diagnostic/init').read_text(encoding='ascii').encode('ascii'):
        raise ValueError('diagnostic_1_init_source_changed')
    for before,after in [(b'UT_DIAG_1',b'UT_DIAG_2'),(b'UBUNTU TOUCH TEST 1',b'UBUNTU TOUCH TEST 2'),
                         (b'ubuntu-touch-boot-diagnostic-1',b'ubuntu-touch-boot-diagnostic-2'),
                         (b'UT-S10P-DIAG-1',b'UT-S10P-DIAG-2'),
                         (b'Ubuntu Touch S10+ boot diagnostic 1',b'Ubuntu Touch S10+ boot diagnostic 2'),
                         (b'/usb_gadget/utdiag1',b'/usb_gadget/utdiag2')]:
        if before not in init:raise ValueError('diagnostic_init_anchor_missing')
        init=init.replace(before,after)
    items=[]
    def add(name,mode,data=b'',major=0,minor=0):
        items.append({'name':name,'values':[len(items)+1,mode,0,0,1,0,len(data),0,0,major,minor,len(name)+1,0],'data':data})
    for name in ['bin','dev','proc','sys','run','data','config','system-probe','vendor-probe']:
        add(name,0o40755)
    add('bin/busybox',0o100755,busybox);add('bin/sh',0o120777,b'busybox')
    add('dev/console',0o20600,major=5,minor=1);add('dev/null',0o20666,major=1,minor=3)
    add('init',0o100755,init);add('ut-diag-display',0o100755,helper)
    payload=encode(items)
    if len(payload)>4*1024*1024:raise ValueError('minimal_initramfs_too_large')
    return payload


def configure(work):
    previous=previous_image();OUT.mkdir(parents=True,exist_ok=True)
    payload=minimal_initramfs(previous);path=OUT/'initramfs.cpio';path.write_bytes(payload)
    (OUT/'previous-diagnostic-1.img').write_bytes(previous)
    kernel=work/'workdir/downloads/kernel-samsung-exynos9820'
    commit=subprocess.check_output(['git','-C',str(kernel),'rev-parse','HEAD'],text=True).strip()
    source=kernel/'init/initramfs.c'
    if commit!=KERNEL_COMMIT or sha(source.read_bytes())!=INITRAMFS_SOURCE_SHA256:
        raise ValueError('initramfs_kernel_source_changed')
    subprocess.run(['git','-C',str(kernel),'apply','--check',str(DIAGNOSTIC_PATCH)],check=True)
    subprocess.run(['git','-C',str(kernel),'apply',str(DIAGNOSTIC_PATCH)],check=True)
    fragment=(ROOT/'config/early-boot-diagnostic.config').read_text().replace('@UT_DIAG_CPIO@',str(path.resolve()))
    (kernel/'arch/arm64/configs/early-boot-diagnostic.config').write_text(fragment)
    info=work/'deviceinfo';text=info.read_text()
    text+='\n# Temporary diagnostic 2; keep the normal Ubuntu configuration separate.\n'
    text+='deviceinfo_kernel_defconfig="exynos9820-beyond2lte_defconfig ubuntu-touch.config early-boot-diagnostic.config"\n'
    info.write_text(text)
    (OUT/'diagnostic-source.json').write_text(json.dumps({'kernel_commit':commit,
        'normal_build_manifest':json.loads((work/'source-manifest.json').read_text()),
        'diagnostic_patch_sha256':sha(DIAGNOSTIC_PATCH.read_bytes()),
        'patched_initramfs_source_sha256':sha(source.read_bytes()),
        'initramfs_sha256':sha(payload),'initramfs_bytes':len(payload)},indent=2)+'\n')


def compose(previous,compiled,payload):
    if sha(previous)!=PREVIOUS_SHA256 or len(previous)!=PREVIOUS_BYTES:raise ValueError('diagnostic_1_image_pin')
    before=boot_header(previous);kernel=image_kernel(compiled)
    if kernel[56:60]!=b'ARM\x64' or kernel.count(payload)!=1:raise ValueError('built_in_initramfs_missing')
    old=config_values(kernel_config(image_kernel(previous)));new=config_values(kernel_config(kernel))
    differences={key:{'before':old.get(key,'n'),'after':new.get(key,'n')} for key in sorted(set(old)|set(new))
                 if old.get(key,'n')!=new.get(key,'n')}
    allowed={'CONFIG_INITRAMFS_SOURCE','CONFIG_INITRAMFS_FORCE','CONFIG_INITRAMFS_ROOT_UID','CONFIG_INITRAMFS_ROOT_GID',
             'CONFIG_INITRAMFS_COMPRESSION','CONFIG_INITRAMFS_COMPRESSION_NONE','CONFIG_INITRAMFS_COMPRESSION_GZIP',
             'CONFIG_INITRAMFS_COMPRESSION_BZIP2','CONFIG_INITRAMFS_COMPRESSION_LZMA','CONFIG_INITRAMFS_COMPRESSION_XZ',
             'CONFIG_INITRAMFS_COMPRESSION_LZO','CONFIG_INITRAMFS_COMPRESSION_LZ4'}
    if set(differences)-allowed:raise ValueError('unrelated_kernel_config_changed:'+','.join(sorted(set(differences)-allowed)))
    if (new.get('CONFIG_INITRAMFS_FORCE')!='y' or new.get('CONFIG_INITRAMFS_COMPRESSION_NONE')!='y'
            or new.get('CONFIG_ANDROID_SAR_RAMDISK')!='y' or new.get('CONFIG_ANDROID_BOOT_PARTITION')!='"/dev/sda14"'
            or new.get('CONFIG_CMDLINE_EXTEND')!='y' or not new.get('CONFIG_INITRAMFS_SOURCE','').endswith('/initramfs.cpio"')):
        raise ValueError('early_diagnostic_config_invalid')
    ramdisk=previous[before['ramdisk_offset']:before['ramdisk_offset']+before['ramdisk_bytes']]
    header=bytearray(previous[:before['page_bytes']]);struct.pack_into('<I',header,8,len(kernel))
    digest=hashlib.sha1()
    for p in (kernel,ramdisk,b'',b'',b''):digest.update(p);digest.update(struct.pack('<I',len(p)))
    header[576:608]=digest.digest()+b'\0'*12
    page=before['page_bytes'];image=bytes(header)+kernel+b'\0'*(aligned(len(kernel),page)-len(kernel))
    image+=ramdisk+b'\0'*(aligned(len(ramdisk),page)-len(ramdisk))
    if len(image)>PARTITION_BYTES:raise ValueError('early_diagnostic_boot_overflow')
    changes={i for i,(a,b) in enumerate(zip(previous[:page],header)) if a!=b}
    if changes-set(range(8,12))-set(range(576,608)):raise ValueError('unrelated_header_changed')
    return image,differences


def finalize(work):
    previous=previous_image();payload=(OUT/'initramfs.cpio').read_bytes()
    image,differences=compose(previous,(work/'workdir/tmp/partitions/boot.img').read_bytes(),payload)
    h=boot_header(image);kernel=image_kernel(image)
    config=(work/'workdir/downloads/KERNEL_OBJ/.config').read_text()
    if config_values(config)!=config_values(kernel_config(kernel)):raise ValueError('compiled_config_mismatch')
    (OUT/'diagnostic-boot.img').write_bytes(image);(OUT/'kernel.config').write_text(config)
    lock={'schema':1,'diagnostic_version':2,'purpose':'builtin_initramfs_before_system_mount',
          'boot_sha256':sha(image),'boot_bytes':len(image),'boot_partition_bytes':PARTITION_BYTES,
          'previous_boot_sha256':PREVIOUS_SHA256,'previous_boot_bytes':PREVIOUS_BYTES,
          'kernel_sha256':sha(kernel),'kernel_bytes':len(kernel),'kernel_source_commit':KERNEL_COMMIT,
          'kernel_config_differences':differences,'builtin_initramfs_sha256':sha(payload),'builtin_initramfs_bytes':len(payload),
          'builtin_initramfs_kernel_offset':kernel.find(payload),'force_builtin_initramfs':True,
          'ramdisk_sha256':sha(image[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]),'ramdisk_bytes':h['ramdisk_bytes'],
          'external_ramdisk_preserved_from_diagnostic_1':True,'unrelated_header_fields_preserved':True,
          'target_device':'/dev/block/sda14','system_write_requested':False,'vendor_write_requested':False,
          'diagnostic_log_directory':'/data/ubuntu-touch-boot-diagnostic-2','original_ubuntu_init_executed':False,
          'hardware_tested':False,'ubuntu_touch_boot_verified':False}
    (OUT/'early-boot-diagnostic.lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print(json.dumps(lock,indent=2))


def fetch_images():
    ref=obtain_job(int(os.environ['GITHUB_RUN_ID']),os.environ['GITHUB_SHA'],'early-diagnostic-images.zip',
                   'beyond2lte-early-boot-diagnostic-images','images',os.environ['UT_ARTIFACT_TOKEN'])
    extract_zip(ROOT/'out/early-diagnostic-images.zip',OUT,['diagnostic-boot.img','previous-diagnostic-1.img',
        'initramfs.cpio','kernel.config','diagnostic-source.json','early-boot-diagnostic.lock.json','early-diagnostic-tests.json'])
    (ROOT/'out/early-diagnostic-artifact-reference.json').write_text(json.dumps(ref,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['inputs','configure','finalize','images'])
    p.add_argument('--work',type=Path);a=p.parse_args()
    if a.phase in ('configure','finalize') and a.work is None:p.error('--work is required')
    if a.phase=='inputs':inputs()
    elif a.phase=='configure':configure(a.work.resolve())
    elif a.phase=='finalize':finalize(a.work.resolve())
    else:fetch_images()
