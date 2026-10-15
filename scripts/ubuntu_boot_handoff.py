"""Embed the original Ubuntu initramfs, with bounded stage logging, in BOOT 4."""
import argparse
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import zlib

from early_boot_diagnostic import (ROOT, KERNEL_COMMIT, INITRAMFS_SOURCE_SHA256,
    DIAGNOSTIC_PATCH, sha, image_kernel, kernel_config, config_values, extract_zip)
from github_artifacts import obtain_job
from inspect_stock_firmware import boot_header, aligned
from prepare_boot_diagnostic import entries, encode, ORIGINAL_RAM_SHA256

OUT=ROOT/'out/ubuntu-boot-handoff-images'
PREVIOUS_SHA256='33e9b86294bce1d7bb61ae0b44af1186ef788bbcdc7137e945a1331e8f0718cc'
PREVIOUS_BYTES=57335808
BOOT2_SHA256='cad81022329d1effb50d1ed421148b5c1741e41ae2eb0414d75ac06ec64ecda0'
PARTITION_BYTES=57671680
INIT_SHA256='cda3570b6edc38c6aebf8a058bf75f5ada94e63a32b27da4d2f1eabf2200d0dc'


def replace_once(text, before, after):
    if text.count(before)!=1:raise ValueError('ubuntu_init_anchor:'+before[:60])
    return text.replace(before,after,1)


def inputs():
    ref=obtain_job(38750867704,'81d458d422824463eca6fd97e886a2f5c52ab7be',
        'handoff-ubuntu-3.zip','beyond2lte-ubuntu-boot-handoff-images','images',
        os.environ['UT_ARTIFACT_TOKEN'],11980658034)
    if ref['sha256']!='a3f7393e2f265ed7d3f347f2e4c6b439114b44bc43721fd057be849441b68bea':
        raise ValueError('ubuntu_3_artifact_pin')
    extract_zip(ROOT/'out/handoff-ubuntu-3.zip',ROOT/'out/handoff-ubuntu-3-input',[
        'boot.img','previous-diagnostic-2.img','initramfs.cpio','kernel.config',
        'ubuntu-boot-source.json','ubuntu-boot-handoff.lock.json','ubuntu-handoff-tests.json'])
    (ROOT/'out/handoff-ubuntu-3-reference.json').write_text(json.dumps(ref,indent=2)+'\n')


def previous_image():
    data=(ROOT/'out/handoff-ubuntu-3-input/boot.img').read_bytes()
    if len(data)!=PREVIOUS_BYTES or sha(data)!=PREVIOUS_SHA256:raise ValueError('ubuntu_3_image_pin')
    return data


def original_image():
    data=(ROOT/'out/boot-diagnostic-images/previous-boot-2.img').read_bytes()
    if len(data)!=53215232 or sha(data)!=BOOT2_SHA256:raise ValueError('boot_2_image_pin')
    return data


