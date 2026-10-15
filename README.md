# Ubuntu Touch for Samsung Galaxy S10+

An experimental **Ubuntu Touch 24.04 / Halium 12** bring-up project for the **Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`)**. The goal is to reach a working Ubuntu Touch boot on the Android 12 firmware/vendor baseline, then validate the device hardware and establish a repeatable installation path.

**Current stage: BOOT 6 reaches the Ubuntu Touch boot screen, but the Lomiri graphical session aborts.** The installed image matches exact physical readback. Its first normal run keeps systemd alive beyond two minutes with Android, HWC 2.2 and the system compositor running. Lomiri repeatedly reports `gralloc-mapper is missing`; the specific Vendor loading failure is still being identified.

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
| BOOT 5 compatibility image and prepared test package | Applied and read back; subsequent USB panic identified |
| BOOT 6 USB correction and RAM profiles | Exact write/readback; RAM bindings and Android/HWC confirmed; no old USB panic in the retained two-minute run |
| Ubuntu systemd, Android container and HWC 2.2 | Confirmed by BOOT 6 runtime logs |
| Reach the graphical shell | Unconfirmed |
| Validate modem, networking, audio, camera, sensors and suspend | Untested |

The detailed [current status](docs/status.md) distinguishes source checks, host tests, physical readback and actual runtime observations. Its conclusions link to the [evidence index](docs/evidence/README.md).

## Current boot investigation

The latest [BOOT 6 handset record](docs/evidence/ubuntu-boot-6-handset-2026-10-15.json) confirms the exact installation and a matching later BOOT readback. The RAM profile hook completes, Android reports boot complete and HWC 2.2 runs. The root compositor/spinner starts; Lomiri then repeatedly aborts with `gralloc-mapper is missing`. The first run remains alive through 120.10 seconds. A panel power-down is logged; a later whole-device power-off is not established within that window.

The only retained panic is a six-second Power/Volume Down reset hook in a different attempt. It does not establish a new spontaneous kernel fault. The first read-only graphics collector hit an unsupported TWRP `stat` option and returned no logs; it did independently confirm the installed BOOT and post-runtime prepared recovery. The next step is the revised [graphics collector, version 2](docs/evidence/ubuntu-graphics-collector-2026-10-15.json), to retrieve USC/greeter/session stderr and identify the Vendor mapper loading error. No new BOOT, driver replacement or Format Data is requested.

The [BOOT 5 handset record](docs/evidence/ubuntu-boot-5-handset-2026-10-15.json) confirms its exact write/readback and two actual Ubuntu systemd starts. The Android container mounts VENDOR read-only and reports the HWC 2.2 service running. Both attempts then panic while `usb_moded` creates a configfs link: Samsung's `is_symboliclink_change_mode()` passes a configuration string to `strcmp` before that string has been assigned. The precise fault was mapped to the compiled BOOT 5 ELF and pinned kernel source.

A separate integration defect prevents the device YAML, HWC2 setting and LightDM wait configuration from being applied: the overlay destination files are missing. The nested Android RC adjustments are also skipped. A stock `install-recovery.sh` attempt is present in the runtime tasks; BOOT 6 includes a RAM mask for that script before starting the Android container. The revised evidence also includes a matching prepared recovery readback after runtime; no post-runtime VBMETA hash is available.

BOOT 6 retains the working handoff/cgroup selection and adds the minimal USB NULL guard plus bounded RAM profile bindings. Its installer requires the exact physical BOOT 5 as the current image while retaining BOOT 4 as rollback. No new SYSTEM/VENDOR flash or Format Data is requested. The [BOOT 6 build record](docs/evidence/ubuntu-boot-6-build-2026-10-15.json) records the compiled USB NULL branch, 33 ARM64 RAM-profile cases and 25 portable PowerShell control-flow cases. Native Windows CI received no runner; a graphical boot is not claimed. See [current status](docs/status.md#next-experiment) for the next test and [evidence](docs/evidence/README.md) for earlier build and handset records.

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
