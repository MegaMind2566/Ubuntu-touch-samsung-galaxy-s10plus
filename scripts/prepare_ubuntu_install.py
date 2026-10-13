"""Verify and expand the immutable UT system artifact locally. No USB code."""
import argparse
from compression import zstd
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import uuid
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_recovery_test import verify_stock, VerificationError

ARTIFACT_BYTES = 1_167_934_045
ARTIFACT_SHA256 = '8440d83ab7ddffc8d76d1f0894be89cf24b91396b447041a1ffc7e5177695f0d'
BOOT_BYTES = 53_215_232
BOOT_SHA256 = '0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc'
SYSTEM_BYTES = 5_368_709_120
SYSTEM_SHA256 = 'd23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3'
ZSTD_BYTES = 1_114_706_918
ZSTD_SHA256 = '6729e58ca7924a7682a332c4a58a1e1ad1dc3b31437707fb49366b518da99928'


class InstallPreparationError(ValueError):
    pass


def require(condition,code):
    if not condition:
        raise InstallPreparationError(code)


def file_hash(path):
    result=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(8*1024*1024),b''):
            result.update(block)
    return result.hexdigest()


def validate_images(directory):
    for name,size,digest in (('boot.img',BOOT_BYTES,BOOT_SHA256),('system.img',SYSTEM_BYTES,SYSTEM_SHA256)):
        path=directory/name
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==size,'prepared_image_size_mismatch')
        require(file_hash(path)==digest,'prepared_image_sha256_mismatch')
    with (directory/'boot.img').open('rb') as source:
        header=source.read(2048)
    require(header[:8]==b'ANDROID!' and b'systempart=/dev/disk/by-partlabel/system' in header[64:576],'boot_system_partition_mismatch')
    with (directory/'system.img').open('rb') as source:
        header=source.read(4096)
    require(header[1080:1082]==b'\x53\xef','system_not_raw_ext4')
    require(struct.unpack_from('<I',header,1028)[0]*(1024<<struct.unpack_from('<I',header,1048)[0])==SYSTEM_BYTES,'system_geometry_mismatch')


def expand_artifact(path,directory):
    require(path.is_file() and path.stat().st_size==ARTIFACT_BYTES,'source_artifact_size_mismatch')
    print('Verifico il pacchetto immagini scaricato...',flush=True)
    require(file_hash(path)==ARTIFACT_SHA256,'source_artifact_sha256_mismatch')
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist())<=50,'source_archive_member_limit')
        boot_name='system-candidate/boot.img';system_name='system-candidate/rootfs.img.zst'
        require(archive.namelist().count(boot_name)==archive.namelist().count(system_name)==1,'source_archive_members_invalid')
        boot=archive.read(boot_name)
        require(len(boot)==BOOT_BYTES and hashlib.sha256(boot).hexdigest()==BOOT_SHA256,'source_boot_mismatch')
        (directory/'boot.img').write_bytes(boot)
        info=archive.getinfo(system_name)
        require(info.file_size==ZSTD_BYTES,'compressed_system_size_mismatch')
        print('Preparo SYSTEM sul PC: 5 GiB. Attendi la fine.',flush=True)
        size=0;digest=hashlib.sha256();next_update=256*1024*1024
        with archive.open(system_name) as compressed, zstd.ZstdFile(compressed,'rb',options={zstd.DecompressionParameter.window_log_max:26}) as source, (directory/'system.img').open('xb') as output:
            for block in iter(lambda:source.read(8*1024*1024),b''):
                size+=len(block)
                require(size<=SYSTEM_BYTES,'expanded_system_oversized')
                output.write(block);digest.update(block)
                if size>=next_update:
                    print(f'Preparazione SYSTEM: {100*size//SYSTEM_BYTES}%',flush=True)
                    next_update+=256*1024*1024
        require(size==SYSTEM_BYTES and digest.hexdigest()==SYSTEM_SHA256,'expanded_system_sha256_mismatch')
    validate_images(directory)


