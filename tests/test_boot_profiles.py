"""BOOT 6 RAM-profile checks using the exact ARM64 BusyBox; mounts are mocked."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tools/boot-observer'
FIXTURES = ROOT / 'tests/fixtures'
SOURCES = [
 ('profile-beyond2lte-original.yaml','/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml','e21dadf14458a0d4aafce01b2e982c56ff0de6cb55ecd52bfbdad2a085423da6'),
 ('profile-force-hwc2-original.conf','/opt/halium-overlay/etc/default/lsc-wrapper.d/10-force-hwc2.conf','93cdec8663134c4c2f59cf76fa1a8f76befaf6c7e1b9c1c65ebf72930b8d7d92'),
 ('wait-for-hwc-original.conf','/opt/halium-overlay/usr/lib/systemd/system/lightdm.service.d/wait-for-hwc.conf','b56435dc9766c4e8caa50ce8af95dfb369240ff0e33e90efc7f6d95e2dd00fcb'),
 ('profile-vndservicemanager-original.rc','/opt/halium-overlay/opt/halium-overlay/vendor/etc/init/vndservicemanager.rc','71053a59906dfd3a71613e29173134573a96e2b800876bb788ea82a7cfa74110'),
 ('profile-init-disabled-original.rc','/opt/halium-overlay/opt/halium-overlay/system/etc/init/init.disabled.rc','a4ce90452ff078df7e42112fe6c3afbf44605086d67000506f7a33068e59c70d'),
 ('profile-mount-halium-overlay-original.service','/usr/lib/systemd/system/mount-halium-overlay.service','62e88bc040ab36e6b3a5e8012ce747178b437bf8eeaada5a0b8a16fe29785d6e'),
 ('profile-lxc-android-original.service','/usr/lib/systemd/system/lxc-android-config.service','c3e4ca001b9feb57cc27b68240e000b8fee9c5fd2a0248b9cf98d500a25db181'),
]
PARENTS=['/etc/deviceinfo/devices','/etc/default/lsc-wrapper.d','/usr/lib/systemd/system/lightdm.service.d']
ALIAS='/var/lib/lxc/android/rootfs'

def quote(s):return "'"+str(s).replace("'","'\"'\"'")+"'"
def write(p,data=b'preserved\n',mode=0o644):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.chmod(mode)

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--qemu',required=True);parser.add_argument('--cpio',type=Path,required=True)
 parser.add_argument('--repository',type=Path,default=ROOT)
 parser.add_argument('--log-independent-only',action='store_true')
 args=parser.parse_args();sys.path.insert(0,str(args.repository/'scripts'))
 from prepare_boot_diagnostic import entries
 items=entries(args.cpio.read_bytes());entry=next(i for i in items if i['name']=='bin/busybox')
 peers=[i['data'] for i in items if i['data'] and i['values'][0]==entry['values'][0] and i['values'][7:9]==entry['values'][7:9]]
 assert len(peers)==1
 for fixture,_,sha in SOURCES:assert hashlib.sha256((FIXTURES/fixture).read_bytes()).hexdigest()==sha
 qemu=shutil.which(args.qemu);assert qemu
 observations=[]
 with tempfile.TemporaryDirectory(prefix='ut-profiles-') as temp:
  top=Path(temp);binary=top/'busybox-arm64';write(binary,peers[0],0o700);backend=[qemu,str(binary)];shell=[*backend,'sh']
  for name in ['profile-functions','android-profile-fix']:subprocess.run([*shell,'-n',str(HERE/name)],check=True)
  def fixture(name,scenario='success'):
   case=top/name;root=case/'root';root.mkdir(parents=True);dev=root/'dev';dev.mkdir();dev.chmod(0o755)
   for node in ['sda25','sda26','sda31']:write(dev/node)
   for directory in PARENTS:
    d=root/directory[1:];d.mkdir(parents=True);d.chmod(0o755);write(d/'preserved.conf',b'keep me\n');(d/'preserved-link').symlink_to('preserved.conf')
   for f,p,_ in SOURCES:write(root/p[1:],(FIXTURES/f).read_bytes())
   mounts=case/'mounts';mounts.write_text(f'udev {dev} devtmpfs rw,nosuid 0 0\n{dev}/sda25 {root} ext4 ro 0 0\n')
   shim=case/'shim.py';shim.write_text('''import json,os,pathlib,shutil,subprocess,sys
case=pathlib.Path(CASE);name,*args=sys.argv[1:]
with (case/'calls').open('a') as f:f.write(json.dumps([name,*args])+'\\n')
statefile=case/'mount-state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {'count':0,'mounts':[]}
scenario=(case/'scenario').read_text()
def save():statefile.write_text(json.dumps(state))
def replace(src,dst):
 if dst.is_dir() and not dst.is_symlink():shutil.rmtree(dst)
 elif dst.exists() or dst.is_symlink():dst.unlink()
 if src.is_dir():shutil.copytree(src,dst,symlinks=True,copy_function=shutil.copy2)
 elif src.is_symlink():dst.symlink_to(os.readlink(src))
 else:shutil.copy2(src,dst)
if name=='mount':
 assert args[:3]==['-n','-o','bind'] and len(args)==5,args
 state['count']+=1;src,dst=map(pathlib.Path,args[3:]);idx=state['count'];save()
 if scenario=='bind-fail-'+str(idx):sys.exit(1)
 backup=case/('backup-'+str(idx));replace(dst,backup);replace(src,dst)
 state['mounts'].append([str(dst),str(backup)]);save()
 if scenario=='readback-mismatch':
  if dst.is_dir():next(p for p in dst.iterdir() if p.is_file() and not p.is_symlink()).write_text('bad')
  else:dst.chmod(dst.stat().st_mode|0o200);dst.write_text('bad')
 sys.exit(0)
if name=='umount':
 if scenario=='unmount-failure':sys.exit(1)
 for row in state['mounts'][::-1]:
  if row[0]==args[0]:replace(pathlib.Path(row[1]),pathlib.Path(row[0]));state['mounts'].remove(row);save();sys.exit(0)
 sys.exit(1)
sys.exit(subprocess.call(BACKEND+[name,*args]))
'''.replace('CASE',repr(str(case))).replace('BACKEND',repr(backend)))
   bridge=case/'bb';write(bridge,('#!/bin/sh\nexec '+quote(sys.executable)+' '+quote(shim)+' "$@"\n').encode(),0o700)
   (case/'scenario').write_text(scenario)
   def patch(text,pre=False):
    mapping={'/bin/busybox':str(bridge),'/ut-boot-android-profile-fix':str(case/'android-helper'),'/proc/mounts':str(mounts),'/dev/kmsg':str(case/'kmsg')}
    if pre:mapping['/root']=str(root)
    else:
     for p in [ALIAS,'/android','/opt','/dev','/userdata']:mapping[p]=str(root/p[1:])
    pattern=r'(?<![A-Za-z0-9_/.-])(?:'+'|'.join(re.escape(p) for p in sorted(mapping,key=len,reverse=True))+r')(?![A-Za-z0-9_.-])'
    text=re.sub(pattern,lambda m:mapping[m.group()],text)
    if pre:text=text.replace('runtime="/dev/${ram##*/}"','runtime="$ram"')
    else:text=text.replace('for POINT in / ', 'for POINT in '+quote(root)+' ')
    return text.replace(' = 0:700 ]',f' = {os.getuid()}:700 ]')
   write(case/'android-helper',patch((HERE/'android-profile-fix').read_text()).encode())
   script=case/'prepare';script.write_text(patch((HERE/'profile-functions').read_text(),True)+'\nut_boot_profiles_prepare run-1\n')
   return case,root,mounts,script
  def run(script):return subprocess.run([*shell,str(script)],capture_output=True,timeout=60)
  def calls(case):return [json.loads(l) for l in (case/'calls').read_text().splitlines()]
  # Every immutable input, plus layout and mount guards, is checked before mutation.
  guards=['hash-'+str(i) for i in range(len(SOURCES))]+['source-link','parent-link','missing-parent','root-rw','dev-noexec','already-mounted','destination-exists','special-file']
  if args.log_independent_only:guards=[]
  for name in guards:
   case,root,mounts,script=fixture(name)
   if name.startswith('hash-'):write(root/SOURCES[int(name[5:])][1][1:],b'changed\n')
   elif name=='source-link':
    p=root/SOURCES[0][1][1:];saved=p.with_suffix('.saved');p.rename(saved);p.symlink_to(saved)
   elif name=='parent-link':
    p=root/PARENTS[0][1:];saved=p.with_name('saved');p.rename(saved);p.symlink_to(saved)
   elif name=='missing-parent':shutil.rmtree(root/PARENTS[1][1:])
   elif name=='root-rw':mounts.write_text(mounts.read_text().replace('ext4 ro','ext4 rw'))
   elif name=='dev-noexec':mounts.write_text(mounts.read_text().replace('rw,nosuid','rw,noexec'))
   elif name=='already-mounted':mounts.write_text(mounts.read_text()+f'fixture {root/PARENTS[0][1:]} tmpfs rw 0 0\n')
   elif name=='destination-exists':write(root/(PARENTS[0]+'/beyond2lte.yaml')[1:])
   elif name=='special-file':os.mkfifo(root/(PARENTS[0]+'/unexpected')[1:])
   result=run(script);assert result.returncode!=0,(name,result.stderr)
   assert not any(a[0] in ['mktemp','cp','mount','umount','rm','rmdir','mkdir','chmod'] for a in calls(case)),name
   observations.append({'prepare_guard':name,'rejected_before_mutation':True})
  # Check exact content preservation, source alias, unit ordering, and rollback.
  for scenario in (['no-log'] if args.log_independent_only else ['success','no-log','bind-fail-3','bind-fail-5','readback-mismatch']):
   case,root,mounts,script=fixture('prep-'+scenario,scenario)
   if scenario=='no-log':script.write_text(script.read_text().replace('ut_boot_profiles_prepare run-1','ut_boot_profiles_prepare none'))
   result=run(script);successful=scenario in ['success','no-log']
   assert (result.returncode==0)==successful,(scenario,result.stderr)
   ramdirs=list((root/'dev').glob('.ut-boot-6-profile.*'))
   if not successful:
    assert not ramdirs,scenario
    assert (root/SOURCES[0][1][1:]).read_bytes()==(FIXTURES/SOURCES[0][0]).read_bytes()
   else:
    assert len(ramdirs)==1;ram=ramdirs[0];assert ram.stat().st_mode&0o777==0o700
    for p in PARENTS:
     d=root/p[1:];assert (d/'preserved.conf').read_bytes()==b'keep me\n';assert (d/'preserved-link').is_symlink();assert d.stat().st_mode&0o777==0o755
    expected=(FIXTURES/SOURCES[0][0]).read_text().replace('beyond2lte:\n','beyond2lte:\n  Names:\n    - beyond2\n',1)
    assert (root/(PARENTS[0]+'/beyond2lte.yaml')[1:]).read_text()==expected
    assert (root/SOURCES[0][1][1:]).read_text()==expected
    unit=(root/SOURCES[5][1][1:]).read_text();assert unit.startswith((FIXTURES/SOURCES[5][0]).read_text())
    run_name='none' if scenario=='no-log' else 'run-1'
    assert unit.endswith(f'ExecStartPost={ram}/busybox sh {ram}/android-profile-fix {ram} {run_name}\n')
   observations.append({'prepare_case':scenario,'success':result.returncode==0})
  # Full post-overlay stage with both LXC aliases and recovery mask before RC binds.
  cases=['no-log'] if args.log_independent_only else ['success','no-log','source-hash','cached-hash','vendor-rw','wrong-vendor','missing-script','script-link','alias-missing','special-rc','bind-fail-2','bind-fail-6','readback-mismatch']
  for scenario in cases:
   case,root,mounts,script=fixture('android-'+scenario);assert run(script).returncode==0
   ram=next((root/'dev').glob('.ut-boot-6-profile.*'));(case/'scenario').write_text(scenario if scenario.startswith('bind-') or scenario=='readback-mismatch' else 'success')
   (case/'calls').write_text('');(case/'mount-state.json').unlink()
   for p in ['/android/system/etc/init','/android/vendor/etc/init',ALIAS+'/system/etc/init',ALIAS+'/vendor/etc/init']:
    d=root/p[1:];d.mkdir(parents=True);d.chmod(0o755);write(d/'original.rc',b'keep original rc\n');(d/'original-link').symlink_to('original.rc')
   for p in ['/android/vendor/bin/install-recovery.sh',ALIAS+'/vendor/bin/install-recovery.sh']:write(root/p[1:],b'original dangerous restore fixture\n',0o755)
   data=root/'userdata/ubuntu-touch-boot-6/run-1';data.mkdir(parents=True,mode=0o700);data.parent.chmod(0o700)
   mounts.write_text(f'udev {root}/dev devtmpfs rw,nosuid 0 0\n{root}/dev/sda25 {root} ext4 ro 0 0\n'
      +f'{root}/dev/sda31 {root}/userdata ext4 rw 0 0\n'
      +''.join(f'{root}/dev/{"sda26" if p=="/android/vendor" else "sda25"} {root}{p} ext4 ro 0 0\n' for p in ['/android','/android/system','/android/vendor']))
   if scenario=='source-hash':write(root/SOURCES[3][1][1:],b'changed\n')
   elif scenario=='cached-hash':write(ram/'init.disabled.rc',b'changed\n')
   elif scenario=='vendor-rw':mounts.write_text(mounts.read_text().replace(f'{root}/android/vendor ext4 ro',f'{root}/android/vendor ext4 rw'))
   elif scenario=='wrong-vendor':mounts.write_text(mounts.read_text().replace(f'{root}/dev/sda26 ',f'{root}/dev/sda25 '))
   elif scenario=='missing-script':(root/'android/vendor/bin/install-recovery.sh').unlink()
   elif scenario=='script-link':
    p=root/'android/vendor/bin/install-recovery.sh';p.unlink();p.symlink_to('other.sh');write(p.with_name('other.sh'))
   elif scenario=='alias-missing':shutil.rmtree(root/(ALIAS+'/vendor/etc/init')[1:])
   elif scenario=='special-rc':os.mkfifo(root/'android/vendor/etc/init/unexpected')
   run_name='none' if scenario=='no-log' else 'run-1'
   invoke=case/'invoke';invoke.write_text('exec '+quote(ram/'busybox')+' sh '+quote(ram/'android-profile-fix')+' '+quote(ram)+' '+run_name+'\n')
   result=run(invoke);successful=scenario in ['success','no-log']
   assert (result.returncode==0)==successful,(scenario,result.returncode,result.stderr)
   actions=calls(case);mounts_called=[a for a in actions if a[0]=='mount']
   if successful:
    assert len(mounts_called)==6
    assert all(a[-1].endswith('/install-recovery.sh') for a in mounts_called[:2]),mounts_called
    for p in ['/android/vendor/bin/install-recovery.sh',ALIAS+'/vendor/bin/install-recovery.sh']:
     assert (root/p[1:]).read_bytes()==b'#!/vendor/bin/sh\nexit 0\n'
    for p in ['/android/system/etc/init',ALIAS+'/system/etc/init']:
     assert (root/(p+'/init.disabled.rc')[1:]).read_bytes()==(FIXTURES/SOURCES[4][0]).read_bytes()
    for p in ['/android/vendor/etc/init',ALIAS+'/vendor/etc/init']:
     d=root/p[1:];assert (d/'vndservicemanager.rc').read_bytes()==(FIXTURES/SOURCES[3][0]).read_bytes();assert (d/'original.rc').read_bytes()==b'keep original rc\n';assert (d/'original-link').is_symlink()
    if scenario=='no-log':assert not (data/'android-profile.log').exists()
    else:assert 'complete' in (data/'android-profile.log').read_text();assert (data/'android-profile.log').stat().st_size<4096
   else:
    state=json.loads((case/'mount-state.json').read_text()) if (case/'mount-state.json').exists() else {'mounts':[]}
    assert not state['mounts'],(scenario,state)
    if not scenario.startswith('bind-') and scenario!='readback-mismatch':assert not mounts_called,scenario
   observations.append({'android_case':scenario,'success':result.returncode==0,'recovery_mask_first':successful})
  result={'schema':1,'success':True,'actual_arm64_busybox':True,'busybox_sha256':hashlib.sha256(peers[0]).hexdigest(),'mount_boundaries_mocked':True,'handset_accessed':False,'observations':observations}
  output=args.repository/('out/boot-profile-no-log-tests.json' if args.log_independent_only else 'out/boot-profile-tests.json');output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
