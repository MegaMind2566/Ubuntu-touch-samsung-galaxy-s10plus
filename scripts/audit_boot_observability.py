"""Read pinned display, persistent-log and command-line sources; execute none."""
import json
from pathlib import Path
import urllib.parse
import urllib.request

from audit_kernel_boot_sources import fetch, KERNEL, KERNEL_COMMIT, OUTPUT


def tree(path):
    found = []
    for page in range(1, 11):
        url = ('https://gitlab.com/api/v4/projects/' + urllib.parse.quote(KERNEL, safe='') +
               '/repository/tree?' + urllib.parse.urlencode({
                   'path': path, 'recursive': 'true', 'per_page': 100,
                   'page': page, 'ref': KERNEL_COMMIT}))
        with urllib.request.urlopen(url, timeout=45) as response:
            entries = json.loads(response.read(1024 * 1024))
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError('unexpected_source_tree')
        for entry in entries:
            value = entry['path']
            if not value.startswith(path + '/') or '..' in value.split('/'):
                raise ValueError('source_tree_path')
        found.extend(entries)
        if len(entries) < 100:
            return found
    raise ValueError('source_tree_page_limit')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {'schema': 1, 'kernel_commit': KERNEL_COMMIT,
                'upstream_code_executed': False, 'trees': {}, 'files': []}
    selected = ['arch/arm64/kernel/setup.c', 'arch/arm64/kernel/head.S',
                'drivers/video/fbdev/core/fbmem.c', 'drivers/video/fbdev/core/fbcon.c',
                'fs/pstore/ram.c', 'fs/pstore/ram_core.c']
    names = {'decon_core.c', 'decon.h', 'dsim_drv.c', 'Kconfig', 'Makefile',
             'sec_debug.c', 'sec_log.c', 'sec_debug_log.c',
             'exynos9820.dtsi', 'exynos9820-beyond2lte_common.dtsi'}
    for prefix in ('drivers/video/fbdev/exynos/dpu20', 'drivers/samsung',
                   'arch/arm64/boot/dts/exynos'):
        entries = tree(prefix)
        manifest['trees'][prefix] = entries
        for entry in entries:
            path = entry['path']
            if (entry['type'] == 'blob' and
                    (Path(path).name in names or
                     ('beyond2lte' in path and path.endswith(('.dts', '.dtsi'))))):
                selected.append(path)
    if 'drivers/video/fbdev/exynos/dpu20/decon_core.c' not in selected:
        raise ValueError('decon_source_not_found')
    for path in dict.fromkeys(selected):
        print('Fetching pinned source: ' + path, flush=True)
        manifest['files'].append(fetch(KERNEL, KERNEL_COMMIT, path))
    target = OUTPUT / 'observability-manifest.json'
    target.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'kernel_commit': KERNEL_COMMIT,
                      'files': manifest['files']}, indent=2))


if __name__ == '__main__':
    main()
