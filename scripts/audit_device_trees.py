"""Inspect the verified stock DTB/DTBO with DTC; operate only on local files."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

from inspect_stock_firmware import boot_header, dtbo_table
from inspect_stock_dtb import fdt_summary


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(argv):
    return subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=60)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dtb-partition', type=Path, required=True)
    p.add_argument('--recovery', type=Path, required=True)
    p.add_argument('--tools', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    raw = a.dtb_partition.read_bytes()
    recovery = a.recovery.read_bytes()
    if digest(raw) != '3c533aa9c658bd0ba7e3837da3fe8faa3e1e4185272c6052065ce4904801db36':
        raise ValueError('stock HWC1 DTB partition identity')
    if digest(recovery) != 'caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e':
        raise ValueError('verified modified TWRP identity')
    if (a.tools / 'source-commit.txt').read_text().strip() != 'f3451d12532b9d382707c458a2ae2e5aa0e1eee4':
        raise ValueError('DTC source identity')
    for line in (a.tools / 'checksums.txt').read_text().splitlines():
        expected, name = line.split()
        name = Path(name).name
        if name not in ('dtc', 'fdtget', 'fdtoverlay') or digest((a.tools / name).read_bytes()) != expected:
            raise ValueError('DTC executable identity')
    a.out.mkdir(parents=True, exist_ok=True)
    entries = dtbo_table(raw)['entries']
    if len(entries) != 1:
        raise ValueError('expected single stock base tree')
    e = entries[0]
    base = raw[e['offset']:e['offset'] + e['bytes']]
    base_path = a.out / 'stock-base.dtb'
    base_path.write_bytes(base)
    header = boot_header(recovery)
    table = recovery[header['recovery_dtbo_offset']:header['recovery_dtbo_offset'] + header['recovery_dtbo_bytes']]
    if digest(table) != '8f37aa2c33f6463a8b96f55c696deec7caaf9d4c61747ee30e5184ae9aa7da1a':
        raise ValueError('stock-equivalent recovery DTBO identity')
    overlay_entry = dtbo_table(table)['entries'][9]
    overlay = table[overlay_entry['offset']:overlay_entry['offset'] + overlay_entry['bytes']]
    overlay_path = a.out / 'stock-overlay-9.dtbo'
    overlay_path.write_bytes(overlay)
    effective = a.out / 'stock-effective-dtbo9.dtb'
    result = run([a.tools / 'fdtoverlay', '-i', base_path, '-o', effective, overlay_path])
    (a.out / 'overlay-apply.log').write_text(result.stderr)
    if result.returncode:
        raise RuntimeError('libfdt could not apply overlay 9')
    trees = []
    for path in (base_path, effective):
        result = run([a.tools / 'dtc', '-I', 'dtb', '-O', 'dts', '-o', path.with_suffix('.dts'), path])
        path.with_suffix('.dtc.log').write_text(result.stderr)
        if result.returncode:
            raise RuntimeError('DTC could not decode ' + path.name)
        blob = path.read_bytes()
        trees.append(dict(name=path.name, bytes=len(blob), sha256=digest(blob),
                          dtc_exit=result.returncode, warning_count=result.stderr.count('Warning'),
                          warning_categories=dict(Counter(re.findall(r'Warning \(([^)]+)\)', result.stderr))),
                          fdt_summary=fdt_summary(blob)))
    report = dict(schema=1, dtc_version=run([a.tools / 'dtc', '--version']).stdout.strip(),
                  dtc_source_commit=(a.tools / 'source-commit.txt').read_text().strip(),
                  stock_dtb_partition_sha256=digest(raw), recovery_sha256=digest(recovery),
                  dtbo_table_sha256=digest(table), overlay_index=9, overlay_entry=overlay_entry,
                  selection_basis='DTBO index 9 and hardware revision 26 were observed in running TWRP; normal boot selection is not captured.',
                  trees=trees, overlay_apply_exit=0, handset_accessed=False, handset_modified=False,
                  kernel_driver_binding_compatibility_verified=False, normal_boot_runtime_observed=False,
                  limits=['DTC warnings are recorded without suppression.',
                          'Successful decoding/application does not prove the normal-boot bootloader tree or all custom-kernel bindings.'])
    (a.out / 'device-tree-tools-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'dtc_version': report['dtc_version'], 'trees': [dict(name=t['name'], warnings=t['warning_count']) for t in trees]}))


if __name__ == '__main__':
    main()
