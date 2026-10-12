#!/usr/bin/env python3
"""Validate a read-only S10+ inventory against an actual compiled boot image."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PARTITIONS = ("boot", "recovery", "system", "vendor", "userdata", "dtbo", "vbmeta")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def property_value(report, name):
    result = report.get("properties", {}).get(name, {})
    require(result.get("exit_code") == 0, f"Property was not read successfully: {name}")
    return result.get("text", "")


def inspect(report, boot_bytes):
    require(report.get("read_only") is True, "Inventory is not marked read-only")
    model = property_value(report, "ro.product.model")
    device = property_value(report, "ro.product.device")
    require(model in ("SM-G975F", "SM-G975F/DS") and device in ("beyond2", "beyond2lte"),
            "Inventory is not for the Exynos S10+ target")
    require(property_value(report, "ro.hardware") == "exynos9820" and
            property_value(report, "ro.board.platform") == "universal9820",
            "Inventory does not confirm Exynos 9820")
    require(property_value(report, "ro.build.version.release") == "12" and
            property_value(report, "ro.vendor.build.version.release") == "12",
            "Android and vendor must both be Android 12 for this Halium 12 build")
    require(property_value(report, "ro.build.version.sdk") in ("31", "32") and
            property_value(report, "ro.vendor.build.version.sdk") in ("31", "32"),
            "Android/vendor API does not match Halium 12")

    proc = report.get("proc_partitions", {})
    blocks = {}
    if proc.get("exit_code") == 0:
        for line in proc.get("text", "").splitlines():
            match = re.fullmatch(r"\s*\d+\s+\d+\s+(\d+)\s+([A-Za-z0-9_-]+)\s*", line)
            if match:
                require(match[2] not in blocks, f"Duplicate /proc/partitions device: {match[2]}")
                # Linux reports /proc/partitions in 1024-byte blocks, NOT sectors.
                blocks[match[2]] = int(match[1]) * 1024
    inventory = report.get("partitions", {})
    require(inventory.get("exit_code") == 0, "Partition labels were not read successfully")
    partitions = {}
    for line in inventory.get("text", "").splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        require(len(fields) == 4, "Malformed partition inventory line")
        label, path, sectors, logical = fields
        label = label.lower()
        require(label in PARTITIONS and label not in partitions, f"Unexpected/duplicate partition: {label}")
        require(re.fullmatch(r"/dev/block/[A-Za-z0-9_-]+", path), f"Unresolved block device: {path}")
        size_sys = None
        if sectors:
            require(sectors.isdecimal(), f"Invalid sector count: {label}")
            # /sys/class/block/*/size always uses 512-byte sectors.
            size_sys = int(sectors) * 512
        size_proc = blocks.get(Path(path).name)
        if size_sys is not None and size_proc is not None:
            require(size_sys == size_proc, f"Conflicting partition size readings: {label}")
        size = size_sys if size_sys is not None else size_proc
        require(size is not None and size > 0, f"No readable size for partition: {label}")
        require(not logical or logical.isdecimal(), f"Invalid logical block size: {label}")
        partitions[label] = {
            "block_device": path, "bytes": size,
            "size_source": "sysfs-512-byte-sectors" if size_sys is not None else "proc-partitions-1024-byte-blocks",
            "logical_block_bytes": int(logical) if logical else None,
        }
    require(all(name in partitions for name in PARTITIONS), "Missing required partition labels")
    require(isinstance(boot_bytes, int) and boot_bytes > 0, "Invalid boot image size")
    require(boot_bytes <= partitions["boot"]["bytes"], "Boot image exceeds the handset boot partition")

    def optional(name):
        result = report.get("properties", {}).get(name, {})
        return result.get("text") if result.get("exit_code") == 0 else None

    return {
        "inventory_valid": True,
        "captured_utc": report.get("captured_utc"),
        "model": model, "stock_device_name": device, "port_codename": "beyond2lte",
        "hardware": "exynos9820", "android_version": "12", "vendor_version": "12",
        "firmware_build": optional("ro.build.display.id"),
        "bootloader_build": optional("ro.boot.bootloader"),
        "vendor_fingerprint": optional("ro.vendor.build.fingerprint"),
        "bootloader_locked": optional("ro.boot.flash.locked") == "1" and optional("ro.boot.vbmeta.device_state") == "locked",
        "verified_boot_state_reported": optional("ro.boot.verifiedbootstate"),
        "knox_warranty_bit_reported": optional("ro.boot.warranty_bit"),
        "partitions": partitions,
        "boot_image": {"bytes": boot_bytes, "fits": True, "remaining_bytes": partitions["boot"]["bytes"] - boot_bytes},
        "halium_vendor_major_matches": True,
        "vendor_runtime_compatibility_verified": False,
        "hardware_tested": False, "install_ready": False,
        "limitations": [
            "Android 12/API agreement does not establish Samsung vendor runtime compatibility",
            "Stock boot/recovery headers and Samsung installation route are not verified",
            "No Ubuntu Touch boot or hardware test has been performed",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--boot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    result = inspect(json.loads(raw.decode("utf-8-sig")), args.boot.stat().st_size)
    result["source_report_sha256"] = hashlib.sha256(raw).hexdigest()
    result["boot_image"]["sha256"] = hashlib.sha256(args.boot.read_bytes()).hexdigest()
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