def ubuntu_initramfs(original):
    h=boot_header(original)
    ram=original[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]
    if sha(original)!=BOOT2_SHA256 or sha(ram)!=ORIGINAL_RAM_SHA256:
        raise ValueError('ubuntu_ramdisk_pin')
    items=entries(gzip.decompress(ram));by_name={i['name']:i for i in items}
    if sha(by_name['init']['data'])!=INIT_SHA256 or len(items)!=347:
        raise ValueError('original_init_pin')
    init=by_name['init']['data'].decode('ascii')
    init=replace_once(init,'mkdir -m 0755 /run/initramfs\n',
        'mkdir -m 0755 /run/initramfs\n. /ut-boot-functions\n'
        'echo "UT_BOOT_4: PID 1 STARTED" >/dev/kmsg\n'
        'ut_boot_trace_start\nPS4="UT_BOOT_4: + "\nset -x\nut_boot_stage ubuntu-init\n')
    for line,stage in [('run_scripts /scripts/init-top','udev-ready'),('mountroot','root-mounted'),
                       ('run_scripts /scripts/init-bottom','init-bottom-complete')]:
        init=replace_once(init,'\n'+line+'\n','\n'+line+'\nut_boot_stage '+stage+'\n')
    init=replace_once(init,'# Move virtual filesystems over to the real filesystem\n',
        'ut_boot_stage userspace-handoff\nut_boot_trace_stop\n# Move virtual filesystems over to the real filesystem\n')
    for before,stage in [('if read_fstab_entry /usr; then','usr-check-start'),
                         ('# Mount cleanup','root-cleanup-start'),
                         ('maybe_break bottom','init-bottom-start')]:
        init=replace_once(init,'\n'+before+'\n','\nut_boot_stage '+stage+'\n'+before+'\n')
    halium=by_name['scripts/halium']['data'].decode('ascii')
    start=halium.index('\ttell_kmsg "checking filesystem integrity for the userdata partition"\n')
    end=halium.index('\n\ttell_kmsg "mounting $path"',start)
    # Data was freshly formatted and diagnostic 2 mounted it successfully. Do not
    # repeat the upstream automatic e2fsck -y / resize path during this experiment.
    halium=halium[:start]+'\tut_boot_stage userdata-mount\n'+halium[end:]
    halium=replace_once(halium,'\tmount -o discard,$OPTIONS $path /tmpmnt\n',
        '\tmount -o discard,$OPTIONS $path /tmpmnt\n'
        '\tut_boot_stage userdata-mounted\n')
    halium=replace_once(halium,'\ttell_kmsg "mounting system rootfs at /halium-system"\n',
        '\tut_boot_stage system-mount\n\ttell_kmsg "mounting system rootfs at /halium-system"\n')
    halium=replace_once(halium,'\tidentify_android_image\n',
        '\tut_boot_stage system-mounted\n\tidentify_android_image\n')
    halium=replace_once(halium,'\tidentify_boot_mode\n',
        '\tut_boot_stage android-image-mounted\n\tidentify_boot_mode\n')
    # Capture every upstream panic before its optional USB handler or reboot.
    functions=by_name['scripts/functions']['data'].decode('ascii')
    functions=replace_once(functions,'panic()\n{\n',
        'panic()\n{\n\tut_boot_stage initramfs-panic\n')
    udev=by_name['scripts/init-bottom/udev']['data'].decode('ascii')
    udev=replace_once(udev,'udevadm control --exit\n',
        'printf "UT_BOOT_4: udev-control-start\\n"\nudevadm control --exit\n'
        'printf "UT_BOOT_4: udev-control-complete\\n"\n')
    modified={'init':init.encode(),'scripts/halium':halium.encode(),
              'scripts/functions':functions.encode(),'scripts/init-bottom/udev':udev.encode()}
    copied=[{'name':i['name'],'values':list(i['values']),
             'data':modified.get(i['name'],i['data'])} for i in items]
    for number,(name,source) in enumerate([('ut-boot-functions','functions'),('ut-boot-trace.awk','trace.awk')],1):
        helper=(ROOT/'tools/boot-observer'/source).read_bytes()
        if b'\r' in helper or len(helper)>16384:raise ValueError('boot_observer_invalid')
        if name in by_name:raise ValueError('observer_path_exists')
        copied.append({'name':name,'values':[max(i['values'][0] for i in items)+number,
            0o100644,0,0,1,0,len(helper),0,0,0,0,len(name)+1,0],'data':helper})
    payload=encode(copied)
    check={i['name']:i for i in entries(payload)}
    for name,item in by_name.items():
        expected=list(item['values']);expected[6]=len(modified.get(name,item['data']))
        if check[name]['values']!=expected or check[name]['data']!=modified.get(name,item['data']):
            raise ValueError('unrelated_ubuntu_ramdisk_entry_changed:'+name)
    if len(payload)>12*1024*1024:raise ValueError('ubuntu_initramfs_size')
    return payload


