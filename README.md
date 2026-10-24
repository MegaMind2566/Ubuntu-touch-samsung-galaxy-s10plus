# Ubuntu Touch for Samsung Galaxy S10+ (Exynos)

> **Project status: SUSPENDED — 24 October 2026**  
> **Maturity: experimental alpha; not suitable for daily use.** No active development, supported update channel or resumption date is currently planned.

This repository documents my effort to bring **Ubuntu Touch 24.04 / Halium 12** to the **Samsung Galaxy S10+ Exynos (`beyond2lte`)**, building on the earlier community port. The aim was to obtain a reliable graphical boot, restore the phone's hardware functions and eventually provide a reproducible installation on the final Samsung Android 12 firmware baseline.

I reached the **first confirmed graphical boot on 15 October 2026**, using **BOOT 6** with a separate graphics-permission correction. Touch input, Wi-Fi internet access and several other peripherals were subsequently tested on my own handset. The port remains incomplete: successful operation on this particular device does **not** imply a stable, generally installable ROM.

I have paused work as of **24 October 2026**. The source code, alpha release, experiments and evidence remain public so that the work can be inspected or continued. This is a suspension, not a claim of project completion. I am not promising new builds, bug fixes or installation support while it is suspended.

## Device and software baseline

| Component | Tested configuration |
| --- | --- |
| Device | Samsung Galaxy S10+ **SM-G975F/DS**, Exynos variant |
| Device codename / SoC | `beyond2lte` / Exynos 9820 |
| Original firmware | Samsung **G975FXXSGHWC1**, Android 12 / One UI 4.1, ITV/OXM |
| Ubuntu userspace | Ubuntu Touch **24.04-2.x**, arm64 |
| Android adaptation | **Halium 12** |
| Known working boot baseline | **BOOT 6** plus **graphics-permission correction 1** applied through userdata |
| Partition scheme | Measured Samsung A-only layout; not a generic A/B or dynamic-partition device |
| Latest included handset observations | **24 October 2026** |

This device-specific work has **not** been validated on Snapdragon S10+ models, the S10/S10e/5G or other firmware and bootloader revisions. Source pins, image identities and test provenance are available in [upstream.lock.json](config/upstream.lock.json), the [evidence index](docs/evidence/README.md) and [development notes](docs/development.md).

## Hardware support

The matrix below separates **physical, user-confirmed tests** from driver detection and unperformed tests. “Working” describes the tested function under the stated conditions, not every mode or long-term reliability. “Partial” means some behavior was demonstrated but significant limitations remain. “Blocked” means a specific software path failed; it does not establish defective hardware. “Not tested” must **not** be interpreted as “broken.”

| Component / function | Status | Verified result and limitations |
| --- | --- | --- |
| Graphical boot and Lomiri session | **Working (basic)** | Reaches the Ubuntu Touch graphical environment with BOOT 6 and the separate graphics fix. Repeated-boot and long-term stability are not certified. |
| Touchscreen | **Working** | Physical touch interaction confirmed in the graphical session. |
| AMOLED display | **Working (basic)** | Image output works. Brief colored-line artifacts occur when a browser surface resizes after the on-screen keyboard closes. Video decoding was not separately tested. |
| Rotation, accelerometer, gyroscope, orientation | **Working (basic)** | Live sensor values and screen autorotation observed; precision and all orientation cases not certified. |
| Wi-Fi 2.4/5 GHz | **Working (basic)** | Internet access confirmed through `wlan1`. Duplicate network lists caused by managed `wlan0`/`wlan1` were removed with a persistent runtime workaround, confirmed after reboot. Some connection failures occurred; extended stability, hotspot and Wi-Fi Direct remain untested. |
| Loudspeaker | **Working (basic)** | Physical playback confirmed through the corrected PulseAudio `sink.primary-out` path without crackling in the acceptance test. Audio routing remains sensitive to default-sink selection. |
| Built-in microphone | **Working (basic)** | Approximately 4.82 seconds of voice recorded and audibly replayed; the test reported no clipping. Other microphone paths are unverified. |
| 3.5 mm headphones (TRS) | **Working (basic)** | Wired headphone playback confirmed. |
| 3.5 mm headset output (TRRS) | **Partial** | Physical playback confirmed with legacy droid-audio routing. Experimental v4 routing switched to the headset on insertion and back to the speaker on removal, including a reboot check. Lomiri can still label the headset as “Speaker”; headset-microphone capture and long-term stability are unverified. |
| Bluetooth radio | **Partial** | Basic radio activation and deactivation were observed on the handset; complete profile support and long-term reliability remain unverified. |
| Bluetooth headset playback | **Partial** | Audio heard in a user test; streaming anomalies remain. A voice-input interaction did not prove that the Bluetooth microphone was the active source. HFP/HSP calls, BLE, pairing persistence and transfers remain unverified. |
| Cellular modem and SIM | **Partial** | oFono exposed two modem objects; a SIM in slot 2 registered on LTE. Calls, SMS, mobile data and actual dual-SIM operation have **not** been verified. |
| USB-C MTP | **Partial** | Storage access from another Android handset confirmed. Computer-host compatibility, bidirectional transfers, ADB during normal Ubuntu boot, tethering and other USB modes remain unverified. |
| Ambient light sensor | **Partial** | Changing sensor readings detected. Automatic brightness control is not established. |
| Brightness and backlight | **Partial** | Kernel backlight values are available; automatic brightness and user-facing control accuracy are not established. |
| Barometer and magnetometer | **Working (basic readings)** | Live pressure and magnetic samples obtained; compass accuracy and calibration remain unverified. |
| GPS / GNSS | **No fix demonstrated** | GNSS service responded but the 120-second test produced no location fix. Outdoor acquisition and navigation are not validated; this is not proof that the GNSS hardware is defective. |
| Proximity sensor | **Blocked in current stack** | SensorFW rejected the proximity session as unregistered. Physical near/far behavior could not be validated. |
| Battery reporting | **Partial** | An unplugged, read-only test reported 56%, `Discharging`, 3.712 V and 24.7 °C; the battery, UPower and `repowerd` were visible. Some vendor current/charge fields were inconsistent or had unknown units. |
| Wired and wireless charging | **Not tested** | Detection and actual charging progression over time were not physically established. |
| Screen-off, suspend/resume, endurance | **Not tested** | Available kernel sleep states and services do not prove successful sleep, wake or acceptable standby consumption. |
| Earpiece, call audio, secondary microphones | **Not tested** | Speaker and built-in recording tests do not establish telephony audio routing. |
| Cameras (rear/front), video recording, flash | **Not tested** | No conclusive capture or flash test on this Ubuntu Touch build. |
| NFC | **Not tested** | No successful transaction or reader test. |
| Fingerprint reader, Hall and heart-rate sensors | **Not tested** | Some interfaces were detected, but no successful physical use was demonstrated. |
| Vibration / haptics, USB-OTG and remaining peripherals | **Not tested** | No reliable end-to-end acceptance result recorded. |

