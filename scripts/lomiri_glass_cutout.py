#!/usr/bin/env python3
"""Stage a complete S10+ cutout profile in a NEW user-owned directory.

Read-only with respect to /etc/deviceinfo and /opt/halium-overlay. Does not
mount, install, restart a service, or request root privileges. A photo-based
rectangle is a proposal, not evidence of physical or runtime calibration.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

from lomiri_glass import PreparationError, contained, digest, read_regular, safe_path, write_new_json


ROOT = Path(__file__).resolve().parents[1]
ESTIMATE = ROOT / "shell/lomiri-glass/cutout/beyond2lte-estimate.json"
DEFAULT_SOURCE = Path("/etc/deviceinfo/devices/beyond2lte.yaml")
DEFAULT_OVERLAY = Path("/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml")
EXPECTED_SCALARS = {
    "Vendor": "Samsung",
    "PrettyName": "Galaxy S10+",
    "DeviceType": "phone",
    "GridUnit": "27",
}
EXPECTED_LISTS = {
    "Names": ["beyond2"],
    "SupportedOrientations": ["Portrait", "Landscape", "InvertedLandscape"],
}
CUTOUT_KEYS = (
    "CollapsedPanelHeight", "DisplayCutoutsCollapsed",
    "DisplayCutoutsCollapsedLight", "DisplayCutoutsExpanded",
)
MAX_PROFILE_SIZE = 64 * 1024


def checked_profile(data: bytes) -> str:
    """Validate the actual, simple handset profile without requiring PyYAML.

    Intentionally refuse unknown structures or keys: an updated device profile
    must be reviewed rather than partly parsed or silently lose settings.
    """
    if len(data) > MAX_PROFILE_SIZE or not data or b"\x00" in data:
        raise PreparationError("Unexpected DeviceInfo profile size or encoding")
    try:
        original = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreparationError("DeviceInfo must use UTF-8") from exc
    if "\r" in original or "\t" in original:
        raise PreparationError("Unexpected DeviceInfo line endings or tabs; review manually")

    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    root_count = 0
    current_list: str | None = None
    for line in original.splitlines():
        clean = line.rstrip(" ")
        if not clean.strip() or clean.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            if clean != "beyond2lte:":
                raise PreparationError("Unexpected DeviceInfo root mapping")
            root_count += 1
            current_list = None
            continue
        mapping = re.fullmatch(r"  ([A-Za-z][A-Za-z0-9]*):(?: (.*))?", clean)
        if mapping:
            if root_count != 1:
                raise PreparationError("DeviceInfo properties must follow the beyond2lte root")
            key, value = mapping.group(1), mapping.group(2)
            if key in CUTOUT_KEYS:
                raise PreparationError("Cutout keys already exist; do not create duplicate YAML keys")
            if key in scalars or key in lists:
                raise PreparationError(f"Duplicate DeviceInfo key: {key}")
            if key in EXPECTED_LISTS and value is None:
                lists[key] = []
                current_list = key
            elif key in EXPECTED_SCALARS and value is not None:
                scalars[key] = value
                current_list = None
            else:
                raise PreparationError(f"Unknown or changed DeviceInfo structure: {key}")
            continue
        member = re.fullmatch(r"    - ([A-Za-z0-9]+)", clean)
        if member and current_list and root_count == 1:
            lists[current_list].append(member.group(1))
            continue
        raise PreparationError("Unexpected DeviceInfo indentation or structure")

    if root_count != 1 or scalars != EXPECTED_SCALARS or lists != EXPECTED_LISTS:
        raise PreparationError("Active profile differs from the inspected S10+ baseline; review first")
    return original


def proposal_values(estimate_path: Path) -> dict:
    try:
        info = json.loads(read_regular(estimate_path))
        keys = info["proposed_deviceinfo_values"]
        screen = info["physical_display_px"]
        if (info["schema"] != 1 or info["grid_unit_px"] != 27
                or set(keys) != set(CUTOUT_KEYS)
                or keys["CollapsedPanelHeight"] != 81
                or screen != {"width": 1440, "height": 3040}):
            raise ValueError("Unexpected S10+ estimate metadata")
        for name in CUTOUT_KEYS[1:]:
            entries = keys[name]
            if not isinstance(entries, list) or len(entries) != 1:
                raise ValueError("Only one rectangle per cutout mode is expected")
            rectangle = entries[0]
            if not isinstance(rectangle, str) or not re.fullmatch(r"\d+ \d+ \d+ \d+", rectangle):
                raise ValueError("Invalid rectangle syntax")
            x, y, width, height = map(int, rectangle.split())
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1440 or y + height > 3040:
                raise ValueError("Rectangle exceeds the S10+ physical display")
        return keys
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise PreparationError("Cutout estimate is invalid") from exc


def normalize_profile(original: str) -> list[str]:
    return [line.rstrip(" ") for line in original.splitlines() if line.strip()]


def proposed_profile(original: str, keys: dict) -> bytes:
    suffix = "" if original.endswith("\n") else "\n"
    lines = [f"  CollapsedPanelHeight: {keys['CollapsedPanelHeight']}"]
    for key in CUTOUT_KEYS[1:]:
        lines.append(f"  {key}:")
        lines.extend(f"    - {rectangle}" for rectangle in keys[key])
    candidate = original + suffix + "\n".join(lines) + "\n"
    checked_candidate_suffix = candidate[len(original) + len(suffix):]
    if checked_candidate_suffix != "\n".join(lines) + "\n":
        raise PreparationError("Unexpected profile merge")
    return candidate.encode("utf-8")


def mount_info(path: Path) -> dict:
    """Collect only read-only mount metadata useful for rollback planning."""
    if not shutil.which("findmnt"):
        return {"status": "tool-unavailable"}
    try:
        done = subprocess.run(
            ["findmnt", "-T", str(path), "-n", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--json"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if done.returncode:
            return {"status": "query-failed"}
        data = json.loads(done.stdout)
        if not isinstance(data.get("filesystems"), list) or len(data["filesystems"]) != 1:
            return {"status": "unexpected-output"}
        info = data["filesystems"][0]
        # Do not include unrelated hardware or user data from mount listings.
        return {"status": "available", "target": str(info.get("target", ""))[:160],
                "source": str(info.get("source", ""))[:160],
                "filesystem": str(info.get("fstype", ""))[:80],
                "options": str(info.get("options", ""))[:400]}
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return {"status": "query-failed"}


def stage(source: Path, overlay: Path, output: Path, estimate: Path = ESTIMATE) -> dict:
    source, overlay, output = safe_path(source), safe_path(overlay), safe_path(output)
    if output.exists():
        raise PreparationError("Output already exists: choose a fresh directory")
    if not output.parent.is_dir():
        raise PreparationError("The output parent directory must already exist")
    for protected in (Path("/etc"), Path("/opt"), Path("/usr"), Path("/boot"),
                      Path("/run"), Path("/var"), Path("/system"), Path("/vendor")):
        if contained(output, protected):
            raise PreparationError("Stage inside your home directory, not a system path")
    if any(contained(path, output) for path in (source, overlay, estimate)):
        raise PreparationError("An input file must not reside within the staging output")

    original_data = read_regular(source)
    overlay_data = read_regular(overlay)
    original_text = checked_profile(original_data)
    overlay_text = checked_profile(overlay_data)
    if normalize_profile(original_text) != normalize_profile(overlay_text):
        raise PreparationError("DeviceInfo and Halium overlay differ; resolve before staging")
    keys = proposal_values(estimate)
    candidate = proposed_profile(original_text, keys)
    original_mount = mount_info(source)
    overlay_mount = mount_info(overlay)

    output.mkdir(exist_ok=False)
    created_identity = (output.stat().st_dev, output.stat().st_ino)
    try:
        staged = {
            "original-etc-beyond2lte.yaml": original_data,
            "original-halium-beyond2lte.yaml": overlay_data,
            "candidate-beyond2lte.yaml": candidate,
        }
        for name, content in staged.items():
            with (output / name).open("xb") as stream:
                stream.write(content)
        report = {
            "schema": 1, "kind": "read-only-cutout-profile-staging",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "device": "Samsung Galaxy S10+ beyond2lte",
            "source_etc": str(source), "source_overlay": str(overlay),
            "both_original_profiles_match_after_trailing_whitespace_normalization": True,
            "original_etc_sha256": digest(original_data),
            "original_overlay_sha256": digest(overlay_data),
            "candidate_sha256": digest(candidate),
            "added_properties": keys,
            "staged_files_sha256": {name: digest(content) for name, content in staged.items()},
            "source_etc_mount": original_mount, "source_overlay_mount": overlay_mount,
            "changes_applied_to_system": False, "lomiri_restarted": False,
            "ready_for_installation": False, "hardware_geometry_verified": False,
            "pending": ["Runtime profile selection check", "Independent automatic restore and rescue route",
                        "On-device cutout fit and orientation tests", "Native Glass shell trial"],
        }
        write_new_json(output / "deviceinfo-stage-report.json", report)
        return report
    except BaseException:
        # Only clean up our freshly created directory, never pre-existing data.
        try:
            info = output.lstat()
            if stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == created_identity:
                shutil.rmtree(output)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["stage"], help="Inspect active originals and stage a merged copy")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--overlay-source", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = stage(args.source, args.overlay_source, args.output)
        print(json.dumps({"staged": str(args.output),
                          "candidate_sha256": report["candidate_sha256"],
                          "changes_applied_to_system": False,
                          "ready_for_installation": False}))
        return 0
    except (OSError, PreparationError, ValueError) as exc:
        print(f"lomiri-glass-cutout: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