def configure(work):
    previous=previous_image();original=original_image();OUT.mkdir(parents=True,exist_ok=True)
    payload=ubuntu_initramfs(original);path=OUT/'initramfs.cpio';path.write_bytes(payload)
    (OUT/'previous-ubuntu-3.img').write_bytes(previous)
    kernel=work/'workdir/downloads/kernel-samsung-exynos9820'
    commit=subprocess.check_output(['git','-C',str(kernel),'rev-parse','HEAD'],text=True).strip()
    source=kernel/'init/initramfs.c'
    if commit!=KERNEL_COMMIT or sha(source.read_bytes())!=INITRAMFS_SOURCE_SHA256:
        raise ValueError('initramfs_kernel_source_changed')
    subprocess.run(['git','-C',str(kernel),'apply','--check',str(DIAGNOSTIC_PATCH)],check=True)
    subprocess.run(['git','-C',str(kernel),'apply',str(DIAGNOSTIC_PATCH)],check=True)
    fragment=(ROOT/'config/ubuntu-boot-handoff.config').read_text().replace('@UT_UBUNTU_CPIO@',str(path.resolve()))
    (kernel/'arch/arm64/configs/ubuntu-boot-handoff.config').write_text(fragment)
    info=work/'deviceinfo'
    info.write_text(info.read_text()+'\n# Ubuntu BOOT 4, observed built-in initramfs.\n'
        'deviceinfo_kernel_defconfig="exynos9820-beyond2lte_defconfig ubuntu-touch.config ubuntu-boot-handoff.config"\n')
    (OUT/'ubuntu-boot-source.json').write_text(json.dumps({'kernel_commit':commit,
        'normal_build_manifest':json.loads((work/'source-manifest.json').read_text()),
        'force_patch_sha256':sha(DIAGNOSTIC_PATCH.read_bytes()),
        'patched_initramfs_source_sha256':sha(source.read_bytes()),
        'original_ubuntu_ramdisk_sha256':ORIGINAL_RAM_SHA256,'original_init_sha256':INIT_SHA256,
        'initramfs_sha256':sha(payload),'initramfs_bytes':len(payload),
        'modified_entries':['init','scripts/halium','scripts/functions','scripts/init-bottom/udev'],
        'added_entries':['ut-boot-functions','ut-boot-trace.awk'],
        'runtime_automatic_fsck_resize_disabled':True,
        'pid1_global_sync_removed':True,'trace_bytes_limit':4194304,
        'passive_wait_samples':12,'passive_wait_interval_seconds':10},indent=2)+'\n')


def embedded_archive(kernel,payload):
    matches=[];offset=0
    while True:
        offset=kernel.find(b'\x1f\x8b\x08',offset)
        if offset<0:break
        try:
            decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
            got=decoder.decompress(kernel[offset:],len(payload)+1)
            if decoder.eof and got==payload:
                matches.append((offset,len(kernel[offset:])-len(decoder.unused_data)))
        except zlib.error:pass
        offset+=1
    if len(matches)!=1:raise ValueError('builtin_ubuntu_archive_missing_or_ambiguous')
    return matches[0]


def compose(previous,compiled,payload):
    if sha(previous)!=PREVIOUS_SHA256 or len(previous)!=PREVIOUS_BYTES:
        raise ValueError('ubuntu_3_image_pin')
    kernel=image_kernel(compiled);embedded_archive(kernel,payload)
    if kernel[56:60]!=b'ARM\x64':raise ValueError('kernel_architecture')
    old=config_values(kernel_config(image_kernel(previous)));new=config_values(kernel_config(kernel))
    differences={k:{'before':old.get(k,'n'),'after':new.get(k,'n')} for k in sorted(set(old)|set(new))
                 if old.get(k,'n')!=new.get(k,'n')}
    allowed={'CONFIG_INITRAMFS_SOURCE'}
    if set(differences)-allowed:raise ValueError('unrelated_kernel_config_changed')
    if (new.get('CONFIG_INITRAMFS_FORCE')!='y' or new.get('CONFIG_INITRAMFS_COMPRESSION_GZIP')!='y'
            or new.get('CONFIG_ANDROID_SAR_RAMDISK')!='y' or new.get('CONFIG_CMDLINE_EXTEND')!='y'
            or new.get('CONFIG_ANDROID_BOOT_PARTITION')!='"/dev/sda14"'):
        raise ValueError('ubuntu_builtin_config_invalid')
    ramdisk=gzip.compress(payload,compresslevel=9,mtime=0)
    h=boot_header(previous);page=h['page_bytes'];header=bytearray(previous[:page])
    struct.pack_into('<I',header,8,len(kernel));struct.pack_into('<I',header,16,len(ramdisk))
    digest=__import__('hashlib').sha1()
    for data in (kernel,ramdisk,b'',b'',b''):digest.update(data);digest.update(struct.pack('<I',len(data)))
    header[576:608]=digest.digest()+b'\0'*12
    image=bytes(header)+kernel+b'\0'*(aligned(len(kernel),page)-len(kernel))
    image+=ramdisk+b'\0'*(aligned(len(ramdisk),page)-len(ramdisk))
    if len(image)>PARTITION_BYTES:raise ValueError('ubuntu_boot_partition_overflow')
    changes={i for i,(a,b) in enumerate(zip(previous[:page],header)) if a!=b}
    if changes-set(range(8,12))-set(range(16,20))-set(range(576,608)):
        raise ValueError('unrelated_header_changed')
    return image,differences


