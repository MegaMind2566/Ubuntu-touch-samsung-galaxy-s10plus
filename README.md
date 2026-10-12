# Ubuntu Touch — Galaxy S10+ Exynos (beyond2lte)

Experimental port workspace for Samsung SM-G975F/DS (Exynos 9820).

## Status
**Experimental Halium 12 adaptation and Ubuntu Touch 24.04 system built and validated. No on-device boot validation.**

First successful adaptation build: **12 October 2026**, commit
`b487799c4c0772c2fbd43008888d299d33ea548e`.
[CI run and experimental artifacts](https://github.com/MegaMind2566/Beyond2lte-UbuntuTouch-port/actions/runs/38301613434).
The boot image is 53,215,232 bytes; the read-only handset inventory confirms a
57,671,680-byte boot partition, leaving 4,456,448 bytes. This confirms size only,
not boot-header/firmware compatibility. All structural/configuration checks passed. Python tests
and Windows inventory tests (mock ADB) also passed. These are not hardware tests.

The `S10+ Halium 12 adaptation` workflow compiles the kernel, `boot.img` and the
device adaptation tarball. The separate system-candidate workflow now includes
the Ubuntu Touch rootfs and Halium GSI. A complete installation package still
requires verified Samsung vendor/runtime compatibility and a verified
installation/recovery route. Build success is not evidence that the handset boots.

Target handset (read-only ADB inventory, 12 October 2026):
- Android 12, One UI 4.1
- Baseband: G975FXXSGHWB3
- Build: G975FXXSGHWC1
- Kernel: 4.14.113-25257816
- Android and vendor both report Android 12/API 31.
- Stock codename `beyond2`; port codename `beyond2lte`.
- Bootloader reports `locked`, verified boot `green`.
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
Its output remains an experimental candidate; vendor runtime, stock boot/recovery
layout and a working Samsung recovery route must be verified before installation.
See [hardware test preparation](docs/hardware-test-preparation.md) for the
remaining firmware/CSC, backup, recovery and AVB prerequisites.

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

On the user's PC, the launcher retains the complete stock ZIP for recovery,
checks the AP TAR's MD5 and extracts only boot, recovery, dtbo and vbmeta into
`firmware-inspection-inputs.zip`. This small bundle is the next input for stock
header/AVB inspection. It performs no handset access or installation.
See [stock target](docs/stock-firmware-target-2026-10-12.json).

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
- Apply the documented 4.14 AppArmor socket/AF_UNIX patches, preserving attribution.
- Merge `config/ubuntu-touch.config` after the Samsung defconfig. Validate the
  effective kernel configuration after compilation.
- Enable the overlay store needed by modern Ubuntu Touch.
- Align the old session grid setting with the S10+ DeviceInfo value of 27.
- Preserve the upstream non-dynamic ramdisk, boot header v1 and 4096-byte rootfs
  sectors. No assumption is made about the actual system partition size.

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
