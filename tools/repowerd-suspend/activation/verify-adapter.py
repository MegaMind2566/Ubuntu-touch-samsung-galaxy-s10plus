#!/usr/bin/env python3
"""Compile/test the actual patched adapter against fake C Binder transport in free CI only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
CASES = ("success", "startup-failure", "false", "malformed-bool", "exception",
         "truncated", "trailing", "transport-error", "timeout", "discovery-timeout",
         "missing-service", "reacquire-failure", "service-death", "release-error", "release-deadline")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("C++ builds/tests run only in the free public GitHub ARM64 workflow")
    source, output = args.source.resolve(), args.output.resolve()
    manifest = json.loads((HERE / "candidate.json").read_text())
    for relative, expected in manifest["source_after_sha256"].items():
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("actual adapter source hash mismatch: " + relative)
    output.mkdir(parents=True, exist_ok=False)
    binary = output / "actual-adapter-fake-binder"
    flags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "libgbinder"], text=True))
    libraries = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "glib-2.0", "gobject-2.0"], text=True))
    command = ["c++", "-std=c++17", "-pthread", "-g", "-O1", "-Wall", "-Wextra",
               "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-Daccess=s10_fake_access",
               "-I", str(source), *flags,
               str(source / "src/adapters/hidl_system_power_control.cpp"),
               str(source / "src/core/log.cpp"), str(source / "src/core/handler_registration.cpp"),
               str(HERE / "fake-binder-test.cpp"), *libraries, "-o", str(binary)]
    subprocess.run(command, check=True, timeout=120)
    report = {"schema": 1, "evidence": "actual adapter and bounded helper; fake Binder C boundary; ASan/UBSan",
              "hardware_operations": False, "source_sha256": manifest["source_after_sha256"],
              "compile_command": command, "cases": {}}
    for name in CASES:
        result = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=12)
        report["cases"][name] = {"exit_code": result.returncode,
                                  "output": result.stdout + result.stderr}
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'}", flush=True)
        print(result.stdout + result.stderr, flush=True)
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if all(value["exit_code"] == 0 for value in report["cases"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
