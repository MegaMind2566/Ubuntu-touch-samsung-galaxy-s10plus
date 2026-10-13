"""Render the measured BOOT-only installer for a temporary diagnostic and BOOT 2 restore."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from prepare_boot_diagnostic import entries, elf_static_arm64, PREVIOUS_SHA256, PREVIOUS_BYTES, ORIGINAL_RAM_SHA256
from inspect_stock_firmware import boot_header

ROOT=Path(__file__).resolve().parents[1]


def render(text,lock):
    text=text.replace('__BOOT_UPDATE_SHA256__',lock['boot_sha256']).replace('__BOOT_UPDATE_BYTES__',str(lock['boot_bytes']))
    if '__BOOT_UPDATE_' in text: raise ValueError('unrendered_template')
    return text


def identity(text):
    # Map the reviewed installer's separate predecessor/update paths without collision.
    return (text.replace('boot-update-1','boot-rollback-2').replace('boot-update-2','boot-diagnostic-1')
            .replace('verify_boot_update_2.py','verify_boot_diagnostic.py')
            .replace('BOOT handoff with spaces','BOOT diagnostic with spaces')
            .replace('INSTALLA-CORREZIONE-AVVIO.cmd','INSTALLA-TEST-AVVIO.cmd')
            .replace('RIPRISTINA-BOOT-1.cmd','RIPRISTINA-BOOT-2.cmd'))


def validate(folder):
    previous=(folder/'previous-boot-2.img').read_bytes();image=(folder/'diagnostic-boot.img').read_bytes()
    lock=json.loads((folder/'boot-diagnostic.lock.json').read_text())
    if len(previous)!=PREVIOUS_BYTES or hashlib.sha256(previous).hexdigest()!=PREVIOUS_SHA256:
        raise ValueError('rollback_boot_2_mismatch')
    if (hashlib.sha256(image).hexdigest()!=lock['boot_sha256'] or len(image)!=lock['boot_bytes'] or
            len(image)>57671680 or lock['diagnostic_version']!=1 or
            not lock['kernel_byte_identical_to_boot_2'] or lock['hardware_tested']):
        raise ValueError('diagnostic_image_lock')
    before=boot_header(previous);after=boot_header(image)
    k1=previous[before['page_bytes']:before['page_bytes']+before['kernel_bytes']]
    k2=image[after['page_bytes']:after['page_bytes']+after['kernel_bytes']]
    if k1!=k2 or hashlib.sha256(k2).hexdigest()!=lock['kernel_sha256']: raise ValueError('kernel_changed')
    header_changes={i for i,(a,b) in enumerate(zip(previous[:2048],image[:2048])) if a!=b}
    if header_changes-set(range(16,20))-set(range(576,608)): raise ValueError('header_changed')
    r1=previous[before['ramdisk_offset']:before['ramdisk_offset']+before['ramdisk_bytes']]
    r2=image[after['ramdisk_offset']:after['ramdisk_offset']+after['ramdisk_bytes']]
    if hashlib.sha256(r1).hexdigest()!=ORIGINAL_RAM_SHA256 or hashlib.sha256(r2).hexdigest()!=lock['ramdisk_sha256']:
        raise ValueError('ramdisk_digest')
    a={e['name']:e for e in entries(gzip.decompress(r1))};b={e['name']:e for e in entries(gzip.decompress(r2))}
    if set(b)!=set(a)|{'ut-diag-display','ut-diag-original-init'}: raise ValueError('ramdisk_paths')
    for name,old in a.items():
        expect=list(old['values'])
        if name=='init': expect[6]=len(b[name]['data'])
        if expect!=b[name]['values'] or (name!='init' and old['data']!=b[name]['data']):
            raise ValueError('unrelated_ramdisk_entry_changed')
    expected_init=(ROOT/'tools/boot-diagnostic/init').read_text(encoding='ascii').encode('ascii')
    if (b['init']['data']!=expected_init or
            b['ut-diag-original-init']['data']!=a['init']['data'] or
            hashlib.sha256(b['ut-diag-display']['data']).hexdigest()!=lock['display_helper_sha256']):
        raise ValueError('diagnostic_payload')
    elf_static_arm64(b['ut-diag-display']['data'])
    return image,previous,lock


def package(folder,output):
    image,previous,lock=validate(folder)
    script=identity((ROOT/'scripts/install-boot-update-2.ps1.in').read_text())
    script=script.replace("$script:BootPreviousHash='d3be319ae9353908e917894d624460e743bfc078d676c592189d415ef02b0993'",
                          "$script:BootPreviousHash='"+PREVIOUS_SHA256+"'")
    script=script.replace('schema=1;update_version=2;','schema=1;update_version=3;diagnostic_version=1;purpose="controlled_boot_diagnostic";')
    footer="""        Write-Host 'AGGIORNAMENTO BOOT COMPLETATO E VERIFICATO.'
        Write-Host 'Ora in TWRP: Reboot > System. Se propone l app TWRP, scegli Do Not Install.'
        Write-Host 'Invia il rapporto e la schermata ottenuta al primo avvio.'"""
    if footer not in script: raise ValueError('mode_footer_anchor')
    script=script.replace(footer,"""        if ($UpdateMode -ceq 'Apply') {
            Write-Host 'BOOT DEL TEST COMPLETATO E VERIFICATO.'
            Write-Host 'Ora in TWRP: Reboot > System. Se propone l app TWRP, scegli Do Not Install.'
            Write-Host 'Attendi 60 secondi, fotografa la schermata, torna in TWRP e usa LEGGI-TEST-AVVIO.cmd.'
        } else {
            Write-Host 'BOOT 2 PRECEDENTE RIPRISTINATO E VERIFICATO.'
            Write-Host 'Il test diagnostico non e piu in BOOT. I suoi log restano disponibili da TWRP.'
            Write-Host 'Invia il rapporto di ripristino; nessun riavvio e stato eseguito.'
        }""",1)
    verifier=(ROOT/'scripts/verify_boot_update_2.py.in').read_text()
    verifier=verifier.replace(ORIGINAL_RAM_SHA256,lock['ramdisk_sha256']).replace('rsize!=4108120','rsize!='+str(lock['ramdisk_bytes']))
    verifier=verifier.replace('BOOT corretto verificato. Ramdisk e selettore di SYSTEM conservati.',
                              'BOOT diagnostico verificato. Il kernel e identico al BOOT 2; ramdisk del test temporaneo.')
    members={'boot-diagnostic-1/boot.img':image,'boot-rollback-2/boot.img':previous,
             'config/boot-diagnostic-1.lock.json':json.dumps(lock,indent=2).encode(),
             'scripts/install-boot-diagnostic-1.ps1':render(script,lock).encode('ascii'),
             'scripts/verify_boot_diagnostic.py':render(verifier,lock).encode('ascii'),
             'scripts/collect-boot-diagnostic.py':render((ROOT/'scripts/collect-boot-diagnostic.py').read_text(),lock).encode('ascii'),
             'boot-diagnostic-1/diagnostic-tests.json':(folder/'diagnostic-tests.json').read_bytes()}
    for name in ['install-ubuntu-twrp.ps1','install-ubuntu-touch.ps1','check-recovery.ps1','flash-recovery-test.ps1',
                 'check-download-mode.ps1','prepare_ubuntu_install.py','verify_recovery_test.py','collect-first-boot.py']:
        members['scripts/'+name]=(ROOT/'scripts'/name).read_bytes()
    for name in ['INSTALLA-TEST-AVVIO.cmd','RIPRISTINA-BOOT-2.cmd','LEGGI-TEST-AVVIO.cmd','LEGGIMI-TEST-AVVIO.txt']:
        members[name]=(ROOT/'tools/windows'/name).read_bytes()
    for name,data in list(members.items()):
        if name.endswith(('.ps1','.cmd','.txt')):
            members[name]=data.decode('ascii').replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
    members['SHA256SUMS']=(''.join(hashlib.sha256(v).hexdigest()+'  '+n+'\n' for n,v in sorted(members.items()))).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(members.items()): z.writestr(name,data)
    # Run the reviewed Windows safety fixtures against these actual generated paths/pins.
    test=identity((ROOT/'tests/test-boot-update-2.ps1').read_text())
    test=test.replace("ubuntu-boot-update-apply-state.json","ubuntu-boot-update-2-apply-state.json")
    test=test.replace('version 1 checkpoint preserved and does not block version 2','BOOT 2 checkpoint preserved and does not block this diagnostic')
    test=test.replace('version 1 cannot be mistaken for version 2','BOOT 2 cannot be mistaken for the diagnostic')
    test=test.replace('version 2 update/restore cases','diagnostic update/restore cases')
    test=test.replace('version 1/version 2 BOOT','BOOT 2/diagnostic BOOT')
    test=test.replace('param([string]$Cmd)','param([string]$Cmd,[string]$Expected="previous_boot_update_needs_review")')
    test=test.replace("$output -match 'previous_boot_update_needs_review'","$output -match $Expected")
    anchor="    Write-Host 'PASS: 24"
    if anchor not in test: raise ValueError('native_collector_test_anchor')
    extra=r'''    # Third real CMD uses embedded Python and the real collector; missing ADB
    # must stop before USB and preserve an actionable read-only report.
    $adbSource=Join-Path $script:BootTestRoot 'platform-tools\adb.exe'
    $adbHidden=Join-Path $script:BootTestRoot 'platform-tools\adb-test-hidden.exe'
    Move-Item -LiteralPath $adbSource -Destination $adbHidden
    try {
        Invoke-BootNativeEntry 'LEGGI-TEST-AVVIO.cmd' 'Lettura fermata: local_tools_unavailable'
        $logZip=[IO.Compression.ZipFile]::OpenRead((Join-Path $script:BootTestRoot 'ubuntu-boot-diagnostic-log-report.zip'))
        try {
            $reader=New-Object IO.StreamReader($logZip.GetEntry('diagnostic-log-report.json').Open())
            try { $logReport=$reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            Assert-BootTest ($logReport.error -ceq 'local_tools_unavailable' -and $logReport.steps.Count -eq 0 -and
                -not $logReport.partition_writes -and -not $logReport.mount_changes_requested) 'real collector CMD stops before USB when tools are unavailable'
        } finally { $logZip.Dispose() }
    } finally { Move-Item -LiteralPath $adbHidden -Destination $adbSource }
'''
    test=test.replace(anchor,extra+anchor,1)
    (ROOT/'tests/test-boot-diagnostic.generated.ps1').write_text(test)
    print(json.dumps({'zip_bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                      'boot_bytes':len(image),'boot_sha256':lock['boot_sha256'],'rollback_boot_sha256':PREVIOUS_SHA256}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',type=Path,default=ROOT/'out/boot-diagnostic-images')
    p.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-test-AVVIO-Windows.zip')
    a=p.parse_args();package(a.images,a.output)
