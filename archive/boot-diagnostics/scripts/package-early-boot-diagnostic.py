"""Package diagnostic 2, its exact diagnostic 1 rollback and read-only collector."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from early_boot_diagnostic import (ROOT,OUT,PREVIOUS_SHA256,PREVIOUS_BYTES,sha,
    compose,image_kernel,kernel_config,config_values,minimal_initramfs)


def render(text,lock):
    text=text.replace('__BOOT_UPDATE_SHA256__',lock['boot_sha256']).replace('__BOOT_UPDATE_BYTES__',str(lock['boot_bytes']))
    if '__BOOT_UPDATE_' in text:raise ValueError('unrendered_template')
    return text


def identity(text):
    return (text.replace('boot-update-1','boot-diagnostic-1').replace('boot-update-2','boot-diagnostic-2')
        .replace('verify_boot_update_2.py','verify_early_boot_diagnostic.py')
        .replace('BOOT handoff with spaces','BOOT early diagnostic with spaces')
        .replace('INSTALLA-CORREZIONE-AVVIO.cmd','INSTALLA-TEST-AVVIO-2.cmd')
        .replace('RIPRISTINA-BOOT-1.cmd','RIPRISTINA-TEST-AVVIO-1.cmd'))


def validate(folder):
    previous=(folder/'previous-diagnostic-1.img').read_bytes();image=(folder/'diagnostic-boot.img').read_bytes()
    lock=json.loads((folder/'early-boot-diagnostic.lock.json').read_text())
    payload=(folder/'initramfs.cpio').read_bytes()
    if (sha(previous)!=PREVIOUS_SHA256 or len(previous)!=PREVIOUS_BYTES or
            lock['diagnostic_version']!=2 or lock['hardware_tested'] or lock['ubuntu_touch_boot_verified']
            or sha(image)!=lock['boot_sha256'] or len(image)!=lock['boot_bytes']):raise ValueError('early_image_identity')
    if payload!=minimal_initramfs(previous) or sha(payload)!=lock['builtin_initramfs_sha256']:
        raise ValueError('builtin_payload_changed')
    rebuilt,differences=compose(previous,image,payload)
    if (rebuilt!=image or differences!=lock['kernel_config_differences']
            or sha(image_kernel(image))!=lock['kernel_sha256']
            or config_values((folder/'kernel.config').read_text())!=config_values(kernel_config(image_kernel(image)))):
        raise ValueError('early_image_structure')
    return image,previous,lock


def collector(lock):
    text=(ROOT/'scripts/collect-boot-diagnostic.py').read_text()
    for old,new in [("'diagnostic_version':1","'diagnostic_version':2"),
                    ('ubuntu-touch-boot-diagnostic-1','ubuntu-touch-boot-diagnostic-2'),
                    ('UT_DIAG_1','UT_DIAG_2'),
                    ('ubuntu-boot-diagnostic-log-report','ubuntu-boot-diagnostic-2-log-report')]:
        if old not in text:raise ValueError('collector_template_anchor')
        text=text.replace(old,new)
    return render(text,lock)


def package(folder,output):
    image,previous,lock=validate(folder)
    script=identity((ROOT/'scripts/templates/verified-boot-install.ps1.in').read_text())
    script=script.replace("$script:BootPreviousHash='d3be319ae9353908e917894d624460e743bfc078d676c592189d415ef02b0993'",
                          "$script:BootPreviousHash='"+PREVIOUS_SHA256+"'")
    script=script.replace('$script:BootPreviousBytes=53215232','$script:BootPreviousBytes='+str(PREVIOUS_BYTES))
    script=script.replace('schema=1;update_version=2;','schema=1;update_version=4;diagnostic_version=2;purpose="builtin_initramfs_diagnostic";')
    footer="""        Write-Host 'AGGIORNAMENTO BOOT COMPLETATO E VERIFICATO.'
        Write-Host 'Ora in TWRP: Reboot > System. Se propone l app TWRP, scegli Do Not Install.'
        Write-Host 'Invia il rapporto e la schermata ottenuta al primo avvio.'"""
    if footer not in script:raise ValueError('mode_footer_anchor')
    script=script.replace(footer,"""        if ($UpdateMode -ceq 'Apply') {
            Write-Host 'TEST 2 INSTALLATO E VERIFICATO.'
            Write-Host 'Ora TWRP > Reboot > System. Se propone l app TWRP, scegli Do Not Install.'
            Write-Host 'Attendi 60 secondi, fotografa la schermata, torna in TWRP e usa LEGGI-TEST-AVVIO-2.cmd.'
        } else {
            Write-Host 'BOOT DEL TEST 1 RIPRISTINATO E VERIFICATO.'
            Write-Host 'Il telefono resta in TWRP. Invia il rapporto di ripristino.'
        }""",1)
    verifier=(ROOT/'scripts/templates/verified-boot-image.py.in').read_text()
    verifier=verifier.replace('439b535193a8e6315e3da3884755db49b04794c28d5e06686fc595dfab8f5a4c',lock['ramdisk_sha256'])
    verifier=verifier.replace('rsize!=4108120','rsize!='+str(lock['ramdisk_bytes']))
    verifier=verifier.replace('BOOT corretto verificato. Ramdisk e selettore di SYSTEM conservati.',
                              'BOOT del test 2 verificato. Diagnostica integrata nel kernel; ramdisk esterno conservato.')
    members={'boot-diagnostic-2/boot.img':image,'boot-diagnostic-1/boot.img':previous,
        'config/early-boot-diagnostic.lock.json':json.dumps(lock,indent=2).encode(),
        'scripts/install-boot-diagnostic-2.ps1':render(script,lock).encode('ascii'),
        'scripts/verify_early_boot_diagnostic.py':render(verifier,lock).encode('ascii'),
        'scripts/collect-boot-diagnostic-2.py':collector(lock).encode('ascii'),
        'boot-diagnostic-2/early-diagnostic-tests.json':(folder/'early-diagnostic-tests.json').read_bytes()}
    for name in ['install-ubuntu-twrp.ps1','install-ubuntu-touch.ps1','check-recovery.ps1','flash-recovery-test.ps1',
                 'check-download-mode.ps1','prepare_ubuntu_install.py','verify_recovery_test.py','collect-first-boot.py']:
        members['scripts/'+name]=(ROOT/'scripts'/name).read_bytes()
    for name in ['INSTALLA-TEST-AVVIO-2.cmd','LEGGI-TEST-AVVIO-2.cmd','RIPRISTINA-TEST-AVVIO-1.cmd','LEGGIMI-TEST-AVVIO-2.txt']:
        members[name]=(ROOT/'tools/windows'/name).read_bytes()
    for name,value in list(members.items()):
        if name.endswith(('.ps1','.cmd','.txt')):members[name]=value.decode('ascii').replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
    members['SHA256SUMS']=''.join(sha(v)+'  '+n+'\n' for n,v in sorted(members.items())).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,value in sorted(members.items()):z.writestr(name,value)
    test=identity((ROOT/'tests/test-boot-template.ps1').read_text())
    test=test.replace('ubuntu-boot-update-apply-state.json','ubuntu-boot-diagnostic-1-apply-state.json')
    test=test.replace('version 1 checkpoint preserved and does not block version 2','diagnostic 1 checkpoint preserved and does not block diagnostic 2')
    test=test.replace('version 1 cannot be mistaken for version 2','diagnostic 1 cannot be mistaken for diagnostic 2')
    test=test.replace('version 2 update/restore cases','early diagnostic update/restore cases')
    test=test.replace('version 1/version 2 BOOT','diagnostic 1/diagnostic 2 BOOT')
    test=test.replace('param([string]$Cmd)','param([string]$Cmd,[string]$Expected="previous_boot_update_needs_review")')
    test=test.replace("$output -match 'previous_boot_update_needs_review'","$output -match $Expected")
    anchor="    Write-Host 'PASS: 24"
    if anchor not in test:raise ValueError('native_collector_test_anchor')
    extra=r'''    $adbSource=Join-Path $script:BootTestRoot 'platform-tools\adb.exe'
    $adbHidden=Join-Path $script:BootTestRoot 'platform-tools\adb-test-hidden.exe'
    Move-Item -LiteralPath $adbSource -Destination $adbHidden
    try {
        Invoke-BootNativeEntry 'LEGGI-TEST-AVVIO-2.cmd' 'Lettura fermata: local_tools_unavailable'
        $logZip=[IO.Compression.ZipFile]::OpenRead((Join-Path $script:BootTestRoot 'ubuntu-boot-diagnostic-2-log-report.zip'))
        try {
            $reader=New-Object IO.StreamReader($logZip.GetEntry('diagnostic-log-report.json').Open())
            try { $logReport=$reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            Assert-BootTest ($logReport.diagnostic_version -eq 2 -and $logReport.error -ceq 'local_tools_unavailable' -and
                $logReport.steps.Count -eq 0 -and -not $logReport.partition_writes -and -not $logReport.mount_changes_requested) 'real test 2 collector stops before USB when tools are unavailable'
        } finally { $logZip.Dispose() }
    } finally { Move-Item -LiteralPath $adbHidden -Destination $adbSource }
'''
    test=test.replace(anchor,extra+anchor,1)
    (ROOT/'out/test-early-boot.generated.ps1').write_text(test)
    print(json.dumps({'zip_bytes':output.stat().st_size,'sha256':sha(output.read_bytes()),
                      'boot_bytes':len(image),'boot_sha256':lock['boot_sha256'],'rollback_sha256':PREVIOUS_SHA256}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path,default=OUT)
    p.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-test-AVVIO-2-Windows.zip')
    a=p.parse_args();package(a.images,a.output)
