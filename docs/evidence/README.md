# Evidence index

Reports retain their original names and contents so image identities and earlier observations remain traceable. The authoritative interpretation of the latest state is [Project status](../status.md).

## Current milestone and supporting experiments

| Report | Finding |
| --- | --- |
| [First working graphical boot](ubuntu-first-graphical-boot-2026-10-15.json) | On 15 October, the user reports boot at 23:23:02 Europe/Rome and confirms touch/basic Wi-Fi at 23:23:55 after correction 1. Exact setup/home screen unspecified; no new photo or post-correction readback/report. |
| [Ubuntu BOOT 6 handset result](ubuntu-boot-6-handset-2026-10-15.json) | Prior exact installation/readback and userspace/Android/HWC evidence, historical mapper diagnosis, and the later user-confirmed graphical result on that baseline. |
| [BOOT 6 graphics permission correction](ubuntu-graphics-permission-fix-2026-10-15.json) | Targeted hwbinder/ion access modes and pre-LightDM checks; user now confirms graphical boot, touch and basic Wi-Fi. Machine-readable post-correction results remain pending. |
| [BOOT 6 runtime graphics probe](ubuntu-graphics-runtime-probe-2026-10-15.json) | Historical pre-correction cause: all 11 logs recovered; root loads Mapper 2.0, while phablet/lightdm receive hwbinder EACCES (0600) and abort. Ion is also restricted. |
| [BOOT 6 graphics collector](ubuntu-graphics-collector-2026-10-15.json) | Version 2 returns four log files and confirms the greeter mapper failure; USC is discarded after CRLF expansion. Version 3 separates remote and transport limits, adds a bounded USC prefix and passes 24 tests. |
| [Ubuntu BOOT 6 build/package](ubuntu-boot-6-build-2026-10-15.json) | Compiled USB NULL guard and RAM profile integration; 33 ARM64 profile and 25 portable PowerShell cases passed. Exact BOOT 5 apply baseline / BOOT 4 rollback. Historical build validation; later physical and graphical results are recorded above. |
| [Ubuntu BOOT 5 handset execution](ubuntu-boot-5-handset-2026-10-15.json) | Exact install/readback; two systemd/Android/HWC starts; repeated USB configfs NULL panic. Graphical boot unconfirmed; RAM profile targets missing. |
| [Ubuntu BOOT 5 build/package](ubuntu-boot-5-build-2026-10-15.json) | Local compiled-image/ARM64 and 24 portable PowerShell cases passed; exact BOOT 4 rollback. New native Windows CI could not start. Subsequent handset execution and USB panic are recorded separately above. |
| [Userspace compatibility audit](userspace-compatibility-2026-10-15.json) | Exact SYSTEM/Android identities; ARM64 init/systemd dependency checks; cgroup v1-controller mismatch and HWC readiness gate identified. No handset userspace boot claim. |
| [Ubuntu BOOT 4 handset execution](ubuntu-boot-4-handset-2026-10-15.json) | Exact write/readback and successful checkpoint; original init completes udev cleanup and saves userspace-handoff at 3.509624 s. Trace redirection and early observer stop limit evidence; systemd/GUI unconfirmed. |
| [Ubuntu BOOT 4 build/package](ubuntu-boot-4-build-2026-10-15.json) | Immutable delivered image/package pins; Linux/ARM64 and 24 native Windows cases passed. Subsequent hardware findings are recorded separately above. |
| [Ubuntu BOOT 3 handset execution](ubuntu-boot-3-handset-2026-10-15.json) | Exact write/readback and two original Ubuntu init attempts; SYSTEM/Android/Data mounted. Last saved stage root-mounted; userspace/GUI unconfirmed. |
| [Ubuntu BOOT 3 build/package](ubuntu-boot-3-build-2026-10-15.json) | Complete original Ubuntu initramfs through the observed route; Linux/ARM64 and native Windows checks passed. Handset execution recorded separately above. |
| [Diagnostic 2 handset execution](boot-diagnostic-2-handset-2026-10-15.json) | Exact BOOT, normal kernel/PID 1, readable storage and USB configuration confirmed. Ubuntu init not executed. |
| [Diagnostic 2 build and package](early-boot-diagnostic-build-2026-10-15.json) | Built-in initramfs verified in the real kernel; Linux and native Windows checks passed; its subsequent handset execution is recorded above. |
| [Diagnostic 1 collected report](boot-diagnostic-1-log-report-2026-10-15.json) | Exact BOOT matches and Data is mounted, but no saved diagnostic logs; S-Boot clears buffers while entering recovery. |
| [Diagnostic installation](boot-diagnostic-1-handset-2026-10-14.json) | BOOT-only write and exact readback succeeded. |
| [Latest recovery logs](boot-diagnostic-1-recovery-logs-2026-10-14.json) | Logs describe active TWRP; diagnostic normal-boot execution remains unconfirmed. |
| [Offline tool results](offline-tools-2026-10-14.json) | Kernel symbol recovery, compiled init-handoff check and stock device-tree inspection. |
| [Diagnostic design](boot-diagnostic-design-2026-10-13.json) | Temporary PID 1, limited writes and observation points. |
| [Diagnostic build](boot-diagnostic-build-2026-10-13.json) | Immutable image identities and Linux/Windows validation. |
| [BOOT 2 handset result](boot-update-2-handset-2026-10-13.json) and [screen observation](boot-update-2-logo-2026-10-13.json) | Write/readback succeeded; normal boot still stayed at the logo. |
| [SAR init handoff](boot-init-handoff-2026-10-13.json) | Source defect and controlled regression fixtures. |

## Baseline and earlier experiments

| Report | Purpose |
| --- | --- |
| [Device inventory](device-check-2026-10-12.json) | Original Android/vendor/hardware baseline. |
| [Actual PIT](download-mode-pit-2026-10-13.json) | Measured Samsung partition table. |
| [Stock image layout](stock-layout-report-2026-10-13.json) and [stock DTB](stock-dtb-report-2026-10-13.json) | Firmware layout, AVB metadata and tree identities. |
| [Recovery checks](recovery-check-2026-10-13.json) | Modified recovery/VBMETA hashes, root ADB and partition measurements. |
| [First-install readback](first-boot-readback-2026-10-13.json) | Physical BOOT/SYSTEM identity after installation. |
| [Odin PIT failure](ubuntu-install-pit-failure-2026-10-13.json) | Earlier transport failure before payload transfer; superseded by TWRP installation. |

Other dated JSON files preserve intermediate build, transport and hardware observations. Filenames identify the experiment; a successful write is not recorded as a successful Ubuntu boot.

## Release packaging

[First alpha package](firmware-alpha-1-packaging-2026-10-15.json) records the firmware/runtime pins, ZIP integrity and offline test boundaries. It is a packaging record; the [draft upload record](firmware-alpha-1-draft-2026-10-15.json) records assets already uploaded and the remaining publication gate.

## Repository maintenance

[Post-boot cleanup](repository-cleanup-2026-10-15.json) records the preserved archive moves, current dependency checks and byte-identical package validation.
