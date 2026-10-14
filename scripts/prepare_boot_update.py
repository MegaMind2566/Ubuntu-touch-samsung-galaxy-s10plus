"""Preserve the installed boot header/ramdisk while replacing its fixed kernel.

CI artifact preparation only. This script never opens a handset or a device.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import tarfile
import io
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from inspect_stock_firmware import boot_header, aligned, newc_files
from github_artifacts import REPO

ORIGINAL_ARTIFACT=11770694913
ORIGINAL_ZIP_BYTES=37243074
ORIGINAL_ZIP_SHA256='9f63fe26d4cff97a7735eda09a3f5fe61ffabe6b2c465be2c8f75d892a304e7c'
ORIGINAL_BOOT_BYTES=53215232
ORIGINAL_BOOT_SHA256='0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc'
RAMDISK_BYTES=4108120
RAMDISK_SHA256='439b535193a8e6315e3da3884755db49b04794c28d5e06686fc595dfab8f5a4c'
BOOT_PARTITION_BYTES=57671680
KERNEL_COMMIT='b9b70b29c94c41365704fcc2ed33be09b4617907'
PREVIOUS_BOOT_SHA256='d3be319ae9353908e917894d624460e743bfc078d676c592189d415ef02b0993'
SAR_INIT_SHA256='2b4684d53f7a756f97ba9deb9310e7156ecddae7ffbae629661ec36c7634401b'


def digest(data):return hashlib.sha256(data).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def download_archive(path):
    token=os.environ.get('UT_ARTIFACT_TOKEN')
    if not token:raise ValueError('Supply the original adaptation archive or a scoped CI artifact token')
    url='https://api.github.com/repos/'+REPO+'/actions/artifacts/'+str(ORIGINAL_ARTIFACT)+'/zip'
    request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    try:
        urllib.request.build_opener(NoRedirect()).open(request,timeout=45)
        raise ValueError('artifact_redirect_missing')
    except urllib.error.HTTPError as error:
        if error.code!=302:raise
        location=error.headers['Location']
    parsed=urllib.parse.urlsplit(location)
    if parsed.scheme!='https' or not parsed.hostname.endswith('.blob.core.windows.net'):
        raise ValueError('artifact_storage_host_unexpected')
    # The GitHub token is never sent to signed object storage.
    with urllib.request.urlopen(location,timeout=60) as source,path.open('xb') as output:
        size=0
        while chunk:=source.read(1024*1024):
            size+=len(chunk)
            if size>ORIGINAL_ZIP_BYTES:raise ValueError('artifact_too_large')
            output.write(chunk)


def baseline(out, archive=None):
    folder=out/'boot-baseline';folder.mkdir(parents=True,exist_ok=True)
    boot_path=folder/'boot.img';ramdisk_path=folder/'ramdisk.img'
    if boot_path.is_file() and ramdisk_path.is_file():
        boot=boot_path.read_bytes();ramdisk=ramdisk_path.read_bytes()
        if (len(boot)!=ORIGINAL_BOOT_BYTES or digest(boot)!=ORIGINAL_BOOT_SHA256 or
                len(ramdisk)!=RAMDISK_BYTES or digest(ramdisk)!=RAMDISK_SHA256):
            raise ValueError('cached_boot_baseline_mismatch')
        return boot_path,ramdisk_path
    if archive is None:
        archive=folder/'original-adaptation.zip'
        if not archive.exists():download_archive(archive)
    data=Path(archive).read_bytes()
    if len(data)!=ORIGINAL_ZIP_BYTES or digest(data)!=ORIGINAL_ZIP_SHA256:
        raise ValueError('original_adaptation_mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        boot=package.read('boot.img')
    if len(boot)!=ORIGINAL_BOOT_BYTES or digest(boot)!=ORIGINAL_BOOT_SHA256:
        raise ValueError('original_boot_mismatch')
    header=boot_header(boot)
    ramdisk=boot[header['ramdisk_offset']:header['ramdisk_offset']+header['ramdisk_bytes']]
    if len(ramdisk)!=RAMDISK_BYTES or digest(ramdisk)!=RAMDISK_SHA256:
        raise ValueError('installed_ramdisk_mismatch')
    newc_files(gzip.decompress(ramdisk))
    boot_path.write_bytes(boot);ramdisk_path.write_bytes(ramdisk)
    return boot_path,ramdisk_path


def compose(original, compiled):
    if len(original)!=ORIGINAL_BOOT_BYTES or digest(original)!=ORIGINAL_BOOT_SHA256:
        raise ValueError('original_boot_mismatch')
    before=boot_header(original);after=boot_header(compiled)
    if (before['second_bytes'] or before['recovery_dtbo_bytes'] or
            before['boot_id_variant']!='lineage-empty-legacy-dt'):
        raise ValueError('original_boot_layout_unexpected')
    kernel=compiled[after['page_bytes']:after['page_bytes']+after['kernel_bytes']]
    if kernel[56:60]!=b'ARM\x64':raise ValueError('compiled_kernel_architecture')
    ramdisk=original[before['ramdisk_offset']:before['ramdisk_offset']+before['ramdisk_bytes']]
    if digest(ramdisk)!=RAMDISK_SHA256:raise ValueError('ramdisk_changed')
    page=before['page_bytes'];header=bytearray(original[:page])
    struct.pack_into('<I',header,8,len(kernel))
    sha=hashlib.sha1()
    for payload in (kernel,ramdisk,b'',b'',b''):
        sha.update(payload);sha.update(struct.pack('<I',len(payload)))
    header[576:608]=sha.digest()+b'\0'*12
    rebuilt=(bytes(header)+kernel+b'\0'*(aligned(len(kernel),page)-len(kernel))+
             ramdisk+b'\0'*(aligned(len(ramdisk),page)-len(ramdisk)))
    if len(rebuilt)>BOOT_PARTITION_BYTES:raise ValueError('boot_partition_overflow')
    checked=boot_header(rebuilt)
    if (checked['cmdline']!=before['cmdline'] or checked['ramdisk_bytes']!=RAMDISK_BYTES or
            rebuilt[checked['ramdisk_offset']:checked['ramdisk_offset']+RAMDISK_BYTES]!=ramdisk):
        raise ValueError('baseline_header_or_ramdisk_changed')
    for start,end in ((0,8),(12,576),(608,page)):
        if rebuilt[start:end]!=original[start:end]:raise ValueError('unrelated_header_change')
    return rebuilt,checked


def finalize(out, work):
    original=(out/'boot-baseline/boot.img').read_bytes()
    rebuilt,header=compose(original,(out/'boot.img').read_bytes())
    source=work/'workdir/downloads/kernel-samsung-exynos9820/init/sar_ramdisk/sar_ramdisk.c'
    if 'unsigned int rd_offset = 0;' not in source.read_text():raise ValueError('sar_offset_fix_missing')
    init_source=work/'workdir/downloads/kernel-samsung-exynos9820/init/main.c'
    if digest(init_source.read_bytes())!=SAR_INIT_SHA256:raise ValueError('sar_init_handoff_fix_missing')
    config=(out/'kernel.config').read_text()
    if 'CONFIG_ANDROID_SAR_RAMDISK=y' not in config or 'CONFIG_ANDROID_BOOT_PARTITION="/dev/sda14"' not in config:
        raise ValueError('normal_boot_ramdisk_path_changed')
    manifest=json.loads((out/'source-manifest.json').read_text())
    if manifest['sources']['sources']['kernel']['commit']!=KERNEL_COMMIT:raise ValueError('kernel_source_changed')
    patch_names=[Path(p['path']).name for p in manifest['kernel_patches']]
    if patch_names!=['0001-apparmor-socket-mediation.patch','0002-apparmor-af-unix-mediation.patch','0003-initialize-sar-ramdisk-offset.patch','0004-restore-init-after-sar-ramdisk-load.patch']:
        raise ValueError('kernel_patch_set_changed')
    tarpath=out/'device_beyond2lte.tar.xz';temporary=out/'device_beyond2lte.tar.corrected.xz'
    count=0
    with tarfile.open(tarpath,'r:xz') as old,tarfile.open(temporary,'w:xz') as new:
        for member in old.getmembers():
            if member.name=='partitions/boot.img':
                count+=1;member.size=len(rebuilt);new.addfile(member,io.BytesIO(rebuilt))
            else:new.addfile(member,old.extractfile(member) if member.isfile() else None)
    if count!=1:raise ValueError('device_tar_boot_entry_count')
    temporary.replace(tarpath);(out/'boot.img').write_bytes(rebuilt)
    (out/'ramdisk.sha256').write_text(RAMDISK_SHA256+'  original-installed-ramdisk.img\n')
    manifest['ramdisk_preserved_from_installed_candidate']={'bytes':RAMDISK_BYTES,'sha256':RAMDISK_SHA256,'baseline_boot_sha256':ORIGINAL_BOOT_SHA256}
    (out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    report={'schema':1,'update_version':2,'correction':'Restore the requested init command after Samsung SAR loads the installed ramdisk',
            'original_boot_sha256':ORIGINAL_BOOT_SHA256,'original_boot_bytes':ORIGINAL_BOOT_BYTES,
            'previous_boot_sha256':PREVIOUS_BOOT_SHA256,'previous_boot_bytes':ORIGINAL_BOOT_BYTES,
            'boot_sha256':digest(rebuilt),'boot_bytes':len(rebuilt),'boot_partition_bytes':BOOT_PARTITION_BYTES,
            'ramdisk_sha256':RAMDISK_SHA256,'ramdisk_bytes':RAMDISK_BYTES,'ramdisk_preserved':True,
            'unrelated_header_fields_preserved':True,'system_changes_requested':False,'vendor_changes_requested':False,
            'kernel_source_commit':KERNEL_COMMIT,'fixed_loader_source_sha256':digest(source.read_bytes()),
            'fixed_init_source_sha256':SAR_INIT_SHA256,
            'kernel_patches':manifest['kernel_patches'],'kernel_header':header,'hardware_boot_verified':False}
    (out/'boot-fix-report.json').write_text(json.dumps(report,indent=2)+'\n')
    lock={'schema':1,'update_version':2,'model':'SM-G975F','pda':'G975FXXSGHWC1',
          'target_partition':'BOOT','target_device':'/dev/block/sda14',
          'previous_boot_bytes':ORIGINAL_BOOT_BYTES,'previous_boot_sha256':PREVIOUS_BOOT_SHA256,
          'boot_bytes':len(rebuilt),'boot_sha256':digest(rebuilt),'boot_partition_bytes':BOOT_PARTITION_BYTES,
          'ramdisk_bytes':RAMDISK_BYTES,'ramdisk_sha256':RAMDISK_SHA256,'kernel_source_commit':KERNEL_COMMIT,
          'correction':report['correction'],'hardware_boot_verified':False}
    (out/'boot-update-2.lock.json').write_text(json.dumps(lock,indent=2)+'\n')
    print(json.dumps(report,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('inputs','finalize'))
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--work',type=Path)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    if args.phase=='inputs':
        paths=baseline(args.out,args.archive)
        print('Verified installed BOOT baseline and exact embedded ramdisk: '+str(paths[0]))
    else:
        if args.work is None:parser.error('--work is required for finalize')
        finalize(args.out,args.work)


if __name__=='__main__':main()
