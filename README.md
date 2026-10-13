# Ubuntu Touch — Galaxy S10+ Exynos (beyond2lte)

Experimental port workspace for Samsung SM-G975F/DS (Exynos 9820).

## Status
**Experimental Halium 12 adaptation and Ubuntu Touch 24.04 system built and validated. The corrected BOOT is installed and its physical readback passes. The subsequent normal-boot photograph still shows the Samsung logo; Ubuntu kernel/userspace execution remains unconfirmed.**

On 13 October 2026 the user unlocked and reset the handset. The new
Download-mode photo confirms **OEM OFF(U), FRP OFF, KG Checking**, with the
Samsung stock system still installed at that point. The user subsequently
installed the prepared recovery and supplied a photograph of the TWRP
3.7.0_9-2 home screen. The subsequent read-only ADB report confirms the exact
modified recovery/VBMETA hashes, root ADB, all measured partition sizes,
unmounted SYSTEM/VENDOR and directly mounted ext4 userdata. The user subsequently completed Format Data and installed the experimental
SYSTEM/BOOT through TWRP. Both physical image prefixes were read back and
matched their fixed SHA-256 hashes. No new Format Data is requested.
See [confirmed recovery checks](docs/recovery-check-2026-10-13.json).
Ubuntu Touch boot and vendor runtime remain unverified.
See [current Download-mode observation](docs/download-mode-state-2026-10-13.json).

First successful adaptation build: **12 October 2026**, commit
`b487799c4c0772c2fbd43008888d299d33ea548e`.
[CI run and experimental artifacts](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38301613434).
The boot image is 53,215,232 bytes; the read-only handset inventory confirms a
57,671,680-byte boot partition, leaving 4,456,448 bytes. This confirms size only,
not boot-header/firmware compatibility. All structural/configuration checks passed. Python tests
and Windows inventory tests (mock ADB) also passed. These are not hardware tests.

The `S10+ Halium 12 adaptation` workflow compiles the kernel, `boot.img` and the
device adaptation tarball. The separate system-candidate workflow now includes
the Ubuntu Touch rootfs and Halium GSI. The measured Samsung recovery route is
now available for the first experimental kernel/system test. Build success is
not evidence that the handset boots or that Samsung vendor services work.

Target handset (read-only ADB inventory, 12 October 2026):
- Android 12, One UI 4.1
- Baseband: G975FXXSGHWB3
- Build: G975FXXSGHWC1
- Kernel: 4.14.113-25257816
- Android and vendor both report Android 12/API 31.
- Stock codename `beyond2`; port codename `beyond2lte`.
- Bootloader reports `locked`, verified boot `green`.
  This is the original inventory; the later Download-mode observation above
  confirms that the user has since unlocked it.
- Software screenshot confirms active CSC `ITV`, CSC family `OXM`, and
  service-provider line `SAOMC_SM-G975F_OXM_ITV_12_0012`.

The partition links and `/proc/partitions` agree on the expected separate boot,
recovery, system and vendor layout. Sysfs size fields returned empty values; the
inventory analyzer uses the documented 1024-byte units of `/proc/partitions`.
See [device compatibility assessment](docs/device-check-2026-10-12.json).

## System candidate

First successful system assembly: **12 October 2026**, commit
`c9e44ce3d38e86b51584a5e6ce05d0f8bb7f3e08`.
[CI run and experimental system image](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38311673964).
The actual ext4 checks passed for both the Ubuntu filesystem and embedded
Halium image. The 5 GiB raw system image leaves 608,174,080 bytes (580 MiB)
of partition margin, with 1,760,321,536 bytes free inside the filesystem.
All 21 Python tests passed. See the [system build report](docs/system-build-report-2026-10-12.json).

`S10+ Ubuntu Touch 24.04 system candidate` reuses the verified adaptation from
build 1 and assembles the official arm64 rootfs build 125 with Halium 12 GSI
build 1310. Inputs are fixed by URL, size and SHA-256 in
[assembly inputs](docs/assembly-inputs-2026-10-12.json).
The candidate uses a 5 GiB ext4 filesystem inside the measured 5700 MiB system
partition. The workflow checks raw and sparse expanded sizes, filesystem
integrity, ARM64 userspace, Halium version and S10+ overlays before compressing
the raw image. It preserves the upstream rootfs access defaults rather than
injecting the upstream development-only passwordless SSH/unauthenticated ADB
settings. There is no official S10+ 24.04 update channel.

