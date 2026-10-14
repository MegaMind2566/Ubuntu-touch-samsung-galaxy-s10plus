"""Package the verified BOOT-only correction for the existing Windows tools."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from prepare_boot_update import compose, ORIGINAL_BOOT_SHA256, RAMDISK_SHA256, KERNEL_COMMIT

ROOT=Path(__file__).resolve().parents[1]


def render_template(text, digest, size):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or not 1648<=size<=57671680:
        raise ValueError('template_pins_invalid')
    text=text.replace('__BOOT_UPDATE_SHA256__',digest).replace('__BOOT_UPDATE_BYTES__',str(size))
    if '__BOOT_UPDATE_' in text:raise ValueError('template_not_fully_rendered')
    return text


def package(build_archive, baseline_boot, output):
    original=baseline_boot.read_bytes()
    if hashlib.sha256(original).hexdigest()!=ORIGINAL_BOOT_SHA256:raise ValueError('baseline_boot_mismatch')
    with zipfile.ZipFile(build_archive) as source:
        image=source.read('boot.img')
        lock=json.loads(source.read('boot-update-1.lock.json'))
        report=json.loads(source.read('boot-fix-report.json'))
        manifest=json.loads(source.read('source-manifest.json'))
    rebuilt,_=compose(original,image)
    if rebuilt!=image:raise ValueError('new_boot_does_not_preserve_installed_header_and_ramdisk')
    digest=hashlib.sha256(image).hexdigest();size=len(image)
    if (digest==ORIGINAL_BOOT_SHA256 or lock['boot_sha256']!=digest or lock['boot_bytes']!=size or
            lock['ramdisk_sha256']!=RAMDISK_SHA256 or lock['kernel_source_commit']!=KERNEL_COMMIT or
            lock['target_device']!='/dev/block/sda14' or report['boot_sha256']!=digest or
            not report['ramdisk_preserved'] or not report['unrelated_header_fields_preserved'] or
            [Path(x['path']).name for x in manifest['kernel_patches']]!=[
                '0001-apparmor-socket-mediation.patch','0002-apparmor-af-unix-mediation.patch','0003-initialize-sar-ramdisk-offset.patch']):
        raise ValueError('boot_update_build_evidence_mismatch')
    members={'boot-update-1/boot.img':image,'config/boot-update-1.lock.json':json.dumps(lock,indent=2).encode(),
             'boot-update-1/boot-fix-report.json':json.dumps(report,indent=2).encode()}
    for template,name in (('install-boot-update.ps1.in','install-boot-update.ps1'),('verify_boot_update.py.in','verify_boot_update.py')):
        members['scripts/'+name]=render_template((ROOT/'scripts'/template).read_text(),digest,size).encode('ascii')
    for name in ('install-ubuntu-twrp.ps1','install-ubuntu-touch.ps1','check-recovery.ps1','flash-recovery-test.ps1',
                 'check-download-mode.ps1','prepare_ubuntu_install.py','verify_recovery_test.py'):
        members['scripts/'+name]=(ROOT/'scripts'/name).read_bytes()
    for name in ('INSTALLA-CORREZIONE-BOOT.cmd','RIPRISTINA-BOOT-PRECEDENTE.cmd','LEGGIMI-CORREZIONE-BOOT.txt'):
        members[name]=(ROOT/'tools/windows'/name).read_bytes()
    for name,value in list(members.items()):
        if name.endswith(('.ps1','.cmd','.txt')):
            members[name]=value.decode('ascii').replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
    members['SHA256SUMS']=(''.join(hashlib.sha256(value).hexdigest()+'  '+name+'\n' for name,value in sorted(members.items()))).encode('ascii')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,value in sorted(members.items()):archive.writestr(name,value)
    print(json.dumps({'file':str(output),'zip_bytes':output.stat().st_size,'boot_bytes':size,'boot_sha256':digest}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-archive',type=Path,required=True)
    parser.add_argument('--baseline-boot',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-correzione-BOOT-Windows.zip')
    args=parser.parse_args();package(args.build_archive,args.baseline_boot,args.output)
