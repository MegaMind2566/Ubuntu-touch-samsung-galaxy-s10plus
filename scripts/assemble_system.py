#!/usr/bin/env python3
"""Assemble a non-flashing UT 24.04/Halium 12 candidate from locked inputs."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

from fetch_sources import ROOT, checkout, git, read_lock
from prepare_build import archive


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            result.update(block)
    return result.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def download(spec, path):
    require(spec["url"].startswith("https://ci.ubports.com/"), "Unexpected upstream binary host")
    if not path.exists():
        print("Downloading " + spec["name"], flush=True)
        with urllib.request.urlopen(spec["url"], timeout=60) as response, path.open("wb") as output:
            shutil.copyfileobj(response, output, 4 * 1024 * 1024)
    require(path.stat().st_size == spec["bytes"] and sha256(path) == spec["sha256"],
            "Input checksum/size mismatch: " + spec["name"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adaptation", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=ROOT / "build/system-candidate")
    parser.add_argument("--output", type=Path, default=ROOT / "out/system-candidate")
    args = parser.parse_args()
    work, output, adaptation = args.work.resolve(), args.output.resolve(), args.adaptation.resolve()
    require(not work.exists() and not output.exists(), "Use fresh work and output directories")
    lock = json.loads((ROOT / "docs/evidence/assembly-inputs-2026-10-12.json").read_text())
    profile = json.loads((ROOT / "docs/evidence/device-check-2026-10-12.json").read_text())
    require(profile["inventory_valid"] and profile["android_version"] == profile["vendor_version"] == "12",
            "No valid Android 12 handset profile")
    image_bytes = lock["system_image_bytes"]
    require(image_bytes % (1024 * 1024) == 0, "System image size must use whole MiB")
    require(image_bytes + 64 * 1024 * 1024 <= profile["partitions"]["system"]["bytes"],
            "System image would exceed the verified partition reserve")
    for name, digest in lock["adaptation"]["sha256"].items():
        require(sha256(adaptation / name) == digest, "Unexpected adaptation input: " + name)
    require((adaptation / "boot.img").stat().st_size <= profile["partitions"]["boot"]["bytes"],
            "Boot image does not fit the verified handset")
    spec = importlib.util.spec_from_file_location("validate_artifacts", ROOT / "scripts/validate-artifacts.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate(adaptation)

    source_spec = read_lock()["sources"]["tools"]
    tools = checkout(source_spec, ROOT / "upstream" / source_spec["directory"])
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    archive(tools, work / "build")
    (work / "deviceinfo").write_text(
        'deviceinfo_codename="beyond2lte"\n'
        'deviceinfo_arch="aarch64"\n'
        'deviceinfo_halium_version="12"\n'
        'deviceinfo_ubuntu_touch_release="24.04-2.x"\n'
        'deviceinfo_use_overlaystore="true"\n'
        f'deviceinfo_system_partition_size="{image_bytes // (1024 * 1024)}M"\n'
    )
    # Retain the upstream assembly flow without its development-only defaults
    # that enable passwordless SSH, USB tethering and unauthenticated ADB.
    preparation = work / "build/prepare-fake-ota.sh"
    text = preparation.read_text()
    start = '# Enable SSH and USB tethering, and disable secure ADBD'
    end = 'print_header "Repacking rootfs..."'
    require(text.count(start) == text.count(end) == 1, "Upstream preparation layout changed")
    first, last = text.index(start), text.index(end)
    preparation.write_text(text[:first] + '# Keep the rootfs original remote-access defaults.\n\n' + text[last:])

    ota = work / "ota"
    ota.mkdir()
    for item in ("rootfs", "halium"):
        download(lock[item], ota / lock[item]["name"])
    manifest = {
        "inputs": lock, "handset_profile_sha256": sha256(ROOT / "docs/evidence/device-check-2026-10-12.json"),
        "tools_commit": git(tools, "rev-parse", "HEAD"),
        "preparation_script_sha256": sha256(preparation),
        "upstream_development_access_defaults_injected": False,
        "hardware_tested": False, "install_ready": False,
    }
    (output / "assembly-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    environment = dict(os.environ, ROOTFS_URL=lock["rootfs"]["url"], OTA_CHANNEL="local/24.04-2.x/beyond2lte")
    subprocess.run(["fakeroot", "--", "bash", str(preparation),
                    str(adaptation / "device_beyond2lte.tar.xz"), "ota"], cwd=work, env=environment, check=True)
    subprocess.run(["bash", str(work / "build/system-image-from-ota.sh"), "ota/ubuntu_command", str(output)],
                   cwd=work, check=True)
    subprocess.run(["python3", str(ROOT / "scripts/validate_system.py"), str(output)], check=True)
    subprocess.run(["zstd", "-3", "-T2", "--rm", str(output / "rootfs.img")], check=True)
    # The raw ext4 image is retained compressed. Keep the sparse conversion's
    # metadata in the report rather than uploading the same filesystem twice.
    (output / "system.img").unlink()
    files = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files))
    print("Verified non-flashing candidate: " + str(output), flush=True)


if __name__ == "__main__":
    main()
