#!/usr/bin/python3
# Copyright (C) 2026 S10+ port contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Event-driven user-unit MTP gate. No USB mode, kernel or greeter writes."""

import json
import os
from pathlib import Path
import platform
import re
import signal
import socket
import sys


KERNEL = "4.14.280-gb9b70b29c94c-dirty"
STATE = Path("/sys/class/android_usb/android0/state")
MTP_MODES = frozenset(("mtp", "mtp_adb"))
UNIT = "mtp-server.service"
USB_NAME = "com.meego.usb_moded"
USB_PATH = "/com/meego/usb_moded"
FAILURE = 77
NO_SUCH_UNIT = "org.freedesktop.systemd1.NoSuchUnit"


def report(event, **fields):
    print(json.dumps({"event": event, **fields}, sort_keys=True), flush=True)


def dbus_error_fields(error, Gio):
    """Log identifiers, never free-form remote messages or bus addresses."""
    def identifier(value):
        value = str(value or "")
        return value if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", value) else "redacted"
    return {"domain": identifier(error.domain), "code": int(error.code),
            "remote_error": identifier(Gio.DBusError.get_remote_error(error))}


def parse_uevent(data, sender, flags=0):
    """Accept complete kernel android0 state events; never userspace senders."""
    if sender[0] != 0 or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        return None
    if not data or len(data) > 65536 or not data.endswith(b"\0"):
        return None
    try:
        fields = data.rstrip(b"\0").decode("ascii").split("\0")
        properties = {}
        for field in fields[1:]:
            key, value = field.split("=", 1)
            if key in properties:
                return None
            properties[key] = value
    except (UnicodeError, ValueError):
        return None
    if properties.get("SUBSYSTEM") != "android_usb":
        return None
    if properties.get("ACTION") not in ("add", "change"):
        return None
    path = properties.get("DEVPATH", "")
    if not path.startswith("/devices/") or path.rsplit("/", 1)[-1] != "android0":
        return None
    state = properties.get("USB_STATE")
    return state if state in ("DISCONNECTED", "CONNECTED", "CONFIGURED") else None


class Gate:
    """Lifecycle reducer, injected unit calls make actual policy fixture-testable."""

    def __init__(self, call, read_state=None):
        self.call = call
        self.mode = None
        self.state = None
        self.running = None
        self.read_state = read_state or (lambda: self.state)

    def set_mode(self, mode):
        self.mode = mode
        self.reconcile()

    def set_state(self, state):
        self.state = state
        self.reconcile()

    def reconcile(self):
        wanted = self.state == "CONFIGURED" and self.mode in MTP_MODES
        if wanted:
            # A queued CONFIGURED or a synchronous mode reply may be stale.
            self.state = self.read_state()
            wanted = self.state == "CONFIGURED"
        if wanted == self.running:
            return
        # Latch before a call: an error must not become an automatic retry loop.
        self.running = wanted
        if wanted:
            self.call("ResetFailedUnit")
            # The reset acknowledgment can take time. Revalidate immediately
            # before requesting the native process, not only before that call.
            self.state = self.read_state()
            if self.state != "CONFIGURED":
                self.running = False
                self.call("StopUnit")
                return
            # Restart rather than Start: a queued disconnect StopUnit can be
            # replaced by a very fast reconnect. Always reopen the native fd.
            self.call("RestartUnit")
        else:
            self.call("StopUnit")
        report("mtp-gate", configured=self.state == "CONFIGURED",
               mtp_mode=self.mode in MTP_MODES, requested_running=wanted)


