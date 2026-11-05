#!/usr/bin/python3
"""Pinned S10+ audio service guards. No HAL calls or privileged mutations.

Pins: handset audio5 (2026-10-22), libhybris 7079712a42ea2754adf747e70c6cc75764c8596e.
PrivateUsers/BindReadOnlyPaths contract: systemd v255 exec-invoke.c/namespace.c.
Only prepare writes, exclusively to the caller's supplied staging directory.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import stat
import subprocess
import sys

UID = GID = 32011
KERNEL = "4.14.280-gb9b70b29c94c-dirty"
CONFIG = "/linkerconfig/ld.config.txt"
CONFIG_SHA = "68cc3bb5f38bae62f3a92d8aa6faaca11db3cef9e16f4616a91fcf5f65bf257d"
PATCHED_SHA = "263536ad3c05a13b9bfb9f711e3558c2a21d36ff081493be55c994bafeaba27c"
VENDOR_SHA = "75f8c91e6045e6590c3432c69eeac611ce5e8cb6383e6d6c0982a8c02f6639cb"
WRAPPER_SHA = "e1590613740e6fba5b9ddec3d0c968b81cba82099edb73f92b5a0980f3d66a4c"
HAL_SHA = "610fae95e7a3d7f546edc41e1165abca0c597c047397e5fabb4cb13ba1741ded"
VENDORS = tuple(p + "/lib64/hw/audio.primary.default.so" for p in ("/android/vendor", "/vendor"))
WRAPPERS = tuple(p + "/lib64/hw/audio.hidl_compat.default.so" for p in ("/android/system", "/system"))
HALS = tuple(p + "/lib64/libaudiohal.so" for p in ("/android/system", "/system"))
HOST_PINS = {CONFIG: CONFIG_SHA, **dict.fromkeys(VENDORS, VENDOR_SHA),
             **dict.fromkeys(WRAPPERS, WRAPPER_SHA), **dict.fromkeys(HALS, HAL_SHA)}
INSIDE_PINS = {**HOST_PINS, CONFIG: PATCHED_SHA, **dict.fromkeys(VENDORS, WRAPPER_SHA)}
MARKER = "UT_AUDIO_GUARD "
MAX_FILE = 16 * 1024 * 1024


class GuardError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GuardError(message)


def ns_valid(value, kind):
    return isinstance(value, str) and re.fullmatch(kind + r":\[[0-9]+\]", value) is not None


def context():
    result = dict(uid=os.getuid(), gid=os.getgid(), euid=os.geteuid(), egid=os.getegid(),
                  kernel=platform.release(), mount_ns=os.readlink("/proc/self/ns/mnt"),
                  user_ns=os.readlink("/proc/self/ns/user"))
    require(result["uid"] == result["euid"] == UID and result["gid"] == result["egid"] == GID,
            "UID/GID inattesi; eseguire come phablet senza sudo")
    require(result["kernel"] == KERNEL, "Kernel diverso dalla prova audio5")
    require(ns_valid(result["mount_ns"], "mnt") and ns_valid(result["user_ns"], "user"),
            "Identita namespace non leggibile")
    return result


def file_bytes(path, root_owned=False):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_FILE,
                "File non regolare o eccessivo: " + str(path))
        if root_owned:
            require(info.st_uid == 0 and not info.st_mode & 0o022,
                    "File host non root-owned/protetto: " + str(path))
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_FILE + 1)
        require(len(data) <= MAX_FILE, "File cresciuto oltre limite: " + str(path))
        after = os.fstat(fd)
        require((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "File cambiato durante lettura")
        return data
    finally:
        os.close(fd)


def check_files(pins, root_owned=False):
    result = {}
    for path, expected in pins.items():
        actual = hashlib.sha256(file_bytes(path, root_owned)).hexdigest()
        require(actual == expected, "SHA256 inatteso: " + str(path))
        result[path] = actual
    return result


def payload_info(path, root_owned=False):
    require(os.path.isabs(path), "Il percorso payload deve essere assoluto")
    check_files({path: PATCHED_SHA}, root_owned)
    return dict(path=os.path.realpath(path), sha256=PATCHED_SHA)


def host_check(payload=None):
    result = context()
    # The Android-generated /linkerconfig file need not have UID 0 or a
    # conventional immutable mode in the host view. The audio5 evidence pins
    # exact bytes, not an owner/mode contract. Require the original files to
    # be regular, non-symlinks, stable during reading and hash-identical.
    # Our *installed* payload, on the other hand, must still be root-owned.
    result["hashes"] = check_files(HOST_PINS)
    if payload is not None:
        result["payload"] = payload_info(payload, root_owned=True)
    return result


def patch_config(text):
    require(len(text) <= 1048576 and "\0" not in text, "Configurazione non testuale/eccessiva")
    section, sections, entries, mappings = None, [], {}, []
    lines = text.splitlines(keepends=True)
    for index, raw in enumerate(lines):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            require(re.fullmatch(r"\[[A-Za-z0-9_.-]+\]", line), "Sezione linker non riconosciuta")
            section = line[1:-1]; sections.append(section)
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*(\+?=)\s*(.*)", line)
        require(match, "Riga linker non riconosciuta")
        key, op, value = match.groups()
        if section is None and key.startswith("dir."):
            mappings.append((key[4:], value))
        if section == "vendor":
            entries.setdefault(key, []).append((index, op, value))
    require(sections.count("vendor") == 1, "Profilo vendor mancante o duplicato")
    profiles = {name for name, directory in mappings if directory.startswith("/") and
                ("/vendor/bin/yes" == directory.rstrip("/") or
                 "/vendor/bin/yes".startswith(directory.rstrip("/") + "/"))}
    require(profiles == {"vendor"}, "Mappatura vendor non univoca")

    def values(key, delimiter):
        rows = entries.get(key, [])
        require(rows and rows[0][1] == "=" and sum(op == "=" for _, op, _ in rows) == 1,
                "Proprieta mancante/ambigua: " + key)
        return [v.strip() for _, _, row in rows for v in row.split(delimiter) if v.strip()]

    links = values("namespace.default.links", ",")
    require(len(links) == len(set(links)) and "system" in links, "Link system assente/duplicato")
    require(not any(k.startswith("namespace.sphal.") for k in entries), "Namespace sphal inatteso")
    require(not any(v == "true" for _, _, v in entries.get(
        "namespace.default.link.system.allow_all_shared_libs", [])), "System gia interamente condiviso")
    require("libaudiohal.so" not in values("namespace.default.link.system.shared_libs", ":"),
            "libaudiohal gia condivisa")
    require(any(p.replace("${LIB}", "lib64").rstrip("/") == "/system/lib64"
                for p in values("namespace.system.search.paths", ":")), "Ricerca system inattesa")
    last = entries["namespace.default.link.system.shared_libs"][-1][0]
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    lines.insert(last + 1, "namespace.default.link.system.shared_libs += libaudiohal.so\n")
    return "".join(lines)


def prepare(destination):
    result = host_check()
    patched = patch_config(file_bytes(CONFIG).decode("ascii")).encode("ascii")
    require(hashlib.sha256(patched).hexdigest() == PATCHED_SHA, "Patch diversa dalla prova audio5")
    require(os.path.isabs(destination), "DEST deve essere assoluto ed esistere")
    directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(directory)
        require(info.st_uid == UID and not info.st_mode & 0o022, "Stage non posseduto/protetto da phablet")
        fd = os.open("ld.config.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o644, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(patched); stream.flush(); os.fsync(fd)
            os.fchmod(fd, 0o644)
        except BaseException:
            os.unlink("ld.config.txt", dir_fd=directory)
            raise
        finally:
            os.close(fd)
    finally:
        os.close(directory)
    result["payload"] = payload_info(os.path.join(destination, "ld.config.txt"))
    return result


def parse_mountinfo(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) >= 10 and "-" in fields[6:], "mountinfo non valido")
        mount_id = fields[0]
        require(mount_id.isdigit() and mount_id not in result, "ID mount ambiguo")
        path = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])
        result[mount_id] = (path, set(fields[5].split(",")))
    return result


def readonly_mount(path, mounts):
    canonical = os.path.realpath(path)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        fdinfo = Path("/proc/self/fdinfo/" + str(fd)).read_text()
        ids = re.findall(r"^mnt_id:\s*([0-9]+)$", fdinfo, re.MULTILINE)
        require(len(ids) == 1 and ids[0] in mounts, "Mount del file non identificabile: " + path)
        mountpoint, options = mounts[ids[0]]
        require(mountpoint == canonical and "ro" in options, "Bind non puntuale/read-only: " + path)
        return dict(path=path, realpath=canonical, mount_id=ids[0], read_only=True)
    finally:
        os.close(fd)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Chiave JSON duplicata: " + key)
        result[key] = value
    return result


def parse_host_result(stdout, payload):
    require(isinstance(stdout, str) and len(stdout) <= 65536, "Output host assente/eccessivo")
    lines = stdout.splitlines()
    require(len(lines) == 1 and lines[0].startswith(MARKER), "Output host non univoco")
    try:
        data = json.loads(lines[0][len(MARKER):], object_pairs_hook=unique_object)
    except (TypeError, ValueError) as exc:
        raise GuardError("JSON host non valido") from exc
    require(isinstance(data, dict) and data.get("mode") == "host-check" and data.get("ok") is True,
            "Host check non riuscito")
    require(all(type(data.get(k)) is int and data[k] == n for k, n in
                (("uid", UID), ("euid", UID), ("gid", GID), ("egid", GID))), "Identita host inattesa")
    require(data.get("kernel") == KERNEL and data.get("hashes") == HOST_PINS, "Pin host inattesi")
    require(ns_valid(data.get("mount_ns"), "mnt") and ns_valid(data.get("user_ns"), "user"),
            "Namespace host non validi")
    require(data.get("payload") == dict(path=os.path.realpath(payload), sha256=PATCHED_SHA),
            "Payload host inatteso")
    return data


def nested_host_check(payload):
    unit = "ut-audio-host-check-%s-%s.service" % (os.getpid(), secrets.token_hex(8))
    command = ["/usr/bin/systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet",
               "--unit=" + unit, "--property=Type=exec", "--property=PrivateUsers=no",
               "--property=PrivateMounts=no", "--property=Restart=no",
               "--property=TimeoutStartSec=10s", "--property=RuntimeMaxSec=10s",
               "--property=TimeoutStopSec=2s", "--property=KillMode=control-group",
               "/usr/bin/python3", os.path.realpath(__file__), "host-check", payload]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, timeout=15, check=False)
    if completed.returncode != 0:
        detail = completed.stderr[-500:].strip()
        if completed.stdout.startswith(MARKER) and len(completed.stdout) <= 65536:
            try:
                failed = json.loads(completed.stdout[len(MARKER):], object_pairs_hook=unique_object)
                if isinstance(failed, dict) and failed.get("ok") is False and isinstance(failed.get("error"), str):
                    detail = failed["error"][:500]
            except (ValueError, GuardError):
                pass
        raise GuardError("Host check manager fallito rc=%s: %s" % (completed.returncode, detail))
    return parse_host_result(completed.stdout, payload)


def inside_check(payload, expected_mount=None, expected_user=None):
    result = context()
    result["payload"] = payload_info(payload)
    result["hashes"] = check_files(INSIDE_PINS)
    mounts = parse_mountinfo(Path("/proc/self/mountinfo").read_text())
    result["binds"] = [readonly_mount(path, mounts) for path in (CONFIG, *VENDORS)]
    result["device_open"] = {}
    for path in ("/dev/hwbinder", "/dev/ion"):
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            require(stat.S_ISCHR(os.fstat(fd).st_mode), "Nodo hardware non character device: " + path)
        finally:
            os.close(fd)
        result["device_open"][path] = True
    host = nested_host_check(payload)
    require(host["mount_ns"] != result["mount_ns"] and host["user_ns"] != result["user_ns"],
            "Namespace privati non separati dalla vista manager")
    if expected_mount is not None or expected_user is not None:
        require(host["mount_ns"] == expected_mount and host["user_ns"] == expected_user,
                "Identita manager cambiata rispetto al preflight")
    result["host"] = host
    result["supplementary_groups_inside"] = os.getgroups()
    result["hal_function_tested"] = False
    return result


def main(argv):
    mode = argv[0] if argv else "invalid"
    result = dict(mode=mode, ok=False, uid=os.getuid(), gid=os.getgid())
    rc = 2
    try:
        if mode == "prepare" and len(argv) == 2:
            data = prepare(argv[1])
        elif mode == "host-check" and len(argv) in (1, 2):
            data = host_check(argv[1] if len(argv) == 2 else None)
        elif mode == "inside-check" and len(argv) == 4:
            require(ns_valid(argv[2], "mnt") and ns_valid(argv[3], "user"), "Namespace attesi non validi")
            data = inside_check(*argv[1:])
        elif mode == "start-check" and len(argv) == 2:
            data = inside_check(argv[1])
        else:
            raise GuardError("Uso: prepare DEST | host-check [PAYLOAD] | inside-check PAYLOAD MNT USER | start-check PAYLOAD")
        result.update(data, mode=mode, ok=True)
        rc = 0
    except KeyboardInterrupt:
        result["error"] = "Interrotto"; rc = 130
    except (GuardError, OSError, ValueError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
    print(MARKER + json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
