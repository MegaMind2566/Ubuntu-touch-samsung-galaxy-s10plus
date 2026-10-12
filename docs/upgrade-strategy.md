# Upgrade strategy: Ubuntu Touch 24.04

Target: Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`), stock Android 12 / One UI 4.1.

## Release selection
- Stable 24.04-2.0 was announced July 2026; 24.04-2.1 release candidates were tested in September/October 2026.
- **Do not assume 24.04-2.1 stable is published or that S10+ is supported.** Verify release status and device channel before pinning.
- Goal: boot a known historical Halium port first, then assess 24.04 compatibility and rootfs/partition constraints. Newer Ubuntu Touch rootfs is not a drop-in replacement for an old device port.

## Compatibility gates
1. Confirm exact source branch, kernel, deviceinfo and firmware/vendor base.
2. Verify device partitions, boot/recovery image layout and Samsung-specific flashing.
3. Build reproducibly and inspect image metadata; no automatic flashing.
4. Verify hardware on-device: display, touch, charging, Wi-Fi, modem, calls, SMS, audio, camera, sensors, suspend.
5. Only then assess migration to 24.04-1.x / 24.04-2.x with updated components.

References:
- https://devices.ubuntu-touch.io/device/beyond2lte/
- https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820
- https://forums.ubports.com/topic/12605/call-for-testing-ubuntu-touch-24-04-2.1/
