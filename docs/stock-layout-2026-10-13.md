# Stock HWC1 image inspection

The supplied `firmware-inspection-inputs.zip` was audited offline on 13 October
2026 (Europe/Rome). The phone was not accessed or modified. The experimental
Ubuntu Touch candidate is not marked installation-ready.

## Inputs and checks

The input bundle is 49,759,089 bytes, SHA-256
`1d1fad0a5e476c9258852b1e92a9c1cc707b9983adf11428aad47db00efc573d`.
Its ZIP CRCs and the collector's SHA-256 values for all four compressed images
match. All LZ4 frames decompress completely within the measured partition bounds.

The downloader reports SM-G975F / ITV / OXM, PDA G975FXXSGHWC1 and modem
G975FXXSGHWB3. The original stock archive is 6,364,940,601 bytes, reported SHA-256
`c7d956cf40cc01b09fccc260540fb65a16ed5ff60fbed1d32abf7fd0f6c32a4d`.
The full stock archive and AP TAR MD5 were checked on the Windows PC. The full
archive was not supplied here, so those are collector-reported facts rather than
an independent rehash of all stock firmware bytes.

## Boot layout

| Field | Stock boot | Stock recovery | Halium build 1 |
| --- | --- | --- | --- |
| Header version | 1 | 1 | 1 |
| Header bytes | 1648 | 1648 | 1648 |
| Page bytes | 2048 | 2048 | 2048 |
| Kernel load address | 0x10008000 | 0x10008000 | 0x10008000 |
| Tags address | 0x10000100 | 0x10000100 | 0x10000100 |
| Ramdisk bytes | 0 | 14,944,246 | 4,108,120 |
| Ramdisk load address | 0 (absent) | 0x11000000 | 0x11000000 |
| OS version | 12.0.0 | 12.0.0 | 12.0.0 |
| Header patch metadata | 2023-03 | 2023-03 | 2023-04 |
| File bytes | 57,671,680 | 67,633,152 | 53,215,232 |

Both stock kernels are identical ARM64 Linux 4.14.113-25257816 images. Stock
boot has no ramdisk, consistent with the separate recovery/system-as-root layout.
The recovery gzip/newc archive has 438 entries; its build properties identify
SM-G975F, stock codename `beyond2`, Android 12/API 31 and G975FXXSGHWC1.
Its fstab maps the system partition to `/` and vendor to `/vendor`.

The Halium candidate is Linux 4.14.280 and includes the Halium ramdisk. Its
header/page/kernel/tags layout agrees with both stock images; its ramdisk load
address agrees with stock recovery. It leaves 4,456,448 bytes in the measured
boot partition. This is a structural comparison, not a bootloader or hardware test.
The upstream April 2023 patch metadata is retained and differs from stock March
2023; this audit does not infer a Samsung rollback guarantee from that field.

The Samsung boot ID checksums match the AOSP SHA-1 convention. The candidate
matches the pinned build tools' Lineage convention, which additionally hashes
the empty legacy `--dt` size. That difference is accounted for explicitly;
the original candidate has not been rewritten. The relevant primary code is
[AOSP mkbootimg](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/mkbootimg.py)
and [the Lineage fork selected by the pinned Halium tools](https://github.com/LineageOS/android_system_tools_mkbootimg/blob/lineage-20.0/mkbootimg.py).

## DTBO and AVB

The stock DTBO table has ten FDT payloads. Its 1,805,256-byte table is identical
to the DTBO embedded in stock recovery. The standalone 8,388,608-byte image
includes padding and an AVB footer; it exactly fills the measured DTBO partition.

Stock boot, recovery, dtbo and top-level vbmeta have SHA256_RSA4096 signatures
that verify against their embedded public keys. The available boot, recovery
and dtbo data also match their salted AVB hash descriptors. Top-level vbmeta's
boot descriptor matches the supplied stock boot. Chain keys match the supplied
recovery and dtbo keys. These checks do not read or validate the handset's
bootloader trust store.

Top-level AVB flags are **0**. It contains direct hashes for boot, bootloader,
cm and keystorage; hashtrees for system/vendor; and chains for recovery (rollback
location 5), dtb (6), dtbo (7) and product (10). All inspected rollback indexes
are 0. No actual device rollback counter was read.

The custom boot differs from stock and is not compatible with the unchanged
stock vbmeta descriptors. A verified Samsung recovery/AVB route is still needed.
No replacement vbmeta, Odin TAR or flashing instructions are supplied by this
audit. The generic stock recovery fstab also mentions vbmeta_samsung and
vbmeta_system; that alone does not establish their presence on this handset.

## Next input

The first collector omitted the separate `dtb.img.lz4`. Use the small Windows
`ESTRAI-DTB.cmd` add-on in the existing downloader folder. It compares the
retained full ZIP's SHA-256 and size with the original download report, streams
the DTB from AP, checks TAR headers and saves `dtb-inspection-inputs.zip`.
It does not write a second 6 GB AP file or access a handset. It stops after the
DTB and clearly marks its AP member listing as incomplete.

Vendor/system/product filesystem contents and vendor runtime remain outside
this small bundle. Recovery compatibility, the Download-mode OEM/FRP/KnoxGuard
state and backup coverage remain prerequisites to a separately authorized
hardware test. Bootloader unlocking has not been requested or performed.

## Reproduce

Install Python `lz4==4.4.5` (the version used for this inspection), obtain
avbtool from AndroidBootloader/platform_external_avb commit
`b27a9aa53d2db7720e4d88d6950dcd979da97de3`, and verify its SHA-256
`1183d0d19467b24b064e59191e3040260ede45f2bacaa8aa44f47be460909bb5`.
The analyzer enforces that source hash before importing it. It also checks the
candidate's SHA-256 against the recorded first successful adaptation build.

```bash
python3 scripts/inspect_stock_firmware.py \
  --bundle /path/to/firmware-inspection-inputs.zip \
  --candidate /path/to/build1/boot.img \
  --avbtool /path/to/avbtool.py \
  --output /path/to/stock-layout-report.json
python3 -m unittest discover -s tests -v
```

Full parsed headers, descriptors, partition limits and hashes are in
[stock-layout-report-2026-10-13.json](stock-layout-report-2026-10-13.json).
Local Python validation passed all 30 tests. The dedicated Windows CI validates
the extraction add-on using PowerShell 5.1 and synthetic AP/ZIP fixtures; it
does not download the 6 GB stock package or test the device.
