"""Recover and independently validate kernel symbols offline; never accesses a handset."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

from fetch_boot_update_2_artifacts import obtain
from inspect_stock_firmware import boot_header

TOOL_COMMIT = '19683fb95b29cd31362d49e6f48ab8368f96cbdf'
BUILDS = {
    'boot-1': (38439532393, 'a6390494079bdaa8fb479644fa902835dafddee2', 11835412882,
               '6acda3c4f5d4746aa1c83845ab51bc155e2a3ee9d2923aa339a7d1b6ebac800e',
               'd3be319ae9353908e917894d624460e743bfc078d676c592189d415ef02b0993'),
    'boot-2': (38452662502, '6b46ada66199005fa7df03c8d4a42f3a6d9c510c', 11843035830,
               '00974b1d2b48523a8b0bbf23c6eb22db1f8f2165150adc064196018e6e1f28fd',
               'cad81022329d1effb50d1ed421148b5c1741e41ae2eb0414d75ac06ec64ecda0'),
}
FUNCTIONS = ('start_kernel', 'kernel_init', 'kernel_init_freeable',
             'prepare_namespace', 'mount_sar_ramdisk', 'unpack_to_rootfs',
             'wait_for_device_probe', 'load_default_modules')
VARIABLES = ('_text', '_stext', '_end', 'ramdisk_execute_command',
             'kallsyms_relative_base', 'kallsyms_offsets')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fetch(out):
    out.mkdir(parents=True, exist_ok=True)
    refs = []
    for name, (run, commit, artifact, archive_sha, boot_sha) in BUILDS.items():
        filename = name + '-symbol-input.zip'
        ref = obtain(run, commit, filename, artifact, os.environ['UT_ARTIFACT_TOKEN'])
        require(ref['sha256'] == archive_sha, 'pinned artifact hash: ' + name)
        with zipfile.ZipFile(Path('out') / filename) as z:
            entries = [v for v in z.infolist() if v.filename.endswith('/boot.img') or v.filename == 'boot.img']
            require(len(entries) == 1 and entries[0].file_size == 53215232, 'BOOT archive shape: ' + name)
            data = z.read(entries[0])
        require(sha(data) == boot_sha, 'pinned BOOT hash: ' + name)
        h = boot_header(data)
        kernel = data[h['page_bytes']:h['page_bytes'] + h['kernel_bytes']]
        require(kernel[56:60] == b'ARM\x64', 'ARM64 Image header')
        (out / (name + '.Image')).write_bytes(kernel)
        refs.append(dict(ref, name=name, boot_bytes=len(data), boot_sha256=sha(data),
                         kernel_bytes=len(kernel), kernel_sha256=sha(kernel), boot_header=h))
    (out / 'inputs.json').write_text(json.dumps(refs, indent=2) + '\n')


def elf64(data):
    """Read ELF structures independently of the converter's ELF implementation."""
    require(data[:7] == b'\x7fELF\x02\x01\x01', 'ELF64 little endian')
    typ, machine = struct.unpack_from('<HH', data, 16)
    require(typ == 2 and machine == 183, 'AArch64 executable ELF')
    entry = struct.unpack_from('<Q', data, 24)[0]
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 58)
    require(size == 64 and 0 < count < 100 and names_index < count and offset + size * count <= len(data),
            'ELF section header bounds')
    sections = []
    for i in range(count):
        fields = struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size)
        name, stype, flags, address, start, length, link, info, alignment, entsize = fields
        require(stype == 8 or start + length <= len(data), 'ELF section content bounds')
        sections.append(dict(name_offset=name, type=stype, flags=flags, address=address,
                             offset=start, bytes=length, link=link, entry_bytes=entsize))
    n = sections[names_index]
    names = data[n['offset']:n['offset'] + n['bytes']]

    def string(buf, off):
        require(0 <= off < len(buf), 'ELF string offset')
        end = buf.find(b'\0', off)
        require(end >= off, 'ELF string termination')
        return buf[off:end].decode('utf-8')

    for section in sections:
        section['name'] = string(names, section['name_offset'])
    tables = [s for s in sections if s['type'] == 2]
    require(len(tables) == 1, 'one ELF symbol table')
    tab = tables[0]
    require(tab['entry_bytes'] == 24 and tab['bytes'] % 24 == 0 and tab['link'] < count,
            'ELF symbol table bounds')
    s = sections[tab['link']]
    require(s['type'] == 3, 'ELF symbol strings')
    strings = data[s['offset']:s['offset'] + s['bytes']]
    symbols = []
    for p in range(tab['offset'], tab['offset'] + tab['bytes'], 24):
        name, info, other, index, address, length = struct.unpack_from('<IBBHQQ', data, p)
        if name:
            symbols.append(dict(name=string(strings, name), address=address,
                                type=info & 15, binding=info >> 4, section=index, bytes=length))
    return entry, sections, symbols


