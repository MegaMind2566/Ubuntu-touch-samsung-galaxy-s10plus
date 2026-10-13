"""Fetch public, pinned upstream boot source for offline review; never execute it."""
import base64
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

KERNEL='ubports/porting/community-ports/android10/samsung-galaxy-s10/kernel-samsung-exynos9820'
KERNEL_COMMIT='b9b70b29c94c41365704fcc2ed33be09b4617907'
PORT='ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820'
PORT_COMMIT='06facc6fbc9cfda5f57428a6d7eeb805f5dedb89'
OUTPUT=Path('out/kernel-boot-source-audit')


def fetch(project, commit, path):
    url=('https://gitlab.com/api/v4/projects/'+urllib.parse.quote(project,safe='')+
         '/repository/files/'+urllib.parse.quote(path,safe='')+'?ref='+commit)
    with urllib.request.urlopen(url,timeout=45) as response:
        document=json.loads(response.read(2*1024*1024))
    if document['encoding']!='base64' or document['ref']!=commit:
        raise ValueError('source_ref_mismatch')
    data=base64.b64decode(document['content'],validate=False)
    if len(data)>1024*1024 or len(data)!=document['size']:
        raise ValueError('source_size_mismatch')
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if blob!=document['blob_id']:
        raise ValueError('source_blob_mismatch')
    target=OUTPUT/('kernel' if project==KERNEL else 'port')/path
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return {'project':project,'commit':commit,'path':path,'bytes':len(data),
            'git_blob_sha1':blob,'sha256':hashlib.sha256(data).hexdigest()}


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    manifest={'schema':1,'public_sources_only':True,'upstream_code_executed':False,'files':[]}
    paths=['COPYING','init/Makefile','init/Kconfig','init/initramfs.c','init/do_mounts.c',
           'init/do_mounts_initrd.c','init/main.c','include/linux/initrd.h',
           'arch/arm64/configs/exynos9820-beyond2lte_defconfig']
    for path in paths:
        manifest['files'].append(fetch(KERNEL,KERNEL_COMMIT,path))
    manifest['files'].append(fetch(PORT,PORT_COMMIT,'deviceinfo-beyond2lte'))
    makefile=(OUTPUT/'kernel/init/Makefile').read_text()
    for line in makefile.splitlines():
        if 'ANDROID_SAR_RAMDISK' in line:
            for object_name in re.findall(r'\b([a-zA-Z0-9_]+)\.o\b',line):
                path='init/'+object_name+'.c'
                if path not in paths:
                    manifest['files'].append(fetch(KERNEL,KERNEL_COMMIT,path));paths.append(path)
    (OUTPUT/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
    for file in manifest['files']:
        if file['path']=='COPYING':continue
        target=OUTPUT/('kernel' if file['project']==KERNEL else 'port')/file['path']
        lines=target.read_text().splitlines()
        patterns=re.compile(r'ANDROID_SAR|ANDROID_BOOT_PARTITION|sar_ramdisk|android_sar|read_boot|boot_partition|populate_rootfs|bootimg|BOOT_IMG|androidboot|kernel_cmdline|deviceinfo_',re.I)
        indices={j for i,line in enumerate(lines) if patterns.search(line) for j in range(max(0,i-8),min(len(lines),i+20))}
        # Full SAR implementation is small and is the object of this audit.
        if 'sar' in file['path'].lower():indices=set(range(min(len(lines),600)))
        print('\nSOURCE '+file['path'])
        for index in sorted(indices):print(str(index+1)+': '+lines[index])


if __name__=='__main__':main()
