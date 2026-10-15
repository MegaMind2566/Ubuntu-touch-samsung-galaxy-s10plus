"""Inspect mapper loading without creating a surface or allocating pixel buffers."""
import ctypes
import glob
import json
import os
from pathlib import Path
import resource
import stat
import sys

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
MAX_READ = 65536


def read_text(path, limit=MAX_READ):
    try:
        with open(path, 'rb') as stream:
            return stream.read(limit).decode('utf-8', 'replace')
    except OSError as error:
        return {'errno': error.errno, 'error': str(error)}


def path_info(path):
    result = {'path': str(path)}
    try:
        value = os.lstat(path)
        result.update(mode=oct(stat.S_IMODE(value.st_mode)), uid=value.st_uid,
                      gid=value.st_gid, kind=stat.S_IFMT(value.st_mode),
                      access_read=os.access(path, os.R_OK),
                      access_write=os.access(path, os.W_OK))
        if stat.S_ISLNK(value.st_mode):
            result['link'] = os.readlink(path)
        if stat.S_ISCHR(value.st_mode):
            result.update(major=os.major(value.st_rdev), minor=os.minor(value.st_rdev))
    except OSError as error:
        result.update(errno=error.errno, error=str(error))
    return result


def credentials():
    return {'uid': os.getuid(), 'euid': os.geteuid(), 'gid': os.getgid(),
            'groups': os.getgroups(), 'apparmor': read_text('/proc/self/attr/current', 4096),
            'selected_environment': selected_environment(os.environ)}


def selected_environment(environment):
    exact = {'PATH', 'HOME', 'USER', 'LOGNAME', 'LD_LIBRARY_PATH', 'LD_PRELOAD',
             'EGL_PLATFORM', 'XDG_RUNTIME_DIR', 'QT_QPA_PLATFORM', 'QT_QPA_PLATFORM_PLUGIN_PATH'}
    return {key: str(value)[:4096] for key, value in environment.items()
            if key in exact or key.startswith(('HYBRIS_', 'MIR_', 'ANDROID_'))}


def device_paths():
    paths = ['/dev', '/dev/binder', '/dev/hwbinder', '/dev/vndbinder', '/dev/ion',
             '/dev/mali0', '/dev/dri', '/dev/dma_heap', '/dev/binderfs']
    for pattern in ('/dev/mali*', '/dev/dri/*', '/dev/dma_heap/*', '/dev/binderfs/*'):
        paths.extend(sorted(glob.glob(pattern))[:32])
    return sorted(set(paths))


def live_processes():
    results = []
    for item in sorted(Path('/proc').iterdir(), key=lambda value: value.name):
        if not item.name.isdecimal():
            continue
        command = read_text(item / 'cmdline', 16384)
        if not isinstance(command, str) or not command:
            continue
        args = command.split('\0')
        executable = Path(args[0]).name
        if executable not in ('lomiri', 'lomiri-system-compositor', 'lightdm', 'lsc-wrapper'):
            continue
        status = read_text(item / 'status')
        wanted = ('Name:', 'State:', 'Uid:', 'Gid:', 'Groups:', 'CapEff:', 'NoNewPrivs:', 'Seccomp:', 'NSpid:')
        environment = read_text(item / 'environ')
        env = dict(entry.split('=', 1) for entry in environment.split('\0') if '=' in entry) if isinstance(environment, str) else {}
        maps = read_text(item / 'maps', 1024 * 1024)
        results.append({'pid': int(item.name), 'argv': args[:24],
                        'status': [line for line in status.splitlines() if line.startswith(wanted)] if isinstance(status, str) else status,
                        'apparmor': read_text(item / 'attr/current', 4096),
                        'mount_namespace': path_info(item / 'ns/mnt'),
                        'selected_environment': selected_environment(env),
                        'graphics_maps': [line for line in maps.splitlines() if any(word in line.lower() for word in ('hybris', 'gralloc', 'mapper', 'libui.', '/vendor/lib64/egl/'))][:160] if isinstance(maps, str) else maps})
        if len(results) >= 16:
            break
    return results


