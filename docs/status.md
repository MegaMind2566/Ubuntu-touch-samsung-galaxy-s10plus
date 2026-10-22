# Project status

Updated: **23 October 2026**, following user-confirmed physical TRRS playback with a reversible PulseAudio legacy-routing trial, plus audio, Wi-Fi, USB, modem and sensor checks. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**, Ubuntu Touch 24.04 / Halium 12.

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
| PulseAudio and physical speaker | Audio-6 v2 restored the normal Ubuntu Touch PulseAudio service; clean playback through `sink.primary-out` confirmed. Normal module and speaker selection restored by the TRRS legacy experiment. | Call, headset microphone and complete post-trial listening regression still pending. |
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
| Wired 3.5 mm jack / audio routing | **23 October physical test:** TRS playback works in the original mode. TRRS headset (mic-equipped) plays an audible tone **in the wired earpieces** when a temporary, loaded-and-verified `use_legacy_stream_set_parameters=true` setting is active and `output-wired_headset` is selected manually. Prior nonlegacy selection played through the speaker. `Headset` event8 reports `EVIOCGSW=0x90` for inserted TRRS and `0x00` after removal. | The test successfully restored the original PA service/module/port. **Automatic TRRS routing is not fixed**, wired headset mic unverified, no persistent setting installed. `create_audio_patch()` ENOSYS logs and module's headset availability predicate point to two separate compatibility issues. See [dated evidence](evidence/audio-trrs-legacy-route-2026-10-23.md). |
| Fingerprint, Hall, heart-rate sensor | Respective kernel/daemon interfaces detected. | No successful physical operation demonstrated. |
| Battery and charging | Kernel exposes power/battery readings. | Verify actual charge progression, wireless charging, suspend and consumption. |
| Bluetooth headset | The tester reports working playback and a successful voice-input interaction while using a Bluetooth headset, but this did not independently identify the active recording source. The tester also reports unresolved Bluetooth streaming anomalies. | Bluetooth mic routing, call audio profile (HFP/HSP), BLE, file transfer, reconnect and streaming quality require separate verification. |
| Camera, NFC, SMS, mobile data and other hardware | No conclusive functional test yet. | Targeted tests only; avoid labelling these features broken without evidence. |

## Next work

**Wired TRRS audio milestone (23 October, on-device):** the original binary `pulseaudio-modules-droid-30` (ARM64, version `14.2.109-0ubports2~20261008093544.3~4ad1b20+ubports24.04.2`, SHA-256 `baf1a48df837278f3ed84fa046d4be81ddeb9be06ed65d0f256eea9f79bb7912`) successfully played a 0.8 s tone **in the physical headset** after a temporary `use_legacy_stream_set_parameters=true` override and manual `output-wired_headset` selection. The user confirmed headphone-only listening. The trial removed its override, returned to `output-speaker`, restarted PulseAudio with its original module arguments and verified no binary changes. Details: [audio TRRS legacy-route evidence](evidence/audio-trrs-legacy-route-2026-10-23.md).

**Implementation prepared, handset test pending (23 October 2026):** standalone `ut-s10-trrs-integrato.py` (experimental `2026-10-23.trrs-integrated-2`) retains the original ARM64 droid module, adds a strictly checked **user-level persistent, reversible** environment override for legacy `set_parameters()` routing, and uses a low-duty-cycle systemd user monitor of `/sys/class/extcon/extcon1/state` to manually choose `output-wired_headset` only for TRRS; unplugs restore speaker as needed. Its acceptance flow requires physical TRRS, TRS and speaker playback before the user explicitly approves persistence. Forty **offline simulation** tests passed, including install, partial failure, interrupted startup, monitor behavior and rollback; `systemd-analyze verify` succeeded. None of these tests establishes the persistent fix on the handset. Script artifact was supplied separately to the tester and is not yet part of a release image.

**Next experiment:** run the guarded handset acceptance for the prepared legacy-routing and TRRS auto-switch candidate while preserving audio6 v2 and the stable `sink.primary-out` baseline. The staged [`droid-extevdev` headset predicate patch](../patches/audio/0001-droid-extevdev-trrs-mic-only.patch) addresses **only** jack availability and has not been built or installed; legacy routing separately addresses physical playback. Do not deploy the predicate patch alone as a complete audio fix. Verify original speaker/TRS operation and examine wired headset mic, calls and Bluetooth regressions before marking a persistent fix stable. Avoid repeated successful tests and do not publish private diagnostic logs.


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
| Further hardware | Speaker, built-in mic and Bluetooth headset playback tested; sensors and LTE registration partly validated. Calls, SMS, GPS fix, camera, further Bluetooth modes and stability remain open. |
| Repeatable installation, updates and recovery for others | In development. |
| iOS-style Lomiri interface | Planned after base-port stabilization; implementation not started. |

## Publication

The confirmed graphical boot meets the user's agreed publication condition. The repository is now public, with GitHub visibility verified on 15 October 2026. Public documentation must retain the user-report evidence level, exact prior image pins and explicit hardware-test limits.
