# Ubuntu Touch for Samsung Galaxy S10+

I am porting **Ubuntu Touch 24.04 / Halium 12** to the **Samsung Galaxy S10+ Exynos (`beyond2lte`)**. My goal is to make it boot reliably, support the phone's hardware and provide a repeatable installation on the Android 12 firmware baseline.

**Ubuntu Touch now boots on my S10+, with working touch and Wi-Fi.** I reached the first graphical boot on **15 October 2026**, using BOOT 6 with graphics permission correction 1. I am now testing stability and the remaining hardware.

This is an early development port. Daily-use reliability and a supported update channel have not been established.

## Hardware support

| Function | Status |
| --- | --- |
| Graphical Ubuntu Touch session | Booted on my test phone |
| Touchscreen | Basic operation tested |
| Wi-Fi | Basic operation tested |
| Repeated boots and long-running stability | Pending validation |
| Charging, battery reporting and suspend/resume | Pending validation |
| Modem, calls, SMS and mobile data | Not yet tested |
| Audio and microphone | Not yet tested |
| Cameras | Not yet tested |
| Bluetooth, GPS and sensors | Not yet tested |
| Normal Ubuntu USB features | Not yet tested |

These are basic checks on my **SM-G975F/DS**, not a complete compatibility test. The [first graphical boot record](docs/evidence/ubuntu-first-graphical-boot-2026-10-15.json) separates my observations from the earlier image readbacks and runtime logs. Those logs verify Ubuntu userspace, the Android container, HWC 2.2 and the Mali/OpenGL display path; extended touch and Wi-Fi testing is still pending.

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

I am preparing **v0.1.0-alpha.1** around the configuration that reached the first graphical boot. The final package contents and installation notes will be linked here once the release is published.

## Installation and builds

I currently use versioned development packages for specific image states. I am still validating a clean-install package and guide for other users.

Existing Windows packages contain state-specific checks and require their complete prepared folder. The launcher source files in this repository are packaging inputs. Consult the [current project status](docs/status.md) before choosing a package or changing an existing test installation.

For building the adaptation, assembling SYSTEM and reproducing the validation checks, start with [Development and validation](docs/development.md). Firmware, generated images and portable runtimes are kept outside the source tree; their identities are retained in the corresponding build records.

## Roadmap

1. Confirm repeat boots and sustained display, touch and Wi-Fi operation.
2. Validate charging, battery reporting, suspend/resume and thermals.
3. Test and bring up the remaining hardware functions listed above.
4. Integrate the working configuration into a repeatable clean installation, with recovery instructions and an update strategy.

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
