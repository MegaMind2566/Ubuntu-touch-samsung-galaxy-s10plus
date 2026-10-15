"""Read and verify immutable build artifacts through a scoped GitHub CI token."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get('GITHUB_REPOSITORY', 'MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def api(path,token):
    request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,
                                   headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=45) as response:return json.loads(response.read(2*1024*1024))


def obtain(run_id,commit,filename,artifact_id,token):
    deadline=time.monotonic()+5400
    while True:
        run=api('actions/runs/'+str(run_id),token)
        if run['head_sha']!=commit or run['head_branch']!='main':raise ValueError('build_identity_mismatch')
        if run['status']=='completed':break
        if time.monotonic()>=deadline:raise ValueError('build_wait_expired')
        time.sleep(20)
    if run['conclusion']!='success':raise ValueError('build_failed')
    return obtain_artifact(run_id,commit,filename,artifact_id,token)


def obtain_job(run_id,commit,filename,artifact_name,job_name,token,artifact_id=None):
    """Read a successful dependency job without waiting for its entire workflow."""
    run=api('actions/runs/'+str(run_id),token)
    if run['head_sha']!=commit or run['head_branch']!='main':raise ValueError('build_identity_mismatch')
    jobs=api('actions/runs/'+str(run_id)+'/jobs',token)['jobs']
    matches=[j for j in jobs if j['name']==job_name]
    if len(matches)!=1 or matches[0]['conclusion']!='success':raise ValueError('dependency_job_not_successful')
    return obtain_artifact(run_id,commit,filename,artifact_id,token,artifact_name)


def obtain_artifact(run_id,commit,filename,artifact_id,token,artifact_name=None):
    candidates=[a for a in api('actions/runs/'+str(run_id)+'/artifacts',token)['artifacts']
                if (a['name']==artifact_name if artifact_name else a['name'].startswith('beyond2lte-halium12-')) and not a['expired']]
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
