# Project status

Updated: **19 October 2026**. Target: **Samsung Galaxy S10+ SM-G975F/DS, Exynos 9820, `beyond2lte`**.

## Active direction

Development has returned to Ubuntu Touch at the user's request. The separate [Sailfish project](https://github.com/MegaMind2566/SailfishOs-S10-Beyond2lte) is paused because a suitable complete-build host is unavailable. Sailfish was never installed on the handset; the working Ubuntu baseline is retained. This direction change adds no new hardware result to the 15 October observations below.

## Current result

**Ubuntu Touch 24.04 now reaches a working graphical interface on the test handset. The user confirms that touch and basic Wi-Fi work.** At 23:23:02 Europe/Rome (+02:00) on 15 October, the user reported “ora si è avviato”; at 23:23:55 they confirmed “touch e wifi funzionano”. These are message times, not measured handset boot times. This result follows the targeted graphics permission correction on the existing BOOT 6 installation.

The [first graphical boot record](evidence/ubuntu-first-graphical-boot-2026-10-15.json) separates this user-confirmed result from earlier machine-readable evidence. The exact setup/home screen has not been specified. No new photo, correction runtime report or image readback has been received after this success; the working configuration is associated with the previously verified baseline through the session history.

The latest independently read BOOT remains **version 6**, 57,344,000 bytes, SHA-256 `2671343e619d99ba8e1809aba73209afb67bdc50e982451f09662765aa6cb4ad`. The correction adds userdata configuration for **0666 access on hwbinder and ion**, with identity checks before LightDM; it does not rebuild or rewrite BOOT, SYSTEM or VENDOR. Keep it installed with this working baseline. The [BOOT 6 handset record](evidence/ubuntu-boot-6-handset-2026-10-15.json) preserves the earlier write/readback and subsequent success report.

The user's publication criterion has been met. The repository is public; visibility was verified through GitHub on 15 October 2026. This first working boot does not establish daily-use reliability or support for untested hardware.

## Verified progress

| Area | Evidence | Status |
| --- | --- | --- |
| Graphical boot | User confirmation after graphics correction 1 | Working interface reported; exact setup/home screen unspecified. |
| Touch | User follow-up | Basic operation confirmed; detailed input testing pending. |
| Wi-Fi | User follow-up | Basic operation confirmed; throughput, reconnect and suspend behaviour untested. |
| BOOT 6 identity | Exact installation/readback and matching later collector hash | 57,344,000 bytes; pinned hash above. No new readback after the successful boot. |
| Ubuntu userspace and Android container | Earlier BOOT 6 runtime logs | systemd alive through 120.10 s, Android boot complete and HWC 2.2 running. |
| Graphics permission cause | Controlled root/phablet/lightdm handset probe | Root initializes Mapper 2.0; nonroot access to root:root 0600 hwbinder fails with EACCES. Ion was also 0600. |
| Firmware and SYSTEM baseline | Device inventory and prior physical image-prefix verification | SM-G975F, Exynos 9820, stock Android/vendor 12, G975FXXSGHWC1; Ubuntu Touch 24.04-2.x / Halium 12. |
| Recovery and partition layout | TWRP, measured PIT and recovery checks | Prepared TWRP opens with root ADB; image targets and bounds are known. |
| Storage | Earlier normal/recovery read-only inspections | SYSTEM/Android/VENDOR readable; no erased Vendor or filesystem corruption demonstrated. |

Charging, suspend, Bluetooth, modem/calls/SMS, audio, camera and sensors remain untested. The diagnostic USB configuration result does not establish normal Ubuntu USB feature support.

See the [evidence index](evidence/README.md) for the original reports, image identities and validation limits.

## Resolved boot blockers and historical findings

Earlier attempts stayed at the Samsung logo. Source patches corrected the Samsung SAR ramdisk offset and late init selection; BOOT 4 reached the original initramfs handoff. BOOT 5 then demonstrated systemd/Android execution and a repeatable USB configfs NULL dereference. BOOT 6 contains the compiled NULL guard and the RAM profile/Android prestart integration.

Before the final permission correction, BOOT 6 already started the root compositor and spinner, but the unprivileged Lomiri session aborted for a missing mapper. The [runtime graphics probe](evidence/ubuntu-graphics-runtime-probe-2026-10-15.json) established the hwbinder EACCES path and root/nonroot difference. The intended adaptation udev rules had been skipped because their overlay destination was absent; the generic installed rule covered binder but not hwbinder/ion. [Correction 1](evidence/ubuntu-graphics-permission-fix-2026-10-15.json) restores only those two access modes through persistent userdata rules and a bounded pre-LightDM check. vndbinder, binder and Mali modes are unchanged.

The retained BOOT 6 panic belongs to a historical Power/Volume Down reset attempt: Samsung's six-second hard-reset hook deliberately calls `BUG()` before reset. Run 1 remained alive through the two-minute observer window; a panel power-down did not establish whole-device power loss. These findings did not justify another kernel rebuild.

Kernel symbol recovery, stock DTB/DTBO composition, source fixtures and ARM64 emulated tests are offline evidence, distinct from handset execution. Earlier dated build reports retain their original pre-test conclusions; the latest graphical result is recorded separately.

## Next work

Retain the working BOOT 6 and permission correction. Record the visible setup/home screen and collect the correction's result/session logs when available, without treating another reflash or Format Data as a prerequisite. The post-correction service/node checks and fresh image identities remain to be corroborated by that report.

Then validate Wi-Fi reconnect/suspend, charging and power management, followed by the remaining hardware functions. Track each result independently. Repair the adaptation's missing overlay destination in the reproducible SYSTEM assembly before presenting the userdata correction as a general installation method; the working handset does not need an immediate rebuild for that development task.

## Milestones

| Milestone | Status |
| --- | --- |
| Normal kernel and diagnostic PID 1 execution | Confirmed by diagnostic 2 on 15 October. |
| Original Ubuntu initramfs and intended SYSTEM mount | Confirmed by BOOT 3/4. |
| Handoff to systemd and Android container | Confirmed by BOOT 5/6. |
| Working graphical boot and touch | Confirmed by the user after correction 1 on 15 October. |
| Basic Wi-Fi operation | Confirmed by the user; extended testing pending. |
| Remaining hardware and long-term reliability | Untested. |
| Repeatable installation, updates and recovery for others | In development. |

## Publication

The confirmed graphical boot meets the user's agreed publication condition. The repository is now public, with GitHub visibility verified on 15 October 2026. Public documentation must retain the user-report evidence level, exact prior image pins and explicit hardware-test limits.
