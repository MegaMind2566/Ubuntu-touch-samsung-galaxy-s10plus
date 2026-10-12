#!/usr/bin/env python3
"""Validate S10+ adaptation structure; this is not a hardware/flashability test."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(out):
    boot = (out / "boot.img").read_bytes()
    require(boot[:8] == b"ANDROID!", "Missing Android boot image magic")
    require(len(boot) >= 1648, "Truncated Android boot header")
    values = struct.unpack_from("<10I", boot, 8)
    ksize, kaddr, rsize, raddr, ssize, _, tags, page, version, _ = values
    require(page == 2048 and version == 1, "Unexpected S10+ boot page size/header version")
    require(kaddr == 0x10008000 and raddr == 0x11000000 and tags == 0x10000100,
            "Boot offsets differ from the pinned S10+ deviceinfo")
    require(ksize > 64 and rsize > 0 and ssize == 0, "Invalid kernel/ramdisk payload sizes")
    aligned = lambda size: ((size + page - 1) // page) * page
    kernel_offset = page
    ramdisk_offset = kernel_offset + aligned(ksize)
    require(ramdisk_offset + rsize <= len(boot), "Boot image payload is truncated")
    kernel = boot[kernel_offset:kernel_offset + ksize]
    require(kernel[56:60] == b"ARM\x64", "Kernel payload is not an ARM64 Linux Image")
    ramdisk = gzip.decompress(boot[ramdisk_offset:ramdisk_offset + rsize])
    require(ramdisk[:6] in (b"070701", b"070702"), "Ramdisk is not a gzip/newc archive")
    cmdline = boot[64:576].split(b"\0", 1)[0] + boot[608:1632].split(b"\0", 1)[0]
    require(b"systempart=/dev/disk/by-partlabel/system" in cmdline,
            "Boot image lacks the S10+ system partition selector")
    config = dict(line.split("=", 1) for line in (out / "kernel.config").read_text().splitlines()
                  if line.startswith("CONFIG_") and "=" in line)
    fragment = ROOT / "config/ubuntu-touch.config"
    for line in fragment.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            require(config.get(key) == value, f"Required kernel option not effective: {key}={value}")

    with tarfile.open(out / "device_beyond2lte.tar.xz", "r:xz") as tar:
        names = set(tar.getnames())
        require("partitions/boot.img" in names, "Device tarball contains no boot image")
        archived_boot = tar.extractfile("partitions/boot.img").read()
        require(archived_boot == boot, "Tarball and standalone boot.img differ")
        require("system/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml" in names,
                "Missing S10+ DeviceInfo in the overlay store")
        require("system/opt/halium-overlay/lib/modules/.halium-override-dir" in names,
                "Kernel module override directory marker is missing")
    report = {
        "structure_valid": True, "hardware_tested": False,
        "complete_installation_image": False,
        "boot_header_version": version, "page_size": page,
        "kernel_bytes": ksize, "ramdisk_bytes": rsize,
        "boot_bytes": len(boot), "cmdline": cmdline.decode(),
        "limitations": ["No on-device boot test", "No matching vendor bundled",
                        "Ubuntu Touch rootfs not assembled", "Actual partition sizes not verified"],
    }
    (out / "artifact-report.json").write_text(json.dumps(report, indent=2) + "\n")
    checked = ["boot.img", "device_beyond2lte.tar.xz", "kernel.config", "source-manifest.json"]
    (out / "SHA256SUMS").write_text("".join(
        hashlib.sha256((out / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in checked))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    print(json.dumps(validate(parser.parse_args().out), indent=2))
