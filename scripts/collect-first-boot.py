"""Read-only, USB-only first-boot evidence from the verified S10+ TWRP.

No phone files are created, no partition is mounted or written, and no reboot
is requested. Previous-boot logs are read before the image metadata checks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

LOG_BYTES = 524288
MAX_PSTORE_FILES = 16
ADB_HASHES = {
    "adb.exe": "b4a6b455702684652cccf7b46258b29e653538904359a58fd4931cf3ef286b3f",
    "AdbWinApi.dll": "c1d653030b4bde65d3e07e4d0b0979e17be56df1436cdd15528630f27808050d",
    "AdbWinUsbApi.dll": "0710e894d9b40f71a670c13c694079d564c92c1279da382cfe4850983aaebe1b",
    "libwinpthread-1.dll": "f2044c755e39efc5d47f47c5a942178dd6d79dc8945bb182dc8753d10e2a4269",
}
PYTHON_HASH = "7ca24f26d6e3f463419ee4f537ddd3acd312c38fe45e678cce08572f26a8bd1a"
PROPERTIES = ("ro.twrp.version", "ro.product.model", "ro.product.device",
              "ro.hardware", "ro.bootloader", "ro.boot.bootloader",
              "ro.boot.verifiedbootstate", "ro.boot.vbmeta.device_state")
BB = "/sbin/busybox "
QUERIES = {
    "version": ["version"],
    "state": ["-d", "get-state"],
    "uid": ["-d", "shell", "id -u"],
    "properties": ["-d", "shell", "for k in " + " ".join(PROPERTIES)
                   + '; do printf "%s|%s\\n" "$k" "$(getprop "$k")"; done'],
    "last-kmsg": ["-d", "shell", BB + "tail -c524288 /proc/last_kmsg"],
    "last-kmsg-start": ["-d", "shell", BB + "head -c65536 /proc/last_kmsg"],
    "pstore-list": ["-d", "shell", 'for p in /sys/fs/pstore/*; do '
                    '[ ! -f "$p" ] || printf "%s\\n" "${p##*/}"; done'],
    "recovery-kernel": ["-d", "shell", BB + "uname -a"],
    "recovery-dmesg": ["-d", "shell", BB + "dmesg | " + BB + "tail -c524288"],
    "recovery-cmdline": ["-d", "shell", BB + "head -c32768 /proc/cmdline"],
    "mounts": ["-d", "shell", BB + "head -c65536 /proc/mounts"],
    "reset-reason": ["-d", "shell", BB + "head -c4096 /proc/reset_reason"],
    "boot-hash": ["-d", "shell", BB + "head -c53215232 /dev/block/sda14 | " + BB + "sha256sum"],
    "recovery-hash": ["-d", "shell", BB + "head -c57556992 /dev/block/sda15 | " + BB + "sha256sum"],
    "vbmeta-hash": ["-d", "shell", BB + "head -c65536 /dev/block/sda23 | " + BB + "sha256sum"],
    "system-magic": ["-d", "shell", BB + "hexdump -v -s1080 -n2 -e '1/1 \"%02x\"' /dev/block/sda25"],
    "vendor-size": ["-d", "shell", BB + "blockdev --getsize64 /dev/block/sda26"],
    "vendor-magic": ["-d", "shell", BB + "hexdump -v -s1080 -n2 -e '1/1 \"%02x\"' /dev/block/sda26"],
    "vendor-fsck": ["-d", "shell", "/sbin/e2fsck -f -n /dev/block/sda26"],
}
EXPECTED_HASHES = {
    "boot-hash": "0992a55b228b97119139a845d9bd51821598fdb0fd18b4b823931f7f4ac8f0fc",
    "recovery-hash": "caecf1ef6c36392739377cfbe7d0c9ce37b255858e6dfd1a5cde2cad7a508b0e",
    "vbmeta-hash": "9cce7c2d752df367292cc17b4e2d21834629360f40521cb1784233b87e3c0025",
}
PSTORE_NAME = re.compile(r"(?:console|dmesg)-ramoops(?:-[0-9]+)?(?:\.enc\.z)?\Z")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
        return result.hexdigest()


def redact(text: str, root: Path) -> str:
    text = text.replace(str(root), "<pc-folder>")
    text = re.sub(r"(?i)((?:androidboot\.)?(?:serialno|serial_number|serial|imei|imsi|meid|did|chip_id|chipid)\s*[=:]\s*)[^\s,;]+",
                  r"\1<redacted>", text)
    text = re.sub(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", text)
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "<mac>", text)
    text = re.sub(r"(?<!\d)\d{15,16}(?!\d)", "<identifier>", text)
    return text


def command_for(query: str) -> list[str]:
    if query in QUERIES:
        return list(QUERIES[query])
    if query.startswith("pstore:") and PSTORE_NAME.fullmatch(query[7:]):
        return ["-d", "shell", BB + "tail -c524288 /sys/fs/pstore/" + query[7:]]
    raise ValueError("query_not_allowed")


def run_query(executable: Path, query: str) -> dict:
    arguments = command_for(query)
    try:
        result = subprocess.run([str(executable), *arguments], capture_output=True,
                                timeout=180 if query == "vendor-fsck" else (90 if query.endswith("-hash") else 45),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if len(result.stdout) > LOG_BYTES + 4096 or len(result.stderr) > 65536:
            return {"exit_code": None, "timed_out": False, "stdout": "", "stderr": "output_limit"}
        return {"exit_code": result.returncode, "timed_out": False,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace")}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "timed_out": True, "stdout": "", "stderr": "read_timeout"}


def check_tools(root: Path) -> None:
    if sha256(Path(sys.executable)) != PYTHON_HASH:
        raise ValueError("portable_python_mismatch")
    for name, expected in ADB_HASHES.items():
        if sha256(root / "platform-tools" / name) != expected:
            raise ValueError("adb_package_mismatch")


def collect_install_evidence(root: Path) -> tuple[dict, dict[str, str]]:
    metadata: dict = {"available": False}
    files: dict[str, str] = {}
    candidates = sorted((p for p in root.glob("ubuntu-twrp-install-report*.zip")
                         if re.fullmatch(r"ubuntu-twrp-install-report(?:-[0-9]+)?\.zip", p.name)),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        source = candidates[0]
        try:
            if source.stat().st_size > 262144:
                raise ValueError("report_too_large")
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) != 1 or entries[0].filename != "ubuntu-twrp-install-report.json" or entries[0].file_size > 131072:
                    raise ValueError("report_shape_invalid")
                report = json.loads(archive.read(entries[0]))
            if not isinstance(report, dict) or report.get("route") != "root_twrp_adb":
                raise ValueError("report_route_invalid")
            files["installation-report.json"] = redact(json.dumps(report, indent=2), root)
            metadata = {"available": True, "source_filename": source.name,
                        "source_zip_sha256": sha256(source),
                        "success": report.get("success"),
                        "system_readback_verified": report.get("system_readback_verified"),
                        "boot_readback_verified": report.get("boot_readback_verified")}
        except (OSError, ValueError, zipfile.BadZipFile):
            metadata = {"available": False, "error": "local_install_report_invalid"}
    state = root / "ubuntu-twrp-run-state.json"
    try:
        if state.is_file() and state.stat().st_size <= 4096:
            data = json.loads(state.read_text(encoding="utf-8-sig"))
            metadata["checkpoint"] = {key: data.get(key) for key in ("write_started", "success")
                                      if isinstance(data.get(key), bool)}
    except (OSError, ValueError, AttributeError):
        metadata["checkpoint_error"] = "checkpoint_unreadable"
    return metadata, files


def collect(root: Path, runner=run_query, verifier=check_tools) -> tuple[dict, Path]:
    root = root.resolve()
    report = {"schema": 1, "collector_version": 1,
              "date_utc": datetime.now(timezone.utc).isoformat(), "target_model": "SM-G975F",
              "partition_writes": False, "mount_changes_requested": False,
              "data_format_requested": False, "reboot_requested": False, "adb_usb_only": True,
              "ubuntu_touch_boot_verified": False, "success": False, "error": None,
              "steps": [], "properties": {}, "image_checks": {}, "prior_boot_log_files": [],
              "log_tail_limit_bytes": LOG_BYTES,
              "note": "recovery-* files describe the current TWRP boot, not the Ubuntu attempt"}
    report["installation"], files = collect_install_evidence(root)
    exe = root / "platform-tools" / "adb.exe"
    reason = "local_tools_unavailable"

    def query(name: str) -> dict:
        command_for(name)
        value = runner(exe, name)
        report["steps"].append({"operation": name, "exit_code": value["exit_code"],
                                "timed_out": value["timed_out"],
                                "stderr": redact(value["stderr"][:4096], root)})
        return value

    def successful(value: dict) -> bool:
        return value["exit_code"] == 0 and not value["timed_out"]

    try:
        verifier(root)
        reason = "adb_version_mismatch"
        result = query("version")
        if not successful(result) or "Version 37.0.1" not in result["stdout"]:
            raise ValueError(reason)
        reason = "twrp_usb_unavailable"
        result = query("state")
        if not successful(result) or result["stdout"].strip() not in ("device", "recovery"):
            raise ValueError(reason)
        reason = "recovery_not_root"
        result = query("uid")
        if not successful(result) or result["stdout"].strip() != "0":
            raise ValueError(reason)
        reason = "recovery_device_unconfirmed"
        result = query("properties")
        if not successful(result):
            raise ValueError(reason)
        props = {}
        for line in result["stdout"].splitlines():
            key, separator, value = line.partition("|")
            if separator and key in PROPERTIES and len(value) <= 256:
                props[key] = redact(value, root)
        report["properties"] = props
        if (props.get("ro.product.device") not in ("beyond2", "beyond2lte")
                or props.get("ro.hardware") != "exynos9820"
                or props.get("ro.twrp.version") not in ("3.7.0_9", "3.7.0_9-2")
                or "G975FXXSGHWC1" not in (props.get("ro.bootloader"), props.get("ro.boot.bootloader"))):
            raise ValueError(reason)
        report["recovery_confirmed"] = True
        print("Lettura dei log del precedente avvio...", flush=True)
        result = query("last-kmsg")
        if successful(result) and result["stdout"].strip():
            files["previous-boot-last-kmsg.txt"] = redact(result["stdout"], root)
            report["prior_boot_log_files"].append("previous-boot-last-kmsg.txt")
        result = query("last-kmsg-start")
        if successful(result) and result["stdout"].strip():
            files["previous-boot-last-kmsg-start.txt"] = redact(result["stdout"], root)
            report["prior_boot_log_files"].append("previous-boot-last-kmsg-start.txt")
        result = query("pstore-list")
        if successful(result):
            names = sorted(set(n for n in result["stdout"].splitlines() if PSTORE_NAME.fullmatch(n)))
            report["pstore_logs_found"] = len(names)
            for name in names[:MAX_PSTORE_FILES]:
                value = query("pstore:" + name)
                if successful(value) and value["stdout"].strip():
                    filename = "previous-boot-pstore-" + name + ".txt"
                    files[filename] = redact(value["stdout"], root)
                    report["prior_boot_log_files"].append(filename)
        for name in ("reset-reason", "recovery-kernel", "recovery-cmdline", "mounts", "recovery-dmesg"):
            result = query(name)
            if successful(result):
                files[name + ".txt"] = redact(result["stdout"], root)
        print("Verifica in lettura di BOOT, RECOVERY e VBMETA...", flush=True)
        for name, expected in EXPECTED_HASHES.items():
            result = query(name)
            match = re.fullmatch(r"([0-9a-f]{64})\s+-?", result["stdout"].strip())
            digest = match[1] if successful(result) and match else None
            report["image_checks"][name] = {"sha256": digest, "matches_expected": digest == expected}
        result = query("system-magic")
        report["image_checks"]["system_ext4_magic_valid"] = successful(result) and result["stdout"].strip() == "53ef"
        print("Controllo del filesystem VENDOR in sola lettura...", flush=True)
        result = query("vendor-size")
        vendor_size_ok = successful(result) and result["stdout"].strip() == "1153433600"
        result = query("vendor-magic")
        vendor_magic_ok = successful(result) and result["stdout"].strip() == "53ef"
        report["vendor_checks"] = {"partition_size_matches": vendor_size_ok,
                                   "ext4_magic_valid": vendor_magic_ok,
                                   "stock_content_hash_verified": False,
                                   "fsck_read_only_requested": False}
        result = query("mounts")
        mount_lines = result["stdout"].splitlines()
        vendor_mounted = any(("sda26" in line.split()[0] or "vendor" in line.split()[0]
                              or line.split()[1] == "/vendor") for line in mount_lines if len(line.split()) >= 2)
        report["vendor_checks"]["mounted_in_recovery"] = vendor_mounted if successful(result) else None
        if successful(result) and not vendor_mounted and vendor_size_ok and vendor_magic_ok:
            report["vendor_checks"]["fsck_read_only_requested"] = True
            value = query("vendor-fsck")
            report["vendor_checks"]["fsck_exit_code"] = value["exit_code"]
            report["vendor_checks"]["fsck_timed_out"] = value["timed_out"]
            files["vendor-fsck-read-only.txt"] = redact(value["stdout"] + "\n" + value["stderr"], root)
        else:
            report["vendor_checks"]["fsck_skipped"] = "vendor_mounted_or_metadata_unavailable"
        report["vendor_checks"]["note"] = "Filesystem consistency only; no stock content comparison, no repair or journal replay."
        report["success"] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z_]+", str(error)) else reason
    zip_path = root / "ubuntu-first-boot-report.zip"
    index = 1
    while zip_path.exists():
        zip_path = root / ("ubuntu-first-boot-report-" + str(index) + ".zip")
        index += 1
    with zipfile.ZipFile(zip_path, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("first-boot-report.json", json.dumps(report, indent=2))
        for name, content in files.items():
            archive.writestr(name, content)
    return report, zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report, path = collect(args.root)
    except OSError:
        print("Impossibile creare il rapporto: usa la cartella originale estratta e scrivibile.")
        return 2
    if report["success"]:
        print("Raccolta completata. Il telefono resta in TWRP.")
        if not report["prior_boot_log_files"]:
            print("Log persistenti assenti o non leggibili: il rapporto lo registra.")
    else:
        print("Raccolta fermata: " + report["error"])
    print("Invia questo file: " + str(path))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
