"""Revalidate an immutable successful BOOT 3 image job without recompiling it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from early_boot_diagnostic import ROOT,sha,extract_zip,INITRAMFS_SOURCE_SHA256,DIAGNOSTIC_PATCH
from github_artifacts import obtain_job
from ubuntu_boot_handoff import OUT

SOURCE_RUN=38747176508
SOURCE_COMMIT='8e92d215fd271cff08fc0f9229a242eb26150c76'
SOURCE_ARTIFACT=11980905738
SOURCE_ZIP_SHA256='8646a283e946ee31396f32dd4fcc5b633a5342cd05ff8321d7cf47f57f55c08e'


def inputs():
    if not SOURCE_ARTIFACT:raise ValueError('source_artifact_not_pinned')
    ref=obtain_job(SOURCE_RUN,SOURCE_COMMIT,'validated-ubuntu-handoff-source.zip',
        'beyond2lte-ubuntu-boot-handoff-images','images',os.environ['UT_ARTIFACT_TOKEN'],SOURCE_ARTIFACT)
    if ref['sha256']!=SOURCE_ZIP_SHA256:raise ValueError('validated_source_artifact_pin')
    extract_zip(ROOT/'out/validated-ubuntu-handoff-source.zip',OUT,['boot.img','previous-diagnostic-2.img',
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
