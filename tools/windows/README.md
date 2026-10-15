# Windows package launchers

These files are inputs to the packaging scripts. The scripts place them at the root of an extracted Windows ZIP together with pinned ADB/Python dependencies, configuration and the required image files. Their relative paths assume that prepared package layout.

## Current handset investigation

| Launcher | Effect |
| --- | --- |
| `INSTALLA-AVVIO-UBUNTU-6.cmd` | Installs BOOT 6 USB and RAM-profile corrections only from exact physical BOOT 5; writes only BOOT. |
| `LEGGI-AVVIO-UBUNTU-6.cmd` | Reads stages, trace, post-root PID 1/journal/Android state and retained logs; produces `ubuntu-boot-6-log-report.zip`. |
| `APPLICA-CORREZIONE-GRAFICA-1.cmd`, `LEGGI-CORREZIONE-GRAFICA-1.cmd`, `ANNULLA-CORREZIONE-GRAFICA-1.cmd` | Apply the persistent hwbinder/ion access correction on exact BOOT 6, read its result/session logs, or undo only its verified configuration. Keep it installed when testing the GUI. |
| `PREPARA-TEST-GRAFICA-1.cmd`, `LEGGI-TEST-GRAFICA-1.cmd`, `RIMUOVI-TEST-GRAFICA-1.cmd` | Prepare one bounded runtime inspection on BOOT 6 using userdata, read its logs after one boot, then remove its unit/assets. |
| `LEGGI-GRAFICA-UBUNTU-6.cmd` | Collector version 3 reads fixed graphics/session log tails and a USC prefix with TWRP-compatible metadata and separate CRLF transfer limits after pinning RECOVERY, BOOT 6 and userdata; produces `ubuntu-graphics-6-report.zip`. |
| `RIPRISTINA-AVVIO-UBUNTU-4.cmd` | Restores exact physical BOOT 4 from BOOT 6. |
| `LEGGI-TEST-AVVIO.cmd` | Reads the diagnostic logs, pstore/last-kmsg, recovery metadata and BOOT identity; produces `ubuntu-boot-diagnostic-log-report.zip`. |
| `INSTALLA-TEST-AVVIO-2.cmd` | Installs the built-in-initramfs diagnostic from the exact verified diagnostic 1 BOOT; targets only BOOT. |
| `LEGGI-TEST-AVVIO-2.cmd` | Reads test 2 logs and BOOT identity; produces `ubuntu-boot-diagnostic-2-log-report.zip`. |
| `RIPRISTINA-TEST-AVVIO-1.cmd` | Restores the exact diagnostic 1 BOOT from diagnostic 2 through the same guarded path. |
| `INSTALLA-TEST-AVVIO.cmd` | Controlled BOOT-only diagnostic installation, requiring verified BOOT 2 and recovery/preflight guards. Already completed on the test handset. |
| `RIPRISTINA-BOOT-2.cmd` | Restores verified BOOT 2 from the diagnostic state. BOOT 2 is an experimental image, not a confirmed working Ubuntu boot. |

BOOT 5 confirms systemd and Android/HWC execution but reboots on a USB configfs NULL dereference. BOOT 6 corrects that driver and applies the missing profiles in RAM. Its installer distinguishes the current BOOT 5 apply baseline from the BOOT 4 rollback image. Completed BOOT 3/4/5 standalone inputs are archived with provenance; do not repeat their completed installations.

BOOT 6 is now installed with matching later readback. The completed runtime comparison identifies hwbinder permissions as the mapper blocker and ion as another restricted device used by root. Apply the targeted graphics correction and retain BOOT 6. The old probe remains available for comparison and removal of its already installed diagnostic; it need not be prepared again.

## Maintained support

Recovery checks/preparation, the TWRP installation route, stock firmware/DTB inspection, first-boot/USB collectors and Android inventory launchers remain available for their documented states. `AVVIA-CONTROLLO.cmd` is now stored here with the other launcher inputs; its generated package name is unchanged.

Old standalone BOOT 1/2 corrections, the superseded Odin SYSTEM/BOOT launcher and the one-time data-format add-on are under [archive](../../archive/README.md). They are not current entry points for the test handset.
