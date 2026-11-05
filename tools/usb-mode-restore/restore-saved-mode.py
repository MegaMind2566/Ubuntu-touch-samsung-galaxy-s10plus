#!/usr/bin/env python3
"""Restore an already saved USB mode after the BOOT 6 rescue-mode latch.

Uses only usb-moded's public system-bus API. No configuration, authentication,
device-node or filesystem writes. Kernel release is a compatibility guard,
not a verification of the BOOT image hash. At most one mode change is attempted.
"""
import ast
import json
import os
from pathlib import Path
import platform
import re
import subprocess
from time import monotonic, sleep

KERNEL_RELEASE = "4.14.280-gb9b70b29c94c-dirty"
INIT_DONE = "/run/systemd/boot-status/init-done"
MARKERS = ("/userdata/.force-adb", "/userdata/.force-ssh")
SAFE_MODES = {"mtp", "mtp_adb", "rndis", "rndis_adb", "charging_only_adb"}
MODE_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class ProbeError(Exception):
    pass


def effective_uid():
    return getattr(os, "geteuid", lambda: -1)()


def kernel_release():
    return platform.release()


def exists(path):
    return Path(path).exists()


def bus(method, argument=None, seconds=3):
    command = ["/usr/bin/gdbus", "call", "--system", "--dest", "com.meego.usb_moded",
               "--object-path", "/com/meego/usb_moded", "--method", "com.meego.usb_moded." + method]
    if argument is not None:
        command.append(argument)
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=seconds, check=False,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except subprocess.TimeoutExpired:
        raise ProbeError("bus-timeout") from None
    except OSError:
        raise ProbeError("bus-unavailable") from None
    if result.returncode:
        raise ProbeError("bus-call-failed")
    if len(result.stdout) > 4096:
        raise ProbeError("invalid-bus-response")
    try:
        reply = ast.literal_eval(result.stdout.decode("utf-8", "strict"))
        if not isinstance(reply, tuple) or len(reply) != 1 or not isinstance(reply[0], str):
            raise ValueError()
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        raise ProbeError("invalid-bus-response") from None
    return reply[0]


def mode(method, seconds=3):
    value = bus(method, seconds=seconds)
    if not MODE_NAME.fullmatch(value):
        raise ProbeError("invalid-mode-name")
    return value


def wait_for_mode(expected):
    deadline = monotonic() + 5
    for _ in range(25):
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        if mode("mode_request", seconds=min(3, remaining)) == expected:
            return
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(0.2, remaining))
    raise ProbeError("mode-readback-timeout")


def emit(event, **values):
    print(json.dumps(dict(event=event, **values), sort_keys=True), flush=True)


def main():
    if effective_uid() != 0:
        emit("failed", reason="root-required")
        return 1
    for condition, reason in ((kernel_release() != KERNEL_RELEASE, "kernel-mismatch"),
                              (any(exists(path) for path in MARKERS), "force-marker"),
                              (not exists(INIT_DONE), "init-not-done")):
        if condition:
            emit("skipped", reason=reason)
            return 0
    try:
        current, configured = mode("mode_request"), mode("get_config")
        if current != "developer_mode" or configured == "developer_mode":
            emit("skipped", reason="preserve-current-selection")
            return 0
        if configured not in SAFE_MODES:
            emit("skipped", reason="unsupported-saved-mode")
            return 0
        available = [value.strip() for value in bus("get_available_modes").split(",")]
        if len(available) > 32 or any(not MODE_NAME.fullmatch(value) for value in available):
            raise ProbeError("invalid-available-modes")
        if configured not in available:
            emit("skipped", reason="saved-mode-unavailable")
            return 0
        if bus("set_mode", configured) != configured:
            raise ProbeError("mode-change-not-acknowledged")
        wait_for_mode(configured)
    except ProbeError as error:
        emit("failed", reason=str(error))
        return 1
    emit("restored", mode=configured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
