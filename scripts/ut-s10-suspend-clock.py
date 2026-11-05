#!/usr/bin/env python3
"""Read-only clock snapshots: BOOTTIME includes suspend, MONOTONIC excludes it.

No power controls, battery reads or polling. A comparison measures kernel clock
accounting only; it does not identify a sleep state, UI wake or battery endurance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import platform
import re
import time

BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
SESSION = re.compile(r"[0-9a-f]{32}\Z")
TOKEN = re.compile(r"[0-9a-f]{64}\Z")
LIMIT = 8192
MAX_NS = 2 ** 63 - 1
FIELDS = {"schema", "kind", "session", "boot_token", "device_time_utc",
          "kernel_release", "clocks", "errors"}
CLOCK_FIELDS = {"boottime_ns", "monotonic_ns", "uncertainty_ns"}
ERRORS = {"clocks-unavailable", "invalid-clock-sample", "boot-id-unavailable", "invalid-boot-id"}


class ClockError(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise ClockError(reason)


def integer(value):
    return type(value) is int and 0 <= value <= MAX_NS


def read_boot_token(session, path=BOOT_ID):
    require(isinstance(session, str) and SESSION.fullmatch(session), "invalid-session")
    try:
        with path.open("rb") as stream:
            raw = stream.read(129)
    except OSError:
        raise ClockError("boot-id-unavailable") from None
    require(len(raw) <= 128 and re.fullmatch(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", raw.strip()),
            "invalid-boot-id")
    return hmac.new(bytes.fromhex(session), raw.strip(), hashlib.sha256).hexdigest()


def sample_clocks():
    try:
        first = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        mono = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        last = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError, ValueError):
        raise ClockError("clocks-unavailable") from None
    require(all(integer(value) for value in (first, mono, last)) and first <= last and mono <= last,
            "invalid-clock-sample")
    return {"boottime_ns": (first + last) // 2, "monotonic_ns": mono,
            "uncertainty_ns": (last - first + 1) // 2}


def snapshot(session):
    require(isinstance(session, str) and SESSION.fullmatch(session), "invalid-session")
    report = {"schema": 1, "kind": "suspend-clock-snapshot", "session": session,
              "device_time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "kernel_release": platform.release(), "errors": []}
    for key, read in (("clocks", sample_clocks), ("boot_token", lambda: read_boot_token(session))):
        try:
            report[key] = read()
        except ClockError as error:
            report[key] = None
            report["errors"].append(str(error))
    return report


def validate_snapshot(report):
    require(type(report) is dict and set(report) == FIELDS, "invalid-snapshot-schema")
    require(type(report["schema"]) is int and report["schema"] == 1 and
            report["kind"] == "suspend-clock-snapshot", "invalid-snapshot-schema")
    require(isinstance(report["session"], str) and SESSION.fullmatch(report["session"]), "invalid-session")
    token = report["boot_token"]
    require(token is None or isinstance(token, str) and TOKEN.fullmatch(token), "invalid-boot-token")
    require(isinstance(report["kernel_release"], str) and
            re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", report["kernel_release"]), "invalid-kernel-release")
    stamp = report["device_time_utc"]
    try:
        require(isinstance(stamp, str) and len(stamp) <= 64 and
                datetime.fromisoformat(stamp).utcoffset().total_seconds() == 0, "invalid-device-time")
    except (ValueError, AttributeError):
        raise ClockError("invalid-device-time") from None
    errors = report["errors"]
    require(type(errors) is list and len(errors) <= 2 and
            all(isinstance(error, str) and error in ERRORS for error in errors), "invalid-snapshot-errors")
    clocks = report["clocks"]
    require(clocks is None or type(clocks) is dict and set(clocks) == CLOCK_FIELDS and
            all(integer(value) for value in clocks.values()), "invalid-clock-sample")
    if clocks is not None:
        require(clocks["boottime_ns"] + clocks["uncertainty_ns"] >= clocks["monotonic_ns"], "invalid-clock-sample")
    return report


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-field")
        result[key] = value
    return result


def load_snapshot(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(LIMIT + 1)
        require(len(raw) <= LIMIT, "snapshot-too-large")
        report = json.loads(raw, object_pairs_hook=unique_object)
    except (OSError, ValueError, RecursionError):
        raise ClockError("invalid-snapshot-json") from None
    return validate_snapshot(report)


def compare(before, after):
    validate_snapshot(before)
    validate_snapshot(after)
    require(before["session"] == after["session"], "session-mismatch")
    require(before["boot_token"] is not None and after["boot_token"] is not None, "boot-id-unavailable")
    require(hmac.compare_digest(before["boot_token"], after["boot_token"]), "boot-token-mismatch-possible-reboot")
    require(before["kernel_release"] == after["kernel_release"], "kernel-mismatch")
    require(before["clocks"] is not None and after["clocks"] is not None, "clocks-unavailable")
    require(not before["errors"] and not after["errors"], "snapshot-unavailable")
    first, last = before["clocks"], after["clocks"]
    boot_delta = last["boottime_ns"] - first["boottime_ns"]
    mono_delta = last["monotonic_ns"] - first["monotonic_ns"]
    require(boot_delta > 0 and mono_delta > 0, "invalid-clock-progress")
    estimate = boot_delta - mono_delta
    uncertainty = first["uncertainty_ns"] + last["uncertainty_ns"]
    require(estimate + uncertainty >= 0, "negative-suspend-estimate")
    lower, upper = max(0, estimate - uncertainty), max(0, estimate + uncertainty)
    return {"schema": 1, "kind": "suspend-clock-comparison", "status": "ok", "same_boot": True,
            "boottime_delta_ns": boot_delta, "monotonic_delta_ns": mono_delta,
            "suspend_estimate_ns": estimate, "uncertainty_ns": uncertainty,
            "suspend_interval_ns": [lower, upper],
            "evidence": "positive-suspend-time" if lower > 0 else "no-positive-suspend-time-resolved",
            "limitations": "Kernel clock accounting only; no deep-sleep, UI-wake or endurance claim."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--snapshot", action="store_true")
    action.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--session", help="32 hexadecimal digits identifying this diagnostic session")
    args = parser.parse_args(argv)
    if args.snapshot and (not args.session or not SESSION.fullmatch(args.session.lower())):
        parser.error("--snapshot requires --session with exactly 32 hexadecimal digits")
    if args.compare and args.session is not None:
        parser.error("--compare reads the diagnostic session from its snapshots")
    try:
        report = snapshot(args.session.lower()) if args.snapshot else compare(*(load_snapshot(path) for path in args.compare))
        status = 2 if report.get("errors") else 0
    except ClockError as error:
        report, status = {"schema": 1, "kind": "suspend-clock-error", "status": "invalid", "reason": str(error)}, 1
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
