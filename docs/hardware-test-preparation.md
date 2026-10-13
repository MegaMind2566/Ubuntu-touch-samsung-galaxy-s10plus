# Hardware test preparation for SM-G975F

The current candidate is an offline image build. On 13 October the user
unlocked the bootloader, accepted the factory reset and completed Android
setup. The subsequent Download-mode photo confirms OEM `OFF(U)`, FRP `OFF`
and KG `Checking`. The diagnostic scripts have not unlocked, flashed or
rebooted the handset. An initial flash invocation has now failed; in the latest
attempt the console proves that initialization stopped at the ODIN/LOKE
handshake, before beginning a session or sending image payloads. The earlier
reports without console details leave their write progress unconfirmed.
The later user photograph confirms the TWRP 3.7.0_9-2 home screen. The Ubuntu
Touch kernel/system has not yet booted on the handset. See
[recovery boot evidence](recovery-boot-2026-10-13.json).

The later [successful read-only recovery report](recovery-check-2026-10-13.json)
supersedes the pending recovery-check steps below. On the actual handset,
root ADB, the modified init/no-op script, exact recovery/VBMETA hashes and all
eight partition sizes are confirmed. SYSTEM and VENDOR were unmounted. Data
is directly mounted ext4, and TWRP reports encryption disabled; legacy
directory encryption policies are not inferred from that flag. The planned
first installation uses a fresh manual Format Data only after all PC image
and complete-stock-backup verification has passed.

The original system artifact has now been independently expanded and hashed;
see [the locked image identities](../config/install-images.lock.json). The
actual boot header selects `systempart=/dev/disk/by-partlabel/system`, so the
first test targets SYSTEM and BOOT. The Windows installer verifies a changed
ext4 UUID after the user's manual Format Data, requires a manual move from
TWRP to Download Mode, and uses one native VCOM flash session with its internal
PIT and size checks. It does not precede that session with another PIT read,
write vendor/DTB/DTBO/modem/EFS, retry a failed write, repartition or automatically
reboot. This is a first hardware test, not an established working UT port.

## Confirmed from the handset

- Exynos 9820, stock Android/vendor 12, firmware G975FXXSGHWC1.
- Software screenshot: active CSC ITV, OXM family; modem G975FXXSGHWB3.
  The displayed carrier-code row is `ITV/ITV,ITV/HUI`, retained verbatim without
  using its final HUI entry to choose a different download region.
- The original 12 October ADB snapshot reported locked/green. The new
  [Download-mode observation](download-mode-state-2026-10-13.json) supersedes
  its bootloader state. Secure Download remains enabled; unlocking is not a
  substitute for resolving the original AVB metadata.
- Boot image fits the 55 MiB boot partition. System candidate is 5120 MiB
  inside a 5700 MiB partition. Size agreement does not establish bootability.
- Knox warranty property reports `1`. It is retained as reported and is
  independent of the bootloader's current unlocked state.

## Recovery route under review

TeamWin identifies this model as A-only/system-as-root. Its official recovery
source configures ARM64, boot header v1, 2048-byte pages and the same boot
base/offsets used by the community Halium port. The source's platform version
is Android 12 and its patch metadata is January 2023. The supplied HWC1 stock
boot/recovery images now independently confirm header v1, 2048-byte pages and
the kernel/tags addresses. Stock recovery also confirms the candidate's ramdisk
address. This does not test a TWRP binary on the handset.

The actual `twrp-3.7.0_9-2-beyond2lte.img` now passes the publisher's SHA-256,
boot ID, ARM64/header/address, bounded LZMA/newc and DTBO checks. It is
57,554,944 bytes and fits the measured recovery partition with 10,078,208
bytes spare. Its entire embedded DTBO table matches the supplied HWC1 stock
table. These static checks do not verify bootloader acceptance or runtime.
No recovery image is bundled or mirrored here.

The ramdisk's init configuration starts `sbin/nuker.sh` when ADB becomes
ready. That script attempts to remount system/vendor read-write and change
encryption/security configuration and stock recovery restoration files.
An unmodified TWRP boot is therefore not a test that preserves the Android
12 vendor baseline. Account for or neutralize those automatic writes before
a recovery test, and separately resolve AVB. Nothing from that script has
been executed on the handset. See the [actual binary audit](twrp-binary-audit-2026-10-13.json).

TeamWin specifically notes the vbmeta/Android Verified Boot dependency for
this device. Flashing only a replacement boot or recovery image is not a
complete installation procedure. A Samsung Download-mode route is required;
generic fastboot instructions must not be assumed to work.

## Remaining prerequisites

1. The user reports no important data to preserve and has already performed
   the bootloader unlock/reset. Do not claim that a backup was created or
   ask the user to repeat that completed step.
2. Retain the original stock firmware package for SM-G975F,
   matching G975FXXSGHWC1 / ITV / OXM and modem G975FXXSGHWB3. The Windows
   downloader completed the exact download and AP MD5 check. The supplied
   boot/recovery/dtbo/vbmeta audit bundle passes structural, embedded-key signature
   and available image-digest checks. The full archive is still on the user's PC;
   its reported hash was not independently recomputed from that full archive here.
   Retain the complete recovery set, not just a boot image. Do not downgrade the
   Samsung bootloader.
