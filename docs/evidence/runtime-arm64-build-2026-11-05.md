# Native ARM64 candidate build — 5 November 2026

The ADB reconnect candidate completed a full official Debian package build on
the public repository's standard free GitHub Actions `ubuntu-24.04-arm` runner.
[Run 42025861432](https://github.com/MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus/actions/runs/42025861432),
job `127239780231`, built commit `5ce6823d290a60fa15d0a270059b728cdf06ca51`.
No local, self-hosted or paid ARM64 compilation was used.

The build applies the entire original Debian patch series from exact installed
UBports source `6391ffe9`, then the [local reconnect patch](../../patches/usb/README.md)
on Android `android-14.0.0_r45` / `b8016a72`. Its explicit worker completion and
retained FunctionFS control/bound/enabled state preserve ADB authentication and
usb-moded ownership. The original duplicate dependency separator and an initial
build-script version-variable collision were corrected in the build tooling;
neither requires changing handset libraries.

Before applying the candidate, the exact baseline fixture reproduced the worker
timeout and control-fd assertion failure. After applying it, **all eight cases
passed**: early worker exit, idle eventfd stop, interruptible submit boundary,
repeated retained-control reconnect, UNBIND/new BIND, stop while still enabled,
queued DISABLE before resume, and reuse of the existing control fd. These tests
compile real source bodies with simulated external I/O boundaries. They do not
exercise the physical S10 kernel/USB host or prove the field regression fixed.

The downloaded artifact archive and `.deb` were hash-verified; the extracted
399,160-byte `usr/bin/adbd` has SHA-256
`7b7c034e0d0039e8c6f8cd867122fc67db6915547a1fec11b5904e1b666ddf43`.
The installed handset loader resolved all candidate libraries from a temporary
staging path. **The candidate daemon was not started or installed by that check.**
Package, archive and source identities are in the
[sanitized machine-readable record](runtime-arm64-build-2026-11-05.json).

The reconnect regression remains open pending a reversible controlled trial:
secure authorized shell and transfers, then repeated physical unplug/replug
without a mode flip or daemon restart, while retaining authenticated Wi-Fi
recovery and the original binary. A build or loader check does not establish
FunctionFS recovery, session stability or unchanged physical MTP behavior.

## First repowerd build completed; deployment held

Job `127239779931` in the same run also completed successfully, producing matching
`repowerd`, `repowerd-data` and `repowerd-tools` packages at
`2025.09+s10hidl.20261105`. Both upstream CTest suites, `repowerd-core-tests` and
`repowerd-adapter-tests`, passed (100%; 3.67 seconds). The downloaded archive and
all package hashes were checked. The extracted 591,992-byte daemon has SHA-256
`43f64c581861bee5af2c89c8f4cb4db82a7381e251c4b6ddb812eb3c7a3b6aa0`;
the installed handset loader resolved its libraries without starting it.

This first artifact contains the unchanged upstream HIDL backport. Further
source review identified wake-lock remote-object ownership/lifetime handling
and Android autosuspend activation as requirements before a controlled trial.
**Deployment is held** while the follow-up candidate is prepared and verified.
The first build's upstream tests do not establish those new behaviors or actual
HIDL/AIDL transactions. No candidate repowerd runtime, positive suspend, resume
or endurance result is established here.
