"""Package pinned Windows tools, without firmware or handset images."""
import argparse
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES={
    'python':('https://www.python.org/ftp/python/3.14.4/python-3.14.4-embed-amd64.zip',12034740,
              'cda80a9b1e75c0f1b4f9872ca1b417f0d19bce32facc811aea9180e70fad5fb9'),
    'adb':('https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip',20000000,
           '45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99'),
    'samloader':('https://github.com/topjohnwu/samloader-rs/releases/download/2.2.0/samloader-v2.2.0-windows-x86_64.zip',1418327,
                 '0132de1b79e208138f980c467f9a7eaa2ffcb72aae14afc3ed13799803c9b9ed'),
}


def dependency(name,path):
    url,limit,digest=DEPENDENCIES[name]
    if path:content=path.read_bytes()
    else:
        with urllib.request.urlopen(url,timeout=60) as source:content=source.read(limit+1)
    if len(content)>limit or (name!='adb' and len(content)!=limit) or hashlib.sha256(content).hexdigest()!=digest:
        raise ValueError('Publisher dependency mismatch: '+name)
    return zipfile.ZipFile(io.BytesIO(content))


def main():
    parser=argparse.ArgumentParser()
    for name in DEPENDENCIES:parser.add_argument('--'+name+'-archive',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-installa-Ubuntu-Windows.zip')
    args=parser.parse_args();members={}
    with dependency('python',args.python_archive) as archive:
        if len(archive.namelist())!=len(set(archive.namelist())):raise ValueError('Duplicate runtime member')
        for name in archive.namelist():
            if '/' in name or '\\' in name or name in ('.','..'):raise ValueError('Unexpected runtime path')
            members['tools/python/'+name]=archive.read(name)
        if '_zstd.pyd' not in archive.namelist():raise ValueError('Zstd runtime missing')
    with dependency('adb',args.adb_archive) as archive:
        for name in ('adb.exe','AdbWinApi.dll','AdbWinUsbApi.dll','libwinpthread-1.dll','NOTICE.txt','source.properties'):
            members['platform-tools/'+name]=archive.read('platform-tools/'+name)
    with dependency('samloader',args.samloader_archive) as archive:
        if archive.namelist()!=['samloader.exe']:raise ValueError('Unexpected samloader members')
        members['tools/samloader/samloader.exe']=archive.read('samloader.exe')
    for path in ('prepare_ubuntu_install.py','prepare-ubuntu-install.ps1','install-ubuntu-touch.ps1',
                 'verify_recovery_test.py','check-recovery.ps1','check-download-mode.ps1','flash-recovery-test.ps1','install-ubuntu-twrp.ps1'):
        members['scripts/'+path]=(ROOT/'scripts'/path).read_bytes()
    for name in ('PREPARA-UBUNTU-TOUCH.cmd','INSTALLA-UBUNTU-TOUCH.cmd','LEGGIMI-INSTALLAZIONE-UBUNTU.txt','INSTALLA-UBUNTU-TWRP.cmd','LEGGIMI-UBUNTU-TWRP.txt'):
        members[name]=(ROOT/'tools/windows'/name).read_bytes()
    for name in ('samloader-LICENSE-APACHE.txt','samloader-LICENSE-MIT.txt'):
        members['licenses/'+name]=(ROOT/'tools/windows/licenses'/name).read_bytes()
    members['config/install-images.lock.json']=(ROOT/'config/install-images.lock.json').read_bytes()
    for name,data in list(members.items()):
        if name.endswith(('.ps1','.cmd','.txt')) and not name.startswith(('tools/python/','platform-tools/')):
            text=data.decode('ascii');members[name]=text.replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
    members['SHA256SUMS']=(''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(members.items()))).encode('ascii')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(members.items()):archive.writestr(name,data)
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__=='__main__':main()
