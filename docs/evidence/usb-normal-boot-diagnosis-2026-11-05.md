# Normal-boot USB diagnosis — 5 November 2026

## Accepted outcome later in the session

Live authenticated SSH confirmed `mode_request=developer_mode` with stored `mtp_adb`. One public `set_mode mtp_adb` activated adbd and its FunctionFS preparation. Windows enumerated a healthy WinUSB ADB interface; the initial host state was unauthorized and no approval prompt appeared. The PC's public ADB key was authorized through the already authenticated SSH channel, retaining `ADBD_SECURE=1`. A subsequent transient `rndis_adb` selection refreshed the transport and a normal Ubuntu ADB shell succeeded.

The new [saved-mode helper](../../tools/usb-mode-restore/README.md) then passed 12 fixture tests and independent review. It was installed in userdata via TWRP with staged/installed hashes and ownership checked. One following normal reboot returned ADB automatically, with the oneshot reporting `Result=success`, `ExecMainStatus=0`, journal `restored: mtp_adb`, and matching current/saved mode. Both adbd and its preparation service were active. The shell reports UID 32011, Ubuntu 24.04 and the existing BOOT 6 kernel. No firmware or Windows driver was changed. [Machine-readable acceptance](usb-saved-mode-acceptance-2026-11-05.json).

SSH public-key access and socket enablement were prepared from recovery because normal Ubuntu lacked administrative authorization; no password was requested or authentication disabled. Only dedicated PC public keys were installed; private keys remain on the PC and are excluded from source/deliverables.

Power readings after the accepted reboot showed USB online=1 and Charging/99%; the follow-up at 11:53:18 Europe/Rome showed Full/100%. This is a brief observed charge progression, not a current/rate, full-cycle or endurance test. The bounded energy v2 inventory also completed in 0.71 s with no warnings. At this earlier ADB acceptance, Windows MTP still reported problem code 28. Later the user selected the compatible Windows driver and a small-file MTP round trip was hash-verified; see the [separate MTP evidence](mtp-windows-2026-11-05.md). The missing mass-storage charging fallback remains a separate kernel limitation.

A later unplugged physical screen-off/wake trial returned ADB `offline` after USB reconnect, while Wi-Fi SSH was usable. A transient official mode sequence `developer_mode` then `mtp_adb` restored ADB without reboot. This reconnect regression remains open and does not invalidate or extend the earlier one-boot helper acceptance. Its cause is not established; see [the separate trial](screen-off-wake-2026-11-05.md).

The sections below preserve how the diagnosis was reached. The reconnect test by itself did not restore the interface; direct mode inspection and selection established the mismatch before the new service's boot acceptance.

## New observations

Windows sees the SM-G975F as composite `1209:0004`. Its only enumerated function is RNDIS (`MI_00`, compatible class/subclass/protocol `e0/01/03`). Both composite and network drivers report problem code 0. The USB network is up and receives an address from the handset. No ADB interface is enumerated in that normal-boot state.

After the user starts `ssh.socket`, SSH responds with OpenSSH 9.6p1 Ubuntu. Authentication requires a public key; this PC is not yet authorized. No password or authorization policy was weakened.

The user subsequently boots TWRP. ADB then sees `beyond2lte` in recovery, independently demonstrating that host ADB communication works in that state. The installed recovery is `3.7.1_12-Android-Artisan_v2-`, not the old pinned recovery. Its current named links map `userdata` to `sda34`, `system` to `sda25` and `cache` to `sda31`. Old scripts guarded for userdata `sda31` must not be loosened or reused as installers on this layout. The BOOT prefix still matches the frozen BOOT 6 identity; this is an identity check, not a new graphical-boot test.

## Recovered configuration and previous-boot evidence

The installed October USB trial is preserved in `/data/ubuntu-touch-usb-config-1`: wrapper, minimally patched configurator and systemd drop-in. Both payload hashes match its installation manifest. The original configurator matches SHA-256 `76059b53af8a12796e3c2908ad8934fa7ca32d65c678d6a97a47a1fce588006a`. The unique installed boot ID is not copied into public evidence.

The stored usb-moded setting is already `mtp_adb`. Defaults map RNDIS to PID `0004`, MTP+ADB to `0003` and RNDIS+ADB to `0005`. The standard `adbd.service`, socket and FunctionFS preparer exist, with secure ADB still enabled. No `.force-adb` or `.force-ssh` marker is present.

Read-only inspection of the saved normal-boot journal records, at 09:36:55 UTC on 5 November:

```
CONFIGFS detected
function mass_storage.usb0 is not registered
switch to charging mode failed
failed to activate charging, all bets are off
mode setting failed, fallback to undefined
```

At 09:36:58 UTC the rescue-off helper records `INIT DONE`, and usb-moded records `init_done -> reached`. The selected unit records contain no `adbd.service` or `adbd-prepare.service` start for that boot. This does not rule out every conceivable Android-container process; it establishes the absence of the intended Ubuntu service activation in the inspected journal.

The exact BOOT 6 embedded kernel configuration has `CONFIG_USB_CONFIGFS_MASS_STORAGE` disabled, while FunctionFS, MTP and RNDIS support are enabled. This explains the mass-storage charging fallback failure. `CONFIG_USB_CONFIGFS_F_ADB` being disabled does not establish lack of ADB support: this userspace expects `ffs.adb`, for which FunctionFS is enabled.

## Interpretation and next narrow test

Two issues must be kept distinct. Upstream usb-moded's charging fallback uses mass-storage and fails on this kernel. Dynamic `mtp_adb` activation follows a separate path, so enabling mass-storage alone is not a demonstrated ADB fix.

The installed usb-moded starts with rescue flag `-r`. In the matching upstream `0.86.0+mer69` control code, the internal rescue latch can retain developer/network mode after init-done until an explicit selection or cable disconnect. This is consistent with PID `0004` despite stored `mtp_adb`, but is not yet runtime proof of the active mode variable.

Next: after a normal graphical boot and unlock, disconnect/reconnect the cable once and inspect the resulting Windows interface and ADB state. If needed, obtain current/available/configured modes and make one transient official `set_mode mtp_adb` selection; preserve the already-correct stored setting. An SSH session over RNDIS will intentionally disconnect when the USB mode changes. Do not replace the working RNDIS driver, disable ADB authentication, remap mass-storage to another function, or flash a new kernel for this test.

Sources: [UBports USB configuration](https://docs.ubports.com/en/latest/porting/configure_test_fix/USBModed.html), upstream [control](https://raw.githubusercontent.com/sailfishos/usb-moded/mer/0.86.0%2Bmer69/src/usb_moded-control.c), [worker](https://raw.githubusercontent.com/sailfishos/usb-moded/mer/0.86.0%2Bmer69/src/usb_moded-worker.c) and [configfs](https://raw.githubusercontent.com/sailfishos/usb-moded/mer/0.86.0%2Bmer69/src/usb_moded-configfs.c).

No phone driver, firmware, audio, Wi-Fi or USB configuration was changed during this recovery inspection. A normal reboot was requested for the targeted reconnect test. Configurations and scripts were copied to the PC with size and independent SHA-256 checks; source recovery is not clean-image integration or a new hardware acceptance test.
