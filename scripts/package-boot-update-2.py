"""Package the corrected SAR init handoff and immutable version 1 rollback BOOT."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from prepare_boot_update import compose, ORIGINAL_BOOT_SHA256, RAMDISK_SHA256, KERNEL_COMMIT, PREVIOUS_BOOT_SHA256, SAR_INIT_SHA256

ROOT=Path(__file__).resolve().parents[1]


def render_template(text,digest,size):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or not 1648<=size<=57671680:
        raise ValueError('template_pins_invalid')
    text=text.replace('__BOOT_UPDATE_SHA256__',digest).replace('__BOOT_UPDATE_BYTES__',str(size))
    if '__BOOT_UPDATE_' in text:raise ValueError('template_not_fully_rendered')
    return text


def package(build_archive,previous_archive,baseline_boot,output):
    original=baseline_boot.read_bytes()
    if hashlib.sha256(original).hexdigest()!=ORIGINAL_BOOT_SHA256:raise ValueError('baseline_boot_mismatch')
    with zipfile.ZipFile(previous_archive) as source:previous=source.read('boot.img')
    if len(previous)!=53215232 or hashlib.sha256(previous).hexdigest()!=PREVIOUS_BOOT_SHA256:raise ValueError('previous_boot_mismatch')
    with zipfile.ZipFile(build_archive) as source:
        image=source.read('boot.img');lock=json.loads(source.read('boot-update-2.lock.json'))
        report=json.loads(source.read('boot-fix-report.json'));manifest=json.loads(source.read('source-manifest.json'))
        regression=json.loads(source.read('sar-init-handoff-test.json'))
    rebuilt,_=compose(original,image)
    if rebuilt!=image:raise ValueError('installed_header_or_ramdisk_changed')
    digest=hashlib.sha256(image).hexdigest();size=len(image)
    if (digest in (ORIGINAL_BOOT_SHA256,PREVIOUS_BOOT_SHA256) or lock['update_version']!=2 or
            lock['boot_sha256']!=digest or lock['boot_bytes']!=size or lock['previous_boot_sha256']!=PREVIOUS_BOOT_SHA256 or
            lock['ramdisk_sha256']!=RAMDISK_SHA256 or lock['kernel_source_commit']!=KERNEL_COMMIT or
            lock['target_device']!='/dev/block/sda14' or report['boot_sha256']!=digest or report['fixed_init_source_sha256']!=SAR_INIT_SHA256 or
            not report['ramdisk_preserved'] or not report['unrelated_header_fields_preserved'] or
            regression['fixed_source_sha256']!=SAR_INIT_SHA256 or
            regression['cases']['original_sar']['late_init']['selected_init']!='/sbin/init' or
            regression['cases']['corrected_sar']['late_init']['selected_init']!='/init' or
            [Path(p['path']).name for p in manifest['kernel_patches']]!=[
                '0001-apparmor-socket-mediation.patch','0002-apparmor-af-unix-mediation.patch',
                '0003-initialize-sar-ramdisk-offset.patch','0004-restore-init-after-sar-ramdisk-load.patch']):
        raise ValueError('boot_handoff_build_evidence_mismatch')
    members={'boot-update-2/boot.img':image,'boot-update-1/boot.img':previous,
             'config/boot-update-2.lock.json':json.dumps(lock,indent=2).encode(),
             'boot-update-2/boot-fix-report.json':json.dumps(report,indent=2).encode(),
             'boot-update-2/sar-init-handoff-test.json':json.dumps(regression,indent=2).encode()}
    for template,name in [('install-boot-update-2.ps1.in','install-boot-update-2.ps1'),('verify_boot_update_2.py.in','verify_boot_update_2.py')]:
        members['scripts/'+name]=render_template((ROOT/'scripts'/template).read_text(),digest,size).encode('ascii')
    for name in ['install-ubuntu-twrp.ps1','install-ubuntu-touch.ps1','check-recovery.ps1','flash-recovery-test.ps1',
                 'check-download-mode.ps1','prepare_ubuntu_install.py','verify_recovery_test.py']:
        members['scripts/'+name]=(ROOT/'scripts'/name).read_bytes()
    for name in ['INSTALLA-CORREZIONE-AVVIO.cmd','RIPRISTINA-BOOT-1.cmd','LEGGIMI-CORREZIONE-AVVIO.txt']:
        members[name]=(ROOT/'tools/windows'/name).read_bytes()
    for name,data in list(members.items()):
        if name.endswith(('.ps1','.cmd','.txt')):members[name]=data.decode('ascii').replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
    members['SHA256SUMS']=(''.join(hashlib.sha256(v).hexdigest()+'  '+n+'\n' for n,v in sorted(members.items()))).encode('ascii')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(members.items()):z.writestr(name,data)
    print(json.dumps({'file':str(output),'zip_bytes':output.stat().st_size,'boot_bytes':size,'boot_sha256':digest,'previous_boot_sha256':PREVIOUS_BOOT_SHA256}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-archive',type=Path,required=True);p.add_argument('--previous-archive',type=Path,required=True)
    p.add_argument('--baseline-boot',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-correzione-AVVIO-Windows.zip')
    a=p.parse_args();package(a.build_archive,a.previous_archive,a.baseline_boot,a.output)
