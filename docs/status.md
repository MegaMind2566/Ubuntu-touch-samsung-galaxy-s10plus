# Project status

Updated: **15 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Current result

**BOOT 6 is physically installed and reaches the reported Ubuntu Touch boot screen; the usable graphical session still fails.** The installer writes and verifies 57,344,000 bytes, SHA-256 `2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad`. The apply checkpoint is complete, and the later read-only collector independently reports the same BOOT hash. The [BOOT 6 handset record](evidence/ubuntu-boot-6-handset-2026-10-15.json) retains all five uploaded input identities and the runtime references.

In normal run 1, systemd remains alive through **120.10 seconds**; the observer ends at its time limit. Android reports `sys.boot_completed=1`, HWC 2.2 is running and all six post-overlay RAM bindings complete. The root system compositor and spinner execute. The previous USB `strcmp(NULL,...)` panic does not recur within the retained evidence window. This does not establish indefinite stability.

The new blocker is the **Lomiri user session**. It repeatedly aborts with `gralloc-mapper is missing` at 94.907411, 95.670759 and 96.397123 seconds. LightDM authenticates phablet, sees its session exit with code 1, then starts a greeter which also stops. Android's `libui.so` has loaded; the failing Vendor mapper implementation, dependency or transport has not yet been identified. Missing package, permissions and linker/environment explanations remain hypotheses.

A panel power-down is recorded at 85.606686 seconds, while PID 1 remains active later. This can account for a black screen; the user's later whole-device power-off is not established by run 1's retained window. The last-kmsg panic belongs to run 3 and follows Power/Volume Down held for six seconds: Samsung's intended hard-reset hook calls `BUG()` before reset. Run 2 and run 3 are charger-mode attempts with early snapshots; run 4 is also captured only very early. These do not justify another kernel patch.

Preflight 29/30 verify RECOVERY/VBMETA before writing BOOT 6, not after the subsequent runtime. The later graphics report independently verifies the pinned prepared RECOVERY after runtime. A post-runtime VBMETA hash remains unavailable. BOOT 6 is now the latest BOOT confirmed by physical readback. A setup/home screen and touch operation are unconfirmed; the repository remains private.

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
| Ubuntu BOOT 6 installed image | Exact 57,344,000-byte write/readback, complete checkpoint and matching later collector hash | Latest BOOT identity is confirmed. |
| BOOT 6 graphics | Reported Ubuntu splash; system compositor/spinner running; Lomiri mapper aborts | Usable shell and touch remain unconfirmed. |
| Ubuntu userspace and Android container | BOOT 6 systemd alive through 120.10 s, Android boot complete, HWC 2.2 running | Actual userspace and RAM-profile execution confirmed. |
| Normal kernel and diagnostic PID 1 | Versioned init/kernel markers with the matching compiled kernel | The forced built-in-initramfs route executes on this phone. |
| Runtime storage probes | Data mounted; SYSTEM Android image and VENDOR directories readable | No missing SYSTEM/VENDOR filesystem was demonstrated; this is not a full content comparison. |
| Diagnostic 2 runtime USB | PID 1 configfs success and kernel `USB_STATE=CONFIGURED` | USB gadget configuration works under the normal kernel; no shell was provided. |
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

The first graphics collector returned zero logs: its `stat -c` call is unsupported by the active TWRP BusyBox 1.22.1. Its `success=true` flag was misleading. Image and raw userdata checks passed, so this is a reader defect rather than evidence that logs are absent. The previous ARM64 tests used the normal BOOT BusyBox, not the TWRP configuration.

Use collector **version 2** from the revised graphics ZIP, with the same `LEGGI-GRAFICA-UBUNTU-6.cmd` launcher in the main TWRP screen. No additional Ubuntu boot is needed before reading retained logs. Keep the installed BOOT 6. The reader checks pinned tools, prepared recovery, exact BOOT 6 and already-mounted raw userdata before reading the fixed USC, greeter, LightDM and phablet session log paths. It writes only its report on the PC: no phone file, partition, mount or reboot change is requested.

The required next evidence is the loader/transport error preceding `gralloc-mapper is missing`, plus session/compositor context. The reader limits each log tail to 512 KiB, rejects symlinks/FIFOs and noncanonical parents, and lists only bounded persistent-journal metadata. It does not copy journal binaries or inspect application data. Missing logs or old retained logs must not be mistaken for current execution results.

The [graphics collector record](evidence/ubuntu-graphics-collector-2026-10-15.json) retains the failed handset collection, revised package and validation limits. All 20 revised tests pass, including 10 methods using the BusyBox, linker and libraries extracted from the hash-pinned original TWRP recovery under QEMU. Mount/device boundaries remain simulated; native Windows CMD/PE execution is not claimed. If the current handset attempt reaches setup/home, capture that screen and test touch instead of interrupting a successful first boot.

Keep [BOOT 6's build record](evidence/ubuntu-boot-6-build-2026-10-15.json) and its source/image checks unchanged. No new kernel or Vendor replacement is justified by the current reports. Publication still requires a confirmed usable Ubuntu Touch graphical boot.

## Milestones after a first boot

| Milestone | Status |
| --- | --- |
| Confirm normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October |
| Run the original Ubuntu ramdisk init and mount the intended SYSTEM | Confirmed by BOOT 3 and BOOT 4 on 15 October |
| Complete original initramfs cleanup and hand off to systemd | Confirmed by BOOT 5 on 15 October |
| Start Ubuntu userspace and the Halium Android container | Confirmed by BOOT 6; current blocker is the Lomiri mapper/session failure |
| Reach the graphical shell with working display and touch | Pending |
| Validate charging, suspend, Wi-Fi, Bluetooth, modem/calls/SMS, audio, camera and sensors | Untested |
| Define repeatable installation, updates and recovery for other users | Pending |

This repository is a bring-up project, not a supported-device release or a daily-use ROM.

## Publication criterion

Keep the repository private during the current boot investigation. Publish it after Ubuntu Touch reaches its graphical shell on the test handset, with the observed screen, available runtime logs and exact BOOT/SYSTEM identities recorded in `docs/evidence/`. Update this status and the README to show the successful boot and the measured hardware support. Untested features remain explicitly marked as untested in the public project.
