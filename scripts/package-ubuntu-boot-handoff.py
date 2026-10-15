"""Package BOOT 4, the exact Ubuntu BOOT 3 rollback and a read-only log reader."""
import argparse
import gzip
import json
from pathlib import Path
import zipfile

from ubuntu_boot_handoff import (ROOT,OUT,PREVIOUS_SHA256,PREVIOUS_BYTES,sha,
    image_kernel,kernel_config,config_values,ubuntu_initramfs,original_image,embedded_archive)
from inspect_stock_firmware import boot_header,aligned


def render(text,lock):
    text=text.replace('__BOOT_UPDATE_SHA256__',lock['boot_sha256']).replace('__BOOT_UPDATE_BYTES__',str(lock['boot_bytes']))
    if '__BOOT_UPDATE_' in text:raise ValueError('unrendered_template')
    return text


def identity(text):
    return (text.replace('boot-update-1','boot-update-3').replace('boot-update-2','boot-update-4')
        .replace('verify_boot_update_2.py','verify_ubuntu_boot_4.py')
        .replace('BOOT handoff with spaces','BOOT Ubuntu 4 with spaces')
        .replace('INSTALLA-CORREZIONE-AVVIO.cmd','INSTALLA-AVVIO-UBUNTU-4.cmd')
        .replace('RIPRISTINA-BOOT-1.cmd','RIPRISTINA-AVVIO-UBUNTU-3.cmd'))


def validate(folder):
    previous=(folder/'previous-ubuntu-3.img').read_bytes();image=(folder/'boot.img').read_bytes()
    lock=json.loads((folder/'ubuntu-boot-handoff.lock.json').read_text());payload=(folder/'initramfs.cpio').read_bytes()
    if (sha(previous)!=PREVIOUS_SHA256 or len(previous)!=PREVIOUS_BYTES or lock['boot_version']!=4
            or lock['hardware_tested'] or lock['ubuntu_touch_boot_verified']
            or sha(image)!=lock['boot_sha256'] or len(image)!=lock['boot_bytes'] or len(image)>57671680):
        raise ValueError('ubuntu_boot_identity')
    if payload!=ubuntu_initramfs(original_image()) or sha(payload)!=lock['builtin_initramfs_sha256']:
        raise ValueError('ubuntu_payload_changed')
    # Verify immutable firmware bytes without recompressing them on the host.
    # Python/zlib versions can emit a different gzip OS byte for the same CPIO.
    h=boot_header(image);before=boot_header(previous);kernel=image_kernel(image)
    ramdisk=image[h['ramdisk_offset']:h['ramdisk_offset']+h['ramdisk_bytes']]
    embedded_archive(kernel,payload)
    old=config_values(kernel_config(image_kernel(previous)));new=config_values(kernel_config(kernel))
    differences={k:{'before':old.get(k,'n'),'after':new.get(k,'n')} for k in sorted(set(old)|set(new))
                 if old.get(k,'n')!=new.get(k,'n')}
    allowed={'CONFIG_INITRAMFS_SOURCE'}
    page=h['page_bytes'];changes={i for i,(a,b) in enumerate(zip(previous[:page],image[:page])) if a!=b}
    layout=image[:page]+kernel+b'\0'*(aligned(len(kernel),page)-len(kernel))
    layout+=ramdisk+b'\0'*(aligned(len(ramdisk),page)-len(ramdisk))
    if (set(differences)-allowed or differences!=lock['kernel_config_differences']
            or new.get('CONFIG_INITRAMFS_FORCE')!='y' or new.get('CONFIG_INITRAMFS_COMPRESSION_GZIP')!='y'
            or new.get('CONFIG_ANDROID_SAR_RAMDISK')!='y' or new.get('CONFIG_CMDLINE_EXTEND')!='y'
            or new.get('CONFIG_ANDROID_BOOT_PARTITION')!='"/dev/sda14"'
            or page!=before['page_bytes'] or kernel[56:60]!=b'ARM\x64'
            or changes-set(range(8,12))-set(range(16,20))-set(range(576,608))
            or not h['boot_id_sha1_valid'] or h['boot_id_variant']!='lineage-empty-legacy-dt'
            or image[596:608]!=b'\0'*12 or image!=layout
            or len(kernel)!=lock['kernel_bytes'] or len(ramdisk)!=lock['ramdisk_bytes']
            or sha(kernel)!=lock['kernel_sha256'] or sha(ramdisk)!=lock['ramdisk_sha256']
            or gzip.decompress(ramdisk)!=payload
            or config_values((folder/'kernel.config').read_text())!=new):
        raise ValueError('ubuntu_boot_structure')
    return image,previous,lock


