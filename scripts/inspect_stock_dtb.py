#!/usr/bin/env python3
"""Audit the supplied Samsung dt.img (AVB partition dtb), without device access."""
import argparse
import json
from pathlib import Path
import struct
import tempfile
import zipfile

from inspect_stock_firmware import ROOT, digest, dtbo_table, inspect_avb, load_avbtool, require


def fdt_summary(blob):
    require(len(blob) >= 40, "Truncated FDT header")
    magic, total, struct_off, strings_off, reserve_off, version, compatible_version, _, strings_size, struct_size = struct.unpack_from(">10I", blob)
    require(magic == 0xD00DFEED and total == len(blob), "Invalid FDT magic/size")
    require(version == 17 and compatible_version <= 17, "Unsupported FDT version")
    require(reserve_off >= 40 and reserve_off + 16 <= total, "Invalid FDT reserve-map bounds")
    require(struct_off >= 40 and struct_off % 4 == 0 and struct_off + struct_size <= total,
            "Invalid FDT structure bounds")
    require(strings_off >= 40 and strings_off + strings_size <= total, "Invalid FDT string bounds")
    require(struct_off + struct_size <= strings_off or strings_off + strings_size <= struct_off,
            "Overlapping FDT structure/string blocks")
    strings = blob[strings_off:strings_off + strings_size]
    pos, end, stack, nodes, properties = struct_off, struct_off + struct_size, [], 0, 0
    root, devices = {}, {}
    ended = False
    while pos + 4 <= end:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:
            stop = blob.find(b"\0", pos, end)
            require(stop >= pos, "Unterminated FDT node name")
            name = blob[pos:stop].decode()
            require(stack or (nodes == 0 and name == ""), "Invalid FDT root")
            stack.append(name)
            nodes += 1
            pos = (stop + 4) // 4 * 4
        elif token == 2:
            require(bool(stack), "Unmatched FDT node end")
            stack.pop()
        elif token == 3:
            require(stack and pos + 8 <= end, "Invalid FDT property header")
            length, name_off = struct.unpack_from(">2I", blob, pos)
            pos += 8
            require(pos + length <= end and name_off < len(strings), "FDT property exceeds block bounds")
            stop = strings.find(b"\0", name_off)
            require(stop >= name_off, "Unterminated FDT property name")
            name = strings[name_off:stop].decode()
            data = blob[pos:pos + length]
            pos = (pos + length + 3) // 4 * 4
            require(pos <= end, "FDT property padding exceeds structure")
            properties += 1
            path = "/" + "/".join(stack[1:])
            if len(stack) == 1 and name in ("compatible", "model", "dtb-hw_rev", "dtb-hw_rev_end",
                                           "#address-cells", "#size-cells"):
                if name in ("compatible", "model"):
                    require(data.endswith(b"\0"), "Unterminated root string property")
                    root[name] = [x.decode() for x in data.rstrip(b"\0").split(b"\0")]
                else:
                    require(len(data) == 4, "Invalid root cell property")
                    root[name] = struct.unpack(">I", data)[0]
            if name == "compatible" and path.startswith(("/mali@", "/cpus/cpu@", "/ufs@",
                                                           "/usb@", "/displayport@")):
                require(data.endswith(b"\0"), "Unterminated compatible property")
                devices[path] = [x.decode() for x in data.rstrip(b"\0").split(b"\0")]
        elif token == 4:
            pass
        elif token == 9:
            require(not stack and nodes > 0, "Unclosed FDT nodes")
            ended = True
            break
        else:
            raise ValueError("Unknown FDT token")
    require(ended, "Missing FDT end token")
    require(not any(blob[pos:end]), "Non-padding data after FDT end")
    return {"bytes": total, "version": version, "node_count": nodes,
            "property_count": properties, "root_properties": root,
            "selected_compatible_nodes": devices}


