"""Fetch only the reviewed handoff build and its pinned version 1 rollback."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from fetch_boot_update_artifact import api, NoRedirect

BUILDS=[
    (38452662502,'6b46ada66199005fa7df03c8d4a42f3a6d9c510c','corrected-adaptation-2.zip',None),
    (38439532393,'a6390494079bdaa8fb479644fa902835dafddee2','previous-adaptation.zip',11835412882),
]


def obtain(run_id,commit,filename,artifact_id,token):
    deadline=time.monotonic()+5400
    while True:
        run=api('actions/runs/'+str(run_id),token)
        if run['head_sha']!=commit or run['head_branch']!='main':raise ValueError('build_identity_mismatch')
        if run['status']=='completed':break
        if time.monotonic()>=deadline:raise ValueError('build_wait_expired')
        time.sleep(20)
    if run['conclusion']!='success':raise ValueError('build_failed')
    candidates=[a for a in api('actions/runs/'+str(run_id)+'/artifacts',token)['artifacts']
                if a['name'].startswith('beyond2lte-halium12-') and not a['expired']]
    if len(candidates)!=1:raise ValueError('artifact_count')
    artifact=candidates[0]
    if artifact_id is not None and artifact['id']!=artifact_id:raise ValueError('rollback_artifact_changed')
    if not 0<artifact['size_in_bytes']<=128*1024*1024:raise ValueError('artifact_size')
    request=urllib.request.Request(artifact['archive_download_url'],headers={'Authorization':'Bearer '+token})
    try:
        urllib.request.build_opener(NoRedirect()).open(request,timeout=45)
        raise ValueError('artifact_redirect_missing')
    except urllib.error.HTTPError as error:
        if error.code!=302:raise
        url=error.headers['Location']
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname.endswith('.blob.core.windows.net'):raise ValueError('unexpected_storage')
    target=Path('out')/filename;target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256();size=0
    with urllib.request.urlopen(url,timeout=60) as source,target.open('xb') as output:
        while chunk:=source.read(1024*1024):
            size+=len(chunk)
            if size>artifact['size_in_bytes']:raise ValueError('artifact_oversized')
            digest.update(chunk);output.write(chunk)
    if size!=artifact['size_in_bytes'] or 'sha256:'+digest.hexdigest()!=artifact['digest']:raise ValueError('artifact_digest')
    return {'run':run_id,'commit':commit,'artifact_id':artifact['id'],'filename':filename,'zip_bytes':size,'sha256':digest.hexdigest()}


if __name__=='__main__':
    token=os.environ['UT_ARTIFACT_TOKEN'];references=[obtain(*build,token) for build in BUILDS]
    Path('out/boot-update-2-artifact-references.json').write_text(json.dumps(references,indent=2)+'\n')
    print('Reviewed handoff kernel and previous BOOT artifact digests verified.')
