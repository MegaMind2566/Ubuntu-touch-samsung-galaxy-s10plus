# Upgrade strategy: Ubuntu Touch 24.04

Target: Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`), stock Android 12 / One UI 4.1.

## Release selection
- Stable 24.04-2.0 was announced July 2026; 24.04-2.1 release candidates were tested in September/October 2026.
- **Do not assume 24.04-2.1 stable is published or that S10+ is supported.** Verify release status and device channel before pinning.
- Active source base: community `halium-12`, commit `06facc6fbc9cfda5f57428a6d7eeb805f5dedb89`, with the pinned Halium 12 kernel. Do not downgrade Samsung bootloader/firmware to match the historical Android 10 port.
- First compilation target: S10+ device adaptation with Ubuntu Touch 24.04-2.x overlay layout. This does not yet bundle a rootfs or establish a supported update channel.
- `Ubuntu Touch 24.04 input metadata` checks Jenkins rootfs/GSI build numbers and official device channels separately. Daily rootfs availability does not prove that 24.04-2.1 stable is published.

## Findings from source inspection
- The Halium 12 Samsung defconfig does not enable AppArmor and explicitly disables `CONFIG_FHANDLE`. Apply the two UBports-linked 4.14 socket/AF_UNIX patches and merge the local UT configuration fragment.
- Upstream uses boot header v1, ARM64 kernel, a non-dynamic ramdisk, and the `system` partition label. Keep this layout until stock image inspection provides a reason to change it.
- The vendor download linked in the historical README was published in October 2021. It is not evidence of Android 12 compatibility and is not bundled with this adaptation build.
- Source pins and recorded input checksums improve traceability. Toolchain and prebuilt binary downloads still need a complete lock before calling the whole image build reproducible.

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