class UnitControl:
    def __init__(self, proxy, Gio, GLib):
        self.proxy, self.Gio, self.GLib = proxy, Gio, GLib

    def __call__(self, method):
        if method not in ("ResetFailedUnit", "RestartUnit", "StopUnit"):
            raise ValueError("unsupported-unit-operation")
        values = (UNIT,) if method == "ResetFailedUnit" else (UNIT, "replace")
        signature = "(s)" if method == "ResetFailedUnit" else "(ss)"
        try:
            self.proxy.call_sync(method, self.GLib.Variant(signature, values),
                                 self.Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
        except self.GLib.Error as error:
            fields = dbus_error_fields(error, self.Gio)
            report("unit-call-error", method=method, **fields)
            if method == "ResetFailedUnit" and fields["remote_error"] == NO_SUCH_UNIT:
                # systemd intentionally does not load for ResetFailedUnit:
                # an unloaded unit has no failed state. RestartUnit loads this
                # fixed, preflight-verified unit itself. No retry or extra load.
                report("unit-reset-unloaded", unit=UNIT)
                return
            raise


def apply_kernel_states(gate, states):
    if not states:
        return
    # A disconnect invalidates the old descriptor even if the link has already
    # reconfigured. Coalesce before readiness to avoid starting from historical
    # intermediate events. Gate also checks the current state file before start.
    if any(state != "CONFIGURED" for state in states):
        gate.set_state("DISCONNECTED")
    report("usb-state", state=states[-1])
    gate.set_state(states[-1])


def read_kernel_state():
    state = STATE.read_text(encoding="ascii").strip()
    if state not in ("DISCONNECTED", "CONNECTED", "CONFIGURED"):
        raise ValueError("invalid-kernel-state")
    return state


def main():
    if platform.system() != "Linux" or platform.release() != KERNEL:
        report("refused", reason="kernel-mismatch")
        return FAILURE
    if os.geteuid() == 0:
        report("refused", reason="run-on-existing-lomiri-user-bus")
        return FAILURE
    from gi.repository import Gio, GLib

    systemd = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES | Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS | Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        None, "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager", None)

    unit_call = UnitControl(systemd, Gio, GLib)
    gate = Gate(unit_call, read_kernel_state)
    # Stop the old process before setting up any event source. A setup failure
    # must leave an inactive service, not the original disconnected restart loop.
    gate.set_mode(None)
    loop = GLib.MainLoop()
    failed = [False]

    def fail(reason):
        if failed[0]:
            return
        failed[0] = True
        report("failed", reason=reason)
        try:
            unit_call("StopUnit")
        except GLib.Error:
            report("failed", reason="stop-unit-call-failed")
        loop.quit()

    usb = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES | Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        None, USB_NAME, USB_PATH, USB_NAME, None)

    def read_mode():
        if not usb.get_name_owner():
            gate.set_mode(None)
            return
        result = usb.call_sync("mode_request", None, Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
        if not result.is_of_type(GLib.VariantType.new("(s)")):
            raise ValueError("invalid-mode-reply")
        gate.set_mode(result.unpack()[0])

    def owner_changed(*_args):
        try:
            read_mode()
        except (GLib.Error, ValueError, OSError):
            fail("mode-query-failed")

    def mode_signal(_proxy, _owner, name, parameters):
        if name != "sig_usb_current_state_ind":
            return
        try:
            if not parameters.is_of_type(GLib.VariantType.new("(s)")):
                raise ValueError("invalid-mode-signal")
            gate.set_mode(parameters.unpack()[0])
        except (GLib.Error, ValueError, OSError):
            fail("mode-signal-or-unit-call-failed")

    # Kernel netlink multicast is event-driven and available without root.
    # Subscribe before bootstrap to avoid losing an edge between read and watch.
    monitor = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)
    monitor.setblocking(False)
    monitor.bind((0, 1))  # NETLINK_KOBJECT_UEVENT, kernel multicast group

    def readable(_fd, condition):
        if condition & (GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL):
            fail("kernel-event-source-lost")
            return False
        try:
            states = []
            for _ in range(64):
                try:
                    data, _ancillary, flags, sender = monitor.recvmsg(65536)
                except BlockingIOError:
                    break
                state = parse_uevent(data, sender, flags)
                if state is not None:
                    states.append(state)
            if states:
                apply_kernel_states(gate, states)
            return True
        except (OSError, ValueError, GLib.Error):
            fail("kernel-event-or-unit-call-failed")
            return False

    GLib.io_add_watch(monitor.fileno(), GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP | GLib.IO_NVAL, readable)
    usb.connect("g-signal", mode_signal)
    usb.connect("notify::g-name-owner", owner_changed)

    def shutdown():
        try:
            unit_call("StopUnit")
        except GLib.Error:
            failed[0] = True
        loop.quit()
        return False

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, shutdown)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, shutdown)
    try:
        gate.set_state(read_kernel_state())
        read_mode()
        loop.run()
    except (OSError, ValueError, GLib.Error):
        fail("bootstrap-or-unit-call-failed")
    finally:
        monitor.close()
    return FAILURE if failed[0] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        report("failed", reason=type(error).__name__)
        sys.exit(FAILURE)
