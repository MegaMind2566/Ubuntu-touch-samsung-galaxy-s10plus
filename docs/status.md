# Project status

Updated: **15 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

The Halium 12 adaptation and Ubuntu Touch 24.04 SYSTEM image have been built and inspected. The test handset accepts the prepared TWRP recovery and the experimental images can be written and read back with matching hashes. **Ubuntu Touch has not reached a confirmed working boot.** Normal BOOT versions 0, 1 and 2 remained at the Samsung Galaxy S10+ logo.

**Ubuntu BOOT 4 is installed and reaches the original initramfs's final userspace-handoff checkpoint.** Its exact 57,337,856-byte BOOT write/readback matches SHA-256 `f9264d385d4915157fbc16562683df7bdc0fad1517d55962884e194d1c5db3df`; the apply checkpoint records both `write_started` and `success`. Recovery checks 25 and 26 confirm the prepared TWRP/VBMETA identities, root ADB and the unchanged partition layout. No SYSTEM/VENDOR write or Format Data was requested by this update.

The single saved BOOT 4 attempt records PID 1 with kernel `4.14.280-gb9b70b29c94c-dirty`. It mounts SYSTEM read-only at `/root`, the embedded Android image read-only, and Data read-write at `/root/userdata`, retaining the original writable-path bindings. The original udev exit command completes at 3.477426 seconds, `init-bottom-complete` is recorded at 3.479156 seconds, and `userspace-handoff` at **3.509624 seconds**. This marker is before the final virtual-filesystem moves and `exec run-init`; it does not prove systemd executed.

Two observer limitations remain. The 7,280-byte shell trace stops at the original Halium `exec &>/dev/kmsg` inside `mountroot`, which bypasses its trace pipe. Later stages still appear in the saved kernel log. The passive sampler waits 10 seconds, but the observer is stopped at the 3.510-second handoff; it therefore retains no samples of the actual root transition or later userspace. Missing wait files and userspace logs cannot be treated as proof those processes never ran. The collected last-kmsg excerpts do not retain a decisive initiating failure and include recovery activity.

No BOOT 4 screen observation was supplied with these reports. Ubuntu systemd PID 1, Android container startup and a graphical boot remain **unconfirmed**. BOOT 3's earlier black-screen/reboot and stationary-logo observations belong to that image, not automatically to BOOT 4.

Android API 32 is identified, while device-name and Android fstab discovery emit warnings. VENDOR is absent from the saved initramfs mount table. Diagnostic 2 previously read that filesystem; these observations do not demonstrate erased VENDOR contents. The latest confirmed physical image is BOOT 4. Its [handset evidence](evidence/ubuntu-boot-4-handset-2026-10-15.json) supplements the unchanged historical build record.

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
| Ubuntu BOOT 4 installed image | Exact 57,337,856-byte write/readback and successful apply checkpoint | Latest installed BOOT identity is confirmed. |
| Original Ubuntu init, root mounts and cleanup | BOOT 3/4 PID 1 markers and saved mounts; BOOT 4 udev exit and userspace-handoff at 3.509624 s | Initramfs preparation reaches the final handoff; systemd/container startup is still unconfirmed. |
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

The [exact SYSTEM/userspace audit](evidence/userspace-compatibility-2026-10-15.json) completed successfully in CI. Ubuntu init, the ARM64 loader and systemd dependencies are present; pinned upstream ARM64 load tests pass. The included Android image requires v1 controllers while systemd 255 defaults to unified v2, with no cgroup hierarchy mounted at the BOOT 4 handoff. This is a concrete compatibility mismatch, not proof that it was the only blocked-boot cause.

Build **BOOT 5** with v1-controller compatibility in the exact built-in command line and header; final null/kmsg descriptors instead of opening the console; complete trace retention through Halium; a post-root observer; and a hash-guarded RAM HWC wait override that accepts real compositor service names without bypassing readiness. Its baseline and rollback are exact physical BOOT 4. Source ARM64 trace, eight observer cases and 26 HWC cases passed locally. The compiled image and native Windows package still require validation; no BOOT 5 image hash or successful handset boot is claimed yet. One complete boot attempt is the objective, without a separate preliminary handset package.

The read-only BOOT 4 TWRP inspector remains an optional evidence tool, not a required next test. It can recover more previous-boot output and inspect SYSTEM through a temporary `ro,noload,nosuid,nodev,noexec` mount. Do not rerun the completed BOOT 4 installer or remove its successful checkpoint. Current evidence does not justify SYSTEM/VENDOR rewriting, repartitioning or Format Data.

The [BOOT 4 build record](evidence/ubuntu-boot-4-build-2026-10-15.json) remains an immutable account of the delivered image and its Linux/ARM64 plus 24 native Windows apply/restore checks; USB/raw writes in CI were simulated. The [BOOT 4 handset record](evidence/ubuntu-boot-4-handset-2026-10-15.json) adds actual write/readback and runtime checkpoints. A build result, a pre-handoff marker and a graphical boot are separate validation levels.

## Milestones after a first boot

| Milestone | Status |
| --- | --- |
| Confirm normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October |
| Run the original Ubuntu ramdisk init and mount the intended SYSTEM | Confirmed by BOOT 3 and BOOT 4 on 15 October |
| Complete original initramfs cleanup and reach userspace-handoff | Confirmed by BOOT 4 on 15 October; final run-init execution unconfirmed |
| Start Ubuntu userspace and the Halium Android container | Pending |
| Reach the graphical shell with working display and touch | Pending |
| Validate charging, suspend, Wi-Fi, Bluetooth, modem/calls/SMS, audio, camera and sensors | Untested |
| Define repeatable installation, updates and recovery for other users | Pending |

This repository is a bring-up project, not a supported-device release or a daily-use ROM.

## Publication criterion

Keep the repository private during the current boot investigation. Publish it after Ubuntu Touch reaches its graphical shell on the test handset, with the observed screen, available runtime logs and exact BOOT/SYSTEM identities recorded in `docs/evidence/`. Update this status and the README to show the successful boot and the measured hardware support. Untested features remain explicitly marked as untested in the public project.
