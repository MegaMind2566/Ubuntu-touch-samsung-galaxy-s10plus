# Guarded Android SDK32 autosuspend activation candidate

Second patch, source candidate awaiting its own free GitHub ARM64 build and runtime acceptance. Apply only to exact official repowerd `36575160752bdd0a983bee1b53e041ccc4ceaa60` after unchanged upstream HIDL patch `d87b74538c368cd7bebef64c5b81c5c377ae3f88`. The first variant's successful build is preserved; it is not evidence for this new behavior.

## Contract and lifecycle

The handset's read-only listing confirms Android SDK32 and normal-binder descriptor `android.system.suspend.internal.ISuspendControlServiceInternal`. Pinned [AOSP Android12 AIDL](https://android.googlesource.com/platform/system/hardware/interfaces/+/858d482871f3b757af1da04777a3bd9be9ea427a/suspend/aidl/android/system/suspend/internal/ISuspendControlServiceInternal.aidl) places boolean `enableAutosuspend()` first, with no arguments. Libgbinder 1.1.52 supplies normal-binder service-manager `aidl3` plus RPC `aidl4` for SDK31/32. No global binder configuration is changed.

The constructor discovers HIDL asynchronously and acquires a verified Android partial wake-lock object before declaring this backend usable. Borrowed service lookup objects are explicitly referenced; the previous autoreleased-sync-result ownership problem is removed. Unknown allow IDs cannot activate or release the bootstrap guard. Multiple inhibition IDs retain the guard until the final known ID is allowed.

At that first legitimate final allow, the backend latches its attempt before sending a single AIDL activation. Discovery and the activation transaction share a three-second monotonic deadline. Only transport success, exception/status integer zero, exact integer boolean one and end-of-parcel count as acknowledgment. False (including an already-enabled response), malformed/truncated/trailing replies, exceptions, service unavailability, deadline or death latch failure. Existing guard references are retained; no blind retry or release follows failure.

After acknowledgment, release is an asynchronous HIDL **oneway** transaction with its own three-second budget. A successful oneway completion means transport acceptance, not an independent service readback. Failure/deadline is explicitly **unknown**: the server may have released despite retained references, so no guard-held claim or second release is made. A later legitimate disallow reacquires a checked wake lock; failure records `inhibition-unavailable` and latches without pretending a lock exists.

## Callback and lifetime rules

Libgbinder 1.1.52 dispatches on the global default GLib context, while repowerd normally uses private contexts. Each bounded operation acquires the global context and iterates it non-blockingly within its deadline; concurrent ownership causes a safe refusal. The timeout budget excludes uncontrolled scheduler delays and construction of the underlying Binder driver objects. Each asynchronous transaction is bounded; a first final-allow path can spend up to three seconds on activation plus three seconds on release.

`gbinder_client_cancel` suppresses callback delivery but cannot interrupt a kernel Binder transaction or undo remote execution. The deferred destroy callback therefore owns a heap/shared result context containing no adapter pointer. A late activation may still run; the failed latch retains the existing bootstrap guard in that case. Service discovery's API has no userdata destructor: it is deliberately not cancelled, and its eventual callback owns the heap holder. If Binder never returns, that single lookup context may remain until process exit. There is no unbounded retry or accumulating polling loop.

No borrowed reply reader survives its callback. New wake-lock references, client references and discovery references have separate ownership. Cleanup drops them exactly once, including constructor failure and callback completion after timeout.

## Safety boundary and rollback

No `forceSuspend`, direct sysfs write or arbitrary activation timer is added. This is coordination with Android's standard loop, not a guarantee of global fail safety. Existing guards protect only while the client and HAL remain alive. Binder wake locks release when their owning client dies; HAL death resets its process-local loop in the pinned implementation. A later wake-lock reacquisition failure after a successful release cannot fabricate inhibition: it is explicit failure, not a held guard.

Android's activation latch has no disable method. Removing the binary/drop-in alone does not reset an enabled service loop. A controlled trial needs verified package/library/data identities, a private root-owned staging tree, one repowerd instance, native authentication preserved, physical wake/USB/Wi-Fi recovery checks and a tested reboot/recovery rollback. No everyday-use or suspend/resume acceptance is claimed by compilation.

## Verification and free build

`candidate.json` pins patch/source hashes. `fake-binder-test.cpp` compiles the **actual patched adapter and bounded helper**, plus actual core logging/handler code, against real libgbinder headers. Only the C transport boundary is simulated. Fifteen cases cover constructor acquisition failure, bootstrap-before-mutation, unknown IDs, multiple IDs/final allow, acknowledgment, false/invalid bool, exception, truncated/trailing reply, transport failure, lookup failure/deadline, activation deadline with late server effect, reacquisition failure, service death, release failure and release deadline. Reference counters plus ASan/UBSan check ownership, including delayed callback cleanup. These do not exercise a real Binder driver or power hardware.

Use only `.github/workflows/suspend-activation-build.yml`, a public-repository standard free `ubuntu-24.04-arm` job. It calls the shared builder with `S10_ENABLE_AIDL_ACTIVATION=1`; default zero preserves the first variant. The new version is `2025.09+s10hidlactivate.20261105`, with exact matching daemon/data/tools dependencies. Tests, logs, package hashes and manifests are retained. No C++ compilation or test was run locally, and neither workflow installs on the phone.
