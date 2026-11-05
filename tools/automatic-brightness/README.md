# S10+ automatic-brightness profile candidate

This profile supplies the missing device-specific brightness curve for repowerd.
It has not been installed or accepted on the handset by this source change.
The existing ambient light sensor and repowerd algorithm are reused; this does
not add a sensor reader, change the kernel, or calibrate the display.

The three resources in `config-beyond2lte.xml` are copied unchanged from
[LineageOS exynos9820-common 0917d5a3](https://github.com/LineageOS/android_device_samsung_exynos9820-common/blob/0917d5a3da9d03eabbf3e5dc8d864b969a445ba1/overlay/frameworks/base/core/res/res/values/config.xml):
`automatic_brightness_available=true`, 35 increasing ambient-lux thresholds and
36 nondecreasing brightness outputs in the range 22..255. The original license
is retained. `manifest.json` records the complete source-file hash, exact arrays
and profile hash. No other Android resources are imported.

## Correct scale and selection

In the installed repowerd source
[36575160752bdd0a983bee1b53e041ccc4ceaa60](https://gitlab.com/ubports/development/core/repowerd/-/tree/36575160752bdd0a983bee1b53e041ccc4ceaa60):

- `AndroidDeviceConfig` loads `config-default.xml`, then `config-<DeviceName>.xml`.
  `config-beyond2lte.xml` matches the live `device-info get Name` result
  `beyond2lte`, as well as the inspected deviceinfo filename.
- `AndroidAutobrightnessAlgorithm::create_brightness_spline()` uses
  `autoBrightnessLevels` and `autoBrightnessLcdBacklightValues`, prepends the
  zero-lux point, and builds a monotone spline. These arrays have exactly the
  required N/N+1 shape, so no resampling or fallback table is used.
- `BrightnessParams` keeps the existing maximum of 255; `notify_brightness()`
  divides the spline output by that maximum. Thus the curve's output is a
  normalized fraction, not a raw panel register value.
- `SysfsBacklight` separately multiplies a normalized request by the driver
  maximum. A reported panel maximum such as 48600 must never replace 255 in
  this profile or be written directly by this installer. The active backlight
  implementation and physical response still need runtime acceptance.

The default minimum, default brightness and dim policy are inherited from the
installed default XML. The Lineage dim setting and high-brightness/nits tables
are deliberately outside this profile's scope. No HBM claim is made.

## Installer and rollback contract

`python3 profile.py --status` reports file identity and saved-state presence;
it cannot establish that the running daemon loaded the profile.
`--install` and `--rollback` are root-only and require the exact BOOT 6 kernel
release, the observed `ID=ubuntu`, `VERSION_ID=24.04`, `VARIANT_ID=touch`, and the inspected
`/etc/deviceinfo/devices/beyond2lte.yaml` containing the `beyond2` alias.
An alternate `--root` is accepted for read-only status only.

Installation writes only
`/usr/share/repowerd/device-configs/config-beyond2lte.xml` and a 0600 state file
at `/userdata/ut-s10-automatic-brightness/state.json`. It preserves any preceding
profile bytes, mode and ownership for rollback. Every existing target/state
ancestor must be root-owned and not writable by group or others. The dedicated
state directory must be root-owned 0700 and the regular state file root-owned
0600; unsafe precreated directories/state are refused. Saved owner/group/mode
values are bounded and validated again before restore. Both writes are atomic; a saved
state allows a failed/interrupted installation to resume. A later unrelated
profile edit blocks overwrite/rollback. Symlink paths, nonregular files and
oversized inputs are rejected. A read-only root filesystem produces a visible
failure; the installer does not remount it.

For a separate controlled trial with `REPOWERD_DEVICE_CONFIG_DIR` pointing to
a userdata directory, that directory must contain **both** this device XML and
the verified installed `config-default.xml`. In the exact source, this variable
replaces the normal repowerd directory; only the legacy powerd directory remains
as a fallback, and it may be absent. The trial's caller owns the temporary service
environment, original-default hash, directory ownership and restoration. This
native-path installer does not install or change such a service override.

Rollback restores the previous profile, or removes only this profile if none
existed. It does not restart repowerd. Neither action changes GSettings,
brightness/sysfs, sensor permissions, packages, service configuration or power
state. Activation is always reported as false/unknown, requiring the caller's
separate controlled runtime verification.

## Acceptance and UI capability

The caller must preserve the current brightness/auto-brightness preference and
confirm the exact profile path is among the daemon's effective config directories
before a controlled reload. The daemon's current startup log must show the true
availability property and both imported arrays, with no spline/light-sensor
initialization error. A real ambient-light change and a user preference toggle
must then produce the expected readback and physical brightness response. Merely
seeing a profile file or a saved preference is insufficient.

The uOS27 native host keeps `automaticBrightnessProfileVerified=false` until that
acceptance evidence exists. Its setter continues to use the real
`com.lomiri.touch.system` auto-brightness preference and readback. This profile
does not provide a live lux value to the UI, so `ambientLuxAvailable` stays false
unless a separate real sensor interface is verified.

Run offline Python fixtures with
`python3 -m unittest discover -s tests -p test_automatic_brightness_profile.py -v`.
They verify table shape/range/hash, context guards, atomic backup/resume,
idempotence, exact rollback, edit conflicts, bounded reads and CLI failure.
Linux CI additionally exercises symlink and FIFO rejection. These tests do not
prove hardware calibration or end-to-end automatic brightness.
