#!/usr/bin/env python3
"""Probe our own joinable pthread, never another process or a real signal.

Linux AArch64/glibc only. A bounded child resolves the same GLIBC_2.34 symbol
imported by the installed adbd. This tests a bug prerequisite, not an ADB fix.
"""
import json
import platform
import subprocess
import sys

WORKER = r'''
import ctypes, json, os, threading, time
libc = ctypes.CDLL('libc.so.6', use_errno=True)
libc.dlvsym.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
libc.dlvsym.restype = ctypes.c_void_p
address = libc.dlvsym(libc._handle, b'pthread_kill', b'GLIBC_2.34')
if not address:
    raise RuntimeError('GLIBC_2.34 pthread_kill unavailable')
kill_zero = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_ulong, ctypes.c_int)(address)
callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)
libc.pthread_create.argtypes = [ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p,
                               callback_type, ctypes.c_void_p]
libc.pthread_create.restype = ctypes.c_int
libc.pthread_join.argtypes = [ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
libc.pthread_join.restype = ctypes.c_int
ready = threading.Event()
worker_tid = []
@callback_type
def worker(_):
    worker_tid.append(threading.get_native_id())
    ready.set()
    return None
thread = ctypes.c_ulong()
create_rc = libc.pthread_create(ctypes.byref(thread), None, worker, None)
if create_rc:
    raise RuntimeError('pthread_create failed: ' + str(create_rc))
result = {'symbol_version': 'GLIBC_2.34', 'create_rc': create_rc}
try:
    if not ready.wait(1):
        raise RuntimeError('worker callback deadline')
    task = '/proc/self/task/' + str(worker_tid[0])
    deadline = time.monotonic() + 1
    while os.path.exists(task) and time.monotonic() < deadline:
        time.sleep(0.005)
    result['worker_task_absent_before_join'] = not os.path.exists(task)
    if not result['worker_task_absent_before_join']:
        raise RuntimeError('worker exit deadline')
    # The pthread remains joinable and valid here. Signal 0 delivers no signal.
    result['kill_zero_before_join_rc'] = kill_zero(thread.value, 0)
finally:
    result['join_rc'] = libc.pthread_join(thread.value, None)
print(json.dumps(result, sort_keys=True))
'''


def main():
    if sys.platform != 'linux' or platform.machine() != 'aarch64' or platform.libc_ver()[0] != 'glibc':
        raise SystemExit('Requires Linux AArch64 with glibc; no probe executed')
    try:
        result = subprocess.run([sys.executable, '-c', WORKER], capture_output=True,
                                text=True, timeout=5, check=True)
        report = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError) as error:
        raise SystemExit('Probe failed: ' + type(error).__name__) from None
    report['schema'] = 1
    report['kind'] = 'joinable-pthread-lifetime-probe'
    report['libc'] = ' '.join(platform.libc_ver())
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
