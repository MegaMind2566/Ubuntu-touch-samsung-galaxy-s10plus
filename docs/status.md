# Project status

Updated: **15 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

**BOOT 5 starts Ubuntu systemd and the Android hardware container, then reboots on a kernel USB fault. Ubuntu Touch has not reached a confirmed graphical boot.** The exact 57,341,952-byte write/readback matches SHA-256 `0d66508e0ed7a415910bd731ab63fe1ff3308ce3dbbbb08490346a18b728a21b`; the apply checkpoint records `write_started` and `success`. The read-only collector finds two normal-boot attempts with the BOOT 5 kernel `4.14.280-gb9b70b29c94c-dirty`.

The first attempt records systemd 255.4 starting at 3.119406 seconds; its PID 1 executable is confirmed at 4.11 seconds. The second starts systemd at 6.321031 seconds. Android/Halium and the actual vendor HWC 2.2 service execute. VENDOR is mounted read-only from its expected raw partition. The selected cgroup hybrid hierarchy and legacy CPU/cpuset/memory controllers are visible at runtime. These reports do not support the earlier hypothesis of a lost VENDOR partition.

Both attempts then hit the same USB fault: `usb_moded` calls `symlinkat`, reaching Samsung `config_usb_cfg_link()` and `strcmp` with a NULL configuration string. Panics occur at 12.324995 and 15.783443 seconds, before graphical startup. The exact BOOT 5 ELF maps LR `config_usb_cfg_link+0x174` to `drivers/usb/gadget/configfs.c:579`; the string can legitimately remain NULL after creation of a configfs language directory and before its configuration attribute is written. The kernel's own attribute read path already accounts for this state.

The new observer captures systemd, its jobs/journal and Android properties; its trace survives the old Halium redirection. No retained old-root FDs or causal observer fault is shown. A minor multi-argument BusyBox `readlink` usage error affects part of the descriptor report; the later directory listing still supplies the descriptor evidence.

Separately, upstream overlay application skips missing destinations for the device YAML, force-HWC2 setting and LightDM wait file, plus nested Android RC adjustments. Vendor reports `beyond2`, which needs an alias in the canonical `beyond2lte` profile. Runtime tasks also show Samsung `install-recovery.sh`/`applypatch`; the pre-boot recovery checks do not establish the recovery hash after that attempt. The handset returned to TWRP, but a post-runtime prefix readback is still a separate check. The next BOOT package's existing recovery preflight performs it before writing.

The [BOOT 5 handset record](evidence/ubuntu-boot-5-handset-2026-10-15.json) retains the upload hashes, line references and validation limits. BOOT 4's [earlier handoff result](evidence/ubuntu-boot-4-handset-2026-10-15.json) and the immutable [BOOT 5 build record](evidence/ubuntu-boot-5-build-2026-10-15.json) remain historical evidence. Latest confirmed installed image: **BOOT 5**. Repository publication remains gated on a confirmed graphical boot.

## What has been verified

| Area | Evidence | Practical meaning |
| --- | --- | --- |
| Device and firmware | SM-G975F, Exynos 9820, Android/vendor 12, G975FXXSGHWC1 | The test uses a defined hardware and vendor baseline. |
| Bootloader and recovery | Unlock confirmed; prepared TWRP 3.7.0_9-2 opens; root ADB works | Recovery access is available for inspection and controlled writes. |
| Partition layout | Actual PIT and recovery measurements; no A/B slots | Image targets and size limits are known for this handset. |
| Recovery preparation | Modified RECOVERY and VBMETA match pinned hashes | The installed recovery removes TWRP's automatic `nuker` modifications. |
| SYSTEM and original BOOT | Physical image-prefix readback matches the installation pins | Those payloads were written correctly; this does not prove successful execution. |
| BOOT 1 and BOOT 2 updates | BOOT-only writes and readback verified | Both SAR fixes reached the BOOT partition. |
| Diagnostic 2 installed image | Exact 55,638,016-byte prefix readback matches its SHA-256 | That built-in diagnostic image was verified on the handset before BOOT 3. |
| Ubuntu BOOT 5 installed image | Exact 57,341,952-byte write/readback and successful apply checkpoint | Latest installed BOOT identity is confirmed. |
| Ubuntu userspace and Android container | BOOT 5 PID 1 executable, journal/jobs, Android init and HWC 2.2 properties | Actual userspace execution confirmed; graphical shell is not confirmed. |
| Normal kernel and diagnostic PID 1 | Versioned init/kernel markers with the matching compiled kernel | The forced built-in-initramfs route executes on this phone. |
| Runtime storage probes | Data mounted; SYSTEM Android image and VENDOR directories readable | No missing SYSTEM/VENDOR filesystem was demonstrated; this is not a full content comparison. |
| Runtime USB | PID 1 configfs success and kernel `USB_STATE=CONFIGURED` | USB gadget configuration works under the normal kernel; no shell was provided. |
| Vendor filesystem | Read-only filesystem check completed cleanly | No filesystem corruption was demonstrated; a full stock-content comparison was not performed. |