This workflow only assembles files. It never connects to or flashes a handset.
Its output remains an experimental candidate. Stock image/PIT layout and the
modified recovery route have now been checked; vendor runtime still needs the
first on-device kernel/container test.
See [hardware test preparation](docs/hardware-test-preparation.md) for the
remaining firmware/CSC, backup, recovery and AVB prerequisites.

## First experimental Ubuntu Touch installation

`PREPARA-UBUNTU-TOUCH.cmd` verifies the complete retained HWC1 stock ZIP and
the immutable [original system artifact](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38311673964/artifacts/11775595258).
It expands the 5 GiB raw ext4 image using embedded Python 3.14.4, validates the
fixed BOOT/SYSTEM hashes and the actual boot cmdline selecting
`/dev/disk/by-partlabel/system`. Inputs are recorded in
[the independent image audit](config/install-images.lock.json).

`INSTALLA-UBUNTU-TOUCH.cmd` locks and revalidates the images and retained stock
firmware, then repeats the measured recovery checks. Only after those pass does
it ask for a manual **Wipe > Format Data > yes** in TWRP, which erases internal
userdata. Read-only filesystem metadata must show a new ext4 UUID. The user
then manually chooses **Reboot > Download**. One VCOM flash session writes
**SYSTEM then BOOT**, with native PIT/name/size checks and `--no-reboot`.
There is no separate PIT handshake, automated erase, repartition, write retry
or automatic reboot. Recovery, VBMETA, vendor, DTB/DTBO, modem and EFS are not
targets of this installer. After a successful write, manually reboot normally
for the first Ubuntu Touch attempt and collect its report and a photograph.

The tools package contains portable Python, official Google ADB 37.0.1 and
samloader 2.2.0 with publisher checksums and notices. It contains no TWRP,
stock firmware or multi-gigabyte handset image. Windows CI expands the actual
original image and tests native CMD/PowerShell entry points in a path with
spaces. USB replies and partition writes in CI are simulated; CI does not
establish hardware boot or functionality. Reproduce with
`python3 scripts/package-ubuntu-install.py` and follow
[the Windows instructions](tools/windows/LEGGIMI-INSTALLAZIONE-UBUNTU.txt).

Installer version 1 stopped before the Format Data prompt on the handset:
the recovery's BusyBox 1.22.1 `od` rejects the desktop `-A` option. This exact
failure was reproduced under ARM64 emulation using the original recovery
runtime. Version 2 reads the same bounded ext4 metadata using explicitly
selected BusyBox `hexdump`, and separates metadata-read errors, missing user
confirmation and an unchanged filesystem UUID. Diagnostic reports retain
stage/exit details without saving the UUID. The small
`UbuntuTouch-S10plus-correzione-dati-Windows.zip` replaces only the installer
script in the already prepared folder; images/preparation do not need to be
downloaded or repeated. See [the observed stop and reproduced cause](docs/ubuntu-install-metadata-failure-2026-10-13.json).

The later report 10 confirms the corrected metadata reads, completed fresh
Format Data, recovery checks and USB model detection. Odin then fails while
receiving PIT chunks. Source review confirms that this precedes BOOT/SYSTEM
payload transfer; see [the actual attempt](docs/ubuntu-install-pit-failure-2026-10-13.json).

`INSTALLA-UBUNTU-TWRP.cmd` is the alternate first-test route for this already
prepared handset. It requires the exact reviewed reset report retained on
the PC, revalidates/locks the complete stock backup and both image inputs,
checks root recovery, all measured sizes and unmounted SYSTEM/VENDOR, and
refuses Android-initialized userdata. It stages files in one new, private
userdata folder, validates their sizes and fixed SHA-256 hashes, then repeats
recovery/mount checks and checks that the userdata UUID has not changed.
It writes only `/dev/block/sda25` (SYSTEM) and `/dev/block/sda14` (BOOT), with
the real recovery BusyBox `dd` and `sync`. Each exact image prefix is read
back and hashed before declaring success. Only the two owned temporary files
are cleaned up. There is no new Format Data, Download-mode protocol,
repartition or automatic reboot/retry. A local pre-write checkpoint blocks
repeat execution after an interrupted or completed write. Hardware UT boot
and vendor functions remain pending even if readback passes.

Reproduce the small add-on with `python3 scripts/package-ubuntu-twrp.py` and
follow [the TWRP instructions](tools/windows/LEGGIMI-UBUNTU-TWRP.txt). Windows
tests use the original pinned images, simulate USB/raw writes and exercise
the native CMD and console capture. ARM64 emulation runs the actual TWRP
BusyBox copy/hash/sync/stat tools against disposable files, including a final
partial copy block and 5 GiB size reporting; it is not a hardware flash test.

