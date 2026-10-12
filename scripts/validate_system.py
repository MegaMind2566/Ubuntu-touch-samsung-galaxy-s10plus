#!/usr/bin/env python3
"""Check filesystem contents, CPU architecture and expanded partition bounds."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sparse_bytes(path):
    with Path(path).open("rb") as stream:
        header = stream.read(28)
        require(len(header) == 28, "Truncated Android sparse header")
        magic, major, minor, header_size, chunk_size, block_size, blocks, chunks, crc = struct.unpack("<I4H4I", header)
        require(magic == 0xED26FF3A and major == 1 and header_size == 28 and chunk_size == 12,
                "Invalid Android sparse image header")
        require(block_size > 0 and block_size % 4096 == 0 and blocks > 0 and chunks > 0, "Invalid sparse image dimensions")
        total_blocks = 0
        file_bytes = Path(path).stat().st_size
        for index in range(chunks):
            chunk = stream.read(12)
            require(len(chunk) == 12, "Truncated sparse chunk header")
            kind, reserved, count, physical = struct.unpack("<2H2I", chunk)
            if kind == 0xCAC1:  # RAW
                payload = count * block_size
            elif kind in (0xCAC2, 0xCAC4):  # FILL or CRC32
                payload = 4
            elif kind == 0xCAC3:  # DONT_CARE: occupies expanded blocks, no payload
                payload = 0
            else:
                raise ValueError("Unknown sparse chunk type")
            require(physical == 12 + payload, "Sparse chunk physical size mismatch")
            require(kind != 0xCAC4 or count == 0, "CRC chunk must not allocate blocks")
            total_blocks += count
            require(total_blocks <= blocks and stream.tell() + payload <= file_bytes, "Truncated or oversized sparse chunk")
            stream.seek(payload, 1)
        require(total_blocks == blocks and stream.tell() == file_bytes, "Sparse image block count or trailing bytes mismatch")
        return block_size * blocks


def image_read(image, path):
    result = subprocess.run(["debugfs", "-R", "cat " + path, str(image)], capture_output=True, check=True)
    require(b"File not found" not in result.stderr and b"not a directory" not in result.stderr,
            "Missing filesystem path: " + path)
    return result.stdout


def elf_arm64(contents):
    return len(contents) >= 20 and contents[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", contents, 18)[0] == 183


def validate(out):
    lock = json.loads((ROOT / "docs/assembly-inputs-2026-10-12.json").read_text())
    profile = json.loads((ROOT / "docs/device-check-2026-10-12.json").read_text())
    raw = out / "rootfs.img"
    size = raw.stat().st_size
    require(size == lock["system_image_bytes"] and size <= profile["partitions"]["system"]["bytes"],
            "Raw system image exceeds the verified bounds")
    expanded = sparse_bytes(out / "system.img")
    require(expanded == size, "Sparse system expanded size differs from the raw filesystem")
    subprocess.run(["e2fsck", "-f", "-n", str(raw)], check=True)
    header = subprocess.run(["dumpe2fs", "-h", str(raw)], text=True, capture_output=True, check=True).stdout

    def number(name):
        found = re.search(r"^" + re.escape(name) + r":\s*(\d+)\s*$", header, re.M)
        require(found is not None, "Missing ext4 dimension: " + name)
        return int(found[1])

    block_bytes = number("Block size")
    require(number("Block count") * block_bytes == size, "Ext4 geometry differs from the image file")
    free_bytes = number("Free blocks") * block_bytes
    require(free_bytes >= 256 * 1024 * 1024, "Insufficient free system filesystem space")
    release = image_read(raw, "/usr/lib/os-release").decode()
    require('VERSION_ID="24.04"' in release and "VARIANT_ID=touch" in release, "Not an Ubuntu Touch 24.04 rootfs")
    require(elf_arm64(image_read(raw, "/usr/bin/dpkg")), "Ubuntu userspace is not ARM64")
    info = image_read(raw, "/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml")
    require(b"beyond2lte" in info, "Missing S10+ overlay-store DeviceInfo")
    image_read(raw, "/opt/halium-overlay/lib/modules/.halium-override-dir")

    # Check the embedded Halium filesystem independently; matching stock vendor
    # still requires a hardware test and is never inferred from this result.
    with tempfile.TemporaryDirectory() as temporary:
        android = Path(temporary) / "android-rootfs.img"
        result = subprocess.run(["debugfs", "-R", "dump /var/lib/lxc/android/android-rootfs.img " + str(android), str(raw)],
                                capture_output=True, check=True)
        require(android.is_file() and android.stat().st_size > 0, "Missing embedded Halium image")
        subprocess.run(["e2fsck", "-f", "-n", str(android)], check=True)
        buildprop = image_read(android, "/system/build.prop").decode()
        require(re.search(r"^ro.build.version.release=12\s*$", buildprop, re.M), "Embedded Halium is not Android 12")
        require(re.search(r"^ro.build.version.sdk=3[12]\s*$", buildprop, re.M), "Embedded Halium API does not match Android 12")
    boot = out / "boot.img"
    require(boot.stat().st_size <= profile["partitions"]["boot"]["bytes"], "Boot exceeds the actual handset partition")
    require(hashlib.sha256(boot.read_bytes()).hexdigest() == lock["adaptation"]["sha256"]["boot.img"],
            "Assembled boot differs from the verified adaptation")
    report = {
        "structure_valid": True, "rootfs_assembled": True,
        "ubuntu_touch_release_target": "24.04-2.x", "architecture": "arm64", "halium": "12",
        "system_raw_bytes": size, "system_sparse_expanded_bytes": expanded,
        "system_partition_bytes": profile["partitions"]["system"]["bytes"],
        "system_partition_remaining_bytes": profile["partitions"]["system"]["bytes"] - size,
        "filesystem_free_bytes": free_bytes, "boot_bytes": boot.stat().st_size,
        "boot_partition_remaining_bytes": profile["partitions"]["boot"]["bytes"] - boot.stat().st_size,
        "filesystem_check_passed": True, "hardware_tested": False,
        "vendor_bundled": False, "vendor_runtime_compatibility_verified": False,
        "install_ready": False, "official_device_update_channel": False,
        "limitations": ["No Ubuntu Touch boot on hardware", "Stock Samsung vendor runtime not verified",
                        "Stock boot/recovery layout and installation/recovery route not verified"],
    }
    (out / "system-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
