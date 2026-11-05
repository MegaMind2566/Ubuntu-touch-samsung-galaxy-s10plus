#!/usr/bin/env python3
"""Short-lived, unprivileged GAction bridge for the real BlueZ adapter state.

The Ayatana Bluetooth action may flip an rfkill switch without bringing an
already unblocked BlueZ Adapter1 to Powered=true on this Halium port. This
bridge exposes *actual* Adapter1.Powered via a private session-bus GAction
group, allowing the existing Qt QDBusActionGroup to request the documented
BlueZ property. It is never installed as an autostart service.

It cannot bypass BlueZ/polkit permissions, and it never claims success before
reading Adapter1.Powered back. No device address, pairing, or discovery data
is logged or exported. Designed to be started for one bounded shell trial.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


BLUEZ_IFACE = "org.bluez.Adapter1"
SESSION_NAME = "org.uos27.Control"
ACTION_PATH = "/org/uos27/Control"
ACTION_NAME = "bluetooth-enabled"


def backlight_readback(path: Path = Path("/sys/class/backlight/panel")) -> dict:
    """Read native values without guessing the scale of actual_brightness."""
    result = {}
    for name in ("brightness", "actual_brightness", "max_brightness"):
        try:
            value = int((path / name).read_text(encoding="ascii").strip())
            result[name] = value if value >= 0 else None
        except (OSError, ValueError):
            result[name] = None
    return result


def bluetooth_rfkill_readback(root: Path = Path("/sys/class/rfkill")) -> list[dict]:
    """Read only block flags, without exporting rfkill IDs or device names."""
    entries = []
    try:
        devices = sorted(root.glob("rfkill[0-9]*"))
    except OSError:
        return entries
    for device in devices:
        try:
            if (device / "type").read_text(encoding="ascii").strip() != "bluetooth":
                continue
            flags = {}
            for field in ("soft", "hard"):
                flag = (device / field).read_text(encoding="ascii").strip()
                flags[field + "_blocked"] = flag == "1" if flag in ("0", "1") else None
            entries.append(flags)
        except OSError:
            continue
    return sorted(entries, key=lambda item: (str(item["soft_blocked"]),
                                              str(item["hard_blocked"])))


class TraceRecorder:
    """Session-only hardware readback; no addresses or notification contents."""

    def __init__(self, path: Path):
        # The wrapper selects a unique file in the phablet runtime directory.
        # O_EXCL/O_NOFOLLOW prevent silently replacing a previous trial log.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        self.writer = os.fdopen(fd, "w", encoding="utf-8", buffering=1)
        self.previous = None
        self.last_snapshot = 0.0

    def write(self, event: str, **details):
        try:
            self.writer.write(json.dumps({"schema": 1, "utc_epoch": time.time(),
                                          "event": event, **details}, sort_keys=True) + "\n")
        except OSError:
            # A full runtime filesystem must not break the native BlueZ UI.
            pass

    def snapshot(self, state: dict):
        now = time.monotonic()
        if state != self.previous or now - self.last_snapshot >= 15:
            self.write("readback", **state)
            self.previous = dict(state)
            self.last_snapshot = now

    def close(self):
        self.writer.close()


def adapter_paths(objects: dict) -> tuple[str, ...]:
    """Get paths only, never addresses/paired-device identities."""
    return tuple(sorted(path for path, interfaces in objects.items()
                        if isinstance(path, str) and path.startswith("/org/bluez/")
                        and isinstance(interfaces, dict) and BLUEZ_IFACE in interfaces))


def unpack_value(value):
    """Unwrap the one D-Bus variant layer, also accepting host test doubles."""
    while callable(getattr(value, "unpack", None)):
        next_value = value.unpack()
        if next_value is value:
            break
        value = next_value
    return value


def gi_modules():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    return Gio, GLib


class BluezReader:
    """System bus operations executed as the normal phablet session user."""

    def __init__(self, connection, gio, glib):
        self.connection, self.Gio, self.GLib = connection, gio, glib
        self.path: str | None = None
        # Sanitized D-Bus error NAME only; never log addresses, paired device
        # names, exception messages or authentication/permission details.
        self.last_power_error = ""

    def call(self, path, interface, method, params, reply_type, timeout_ms=4500):
        return self.connection.call_sync("org.bluez", path, interface, method,
                                         params, reply_type, self.Gio.DBusCallFlags.NONE,
                                         timeout_ms, None)

    def discover(self) -> str | None:
        reply = self.call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                          None, self.GLib.VariantType.new("(a{oa{sa{sv}}})"))
        paths = adapter_paths(unpack_value(reply)[0])
        self.path = paths[0] if paths else None
        return self.path

    def power(self) -> bool | None:
        try:
            if not self.path and not self.discover():
                return None
            reply = self.call(self.path, "org.freedesktop.DBus.Properties", "Get",
                              self.GLib.Variant("(ss)", (BLUEZ_IFACE, "Powered")),
                              self.GLib.VariantType.new("(v)"))
            value = unpack_value(reply)[0]
            actual = unpack_value(value)
            return actual if isinstance(actual, bool) else None
        except Exception:
            self.path = None  # Adapter may have been unplugged or reset.
            return None

    def set_power(self, desired: bool) -> bool:
        self.last_power_error = ""
        if not isinstance(desired, bool) or not self.path:
            self.last_power_error = "adapter-unavailable"
            return False
        try:
            self.call(self.path, "org.freedesktop.DBus.Properties", "Set",
                      self.GLib.Variant("(ssv)",
                                        (BLUEZ_IFACE, "Powered",
                                         self.GLib.Variant("b", desired))), None, 5500)
            return True
        except Exception as exc:
            name = ""
            try:
                name = self.Gio.DBusError.get_remote_error(exc) or ""
            except (AttributeError, TypeError):
                pass
            if name.startswith(("org.bluez.Error.", "org.freedesktop.DBus.Error.")):
                self.last_power_error = name
            else:
                self.last_power_error = "BlueZ-property-set-failed"
            return False


class ShortLivedBridge:
    def __init__(self, gio, glib, reader: BluezReader, trace: TraceRecorder | None = None):
        self.Gio, self.GLib, self.reader = gio, glib, reader
        self.trace = trace
        self.loop = glib.MainLoop()
        self.session = gio.bus_get_sync(gio.BusType.SESSION, None)
        self.power_actions = gio.DBusActionGroup.get(
            self.session, "org.ayatana.indicator.power", "/org/ayatana/indicator/power")
        self.indicator_actions = gio.DBusActionGroup.get(
            self.session, "org.ayatana.indicator.bluetooth", "/org/ayatana/indicator/bluetooth")
        self.pending_power: bool | None = None
        self.group = gio.SimpleActionGroup()
        initial = reader.power()
        self.action = gio.SimpleAction.new_stateful(
            ACTION_NAME, glib.VariantType.new("b"),
            glib.Variant("b", bool(initial)))
        self.action.set_enabled(initial is not None)
        self.action.connect("activate", self.on_activate)
        self.group.add_action(self.action)
        self.export_id = self.session.export_action_group(ACTION_PATH, self.group)
        # QDBusActionGroup keeps cached values when a name vanishes. This
        # empty menu makes AyatanaMenuModel.nameOwner a reliable lifecycle
        # observer (and carries no device identities or extra actions).
        self.menu = gio.Menu.new()
        self.menu_export_id = self.session.export_menu_model(ACTION_PATH + "/phone", self.menu)
        self.bus_owner = gio.bus_own_name_on_connection(
            self.session, SESSION_NAME, gio.BusNameOwnerFlags.NONE,
            lambda *args: None, lambda *args: self.loop.quit())

    def refresh(self):
        powered = self.reader.power()
        self.action.set_enabled(powered is not None)
        if powered is not None and unpack_value(self.action.get_state()) != powered:
            self.action.set_state(self.GLib.Variant("b", powered))
        if self.trace:
            try:
                brightness = unpack_value(self.power_actions.get_action_state("brightness"))
                if not isinstance(brightness, (int, float)) or isinstance(brightness, bool):
                    brightness = None
            except Exception:
                brightness = None
            self.trace.snapshot({"bluetooth_powered": powered,
                                 "bluetooth_rfkill": bluetooth_rfkill_readback(),
                                 "native_brightness_action": brightness,
                                 **backlight_readback()})
        return True

    def on_activate(self, action, parameter):
        if parameter is None or not action.get_enabled():
            return
        desired = unpack_value(parameter)
        if not isinstance(desired, bool):
            return
        if self.pending_power is not None:
            return  # Do not race two hardware power transitions.
        if self.reader.power() == desired:
            self.refresh()
            return
        self.pending_power = desired
        native_result = self.request_native_indicator(desired)
        if self.trace:
            self.trace.write("bluetooth_request", target_powered=desired,
                             ayatana_action=native_result)
        # On Halium the indicator may unblock the lower-level rfkill switch
        # asynchronously. Give the stock action an opportunity to bring BlueZ
        # up before issuing Properties.Set as phablet. Never falsify the state.
        self.GLib.timeout_add(380, self.complete_power_request)

    def request_native_indicator(self, desired: bool) -> str:
        try:
            group = self.indicator_actions
            if not group or not group.has_action(ACTION_NAME):
                return "unavailable"
            state = unpack_value(group.get_action_state(ACTION_NAME))
            if state == desired:
                return "already-requested"
            group.activate_action(ACTION_NAME, self.GLib.Variant("b", desired))
            return "requested"
        except Exception:
            # A broken or absent indicator must not prevent a direct BlueZ
            # attempt; only the failure class is revealed, never bus metadata.
            return "unavailable"

    def complete_power_request(self):
        desired = self.pending_power
        if desired is None:
            return False
        try:
            # Skip a redundant DBus Set if the original indicator succeeded.
            actual = self.reader.power()
            already = actual == desired
            accepted = True if already else self.reader.set_power(desired)
            if self.trace:
                self.trace.write("bluetooth_set_result", target_powered=desired,
                                 already_powered=already,
                                 bluez_set_returned=accepted,
                                 error=getattr(self.reader, "last_power_error", "")
                                 if not accepted else "")
        finally:
            self.pending_power = None
        self.refresh()
        return False

    def serve(self, ttl_seconds: int):
        self.GLib.timeout_add(650, self.refresh)
        self.GLib.timeout_add_seconds(ttl_seconds, self.loop.quit)
        self.refresh()
        try:
            self.loop.run()
        finally:
            self.Gio.bus_unown_name(self.bus_owner)
            self.session.unexport_menu_model(self.menu_export_id)
            self.session.unexport_action_group(self.export_id)
            if self.trace:
                self.trace.write("end", cause="bounded-service-exit")
                self.trace.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--serve", action="store_true")
    parser.add_argument("--ttl", type=int, default=720)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    if os.geteuid() == 0 and args.serve:
        parser.error("Refusing to control BlueZ as root")
    if not 60 <= args.ttl <= 900:
        parser.error("--ttl must be between 60 and 900 seconds")
    if args.trace is not None and not args.serve:
        parser.error("--trace is allowed only with --serve")
    try:
        Gio, GLib = gi_modules()
        conn = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        reader = BluezReader(conn, Gio, GLib)
        actual = reader.power()
        if args.check:
            print(json.dumps({"schema": 1, "bluez_adapter_present": actual is not None,
                              "powered": actual, "python_gi": True,
                              "changes": False}))
            return 0 if actual is not None else 2
        if actual is None:
            return 2
        trace = TraceRecorder(args.trace) if args.trace is not None else None
        ShortLivedBridge(Gio, GLib, reader, trace=trace).serve(args.ttl)
        return 0
    except (ImportError, RuntimeError, OSError) as exc:
        if args.check:
            print(json.dumps({"schema": 1, "python_gi": False,
                              "bluez_adapter_present": False,
                              "error_type": type(exc).__name__, "changes": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
