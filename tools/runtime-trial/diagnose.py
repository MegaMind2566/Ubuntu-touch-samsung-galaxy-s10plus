#!/usr/bin/env python3
"""Bounded, read-only startup evidence for the S10+ userdata runtime trial.

Never opens wakeup_count/autosleep, writes power controls, or enables suspend.
The systemd caller owns the output file; this program writes only stdout.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def command(args, limit=16000):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=4)
        return {"returncode": result.returncode, "text": result.stdout[:limit],
                "error": result.stderr[:400]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}


def daemon(name):
    result = command(["systemctl", "show", name, "-p", "MainPID", "-p", "ActiveState",
                      "-p", "Result", "-p", "NRestarts", "-p", "DropInPaths"])
    properties = dict(line.split("=", 1) for line in result.get("text", "").splitlines() if "=" in line)
    try:
        pid = int(properties.get("MainPID", "0"))
        if pid > 0:
            executable = Path(f"/proc/{pid}/exe")
            properties["executable"] = str(executable.resolve(strict=True))
            with executable.open("rb") as stream:
                properties["executable_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, ValueError):
        properties["executable_error"] = "unavailable"
    return properties


def suspend_descriptors():
    result = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text().strip() != "suspend@1.0-ser":
                continue
            targets = []
            sockets = 0
            for index, fd in enumerate((entry / "fd").iterdir()):
                if index >= 128:
                    break
                target = os.readlink(fd)
                if target.startswith("/sys/power/"):
                    targets.append(target)
                elif target.startswith("socket:"):
                    sockets += 1
            result.append({"pid": int(entry.name), "power_fd_targets": sorted(targets),
                           "socket_fd_count": sockets})
        except OSError:
            continue
    return result


def main():
    if os.geteuid() != 0 or platform.release() != "4.14.280-gb9b70b29c94c-dirty":
        raise SystemExit("Requires the normal BOOT 6 root service")
    report = {"schema": 1, "kind": "userdata-runtime-trial-read-only",
              "device_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "kernel_release": platform.release(),
              "adbd": daemon("adbd.service"), "repowerd": daemon("repowerd.service"),
              "suspend_service": suspend_descriptors()}
    report["android_suspend_counters"] = command(["/system/bin/dumpsys", "suspend_control_internal", "--suspend_controls"])
    report["brightness_params"] = command(["gdbus", "call", "--system", "--dest", "com.lomiri.Repowerd",
                                             "--object-path", "/com/lomiri/Repowerd", "--method",
                                             "com.lomiri.Repowerd.getBrightnessParams"])
    locks = command(["/system/bin/dumpsys", "suspend_control_internal", "--wakelocks"])
    report["repowerd_wakelock_lines"] = [line for line in locks.get("text", "").splitlines()
                                        if "repowerd" in line][:10]
    report["kernel_suspend_counters"] = command(["head", "-c", "8192", "/sys/kernel/debug/suspend_stats"])
    startup = command(["journalctl", "-b", "-u", "repowerd.service", "-n", "160", "--no-pager", "-o", "cat"])
    needles = ("HidlSystemPowerControl", "LibsuspendSystemPowerControl", "LogindSystemPowerControl",
               "Autobrightness not supported", "SensorfwLightSensor", "Property: autoBrightness",
               "Property: automatic_brightness", "parse_file(")
    report["repowerd_selected_logs"] = [line for line in startup.get("text", "").splitlines()
                                        if any(needle in line for needle in needles)]
    report["boundary"] = "Read-only startup inventory; no autosuspend activation or hardware acceptance claim."
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