def collector(lock):
    return render((ROOT/'scripts/collect-ubuntu-handoff.py.in').read_text(),lock)


def package(folder,output):
    image,previous,lock=validate(folder)
    script=identity((ROOT/'scripts/templates/verified-boot-install.ps1.in').read_text())
    script=script.replace("$script:BootPreviousHash='d3be319ae9353908e917894d624460e743bfc078d676c592189d415ef02b0993'",
                          "$script:BootPreviousHash='"+PREVIOUS_SHA256+"'")
    script=script.replace('$script:BootPreviousBytes=53215232','$script:BootPreviousBytes='+str(PREVIOUS_BYTES))
    script=script.replace('schema=1;update_version=2;',
                          'schema=1;update_version=6;boot_version=4;purpose="ubuntu_init_trace_and_waits";')
    footer="""        Write-Host 'AGGIORNAMENTO BOOT COMPLETATO E VERIFICATO.'
        Write-Host 'Ora in TWRP: Reboot > System. Se propone l app TWRP, scegli Do Not Install.'
        Write-Host 'Invia il rapporto e la schermata ottenuta al primo avvio.'"""
    if footer not in script:raise ValueError('mode_footer_anchor')
    script=script.replace(footer,"""        if ($UpdateMode -ceq 'Apply') {
            Write-Host 'BOOT UBUNTU 4 INSTALLATO E VERIFICATO.'
            Write-Host 'Ora TWRP > Reboot > System. Se propone l app TWRP, scegli Do Not Install.'
            Write-Host 'Attendi fino a 3 minuti. Fotografa la schermata e inviala.'
            Write-Host 'Se resta bloccato, torna in TWRP e usa LEGGI-AVVIO-UBUNTU-4.cmd.'
        } else {
            Write-Host 'BOOT UBUNTU 3 RIPRISTINATO E VERIFICATO.'
            Write-Host 'Il telefono resta in TWRP. Invia il rapporto di ripristino.'
        }""",1)
    verifier=(ROOT/'scripts/templates/verified-boot-image.py.in').read_text()
    verifier=verifier.replace('439b535193a8e6315e3da3884755db49b04794c28d5e06686fc595dfab8f5a4c',lock['ramdisk_sha256'])
    verifier=verifier.replace('rsize!=4108120','rsize!='+str(lock['ramdisk_bytes']))
    verifier=verifier.replace('BOOT corretto verificato. Ramdisk e selettore di SYSTEM conservati.',
                              'BOOT Ubuntu 4 verificato. Initramfs Ubuntu integrato; selettore di SYSTEM conservato.')
    members={'boot-update-4/boot.img':image,'boot-update-3/boot.img':previous,
        'config/ubuntu-boot-handoff.lock.json':json.dumps(lock,indent=2).encode(),
        'scripts/install-boot-update-4.ps1':render(script,lock).encode('ascii'),
        'scripts/verify_ubuntu_boot_4.py':render(verifier,lock).encode('ascii'),
        'scripts/collect-ubuntu-handoff.py':collector(lock).encode('ascii'),
        'boot-update-4/ubuntu-handoff-tests.json':(folder/'ubuntu-handoff-tests.json').read_bytes()}
    for name in ['install-ubuntu-twrp.ps1','install-ubuntu-touch.ps1','check-recovery.ps1','flash-recovery-test.ps1',
                 'check-download-mode.ps1','prepare_ubuntu_install.py','verify_recovery_test.py','collect-first-boot.py']:
        members['scripts/'+name]=(ROOT/'scripts'/name).read_bytes()
    for name in ['INSTALLA-AVVIO-UBUNTU-4.cmd','LEGGI-AVVIO-UBUNTU-4.cmd','RIPRISTINA-AVVIO-UBUNTU-3.cmd','LEGGIMI-AVVIO-UBUNTU-4.txt']:
        members[name]=(ROOT/'tools/windows'/name).read_bytes()
    for name,value in list(members.items()):
        if name.endswith(('.ps1','.cmd','.txt')):members[name]=value.decode('ascii').replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
    members['SHA256SUMS']=''.join(sha(v)+'  '+n+'\n' for n,v in sorted(members.items())).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,value in sorted(members.items()):z.writestr(name,value)
    test=identity((ROOT/'tests/test-boot-template.ps1').read_text())
    test=test.replace('ubuntu-boot-update-apply-state.json','ubuntu-boot-update-3-apply-state.json')
    test=test.replace('version 1 checkpoint preserved and does not block version 2','Ubuntu BOOT 3 checkpoint preserved and does not block Ubuntu BOOT 4')
    test=test.replace('version 1 cannot be mistaken for version 2','Ubuntu BOOT 3 cannot be mistaken for Ubuntu BOOT 4')
    test=test.replace('version 2 update/restore cases','Ubuntu BOOT 4 update/restore cases')
    test=test.replace('version 1/version 2 BOOT','Ubuntu BOOT 3/Ubuntu BOOT 4')
    test=test.replace('param([string]$Cmd)','param([string]$Cmd,[string]$Expected="previous_boot_update_needs_review")')
    test=test.replace("$output -match 'previous_boot_update_needs_review'","$output -match $Expected")
    anchor="    Write-Host 'PASS: 24"
    if anchor not in test:raise ValueError('native_collector_test_anchor')
    extra=r'''    $adbSource=Join-Path $script:BootTestRoot 'platform-tools\adb.exe'
    $adbHidden=Join-Path $script:BootTestRoot 'platform-tools\adb-test-hidden.exe'
    Move-Item -LiteralPath $adbSource -Destination $adbHidden
    try {
        Invoke-BootNativeEntry 'LEGGI-AVVIO-UBUNTU-4.cmd' 'Lettura fermata: local_tools_unavailable'
        $logZip=[IO.Compression.ZipFile]::OpenRead((Join-Path $script:BootTestRoot 'ubuntu-boot-4-log-report.zip'))
        try {
            $reader=New-Object IO.StreamReader($logZip.GetEntry('ubuntu-boot-log-report.json').Open())
            try { $logReport=$reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            Assert-BootTest ($logReport.boot_version -eq 4 -and $logReport.error -ceq 'local_tools_unavailable' -and
                $logReport.steps.Count -eq 0 -and -not $logReport.partition_writes -and -not $logReport.mount_changes_requested) 'real BOOT 4 collector stops before USB when tools are unavailable'
        } finally { $logZip.Dispose() }
    } finally { Move-Item -LiteralPath $adbHidden -Destination $adbSource }
'''
    test=test.replace(anchor,extra+anchor,1)
    (ROOT/'out/test-ubuntu-handoff.generated.ps1').write_text(test)
    print(json.dumps({'zip_bytes':output.stat().st_size,'sha256':sha(output.read_bytes()),
        'boot_bytes':len(image),'boot_sha256':lock['boot_sha256'],'rollback_sha256':PREVIOUS_SHA256}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path,default=OUT)
    p.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-avvio-Ubuntu-3-Windows.zip')
    a=p.parse_args();package(a.images,a.output)
