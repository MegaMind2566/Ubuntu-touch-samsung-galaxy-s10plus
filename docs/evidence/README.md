# Evidence index

Reports retain their original names and contents so image identities and earlier observations remain traceable. The authoritative interpretation of the latest state is [Project status](../status.md).

## Current boot investigation

| Report | Finding |
| --- | --- |
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
