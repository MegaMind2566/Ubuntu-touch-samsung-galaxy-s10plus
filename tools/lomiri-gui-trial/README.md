# First timed native GUI trial

Candidate source only, prepared 5 November 2026. No revised GUI has been installed
or accepted on the handset. This is one ten-minute Lomiri QML trial, with an
unconditional return to the original shell. There is no accept/commit command.

## Observed compatibility

The parent collected 26/26 matching QML originals on the actual SM-G975F,
Ubuntu 24.04 touch/arm64, with `lomiri` and `lomiri-common` both exactly
`0.5.0+0~20260910085057.5+ubports24.04.2~1.gbp0bd07c`. The source base is
`0bd07c68b7ab8dee5720516c7549dff8992995c6`. Original `/usr/share/lomiri` is
root-owned 0755, not a symlink, has no nested mount and has no `Panel/Glass`.
The root SYSTEM filesystem is read-only. LightDM is active with its existing
graphics/session/wait-for-HWC configuration preserved. A partially unreadable
drop-in was not assumed absent or replaced.

Native Lomiri.Components, QMenuModel/settings menus and the actual GSettings
module (`qml-module-gsettings:arm64`) are present. DeviceInfo returned no valid
cutout rectangles; the candidate retains its provisional 27% right-side reserve.
It is not a physical cutout calibration. Full runtime/root/mount-namespace and
package identity are checked again before a mount, not inferred from version
strings or a previous probe alone.

## Narrow payload and recovery

The package contains 26 modified QML files and 13 new Glass QML/JS files. On
the handset the preparer copies the current complete installed resource tree,
checks all 26 originals, applies the locked patch and adds the 13 modules.
Unchanged graphics/resources come from the handset, not the desktop fixtures.
The complete prepared tree and affected originals are retained under a private,
root-owned `/run/ut-s10-gui-trial-20261105`. Its mounted QML root is readable by
Lomiri; the private parent, state and recovery entrypoint remain root-only.

The external SHA-256 of `candidate-manifest.json` binds every payload and the
executable support code. The package must be root-owned and not writable by
other users. Preparation checks Linux/BOOT 6, Ubuntu/arm64, exact package
versions, native LightDM, shared PID1/LightDM mount namespace, no existing live
or nested QML mount, no stale trial, source hashes and available volatile space.
It never copies a desktop mock or font into the production shell.

Before the first bind mount, PID1 must acknowledge an active recovery timer for
600 seconds. The script mounts only `/usr/share/lomiri`, verifies the mounted
inode/identity, remounts it read-only, then schedules a LightDM restart after
three seconds. The existing LightDM unit, credentials, PAM, session policy,
package files, BOOT, SYSTEM and VENDOR are not replaced. The original unit's
dependencies/drop-ins still execute during both restarts.

Recovery stops both owned activation timer/service, stops LightDM to release
GUI references, then uses normal unmount only for the trial's own mounted
inode/mount ID. It checks the original QML inventory and starts native LightDM
even when the candidate left it inactive. Ordinary stop/unmount/status errors
still attempt display recovery and produce a failed result, never a false
acceptance. It never unmounts a foreign
overlay, performs lazy unmount, or automatically reboots the device. An early
manual restore leaves the independent timer armed; its later call is idempotent.
`ROLLBACK_OK` establishes command/hash readback, not visual recovery or a
successful unlock. The parent must confirm the stock screen and touch afterward.

The root-owned 0644 `/run/ut-s10-gui-trial-status.json` is readable from the
ordinary ADB/SSH user. It exposes only phases, an advisory deadline, recovery
hash/active-state booleans and a failure flag. It contains no private inventory,
identifiers or command input, and cannot trigger a privileged operation.
Recovery calls serialize through a root-only lock; a timer waits for a concurrent
early restore and checks again. No unprivileged restore socket is introduced.

If normal unmount/restart fails, the timer remains a recovery attempt rather
than a promise. Independent SSH/ADB access and physically available TWRP remain
required. A manual reboot removes the volatile `/run` bind; a one-shot boot
handoff must already have consumed its activation marker so it cannot replay.

## Explicit privileged handoff

`trial.py` does not install or enable a system service and does not attempt
privilege escalation. The current normal ADB shell is unprivileged. The parent
must use an explicitly reviewed TWRP root handoff if no existing authorized root
channel is available. Stage/check the private package, timer/recovery route and
one-use marker before enabling a boot handoff. No persistent root command service
or writable user-supplied command may be introduced. Do not activate during a
USB transfer, reconnect/lock experiment or other session-sensitive work.

The commands below describe the reviewed root entrypoint, not an instruction to
run them from the current user session or to replace its permission policy:

```sh
python3 PACKAGE/tools/lomiri-gui-trial/trial.py check --package PACKAGE --manifest-sha256 EXPECTED_SHA256
python3 PACKAGE/tools/lomiri-gui-trial/trial.py stage --package PACKAGE --manifest-sha256 EXPECTED_SHA256
python3 PACKAGE/tools/lomiri-gui-trial/trial.py trial --package PACKAGE --manifest-sha256 EXPECTED_SHA256
python3 /run/ut-s10-gui-trial-20261105/rollback.py restore
```

`stage` is optional: `trial` can stage a new run after the same guards. A previous
run is never automatically overwritten or cleaned. Every signature or version
mismatch refuses the trial. Neither positive UI feedback nor a marker silently
turns this first trial into a permanent installation.

## What this first GUI can exercise

Home/catalog/dock/search, native top-panel controls, notification cards/privacy,
native greeter PIN presentation and bottom Home/right-edge switcher integration
are QML candidates. The real native application and notification models remain
authoritative. Lock/PIN still forwards the original LightDM challenge and never
verifies a credential itself. Existing passwords, multiple users and fallback
authentication keep native routing; their full handset behavior needs review.

Wi-Fi/radio, manual brightness and volume requests use native indicators and
readback. The optional existing `uos27_radio_bridge.py --serve --ttl 720` runs
only as the Lomiri user, after that user bus exists, and supplies BlueZ readback
and read-only repowerd support. Without the bridge, unavailable automatic
brightness is displayed honestly. The root trial does not start that user
bridge or alter brightness/Bluetooth preferences itself. The optional user-only
`uos27-radio-bridge.service` has no Install section and a 750-second hard runtime
limit. Its reviewed Python source must first be copied to the unit's exact
user-cache path; start it only after the new user bus exists, never as root.

Maliit keyboard, compiled Settings/app content, folders, Liquid Glass refraction,
GPU timing and complete iOS 27 parity are outside this first shell-only trial.
Do not bind old Settings binaries or historical Maliit themes into this trial.
The tested Qt fixture pipeline and a successful source match do not establish
handset visual acceptance, lock security, app launch or notification delivery.

## Validation

The separate free GitHub `uos27-preview.yml` workflow runs the inert
`tests/test_lomiri_gui_trial.py` filesystem/mount/service policy fixtures, then
the existing Qt native component tests and renders. These fixtures execute no
real mount, systemd operation, display restart or phone command. A physical trial
requires the source/runtime guard plus separately observed timer and rollback.
