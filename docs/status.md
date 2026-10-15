# Project status

Updated: **15 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

The Halium 12 adaptation and Ubuntu Touch 24.04 SYSTEM image have been built and inspected. The test handset accepts the prepared TWRP recovery and the experimental images can be written and read back with matching hashes. **Ubuntu Touch has not reached a confirmed working boot.** Normal BOOT versions 0, 1 and 2 remained at the Samsung Galaxy S10+ logo.

**Ubuntu BOOT 3 has now executed the original Ubuntu init on the handset.** Its BOOT-only write and readback match SHA-256 `33e9b86294bce1d7bb61ae0b44af1186ef788bbcdc7137e945a1331e8f0718cc`. Both recorded attempts mount the intended SYSTEM read-only at `/root`, its embedded Android image read-only at `/root/var/lib/lxc/android/rootfs`, and Data read-write at `/root/userdata`. The original writable-path bindings are present.

Both attempts last saved `root-mounted`. The user observed a black screen followed by a reboot on the first attempt, then a stationary Samsung screen on the second. No `init-bottom-complete`, userspace handoff, Ubuntu systemd PID 1 or graphical shell is confirmed. Most detailed shell trace records sent directly to `/dev/kmsg` are empty. The original udev cleanup moves devtmpfs to `/root/dev`; the BOOT 3 logger then rejects the changed canonical userdata path and stops saving snapshots. Therefore `root-mounted` alone does not locate the actual stall. BOOT 4 accepts both exact raw-node paths, with a regression test. The retained last-kmsg is dominated by a reset-hook/pstore tail and subsequent recovery boot; it does not retain the initiating normal-boot failure.

Android API 32 is identified, but the original ramdisk reports an unknown device name and no top-level Android `fstab*`. VENDOR is absent from this saved mount table. This is a mount/discovery finding, **not evidence that VENDOR was erased**; diagnostic 2 previously read that filesystem. These warnings and the exact wait after `root-mounted` need investigation with usable trace data.

The latest confirmed physical BOOT is **Ubuntu BOOT 3**. BOOT 4 has passed its Linux/ARM64 checks and 24 native Windows apply/restore cases. It is ready with bounded regular-file tracing, passive wait sampling and the post-devtmpfs-move logging correction. Original Ubuntu mount logic and peripheral settings are preserved; handset execution is pending.

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
| Ubuntu BOOT 3 installed image | Exact 57,335,808-byte readback matches its pin | Original Ubuntu initramfs BOOT is installed. |
| Original Ubuntu init and root mounts | Two attempts, versioned PID 1/stage markers and saved mount tables | SYSTEM, embedded Android and Data mounts execute; systemd/container startup is still unconfirmed. |
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

Test the validated **Ubuntu BOOT 4** once from the exact physically verified BOOT 3 baseline. A bounded awk pipe retains complete shell trace lines in a regular RAM file instead of the empty `/dev/kmsg` fragments observed with BOOT 3. Stage snapshots and a passive 10-second sampler retain that trace, PID 1 and child wait states on the already-mounted Data filesystem. The sampler is limited to 120 seconds; at most five attempt directories are created. No extra filesystem is mounted by the observer.

Add checkpoints before the `/usr` check, root cleanup and init-bottom, plus markers around udev's exit command. Remove global `sync` from stage capture so that filesystem-wide writeback cannot block PID 1 inside the observer. Its role in the BOOT 3 stall is unproven. The original Ubuntu `/usr`, device-name, Android mount, service and handoff logic is preserved for the next observation.

The package accepts only BOOT 3 above, targets `/dev/block/sda14`, verifies the write, and includes the exact BOOT 3 rollback. No SYSTEM/VENDOR rewrite, repartitioning or Format Data is needed. Do not rerun the already-completed BOOT 3 installer or remove its checkpoint.

The [BOOT 3 handset evidence](evidence/ubuntu-boot-3-handset-2026-10-15.json) records the new runtime result. The [BOOT 3 build record](evidence/ubuntu-boot-3-build-2026-10-15.json) remains the immutable validation record for that delivered image. The [BOOT 4 build record](evidence/ubuntu-boot-4-build-2026-10-15.json) identifies its 57,337,856-byte image, SHA-256 `f9264d385d4915157fbc16562683df7bdc0fad1517d55962884e194d1c5db3df`, and the delivered ZIP. The image leaves 333,824 bytes in the measured BOOT partition. Actual-image preservation, embedded/external CPIO, source force guards, ARM64 trace/cap/mount-move cases and 24 native Windows apply/restore cases passed. USB and raw writes in CI are simulated.

The handset sequence is:

1. Merge **`UbuntuTouch-S10plus-avvio-Ubuntu-4-Windows.zip`** into the original prepared installation folder.
2. With TWRP open and USB connected, run **`INSTALLA-AVVIO-UBUNTU-4.cmd`** and require write/readback success.
3. Choose **Reboot > System**, declining the optional TWRP app. Wait up to three minutes. Record any black screen, automatic reboot or stationary logo.
4. If blocked or rebooted, return to TWRP and run **`LEGGI-AVVIO-UBUNTU-4.cmd`**. Inspect **`ubuntu-boot-4-log-report.zip`** together with the observed screen. Do not manually repeat the installation.

**`RIPRISTINA-AVVIO-UBUNTU-3.cmd`** is the exact BOOT 3 rollback if needed after reviewing the report. It does not restore stock Android or a confirmed working Ubuntu image.

The next test must distinguish an initramfs wait, udev/console or init validation failure, and any later systemd/Android problem. A saved `userspace-handoff` marker alone will not establish a graphical boot.

## Milestones after a first boot

| Milestone | Status |
| --- | --- |
| Confirm normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October |
| Run the original Ubuntu ramdisk init and mount the intended SYSTEM | Confirmed by BOOT 3 on 15 October |
| Start Ubuntu userspace and the Halium Android container | Pending |
| Reach the graphical shell with working display and touch | Pending |
| Validate charging, suspend, Wi-Fi, Bluetooth, modem/calls/SMS, audio, camera and sensors | Untested |
| Define repeatable installation, updates and recovery for other users | Pending |

This repository is a bring-up project, not a supported-device release or a daily-use ROM.

## Publication criterion

Keep the repository private during the current boot investigation. Publish it after Ubuntu Touch reaches its graphical shell on the test handset, with the observed screen, available runtime logs and exact BOOT/SYSTEM identities recorded in `docs/evidence/`. Update this status and the README to show the successful boot and the measured hardware support. Untested features remain explicitly marked as untested in the public project.
