#!/usr/bin/env python3
"""Read-only audit of the exact installed Ubuntu Touch SYSTEM candidate."""
import hashlib,json,os,re,subprocess,tempfile,urllib.request,urllib.error,urllib.parse,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
WORK=Path(os.environ.get('RUNNER_TEMP',str(BASE)))/'system-handoff-audit-work'
OUT=Path(os.environ.get('AUDIT_OUTPUT',str(BASE/'ci-audit')))
REPO='MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus'
ARTIFACT_ID=11775595258
EXPECTED={'artifact_bytes':1167934045,'artifact_sha256':'8440d83ab7ddffc8d76d1f0894be89cf24b91396b447041a1ffc7e5177695f0d','zstd_bytes':1114706918,'zstd_sha256':'6729e58ca7924a7682a332c4a58a1e1ad1dc3b31437707fb49366b518da99928','system_bytes':5368709120,'system_sha256':'d23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3','run_id':38311673964,'source_commit':'c9e44ce3d38e86b51584a5e6ce05d0f8bb7f3e08'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def require(c,m):
 if not c:raise RuntimeError(m)

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(4*1024*1024):h.update(b)
 return h.hexdigest()

def api(path):
 token=os.environ.get('GH_TOKEN','')
 require(bool(token),'GH_TOKEN missing')
 return urllib.request.Request('https://api.github.com/repos/'+REPO+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})

