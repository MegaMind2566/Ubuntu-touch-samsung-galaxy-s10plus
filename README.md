# Ubuntu Touch for Samsung Galaxy S10+

An experimental **Ubuntu Touch 24.04 / Halium 12** bring-up project for the **Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`)**. The goal is to reach a working Ubuntu Touch boot on the Android 12 firmware/vendor baseline, then validate the device hardware and establish a repeatable installation path.

**Current stage: first-boot investigation. Ubuntu Touch has not yet booted successfully on the test handset.** The adaptation and SYSTEM image are built, recovery works, and image writes have been verified by readback. Normal boot remains at the Samsung logo. The first diagnostic report confirms the installed image but contains no PID 1 marker. A second test with its diagnostic initramfs inside the kernel has passed Linux and Windows host checks and is ready for the handset.

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
| Install the controlled diagnostic BOOT | Write and exact readback confirmed |
| Collect the first diagnostic result | BOOT identity confirmed; no saved PID 1 marker or normal-kernel trace |
| Build a diagnostic initramfs inside the kernel | Built and host-tested; awaiting the handset attempt |
| Confirm normal kernel / diagnostic PID 1 execution | Still unconfirmed |
| Reach Ubuntu userspace and the graphical shell | Not achieved |
| Validate modem, networking, audio, camera, sensors and suspend | Untested |

The detailed [current status](docs/status.md) distinguishes source checks, host tests, physical readback and actual runtime observations. Its conclusions link to the [evidence index](docs/evidence/README.md).

## Current boot investigation

The kernel uses Samsung's late system-as-root ramdisk loading path. Two defects in that path were corrected, but BOOT 2 still remained at the logo. The installed diagnostic image keeps the exact BOOT 2 kernel and uses a small temporary init to report how far normal boot gets; it does not start Ubuntu.

Offline analysis has now recovered **113,088 kernel symbols** from BOOT 1 and BOOT 2 and confirmed the compiled init-handoff correction. Pinned DTC also decodes the stock tree and applies the TWRP-selected overlay. These results narrow the investigation; they do not demonstrate normal execution on the phone.

The report collected on 15 October matches diagnostic BOOT 1 and shows `/data` mounted in TWRP, but the diagnostic data logs are absent. Its `last_kmsg` contains S-Boot entering recovery and clearing debug buffers after a pin reset; it is not a trace of the blocked normal kernel. These observations do not identify the exact failing stage.

The next experiment embeds a minimal diagnostic initramfs in the kernel and forces that built-in payload to be used, so PID 1 can run before mounting SYSTEM. The build verified that peripheral configuration and the external ramdisk remain unchanged. The generated Windows package passed 24 guarded apply/restore cases and its native CMD checks. See the [diagnostic 2 build record](docs/evidence/early-boot-diagnostic-build-2026-10-15.json) and [handset procedure](docs/status.md#next-experiment). These host results do not confirm handset execution.

See [the diagnostic procedure and remaining milestones](docs/status.md#next-experiment).

## Repository map

| Location | Contents |
| --- | --- |
| [config](config) | Source, configuration and installation image pins |
| [patches/kernel](patches/kernel) | AppArmor and Samsung SAR kernel fixes |
| [patches/diagnostic](patches/diagnostic) | Conditional built-in-initramfs change used only by the second diagnostic |
| [scripts](scripts/README.md) | Maintained build, inspection, packaging and shared support code |
| [scripts/templates](scripts/templates) | Shared verified BOOT installer/image-verifier templates |
| [tools/boot-diagnostic](tools/boot-diagnostic) | Temporary init and static ARM64 display helper |
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
