# Windows package entry points

These files are packaging inputs. Use the complete extracted package, including its pinned Python/ADB dependencies. The current test handset boots Ubuntu Touch with BOOT 6 and graphics permission correction 1; touch and basic Wi-Fi work.

## Working configuration and result collection

| Launcher | Purpose |
| --- | --- |
| `APPLICA-CORREZIONE-GRAFICA-1.cmd` | Store the persistent hwbinder/ion correction for the next BOOT 6 start. Keep it installed on the working handset. |
| `LEGGI-CORREZIONE-GRAFICA-1.cmd` | Read bounded correction and compositor/session logs from TWRP. |
| `ANNULLA-CORREZIONE-GRAFICA-1.cmd` | Undo only the correction's verified userdata configuration; preserve logs. Read them before any undo. |
| `LEGGI-GRAFICA-UBUNTU-6.cmd` | Read bounded retained graphics logs, including the compositor prefix. |
| `LEGGI-AVVIO-UBUNTU-6.cmd` | Read BOOT 6 checkpoints and retained systemd/Android observations. |

## Installation and recovery support

| Launcher | Prerequisite and effect |
| --- | --- |
| `INSTALLA-AVVIO-UBUNTU-6.cmd` | Exact BOOT 5 baseline; install BOOT 6 only. This is an upgrade tool for that development state. |
| `RIPRISTINA-AVVIO-UBUNTU-4.cmd` | Exact BOOT 6 baseline; restore the separate experimental BOOT 4 rollback image. |
| `PREPARA-RECOVERY.cmd`, `INSTALLA-RECOVERY-TEST.cmd`, `CONTROLLA-RECOVERY.cmd` | Prepare, validate or install the hash-pinned recovery in their documented package states. |
| `PREPARA-UBUNTU-TOUCH.cmd`, `INSTALLA-UBUNTU-TWRP.cmd` | Original SYSTEM/BOOT preparation and guarded TWRP installation. Read the package instructions and exact image requirements. |
| `SCARICA-FIRMWARE.cmd` | Retrieve the pinned stock firmware for the original recovery baseline. |
| `CONTROLLA-DOWNLOAD.cmd`, `ESTRAI-DTB.cmd` | Download-mode layout checks and stock device-tree extraction. |

## Optional diagnostics

`PREPARA-TEST-GRAFICA-1.cmd`, `LEGGI-TEST-GRAFICA-1.cmd` and `RIMUOVI-TEST-GRAFICA-1.cmd` retain the controlled mapper comparison and removal path for a previously installed probe. Preparing that probe again is not a prerequisite for the working correction. `CONTROLLA-USB-AVVIO.cmd` remains a read-only Windows USB observer. `AVVIA-CONTROLLO.cmd` collects the initial stock-Android inventory for a new test handset.

## Historical packages

Completed PID 1 diagnostics, the BOOT 4 userspace inspector, old first-boot add-ons and BOOT 1–5 standalone updates are in [archive](../../archive/README.md). They are no longer current entry points. Shared dependencies, current collectors and the working correction remain maintained.