def finalize(work):
    previous=previous_image();payload=(OUT/'initramfs.cpio').read_bytes()
    image,differences=compose(previous,(work/'workdir/tmp/partitions/boot.img').read_bytes(),payload)
    kernel=image_kernel(image);h=boot_header(image);offset,size=embedded_archive(kernel,payload)
    config=(work/'workdir/downloads/KERNEL_OBJ/.config').read_text()
    if config_values(config)!=config_values(kernel_config(kernel)):raise ValueError('compiled_config_mismatch')
    (OUT/'boot.img').write_bytes(image);(OUT/'kernel.config').write_text(config)
    lock={'schema':1,'boot_version':4,'purpose':'original_ubuntu_init_through_builtin_initramfs',
        'boot_sha256':sha(image),'boot_bytes':len(image),'boot_partition_bytes':PARTITION_BYTES,
        'previous_boot_sha256':PREVIOUS_SHA256,'previous_boot_bytes':PREVIOUS_BYTES,
        'kernel_sha256':sha(kernel),'kernel_bytes':len(kernel),'kernel_source_commit':KERNEL_COMMIT,
        'kernel_config_differences':differences,'builtin_initramfs_sha256':sha(payload),
        'builtin_initramfs_bytes':len(payload),'builtin_compressed_offset':offset,'builtin_compressed_bytes':size,
        'force_builtin_initramfs':True,'ramdisk_sha256':sha(image[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]),
        'ramdisk_bytes':h['ramdisk_bytes'],'external_ramdisk_matches_builtin':True,
        'unrelated_header_fields_preserved':True,'target_device':'/dev/block/sda14',
        'system_write_requested':False,'vendor_write_requested':False,'data_format_requested':False,
        'runtime_automatic_fsck_resize_disabled':True,'runtime_log_directory':'/data/ubuntu-touch-boot-4',
        'runtime_log_attempts_limit':5,'trace_bytes_limit':4194304,
        'passive_wait_samples':12,'passive_wait_interval_seconds':10,
        'ubuntu_init_execution_requested':True,
        'hardware_tested':False,'ubuntu_touch_boot_verified':False}
    (OUT/'ubuntu-boot-handoff.lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print(json.dumps(lock,indent=2))


def fetch_images():
    ref=obtain_job(int(os.environ['GITHUB_RUN_ID']),os.environ['GITHUB_SHA'],'ubuntu-handoff-images.zip',
        'beyond2lte-ubuntu-boot-handoff-images','images',os.environ['UT_ARTIFACT_TOKEN'])
    extract_zip(ROOT/'out/ubuntu-handoff-images.zip',OUT,['boot.img','previous-ubuntu-3.img',
        'initramfs.cpio','kernel.config','ubuntu-boot-source.json','ubuntu-boot-handoff.lock.json','ubuntu-handoff-tests.json'])
    (ROOT/'out/ubuntu-handoff-artifact-reference.json').write_text(json.dumps(ref,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['inputs','configure','finalize','images'])
    p.add_argument('--work',type=Path);a=p.parse_args()
    if a.phase in ('configure','finalize') and a.work is None:p.error('--work is required')
    if a.phase=='inputs':inputs()
    elif a.phase=='configure':configure(a.work.resolve())
    elif a.phase=='finalize':finalize(a.work.resolve())
    else:fetch_images()
