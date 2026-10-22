# Project status

Updated: **22 October 2026**, following handset audio, Wi-Fi, USB, modem and sensor checks. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**, Ubuntu Touch 24.04 / Halium 12.

## Active direction and validated baseline

Development remains focused on Ubuntu Touch. The separate Sailfish project is paused; it has not been installed on this handset. **BOOT 6 with graphics-permission correction 1 remains the running baseline**; these new tests do not constitute a new SYSTEM or BOOT image release. The port boots to a graphical session with working touch and basic Wi-Fi, but daily-driver reliability is not established.

### Verified on the handset

| Area | Evidence and result | Boundary |
| --- | --- | --- |
| Graphical boot and touchscreen | User-confirmed normal Ubuntu Touch graphical session and touch interaction. | Long-term stability still needs measurement. |
| Display rotation, accelerometer, gyroscope and orientation | Actual changing sensor samples; UI autorotation confirmed. | No accuracy certification. |
| Ambient light sensor and barometer | Fresh light/pressure samples decoded from SensorFW socket streams. | Automatic screen brightness still not working/confirmed; absolute calibration not measured. |
| Magnetometer and compass basic measurements | Changing samples; calibration level progressed 0 to 1. | Absolute north and physical repeatability not established. |
| Wi-Fi radio connectivity | Real internet connection via `wlan1`; both 2.4 and 5 GHz networks detected. | Duplicated UI and intermittent connection problems described below. |
| PulseAudio and physical speaker | Audio-6 v2 restored the normal Ubuntu Touch PulseAudio service; user heard audio and reported clean playback through `sink.primary-out`. | Microphones and remaining output paths untested. |
| Built-in microphone and playback | 22 October: `source.primary-in` with `input-builtin_mic` recorded ~4.82 s of actual voice, `parec` reported success, ~52.15% peak and 0% clipping, and the user confirmed clear replay on `sink.primary-out`. | Does not establish secondary microphones, headset mic or call capture. No voice recording stored. |
| PulseAudio post-reboot selection | After a later reboot, `pulseaudio.service` was active and the dedicated user unit selected `sink.primary-out`, with success reported. | Fresh listening after that particular reboot was not separately documented. |
| USB MTP basic use | User confirmed memory access from another Android handset over USB-C; targeted USB boot configurator executed on earlier reboot. | Two-way file transfer and other hosts/USB modes not fully verified. |
| LTE modem/SIM detection | oFono exposed two modem objects; one valid SIM in slot 2 was registered to LTE on a handset test. | No verified call, SMS or mobile packet transfer. |

### Known anomalies and incomplete tests

| Area | Current observation | Next check |
| --- | --- | --- |
| Wi-Fi duplication | Driver `wl` exposes `wlan0` and `wlan1`, both managed by NetworkManager on the same `phy0` and both scanning 2.4/5 GHz. Two settings lists and two status icons appear while both are managed. Making idle `wlan0` unmanaged yielded one list with internet still working via `wlan1`. | A guarded configuration file under `/etc/NetworkManager/conf.d/` was installed; after an accidental rollback the user reinstalled it and **confirmed persistence after a normal reboot (22 October 2026)**. The duplicate lists were eliminated while internet remained functional on `wlan1`. This is a user-reported post-reboot validation, not an independently collected post-boot log. Separately check reconnect over time, hotspot and Wi-Fi Direct. |
| Wi-Fi connection errors | NetworkManager attempted some connections with no available secrets (`no-secrets`). | This proves those authentication failures, not the cause of all intermittency. |
| Temporary graphical artifacts | User observes brief colored lines during browser surface resize, especially when the on-screen keyboard disappears. | Graphics compositor/buffer investigation; **video decoding itself has not been tested**. |
| GNSS/GPS | Service active; during a 120-second run up to 3 satellites were signaled, none used for a fix; no new position update. | Outdoor satellite fix and positioning test. |
| Proximity | SensorFW denied the proximity session: ID not registered. | Check SensorFW/HAL registration and actual near/far behavior. |
| Audio routing | HAL reported `Failed to create ... audio patch (38)` for output and input, **but a real five-second built-in mic recording and playback succeeded**. | Wired headset/jack detection, earpiece, hands-free and call audio are untested. HAL errors must be correlated with functional failures rather than presumed fatal. |
| Fingerprint, Hall, heart-rate sensor | Respective kernel/daemon interfaces detected. | No successful physical operation demonstrated. |
| Battery and charging | Kernel exposes power/battery readings. | Verify actual charge progression, wireless charging, suspend and consumption. |
| Camera, Bluetooth, NFC, SMS, mobile data and other hardware | No conclusive functional test yet. | Targeted tests only; avoid labelling these features broken without evidence. |

## Next work

