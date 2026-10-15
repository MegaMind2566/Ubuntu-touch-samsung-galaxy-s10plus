"""Compile the pinned Samsung USB mode helper; no USB or handset access.

The fixture models only its list/string inputs. --source verifies the complete
pinned configfs.c and applies the actual patch before extracting the helper.
Optional --arm64-clang/--qemu also runs the same helper as a static ARM64 ELF.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'a2e95754e836f0d3b733528c24ad36a569f9f77bf0273d79719635787af3fe7d'
PATCH = ROOT / 'patches/kernel/0005-guard-null-usb-configuration-string.patch'
ANCHOR = '''#ifdef CONFIG_USB_CONFIGFS_UEVENT
static bool is_symboliclink_change_mode(struct config_usb_cfg *cfg)
{
\tstruct gadget_config_name *cn;

\tif (!list_empty(&cfg->string_list)) {
\t\tlist_for_each_entry(cn, &cfg->string_list, list) {
\t\t\tif (strcmp(cn->configuration, "Conf 1") != 0)
\t\t\t\treturn true;
\t\t}
\t}
\treturn false;
}

static struct usb_function *get_adb_function_from_linked_func'''

HARNESS = r'''
typedef _Bool bool;
#define true 1
#define false 0
#define NULL ((void *)0)
struct list_head { struct list_head *next, *prev; };
struct gadget_config_name { char *configuration; struct list_head list; };
struct config_usb_cfg { struct list_head string_list; };
#define container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - __builtin_offsetof(type, member)))
#define list_empty(head) ((head)->next == (head))
#define list_for_each_entry(pos, head, member) \
    for (pos = container_of((head)->next, __typeof__(*pos), member); \
         &pos->member != (head); \
         pos = container_of(pos->member.next, __typeof__(*pos), member))
static int invalid_strcmp;
/* Detect the invalid strcmp input without deliberately crashing the host. */
static int strcmp(const char *a, const char *b) {
    if (!a || !b) { invalid_strcmp++; return 0; }
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}
__HELPER__
static void append(struct list_head *head, struct list_head *entry) {
    entry->prev = head->prev; entry->next = head;
    head->prev->next = entry; head->prev = entry;
}
int main(void) {
    struct fixture_case { char *first, *second; int count, expected; } cases[] = {
        {NULL, NULL, 0, 0},
        {NULL, NULL, 1, 0},
        {"", NULL, 1, 1},
        {"Conf 1", NULL, 1, 0},
        {"rndis", NULL, 1, 1},
        {NULL, "Conf 1", 2, 0},
        {NULL, "rndis", 2, 1},
        {"rndis", NULL, 2, 1},
    };
    unsigned int i;
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        struct config_usb_cfg cfg;
        struct gadget_config_name entries[2];
        int actual;
        cfg.string_list.next = cfg.string_list.prev = &cfg.string_list;
        entries[0].configuration = cases[i].first;
        entries[1].configuration = cases[i].second;
        if (cases[i].count > 0) append(&cfg.string_list, &entries[0].list);
        if (cases[i].count > 1) append(&cfg.string_list, &entries[1].list);
        actual = is_symboliclink_change_mode(&cfg);
        if (invalid_strcmp) return 90;
        if (actual != cases[i].expected) return (int)i + 1;
    }
    return 0;
}
#ifdef FIXTURE_ARM64
__asm__(".global _start\n"
        "_start:\n"
        "bl main\n"
        "mov x8, #93\n"
        "svc #0\n");
#endif
'''


def extract_helper(source):
    start = source.index('static bool is_symboliclink_change_mode(')
    end = source.index('\n}\n', start) + 3
    return source[start:end]


def compile_and_run(root, compiler, original, corrected, qemu=None):
    values = {}
    for name, source in [('original', original), ('corrected', corrected)]:
        code = HARNESS.replace('__HELPER__', extract_helper(source))
        c_file = root / (name + ('-arm64.c' if qemu else '-host.c'))
        c_file.write_text(code)
        exe = c_file.with_suffix('')
        command = [compiler, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-fno-builtin']
        if qemu:
            command += ['--target=aarch64-linux-gnu', '-fuse-ld=lld', '-nostdlib',
                        '-static', '-ffreestanding', '-fno-stack-protector',
                        '-DFIXTURE_ARM64=1', '-Wl,-e,_start']
        subprocess.run(command + [str(c_file), '-o', str(exe)], check=True,
                       capture_output=True, text=True)
        run = subprocess.run(([qemu] if qemu else []) + [str(exe)],
                             capture_output=True, text=True, timeout=10)
        expected = 90 if name == 'original' else 0
        if run.returncode != expected:
            raise AssertionError(f'{name} USB helper returned {run.returncode}, expected {expected}: {run.stderr}')
        values[name] = {'exit_code': run.returncode,
                        'null_strcmp_detected': name == 'original',
                        'all_eight_cases_pass': name == 'corrected'}
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Original pinned drivers/usb/gadget/configfs.c')
    parser.add_argument('--arm64-clang', help='Clang with ARM64 and LLD support')
    parser.add_argument('--qemu', help='qemu-aarch64 executable')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if bool(args.arm64_clang) != bool(args.qemu):
        parser.error('--arm64-clang and --qemu must be used together')
    original = args.source.read_text() if args.source else ANCHOR + '\n'
    if args.source and hashlib.sha256(args.source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('pinned_configfs_source_mismatch')
    if original.count(ANCHOR) != 1:
        raise ValueError('pinned_samsung_helper_anchor_mismatch')
    compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
    if not compiler:
        raise ValueError('host_C_compiler_unavailable')
    with tempfile.TemporaryDirectory(prefix='usb configfs fixture ') as temporary:
        root = Path(temporary)
        target = root / 'drivers/usb/gadget/configfs.c'
        target.parent.mkdir(parents=True)
        target.write_text(original)
        subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=root, check=True,
                       capture_output=True, text=True)
        subprocess.run(['git', 'apply', str(PATCH)], cwd=root, check=True,
                       capture_output=True, text=True)
        corrected = target.read_text()
        expected_helper = extract_helper(original).replace(
            '\t\t\tif (strcmp(cn->configuration, "Conf 1") != 0)',
            '\t\t\t/* A language directory can exist before its string is written. */\n'
            '\t\t\tif (cn->configuration &&\n'
            '\t\t\t    strcmp(cn->configuration, "Conf 1") != 0)')
        if (extract_helper(corrected) != expected_helper or
                original.replace(extract_helper(original), expected_helper, 1) != corrected):
            raise AssertionError('patch_changed_code_outside_null_guard')
        report = {'schema': 1, 'kernel_pin': 'b9b70b29c94c41365704fcc2ed33be09b4617907',
                  'pinned_complete_source_verified': bool(args.source),
                  'pinned_source_sha256': SOURCE_SHA256,
                  'patch_sha256': hashlib.sha256(PATCH.read_bytes()).hexdigest(),
                  'original_helper_sha256': hashlib.sha256(extract_helper(original).encode()).hexdigest(),
                  'corrected_helper_sha256': hashlib.sha256(extract_helper(corrected).encode()).hexdigest(),
                  'samsung_branch_preserved': True,
                  'host': compile_and_run(root, compiler, original, corrected),
                  'cases': ['empty_list', 'null_string', 'empty_string', 'Conf 1',
                            'other_string', 'null_then_Conf 1', 'null_then_other', 'other_then_null'],
                  'handset_or_USB_accessed': False}
        if args.qemu:
            report['actual_arm64'] = compile_and_run(
                root, str(Path(args.arm64_clang).resolve()), original, corrected,
                str(Path(args.qemu).resolve()))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
