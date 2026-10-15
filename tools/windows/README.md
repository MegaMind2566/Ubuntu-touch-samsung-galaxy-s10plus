# Windows package launchers

These files are inputs to the packaging scripts. The scripts place them at the root of an extracted Windows ZIP together with pinned ADB/Python dependencies, configuration and the required image files. Their relative paths assume that prepared package layout.

## Current handset investigation

| Launcher | Effect |
| --- | --- |
| `INSTALLA-AVVIO-UBUNTU-4.cmd` | Installs the traced original Ubuntu initramfs only from exact BOOT 3; writes only BOOT. |
| `LEGGI-AVVIO-UBUNTU-4.cmd` | Reads stages, shell trace, passive wait samples and retained logs; produces `ubuntu-boot-4-log-report.zip`. |
| `RIPRISTINA-AVVIO-UBUNTU-3.cmd` | Restores exact verified Ubuntu BOOT 3 from BOOT 4. |
| `LEGGI-TEST-AVVIO.cmd` | Reads the diagnostic logs, pstore/last-kmsg, recovery metadata and BOOT identity; produces `ubuntu-boot-diagnostic-log-report.zip`. |
| `INSTALLA-TEST-AVVIO-2.cmd` | Installs the built-in-initramfs diagnostic from the exact verified diagnostic 1 BOOT; targets only BOOT. |
| `LEGGI-TEST-AVVIO-2.cmd` | Reads test 2 logs and BOOT identity; produces `ubuntu-boot-diagnostic-2-log-report.zip`. |
| `RIPRISTINA-TEST-AVVIO-1.cmd` | Restores the exact diagnostic 1 BOOT from diagnostic 2 through the same guarded path. |
| `INSTALLA-TEST-AVVIO.cmd` | Controlled BOOT-only diagnostic installation, requiring verified BOOT 2 and recovery/preflight guards. Already completed on the test handset. |
| `RIPRISTINA-BOOT-2.cmd` | Restores verified BOOT 2 from the diagnostic state. BOOT 2 is an experimental image, not a confirmed working Ubuntu boot. |

Diagnostic 2 and the original Ubuntu init in BOOT 3 have executed. BOOT 4 passed Linux/ARM64 checks and 24 native Windows cases and is ready for one handset attempt. Completed BOOT 3 launchers are archived with their provenance. Earlier launchers remain immutable baseline/rollback inputs; they are not instructions to repeat completed installations.

## Maintained support

Recovery checks/preparation, the TWRP installation route, stock firmware/DTB inspection, first-boot/USB collectors and Android inventory launchers remain available for their documented states. `AVVIA-CONTROLLO.cmd` is now stored here with the other launcher inputs; its generated package name is unchanged.

Old standalone BOOT 1/2 corrections, the superseded Odin SYSTEM/BOOT launcher and the one-time data-format add-on are under [archive](../../archive/README.md). They are not current entry points for the test handset.
