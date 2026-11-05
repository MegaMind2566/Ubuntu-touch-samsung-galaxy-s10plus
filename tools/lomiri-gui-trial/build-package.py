#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a text-only exact GUI trial bundle, never install or call a device."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import lomiri_glass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        raise SystemExit('Choose a new output archive in an existing directory')
    _,lock,_,_=lomiri_glass.load_package(ROOT/'shell/lomiri-glass')
    prepared=json.loads((args.prepared/'prepared-manifest.json').read_text(encoding='utf-8'))
    if prepared['patch_sha256']!=lock['patch_sha256'] or len(prepared['files'])!=39:
        raise SystemExit('Prepared candidate does not match the locked patch/39 files')
    source_files=['scripts/lomiri_glass.py','scripts/uos27_radio_bridge.py',
      'shell/lomiri-glass/upstream.lock.json','shell/lomiri-glass/integration.patch',
      'tools/lomiri-gui-trial/trial.py','tools/lomiri-gui-trial/README.md',
      'tools/lomiri-gui-trial/uos27-radio-bridge.service']
    source_files += ['shell/lomiri-glass/qml/Glass/'+name for name in sorted(lock['module_files'])]
    entries={name:(ROOT/name).read_bytes() for name in source_files}
    digest=lambda data:hashlib.sha256(data).hexdigest()
    files={}
    for name,info in prepared['files'].items():
        data=(args.prepared/name).read_bytes()
        if digest(data)!=info['prepared_sha256']:
            raise SystemExit('Prepared payload changed: '+name)
        if info['kind']=='modified' and info['original_sha256']!=lock['files'][name]:
            raise SystemExit('Original source identity mismatch: '+name)
        if info['kind']=='new' and digest(data)!=lock['module_files'][PurePosixPath(name).name]:
            raise SystemExit('Glass module changed: '+name)
        files[name]={'bytes':len(data),'sha256':digest(data),
                     'kind':info['kind'],'original_sha256':info['original_sha256']}
        entries['candidate/'+name]=data
    spec=importlib.util.spec_from_file_location('trial_contract',ROOT/'tools/lomiri-gui-trial/trial.py')
    trial=importlib.util.module_from_spec(spec);spec.loader.exec_module(trial)
    manifest={'schema':1,'kind':'timed-native-lomiri-qml-candidate',
      'upstream_commit':trial.UPSTREAM,'source_tested_commit':'fce018c5ded5ebce1d82120f88fa9feb17ae09c3',
      'patch_sha256':lock['patch_sha256'],'kernel':trial.KERNEL,'architecture':'arm64',
      'qml_root':'/usr/share/lomiri','trial_seconds':trial.SECONDS,
      'package_versions':{'lomiri':trial.VERSION,'lomiri-common':trial.VERSION},
      'files':files,'support_files':{n:{'bytes':len(entries[n]),'sha256':digest(entries[n])} for n in source_files},
      'installed':False,'root_runtime_preflight_pending':True,'full_ios27_parity':False}
    manifest_bytes=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    entries['candidate-manifest.json']=manifest_bytes
    prefix='ut-s10-gui-trial-20261105/'
    with zipfile.ZipFile(args.output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(entries.items()):
            path=PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or b'\0' in data or b'PRIVATE KEY-----' in data:
                raise SystemExit('Unsafe/non-text payload: '+name)
            archive.writestr(prefix+name,data)
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:raise SystemExit('Archive CRC failed')
        for name,data in entries.items():
            if archive.read(prefix+name)!=data:raise SystemExit('Archive identity failed')
    print(json.dumps({'archive':str(args.output.resolve()),'bytes':args.output.stat().st_size,
      'archive_sha256':digest(args.output.read_bytes()),'manifest_sha256':digest(manifest_bytes),
      'candidate_files':len(files),'support_files':len(source_files),'installed':False}))


if __name__=='__main__':main()
