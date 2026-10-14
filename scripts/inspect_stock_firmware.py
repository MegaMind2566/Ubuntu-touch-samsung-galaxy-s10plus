#!/usr/bin/env python3
"""Audit supplied Samsung stock images offline. Never accesses a handset."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
AVBTOOL_COMMIT = "b27a9aa53d2db7720e4d88d6950dcd979da97de3"
AVBTOOL_SHA256 = "1183d0d19467b24b064e59191e3040260ede45f2bacaa8aa44f47be460909bb5"
AVBTOOL_URL = ("https://raw.githubusercontent.com/AndroidBootloader/platform_external_avb/"
               + AVBTOOL_COMMIT + "/avbtool.py")
IMAGES = ("boot", "recovery", "dtbo", "vbmeta")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def aligned(size, page):
    return (size + page - 1) // page * page


def boot_header(data):
    require(len(data) >= 1648 and data[:8] == b"ANDROID!", "Invalid Android boot header")
    ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, version, osv = struct.unpack_from("<10I", data, 8)
    require(version == 1 and page == 2048, "Expected S10+ header v1 / 2048-byte pages")
    recovery_size, recovery_offset, header_size = struct.unpack_from("<IQI", data, 1632)
    require(header_size == 1648, "Invalid v1 header size")
    offsets = [page, page + aligned(ksize, page), page + aligned(ksize, page) + aligned(rsize, page)]
    sha1 = hashlib.sha1()
    for size, offset in zip((ksize, rsize, ssize), offsets):
        require(offset + size <= len(data), "Truncated boot payload")
        sha1.update(data[offset:offset + size])
        sha1.update(struct.pack("<I", size))
    if recovery_size:
        require(recovery_offset == offsets[2] + aligned(ssize, page), "Invalid recovery DTBO offset")
        require(recovery_offset + recovery_size <= len(data), "Truncated recovery DTBO")
    # Lineage's mkbootimg additionally hashes the legacy, empty --dt field.
    # The pinned Halium tools use that fork; Samsung uses the AOSP variant.
    legacy = sha1.copy()
    legacy.update(struct.pack("<I", 0))
    for checksum in (sha1, legacy):
        checksum.update(data[recovery_offset:recovery_offset + recovery_size])
        checksum.update(struct.pack("<I", recovery_size))
    variant = "aosp" if sha1.digest() == data[576:596] else "lineage-empty-legacy-dt"
    require(data[576:596] in (sha1.digest(), legacy.digest()), "Android boot ID checksum mismatch")
    kernel = data[page:page + ksize]
    require(len(kernel) >= 64 and kernel[56:60] == b"ARM\x64", "Expected ARM64 Linux Image")
    linux = re.search(rb"Linux version [ -~]+", kernel)
    packed_version, patch = osv >> 11, osv & 2047
    return {
        "header_version": version, "header_bytes": header_size, "page_bytes": page,
        "kernel_bytes": ksize, "kernel_address": kaddr,
        "ramdisk_bytes": rsize, "ramdisk_address": raddr,
        "ramdisk_offset": offsets[1], "second_bytes": ssize, "second_address": saddr,
        "tags_address": tags, "recovery_dtbo_bytes": recovery_size,
        "recovery_dtbo_offset": recovery_offset,
        "os_version": ".".join(str((packed_version >> n) & 127) for n in (14, 7, 0)),
        "security_patch": f"{2000 + (patch >> 4):04d}-{patch & 15:02d}",
        "cmdline": (data[64:576].split(b"\0", 1)[0] + data[608:1632].split(b"\0", 1)[0]).decode(),
        "kernel_version": linux.group().decode() if linux else None,
        "boot_id_sha1_valid": True, "boot_id_variant": variant,
    }


def newc_files(data):
    """Read names/content without extracting paths or following symlinks."""
    pos, files = 0, {}
    while pos + 110 <= len(data):
        require(data[pos:pos + 6] in (b"070701", b"070702"), "Invalid newc ramdisk")
        values = [int(data[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
        size, name_size = values[6], values[11]
        require(name_size > 0 and pos + 110 + name_size <= len(data), "Truncated newc name")
        raw_name = data[pos + 110:pos + 110 + name_size]
        require(raw_name[-1:] == b"\0", "Unterminated newc name")
        name = raw_name[:-1].decode()
        start = aligned(pos + 110 + name_size, 4)
        require(start + size <= len(data), "Truncated newc content")
        if name == "TRAILER!!!":
            return files
        require(name not in files, "Duplicate newc name")
        files[name] = data[start:start + size]
        pos = aligned(start + size, 4)
    raise ValueError("Missing newc trailer")


def recovery_ramdisk(data):
    decoder = zlib.decompressobj(31)
    raw = decoder.decompress(data, 128 * 1024 * 1024 + 1)
    require(decoder.eof and not decoder.unused_data and len(raw) <= 128 * 1024 * 1024,
            "Incomplete, trailing or oversized recovery gzip")
    return newc_files(raw)


def dtbo_table(data):
    require(len(data) >= 32, "Truncated DTBO header")
    magic, total, hsize, esize, count, offset, page, version = struct.unpack_from(">8I", data)
    require(magic == 0xD7B7AB1E and hsize == 32 and esize == 32 and version == 0,
            "Unsupported DTBO table")
    require(32 <= total <= len(data) and offset >= hsize and offset + count * esize <= total,
            "DTBO entries exceed table bounds")
    entries = []
    for i in range(count):
        size, start, ident, revision, *custom = struct.unpack_from(">8I", data, offset + i * esize)
        require(start >= offset + count * esize and size >= 40 and start + size <= total,
                "DTBO payload exceeds table bounds")
        fdt = data[start:start + size]
        require(fdt[:4] == b"\xd0\x0d\xfe\xed" and struct.unpack_from(">I", fdt, 4)[0] == size,
                "Invalid DTBO FDT payload")
        entries.append({"bytes": size, "offset": start, "id": ident, "revision": revision,
                        "custom": custom, "sha256": digest(fdt)})
    return {"table_bytes": total, "page_bytes": page, "version": version, "entries": entries}


def load_avbtool(path):
    require(digest(path.read_bytes()) == AVBTOOL_SHA256, "avbtool source checksum mismatch")
    spec = importlib.util.spec_from_file_location("stock_audit_avbtool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect_avb(path, module, images):
    raw = path.read_bytes()
    image = module.ImageHandler(str(path), read_only=True)
    try:
        footer, header, descriptors, _ = module.Avb()._parse_image(image)
    finally:
        image._image.close()
    offset = footer.vbmeta_offset if footer else 0
    size = 256 + header.authentication_data_block_size + header.auxiliary_data_block_size
    require(offset + size <= len(raw), "Truncated AVB metadata")
    if footer:
        require(footer.original_image_size <= offset and offset + size <= len(raw) - 64,
                "Invalid AVB footer bounds")
        require(footer.vbmeta_size == size, "AVB footer metadata size mismatch")
    require(header.algorithm_type == 2, "Expected signed SHA256_RSA4096 stock metadata")
    require(module.verify_vbmeta_signature(header, raw[offset:offset + size]), "Invalid AVB signature")
    key_start = offset + 256 + header.authentication_data_block_size + header.public_key_offset
    key = raw[key_start:key_start + header.public_key_size]
    parsed = []
    for desc in descriptors:
        values = {k: (v.hex() if isinstance(v, bytes) else v) for k, v in vars(desc).items()
                  if k not in ("tag", "data")}
        values["type"] = type(desc).__name__
        if isinstance(desc, module.AvbChainPartitionDescriptor):
            values.pop("public_key")
            values["public_key_sha256"] = digest(desc.public_key)
        if isinstance(desc, module.AvbHashDescriptor):
            part = images.get(desc.partition_name)
            values["image_available"] = part is not None
            if part is not None:
                require(desc.image_size <= len(part), "Hash descriptor exceeds image")
                computed = hashlib.new(desc.hash_algorithm, desc.salt + part[:desc.image_size]).digest()
                require(computed == desc.digest, "AVB image digest mismatch: " + desc.partition_name)
                values["image_digest_valid"] = True
        if isinstance(desc, module.AvbHashtreeDescriptor):
            values["hashtree_verified"] = False
        parsed.append(values)
    return {"algorithm": "SHA256_RSA4096", "flags": header.flags,
            "rollback_index": header.rollback_index,
            "rollback_index_location": header.rollback_index_location,
            "release_string": header.release_string, "vbmeta_bytes": size,
            "public_key_sha256": digest(key), "embedded_key_signature_valid": True,
            "bootloader_trust_verified": False,
            "footer": ({"original_image_bytes": footer.original_image_size,
                        "vbmeta_offset": offset, "vbmeta_bytes": footer.vbmeta_size} if footer else None),
            "descriptors": parsed}


def inspect_bundle(bundle, candidate_path, avbtool_path, assessment):
    import lz4.frame
    avbtool = load_avbtool(avbtool_path)
    limits = {part: assessment["partitions"][part]["bytes"] for part in IMAGES}
    required = {part + ".img.lz4" for part in IMAGES} | {"firmware-download-report.json"}
    require(bundle.stat().st_size <= 150 * 1024 * 1024, "Inspection ZIP is unexpectedly large")
    images = {}
    with zipfile.ZipFile(bundle) as archive:
        require(set(archive.namelist()) == required and len(archive.infolist()) == len(required),
                "Unexpected or duplicate ZIP members")
        require(archive.getinfo("firmware-download-report.json").file_size <= 1024 * 1024,
                "Download report is unexpectedly large")
        download = json.loads(archive.read("firmware-download-report.json").decode("utf-8-sig"))
        for key, expected in {"model": "SM-G975F", "region": "ITV", "csc_family": "OXM",
                              "pda": "G975FXXSGHWC1", "modem": "G975FXXSGHWB3"}.items():
            require(download.get(key) == expected, "Stock target mismatch: " + key)
        require(download.get("firmware_download_complete") and download.get("ap_md5_verified"),
                "Download or AP verification incomplete")
        manifest = {entry["name"]: entry for entry in download["stock_image_files"]}
        require(set(manifest) == required - {"firmware-download-report.json"}, "Invalid image manifest")
        for part in IMAGES:
            name = part + ".img.lz4"
            require(archive.getinfo(name).file_size <= 70 * 1024 * 1024, "Oversized compressed image")
            compressed = archive.read(name)
            require(len(compressed) == manifest[name]["compressed_bytes"]
                    and digest(compressed) == manifest[name]["sha256"], "Compressed image checksum mismatch")
            decoder = lz4.frame.LZ4FrameDecompressor()
            raw = decoder.decompress(compressed, max_length=limits[part] + 1)
            require(decoder.eof and not decoder.unused_data and len(raw) <= limits[part],
                    "Incomplete, trailing or oversized LZ4 image")
            images[part] = raw
    headers = {part: boot_header(images[part]) for part in ("boot", "recovery")}
    require(headers["boot"]["kernel_bytes"] == headers["recovery"]["kernel_bytes"], "Stock kernels differ in size")
    ks = headers["boot"]["kernel_bytes"]
    require(images["boot"][2048:2048 + ks] == images["recovery"][2048:2048 + ks], "Stock kernels differ")
    rh = headers["recovery"]
    files = recovery_ramdisk(images["recovery"][rh["ramdisk_offset"]:rh["ramdisk_offset"] + rh["ramdisk_bytes"]])
    properties = dict(line.split("=", 1) for line in files["prop.default"].decode().splitlines()
                      if line.startswith("ro.") and "=" in line)
    require(properties.get("ro.product.system.model") == download["model"] and
            properties.get("ro.system.build.version.incremental") == download["pda"],
            "Recovery metadata differs from downloaded target")
    dtbo = dtbo_table(images["dtbo"])
    embedded = images["recovery"][rh["recovery_dtbo_offset"]:rh["recovery_dtbo_offset"] + rh["recovery_dtbo_bytes"]]
    require(embedded == images["dtbo"][:dtbo["table_bytes"]], "Recovery and standalone DTBO differ")
    with tempfile.TemporaryDirectory() as tmp:
        avb = {}
        for part in IMAGES:
            path = Path(tmp) / (part + ".img")
            path.write_bytes(images[part])
            avb[part] = inspect_avb(path, avbtool, images)
    top = avb["vbmeta"]
    chain = {d["partition_name"]: d for d in top["descriptors"] if d["type"] == "AvbChainPartitionDescriptor"}
    for part in ("recovery", "dtbo"):
        require(chain[part]["public_key_sha256"] == avb[part]["public_key_sha256"], "AVB chain key mismatch")
    require(top["public_key_sha256"] == avb["boot"]["public_key_sha256"], "Boot AVB key mismatch")
    candidate = candidate_path.read_bytes()
    expected_sha = json.loads((ROOT / "docs/evidence/build-report-2026-10-12.json").read_text())["sha256"]["boot.img"]
    require(digest(candidate) == expected_sha, "Candidate boot differs from validated build 1")
    ch = boot_header(candidate)
    reference = headers["recovery"]
    fields = ("header_version", "header_bytes", "page_bytes", "kernel_address", "ramdisk_address", "tags_address")
    matches = {field: ch[field] == reference[field] for field in fields}
    require(all(matches.values()), "Candidate load layout differs from stock recovery")
    require(len(candidate) <= limits["boot"], "Candidate exceeds boot partition")
    selected_props = {k: properties[k] for k in ("ro.product.system.model", "ro.product.system.device",
                      "ro.system.build.fingerprint", "ro.system.build.version.release", "ro.system.build.version.sdk")}
    fstab = [line for line in files["system/etc/recovery.fstab"].decode().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    return {
        "stock_layout_inspected": True, "hardware_tested": False, "handset_modified": False,
        "install_ready": False, "inspection_bundle_sha256": digest(bundle.read_bytes()),
        "model": download["model"], "pda": download["pda"], "modem": download["modem"],
        "region": download["region"], "csc_family": download["csc_family"],
        "download_reported": {"firmware_zip_sha256": download["firmware_zip_sha256"],
                              "firmware_zip_bytes": download["firmware_zip_bytes"], "ap_md5_verified": True},
        "avbtool": {"url": AVBTOOL_URL, "sha256": AVBTOOL_SHA256},
        "images": {part: {"raw_bytes": len(data), "sha256": digest(data),
                   "partition_bytes": limits[part], "boot_header": headers.get(part), "avb": avb[part]}
                   for part, data in images.items()},
        "stock_kernels_identical": True, "recovery_dtbo_matches_standalone": True,
        "dtbo_table": dtbo, "recovery_ramdisk_entries": len(files),
        "recovery_build_properties": selected_props, "recovery_fstab": fstab,
        "candidate": {"boot_sha256": digest(candidate), "boot_bytes": len(candidate),
                      "boot_partition_remaining_bytes": limits["boot"] - len(candidate),
                      "boot_header": ch, "load_layout_matches_stock_recovery": matches,
                      "stock_avb_compatible": False,
                      "note": "Custom kernel/ramdisk differ from signed stock boot. Header agreement is not a hardware boot test."},
        "unverified_partitions": sorted({d["partition_name"] for d in top["descriptors"]
                                  if "partition_name" in d and d["partition_name"] not in images}),
        "limitations": ["Full stock ZIP retained on user PC; its hash/MD5 result is reported, not recomputed here",
                        "Separate dtb image and system/vendor/product filesystem contents are absent",
                        "AVB signatures checked against embedded keys; bootloader trust store not read",
                        "Stock recovery contains vbmeta_samsung/vbmeta_system fstab entries; their presence on this handset is not established",
                        "Samsung recovery/AVB installation route and vendor runtime remain unverified"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--avbtool", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, default=ROOT / "docs/evidence/device-check-2026-10-12.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_bundle(args.bundle, args.candidate, args.avbtool, json.loads(args.assessment.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"stock_layout_inspected": True, "install_ready": False,
                      "report": str(args.output.resolve())}, indent=2))
