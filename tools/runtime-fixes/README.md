# Recovered runtime fixes

These text snapshots preserve the configuration recovered read only through TWRP on **5 November 2026**. They are reference inputs for future SYSTEM integration. No installer or image assembly consumes this directory. Recovery file presence establishes installed bytes; it does not show that a service was enabled, running or successful during this recovery session.

[`manifest.json`](manifest.json) records SHA-256, size, normal Ubuntu Touch path and observed ownership/mode for twelve recovered files. Eleven have exact snapshots here. The existing maintained [`ut-s10-trrs-integrato.py`](../../scripts/ut-s10-trrs-integrato.py) matches the twelfth after LF normalization and is not duplicated. Recovery mount aliases have been translated to normal OS paths; device serials, keys, runtime boot IDs and personal data are excluded. Git preserves text bytes; recorded Linux modes and ownership must be deliberately applied by any future installer.

| Sources | Prior evidence and limits |
| --- | --- |
| `audio6/` | Audio6 v2 restored normal PulseAudio and physical speaker/microphone operation. Later TRRS v4 insertion/removal and reboot persistence were observed on the test handset. These recovered files do not add a new playback or microphone test. Headset microphone, UI labels and default-sink stability remain open. |
| `wifi/` | The unmanaged-`wlan0` workaround was reported persistent after reboot, with internet retained through `wlan1`. Reconnection, hotspot and Wi-Fi Direct remain unverified. No network credentials are stored here. |
| `usb/` | Earlier USB boot configuration and basic MTP operation were observed. The recovered original and patched configurators retain the UBports license notice. This recovery does not validate normal-boot ADB, two-way transfers or a clean install. |

The [status](../../docs/status.md) and [dated evidence](../../docs/evidence/README.md) retain the original hardware-validation boundaries.

## Dependencies before integration

Audio6's drop-in uses `audio_guard.py` and the patched `ld.config.txt`, private user/mount namespaces, an existing PulseAudio service/socket and D-Bus. The guard pins the BOOT 6 kernel, phablet UID/GID, original linker configuration and Android audio libraries. Its bindings expose the HIDL compatibility wrapper at two vendor HAL paths without replacing the underlying binaries. The primary-sink unit invokes `pactl`; TRRS additionally requires the existing audio6 baseline and exact ARM64 droid-module identity. Library availability, service enablement links, ordering and user-session ownership must be validated separately.

The USB wrapper expects `/userdata/ubuntu-touch-usb-config-1/manifest.json`, a pinned original configurator, the exact BOOT 6 kernel, root-owned payloads and a pristine normal-boot configfs gadget. Its installation manifest contains a per-installation boot ID, deliberately omitted here. The public preservation manifest is **not** that installation manifest and cannot be substituted for it. Do not replay this recovered drop-in automatically: it clears the original `ExecStartPre`, and a failed or stale guard can prevent `usb-moded` from starting. A future installer must establish a fresh guarded installation state and preserve recovery access.

Before assembling a new SYSTEM, reconcile these files with the exact base image, collect service/link and library identities, design installation and rollback, then test normal-boot behavior. No new SYSTEM, BOOT, clean-install or hardware claim follows from this source recovery.

Verify preserved identities without executing any recovered helper:

```sh
python3 -m unittest discover -s tests -p test_runtime_fix_sources.py -v
```