The first normal boot remains on the Galaxy S10+ logo. The hardware report
now confirms both SYSTEM/BOOT physical readbacks and the unchanged expected
BOOT/RECOVERY/VBMETA prefixes. VENDOR passes all five read-only filesystem
check stages with exit code 0; its complete stock content has not been compared.
The received `dmesg.log` is the current TWRP kernel (4.14.113). `last_kmsg`
contains Samsung S-Boot selecting RECOVERY and loading TWRP's measured image,
not a Linux log from the compiled Ubuntu kernel (4.14.280). Its AVB/footer
warnings concern the working custom recovery and do not establish the cause
of the Ubuntu stop. No Ubuntu kernel or userspace boot is confirmed yet.
See [the hardware readback and log provenance](docs/first-boot-readback-2026-10-13.json).

`CONTROLLA-PRIMO-AVVIO.cmd` reuses the existing pinned Windows tools to read
`/proc/last_kmsg` and available console/dmesg pstore records before collecting
current recovery metadata, BOOT/RECOVERY/VBMETA prefix hashes and the local
TWRP installation report. VENDOR size/ext4 checks and an unmounted-only
`e2fsck -f -n` check gather filesystem evidence without repairs or journal
replay. The collector requests no phone writes, mounts or reboot. Missing
persistent logs are not proof that the Ubuntu kernel never ran. Reproduce
the small add-on with `python3 scripts/package-first-boot-check.py`; follow
[the collection instructions](tools/windows/LEGGIMI-PRIMO-AVVIO.txt).
[Windows CI](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38431158880)
passes nine evidence/guard cases and the actual CMD with embedded Python in a
path containing spaces. USB replies in the unit cases are simulated; the
native launch test has no handset.

`CONTROLLA-USB-AVVIO.cmd` reads three host PnP/CIM snapshots while the user
manually boots normally and leaves the phone at the logo. It includes only
the selected USB descriptors and currently present USB network adapters,
omits serial suffixes and excludes cached disconnected adapters. It sends
no phone commands and changes no drivers or network settings. A Halium panic
gadget can establish that the kernel/initramfs ran; absent USB evidence is
inconclusive. Reproduce the standalone small package with
`python3 scripts/package-boot-usb-check.py` and follow
[the live USB instructions](tools/windows/LEGGIMI-USB-AVVIO.txt).
[Windows CI](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38434679157)
checks filters, serial omission, disconnected-adapter exclusion and the
actual CMD/PowerShell 5.1 PnP/CIM queries. No handset is attached in CI.

## BOOT-only SAR loader correction

The host USB report contains three successful PnP/CIM snapshots with no
selected USB device or USB network adapter. This does not establish where
normal boot stopped. See [the USB evidence](docs/first-boot-usb-2026-10-13.json).

The exact pinned Halium kernel source declares `rd_offset` without an initial
value in `init/sar_ramdisk/sar_ramdisk.c` and then adds the header/kernel sizes
to it. The new patch initializes it to zero. This fixes a source-level defect;
it is not yet a demonstrated cause of the handset's logo stop. File-only
regression tests compile the actual pinned loader before/after the patch:
both host cases read the correct ramdisk, and only the original produces the
uninitialized-variable warning. These are not handset or Android-toolchain
kernel-runtime tests.

[Corrected kernel build](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38439532393)
compiles successfully. The resulting 53,215,232-byte BOOT has SHA-256
`d3be319ae9353908e917894d624460e743bfc078d676c592189d415ef02b0993`.
It contains the new kernel while preserving the installed ramdisk byte for
byte, the old boot header addresses/parameters and its SYSTEM selector.
Only the kernel-size and boot-ID fields are recomputed. It fits the measured
57,671,680-byte BOOT partition. No new SYSTEM/VENDOR image is required.

`INSTALLA-CORREZIONE-BOOT.cmd` is a small add-on for the existing prepared
Windows directory. It revalidates and locks the original images, retained
full stock backup, corrected BOOT and portable tools. Root TWRP identity,
recovery/VBMETA/startup hashes, partition sizes and unmounted SYSTEM/VENDOR
are checked before staging. The current BOOT must match the reviewed old
image. After transfer, both the recovery inventory and current BOOT hash are
checked again. The installer writes only `/dev/block/sda14`, performs an
exact image-prefix readback and requires its new SHA-256 before success.
It requests no format, repartition, SYSTEM/VENDOR write or automatic reboot.
A pre-write checkpoint blocks repeated writes; a possible partial write is
preserved for report review.