def verified_state(root):
    state_path=root/'ubuntu-local-state.json'
    require(state_path.is_file() and state_path.stat().st_size<=131072,'prepared_state_missing')
    state=json.loads(state_path.read_text(encoding='utf-8-sig'))
    directory=Path(state['prepared_directory']).resolve()
    require(directory.parent==root.resolve() and directory.name.startswith('prepared-ubuntu-')
            and len(directory.name)==48 and all(c in '0123456789abcdef' for c in directory.name[16:]),'prepared_directory_invalid')
    require(state.get('schema')==1 and state.get('model')=='SM-G975F' and state.get('pda')=='G975FXXSGHWC1'
            and state.get('success') is True and state.get('backup_verified') is True,'prepared_state_unverified')
    validate_images(directory)
    stock=Path(state['stock_firmware_path']).resolve()
    print('Ricontrollo il firmware completo di ripristino...',flush=True)
    verify_stock(stock)
    return {'success':True,'backup_verified':True,'boot_path':str(directory/'boot.img'),
            'system_path':str(directory/'system.img'),'stock_firmware_path':str(stock)}


def prepare(root,artifact,stock):
    root=root.resolve();root.mkdir(parents=True,exist_ok=True)
    (root/'ubuntu-local-state.json').unlink(missing_ok=True)
    directory=root/('prepared-ubuntu-'+uuid.uuid4().hex);directory.mkdir()
    report={'schema':1,'preparer_version':1,'model':'SM-G975F','pda':'G975FXXSGHWC1',
            'handset_accessed':False,'partition_writes':False,'success':False,'backup_verified':False,'error':None}
    try:
        require(shutil.disk_usage(root).free>=SYSTEM_BYTES+BOOT_BYTES+512*1024*1024,'insufficient_pc_disk_space')
        print('Verifico il firmware originale conservato per il ripristino...',flush=True)
        verify_stock(stock);report['backup_verified']=True
        expand_artifact(artifact,directory)
        report.update(success=True,artifact_sha256=ARTIFACT_SHA256,boot_sha256=BOOT_SHA256,
                      system_sha256=SYSTEM_SHA256,boot_bytes=BOOT_BYTES,system_bytes=SYSTEM_BYTES)
        state={**report,'prepared_directory':str(directory),'stock_firmware_path':str(stock.resolve())}
        (root/'ubuntu-local-state.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    except Exception as error:
        report['error']=str(error) if isinstance(error,(InstallPreparationError,VerificationError)) else 'preparation_failed'
        for name in ('boot.img','system.img'):(directory/name).unlink(missing_ok=True)
    (directory/'ubuntu-preparation-report.json').write_text(json.dumps(report,indent=2)+'\n')
    path=root/'ubuntu-preparation-report.zip';index=1
    while path.exists():path=root/f'ubuntu-preparation-report-{index}.zip';index+=1
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.write(directory/'ubuntu-preparation-report.json','ubuntu-preparation-report.json')
    print('File pronti. Puoi aprire INSTALLA-UBUNTU-TOUCH.cmd.' if report['success'] else f'Preparazione fermata. Invia {path.name}.',flush=True)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--artifact',type=Path)
    parser.add_argument('--stock-firmware',type=Path)
    parser.add_argument('--verify-output',type=Path)
    args=parser.parse_args()
    if args.verify_output:
        args.verify_output.unlink(missing_ok=True)
        try:result=verified_state(args.root.resolve())
        except Exception as error:result={'success':False,'error':str(error) if isinstance(error,InstallPreparationError) else 'image_or_backup_verification_failed'}
        args.verify_output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        return 0 if result['success'] else 1
    require(args.artifact is not None and args.stock_firmware is not None,'source_and_stock_required')
    return 0 if prepare(args.root,args.artifact,args.stock_firmware)['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
