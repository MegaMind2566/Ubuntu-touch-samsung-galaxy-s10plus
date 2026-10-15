# Project status

Updated: **15 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

The Halium 12 adaptation and Ubuntu Touch 24.04 SYSTEM image have been built and inspected. The test handset accepts the prepared TWRP recovery and the experimental images can be written and read back with matching hashes. **Ubuntu Touch has not reached a confirmed working boot.** Normal BOOT versions 0, 1 and 2 remained at the Samsung Galaxy S10+ logo.

**Diagnostic 2 has now executed on the handset.** The second uploaded collection matches BOOT SHA-256 `7d65acf13c1180b4ba77dfdd96a703546bc5b7083fb2e85714151203b740076d` and records `UT_DIAG_2: PID 1 STARTED` in both the init and kernel logs. Its kernel is `4.14.280-gb9b70b29c94c-dirty`, compiled on 15 October. Data mounted read-write; SYSTEM and VENDOR mounted for read-only probes. The expected Android rootfs image is present, and configfs ACM reached `USB_STATE=CONFIGURED`.

The first collection stopped at `no devices found`; the later collection succeeded. The framebuffer helper reported an unsupported or unavailable layout. Pstore contains a panic tail with the same diagnostic kernel build banner but no initiating message. The unbounded last-kmsg request exceeded its output cap; a separate bounded start read is present. These limits do not invalidate the captured PID 1 execution, but the panic cause and complete graphics support are still unknown.

The latest physical BOOT is diagnostic 2. **The test never executes the original Ubuntu init, so it is not a successful Ubuntu boot.** BOOT 3 now embeds the full original Ubuntu initramfs, with stage capture, through this verified route. Its Linux/ARM64 and native Windows checks have passed; it is ready for the next handset attempt.

## What has been verified

| Area | Evidence | Practical meaning |
| --- | --- | --- |
| Device and firmware | SM-G975F, Exynos 9820, Android/vendor 12, G975FXXSGHWC1 | The test uses a defined hardware and vendor baseline. |
| Bootloader and recovery | Unlock confirmed; prepared TWRP 3.7.0_9-2 opens; root ADB works | Recovery access is available for inspection and controlled writes. |
| Partition layout | Actual PIT and recovery measurements; no A/B slots | Image targets and size limits are known for this handset. |
| Recovery preparation | Modified RECOVERY and VBMETA match pinned hashes | The installed recovery removes TWRP's automatic `nuker` modifications. |
| SYSTEM and original BOOT | Physical image-prefix readback matches the installation pins | Those payloads were written correctly; this does not prove successful execution. |
| BOOT 1 and BOOT 2 updates | BOOT-only writes and readback verified | Both SAR fixes reached the BOOT partition. |
| Diagnostic 2 installed image | Exact 55,638,016-byte prefix readback matches its SHA-256 | The tested built-in diagnostic image is on the handset. |
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

On 14 October, `vmlinux-to-elf` recovered **113,088 symbols from each of BOOT 1 and BOOT 2**. An independent ELF reader verified the mapped raw kernel bytes and the `_text` base. ARM64 disassembly confirms the additional access check and pointer restoration in the compiled BOOT 2. This also applies to the byte-identical kernel in the current diagnostic image.

Pinned DTC 1.8.1 successfully decoded the stock base tree and applied DTBO entry 9, the index observed in TWRP on hardware revision 26. The resulting tree also decodes successfully. DTC reported 214 warnings for the base tree and 273 for the composed tree; these are retained in the report. This is an offline composition, not a capture of the normal-boot tree or proof that every custom-kernel driver binding matches. Diagnostic 2 now also reports `androidboot.dtbo_idx=9` and hardware revision 26 in its normal-kernel command line.

The reviewed Exynos 9820 QEMU fork uses stub peripheral responses and has incomplete UFS support. It is unsuitable as a complete reproduction of this handset's Linux boot.

## Next experiment

Test the validated **Ubuntu BOOT 3** package once on the handset. Its complete original Ubuntu initramfs is compressed into the kernel and also retained as the external ramdisk. It shares diagnostic 2's force guard and peripheral settings. The original rootfs/container logic is kept, with staged kernel-log snapshots to Data. The previous automatic `e2fsck -y` and userdata resize call block is skipped for this already-formatted, readable filesystem.

The package accepts only the exact diagnostic 2 BOOT above, writes only `/dev/block/sda14`, reads it back, and includes the exact diagnostic 2 rollback. No SYSTEM/VENDOR rewrite, repartitioning or Format Data is required. The collector uses bounded last-kmsg reads and captures up to five recorded initramfs attempts without mounting or writing anything on the phone.

The [passing build record](evidence/ubuntu-boot-3-build-2026-10-15.json) identifies BOOT SHA-256 `33e9b86294bce1d7bb61ae0b44af1186ef788bbcdc7137e945a1331e8f0718cc`, its 57,335,808-byte size and the delivered ZIP. It verifies the exact embedded/external CPIO, four initramfs-only configuration differences, ARM64 logging guards, the no-recompression regression, seven collector cases and 24 native Windows apply/restore cases. USB and raw writes in CI are simulated. The compiled image itself is preserved across host packaging fixes.

The handset sequence is:

1. Merge **`UbuntuTouch-S10plus-avvio-Ubuntu-3-Windows.zip`** into the original prepared installation folder.
2. With TWRP open and USB connected, run **`INSTALLA-AVVIO-UBUNTU-3.cmd`** and require write/readback success.
3. Choose **Reboot > System** manually. Decline the optional TWRP app. Wait up to three minutes and photograph the screen.
4. If blocked, return to TWRP and run **`LEGGI-AVVIO-UBUNTU-3.cmd`**. Inspect **`ubuntu-boot-3-log-report.zip`**, its image identity, stage records, available userspace logs and the observed screen together.

A `userspace-handoff` stage proves only that the initramfs prepared its handoff. It does not prove that systemd, the Android container or the graphical shell ran. Saved attempts are preserved, so retained markers are not automatically evidence of the latest reboot. **`RIPRISTINA-TEST-AVVIO-2.cmd`** restores the previous diagnostic BOOT if needed; it does not restore stock Android or a working Ubuntu image.

## Milestones after a first boot

| Milestone | Status |
| --- | --- |
| Confirm normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October |
| Run the original Ubuntu ramdisk init and mount the intended SYSTEM | Pending |
| Start Ubuntu userspace and the Halium Android container | Pending |
| Reach the graphical shell with working display and touch | Pending |
| Validate charging, suspend, Wi-Fi, Bluetooth, modem/calls/SMS, audio, camera and sensors | Untested |
| Define repeatable installation, updates and recovery for other users | Pending |

This repository is a bring-up project, not a supported-device release or a daily-use ROM.

## Publication criterion

Keep the repository private during the current boot investigation. Publish it after Ubuntu Touch reaches its graphical shell on the test handset, with the observed screen, available runtime logs and exact BOOT/SYSTEM identities recorded in `docs/evidence/`. Update this status and the README to show the successful boot and the measured hardware support. Untested features remain explicitly marked as untested in the public project.
