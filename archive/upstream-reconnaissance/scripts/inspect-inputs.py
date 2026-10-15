#!/usr/bin/env python3
"""Inspect official 24.04 rootfs/GSI metadata without fetching or flashing images."""
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ROOTFS = "https://ci.ubports.com/job/ubuntu-touch-rootfs/job/ubports%252F24.04-2.x/lastSuccessfulBuild"
GENERIC = "https://ci.ubports.com/job/UBportsCommunityPortsJenkinsCI/job/ubports%252Fporting%252Fcommunity-ports%252Fjenkins-ci%252Fgeneric_arm64/job/halium-12.0/lastSuccessfulBuild"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "beyond2lte-port-input-audit"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def inspect():
    report = {"target": "24.04-2.x", "hardware_tested": False, "errors": {}}
    for key, base, filename in [
        ("rootfs", ROOTFS, "ubuntu-touch-android9plus-rootfs-arm64.tar.gz"),
        ("halium_gsi", GENERIC, "halium_halium_arm64.tar.xz"),
    ]:
        try:
            build = fetch(base + "/api/json?tree=number,timestamp,url,artifacts[fileName,relativePath]")
            artifact = next(a for a in build["artifacts"] if a["fileName"] == filename)
            # Jenkins build-number URL is fixed, unlike lastSuccessfulBuild.
            report[key] = {"build": build["number"], "timestamp": build["timestamp"],
                           "url": build["url"] + "artifact/" + artifact["relativePath"]}
        except Exception as error:
            report["errors"][key] = f"{type(error).__name__}: {error}"
    try:
        channels = fetch("https://system-image.ubports.com/channels.json")
        report["official_s10plus_channels"] = [
            channel for channel, info in channels.items()
            if any(device in info.get("devices", {}) for device in ("beyond2lte", "samsung-beyond2lte"))
        ]
        report["official_24_04_channels"] = [
            channel for channel in channels if channel.startswith("24.04")
        ]
        # Inspect release metadata from a supported handset. Do not download
        # or reuse its device adaptation on the S10+.
        stable_channel = "24.04-2.x/arm64/android9plus/stable"
        devices = channels[stable_channel]["devices"]
        reference = "FP4" if "FP4" in devices else sorted(devices)[0]
        index_url = "https://system-image.ubports.com" + devices[reference]["index"]
        index = fetch(index_url)
        latest = max(index["images"], key=lambda image: image["version"])
        report["stable_release_reference"] = {
            "device": reference, "index_url": index_url,
            "image_version": latest["version"],
            "image_type": latest["type"],
            "description": latest.get("description"),
            "version_detail": latest.get("version_detail"),
        }
    except Exception as error:
        report["errors"]["channels"] = f"{type(error).__name__}: {error}"
    report["matching_vendor_verified"] = False
    report["note"] = "Historical 2021 vendor image is not assumed compatible with Halium 12. Rootfs metadata is a development input, not a device release."
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out/input-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return not report["errors"]


if __name__ == "__main__":
    raise SystemExit(0 if inspect() else 1)