def analyze(inputs, out, source, objdump):
    out.mkdir(parents=True, exist_ok=True)
    actual_commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    require(actual_commit == TOOL_COMMIT, 'converter source commit')
    results = []
    for ref in json.loads((inputs / 'inputs.json').read_text()):
        name = ref['name']
        image = inputs / (name + '.Image')
        raw = image.read_bytes()
        require(sha(raw) == ref['kernel_sha256'], 'input kernel preservation')
        elf = out / (name + '.elf')
        log = out / (name + '-conversion.log')
        with log.open('w') as f:
            subprocess.run([sys.executable, '-m', 'vmlinux_to_elf.scripts.vmlinux_to_elf',
                            str(image), str(elf), '--e-machine', '183', '--bit-size', '64'],
                           stdout=f, stderr=subprocess.STDOUT, check=True, timeout=240)
        require(elf.is_file(), 'converter must produce output')
        data = elf.read_bytes()
        entry, sections, symbols = elf64(data)
        first = next(s for s in sections if s['name'] == '.kernel')
        base = first['address']
        mappings = []
        for s in sections:
            if s['name'] not in ('.kernel', '.kernel2'):
                continue
            pos = s['address'] - base
            require(0 <= pos <= len(raw) and pos + s['bytes'] <= len(raw), 'ELF kernel mapping bounds')
            mapped = data[s['offset']:s['offset'] + s['bytes']]
            require(mapped == raw[pos:pos + s['bytes']], 'ELF preserves mapped raw kernel bytes')
            mappings.append(dict(section=s['name'], raw_offset=pos, bytes=s['bytes'], sha256=sha(mapped)))
        by_name = {s['name']: s for s in symbols}
        require(by_name['_text']['address'] == base, 'base address agrees with _text')
        require(by_name['_end']['address'] >= base + len(raw), 'kernel end exceeds file-backed bytes')
        for required in ('start_kernel', 'kernel_init_freeable', 'mount_sar_ramdisk'):
            require(required in by_name, 'required boot symbol: ' + required)
        selected = {}
        addresses = sorted(set(s['address'] for s in symbols if s['type'] == 2))
        for fn in FUNCTIONS + VARIABLES:
            if fn not in by_name:
                selected[fn] = {'present': False}
                continue
            s = by_name[fn]
            item = dict(s, present=True, address_hex=hex(s['address']))
            if fn in FUNCTIONS:
                start = s['address']
                end = min(next((a for a in addresses if a > start), start + 8192), start + 8192)
                pos = start - base
                require(0 <= pos < len(raw) and pos + end - start <= len(raw), 'boot function mapping bounds')
                item.update(raw_offset=pos, disassembled_bytes=end - start,
                            raw_bytes_sha256=sha(raw[pos:pos + end - start]))
                result = subprocess.run([objdump, '-d', '--start-address=' + hex(start),
                                         '--stop-address=' + hex(end), str(elf)],
                                        capture_output=True, text=True, check=True, timeout=30)
                (out / (name + '-' + fn + '.asm')).write_text(result.stdout)
            selected[fn] = item
        (out / (name + '-symbols.tsv')).write_text(
            'address\ttype\tbinding\tname\n' + ''.join(
                f"{s['address']:016x}\t{s['type']}\t{s['binding']}\t{s['name']}\n" for s in symbols))
        results.append(dict(ref, elf_bytes=len(data), elf_sha256=sha(data),
                            symbol_count=len(symbols), inferred_base_address=hex(base),
                            elf_entry_point=hex(entry), sections=sections, mapped_bytes_verified=mappings,
                            selected_symbols=selected))
    report = dict(schema=1, tool_repository='marin-m/vmlinux-to-elf', tool_commit=actual_commit,
                  packages={p: importlib.metadata.version(p) for p in
                            ('vmlinux-to-elf', 'lz4', 'zstandard', 'minilzo', 'peewee')},
                  images=results, handset_accessed=False, handset_modified=False,
                  normal_boot_runtime_observed=False, ubuntu_touch_boot_verified=False,
                  limits=['Base and entry point are reconstructed static analysis metadata; they do not prove bootloader behavior.',
                          'Default BSS allocation is synthetic; output ELF is not a flashable BOOT image.',
                          'Relocation tables may be represented separately from the original raw byte ranges.'])
    (out / 'kernel-symbol-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({r['name']: {'symbols': r['symbol_count'], 'mapped_bytes_verified': True,
                                'base': r['inferred_base_address']} for r in results}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('fetch', 'analyze'))
    p.add_argument('--inputs', type=Path, default=Path('out/kernel-symbol-inputs'))
    p.add_argument('--out', type=Path, default=Path('out/kernel-symbol-audit'))
    p.add_argument('--source', type=Path, default=Path('out/vmlinux-to-elf-source'))
    p.add_argument('--objdump', default='aarch64-linux-gnu-objdump')
    a = p.parse_args()
    if a.mode == 'fetch':
        fetch(a.inputs)
    else:
        analyze(a.inputs, a.out, a.source, a.objdump)
