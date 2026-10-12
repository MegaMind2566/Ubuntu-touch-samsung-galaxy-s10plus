# Ubuntu Touch — Galaxy S10+ Exynos (beyond2lte)

Experimental port workspace for Samsung SM-G975F/DS (Exynos 9820).

## Status
**Experimental Halium 12 build preparation. No on-device validation.**

The `S10+ Halium 12 adaptation` workflow compiles the kernel, `boot.img` and the
device adaptation tarball. It does not produce a complete installation package:
the Ubuntu Touch rootfs, matching vendor and verified partition sizes are still
required. Build success is not evidence that the handset boots.

Target handset (reported):
- Android 12, One UI 4.1
- Baseband: G975FXXSGHWB3
- Build: G975FXXSGHWC1
- Kernel: 4.14.113-25257816
- OEM unlock option visible; bootloader unlock **not** verified.

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
