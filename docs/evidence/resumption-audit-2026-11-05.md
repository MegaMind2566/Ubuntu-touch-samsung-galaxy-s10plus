# Local resumption audit — 5 November 2026

This records the initial local audit. Later direct device access, recovered sources, successful normal-boot ADB restoration and battery observations supersede its transport blocker; see the [USB diagnosis and acceptance](usb-normal-boot-diagnosis-2026-11-05.md).

## Scope and provenance

The user requested resumption and explicitly selected Ubuntu Touch 24.04 / Halium 12. Android 16 / DeX artifacts found locally belong to a separate project. This audit starts at repository commit `1b11800d50f60e612edd4eb4ae3b01b3f1b64ab6`. Changes are local and uncommitted; no new firmware release or handset installation was made.

The user reports Ubuntu Touch currently running with Developer Mode enabled. Repeated host `adb devices -l` queries returned an empty device list. Windows also exposed no identifiable handset USB interface. This is a transport blocker, not evidence of a failed Ubuntu boot. No root command, service restart, reboot, partition write or hardware configuration change was requested from the phone.

## Local artifact verification

- Desktop alpha.1 Windows ZIP: 73,287,864 bytes, SHA-256 `643bcc8c137060c87871d472c8bd35a6b03f55aa905fc2f4a92d833975acdedb`; ZIP CRC and all 70 manifest checksum entries match.
- All 12 TWRP SHA-256 sidecars match. This establishes file integrity only, not restoreability or identity with Ubuntu SYSTEM. The backed-up system image is 5,976,883,200 bytes versus alpha.1's expected 5,368,709,120-byte raw SYSTEM.
- The separate `SYSTEM.img.zst` was not found at the top level of Desktop/Downloads; the release manifest expects 1,114,706,918 bytes, SHA-256 `6729e58ca7924a7682a332c4a58a1e1ad1dc3b31437707fb49366b518da99928`. No claim of an exhaustive disk search.
- The backup was read only; no personal recordings or raw backup contents are included in this record.

## Source findings and bounded corrections

1. Windows `core.autocrlf=true` changed seven hash-pinned graphics text payloads. Baseline graphics installer tests failed with `local_payload_hash_mismatch`. Explicit LF attributes preserve the original committed bytes without changing their pinned hashes. A fresh autocrlf-enabled checkout and the refreshed local files pass all 18 host graphics installer tests.
2. Energy v2's historical test results were documented but the tests were not retained. Added 16 standard-library regressions for allowlisted data, exclusion of blocking sysfs fields and private fields, timeout cleanup, partial reports, optional tools and CLI behavior. Tests use fixtures and dedicated sleeping child processes, not a phone. Mutating the serial allowlist or adding `wakeup_count` makes the corresponding test fail.
3. Added a host-only Ubuntu 24.04 workflow for energy and existing TRRS regressions, including script path triggers. The new workflow has not run on GitHub; native Windows lacks `fcntl`, so TRRS was not revalidated here.
4. Corrected the scripts index's stale TRRS test count and hardware-pending description against the later 23 October evidence. No audio behavior changed.

## Verification boundaries

- New energy suite: 16 passed on Windows / Python 3.14.
- Graphics permissions Host suite: 10 passed; graphics probe Host suite: 8 passed.
- Full baseline discovery before changes: 165 tests, 8 assertion failures, 51 errors, 3 skipped. An independent LF-controlled baseline eliminated assertion failures and left 45 environment errors (POSIX APIs, missing Linux tools and symlink permissions). This is not a passing full suite.
- Syntax baseline: 78 Python files, 4 shell files and 23 PowerShell files parsed successfully.
- Independent review found no blocking defect in the changes. `git diff --check` passes.
- No full Linux suite, ARM64 build, SYSTEM assembly, physical charging experiment, suspend/wake trial or clean install was performed.

## Integration work still required

USB's kernel NULL guard is integrated into BOOT 6 tooling. The graphics permission payload has maintained source and guarded installation but remains a separate userdata correction. SYSTEM assembly does not incorporate the later runtime fixes. Exact installed Wi-Fi configuration, audio6 v2 drop-in and primary-sink service must be recovered before image integration; their contents must not be invented from narrative descriptions. TRRS v4 source and tests exist, but depend on the already installed audio baseline.

Once USB/SSH is available, confirm model/OS and read back the existing configuration without restarting services. Continue the previously selected energy work: read-only baseline, physical charger connection, snapshots after about 1 and 10–15 minutes, then a separate ordinary screen-off/wake test. Preserve BOOT 6, graphics correction, Wi-Fi, audio6 and TRRS v4. Do not infer actual charging, suspend or endurance from capability flags or one sample.

## Engineering references used

- [Agent Skills](https://github.com/addyosmani/agent-skills), commit `301b02b12bff98e4688e6984af6556802322bbde`: context engineering, systematic debugging, test-driven implementation and independent review.
- Context7 resolved CPython documentation and supplied the [subprocess timeout/cleanup contract](https://github.com/python/cpython/blob/v3.13.9/Doc/library/subprocess.rst). The collector deliberately retains a bounded second communicate call for potentially uninterruptible sysfs workers.
- [UBports ADB documentation](https://docs.ubports.com/en/latest/userguide/advanceduse/adb.html) used for Developer Mode and authorization checks; Context7 did not return a matching UBports library, so primary documentation was consulted directly.
- 21Dev catalog consulted for diagnostic/status presentation references only. Its React components were not added to the native port.
- [Impeccable](https://github.com/pbakaus/impeccable), commit `c8891a9ae865d6ee311836ae5199bfce0fe115b1`: context inspected; no visual implementation is present in this repository. No UI redesign, design hook or generated web console was introduced.
