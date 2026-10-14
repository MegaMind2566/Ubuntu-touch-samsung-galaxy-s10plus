# Windows package launchers

These files are inputs to the packaging scripts. The scripts place them at the root of an extracted Windows ZIP together with pinned ADB/Python dependencies, configuration and the required image files. Their relative paths assume that prepared package layout.

## Current handset investigation

| Launcher | Effect |
| --- | --- |
| `LEGGI-TEST-AVVIO.cmd` | Reads the diagnostic logs, pstore/last-kmsg, recovery metadata and BOOT identity; produces `ubuntu-boot-diagnostic-log-report.zip`. |
| `INSTALLA-TEST-AVVIO.cmd` | Controlled BOOT-only diagnostic installation, requiring verified BOOT 2 and recovery/preflight guards. Already completed on the test handset. |
| `RIPRISTINA-BOOT-2.cmd` | Restores verified BOOT 2 from the diagnostic state. BOOT 2 is an experimental image, not a confirmed working Ubuntu boot. |

The next required step is the read-only collector, not a repeated installation.

## Maintained support

Recovery checks/preparation, the TWRP installation route, stock firmware/DTB inspection, first-boot/USB collectors and Android inventory launchers remain available for their documented states. `AVVIA-CONTROLLO.cmd` is now stored here with the other launcher inputs; its generated package name is unchanged.

Old standalone BOOT 1/2 corrections, the superseded Odin SYSTEM/BOOT launcher and the one-time data-format add-on are under [archive](../../archive/README.md). They are not current entry points for the test handset.