`RIPRISTINA-BOOT-PRECEDENTE.cmd` is a separate manual previous-BOOT restore.
It accepts only the exact corrected BOOT as its current input state, applies
the same guards and restores the retained original experimental BOOT. This
is not a full Android restore, and full stock restoration remains untested
on hardware. See [the Windows instructions](tools/windows/LEGGIMI-CORREZIONE-BOOT.txt).

[Windows 5.1 validation](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38444246956)
passes 22 update/restore guard cases using both actual immutable BOOT images,
embedded Python and both real CMD entry points in a directory with spaces.
USB responses/raw writes are simulated; hardware Ubuntu boot remains
unverified. See [the correction evidence](docs/boot-update-1-2026-10-13.json).
The subsequent handset reports confirm the corrected 53,215,232-byte BOOT
was written and read back with the expected SHA-256. Both recovery inventory
reports pass, and the local Apply checkpoint records success. SYSTEM/VENDOR
were not written and no data format/repartition was requested. The normal
boot photograph still shows the Galaxy S10+ logo and Samsung's modified-software
warning, without an Ubuntu UI. This single image does not prove whether the
kernel/initramfs ran. A fresh host USB snapshot with the corrected BOOT is the
next read-only check; do not repeat Apply or erase userdata. See
[the corrected-BOOT logo observation](docs/boot-update-1-logo-2026-10-13.json).
See [the hardware correction result](docs/boot-update-1-handset-2026-10-13.json).

Reproduce with `scripts/prepare_boot_update.py`,
`scripts/fetch_boot_update_artifact.py` and `scripts/package-boot-update.py`;
the workflow fixes the original and corrected artifact identities.

## Exact stock-firmware download on Windows

The new `SCARICA-FIRMWARE.cmd` package targets the screenshot's SM-G975F/ITV,
PDA G975FXXSGHWC1, modem G975FXXSGHWB3 and OXM CSC family. It queries Samsung,
selects the exact installed version and passes it explicitly to samloader.
A returned version mismatch terminates the download process before acceptance;
no newer or different firmware is automatically substituted.

The package includes samloader 2.2.0 from its publisher's release, verified
against GitHub's published archive SHA-256, with Apache/MIT notices. The Windows
workflow validates native argument quoting, process termination, timeouts,
target/catalog guards and the real executable's CLI using PowerShell 5.1.
It queries Samsung version metadata separately; metadata availability does not
mean that the complete stock package has been obtained.

The independent BinaryInform probe confirmed that Samsung offers the exact
HWC1/ITV/OXM binary, size 6,364,940,608 bytes, and returns the requested PDA,
CSC and modem versions. This probe never initializes a firmware-body download.
See [exact binary metadata](docs/stock-binary-metadata-2026-10-12.json) and
[successful metadata/Windows validation run](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38315969407).
The full stock archive has now been downloaded on the user's PC. The supplied
inspection bundle passes LZ4, boot ID, ARM64/header layout, AVB signature and
available image-digest checks. The full ZIP's hash and AP MD5 are reported by
the Windows collector; only the small inspection bundle was independently
checked here. The subsequent preparation and recovery ADB reports confirm
the retained full ZIP hash and the installed recovery route; Ubuntu boot is pending.

On the user's PC, the launcher retains the complete stock ZIP for recovery,
checks the AP TAR's MD5 and extracts only boot, recovery, dtbo and vbmeta into
`firmware-inspection-inputs.zip`. That bundle has been inspected against build 1.
It performs no handset access or installation.
See [stock target](docs/stock-firmware-target-2026-10-12.json).

### Stock layout inspected

The HWC1 stock boot and recovery both use header v1, 2048-byte pages and the
same kernel/tags addresses as the Halium candidate. Stock boot has no ramdisk;
the candidate's ramdisk address agrees with stock recovery. The stock recovery
DTBO matches the standalone table, which contains ten overlays. AVB metadata
uses SHA256_RSA4096 with flags 0 and protects the original boot plus the
system/vendor contents and chained recovery, dtb, dtbo and product images.
These checks do not make the unsigned Halium candidate installable.