3. The separate Samsung `dt.img.lz4` (AVB partition `dtb`) has now passed
   signature, salted payload digest, vbmeta chain-key and Exynos 9820 FDT
   checks; see [completed DTB audit](stock-dtb-2026-10-13.md). Confirm a
   compatible recovery and an AVB/vbmeta plan for this exact firmware. Stock flags are 0, so replacing boot/system without an
   appropriate verified installation route remains unsupported. Vendor filesystem
   contents and runtime have not yet been inspected/tested.
4. Download-mode OEM/FRP/KnoxGuard state is confirmed from the new photo.
   The user completed `CONTROLLA-DOWNLOAD.cmd`: the pinned samloader 2.2.0
   executable uses Windows VCOM, queries the device model and reads its PIT
   with `--no-reboot`. The launcher performs no partition write, erase or
   reboot. It saves a bounded PIT, a locally decoded partition table and a
   report without the identifiers returned by native USB detection. If an
   older bootloader cannot return a model, that field remains unconfirmed;
   the supplied photo identifies SM-G975F. Windows PowerShell 5.1 tests use
   synthetic handset responses and the real publisher executable only for
   offline version/PIT decoding; they do not establish hardware compatibility.
   The real VCOM detection/PIT read succeeded with the confirmed SM-G975F.
   The PIT has 41 UFS entries and matches the ADB boot/recovery/system/vendor
   sizes. DTB and DTBO are both 8 MiB; VBMETA is 64 KiB. No separate
   VBMETA_SYSTEM or VBMETA_SAMSUNG entry is present. USERDATA's PIT block count
   is zero with the `remained` marker, so its size remains the previous ADB
   measurement, not zero. See [actual PIT audit](download-mode-pit-2026-10-13.json).
5. `PREPARA-RECOVERY.cmd` prepares files locally without accessing the phone.
   It verifies the retained complete HWC1 stock ZIP by size and SHA-256, then
   obtains the publisher-pinned TWRP image on the user's PC. The patch removes
   the `nuker` init trigger and replaces its script with a no-op while preserving
   its attribution; kernel, embedded DTBO, all remaining ramdisk contents and
   metadata are unchanged. It rebuilds the original LZMA/header/boot-ID layout.
   The pinned AOSP avbtool produces a 64 KiB unsigned, descriptor-free vbmeta
   with flags 3, rollback index 0 and minimum libavb 1.0. These flags disable
   verification and hashtree enforcement for an unlocked-device test; they do
   not validate Samsung acceptance or the hardware. The first test writes
   only RECOVERY and VBMETA by their verified PIT names, after checking this
   preparation result. No flash command is included in the preparation package.
6. The user's `recovery-preparation-report.zip` confirms production preparation
   success and a retained, full-size stock firmware with the exact expected
   SHA-256. Both prepared image hashes match the independent Linux and Windows
   audits. See [reviewed preparation report](recovery-preparation-2026-10-13.json).
   The small `INSTALLA-RECOVERY-TEST.cmd` add-on is extracted into the existing
   preparation folder. It requires that verified production state, locks the
   retained firmware and image inputs before validating their contents, and
   rechecks the USB model and exact handset PIT before writing. It permits
   only named VBMETA and RECOVERY payloads with `--no-reboot`; there is no erase,
   repartition, additional image, size-check bypass or automatic recovery attempt.
   Version 2 pauses after the PIT read for a fresh manual entry into Download
   Mode, then verifies the model and the same serial in memory before the
   separate flash command. This addresses the most likely cause of the observed
   second-handshake failure; the hardware result is still pending. The console
   streams are drained concurrently without a wrapper timeout or forced kill.
   Its diagnostic ZIP retains bounded, redacted flash stdout/stderr in JSON,
   without PC paths or device identifiers. Handshake failures are distinguished
   from failures at an unknown later point; there is no automatic write retry.
   After a successful write, boot immediately to recovery with USB connected,
   select Keep Read Only and cancel any data-password prompt. A failed write
   may be partial: stay in Download Mode and inspect its report before retrying.
7. The latest supplied attempt failed the handshake before image transfer;
   see [observed failure and fix](recovery-handshake-failure-2026-10-13.json).
   The subsequent recovery photograph confirms TWRP boot. Complete the read-only
   ADB checks of the exact installed images, mounts and userdata encryption with
   `CONTROLLA-RECOVERY.cmd` are now complete. It reads
   only selected metadata and recovery/vbmeta image bytes, without mounting,
   writing, formatting or rebooting. Ubuntu Touch boot remains pending.

See [stock-layout findings](stock-layout-2026-10-13.md) for the completed audit
and exact remaining limits. The generic recovery fstab mentions
`vbmeta_samsung` and `vbmeta_system`; the actual PIT has neither partition.

The Android 12 vendor currently on the handset is the candidate baseline;
the historical October 2021 vendor image must not be substituted. Runtime
compatibility remains unverified until the Android container and hardware
services are exercised on the phone.

## Primary references

- https://twrp.me/samsung/samsunggalaxys10plus.html
- https://eu.dl.twrp.me/beyond2lte/twrp-3.7.0_9-2-beyond2lte.img.html
- https://github.com/TeamWin/android_device_samsung_beyond2lte/blob/android-9.0/BoardConfig.mk
- https://topjohnwu.github.io/Magisk/install.html#samsung-devices
- https://www.samsung.com/uk/support/mobile-devices/how-do-i-backup-my-smartphone-to-my-pc-or-mac/
