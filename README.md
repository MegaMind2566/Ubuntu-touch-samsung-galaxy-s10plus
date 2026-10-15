# Ubuntu Touch for Samsung Galaxy S10+

An experimental **Ubuntu Touch 24.04 / Halium 12** bring-up project for the **Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`)**. The goal is to reach a working Ubuntu Touch boot on the Android 12 firmware/vendor baseline, then validate the device hardware and establish a repeatable installation path.

**Current stage: original Ubuntu init executes and mounts SYSTEM; userspace and graphical startup remain unconfirmed.** BOOT 3 has executed on the test handset with matching physical readback. Two attempts mounted the Ubuntu root filesystem, its embedded Android image and Data. Their last saved stage is `root-mounted`; Ubuntu services and the graphical shell have not been confirmed. BOOT 4 is ready with bounded shell tracing and passive wait sampling to locate the next failure.

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
| Original Ubuntu init, intended SYSTEM and embedded Android mounts | Confirmed twice by BOOT 3 on the handset |
| Reach Ubuntu userspace and the graphical shell | Not achieved |
| Validate modem, networking, audio, camera, sensors and suspend | Untested |

The detailed [current status](docs/status.md) distinguishes source checks, host tests, physical readback and actual runtime observations. Its conclusions link to the [evidence index](docs/evidence/README.md).

## Current boot investigation

The [BOOT 3 handset report](docs/evidence/ubuntu-boot-3-handset-2026-10-15.json) confirms original Ubuntu init execution and the intended root mounts. Both recorded attempts last saved `root-mounted`. The user observed a black screen followed by a reboot on the first attempt, then a stationary Samsung screen on the second. The trace sent directly to `/dev/kmsg` loses most shell-command text, so the exact subsequent wait or failure is still unknown. The original udev cleanup moves devtmpfs to `/root/dev`; the BOOT 3 logger then rejects the changed canonical userdata path and stops saving snapshots. Therefore `root-mounted` alone does not locate the actual stall. BOOT 4 accepts both exact raw-node paths, with a regression test. Android API 32 is recognized, while device-name and Android fstab discovery report warnings. These findings do not demonstrate missing or erased vendor contents.

BOOT 4 keeps the forced built-in-initramfs route and the original Ubuntu mount logic, adding bounded regular-file tracing, passive PID 1/child wait samples and finer cleanup/udev checkpoints. It also removes global filesystem sync from the observer's PID 1 path; no claim is made that sync caused the failure. Linux/ARM64 checks and 24 native Windows apply/restore cases passed. The [BOOT 4 build record](docs/evidence/ubuntu-boot-4-build-2026-10-15.json) pins the tested 57,337,856-byte BOOT and Windows ZIP. The package writes only BOOT from the exact installed BOOT 3 and includes that image as rollback. Its handset result is pending.

The earlier [diagnostic 2 execution](docs/evidence/boot-diagnostic-2-handset-2026-10-15.json), [BOOT 3 build](docs/evidence/ubuntu-boot-3-build-2026-10-15.json), and [symbol/device-tree analysis](docs/evidence/offline-tools-2026-10-14.json) remain traceable evidence. See [current status](docs/status.md#next-experiment) for the next test and unverified milestones.

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
