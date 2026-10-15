"""Firmware verification must retain the tested gzip stream on every host."""
import argparse
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--images',type=Path,required=True)
    a=p.parse_args()
    spec=importlib.util.spec_from_file_location('package_handoff',ROOT/'scripts/package-ubuntu-boot-handoff.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original=(a.images/'boot.img').read_bytes()
    with patch('gzip.compress',side_effect=AssertionError('firmware verification attempted host recompression')):
        image,_,_=module.validate(a.images)
    assert image==original
    print('PASS: tested BOOT bytes retained exactly; validation performs no host gzip recompression.')
