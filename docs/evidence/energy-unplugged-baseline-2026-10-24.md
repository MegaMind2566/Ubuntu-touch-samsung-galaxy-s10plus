# Unplugged energy baseline — 24 October 2026

**Device:** Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`), Ubuntu Touch 24.04 / Halium 12 on the existing BOOT 6 baseline.  
**Test:** `ut-s10-energia-diagnosi-v2.py --inventario`; user explicitly confirmed the charger was disconnected.  
**Handset report time:** `2026-10-24T11:57:11+02:00`.  
**Read-only collector:** `2026-10-24.power-inventory-v2`, elapsed 0.59 s, `avvisi={}`, uptime 526.6 s.

## Observed on the handset

| Kernel/UPower reading | Value |
| --- | --- |
| `battery/capacity` | `56` (%) |
| `battery/status` | `Discharging` |
| `battery/health` | `Good` (driver report; not independently measured battery health) |
| `battery/voltage_now` | `3712000` (normally µV; 3.712 V) |
| `battery/temp` | `247` (Samsung tenths of °C; 24.7 °C, matches thermal_zone6 `24700` m°C) |
| `battery/charge_full`, `charge_full_design` | `4000000`, `4000000` (nominal 4000 mAh if standard µAh units) |
| `battery/charge_now` | `0` **inconsistent with 56%**; not a reliable remaining-charge value |
| `battery/current_now`, `current_avg`, `power_now` | `-697`, `-812`, `697` (raw integers; vendor units unverified, **not** used to calculate current or watts) |
| `ac/online`, `usb/online`, `wireless/online` | `0`, `0`, `0` (consistent with unplugged state) |
| `battery/online` | `1` (battery power supply status, **not** evidence of charger attachment) |
| UPower percentage, energy-full, reported energy-rate | `56%`, `14.848 Wh`, `0 W` (power-rate value unavailable/unreliable; not zero actual device consumption) |
| `mem_sleep` | `s2idle [deep]` (`deep` selected, actual suspend **not** measured) |
| `repowerd.service`, `upower.service` | `active`, `active` |
| `powerd.service` | `not-found` (Ubuntu Touch can use repowerd; this alone is not a failure) |
| Backlight `brightness`/`max_brightness`/`actual_brightness` | `48600`/`48600`/`800` (do not assume equal scaling or measured panel luminance) |

## Interpretation and next action

- The battery is detected, reporting discharge, remaining percentage, voltage and thermal data while unplugged. No errors were reported by the bounded v2 inventory.
- This **does not verify charging current, actual battery condition/capacity, endurance, automatic system suspend, wake or reboot persistence**. Some exposed values are not trustworthy for rate/energy computations without checking Samsung driver units.
- **Next physical experiment:** connect a known-good USB-C charger and cable to wall power; wait ~1 minute and take a second v2 inventory; keep connected ~10–15 min and take a third. Compare `battery/status`, `battery/capacity`, `usb/online`/`ac/online`, `voltage_now` and temperatures. Do not claim charging from `battery/online=1` alone. Assess screen-off/suspend separately after establishing charger behaviour.
- No root, sysfs writes, forced `mem` suspend, service restarts, or firmware changes.
