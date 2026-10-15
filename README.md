# Ubuntu Touch for Samsung Galaxy S10+

An experimental **Ubuntu Touch 24.04 / Halium 12** bring-up project for the **Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`)**. The goal is to reach a working Ubuntu Touch boot on the Android 12 firmware/vendor baseline, then validate the device hardware and establish a repeatable installation path.

**Current stage: Ubuntu initramfs reaches its final userspace handoff; systemd and graphical startup remain unconfirmed.** BOOT 4 is installed on the test handset with matching physical readback. Its recorded attempt mounts Ubuntu SYSTEM, the embedded Android image and Data, completes udev cleanup, then saves `userspace-handoff` at 3.510 seconds. That marker precedes the final `run-init` execution; it does not establish a working Ubuntu boot.

Status updated **15 October 2026**. This repository documents an experimental port, not a supported release for daily use.

Publication is planned after the first confirmed Ubuntu Touch graphical boot on the test handset. The published status will identify the tested images and list hardware features that remain untested.

## Scope

| Item | Target |
| --- | --- |
| Phone | Galaxy S10+ Exynos, SM-G975F/DS |
| Codename / SoC | `beyond2lte` / Exynos 9820 |
| Test firmware | G975FXXSGHWC1, Android 12 / One UI 4.1, ITV/OXM |
| Adaptation | Community Samsung Halium 12 sources with local kernel/configuration fixes |
| Ubuntu userspace | Ubuntu Touch 24.04 arm64 |
| Storage | Measured A-only Samsung partition layout; SYSTEM and BOOT installation |

Snapdragon variants and other Galaxy S10 models are outside the tested scope.

## Progress

| Milestone | Result |
| --- | --- |
| Identify the handset, firmware and actual partition layout | Confirmed on the test handset |
| Build and inspect the Halium adaptation and Ubuntu SYSTEM | Completed offline and in CI |
| Prepare and boot TWRP; verify recovery/VBMETA and root ADB | Confirmed on the test handset |
| Install SYSTEM/BOOT and verify the written image prefixes | Confirmed on the test handset |
| Correct the SAR ramdisk offset and late `/init` handoff | Implemented and tested; compiled handoff fix verified |
| Diagnostic 2 kernel and PID 1 | Confirmed on the phone with the exact BOOT hash |
| Read Data, SYSTEM and VENDOR under the normal kernel | Confirmed by diagnostic 2 |
| Configure USB ACM under the normal kernel | Configuration and host enumeration recorded |
| Original Ubuntu init, intended SYSTEM and embedded Android mounts | Confirmed by BOOT 3 and BOOT 4 on the handset |
| Original initramfs cleanup and final userspace-handoff checkpoint | Confirmed by BOOT 4; systemd execution unconfirmed |
| Reach Ubuntu userspace and the graphical shell | Unconfirmed |
| Validate modem, networking, audio, camera, sensors and suspend | Untested |

The detailed [current status](docs/status.md) distinguishes source checks, host tests, physical readback and actual runtime observations. Its conclusions link to the [evidence index](docs/evidence/README.md).

## Current boot investigation

The [BOOT 4 handset report](docs/evidence/ubuntu-boot-4-handset-2026-10-15.json) confirms the exact 57,337,856-byte BOOT write/readback and original Ubuntu init execution through `userspace-handoff`. The saved mounts retain SYSTEM and Android read-only, Data read-write and the original writable-path bindings. Udev's exit command completes. No BOOT 4 screen observation was supplied, and neither systemd nor the graphical shell is confirmed.

The 7,280-byte shell trace stops when the original Halium mount code redirects output to `/dev/kmsg`; later stage markers still reach the kernel log. The observer is stopped at handoff, before its first 10-second passive sample. Missing wait samples and userspace log files therefore do not identify the failure or prove userspace never ran.

The [exact userspace audit](docs/evidence/userspace-compatibility-2026-10-15.json) verifies Ubuntu init and its loader/dependencies. It identifies a compatibility mismatch between systemd 255's unified cgroup default and the included Android image's v1 controllers. BOOT 5 corrects that selection, removes console opening from the final handoff, retains the real HWC readiness gate across compositor service names, and records startup after the root transition. BOOT 5 has no validated image identity or handset result yet. The optional read-only TWRP inspector can collect additional evidence, but is not a required extra handset step. No new SYSTEM/VENDOR flash or Format Data is justified by the current reports.

The immutable [BOOT 4 build record](docs/evidence/ubuntu-boot-4-build-2026-10-15.json) retains its source/image pins and Linux/ARM64 plus 24 native Windows validation cases. Earlier [BOOT 3 execution](docs/evidence/ubuntu-boot-3-handset-2026-10-15.json), [diagnostic 2 execution](docs/evidence/boot-diagnostic-2-handset-2026-10-15.json), and [symbol/device-tree analysis](docs/evidence/offline-tools-2026-10-14.json) remain available. See [current status](docs/status.md#next-experiment) for the next experiment and its limits.

## Repository map

| Location | Contents |
| --- | --- |
| [config](config) | Source, configuration and installation image pins |
| [patches/kernel](patches/kernel) | AppArmor and Samsung SAR kernel fixes |
| [patches/diagnostic](patches/diagnostic) | Forced built-in-initramfs change shared by diagnostic 2 and the Ubuntu BOOT family |
| [scripts](scripts/README.md) | Maintained build, inspection, packaging and shared support code |
| [scripts/templates](scripts/templates) | Shared verified BOOT installer/image-verifier templates |
| [tools/boot-diagnostic](tools/boot-diagnostic) | Original diagnostic input and static ARM64 display helper |
| [tools/boot-observer](tools/boot-observer) | Bounded initramfs trace, stage capture and passive wait sampling |
| [tools/windows](tools/windows/README.md) | Launcher inputs for prepared Windows packages |
| [tests](tests) | Image, source, collector and Windows guard validation |
| [docs](docs/README.md) | Current status and development documentation |
| [docs/evidence](docs/evidence/README.md) | Dated build and handset reports |
| [docs/history](docs/history/README.md) | Earlier planning and bring-up notes |
| [archive](archive/README.md) | Superseded standalone tools, with a move/provenance manifest |

Generated images, firmware archives, extracted ELF files and portable runtimes remain build artifacts rather than repository files. The old chronological README remains available in Git history.

## Development

Start with [Development and validation](docs/development.md) for source pins, build dependencies, image assembly and the current CI workflows. Windows launchers require the complete prepared package; they are not intended to run from a source checkout.

The new offline analysis tools complement binary inspection:

- [vmlinux-to-elf](https://github.com/marin-m/vmlinux-to-elf) recovers kernel symbols and an ELF suitable for ARM64 disassembly or Ghidra.
- [DTC / libfdt](https://github.com/dgibson/dtc) decodes and composes DTB/DTBO device trees.
- The reviewed Exynos 9820 QEMU fork has incomplete peripheral/UFS support and is not used as a full handset boot simulator.

Contributions should state which validation level supports a result and include image identities for hardware observations. The immediate objective is a confirmed first boot; hardware support and an update channel are later milestones.

## Upstream and attribution

This work builds on the [UBports Samsung Galaxy S10 community port](https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820), its matching Halium kernel, generic adaptation build tools, Ubuntu Touch images and TeamWin recovery. Exact source revisions are recorded in [upstream.lock.json](config/upstream.lock.json).

Third-party licensing and attribution are documented in [THIRD_PARTY.md](THIRD_PARTY.md). This repository does not imply official Samsung, TeamWin or UBports support for the resulting experimental image.
