# Lomiri RC7/uOS27 v015: handset UI observations — 24 October 2026

**Device:** Samsung Galaxy S10+ SM-G975F/DS (`beyond2lte`), Exynos 9820.  
**Base system:** Ubuntu Touch 24.04 / Halium 12, development BOOT 6 baseline.  
**Experiment:** RC7/uOS27 v015 interface prototype.  
**Evidence level:** direct visual and interactive observations reported by the handset tester; no complete image/build promotion or independently archived reproduction log accompanies these results.

## Observed behavior

| Area | Result | Interpretation |
| --- | --- | --- |
| Bluetooth control | The tester confirmed that pressing the prototype toggle successfully enabled and disabled Bluetooth. | Working control in this experiment; does not prove all Bluetooth profiles, power-state persistence or integration into an alpha release. |
| Brightness slider | The slider continued to initialize at zero. | The control did not faithfully reflect the existing brightness state; brightness-range accuracy and actual panel response were not established by this observation alone. |
| Home interface | The standard lateral Lomiri Home/application navigation remained present. | The intended Home replacement was not achieved. |
| Control Center | The prototype occupied only the upper part of the display. | The proposed full-size visual layout was incomplete. |
| Visual acceptance | The tester rejected the current styling as unsatisfactory. | This UI is an unfinished prototype, not a production-ready redesign. |

## Scope and limitations

The tester referred to the RC7/uOS27 v015 run as stable in the limited sense that the test could be carried out; this was **not** a formal soak test of the whole system. An earlier RC6.1 rollback was separately confirmed, but does not certify rollback behavior for every v015 installation state. No claim is made that this prototype is contained in the published `v0.1.0-alpha.1` firmware.

These observations must be kept separate from the verified underlying audio/Wi-Fi/boot hardware baseline and from the broader unfinished iOS-inspired Lomiri roadmap. **Development was suspended on 24 October 2026**, with no further UI acceptance tests scheduled.
