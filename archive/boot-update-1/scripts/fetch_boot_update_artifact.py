"""Obtain only the reviewed correction build through a scoped CI token."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

REPO='MegaMind2566/Beyond2lte-UbuntuTouch-port'
RUN=38439532393
COMMIT='a6390494079bdaa8fb479644fa902835dafddee2'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def api(path,token):
    request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,
                                   headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=45) as response:return json.loads(response.read(2*1024*1024))


def main():
    token=os.environ['UT_ARTIFACT_TOKEN'];deadline=time.monotonic()+5400
    while True:
        run=api('actions/runs/'+str(RUN),token)
        if run['head_sha']!=COMMIT or run['head_branch']!='main':raise ValueError('build_identity_mismatch')
        if run['status']=='completed':break
        if time.monotonic()>=deadline:raise ValueError('correction_build_wait_expired')
        time.sleep(20)
    if run['conclusion']!='success':raise ValueError('correction_build_failed')
    candidates=[a for a in api('actions/runs/'+str(RUN)+'/artifacts',token)['artifacts']
                if a['name'].startswith('beyond2lte-halium12-') and not a['expired']]
    if len(candidates)!=1:raise ValueError('correction_artifact_count')
    artifact=candidates[0]
    if not 0<artifact['size_in_bytes']<=128*1024*1024:raise ValueError('correction_artifact_size')
    request=urllib.request.Request(artifact['archive_download_url'],headers={'Authorization':'Bearer '+token})
    try:
        urllib.request.build_opener(NoRedirect()).open(request,timeout=45)
        raise ValueError('artifact_redirect_missing')
    except urllib.error.HTTPError as error:
        if error.code!=302:raise
        url=error.headers['Location']
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname.endswith('.blob.core.windows.net'):raise ValueError('unexpected_storage')
    target=Path('out/corrected-adaptation.zip');target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256();size=0
    with urllib.request.urlopen(url,timeout=60) as source,target.open('xb') as output:
        while chunk:=source.read(1024*1024):
            size+=len(chunk)
            if size>artifact['size_in_bytes']:raise ValueError('correction_artifact_oversized')
            digest.update(chunk);output.write(chunk)
    if size!=artifact['size_in_bytes'] or 'sha256:'+digest.hexdigest()!=artifact['digest']:raise ValueError('correction_artifact_digest')
    Path('out/corrected-artifact-reference.json').write_text(json.dumps({'run':RUN,'commit':COMMIT,
        'artifact_id':artifact['id'],'zip_bytes':size,'sha256':digest.hexdigest()},indent=2)+'\n')
    print('Reviewed correction build and archive digest verified.')


if __name__=='__main__':main()
