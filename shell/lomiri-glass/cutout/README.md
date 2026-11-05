# S10+ front-camera cutout: candidate geometry, not an installer

The active Ubuntu Touch 24.04 handset probe matched **9/9** Lomiri QML source
hashes. `device-info get GridUnit` returned `27`, while `CollapsedPanelHeight`
and all three cutout properties returned `Unknown prop`. The Linux framebuffer
reported a 1440x6080 *virtual* size; Samsung specifies a 1440x3040 physical
display for this model, consistent with a double-height virtual framebuffer.

Two frontal photographs show the dual-camera pill near the top-right edge,
overlapping the current indicator row and clock. Projection from the camera
photos into physical display pixels gives a **rough** envelope around
`x=1110..1390`, `y=55..185`. The recommended initial avoidance area is more
conservative: **`1080 0 360 210`** (x, y, width, height), with 30+ pixels of
left-side margin and all space to the right edge reserved. This region will
reduce the horizontal space available to indicators. It is a *calibration
candidate*, not verified device geometry.

The included `DeviceInfo-keys.snippet` is deliberately **not** a complete YAML
profile. Never replace `/etc/deviceinfo/devices/*.yaml` with it. The original
device mapping contains other settings (e.g. grid, orientation and hardware
features) that must be preserved. `CollapsedPanelHeight` is 3 × the current
27-pixel GridUnit, matching Lomiri's existing fallback instead of enlarging
the entire top bar. The cutout's larger 210-pixel y extent still represents
the camera exclusion envelope; Lomiri's portrait row placement avoids the
horizontal x/width interval.

## Complete DeviceInfo mapping obtained from the actual handset

On **23 October 2026** the user read both files on the Galaxy S10+:

- `/etc/deviceinfo/devices/beyond2lte.yaml`
- `/opt/halium-overlay/etc/deviceinfo/devices/beyond2lte.yaml`

Both showed the same `beyond2lte` mapping: alias `beyond2`, Samsung vendor,
`Galaxy S10+`, phone type, `GridUnit: 27` and Portrait, Landscape and
InvertedLandscape. Neither includes cutout properties. The complete
**illustrative** merge is now in `beyond2lte-merged-candidate.yaml`; it adds
only `CollapsedPanelHeight` and the three `DisplayCutouts*` lists. The source
files were viewed through the user's terminal output, not copied from the
device with authenticated file hashes. Trailing spaces and actual mount
layouts must be checked on the device before moving further.

To make an exact merge **without changing the system**, extract the complete
package on the handset and run as `phablet`, **not with sudo**:

```sh
python3 scripts/lomiri_glass_cutout.py stage \
  --output "$HOME/lomiri-glass-cutout-stage"
```

The script checks both real file contents against the observed profile,
refuses differing mappings or existing cutout keys, preserves each original
byte-for-byte under distinct filenames, and writes the appended candidate and
`deviceinfo-stage-report.json` in a fresh home-directory folder. It collects
read-only filesystem mount descriptions when `findmnt` is available; it does
**not** call an installer, `sudo`, bind mounts or shell restarts. It never
overwrites a pre-existing output folder. Send back only the JSON report first.

If the profile is different on the phone, the script deliberately stops. The
candidate is *not* ready for installation: a recovery path plus on-device
measurement of the camera exclusion area are outstanding. Upstream also notes
that landscape cutout placement has limitations, so that orientation must not
be declared compatible on the strength of a portrait simulation alone.

## Before a reversible trial

1. Review the two originals and the isolated merged candidate from `stage`;
   verify the active DeviceInfo selection and exact file hashes. Lomiri
   currently chooses its old `WithoutCutouts` panel. A valid cutout key can
   select `WithCutouts` at **next shell start**, not necessarily via reload.
2. Verify file/mount layout; do not overwrite the overlay or replace
   DeviceInfo in a running session merely because the YAML now parses.
3. Provide an automatic timed restore and a recovery-shell escape route
   **before** starting the new Lomiri process; do not change BOOT/SYSTEM.
4. On the handset, examine clock, notifications, network (including dual SIM),
   landscape, light/dark appearance and top-edge gestures. Adjust candidate
   coordinates if necessary; photograph-based figures are provisional.

Useful read-only handset command for the next stage:

```sh
ls -l /etc/deviceinfo/devices/
device-info get GridUnit
```

Documented Lomiri implementation: [UBports display cutouts](https://docs.ubports.com/en/latest/porting/configure_test_fix/device_info/DisplayCutouts.html).
UBports provides a visual calibration tool named
[`tool-notch-helper`](https://gitlab.com/ubports/porting/tools/tool-notch-helper).
