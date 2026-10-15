# Ubuntu Touch for Samsung Galaxy S10+

An experimental **Ubuntu Touch 24.04 / Halium 12** port for the **Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`)**. The project has reached its first user-confirmed graphical boot. The goal now is to stabilize that boot, validate the remaining hardware and establish a repeatable installation path.

**Current result: Ubuntu Touch boots, and the test user reports working touch and Wi-Fi.** This follows graphics permission correction 1 on the existing BOOT 6. The [first graphical boot record](docs/evidence/ubuntu-first-graphical-boot-2026-10-15.json) documents the user confirmation that meets the publication milestone. A screenshot and a fresh correction/runtime log report are still pending; the earlier readback and runtime evidence described below predates this successful session.

Status updated **15 October 2026**. This is a development port. Daily-use reliability, complete hardware support and an update channel remain unvalidated.

## Tested baseline

| Item | Target |
| --- | --- |
| Phone | Galaxy S10+ Exynos, SM-G975F/DS |
| Codename / SoC | `beyond2lte` / Exynos 9820 |
| Firmware | G975FXXSGHWC1, Android 12 / One UI 4.1, ITV/OXM |
| Ubuntu userspace | Ubuntu Touch 24.04 arm64 |
| Current configuration | BOOT 6 with graphics permission correction 1 on userdata |
| Adaptation | Community Samsung Halium 12 sources with local kernel and configuration fixes |
| Storage | Measured A-only Samsung partition layout; SYSTEM and BOOT installation |

Snapdragon variants and other Galaxy S10 models are outside the tested scope. The [BOOT 6 handset record](docs/evidence/ubuntu-boot-6-handset-2026-10-15.json) identifies the earlier measured image readback.

## Hardware status

| Function | Current evidence |
| --- | --- |
| Graphical Ubuntu Touch session | Started, confirmed by the test user after correction 1 |
| Touchscreen | Working, confirmed by the test user in that session |
| Wi-Fi | Working, confirmed by the test user in that session |
| Repeated reboot, long-running stability and thermals | Pending validation |
| Charging, battery reporting and suspend/resume | Pending validation |
| Modem, calls, SMS and mobile data | Untested |
| Audio and microphone | Untested |
| Camera | Untested |
| Bluetooth, GPS and sensors | Untested |

Previous normal-boot logs independently establish Ubuntu systemd execution, Android boot completion, HWC 2.2 and the Mali/OpenGL display path.

## Boot fixes and evidence

BOOT 6 combines corrections to the Samsung system-as-root init handoff, a USB configfs NULL guard and guarded RAM device/Android profiles. It preserves the verified image layout and reaches Ubuntu userspace without rewriting SYSTEM or VENDOR for those profile changes. The [BOOT 6 build record](docs/evidence/ubuntu-boot-6-build-2026-10-15.json) and [handset record](docs/evidence/ubuntu-boot-6-handset-2026-10-15.json) separate source tests, compiled checks, physical readback and runtime execution.

The remaining graphical failure was an access problem: root loaded Mapper 2.0, while phablet and lightdm received `EACCES` on `/dev/hwbinder`, which was root-owned with mode 0600. `/dev/ion` was also restricted. The [runtime comparison](docs/evidence/ubuntu-graphics-runtime-probe-2026-10-15.json) records that diagnosis. [Graphics permission correction 1](docs/evidence/ubuntu-graphics-permission-fix-2026-10-15.json) supplies the intended access for those two devices through dedicated udev/systemd configuration on userdata, before LightDM starts. The user reports the successful graphical boot after that correction.

The [current status](docs/status.md) and [evidence index](docs/evidence/README.md) retain the detailed findings and validation limits.

## Next work

1. Record the successful session with a screenshot, fresh correction logs and the tested image/configuration identities.
2. Check repeat boots, display/touch/Wi-Fi stability, charging, suspend/resume and thermals.
3. Bring up the remaining hardware and define a repeatable installation, recovery and update process for other users.

Keep the graphics correction installed on the working test handset. The current Windows packages are guarded development tools for their documented image states; a clean-install procedure for other users is still being validated.

## Repository map

| Location | Contents |
| --- | --- |
| [config](config) | Source, configuration and installation image pins |
| [patches/kernel](patches/kernel) | AppArmor, Samsung SAR and USB configuration fixes |
| [patches/diagnostic](patches/diagnostic) | Forced built-in-initramfs change shared by diagnostic 2 and the Ubuntu BOOT family |
| [scripts](scripts/README.md) | Maintained build, inspection, packaging and shared support code |
| [scripts/templates](scripts/templates) | Shared verified BOOT installer/image-verifier templates |
| [tools/boot-diagnostic](tools/boot-diagnostic) | Original diagnostic input and static ARM64 display helper |
| [tools/boot-observer](tools/boot-observer) | Bounded tracing, post-root observation and guarded RAM device/Android profiles |
| [tools/graphics-permissions](tools/graphics-permissions) | Targeted persistent hwbinder/ion access correction before LightDM on BOOT 6 |
| [tools/graphics-probe](tools/graphics-probe) | Bounded mapper inspection; retained for comparison and removal of the installed diagnostic |
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

Contributions should state which validation level supports a result and include image identities for hardware observations. The next objectives are stable reboot/display behavior, validation of the remaining hardware and a repeatable installation path. An update channel has not yet been established.

## Upstream and attribution

This work builds on the [UBports Samsung Galaxy S10 community port](https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820), its matching Halium kernel, generic adaptation build tools, Ubuntu Touch images and TeamWin recovery. Exact source revisions are recorded in [upstream.lock.json](config/upstream.lock.json).

Third-party licensing and attribution are documented in [THIRD_PARTY.md](THIRD_PARTY.md). This repository does not imply official Samsung, TeamWin or UBports support for the resulting experimental image.
