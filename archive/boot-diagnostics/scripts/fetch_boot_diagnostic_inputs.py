"""Obtain the pinned BOOT 2 or this workflow's successfully tested images."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from github_artifacts import obtain
from github_artifacts import api, NoRedirect


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['previous','images'])
    a=p.parse_args();token=os.environ['UT_ARTIFACT_TOKEN'];Path('out').mkdir(exist_ok=True)
    if a.mode=='previous':
        ref=obtain(38452662502,'6b46ada66199005fa7df03c8d4a42f3a6d9c510c',
                   'diagnostic-previous-adaptation.zip',11843035830,token)
        if ref['sha256']!='00974b1d2b48523a8b0bbf23c6eb22db1f8f2165150adc064196018e6e1f28fd':
            raise ValueError('previous_artifact_pin')
        Path('out/diagnostic-previous-artifact.json').write_text(json.dumps(ref,indent=2)+'\n')
        return
    run_id=int(os.environ['GITHUB_RUN_ID']);commit=os.environ['GITHUB_SHA']
    run=api('actions/runs/'+str(run_id),token)
    if run['head_sha']!=commit or run['head_branch']!='main': raise ValueError('workflow_identity')
    jobs=api('actions/runs/'+str(run_id)+'/jobs',token)['jobs']
    if not any(j['name']=='images' and j['conclusion']=='success' for j in jobs):
        raise ValueError('diagnostic_image_tests_not_successful')
    matches=[v for v in api('actions/runs/'+str(run_id)+'/artifacts',token)['artifacts']
             if v['name']=='beyond2lte-boot-diagnostic-images' and not v['expired']]
    if len(matches)!=1: raise ValueError('diagnostic_artifact_count')
    artifact=matches[0]
    if not 0<artifact['size_in_bytes']<=128*1024*1024: raise ValueError('artifact_size')
    req=urllib.request.Request(artifact['archive_download_url'],headers={'Authorization':'Bearer '+token})
    try:
        urllib.request.build_opener(NoRedirect()).open(req,timeout=45)
        raise ValueError('artifact_redirect_missing')
    except urllib.error.HTTPError as e:
        if e.code!=302: raise
        url=e.headers['Location']
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname.endswith('.blob.core.windows.net'):
        raise ValueError('unexpected_artifact_storage')
    target=Path('out/boot-diagnostic-images.zip');size=0;digest=hashlib.sha256()
    with urllib.request.urlopen(url,timeout=60) as src,target.open('xb') as dst:
        while chunk:=src.read(1024*1024):
            size+=len(chunk)
            if size>artifact['size_in_bytes']: raise ValueError('artifact_oversized')
            digest.update(chunk);dst.write(chunk)
    if size!=artifact['size_in_bytes'] or 'sha256:'+digest.hexdigest()!=artifact['digest']:
        raise ValueError('artifact_digest')
    expected={'diagnostic-boot.img','previous-boot-2.img','boot-diagnostic.lock.json','diagnostic-tests.json'}
    folder=Path('out/boot-diagnostic-images');folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(target) as z:
        if set(z.namelist())!=expected or z.testzip() is not None: raise ValueError('diagnostic_archive_shape')
        for name in expected: (folder/name).write_bytes(z.read(name))
    Path('out/boot-diagnostic-artifact-reference.json').write_text(json.dumps({
        'run':run_id,'commit':commit,'artifact_id':artifact['id'],
        'zip_bytes':size,'sha256':digest.hexdigest()},indent=2)+'\n')
    print('Verified successfully tested diagnostic image artifact from this workflow.')


if __name__=='__main__': main()
