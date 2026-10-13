#!/usr/bin/env python3
"""Stage the locked S10+ port and kernel changes in an isolated build directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from fetch_sources import ROOT, checkout, git, read_lock


def archive(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryFile() as stream:
        subprocess.run(["git", "-C", str(source), "archive", "HEAD"], stdout=stream, check=True)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as tar:
            # Trusted, pinned upstream Git tree; preserve executable bits/symlinks.
            tar.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT / "build/port")
    args = parser.parse_args()
    work = args.work.resolve()
    if work.exists():
        raise RuntimeError(f"Build directory already exists: {work}. Use a new --work path.")
    lock = read_lock()
    sources = {}
    for name, spec in lock["sources"].items():
        sources[name] = checkout(spec, ROOT / "upstream" / spec["directory"])
    archive(sources["port"], work)
    archive(sources["tools"], work / "build")
    kernel = work / "workdir/downloads/kernel-samsung-exynos9820"
    kernel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(sources["kernel"]), str(kernel)], check=True)
    git(kernel, "checkout", "--quiet", "--detach", lock["sources"]["kernel"]["commit"])

    patches = []
    for patch in sorted((ROOT / "patches/kernel").glob("*.patch")):
        git(kernel, "apply", "--check", str(patch))
        git(kernel, "apply", str(patch))
        patches.append({"path": str(patch.relative_to(ROOT)), "sha256": hashlib.sha256(patch.read_bytes()).hexdigest()})
    expected_patches = ["0001-apparmor-socket-mediation.patch", "0002-apparmor-af-unix-mediation.patch",
                        "0003-initialize-sar-ramdisk-offset.patch", "0004-restore-init-after-sar-ramdisk-load.patch"]
    if [Path(patch["path"]).name for patch in patches] != expected_patches:
        raise RuntimeError("The two AppArmor and both SAR ramdisk fixes are required")
    fragment = ROOT / "config/ubuntu-touch.config"
    shutil.copy2(fragment, kernel / "arch/arm64/configs/ubuntu-touch.config")
    info = (work / "deviceinfo-beyond2lte").read_text()
    info += '\n# Local Ubuntu Touch 24.04 preparation\n'
    info += 'deviceinfo_kernel_source="' + lock["sources"]["kernel"]["url"] + '"\n'
    info += 'deviceinfo_kernel_defconfig="exynos9820-beyond2lte_defconfig ubuntu-touch.config"\n'
    info += 'deviceinfo_ubuntu_touch_release="' + lock["target"]["ubuntu_touch_release"] + '"\n'
    info += 'deviceinfo_use_overlaystore="true"\n'
    (work / "deviceinfo").write_text(info)
    # Historical android.conf overrides the S10+ DeviceInfo GridUnit of 27.
    session = work / "overlay/system/etc/ubuntu-touch-session.d/android.conf"
    session.write_text(session.read_text().replace("GRID_UNIT_PX=31", "GRID_UNIT_PX=27"))
    manifest = {
        "sources": lock, "kernel_patches": patches,
        "config_sha256": hashlib.sha256(fragment.read_bytes()).hexdigest(),
        "hardware_tested": False,
        "scope": "Device adaptation only; rootfs and matching vendor not assembled",
    }
    (work / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(work, flush=True)


if __name__ == "__main__":
    main()

