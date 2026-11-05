# Restore the saved USB mode after rescue startup

This S10+ BOOT 6 helper addresses a confirmed mode-selection mismatch: `mode_request` remained `developer_mode` (USB networking), while the saved configuration was `mtp_adb`. One public `set_mode` selection activated Ubuntu's ADB service. This is separate from the kernel's missing mass-storage function and from Windows MTP driver matching.

The root oneshot runs after the existing rescue-off and force-ADB services. It preserves force markers, an intentionally saved `developer_mode`, other current modes and unavailable/unsupported saved modes. Only a remaining rescue/developer-mode mismatch triggers one supported `set_mode` call. It never calls `set_config`, edits authentication, writes sysfs/configfs, restarts USB services or retries a mutation. Readback polling is bounded to five seconds; the systemd unit has a 25-second timeout.

The kernel-release guard checks compatibility with `4.14.280-gb9b70b29c94c-dirty`; it is not an image-hash check. Deployment additionally requires verified device/image identity and the existing init-done, service and userdata layout. This directory is source, not an automatic installer for another handset.

## Deployed paths

- Helper: `/userdata/ut-s10-usb-mode-restore/restore-saved-mode.py`, root-owned, mode 0644.
- Unit: `/etc/systemd/system/ut-s10-usb-restore-saved-mode.service`, root-owned, mode 0644.
- Enablement: `graphical.target.wants/ut-s10-usb-restore-saved-mode.service` points to the unit.

On the inspected TWRP userdata mount, these correspond to `/data/ut-s10-usb-mode-restore/` and `/data/system-data/etc/systemd/system/`. Do not use hardcoded historical block numbers: the currently observed layout differs from the original installation tooling.

## Verification and rollback

Run the fixture tests with `python3 -m unittest discover -s tests -p test_usb_saved_mode.py -v`. These do not prove boot ordering or hardware behavior. For handset acceptance, inspect the unit's `Result`/`ExecMainStatus`, its journal, actual usb-moded mode, adbd state and host ADB shell after a normal boot. A successful oneshot may become `inactive`; that alone is not failure. Preserve the saved mode and check that authentication remains enabled.

To disable this added behavior in TWRP, remove only its newly created enablement symlink under `/data/system-data/etc/systemd/system/graphical.target.wants/`. The new unit/helper may remain inert. This does not change BOOT 6, the original configurator, graphics, audio, Wi-Fi or the stored USB setting.

Handset results and limitations are recorded in [the dated USB diagnosis](../../docs/evidence/usb-normal-boot-diagnosis-2026-11-05.md).
