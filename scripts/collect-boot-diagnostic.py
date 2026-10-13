"""Read only the controlled test's bounded logs after manual return to TWRP."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import zipfile

spec=importlib.util.spec_from_file_location('first_boot_helpers',Path(__file__).with_name('collect-first-boot.py'))
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
DIAG_BYTES=__BOOT_UPDATE_BYTES__
DIAG_SHA256='__BOOT_UPDATE_SHA256__'
LOGDIR='/data/ubuntu-touch-boot-diagnostic-1'
LIMITS={'diagnostic-init':262144,'diagnostic-kernel':2097152,'diagnostic-display':32768}
NAMES={'diagnostic-init':'init.log','diagnostic-kernel':'kernel.log','diagnostic-display':'display.log'}


def command_for(name):
    if name in NAMES:
        path=LOGDIR+'/'+NAMES[name]
        return ['-d','shell',"test ! -L '"+LOGDIR+"' && test -d '"+LOGDIR+"' && test ! -L '"+path+"' && test -f '"+path+"' && /sbin/busybox head -c "+str(LIMITS[name])+" '"+path+"'"]
    if name=='diagnostic-boot-hash':
        return ['-d','shell','/sbin/busybox head -c '+str(DIAG_BYTES)+' /dev/block/sda14 | /sbin/busybox sha256sum']
    if name in ('state','uid','properties','last-kmsg','last-kmsg-start',
                'recovery-kernel','mounts','pstore-list') or name.startswith('pstore:'):
        return legacy.command_for(name)
    raise ValueError('diagnostic_query_not_allowed')


def run_query(exe,name):
    import subprocess
    try:
        r=subprocess.run([str(exe),*command_for(name)],capture_output=True,timeout=45,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if len(r.stdout)>LIMITS.get(name,524288)+4096 or len(r.stderr)>65536:
            return {'exit_code':None,'timed_out':False,'stdout':'','stderr':'output_limit'}
        return {'exit_code':r.returncode,'timed_out':False,'stdout':r.stdout.decode('utf-8','replace'),
                'stderr':r.stderr.decode('utf-8','replace')}
    except subprocess.TimeoutExpired:
        return {'exit_code':None,'timed_out':True,'stdout':'','stderr':'read_timeout'}


def collect(root,runner=run_query,verifier=legacy.check_tools):
    root=Path(root).resolve();files={};report={'schema':1,'diagnostic_version':1,
        'date_utc':datetime.now(timezone.utc).isoformat(),'adb_usb_only':True,
        'partition_writes':False,'mount_changes_requested':False,'data_format_requested':False,
        'reboot_requested':False,'ubuntu_touch_boot_verified':False,'success':False,'error':None,
        'steps':[],'diagnostic_pid1_marker_found':False,'diagnostic_kernel_version':None}
    def read(name):
        command_for(name);v=runner(root/'platform-tools/adb.exe',name)
        report['steps'].append({'operation':name,'exit_code':v['exit_code'],'timed_out':v['timed_out'],
                                'stderr':legacy.redact(v['stderr'][:4096],root)})
        if v['exit_code']==0 and not v['timed_out']:
            return legacy.redact(v['stdout'],root)
        return None
    reason='local_tools_unavailable'
    try:
        verifier(root)
        reason='twrp_usb_unavailable'
        if (read('state') or '').strip() not in ('device','recovery'):
            raise ValueError(reason)
        reason='recovery_not_root'
        if (read('uid') or '').strip()!='0': raise ValueError(reason)
        reason='recovery_device_unconfirmed'
        values=read('properties') or ''
        props=dict(line.split('|',1) for line in values.splitlines() if '|' in line)
        if (props.get('ro.product.device') not in ('beyond2','beyond2lte') or
                props.get('ro.hardware')!='exynos9820' or
                props.get('ro.twrp.version') not in ('3.7.0_9','3.7.0_9-2') or
                'G975FXXSGHWC1' not in (props.get('ro.bootloader'),props.get('ro.boot.bootloader'))):
            raise ValueError(reason)
        report['recovery_confirmed']=True
        for name in NAMES:
            value=read(name)
            if value is not None: files[name+'.txt']=value
        report['diagnostic_pid1_marker_found']='UT_DIAG_1: PID 1 STARTED' in files.get('diagnostic-init.txt','')
        match=re.search(r'Linux version (\S+)',files.get('diagnostic-kernel.txt',''))
        report['diagnostic_kernel_version']=match[1] if match else None
        for name in ('last-kmsg','last-kmsg-start','recovery-kernel','mounts'):
            value=read(name)
            if value is not None: files[name+'.txt']=value
        names=read('pstore-list') or ''
        for name in sorted(set(n for n in names.splitlines() if legacy.PSTORE_NAME.fullmatch(n)))[:16]:
            value=read('pstore:'+name)
            if value is not None: files['previous-boot-pstore-'+name+'.txt']=value
        value=(read('diagnostic-boot-hash') or '').strip()
        report['diagnostic_boot_readback_sha256']=value.split()[0] if re.fullmatch(r'[a-f0-9]{64}\s+-?',value) else None
        report['diagnostic_boot_matches']=report['diagnostic_boot_readback_sha256']==DIAG_SHA256
        report['success']=True
        report['interpretation']='A diagnostic PID 1 marker confirms this controlled ramdisk executed. Its absence does not by itself identify the failing kernel stage. This test does not start Ubuntu userspace.'
    except (OSError,ValueError) as e:
        report['error']=str(e) if isinstance(e,ValueError) and re.fullmatch('[a-z_]+',str(e)) else reason
    path=root/'ubuntu-boot-diagnostic-log-report.zip';i=1
    while path.exists():
        path=root/('ubuntu-boot-diagnostic-log-report-'+str(i)+'.zip');i+=1
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
        for name,value in files.items(): z.writestr(name,value)
        z.writestr('diagnostic-log-report.json',json.dumps(report,indent=2))
    if report['error']:
        print('Lettura fermata: '+report['error'])
    else:
        print('Log diagnostico PID 1: '+('presente' if report['diagnostic_pid1_marker_found'] else 'non trovato'))
    print('Invia questo rapporto: '+str(path),flush=True)
    return report,path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    r,_=collect(p.parse_args().root)
    raise SystemExit(0 if r['success'] else 1)
