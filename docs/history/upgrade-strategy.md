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

## Handset inventory and system assembly

The 12 October 2026 read-only ADB inventory confirms SM-G975F/Exynos 9820,
Android 12/API 31 and vendor Android 12/API 31, firmware G975FXXSGHWC1.
Boot is 55 MiB; the first adaptation boot is 50.75 MiB. System is 5700 MiB,
vendor 1100 MiB, recovery 64.5 MiB, dtbo 8 MiB and vbmeta 64 KiB.
Sizes are resolved from the partition links and `/proc/partitions`; sysfs size
reads returned empty values. The bootloader remains locked. Knox's property reports
`1`; this is recorded as a raw property, not an unlock-status inference.

The assembly workflow targets a 5120 MiB system filesystem, with 580 MiB of
partition margin. It combines the pinned first adaptation with official UT
24.04-2.x arm64 rootfs build 125 and Halium 12 GSI build 1310. These binary
inputs are locked separately from source revisions. Android version agreement
is a necessary prerequisite and does not verify Samsung vendor services or
hardware. The generated files do not include a vendor, recovery or vbmeta
replacement and are not an installation package.

References:
- https://devices.ubuntu-touch.io/device/beyond2lte/
- https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820
- https://forums.ubports.com/topic/12605/call-for-testing-ubuntu-touch-24-04-2.1/
- https://docs.ubports.com/en/latest/porting/build_and_boot/standalone_kernel_install.html
- https://man7.org/linux/man-pages/man5/proc_partitions.5.html
