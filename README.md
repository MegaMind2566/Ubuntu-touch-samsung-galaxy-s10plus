# Ubuntu Touch for Samsung Galaxy S10+

An experimental **Ubuntu Touch 24.04 / Halium 12** bring-up project for the **Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`)**. The goal is to reach a working Ubuntu Touch boot on the Android 12 firmware/vendor baseline, then validate the device hardware and establish a repeatable installation path.

**Current stage: Ubuntu initramfs handoff. Ubuntu Touch has not yet booted successfully on the test handset.** Diagnostic 2 now confirms execution of the Halium kernel and its diagnostic PID 1 on the phone. Data, SYSTEM and VENDOR are readable, and USB ACM configuration works. The next BOOT runs the original Ubuntu initramfs through that verified built-in route, with saved stages to locate any remaining userspace failure.

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
| Run the original Ubuntu initramfs via the built-in route | BOOT 3 in preparation; handset result pending |
| Reach Ubuntu userspace and the graphical shell | Not achieved |
| Validate modem, networking, audio, camera, sensors and suspend | Untested |

The detailed [current status](docs/status.md) distinguishes source checks, host tests, physical readback and actual runtime observations. Its conclusions link to the [evidence index](docs/evidence/README.md).

## Current boot investigation

The phone now executes the Halium 4.14.280 kernel and the built-in diagnostic initramfs. The [15 October handset report](docs/evidence/boot-diagnostic-2-handset-2026-10-15.json) matches the tested diagnostic 2 BOOT and contains the PID 1 marker, readable storage and USB configuration. This confirms the earlier kernel-to-initramfs milestone; it does not start Ubuntu.

The diagnostic framebuffer helper could not use the reported fb0 layout. A retained panic tail includes the same diagnostic kernel banner, but omits the initiating message. Neither observation is a complete diagnosis of the remaining Ubuntu boot failure.

BOOT 3 keeps the tested forced built-in-initramfs path and replaces the temporary diagnostic program with the complete original Ubuntu initramfs. Three scripts gain stage observations; the existing rootfs and Android-container mount logic remains. The one-off attempt skips the upstream automatic userdata repair and resize, preserves SYSTEM/VENDOR and collects bounded logs. It is still awaiting host validation and the handset test.

Earlier [symbol and device-tree inspection](docs/evidence/offline-tools-2026-10-14.json) and the two SAR fixes remain documented. The late external ramdisk route has not been proved to work on the phone. See [the current procedure and remaining milestones](docs/status.md#next-experiment).

## Repository map

| Location | Contents |
| --- | --- |
| [config](config) | Source, configuration and installation image pins |
| [patches/kernel](patches/kernel) | AppArmor and Samsung SAR kernel fixes |
| [patches/diagnostic](patches/diagnostic) | Forced built-in-initramfs change shared by diagnostic 2 and Ubuntu BOOT 3 |
| [scripts](scripts/README.md) | Maintained build, inspection, packaging and shared support code |
| [scripts/templates](scripts/templates) | Shared verified BOOT installer/image-verifier templates |
| [tools/boot-diagnostic](tools/boot-diagnostic) | Original diagnostic input and static ARM64 display helper |
| [tools/boot-observer](tools/boot-observer) | Bounded Ubuntu initramfs stage capture |
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