def vendor_inventory():
    patterns = ('/vendor/lib64/hw/*mapper*', '/vendor/lib64/hw/*gralloc*',
                '/vendor/lib64/egl/*', '/vendor/lib64/libgralloc*',
                '/android/vendor/lib64/hw/*mapper*', '/android/vendor/lib64/hw/*gralloc*',
                '/android/vendor/lib64/egl/*', '/android/vendor/lib64/libgralloc*')
    files = sorted(set(path for pattern in patterns for path in glob.glob(pattern)))[:160]
    manifest_paths = sorted(set(path for root in ('/vendor', '/android/vendor')
                                for pattern in ('/etc/vintf/manifest*.xml', '/etc/vintf/manifest/*.xml')
                                for path in glob.glob(root + pattern)))[:100]
    manifests = []
    for path in manifest_paths:
        data = read_text(path)
        if not isinstance(data, str):
            manifests.append({'path': path, 'read': data})
            continue
        if any(word in data.lower() for word in ('graphics.mapper', 'graphics.allocator', 'graphics.composer')):
            manifests.append({'path': path, 'content': data[:16384]})
    chain = set()
    for path in files:
        chain.update(str(parent) for parent in Path(path).parents)
    return {'files': [path_info(path) for path in files],
            'directory_chain': [path_info(path) for path in sorted(chain)],
            'graphics_manifests': manifests}


def inventory():
    return {'schema': 1, 'inspection': 'UT_GRAPHICS_PROBE_1',
            'bounds': {'read_bytes': MAX_READ, 'outer_log_bytes': 524288,
                       'outer_capture_may_truncate_json_with_head_tail_marker': True},
            'credentials': credentials(), 'uptime': read_text('/proc/uptime', 256),
            'kernel': read_text('/proc/version', 4096),
            'android_path_metadata': [path_info(path) for path in
                                      ('/android', '/android/system', '/android/vendor',
                                       '/vendor', '/android/linkerconfig',
                                       '/android/linkerconfig/ld.config.txt')],
            'generated_android_linker_config': read_text('/android/linkerconfig/ld.config.txt'),
            'devices': [path_info(path) for path in device_paths()],
            'processes': live_processes(), 'vendor': vendor_inventory()}


def emit(event, **values):
    print(json.dumps({'event': event, **values}, sort_keys=True), flush=True)


def bionic_stderr_logger():
    common = ctypes.CDLL('libhybris-common.so.1', mode=os.RTLD_NOW | os.RTLD_GLOBAL)
    common.android_dlopen.argtypes = [ctypes.c_char_p, ctypes.c_int]
    common.android_dlopen.restype = ctypes.c_void_p
    common.android_dlsym.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    common.android_dlsym.restype = ctypes.c_void_p
    handle = common.android_dlopen(b'liblog.so', os.RTLD_NOW)
    if not handle:
        raise RuntimeError('Bionic liblog.so did not load')
    symbols = {name: common.android_dlsym(handle, name.encode()) for name in
               ('__android_log_set_logger', '__android_log_stderr_logger',
                '__android_log_set_minimum_priority', '__android_log_write')}
    missing = [name for name, address in symbols.items() if not address]
    if missing:
        raise RuntimeError('Bionic logger symbols unavailable: ' + ', '.join(missing))
    ctypes.CFUNCTYPE(None, ctypes.c_void_p)(symbols['__android_log_set_logger'])(symbols['__android_log_stderr_logger'])
    ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(symbols['__android_log_set_minimum_priority'])(2)
    value = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p)(symbols['__android_log_write'])(
        6, b'UTGraphicsProbe', b'Bionic stderr route verified')
    if value < 0:
        raise RuntimeError('Bionic stderr marker write failed: ' + str(value))
    emit('bionic_stderr_logger_installed', marker_write_return=value)
    return common


def mapper_probe():
    emit('credentials', **credentials())
    emit('device_access_metadata', devices=[path_info(path) for path in device_paths()])
    # Keep the CDLL alive: logger function pointers belong to this process only.
    logger_library = None
    try:
        logger_library = bionic_stderr_logger()
    except (OSError, AttributeError, RuntimeError) as error:
        emit('bionic_stderr_logger_unavailable', error=str(error))
    emit('loading_libui_wrapper', name='libui.so.1')
    library = ctypes.CDLL('libui.so.1', mode=os.RTLD_NOW | os.RTLD_LOCAL)
    constructor = library.graphic_buffer_new
    constructor.argtypes = []
    constructor.restype = ctypes.c_void_p
    destructor = library.graphic_buffer_free
    destructor.argtypes = [ctypes.c_void_p]
    destructor.restype = None
    emit('calling_graphic_buffer_default_constructor', allocates_pixel_buffer=False,
         logger_installed=logger_library is not None)
    pointer = constructor()
    if not pointer:
        emit('graphic_buffer_constructor_returned_null')
        return 2
    emit('graphic_buffer_default_constructor_returned')
    destructor(pointer)
    emit('graphic_buffer_released')
    return 0


def main():
    if sys.argv[1:] == ['--inventory']:
        print(json.dumps(inventory(), indent=2, sort_keys=True), flush=True)
        return 0
    if sys.argv[1:]:
        raise ValueError('unknown probe arguments')
    try:
        return mapper_probe()
    except (OSError, AttributeError, RuntimeError) as error:
        emit('probe_loader_error', error=str(error))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