The [detailed project status](docs/status.md) and [dated evidence](docs/evidence/README.md) record the difference between successful offline tests, actual handset behavior and unresolved issues. Runtime fixes for Wi-Fi, audio and USB were exercised on the development phone; **they have not all been incorporated into one cleanly reproducible, public installation image**. No private audio recordings or raw personal device diagnostics are published here.

## Available alpha release

I published [**v0.1.0-alpha.1**](https://github.com/MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus/releases/tag/v0.1.0-alpha.1) on **15 October 2026**, including the SYSTEM image, Windows boot/tools package, checksums, manifest and installation notes. This release represents an **early graphical-boot milestone**, not the final collection of subsequent on-device audio and Wi-Fi experiments.

**Do not treat this release as a stable daily-driver ROM or an automatic upgrade for another S10+.** It requires a compatible device/firmware state, careful image-identity checks and a reliable recovery path. I have not established a general clean-install procedure or supported OTA updates. Review the [alpha installation notes](docs/install-alpha.md) and [current status](docs/status.md) before touching partitions. I am not performing further installation validation while the project is suspended.

## Outstanding work if development resumes

1. Measure real charging progression, suspend/resume, standby consumption and repeated-boot reliability without disturbing the confirmed BOOT 6 baseline.
2. Verify phone calls, SMS, mobile data, dual-SIM behavior, earpiece and call-microphone routing.
3. Finish GNSS acquisition, proximity registration, cameras, NFC, fingerprint, Bluetooth profiles and remaining peripheral tests.
4. Address graphics artifacts, Wi-Fi reconnection, PulseAudio default-sink regressions and wired-headset microphone routing.
5. Integrate validated runtime corrections into a reproducible image with tested installation, update and rollback procedures.

**All items above are backlog, not active commitments or a delivery schedule.**

## Repository documentation

| Resource | Purpose |
| --- | --- |
| [Project status](docs/status.md) | Evidence-backed hardware state, regressions, experiments and suspended work |
| [Development guide](docs/development.md) | Pinned sources, BOOT/SYSTEM assembly and validation boundaries |
| [Evidence index](docs/evidence/README.md) | Dated build records, image readbacks and physical device findings |
| [Scripts](scripts/README.md) | Maintained source tooling and guarded diagnostics |
| [Windows tools](tools/windows/README.md) | State-specific development packages and launchers |

The code is organized under `config/`, `patches/`, `scripts/`, `tests/` and `tools/`; superseded experiments remain in `archive/`. Contributions or independent testing should identify the exact model, firmware, image revision, operation performed and observed result. A detected driver or successful simulated test is not sufficient to mark a feature supported.

## Credits and licensing

This independent work builds on the [UBports community Samsung Exynos 9820 port](https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820), Halium, Ubuntu Touch, the associated kernel and adaptation tooling, and TeamWin recovery. Upstream projects retain their respective copyrights and licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).

This is **not** an official Samsung, UBports or TeamWin release. The repository is preserved for technical reference in its **suspended** state.
