# Project status

Updated: **14 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

The Halium 12 adaptation and Ubuntu Touch 24.04 SYSTEM image have been built and inspected. The test handset accepts the prepared TWRP recovery and the experimental images can be written and read back with matching hashes. **Ubuntu Touch has not reached a confirmed working boot.** Normal BOOT versions 0, 1 and 2 remained at the Samsung Galaxy S10+ logo.

A temporary diagnostic BOOT is now installed. Its kernel is byte-identical to BOOT 2; its ramdisk replaces Ubuntu's init with a small diagnostic program. Successful installation and readback are confirmed. Execution of that kernel and diagnostic PID 1 is still unconfirmed. The latest uploaded `dmesg` and recovery logs describe the running TWRP kernel, not the preceding normal boot.

## What has been verified

| Area | Evidence | Practical meaning |
| --- | --- | --- |
| Device and firmware | SM-G975F, Exynos 9820, Android/vendor 12, G975FXXSGHWC1 | The test uses a defined hardware and vendor baseline. |
| Bootloader and recovery | Unlock confirmed; prepared TWRP 3.7.0_9-2 opens; root ADB works | Recovery access is available for inspection and controlled writes. |
| Partition layout | Actual PIT and recovery measurements; no A/B slots | Image targets and size limits are known for this handset. |
| Recovery preparation | Modified RECOVERY and VBMETA match pinned hashes | The installed recovery removes TWRP's automatic `nuker` modifications. |
| SYSTEM and original BOOT | Physical image-prefix readback matches the installation pins | Those payloads were written correctly; this does not prove successful execution. |
| BOOT 1 and BOOT 2 updates | BOOT-only writes and readback verified | Both SAR fixes reached the BOOT partition. |
| Diagnostic BOOT | Exact 53,475,328-byte prefix readback matches its SHA-256 | The temporary diagnostic payload is installed. |
| Vendor filesystem | Read-only filesystem check completed cleanly | No filesystem corruption was demonstrated; a full stock-content comparison was not performed. |

See the [evidence index](evidence/README.md) for the reports supporting these statements.

## Findings from offline analysis

Two source defects in the Samsung system-as-root ramdisk path have been corrected:

1. The ramdisk offset was accumulated from an uninitialized variable. Patch 0003 initializes it before computing the payload position.
2. `kernel_init_freeable()` cleared the init pointer before `prepare_namespace()` loaded the late ramdisk, without restoring it afterward. Patch 0004 rechecks the requested init and restores the pointer when it becomes available.

Source fixtures test those paths, but neither defect has been established as the complete cause of the handset's blocked boot. BOOT 2 still remains at the logo.

On 14 October, `vmlinux-to-elf` recovered **113,088 symbols from each of BOOT 1 and BOOT 2**. An independent ELF reader verified the mapped raw kernel bytes and the `_text` base. ARM64 disassembly confirms the additional access check and pointer restoration in the compiled BOOT 2. This also applies to the byte-identical kernel in the current diagnostic image.

Pinned DTC 1.8.1 successfully decoded the stock base tree and applied DTBO entry 9, the index observed in TWRP on hardware revision 26. The resulting tree also decodes successfully. DTC reported 214 warnings for the base tree and 273 for the composed tree; these are retained in the report. This is an offline composition, not a capture of the normal-boot tree or proof that every custom-kernel driver binding matches.

The reviewed Exynos 9820 QEMU fork uses stub peripheral responses and has incomplete UFS support. It is unsuitable as a complete reproduction of this handset's Linux boot.

## Next experiment

Collect the result of the diagnostic image already installed:

1. Record whether the normal-boot attempt displayed `UBUNTU TOUCH TEST 1`, another diagnostic status, or the Samsung logo.
2. Return to TWRP with USB connected and run the already delivered **`LEGGI-TEST-AVVIO.cmd`**.
3. Inspect **`ubuntu-boot-diagnostic-log-report.zip`**, including any diagnostic data, pstore/last-kmsg and BOOT identity. A report with no diagnostic markers remains useful, but marker absence alone does not prove that the kernel never ran.
4. Use the earliest observed boot stage to choose the next change. Preserve the measured stock/vendor baseline and keep any new experiment limited to the component being tested.

The collector is read-only. This step does not require another Format Data, SYSTEM write or speculative VENDOR replacement.

## Milestones after a first boot

| Milestone | Status |
| --- | --- |
| Confirm normal kernel and diagnostic PID 1 execution | Pending |
| Run the original Ubuntu ramdisk init and mount the intended SYSTEM | Pending |
| Start Ubuntu userspace and the Halium Android container | Pending |
| Reach the graphical shell with working display and touch | Pending |
| Validate charging, suspend, Wi-Fi, Bluetooth, modem/calls/SMS, audio, camera and sensors | Untested |
| Define repeatable installation, updates and recovery for other users | Pending |

This repository is a bring-up project, not a supported-device release or a daily-use ROM.