def download():
 meta=json.load(urllib.request.urlopen(api('/actions/artifacts/'+str(ARTIFACT_ID)),timeout=60))
 require(meta['id']==ARTIFACT_ID and meta['size_in_bytes']==EXPECTED['artifact_bytes'] and meta['digest']=='sha256:'+EXPECTED['artifact_sha256'],'Artifact metadata mismatch')
 require(meta['workflow_run']['id']==EXPECTED['run_id'] and meta['workflow_run']['head_sha']==EXPECTED['source_commit'],'Artifact source mismatch')
 (OUT/'artifact-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 try:r=urllib.request.build_opener(NoRedirect).open(api('/actions/artifacts/'+str(ARTIFACT_ID)+'/zip'),timeout=60)
 except urllib.error.HTTPError as e:
  require(e.code in (301,302,303,307,308),'API did not redirect');location=e.headers['Location'];e.close()
 else:r.close();raise RuntimeError('Expected temporary blob redirect')
 parsed=urllib.parse.urlparse(location)
 require(parsed.scheme=='https' and (parsed.hostname.endswith('.blob.core.windows.net') or parsed.hostname.endswith('.githubusercontent.com')),'Unexpected artifact storage host')
 p=WORK/'system-artifact.zip';h=hashlib.sha256();n=0
 with urllib.request.urlopen(urllib.request.Request(location),timeout=120) as response,p.open('wb') as f:
  while b:=response.read(4*1024*1024):
   n+=len(b);require(n<=EXPECTED['artifact_bytes'],'Artifact too large');h.update(b);f.write(b)
 require(n==EXPECTED['artifact_bytes'] and h.hexdigest()==EXPECTED['artifact_sha256'],'Artifact payload mismatch')
 return p

def unpack(p):
 zstd=WORK/'rootfs.img.zst'
 with zipfile.ZipFile(p) as z:
  require(z.testzip() is None,'ZIP CRC failed')
  index=z.getinfo('system-candidate/rootfs.img.zst');require(index.file_size==EXPECTED['zstd_bytes'],'Compressed SYSTEM size mismatch')
  with z.open(index) as src,zstd.open('wb') as dst:
   while b:=src.read(4*1024*1024):dst.write(b)
  for name in ['SHA256SUMS','system-report.json','assembly-manifest.json']:
   data=z.read('system-candidate/'+name);require(len(data)<1024*1024,'Unexpected metadata size');(OUT/name).write_bytes(data)
 require(digest(zstd)==EXPECTED['zstd_sha256'],'Compressed SYSTEM digest mismatch')
 raw=WORK/'rootfs.img';n=0;h=hashlib.sha256()
 proc=subprocess.Popen(['zstd','--decompress','--stdout',str(zstd)],stdout=subprocess.PIPE)
 try:
  with raw.open('wb') as f:
   while b:=proc.stdout.read(4*1024*1024):
    n+=len(b);require(n<=EXPECTED['system_bytes'],'Expanded SYSTEM too large');f.write(b);h.update(b)
  require(proc.wait()==0,'zstd failed')
 finally:
  if proc.poll() is None:proc.kill();proc.wait()
 require(n==EXPECTED['system_bytes'] and h.hexdigest()==EXPECTED['system_sha256'],'Expanded SYSTEM digest mismatch')
 return raw

def debug(image,command):
 r=subprocess.run(['debugfs','-R',command,str(image)],capture_output=True,timeout=60)
 return {'returncode':r.returncode,'stdout':r.stdout.decode('utf-8','replace')[:512*1024],'stderr':r.stderr.decode('utf-8','replace')[:8192]}

def main():
 WORK.mkdir(parents=True,exist_ok=False);OUT.mkdir(parents=True,exist_ok=True)
 raw=unpack(download())
 report={'identity':EXPECTED,'artifact_id':ARTIFACT_ID,'read_only':True,'filesystem_commands':{},'files':{},'elf':{}}
 paths=['/','/etc','/usr/lib/lxc-android-config','/usr/libexec/lxc-android-config','/usr/lib/systemd/system','/etc/systemd/system','/opt/halium-overlay','/opt/halium-overlay/system/etc','/var/lib/lxc/android','/var/log/journal']
 for p in paths:report['filesystem_commands']['ls '+p]=debug(raw,'ls -l '+p)
 texts=['/usr/libexec/lxc-android-config/mount-android-system','/usr/libexec/lxc-android-config/mount-android-partitions','/usr/libexec/lxc-android-config/mount-halium-overlay','/usr/libexec/lxc-android-config/start-android-container','/usr/libexec/lxc-android-config/lxc-android-init','/init','/etc/fstab','/usr/lib/lxc-android-config/common.sh','/usr/lib/lxc-android-config/lxc-android-start','/usr/lib/lxc-android-config/lxc-android-init','/usr/lib/lxc-android-config/overlay-store.sh','/etc/system-image/writable-paths','/etc/systemd/journald.conf','/etc/systemd/system/default.target','/usr/lib/systemd/system/default.target','/usr/lib/systemd/system/lxc-android-config.service','/usr/lib/systemd/system/lxc-android.service','/usr/lib/systemd/system/lightdm.service','/var/lib/lxc/android/config','/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml','/usr/lib/os-release']
 for p in texts:report['files'][p]={'stat':debug(raw,'stat '+p),'content':debug(raw,'cat '+p)}
 for i,p in enumerate(['/init','/sbin/init','/usr/sbin/init','/lib/systemd/systemd','/usr/lib/systemd/systemd','/bin/sh','/usr/bin/dash','/lib/ld-linux-aarch64.so.1','/usr/lib/ld-linux-aarch64.so.1','/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1','/usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1']):
  item={'stat':debug(raw,'stat '+p)}
  dest=WORK/('elf-'+str(i))
  item['dump']=debug(raw,'dump '+p+' '+str(dest))
  if dest.is_file():
   item['size']=dest.stat().st_size;item['sha256']=digest(dest)
   with dest.open('rb') as stream:magic=stream.read(4)
   if magic==b'\x7fELF':
    result=subprocess.run(['readelf','-h','-l','-d',str(dest)],capture_output=True,text=True,timeout=30)
    item['readelf']=result.stdout[:128*1024];item['readelf_stderr']=result.stderr[:8192]
   else:
    with dest.open('rb') as stream:item['non_elf_prefix']=stream.read(8192).decode('utf-8','replace')
   dest.unlink()
  report['elf'][p]=item
 # Inspect direct systemd runtime dependencies at their normal ARM64 locations.
 needed=set()
 for item in report['elf'].values():needed.update(re.findall(r'Shared library: \[([^\]]+)\]',item.get('readelf','')))
 report['systemd_dependency_paths']={name:{d:debug(raw,'stat '+d+'/'+name) for d in ['/usr/lib/aarch64-linux-gnu/systemd','/usr/lib/aarch64-linux-gnu','/lib/aarch64-linux-gnu']} for name in sorted(needed)}
 # Inspect embedded Android routing and vendor mount definitions, never mount or execute.
 android=WORK/'android-rootfs.img'
 report['android_dump']=debug(raw,'dump /var/lib/lxc/android/android-rootfs.img '+str(android))
 if android.is_file():
  report['android_identity']={'bytes':android.stat().st_size,'sha256':digest(android)}
  report['android_filesystem']={p:debug(android,'ls -l '+p) for p in ['/','/system','/system/etc','/system/etc/init','/vendor','/odm']}
  report['android_files']={p:{'stat':debug(android,'stat '+p),'content':debug(android,'cat '+p)} for p in ['/fstab.exynos9820','/fstab.samsungexynos9820','/system/etc/fstab.exynos9820','/system/etc/init/hw/init.rc','/system/build.prop','/system/etc/prop.default','/system/etc/init/hw/init.exynos9820.rc','/system/etc/init/halium.rc']}
 # Enumerate complete service names without collecting binaries.
 for d in ['/usr/lib/systemd/system','/etc/systemd/system']:
  listing=debug(raw,'ls -p '+d)
  for name in re.findall(r'^/\d+/\d+/\d+/\d+/([^/]+)/',listing['stdout'],re.M):
   if name.endswith(('.service','.target','.mount','.socket')) and re.search(r'android|halium|lightdm|lomiri|overlay|local-fs|journald|lxc|usb',name):
    p=d+'/'+name
    if p not in report['files']:report['files'][p]={'stat':debug(raw,'stat '+p),'content':debug(raw,'cat '+p)}
 (OUT/'system-userspace-audit.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'audit_complete':True,'artifact_id':ARTIFACT_ID,'system_sha256':EXPECTED['system_sha256'],'file_count':len(report['files']),'output':str(OUT)},indent=2))
if __name__=='__main__':main()
