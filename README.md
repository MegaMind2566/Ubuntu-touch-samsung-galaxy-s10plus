# Ubuntu Touch for Samsung Galaxy S10+

I am porting **Ubuntu Touch 24.04 / Halium 12** to the **Samsung Galaxy S10+ Exynos (`beyond2lte`)**. My goal is to make it boot reliably, support the phone's hardware and provide a repeatable installation on the Android 12 firmware baseline.

**Ubuntu Touch now boots on my S10+, with working touch, basic Wi-Fi and speaker playback.** I reached the first graphical boot on **15 October 2026**, using BOOT 6 with graphics permission correction 1. I am now testing stability and the remaining hardware.

This is an early development port. Daily-use reliability and a supported update channel have not been established.

## Hardware support

**Status from physical tests through 23 October 2026.** A detected driver or a running daemon is not equivalent to a verified peripheral. The [project status](docs/status.md) tracks observations and limitations.

| Function | Status |
| --- | --- |
| Ubuntu Touch graphical session and touchscreen | Working in basic handset tests |
| Wi-Fi (2.4/5 GHz) | Internet works; duplicated network lists/icons traced to two managed interfaces. Excluding idle `wlan0` leaves one list and `wlan1` connected. Persistent single-list behavior confirmed by the tester after reboot; long-term connection reliability and Wi-Fi Direct still pending |
| Display, autorotation and inertial sensors | Working in basic tests; transient colored lines observed when browser resizes after on-screen keyboard dismissal |
| Ambient light, barometer and magnetometer | Fresh measurements observed; automatic brightness and compass accuracy still pending |
| Speaker and PulseAudio | Physical playback works with `sink.primary-out` and avoids crackling; service and stable sink selection verified after reboot |
| USB MTP | Access from another Android handset confirmed; other hosts, two-way transfers and USB modes not fully validated |
| Cellular modem and SIM | Slot-2 SIM registered on LTE; calls, SMS and mobile data not yet verified |
| GNSS | Service responds, but no position fix within a 120-second test |
| Proximity sensor | Session unavailable / unregistered in SensorFW |
| Built-in microphone | Functional ~5 s recording and clear replay confirmed by tester; 0% clipping reported; no audio stored |
| Wired 3.5 mm audio | **TRS headphones play normally. TRRS headset playback works in a physical test when legacy audio routing is enabled temporarily and the headset port is selected manually**. Automatic TRRS switching and cable microphone not yet working/verified; experimental configuration was reverted after test |
| Bluetooth headset | Playback works in user test; streaming anomalies remain. Mic route and call profile not independently verified |
| Secondary microphones, earpiece/call audio, cameras and NFC | Functional tests still pending |
| Charging, battery endurance, suspend/resume, fingerprint and extra sensors | Functional tests still pending |

The Wi-Fi, audio and USB runtime corrections were tested on the working handset; **integration into a reproducible image and universal installation remains a separate task**. No raw private device diagnostics or voice recordings are published in this repository.

## Tested baseline

| Component | Configuration |
| --- | --- |
| Device | Samsung Galaxy S10+ SM-G975F/DS |
| Codename / SoC | `beyond2lte` / Exynos 9820 |
| Samsung firmware | G975FXXSGHWC1, Android 12 / One UI 4.1, ITV/OXM |
| Ubuntu userspace | Ubuntu Touch 24.04-2.x, arm64 |
| Android adaptation | Halium 12 |
| Boot configuration | BOOT 6 with graphics permission correction 1 on userdata |
| Storage | Measured A-only Samsung partition layout |

I have not tested Snapdragon variants or other Galaxy S10 models. Source revisions are pinned in [upstream.lock.json](config/upstream.lock.json); measured image identities are recorded in the [evidence index](docs/evidence/README.md).

The current boot configuration includes Samsung init-handoff and USB fixes, device profiles, and a targeted graphics permission correction. The latter supplies access to `hwbinder` and `ion` before the display manager starts. The [correction record](docs/evidence/ubuntu-graphics-permission-fix-2026-10-15.json) links the diagnosed access failure, implementation and validation.

## First experimental release

I have published [**v0.1.0-alpha.1**](https://github.com/MegaMind2566/Ubuntu-touch-samsung-galaxy-s10plus/releases/tag/v0.1.0-alpha.1), based on the configuration that reached the first graphical boot. The release includes the SYSTEM image, the Windows boot/tools archive, checksums and installation notes. My working handset remains on BOOT 6 with graphics permission correction 1.

## Installation and builds

I currently use versioned development packages for specific image states. I am still validating a clean-install package and guide for other users.

Existing Windows packages contain state-specific checks and require their complete prepared folder. The launcher source files in this repository are packaging inputs. Consult the [current project status](docs/status.md) before choosing a package or changing an existing test installation.

For building the adaptation, assembling SYSTEM and reproducing the validation checks, start with [Development and validation](docs/development.md). Firmware, generated images and portable runtimes are kept outside the source tree; their identities are retained in the corresponding build records.

## Roadmap

1. TRRS headphone playback is physically verified with a temporary legacy-routing override. A guarded userspace auto-switch/legacy integration candidate now passes 40 offline tests but **has not yet been installed or validated on the handset**; next run its TRRS/TRS/speaker acceptance and rollback checks before marking automatic routing supported. Wired microphone and Bluetooth regressions remain separate checks.
2. Test real calls, SMS, mobile data and Wi-Fi reliability, including the persisted single-network-list workaround after reboot.
3. Validate charging, battery reporting, suspend/resume, thermals and the brief graphical artifacts during keyboard dismissal.
4. Complete cameras, GNSS fix, Bluetooth microphone/call profiles and other modes, NFC, fingerprint and other hardware tests.
5. Integrate confirmed fixes into a reproducible clean installation with recovery/update instructions, then pursue an iOS-style Lomiri interface; see [planned interface work](docs/status.md#planned-interface-work).

I track each hardware result separately and will update the support table as testing progresses.

## Documentation and contributions

| Resource | Contents |
| --- | --- |
| [Project status](docs/status.md) | Current handset results, limitations and next work |
| [Development guide](docs/development.md) | Source pins, builds, image assembly and validation |
| [Evidence index](docs/evidence/README.md) | Dated build records, readback identities and hardware observations |
| [Scripts](scripts/README.md) | Maintained build, inspection and packaging components |
| [Windows packages](tools/windows/README.md) | Development launcher entry points and required states |

Configuration lives in `config/`, adaptation patches in `patches/`, runtime support in `tools/`, and checks in `tests/`. Detailed experiment history is retained in `docs/` and the archive.

If you test the port or contribute a change, include your device model, firmware, observed behavior and relevant logs or image identities. Keep build/test results separate from execution on real hardware, and include a reproducible test when updating hardware support.

## Upstream and licensing

I build on the [UBports community Samsung Exynos 9820 port](https://gitlab.com/ubports/porting/community-ports/android10/samsung-galaxy-s10/samsung-exynos9820), its matching Halium kernel, the Halium generic adaptation build tools, Ubuntu Touch and TeamWin recovery.

Upstream components retain their respective copyright and license terms. See [THIRD_PARTY.md](THIRD_PARTY.md) for attribution, component licenses and source references. This independent development port carries no claim of official Samsung, TeamWin or UBports support.