See [stock-layout findings](docs/stock-layout-2026-10-13.md) and the
[machine-readable audit](docs/stock-layout-report-2026-10-13.json).
The separate stock device-tree image has now been supplied by the v3 collector
as `dt.img.lz4`. Its AVB partition is `dtb`. Signature, salted payload digest,
stock vbmeta chain key and Exynos 9820 base-tree checks pass. The raw factory
image is 8 MiB with one base FDT. The subsequent real Download-mode PIT confirms
an 8 MiB DTB partition. See [completed DTB audit](docs/stock-dtb-2026-10-13.md)
and [actual PIT audit](docs/download-mode-pit-2026-10-13.json).
The small `ESTRAI-DTB.cmd` add-on verifies the retained stock ZIP and streams
that file from BL, AP or the other firmware packages without writing the whole
6 GB AP to disk. It supports compressed/raw DTBs and saves TAR member lists
even when none is found. A failed prior attempt does not block a retry.
The supplied DTB has completed this extraction/audit step; the add-on remains
for reproducing it. It does not access a handset.
Reproduce the add-on with `python3 scripts/package-stock-dtb.py`.

## Windows Download-mode connection and PIT check

After unlocking, `CONTROLLA-DOWNLOAD.cmd` checks the actual Download-mode
connection and reads the handset's partition information table (PIT). It uses
the publisher's samloader 2.2.0 Windows binary, pinned by archive/executable
SHA-256, with the VCOM backend. It does not replace the Samsung USB driver.
Its command allowlist only permits version, JSON detection, `dump-pit` with
`--no-reboot`, and local PIT decoding. Detection identifiers are discarded;
the report retains only a validated model. A diagnostic ZIP is also produced
after failures, and earlier reports are preserved on retry.

Extract the package on Windows, connect only the SM-G975F in Download Mode,
close Odin/Smart Switch and open the CMD launcher. Send the generated
`download-mode-check.zip`. No image, partition write, erase or reboot is part
of this check. ADB is not the Download-mode transport.

Reproduce with `python3 scripts/package-download-check.py`.

The user completed collector v2 on 13 October: VCOM detection and the PIT read
succeeded, the USB model is SM-G975F, and the 41-entry UFS table confirms the
previous boot/recovery/system/vendor measurements. DTB/DTBO are 8 MiB and
VBMETA is 64 KiB. There is no VBMETA_SYSTEM/VBMETA_SAMSUNG entry. USERDATA's
zero PIT block count means remaining space, not a zero-byte partition.

## Local preparation of the first recovery test

`PREPARA-RECOVERY.cmd` verifies the complete stock recovery ZIP retained on
the user's PC and downloads the publisher-pinned beyond2lte TWRP image there.
It removes the automatic `nuker` trigger and replaces that script with a no-op,
preserving attribution. Kernel, embedded DTBO, other ramdisk bytes/metadata,
header addresses and version/patch fields are unchanged. Only the ramdisk size,
DTBO offset and boot-ID checksum are regenerated with the original layout.

The preparation also creates a 64 KiB flags-3/algorithm-NONE vbmeta using
the checksum-pinned AOSP avbtool. It is unsigned and intended for an unlocked
device test. Valid metadata/layout does not prove Samsung acceptance or boot.
The package includes the official Python 3.14.4 embedded Windows runtime,
verified against the publisher's SHA-256, and the applicable licenses.
It never accesses a handset or flashes images, and does not bundle/mirror TWRP.
Original images and modified outputs remain on the user's PC; only the small
preparation report is returned for review. The first recovery boot is now
confirmed by the user's photograph; Ubuntu Touch boot remains pending.

Reproduce with `python3 scripts/package-recovery-preparation.py`.

The user's production preparation report now confirms the complete retained
stock ZIP and both image hashes; see
[the reviewed result](docs/recovery-preparation-2026-10-13.json).
`INSTALLA-RECOVERY-TEST.cmd` is a small add-on for that same preparation folder.
It locks and revalidates the exact image/firmware inputs, confirms the USB model
and exact measured PIT, and writes only VBMETA and RECOVERY with no reboot or
erase. Version 2 pauses after the PIT read for a fresh manual Download Mode
entry, then rechecks the same handset before the separate flash handshake.
The console streams are drained concurrently without a wrapper timeout, and
bounded, redacted native messages are retained in `recovery-test-report.zip`.
The latest user console identifies a handshake failure before beginning a
session or transmitting image payloads. The later recovery photograph and ADB hash checks confirm that TWRP does boot.
The Ubuntu Touch kernel/system still needs hardware verification. See
[the failure record](docs/recovery-handshake-failure-2026-10-13.json).
Windows CI validates the real images and native CMD entry point, with simulated
USB responses/writes and a local console stub only.
Reproduce the add-on with `python3 scripts/package-recovery-test.py`.

