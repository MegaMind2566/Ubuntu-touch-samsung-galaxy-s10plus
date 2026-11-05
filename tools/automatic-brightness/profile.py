#!/usr/bin/env python3
"""Install/restore only the pinned repowerd profile; no service or display writes."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
TARGET = Path("usr/share/repowerd/device-configs/config-beyond2lte.xml")
STATE = Path("userdata/ut-s10-automatic-brightness/state.json")
DEVICEINFO = Path("etc/deviceinfo/devices/beyond2lte.yaml")
KERNEL = "4.14.280-gb9b70b29c94c-dirty"
ROOT_UID = 0


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded_read(path, limit=16384):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError(f"regular file required: {path.name}")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"file too large: {path.name}")
    return data


def safe_path(root, relative):
    path = root
    if path.is_symlink():
        raise ValueError("symlink root")
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"symlink path: {relative}")
    return path


def ownership_info(path):
    return path.lstat()


def require_trusted(path, *, mode=None, directory=False):
    info = ownership_info(path)
    if info.st_uid != ROOT_UID:
        raise ValueError(f"root ownership required: {path.name}")
    predicate = stat.S_ISDIR if directory else stat.S_ISREG
    if not predicate(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o022:
        raise ValueError(f"unsafe type/permissions: {path.name}")
    if mode is not None and stat.S_IMODE(info.st_mode) != mode:
        raise ValueError(f"private mode {mode:04o} required: {path.name}")


def validate_layout(root):
    for relative in (TARGET, STATE):
        current = root
        require_trusted(current, directory=True)
        for part in relative.parent.parts:
            current /= part
            if current.exists():
                private = current == root / STATE.parent
                require_trusted(current, directory=True, mode=0o700 if private else None)
        path = safe_path(root, relative)
        if path.exists():
            require_trusted(path, mode=0o600 if relative == STATE else None)


def check_context(root, uid=None, release=None):
    uid = getattr(os, "geteuid", lambda: -1)() if uid is None else uid
    if uid != 0:
        raise ValueError("root required")
    if (platform.release() if release is None else release) != KERNEL:
        raise ValueError("kernel release mismatch")
    text = bounded_read(safe_path(root, Path("etc/os-release"))).decode()
    values = dict(re.findall(r'^([A-Z_]+)=[\'"]?([^\n\'"]*)[\'"]?$', text, re.M))
    if (values.get("ID") != "ubuntu" or values.get("VERSION_ID") != "24.04"
            or values.get("VARIANT_ID") != "touch"):
        raise ValueError("Ubuntu Touch 24.04 baseline required")
    device = bounded_read(safe_path(root, DEVICEINFO)).decode()
    if not re.search(r"(?m)^\s*Names:\s*(?:\[\s*beyond2\s*\]|\n\s*-\s*beyond2\s*$)", device):
        raise ValueError("deviceinfo beyond2 alias mismatch")


def load_profile():
    metadata = json.loads(bounded_read(HERE / "manifest.json").decode())
    data = bounded_read(HERE / "config-beyond2lte.xml")
    if digest(data) != metadata["profile_sha256"]:
        raise ValueError("profile hash mismatch")
    root = ET.fromstring(data)
    fields = {node.attrib.get("name"): node for node in root}
    required = {"config_automatic_brightness_available", "config_autoBrightnessLevels",
                "config_autoBrightnessLcdBacklightValues"}
    if root.tag != "resources" or set(fields) != required or len(root) != 3:
        raise ValueError("unexpected profile fields")
    if fields["config_automatic_brightness_available"].text.strip() != "true":
        raise ValueError("automatic brightness flag missing")
    levels = [int(node.text) for node in fields["config_autoBrightnessLevels"]]
    values = [int(node.text) for node in fields["config_autoBrightnessLcdBacklightValues"]]
    if levels != metadata["levels"] or values != metadata["values"]:
        raise ValueError("profile differs from pinned original tables")
    if (len(values) != len(levels) + 1 or len(values) > 255 or levels[0] <= 0
            or any(a >= b for a, b in zip(levels, levels[1:]))
            or any(a > b for a, b in zip(values, values[1:]))
            or not all(0 <= value <= 255 for value in values)):
        raise ValueError("invalid spline range/order")
    return data


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".s10-profile-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
        if os.name == "posix":
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_state(path, expected):
    value = json.loads(bounded_read(path, 65536))
    if (not isinstance(value, dict) or value.get("schema") != 1
            or value.get("installed_sha256") != expected
            or set(value) != {"schema", "installed_sha256", "previous", "mode", "uid", "gid"}):
        raise ValueError("invalid saved profile state")
    previous = value["previous"]
    if previous is not None:
        if not isinstance(previous, str):
            raise ValueError("invalid previous profile")
        value["bytes"] = base64.b64decode(previous, validate=True)
        if len(value["bytes"]) > 16384:
            raise ValueError("previous profile too large")
    else:
        value["bytes"] = None
    for key in ("mode", "uid", "gid"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError("invalid saved ownership")
    if value["uid"] != ROOT_UID or value["gid"] >= 2**32 - 1:
        raise ValueError("invalid saved ownership range")
    if value["mode"] > 0o777 or value["mode"] & 0o022:
        raise ValueError("invalid saved mode")
    return value


def install(root):
    check_context(root)
    validate_layout(root)
    data = load_profile()
    target, state = safe_path(root, TARGET), safe_path(root, STATE)
    current = bounded_read(target) if target.exists() else None
    if state.exists():
        saved = read_state(state, digest(data))
        if current == data:
            return {"installed": True, "changed": False, "activated": False}
        if current != saved["bytes"]:
            raise ValueError("profile changed after saved state")
    else:
        info = ownership_info(target) if current is not None else None
        if info and stat.S_IMODE(info.st_mode) & 0o7000:
            raise ValueError("special mode on existing profile")
        saved = {"schema": 1, "installed_sha256": digest(data),
                 "previous": base64.b64encode(current).decode() if current is not None else None,
                 "mode": stat.S_IMODE(info.st_mode) & 0o777 if info else 0o644,
                 "uid": info.st_uid if info else 0, "gid": info.st_gid if info else 0}
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        validate_layout(root)
        atomic_write(state, (json.dumps(saved, sort_keys=True) + "\n").encode(), 0o600)
    atomic_write(target, data)
    return {"installed": True, "changed": True, "activated": False}


def rollback(root):
    check_context(root)
    validate_layout(root)
    target, state = safe_path(root, TARGET), safe_path(root, STATE)
    saved = read_state(state, digest(load_profile()))
    current = bounded_read(target) if target.exists() else None
    if current != load_profile() and current != saved["bytes"]:
        raise ValueError("profile changed; refusing rollback overwrite")
    if saved["bytes"] is None:
        if target.exists():
            target.unlink()
    else:
        atomic_write(target, saved["bytes"], saved["mode"])
        if hasattr(os, "chown"):
            os.chown(target, saved["uid"], saved["gid"])
    state.unlink()
    return {"restored": True, "activated": False}


def status(root):
    target = safe_path(root, TARGET)
    current = bounded_read(target) if target.exists() else None
    return {"profile_matches": current == load_profile(),
            "state_present": safe_path(root, STATE).is_file(), "activated": "unknown"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    for name in ("install", "rollback", "status"):
        action.add_argument("--" + name, action="store_true")
    parser.add_argument("--root", type=Path, default=Path("/"), help="alternate filesystem for read-only status")
    args = parser.parse_args()
    try:
        if not args.status and args.root != Path("/"):
            raise ValueError("alternate root is read-only")
        operation = status if args.status else install if args.install else rollback
        print(json.dumps(operation(args.root), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        print(f"profile: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
