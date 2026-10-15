# Project status

Updated: **15 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

The Halium 12 adaptation and Ubuntu Touch 24.04 SYSTEM image have been built and inspected. The test handset accepts the prepared TWRP recovery and the experimental images can be written and read back with matching hashes. **Ubuntu Touch has not reached a confirmed working boot.** Normal BOOT versions 0, 1 and 2 remained at the Samsung Galaxy S10+ logo.

A temporary diagnostic BOOT 1 is installed. Its kernel is byte-identical to BOOT 2; its ramdisk replaces Ubuntu's init with a small diagnostic program. The report received on 15 October reconfirms its exact BOOT hash and shows `/data` mounted in TWRP, but no diagnostic data logs were found. Its `last_kmsg` is S-Boot entering recovery after a pin reset, with explicit debug-buffer clearing. It does not contain an identifiable normal-kernel trace. Kernel/PID 1 execution remains unconfirmed.

Diagnostic 2 has been built to place a minimal initramfs inside the kernel and use it before the late SYSTEM-dependent ramdisk path. Its Linux image checks and native Windows apply/restore tests passed. The 55,638,016-byte BOOT fits the measured 57,671,680-byte partition, and its kernel configuration differs from BOOT 2 only in six initramfs-related symbols. This is a controlled observation experiment; it does not start Ubuntu. The latest confirmed physical BOOT remains diagnostic 1 until the next handset test.

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
| Diagnostic 1 log collection | BOOT matches; Data is mounted; no PID 1 marker; recovery S-Boot buffer only | The kernel's actual normal-boot stage is still unknown. |
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

Test the validated diagnostic 2 package once on the handset:

1. Copy the contents of **`UbuntuTouch-S10plus-test-AVVIO-2-Windows.zip`** into the original prepared installation folder, merging directories and replacing matching files.
2. With TWRP open and USB connected, keep SYSTEM/VENDOR unmounted and Data available. Run **`INSTALLA-TEST-AVVIO-2.cmd`**. The installer accepts only the exact diagnostic 1 BOOT reconfirmed in the latest report. Continue only after its write/readback success message.
3. Select TWRP **Reboot > System** manually, wait 60 seconds and photograph the screen. The expected diagnostic screen says **`UBUNTU TOUCH TEST 2`**; record the Samsung logo too if it remains there.
4. Return to TWRP and run **`LEGGI-TEST-AVVIO-2.cmd`**. Inspect **`ubuntu-boot-diagnostic-2-log-report.zip`** together with the observed screen and new BOOT identity. **`RIPRISTINA-TEST-AVVIO-1.cmd`** restores the exact previous diagnostic BOOT if required.

The [build record](evidence/early-boot-diagnostic-build-2026-10-15.json) pins the image and ZIP, verifies the embedded CPIO and unchanged peripheral configuration, and records actual ARM64 helper execution, four source force-guard cases, six collector fixtures and 24 native Windows apply/restore cases. `CONFIG_INITRAMFS_FORCE` plus a diagnostic-only guard change makes the built-in rootfs available even if `skip_initramfs` is supplied.

The installer targets only BOOT. The collector is read-only. SYSTEM/VENDOR and the existing userdata format are preserved; the running diagnostic creates its own bounded data logs.

### How the next report selects the next experiment

Start with `diagnostic_boot_matches` and the recorded screen. Pair runtime observations with the image identity checked by the collector.

| Observation | Conclusion and next action |
| --- | --- |
| Installed BOOT hash differs from the diagnostic pin | Establish the actual installed image before attributing logs to this diagnostic or preparing another update. |
| The selected version's PID 1 marker is present (`UT_DIAG_2` for test 2) | The controlled ramdisk executed. Inspect its kernel, storage and display results to decide where to instrument the original Ubuntu init. |
| No data marker, but previous-boot buffers contain an identifiable normal-kernel failure | Use the earliest failure and its surrounding trace to select a focused kernel or device-tree experiment. |
| Data logs are missing and recovery's mount list shows `/data` unavailable | Saved-data evidence is unavailable in that collection; inspect the remaining buffers without treating this as a failed PID 1 execution. |
| No diagnostic marker or identifiable previous-boot trace | The failing stage remains unknown. Define an earlier observation point before preparing another BOOT image. |

The diagnostic preserves an existing log directory, so retained markers prove a recorded diagnostic execution, not necessarily the most recent attempt. The observed screen and experiment history remain part of interpreting the report.

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

## Publication criterion

Keep the repository private during the current boot investigation. Publish it after Ubuntu Touch reaches its graphical shell on the test handset, with the observed screen, available runtime logs and exact BOOT/SYSTEM identities recorded in `docs/evidence/`. Update this status and the README to show the successful boot and the measured hardware support. Untested features remain explicitly marked as untested in the public project.