## Read-only checks in the running recovery

The TWRP photograph confirms the recovery home screen. `CONTROLLA-RECOVERY.cmd`
uses the official, checksum-pinned Google ADB 37.0.1 for USB-only read queries.
It checks root recovery identity, measured partition sizes, the modified init
and no-op script, and hashes of the exact installed recovery prefix and bounded
VBMETA image. It reads selected mount metadata, static fstab configuration and
TWRP encryption/decryption state. It never mounts, pushes, formats, flashes or
reboots the handset, and does not read personal files from USERDATA.

The report ZIP retains selected metadata, without general property dumps,
ADB serials or raw errors. Failures also produce a report. These results guide
the first Ubuntu Touch installation; recovery success does not establish
compatibility of the Ubuntu Touch kernel/container with Samsung vendor.
Reproduce with `python3 scripts/package-recovery-check.py`.

## Build

Source revisions are pinned in `config/upstream.lock.json`. The rootfs migration
target is Ubuntu Touch **24.04-2.x**; this is a development target, not a claim
that an S10+ release exists. The historical 16.04 device status does not describe
this new build.

On Ubuntu 22.04 with the dependencies listed in the workflow:

```bash
bash scripts/build-adaptation.sh
```

Run this once in a fresh build directory. For a second attempt, pass a new path
such as `bash scripts/build-adaptation.sh "$PWD/build/attempt-2"`.

Changes to the upstream Halium 12 tree:
- Initialize the Samsung SAR ramdisk offset before computing the BOOT payload position.
- Apply the documented 4.14 AppArmor socket/AF_UNIX patches, preserving attribution.
- Merge `config/ubuntu-touch.config` after the Samsung defconfig. Validate the
  effective kernel configuration after compilation.
- Enable the overlay store needed by modern Ubuntu Touch.
- Align the old session grid setting with the S10+ DeviceInfo value of 27.
- Preserve the exact already installed non-dynamic ramdisk, boot header v1 and
  its original parameters while rebuilding the corrected kernel. Preserve
  4096-byte rootfs sectors and check against measured partition bounds.

Artifacts include a source/patch manifest, kernel config, ramdisk checksum,
build log, boot image and device tarball. `validate-artifacts.py` verifies header,
ARM64 kernel, ramdisk, required config and tarball contents. It does not validate
vendor compatibility, hardware functionality or flashing safety.

See [THIRD_PARTY.md](THIRD_PARTY.md) for source attribution and binary-lock limits.

## Read-only handset inventory

The Windows package includes official ADB 37.0.1 and its notices, verified
against the fixed Google archive SHA-256. Extract the package, enable USB
debugging on the S10+, then open `AVVIA-CONTROLLO.cmd`. The launcher waits up to
60 seconds for USB authorization and saves `beyond2lte-device-report.json`.
It does not enable OEM unlock or install a driver/firmware.

To reproduce the package:

```bash
python3 scripts/package-device-check.py
```

For the next compatibility check, `scripts/collect-device.ps1` reads selected
Android/vendor properties and boot/system/vendor partition sizes through ADB.
It does not unlock, reboot or change the phone. Run it on Windows with an already
authorized ADB connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\collect-device.ps1
```

No IMEI, accounts, phone numbers or ADB serial are saved. Missing properties or
permissions are recorded as diagnostic results rather than invented values.

## Upstream sources
- [UBports community device port](https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820) — inspect `halium-12` and historical branches, especially `deviceinfo-beyond2lte`, `build.sh`, CI and overlays.
- [UBports Exynos 9820 kernel](https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/kernel-samsung-exynos9820) — historical `halium-10.0` kernel, not assumed compatible with stock Android 12 firmware.
- [Original historical port](https://gitlab.com/ubuntu-touch-for-beyondxlte/samsung-exynos9820) — archived reference, not current installation guidance.

## Plan
1. Inventory upstream branches, device configuration, kernel source, build scripts and binary/vendor dependencies.
2. Pin upstream commit IDs and record licenses. Import only the necessary sources with attribution.
3. Establish a reproducible, **non-flashing** build and artifact validation in CI.
4. Check compatibility of boot, vendor, recovery and partitions against the exact device firmware before attempting an install.
5. Test on hardware only after backup and verified stock-firmware recovery procedure.

## Safety
Unlocking the bootloader wipes user data and may permanently trip Samsung Knox. Never flash an image simply because CI succeeded. Phone functions (including calls, dual SIM, VoLTE, cameras) remain unverified.

