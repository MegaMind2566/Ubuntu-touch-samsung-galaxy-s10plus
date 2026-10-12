# Ubuntu Touch — Galaxy S10+ Exynos (beyond2lte)

Experimental port workspace for Samsung SM-G975F/DS (Exynos 9820).

## Status
**Research / preparation only. No bootable or tested images yet. Do not flash.**

Target handset (reported):
- Android 12, One UI 4.1
- Baseband: G975FXXSGHWB3
- Build: G975FXXSGHWC1
- Kernel: 4.14.113-25257816
- OEM unlock option visible; bootloader unlock **not** verified.

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
