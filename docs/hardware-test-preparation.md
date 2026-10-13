# Hardware test preparation for SM-G975F

The current candidate is an offline image build. The handset has not been
unlocked, flashed or rebooted by the diagnostic scripts.

## Confirmed from the handset

- Exynos 9820, stock Android/vendor 12, firmware G975FXXSGHWC1.
- Software screenshot: active CSC ITV, OXM family; modem G975FXXSGHWB3.
  The displayed carrier-code row is `ITV/ITV,ITV/HUI`, retained verbatim without
  using its final HUI entry to choose a different download region.
- Bootloader reports locked; verified boot reports green.
- Boot image fits the 55 MiB boot partition. System candidate is 5120 MiB
  inside a 5700 MiB partition. Size agreement does not establish bootability.
- Knox warranty property reports `1`. It is retained as reported and is
  independent of the bootloader's current locked state.

## Recovery route under review

TeamWin identifies this model as A-only/system-as-root. Its official recovery
source configures ARM64, boot header v1, 2048-byte pages and the same boot
base/offsets used by the community Halium port. The source's platform version
is Android 12 and its patch metadata is January 2023. The supplied HWC1 stock
boot/recovery images now independently confirm header v1, 2048-byte pages and
the kernel/tags addresses. Stock recovery also confirms the candidate's ramdisk
address. This does not test a TWRP binary on the handset.

The official download listing offers `twrp-3.7.0_9-2-beyond2lte.img` as a
candidate. Exact compatibility with G975FXXSGHWC1 still needs confirmation.
No recovery image is bundled or mirrored here.

TeamWin specifically notes the vbmeta/Android Verified Boot dependency for
this device. Flashing only a replacement boot or recovery image is not a
complete installation procedure. A Samsung Download-mode route is required;
generic fastboot instructions must not be assumed to work.

## Remaining prerequisites

1. Preserve any user data and confirm the backup's coverage. Samsung Smart
   Switch supports PC backups, but secure/encrypted app data and login details
   may need separate backups.
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
4. Confirm Download-mode OEM/FRP/KnoxGuard state before any installation.
5. Only after those prerequisites, perform the separately authorized first
   hardware test. Bootloader unlocking erases user data.

See [stock-layout findings](stock-layout-2026-10-13.md) for the completed audit
and exact remaining limits. The generic recovery fstab mentions
`vbmeta_samsung` and `vbmeta_system`; their existence on this handset is not
established by the limited partition inventory and must not be assumed.

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