def inspect(bundle, avbtool_path, stock_report, handset):
    import lz4.frame
    require(bundle.stat().st_size <= 40 * 1024 * 1024, "Oversized DTB inspection ZIP")
    with zipfile.ZipFile(bundle) as archive:
        require(set(archive.namelist()) == {"dt.img.lz4", "dtb-extraction-report.json"}
                and len(archive.infolist()) == 2, "Unexpected/duplicate DTB ZIP members")
        require(archive.getinfo("dtb-extraction-report.json").file_size <= 1024 * 1024,
                "Oversized DTB extraction report")
        report_bytes = archive.read("dtb-extraction-report.json")
        extracted = json.loads(report_bytes.decode("utf-8-sig"))
        for field in ("model", "pda", "modem", "region", "csc_family"):
            require(extracted[field] == stock_report[field], "Stock DTB target mismatch: " + field)
        require(extracted["dtb_extracted"] and extracted["inspection_inputs_created"], "DTB extraction incomplete")
        require(extracted["firmware_zip_sha256"] == stock_report["download_reported"]["firmware_zip_sha256"],
                "DTB belongs to another stock archive")
        require(extracted["firmware_zip_bytes"] == stock_report["download_reported"]["firmware_zip_bytes"],
                "Stock archive size mismatch")
        spec = extracted["stock_dtb"]
        require(spec["name"] == "dt.img.lz4" and spec["compressed"], "Unexpected stock DTB filename/format")
        require(spec["package_name"].startswith("AP_" + extracted["pda"] + "_"), "DTB package mismatch")
        require(archive.getinfo("dt.img.lz4").file_size <= 32 * 1024 * 1024, "Oversized compressed DTB")
        compressed = archive.read("dt.img.lz4")
        require(len(compressed) == spec["bytes"] and digest(compressed) == spec["sha256"],
                "Compressed DTB checksum mismatch")
    decoder = lz4.frame.LZ4FrameDecompressor()
    raw = decoder.decompress(compressed, max_length=32 * 1024 * 1024 + 1)
    require(decoder.eof and not decoder.unused_data and len(raw) <= 32 * 1024 * 1024,
            "Incomplete, trailing or oversized DTB LZ4 image")
    table = dtbo_table(raw)
    fdts = []
    for entry in table["entries"]:
        summary = fdt_summary(raw[entry["offset"]:entry["offset"] + entry["bytes"]])
        require("samsung,exynos9820" in summary["root_properties"].get("compatible", []),
                "DTB does not describe Exynos 9820")
        fdts.append(summary)
    require(handset["hardware"] == "exynos9820", "Handset assessment SoC mismatch")
    avbtool = load_avbtool(avbtool_path)
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "dt.img"
        image.write_bytes(raw)
        avb = inspect_avb(image, avbtool, {"dtb": raw})
    chains = [d for d in stock_report["images"]["vbmeta"]["avb"]["descriptors"]
              if d["type"] == "AvbChainPartitionDescriptor" and d["partition_name"] == "dtb"]
    require(len(chains) == 1 and chains[0]["public_key_sha256"] == avb["public_key_sha256"],
            "DTB signature key differs from stock vbmeta chain")
    hashes = [d for d in avb["descriptors"] if d["type"] == "AvbHashDescriptor"]
    require(len(hashes) == 1 and hashes[0]["partition_name"] == "dtb" and hashes[0]["image_digest_valid"],
            "Expected DTB AVB hash descriptor missing")
    require(avb["footer"]["original_image_bytes"] >= table["table_bytes"], "DTB table exceeds signed payload")
    return {
        "stock_dtb_inspected": True, "dtb_extracted": True,
        "model": extracted["model"], "pda": extracted["pda"], "region": extracted["region"],
        "inspection_bundle_sha256": digest(bundle.read_bytes()),
        "collector_tool_version": extracted["tool_version"],
        "collector_report_captured_utc": extracted["captured_utc"],
        "source_firmware_zip_sha256_reported": extracted["firmware_zip_sha256"],
        "source_firmware_package": spec["package_name"], "source_image_name": spec["name"],
        "compressed_bytes": len(compressed), "compressed_sha256": digest(compressed),
        "raw_bytes": len(raw), "raw_sha256": digest(raw),
        "avb_partition_name": "dtb", "stock_vbmeta_chain_key_matches": True,
        "chain_rollback_index_location": chains[0]["rollback_index_location"],
        "avb": avb, "device_tree_table": table, "fdts": fdts,
        "soc_matches_handset_assessment": True,
        "handset_dtb_partition_bytes": None,
        "hardware_tested": False, "handset_modified": False, "install_ready": False,
        "limitations": ["DTB partition size was not collected from the handset; factory image size alone is not a measurement",
                        "Embedded-key signature/chain checks do not read the bootloader trust store",
                        "Stock DTB parsing and SoC agreement do not verify every binding against the custom kernel",
                        "Vendor runtime and Samsung recovery/AVB installation route remain untested"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--avbtool", type=Path, required=True)
    parser.add_argument("--stock-report", type=Path, default=ROOT / "docs/stock-layout-report-2026-10-13.json")
    parser.add_argument("--handset", type=Path, default=ROOT / "docs/device-check-2026-10-12.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.bundle, args.avbtool, json.loads(args.stock_report.read_text()), json.loads(args.handset.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"stock_dtb_inspected": True, "soc_matches_handset": True,
                      "stock_avb_chain_matches": True, "install_ready": False, "report": str(args.output.resolve())}, indent=2))
