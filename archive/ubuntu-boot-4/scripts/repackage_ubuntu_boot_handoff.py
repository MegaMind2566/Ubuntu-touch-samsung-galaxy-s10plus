"""Revalidate an immutable successful BOOT 4 image job without recompiling it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from early_boot_diagnostic import ROOT,sha,extract_zip,INITRAMFS_SOURCE_SHA256,DIAGNOSTIC_PATCH
from github_artifacts import obtain_job
from ubuntu_boot_handoff import OUT

SOURCE_RUN=38756613455
SOURCE_COMMIT='3b673e3d2b5cf520961ea7cb6b4dc03d1a36190f'
SOURCE_ARTIFACT=11985068265
SOURCE_ZIP_SHA256='f6218c175747df6114c94644fae27f32ee63c68c6e8b7aca87f8073b3ab738a7'


def inputs():
    if not SOURCE_ARTIFACT:raise ValueError('source_artifact_not_pinned')
    ref=obtain_job(SOURCE_RUN,SOURCE_COMMIT,'validated-ubuntu-handoff-source.zip',
        'beyond2lte-ubuntu-boot-handoff-images','images',os.environ['UT_ARTIFACT_TOKEN'],SOURCE_ARTIFACT)
    if ref['sha256']!=SOURCE_ZIP_SHA256:raise ValueError('validated_source_artifact_pin')
    extract_zip(ROOT/'out/validated-ubuntu-handoff-source.zip',OUT,['boot.img','previous-ubuntu-3.img',
        'initramfs.cpio','kernel.config','ubuntu-boot-source.json','ubuntu-boot-handoff.lock.json','ubuntu-handoff-tests.json'])
    (ROOT/'out/ubuntu-handoff-source-reference.json').write_text(json.dumps(ref,indent=2)+'\n')


def force_source():
    source=ROOT/'out/kernel-boot-source-audit/kernel/init/initramfs.c'
    if sha(source.read_bytes())!=INITRAMFS_SOURCE_SHA256:raise ValueError('audited_source_pin')
    folder=ROOT/'build/ubuntu-handoff/workdir/downloads/kernel-samsung-exynos9820'
    target=folder/'init/initramfs.c';target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    directory=str(folder.relative_to(ROOT))
    subprocess.run(['git','apply','--check','--directory='+directory,str(DIAGNOSTIC_PATCH)],cwd=ROOT,check=True)
    subprocess.run(['git','apply','--directory='+directory,str(DIAGNOSTIC_PATCH)],cwd=ROOT,check=True)
    expected=json.loads((OUT/'ubuntu-boot-source.json').read_text())['patched_initramfs_source_sha256']
    if sha(target.read_bytes())!=expected:raise ValueError('compiled_source_mismatch')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['inputs','force-source'])
    if p.parse_args().phase=='inputs':inputs()
    else:force_source()
