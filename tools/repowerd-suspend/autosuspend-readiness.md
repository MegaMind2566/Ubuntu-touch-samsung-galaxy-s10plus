# Android autosuspend readiness prerequisite

The HIDL backport is **incomplete as a handset suspend candidate until Android autosuspend activation is established**. No enabling call, forced suspend or sysfs write was performed for this analysis.

## Pinned source findings

Reference implementation: AOSP `platform/system/hardware/interfaces`, `android12-release` commit `858d482871f3b757af1da04777a3bd9be9ea427a`:

- [`suspend/1.0/default/main.cpp`](https://android.googlesource.com/platform/system/hardware/interfaces/+/858d482871f3b757af1da04777a3bd9be9ea427a/suspend/1.0/default/main.cpp) opens the power-control files, registers `suspend_control`, `suspend_control_internal` and the HIDL service, then joins the threadpool. It does not call `enableAutosuspend()`.
- `SystemSuspend.cpp:179`: `enableAutosuspend()` sets `mAutosuspendEnabled` and starts `initAutosuspend()`. Merely acquiring/releasing HIDL wake locks does not call it.
- `SystemSuspend.cpp:239,268,297`: the autosuspend loop calls `updateSleepTime()` after an attempt; that function increments `suspendAttemptCount`.
- `SuspendControlService.cpp:214,307`: the read-only dump exposes attempt/failure/suspend-time/backoff counters. It does not expose `mAutosuspendEnabled`, nor a direct readiness boolean.
- `main.cpp` substitutes blocking socketpair file descriptors if opening either `/sys/power/wakeup_count` or `/sys/power/state` fails. A registered, responsive HAL can therefore deliberately never suspend the kernel.
- The stock rc file only starts the service as `system`, group `system wakelock`, capability `BLOCK_SUSPEND`; it contains no autosuspend-enable command.

The normal AOSP caller is [frameworks/base PowerManagerService JNI](https://android.googlesource.com/platform/frameworks/base/+/c53e71dc397de7486c9a8899f71598c3c3a18d44/services/core/jni/com_android_server_power_PowerManagerService.cpp), Android 12 commit `c53e71dc397de7486c9a8899f71598c3c3a18d44`: `enableAutoSuspend()` obtains `suspend_control_internal` and invokes `enableAutosuspend()`. This path belongs to Android framework power management; an Android container without `system_server` does not establish that it runs.

These are exact AOSP reference-source findings. The installed Halium binary has not been matched byte-for-byte to this source. A vendor/Halium patch or another client may change startup behavior; do not infer absence of every possible caller solely from these files.

## Sufficient read-only observations and limits

Inside the existing Android container, obtain a **bounded** `dumpsys suspend_control_internal --suspend_controls` response. A positive `suspend attempts` value, especially a later increase for the same still-running service process, proves that the reference autosuspend loop has run. It does not establish successful suspension or future progress. All-zero counters are inconclusive: the loop may never have been enabled, may be blocked by wake locks or may be blocked on its file descriptors.

Inspect the existing suspend-service process's descriptor symlink targets for actual `/sys/power/state` and `/sys/power/wakeup_count` descriptors. Socket substitutes instead of those descriptors indicate the intentional non-suspending fallback in the reference implementation. Listing these descriptor targets reads metadata; do not open/read `wakeup_count`, which can block, or write either descriptor.

Inspect targeted service startup errors and client provenance. An error opening either power-control file or a known successful enable invocation would be relevant; a process name, HIDL registration, accessible device-node mode, or mere `enableAutosuspend` string in a binary is insufficient. Confirming a client exists is separate from observing its call.

No read-only AOSP Android 12 API directly answers the enabled flag when counters remain zero. If runtime evidence remains inconclusive, retain the prerequisite as unresolved and design a separate, explicitly reviewed activation experiment. Do not call the mutating AIDL `enableAutosuspend`/`forceSuspend`, change properties, or write sysfs as a diagnostic query.
