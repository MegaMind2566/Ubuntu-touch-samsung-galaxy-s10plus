# adbd USB reconnect candidate

Source candidate for the S10+ ADB reconnect regression, not an installed fix.
Compilation is restricted to the public repository's standard free
`ubuntu-24.04-arm` GitHub Actions workflow. No local or paid builder is used.
Hardware acceptance remains required after successful build and review.

## Exact source and evidence

The installed package is
`1:14.0.0+r45-0ubports1+0~20260505122413.7+ubports24.04.2~1.gbp6391ff`.
The patch is appended after the complete existing Debian series from
[UBports packaging 6391ffe9](https://gitlab.com/ubports/development/core/packaging/adbd/-/tree/6391ffe9e12162de349fe595fdf8d92b5cbf443f),
on [Android android-14.0.0_r45, b8016a72](https://android.googlesource.com/platform/packages/modules/adb/+/b8016a7210eba240788f262e1e4214576aa6fdd8/).
`candidate.json` pins the patch and both affected files before/after application.

The observed failure is ADB becoming offline after unplug/replug: adbd remains
alive after `FUNCTIONFS_DISABLE`, with no following `ENABLE` in its captured log.
An official usb-moded mode change recreates adbd and restores authorized ADB.
This establishes the regression and a recovery path, not a captured worker stack.

There are two source-level barriers:

1. `UsbFfsConnection::StopWorker()` repeatedly tests a joinable pthread using
   signal zero before joining it. The imported `pthread_kill@GLIBC_2.34` can
   return zero after the kernel task has exited. The bounded own-thread probe
   in `probe-pthread-lifetime.py`, with its recorded handset result, confirms
   that prerequisite on the actual glibc 2.39 runtime. It does not signal adbd
   or prove the complete bug fix. See the
   [glibc 2.39 implementation](https://github.com/bminor/glibc/blob/release/2.39/master/nptl/pthread_kill.c).
2. Teardown then closes FunctionFS ep0 and the next transport expects a fresh
   `BIND`. On Ubuntu Touch, usb-moded owns UDC and the Android property-driven
   rebinding mechanism is absent. `open_functionfs()` also overwrites an
   already-open control fd with its empty local fd on the reuse path.

The [Debian maintainer report](https://salsa.debian.org/android-tools-team/admin/-/issues/54)
independently describes both barriers and an ep0-retention proof of concept.
This candidate is a local implementation, not a claimed released upstream fix.
The actual Android source is
[usb.cpp](https://android.googlesource.com/platform/packages/modules/adb/+/android-14.0.0_r45/daemon/usb.cpp)
and [usb_ffs.cpp](https://android.googlesource.com/platform/packages/modules/adb/+/android-14.0.0_r45/daemon/usb_ffs.cpp).

## Candidate behavior

The worker publishes completion through a release/acquire atomic flag on every
return path. Stop still wakes eventfd waits, interrupts blocking kernel submits
with the existing SIGUSR1 mechanism, and joins the thread. There is no signal-zero
liveness polling. An uninterruptible kernel wait is not repaired by this change.

The open thread retains ep0 and its `bound` state across transport lifetimes.
Each previous monitor is joined before another monitor accesses that state.
`DISABLE` preserves binding, while an actual `UNBIND` clears it. Existing ep0
is retained when bulk endpoints reopen; descriptors are not rewritten. A service
stop still closes the process's descriptors normally.

Only `daemon/usb.cpp` and `daemon/usb_ffs.cpp` change. The patch does not write
UDC/configfs, flip USB modes, add a watcher, alter ADB authorization, replace host
keys, or change the service's `ADBD_SECURE=1` behavior. usb-moded remains the USB
mode owner.

## Reproducible verification and build

`build-linux-arm64.sh OUTPUT_DIRECTORY` is invoked by
`.github/workflows/runtime-arm64-build.yml`, only on native Ubuntu 24.04 arm64.
It fetches the two exact revisions, applies the original Debian series with
quilt, verifies the failing baseline, applies this candidate, verifies the
candidate, and runs the full official Debian package build. It never installs a
package or contacts a handset. The local version is
`1:14.0.0+r45-0ubports1+s10reconnect.20261105`.

`verify-adbd-reconnect.py` extracts the actual four lifecycle methods from the
hash-checked source and compiles them with real Linux threads, signals, pipes,
poll and eventfd. It also compiles the actual `usb_ffs.cpp`, stubbing only its
external Android boundaries and using ordinary temporary endpoint files.
Each executable runs in a bounded child process.

| Case | Baseline required result | Candidate required result |
| --- | --- | --- |
| Worker returns during initial read submission | Timeout | Completes |
| Idle worker waiting on eventfd | Not run | Completes |
| Interruptible blocked submit boundary | Not run | Completes |
| Three reconnects, subsequent ENABLE without new BIND | Not run | Completes |
| Explicit UNBIND followed by fresh BIND/ENABLE | Not run | Completes |
| Reopen bulk endpoints with existing ep0 | Assertion failure | Same valid fd, one descriptor write sequence |

Baseline failure is required: merely compiling the candidate cannot pass this
gate. `baseline-tests/results.json` and `candidate-tests/results.json` retain
the observed and required results. These fixtures test the userspace protocol;
they do not simulate the S10 kernel AIO implementation, a real USB host, transfer
integrity, or authenticated end-to-end ADB. Full upstream AOSP test coverage is
not claimed.

Build requirements are those in the pinned `debian/control`: debhelper 13,
dpkg-dev, quilt, clang, make, pkg-config, protobuf compiler, pandoc; systemd,
PAM, audit, Android base/cutils/selinux/boringssl/utils/properties development
libraries; brotli, cap, gtest, lz4, protobuf, safe-iop, libusb, zstd, zlib and
Avahi compatibility headers. The workflow uses authenticated official UBports
APT packages matching its Ubuntu baseline. Installed builder package versions
are recorded. The original `liblz4-dev,,` dependency separator is corrected only
in the generated build tree and recorded in `packaging-adjustments.txt`.

Artifacts include the complete `.deb`, build metadata, dependency declarations,
logs, SHA-256 sums and fixture results. Runtime dependencies must be compared
with the handset before deployment; a build is not permission to upgrade the
handset's libraries.

## Deployment gate and rollback

Before any installation, review the successful fixture/build logs, exact package
contents/dependencies and ELF architecture/imports, and retain a verified copy
of the original package or binary plus service metadata. No deployment commands
are embedded here. The existing authenticated Wi-Fi SSH recovery route must
remain available during any later hardware trial.

Hardware acceptance must check secure authorized ADB shell and file transfers,
then repeated physical unplug/replug in the existing usb-moded mode, without
mode flips or daemon restarts. Compare adbd lifecycle events and process identity;
check that the final mode, authorization and unrelated functions remain valid.
Unexpected failure requires restoring the retained original package through the
existing recovery route and recording the failed candidate. Until that evidence
exists, the reconnect regression remains open.
