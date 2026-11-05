# Physical screen-off/wake trial - 5 November 2026

The user unplugged USB, used normal power-button screen-off, and left the phone untouched for the requested approximately two-minute rest, without active ADB/SSH traffic. The user then reported **normal wake with the screen and touch working before USB was reconnected**. No forced suspend API, `/sys/power/state` write or firmware change was used.

The bounded clock snapshots bracket **12:27:02 to 12:31:15 Europe/Rome**. Their whole interval includes active setup and recovery overhead; it is not a measurement of exactly how long the screen was off. The [before](suspend-before-2026-11-05.json) and [after](suspend-after-2026-11-05.json) records retain only clocks, kernel version, timestamps and session-scoped diagnostic nonce/HMAC identity, not the raw boot ID. The comparison confirms the same boot.

| Clock comparison | Result |
| --- | --- |
| BOOTTIME delta | 253.131824041 seconds |
| MONOTONIC delta | 253.131823945 seconds |
| Suspend-time estimate | 96 ns |
| Combined sampling uncertainty | 3,174 ns |
| Nonnegative suspend interval | 0 to 3,270 ns |
| Classification | `no-positive-suspend-time-resolved` |

The estimate is inside sampling uncertainty. **No positive kernel-accounted suspend time was resolved in this trial.** This does not establish deep sleep or acceptable standby consumption, and it does not identify why suspend was not resolved. Screen-off and successful physical screen/touch recovery are separate observations. See the [machine-readable comparison](suspend-comparison-2026-11-05.json) and [kernel clock semantics](https://www.kernel.org/doc/html/latest/core-api/timekeeping.html).

After USB reconnect, the host reported ADB **offline**. Authenticated Wi-Fi SSH was usable and supplied the after snapshot. An official transient USB mode sequence, `developer_mode` followed by `mtp_adb`, restored ADB without reboot. No saved-mode configuration or ADB authentication change was needed. This is an **open reconnect regression**; the earlier [saved-mode helper acceptance](usb-saved-mode-acceptance-2026-11-05.json) verified one normal cold boot and does not establish reconnect reliability.

## Later read-only backend diagnosis

The [bounded power-backend inventory](power-backend-2026-11-05.json), collected awake with USB connected at **12:45:18 Europe/Rome**, records the installed `repowerd` package suffix `gbp365751`. This maps to official source revision `36575160752bdd0a983bee1b53e041ccc4ceaa60`; it is source provenance, not a binary reproducibility check. Startup records explicitly report failed Libsuspend initialization and a transition to Logind. Separate unit inspection reported root execution without local overrides.

In that exact revision, the [factory](https://gitlab.com/ubports/development/core/repowerd/-/blob/36575160752bdd0a983bee1b53e041ccc4ceaa60/src/default_daemon_config.cpp#L359) tries Libsuspend before Logind, and Logind's [`allow_automatic_suspend` / `disallow_automatic_suspend`](https://gitlab.com/ubports/development/core/repowerd/-/blob/36575160752bdd0a983bee1b53e041ccc4ceaa60/src/adapters/logind_system_power_control.cpp#L121) methods are empty. This is a source-grounded explanation for the missing repowerd automatic-suspend mechanism in the selected fallback. It does not prove that every other suspend mechanism is absent, that a single patch resolves the handset, or that this explains the USB reconnect regression.

The live `/sys/power/autosleep` path is absent. `IKCONFIG` extracted from BOOT 6 in the verified local alpha.1 ZIP has `CONFIG_PM_AUTOSLEEP` unset while `CONFIG_SUSPEND=y` and `CONFIG_PM_WAKELOCKS=y`. The read-only suspend counters report **success 0, fail 0**. Together these support the backend gap without requesting suspend or writing a power-control attribute.

A HIDL `android.system.suspend@1.0::ISystemSuspend/default` service was listed; `/dev/hwbinder` was present with mode 0666 and libgbinder 1.1.52 was installed. However, `lshal` exited 72 with warnings about other services: this is a partial inventory, not a successful transaction or proof that Android's autosuspend loop is enabled. The empty repowerd request lists and logind inhibitor snapshot describe the later awake state, not the earlier disconnected rest. Delay inhibitors are not retrospective proof of a blocking cause.

The unchanged upstream [SystemSuspend HIDL backport candidate](../../tools/repowerd-suspend/README.md), commit `d87b74538c368cd7bebef64c5b81c5c377ae3f88`, applies to the exact installed-source revision. A later free GitHub ARM64 build produced matching packages and passed both upstream CTest suites; the installed loader resolved candidate libraries without starting the daemon. **The first artifact is held** following source review of wake-lock remote-object lifetime and Android autosuspend activation. It has not been installed or hardware-tested. [Build record](runtime-arm64-build-2026-11-05.md#first-repowerd-build-completed-deployment-held).

Next: complete and test the follow-up lifetime/activation candidate, then verify backend and Android suspend-controller prerequisites before a reversible trial. Keep BOOT 6 and proven audio/Wi-Fi/USB settings. The ADB reconnect regression remains separately open; no forced-suspend experiment is part of this diagnosis.
