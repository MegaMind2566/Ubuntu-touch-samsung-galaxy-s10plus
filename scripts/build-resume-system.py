#!/usr/bin/env python3
"""Derive a non-flashing graphics candidate from the exact published SYSTEM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import threading
import zipfile

from graphics_assembly import RULE_FILENAME, RULE_PATH, RULE_SHA256, canonical_rules

ROOT = Path(__file__).resolve().parents[1]
RELEASE_CONFIG = ROOT / "config/releases/v0.1.0-alpha.1.json"
BOOT_PIN = {"bytes": 57344000, "sha256": "2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad"}
RAW_PIN = {"bytes": 5368709120, "sha256": "d23c80be74e3313e1a18272b7d27003a56a1ebc8593d5302738abe657a6e27c3"}
BLOCK = 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def identity(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), "input_not_regular_file:" + path.name)
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            count += len(block)
            digest.update(block)
    return {"bytes": count, "sha256": digest.hexdigest()}


def verify(path, pin):
    require(Path(path).lstat().st_size == pin["bytes"], "input_size_mismatch:" + Path(path).name)
    actual = identity(path)
    require(actual == {key: pin[key] for key in ("bytes", "sha256")}, "input_hash_mismatch:" + Path(path).name)
    return actual


def run_command(command, cwd=None):
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True,
                          timeout=900, env=dict(os.environ, LC_ALL="C"))


def stream_zstd(source, pin, target=None, popen=subprocess.Popen):
    """Bound decompression and hash without ever creating a second raw image."""
    digest = hashlib.sha256()
    count = 0
    destination = None
    process = None
    try:
        if target is not None:
            destination = Path(target).open("xb")
        with tempfile.TemporaryFile() as errors:
            process = popen(["zstd", "-d", "-c", "--", str(source)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=errors)
            # A stalled executable must not occupy a hosted runner indefinitely.
            timer = threading.Timer(900, process.kill)
            timer.daemon = True
            timer.start()
            try:
                while True:
                    block = process.stdout.read(min(BLOCK, pin["bytes"] - count + 1))
                    if not block:
                        break
                    count += len(block)
                    require(count <= pin["bytes"], "expanded_system_oversized")
                    digest.update(block)
                    if destination is not None:
                        destination.write(block)
                require(process.wait(timeout=30) == 0, "zstd_decompression_failed")
            finally:
                timer.cancel()
                process.stdout.close()
            actual = {"bytes": count, "sha256": digest.hexdigest()}
            require(actual == pin, "expanded_system_identity_mismatch")
            return actual
    except BaseException:
        if process is not None:
            process.kill()
            process.wait(timeout=30)
        if destination is not None:
            destination.close()
            Path(target).unlink(missing_ok=True)
        raise
    finally:
        if destination is not None:
            destination.close()


def read_boot_tools(path, output, release):
    verify(path, release["boot_and_tools"])
    with zipfile.ZipFile(path) as archive:
        for name, size_limit in (("config/firmware-release.json", 65536), ("images/boot.img", BOOT_PIN["bytes"])):
            entries = [entry for entry in archive.infolist() if entry.filename == name]
            require(len(entries) == 1 and not entries[0].is_dir() and entries[0].file_size <= size_limit,
                    "release_zip_member_invalid:" + name)
        manifest = json.loads(archive.read("config/firmware-release.json"))
        require(manifest.get("release") == release["tag"] and manifest.get("firmware") == "G975FXXSGHWC1",
                "release_zip_baseline_mismatch")
        require(manifest.get("images", {}).get("boot.img") == BOOT_PIN, "release_zip_boot_pin_mismatch")
        separate = manifest.get("separate_asset", {})
        require(all(separate.get(key) == release["system"][key] for key in ("name", "bytes", "sha256"))
                and separate.get("raw_bytes") == RAW_PIN["bytes"]
                and separate.get("raw_sha256") == RAW_PIN["sha256"], "release_zip_system_pin_mismatch")
        require(manifest.get("graphics_payload_sha256", {}).get(RULE_FILENAME) == RULE_SHA256,
                "release_zip_graphics_pin_mismatch")
        boot = output / "BOOT6.img"
        digest = hashlib.sha256()
        count = 0
        with archive.open("images/boot.img") as source, boot.open("xb") as target:
            while block := source.read(min(BLOCK, BOOT_PIN["bytes"] - count + 1)):
                count += len(block)
                require(count <= BOOT_PIN["bytes"], "release_boot_oversized")
                digest.update(block)
                target.write(block)
        require({"bytes": count, "sha256": digest.hexdigest()} == BOOT_PIN, "release_boot_identity_mismatch")
        return manifest


def debugfs(image, command, run=run_command, cwd=None, missing_ok=False):
    write = command.startswith(("write ", "set_inode_field "))
    result = run(["debugfs", *(["-w"] if write else []), "-R", command, str(image)], cwd=cwd)
    text = result.stdout
    errors = result.stderr
    missing = "file not found" in errors.lower()
    if missing_ok and missing and not text.strip():
        return None
    require(not re.search(r"file not found|not a directory|filesystem not open|bad magic|short read|could not|invalid|error|permission denied|already exists",
                          errors + "\n" + text, re.I), "debugfs_command_failed:" + command.split()[0])
    return text


def inode(image, path, run=run_command, missing_ok=False):
    text = debugfs(image, "stat " + path, run=run, missing_ok=missing_ok)
    if text is None:
        return None
    kind = re.search(r"^Inode:\s*\d+\s+Type:\s*(\w+)\s+Mode:\s*([0-7]+)", text, re.M)
    owner = re.search(r"^User:\s*(\d+)\s+Group:\s*(\d+)", text, re.M)
    links = re.search(r"^Links:\s*(\d+)", text, re.M)
    require(kind is not None and owner is not None and links is not None, "debugfs_stat_unrecognized:" + path)
    return {"type": kind[1], "mode": int(kind[2], 8), "uid": int(owner[1]), "gid": int(owner[2]), "links": int(links[1])}


def verify_rule(image, payload, temporary, run):
    metadata = inode(image, RULE_PATH, run=run)
    require(metadata == {"type": "regular", "mode": 0o644, "uid": 0, "gid": 0, "links": 1},
            "graphics_rule_metadata_mismatch")
    readback = temporary / "readback.rules"
    readback.unlink(missing_ok=True)
    debugfs(image, "dump " + RULE_PATH + " readback.rules", run=run, cwd=temporary)
    require(readback.is_file() and not readback.is_symlink() and readback.read_bytes() == payload,
            "graphics_rule_readback_mismatch")
    return metadata


def integrate(image, payload, run=run_command):
    # Check each directory component: debugfs would otherwise follow symlinks.
    for path in ("/", "/usr", "/usr/lib", "/usr/lib/udev", "/usr/lib/udev/rules.d"):
        require(inode(image, path, run=run)["type"] == "directory", "graphics_parent_not_directory:" + path)
    existing = inode(image, RULE_PATH, run=run, missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="ut-graphics-") as name:
        temporary = Path(name)
        if existing is not None:
            metadata = verify_rule(image, payload, temporary, run)
            return {"created": False, "metadata": metadata}
        (temporary / "graphics.rules").write_bytes(payload)
        # Host filenames inside debugfs's own parser are fixed ASCII basenames.
        # The possibly spaced image path remains a separate subprocess argument.
        debugfs(image, "write graphics.rules " + RULE_PATH, run=run, cwd=temporary)
        for field, value in (("uid", "0"), ("gid", "0"), ("mode", "0100644")):
            debugfs(image, "set_inode_field " + RULE_PATH + " " + field + " " + value, run=run)
        return {"created": True, "metadata": verify_rule(image, payload, temporary, run)}


def build(system_zstd, boot_tools, output, run=run_command, popen=subprocess.Popen):
    release = json.loads(RELEASE_CONFIG.read_text())
    require(release.get("schema") == 1 and release.get("tag") == "v0.1.0-alpha.1", "release_config_mismatch")
    # Do not resolve away symlinked input files before checking their types.
    system_zstd, boot_tools = Path(system_zstd).absolute(), Path(boot_tools).absolute()
    original = verify(system_zstd, release["system"])
    verify(boot_tools, release["boot_and_tools"])
    payload = canonical_rules(ROOT / "tools/graphics-permissions" / RULE_FILENAME)
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), "output_must_be_fresh")
    output.mkdir(parents=True, exist_ok=False)
    working = output / "SYSTEM-working.img"
    compressed = output / "SYSTEM-graphics-candidate.img.zst"
    try:
        read_boot_tools(boot_tools, output, release)
        print("Verifying and expanding the immutable published SYSTEM...", flush=True)
        stream_zstd(system_zstd, RAW_PIN, target=working, popen=popen)
        # No write command is possible before the raw baseline identity verifies.
        run(["e2fsck", "-f", "-n", str(working)])
        graphics = integrate(working, payload, run=run)
        require(working.stat().st_size == RAW_PIN["bytes"], "candidate_raw_size_changed")
        run(["e2fsck", "-f", "-n", str(working)])
        candidate = identity(working)
        print("Compressing and verifying the complete candidate SYSTEM...", flush=True)
        run(["zstd", "-3", "-T2", "--no-progress", "-o", str(compressed), "--", str(working)])
        run(["zstd", "-t", "--", str(compressed)])
        stream_zstd(compressed, candidate, popen=popen)
        # Prove the separate input archive and BOOT6 still retain their identities.
        verify(system_zstd, release["system"])
        verify(boot_tools, release["boot_and_tools"])
        verify(output / "BOOT6.img", BOOT_PIN)
        working.rename(output / "SYSTEM.img")
        report = {
            "schema": 1, "kind": "derived-graphics-system-candidate",
            "source_release": release["tag"], "source_system_zstd": original,
            "source_system_raw": RAW_PIN, "source_boot_tools": {key: release["boot_and_tools"][key] for key in ("bytes", "sha256")},
            "boot6": BOOT_PIN, "boot6_preserved_byte_for_byte": True,
            "system_candidate_raw": candidate, "system_candidate_zstd": identity(compressed),
            "graphics_rule": {"path": RULE_PATH, "sha256": RULE_SHA256, **graphics},
            "requested_file_changes": [RULE_PATH], "filesystem_metadata_changes_expected": True,
            "other_file_content_readback_comparison": False,
            "filesystem_checks_before_and_after": True, "compressed_roundtrip_verified": True,
            "source_archives_unchanged": True, "image_mounted": False, "phone_accessed": False,
            "hardware_tested": False, "install_ready": False,
            "baseline_firmware": "G975FXXSGHWC1",
            "current_handset_vendor_compatibility_verified": False,
            "limitations": ["Derivative of the exact published SYSTEM, not clean assembly from upstream tarballs",
                            "A new SYSTEM candidate has not booted on a handset",
                            "Later userdata audio and Wi-Fi fixes are not added to this SYSTEM",
                            "The existing published image/release pins are unchanged"],
        }
        (output / "candidate-report.json").write_text(json.dumps(report, indent=2) + "\n")
        # The raw hash is in the report; only these three files travel in the
        # workflow artifact, so its SHA256SUMS is directly checkable after unzip.
        names = ("BOOT6.img", compressed.name, "candidate-report.json")
        (output / "SHA256SUMS").write_text("".join(identity(output / name)["sha256"] + "  " + name + "\n" for name in names))
        print(json.dumps(report, indent=2), flush=True)
        return report
    except BaseException:
        working.unlink(missing_ok=True)
        compressed.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-zstd", type=Path, required=True)
    parser.add_argument("--boot-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build(arguments.system_zstd, arguments.boot_tools, arguments.output)