See the [evidence index](evidence/README.md) for the reports supporting these statements.

## Findings from offline analysis

Two source defects in the Samsung system-as-root ramdisk path have been corrected:

1. The ramdisk offset was accumulated from an uninitialized variable. Patch 0003 initializes it before computing the payload position.
2. `kernel_init_freeable()` cleared the init pointer before `prepare_namespace()` loaded the late ramdisk, without restoring it afterward. Patch 0004 rechecks the requested init and restores the pointer when it becomes available.

Source fixtures test those paths, but neither defect has been established as the complete cause of the handset's blocked boot. BOOT 2 still remains at the logo.

On 14 October, `vmlinux-to-elf` recovered **113,088 symbols from each of BOOT 1 and BOOT 2**. An independent ELF reader verified the mapped raw kernel bytes and the `_text` base. ARM64 disassembly confirms the additional access check and pointer restoration in the compiled BOOT 2. Diagnostic 1 used that same kernel. Diagnostic 2 and the Ubuntu BOOT family preserve those source fixes while adding their separately tested built-in initramfs route.

Pinned DTC 1.8.1 successfully decoded the stock base tree and applied DTBO entry 9, the index observed in TWRP on hardware revision 26. The resulting tree also decodes successfully. DTC reported 214 warnings for the base tree and 273 for the composed tree; these are retained in the report. This is an offline composition, not a capture of the normal-boot tree or proof that every custom-kernel driver binding matches. Diagnostic 2 now also reports `androidboot.dtbo_idx=9` and hardware revision 26 in its normal-kernel command line.

The reviewed Exynos 9820 QEMU fork uses stub peripheral responses and has incomplete UFS support. It is unsuitable as a complete reproduction of this handset's Linux boot.

## Next experiment

Build **BOOT 6** with the minimal USB configuration-string NULL guard. Preserve the working cgroup selection and original Ubuntu wrapper. Apply the small device/HWC destination directories in RAM, retain their existing files, and add the `beyond2` alias. After upstream overlay mounting and before its requiring Android container, apply the pinned Android RC files in RAM and mask Samsung's recovery-restoration script. Preparation failure must stop before the container can execute.

The current image accepted by the installer is exact BOOT 5 (`0d66508e...`, 57,341,952 bytes). The included rollback remains exact BOOT 4 (`f9264d38...`, 57,337,856 bytes), rather than the BOOT 5 image that now loops. Both roles are checked separately in the package and apply/restore fixtures. No SYSTEM/VENDOR write, partition change or Format Data is requested.

The USB helper regression cases pass on host and ARM64: the original code reaches `strcmp(NULL,...)`; the corrected helper handles eight list/string cases while preserving every non-NULL decision. All 31 ARM64 RAM-profile integration/rollback fixtures also pass. BOOT 6 compilation and final package validation are pending. Native Windows CI availability remains uncertain; any local portable tests will be identified separately. The next handset action will be one aggregated package, with no additional preliminary test requested.

## Milestones after a first boot

| Milestone | Status |
| --- | --- |
| Confirm normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October |
| Run the original Ubuntu ramdisk init and mount the intended SYSTEM | Confirmed by BOOT 3 and BOOT 4 on 15 October |
| Complete original initramfs cleanup and hand off to systemd | Confirmed by BOOT 5 on 15 October |
| Start Ubuntu userspace and the Halium Android container | Confirmed by BOOT 5 on 15 October; interrupted by USB kernel panic |
| Reach the graphical shell with working display and touch | Pending |
| Validate charging, suspend, Wi-Fi, Bluetooth, modem/calls/SMS, audio, camera and sensors | Untested |
| Define repeatable installation, updates and recovery for other users | Pending |

This repository is a bring-up project, not a supported-device release or a daily-use ROM.

## Publication criterion

Keep the repository private during the current boot investigation. Publish it after Ubuntu Touch reaches its graphical shell on the test handset, with the observed screen, available runtime logs and exact BOOT/SYSTEM identities recorded in `docs/evidence/`. Update this status and the README to show the successful boot and the measured hardware support. Untested features remain explicitly marked as untested in the public project.