**Next: wired 3.5 mm headset detection and playback routing**, using only read-only PulseAudio state checks and manual listening. The built-in microphone has passed the functional test; do not repeat it without a specific regression. Follow with earpiece/call audio, SMS and mobile data, then battery/suspend and graphics/Wi-Fi reliability. Preserve current audio and Wi-Fi fixes; do not force audio profiles without separate safeguards. Preserve working audio-6 v2 and BOOT 6 baseline.

Only sanitized observations belong in the public repository: no raw handset logs, SSIDs/BSSIDs, device MACs, SIM details or voice recordings. Local mocked tests of a diagnostic script are **not** physical device validation.

## Resolved boot blockers and historical findings

Earlier attempts stayed at the Samsung logo. Source patches corrected the Samsung SAR ramdisk offset and late init selection; BOOT 4 reached the original initramfs handoff. BOOT 5 then demonstrated systemd/Android execution and a repeatable USB configfs NULL dereference. BOOT 6 contains the compiled NULL guard and the RAM profile/Android prestart integration.

Before the final permission correction, BOOT 6 already started the root compositor and spinner, but the unprivileged Lomiri session aborted for a missing mapper. The [runtime graphics probe](evidence/ubuntu-graphics-runtime-probe-2026-10-15.json) established the hwbinder EACCES path and root/nonroot difference. The intended adaptation udev rules had been skipped because their overlay destination was absent; the generic installed rule covered binder but not hwbinder/ion. [Correction 1](evidence/ubuntu-graphics-permission-fix-2026-10-15.json) restores only those two access modes through persistent userdata rules and a bounded pre-LightDM check. vndbinder, binder and Mali modes are unchanged.

The retained BOOT 6 panic belongs to a historical Power/Volume Down reset attempt: Samsung's six-second hard-reset hook deliberately calls `BUG()` before reset. Run 1 remained alive through the two-minute observer window; a panel power-down did not establish whole-device power loss. These findings did not justify another kernel rebuild.

Kernel symbol recovery, stock DTB/DTBO composition, source fixtures and ARM64 emulated tests are offline evidence, distinct from handset execution. Earlier dated build reports retain their original pre-test conclusions; the latest graphical result is recorded separately.

## Next work

Retain the working BOOT 6 and permission correction. Record the visible setup/home screen and collect the correction's result/session logs when available, without treating another reflash or Format Data as a prerequisite. The post-correction service/node checks and fresh image identities remain to be corroborated by that report.

Then validate Wi-Fi reconnect/suspend, charging and power management, followed by the remaining hardware functions. Track each result independently. Repair the adaptation's missing overlay destination in the reproducible SYSTEM assembly before presenting the userdata correction as a general installation method; the working handset does not need an immediate rebuild for that development task.

## Planned interface work

Added to the backlog on **21 October 2026**: a deep visual and interaction redesign of Lomiri to closely match a chosen iOS reference.

**Status: planned, not started. Priority: after stabilization of the base port.** Existing stability, power-management and essential hardware work takes precedence. Implementation depends on validated repeated boots, sustained graphical/touch/Wi-Fi operation, charging and suspend/resume, and a repeatable installation/recovery path. This roadmap addition records no new handset result.

- [ ] Choose the exact iOS visual reference and target screens, with layouts adapted to the S10+ display and camera cutout.
- [ ] Build a functional Home screen with pages, folders and dock, followed by a Control Center connected to real system services.
- [ ] Adapt the lock screen, notifications, app switcher and gestures while preserving the existing authentication and session mechanisms.
- [ ] Align the keyboard, shared toolkit components, Settings and selected core apps; track third-party app styling separately.
- [ ] Measure animation and blur performance, input behaviour and suspend/resume on the handset; provide reduced effects where needed.
- [ ] Package versioned, reproducible changes with an update-compatibility check and a tested rollback to the standard interface.

The first visual milestone is Home, dock and Control Center working on the handset. Appearance work does not establish hardware support or iOS application compatibility.

## Milestones

| Milestone | Status |
| --- | --- |
| Normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October. |
| Original Ubuntu initramfs and intended SYSTEM mount | Confirmed by BOOT 3/4. |
| Handoff to systemd and Android container | Confirmed by BOOT 5/6. |
| Working graphical boot and touch | Confirmed by the user after correction 1 on 15 October. |
| Wi-Fi interface issue | Reproduced duplicated lists; a runtime unmanaged-`wlan0` test showed one list and retained Internet on `wlan1`; persistence/reconnection pending. |
| Further hardware | Speaker/PulseAudio, sensors and LTE registration partially validated; microphones, calls, SMS, GPS fix, camera, Bluetooth and stability remain open. |
| Repeatable installation, updates and recovery for others | In development. |
| iOS-style Lomiri interface | Planned after base-port stabilization; implementation not started. |

## Publication

The confirmed graphical boot meets the user's agreed publication condition. The repository is now public, with GitHub visibility verified on 15 October 2026. Public documentation must retain the user-report evidence level, exact prior image pins and explicit hardware-test limits.
