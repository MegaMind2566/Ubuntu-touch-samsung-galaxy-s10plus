# repowerd SystemSuspend HIDL backport candidate

Source-only candidate, prepared 5 November 2026. **Not compiled, packaged, installed or hardware-validated.** It is not part of the alpha.1 ROM and is not a suspend fix proven on this handset.

## Scope and provenance

`0001-upstream-system-suspend-hidl.patch` is the unchanged upstream commit [d87b74538c368cd7bebef64c5b81c5c377ae3f88](https://gitlab.com/ubports/development/core/repowerd/-/commit/d87b74538c368cd7bebef64c5b81c5c377ae3f88), authored 17 June 2026: `src/adapters: add SystemSuspend HIDL system power control`. It adds two adapter files, one CMake source entry and a factory preference. Original GPL-3.0 notices/authorship are retained. The patch is the commit immediately after the `2026.06` release commit; checking out tag `2026.06` alone does not include it.

| Source identity | Pinned commit | Check performed |
| --- | --- | --- |
| Preferred source: official `ubports/24.04-2.x`, matching installed package suffix `gbp365751` | `36575160752bdd0a983bee1b53e041ccc4ceaa60` | Patch apply-check, application and whitespace check passed |
| Original `2025.09` release | `631d17f7654915d65b04b766d0abd3d38aa51eb2` | Same checks passed; factory context offsets only |
| Upstream HIDL change | `d87b74538c368cd7bebef64c5b81c5c377ae3f88` | New adapter source/header match, allowing checkout LF normalization |

Patch SHA-256: `a811a6547382f9f757678694f9582c1dc9988ef18f3743cd7680e9bb9b9c41c5`. Machine-readable boundaries and pins are in `verification.json`. Matching the package suffix identifies its official source revision; it does not establish the installed binary's reproducibility or integrity.

## Reason for this candidate

The 2025.09 factory tries Libsuspend and then Logind. Logind's automatic-suspend entry points are empty. The HIDL adapter instead coordinates repowerd's suspend inhibitions with Android's `android.system.suspend@1.0::ISystemSuspend/default`: it acquires an Android partial wake lock while inhibitions exist and releases it when the last inhibition is removed. It preserves the existing Libsuspend/Logind fallback.

The handset has a listed SystemSuspend HIDL service, `/dev/hwbinder`, libgbinder 1.1.52, and an Android suspend service process. This makes the source backport relevant. A listed process/service does not prove its autosuspend loop is enabled, that repowerd can transact with it, or that suspend/resume will succeed. This patch does not itself start that loop or call forced suspend.

See `autosuspend-readiness.md` for the unresolved Android autosuspend activation prerequisite and the limits of read-only counters.

## Dependencies and build prerequisites

No build dependency is added by the patch. Both pinned bases already use C++17, `libgbinder`, GLib/GIO, deviceinfo and optional hybris. All 17 gbinder API names used by the new adapter occur in official [libgbinder 1.1.52 headers](https://github.com/mer-hybris/libgbinder/tree/e906afcffbfa51b7fbefe042a13b933d9e8dfdd9/include); this is an API declaration check, not compilation/link validation. The library also depends on libglibutil; do not replace either installed library for this candidate.

Under the user's free-build requirement, use only the public repository's standard **GitHub Actions `ubuntu-24.04-arm` runner** via `.github/workflows/runtime-arm64-build.yml`, with an Ubuntu 24.04 arm64 environment with compatible official UBports development packages. Resolve the selected source's `debian/control` dependencies there: debhelper 13, dh-apport, android-headers, cmake/cmake-extras, dbus, googletest/google-mock and libgtest-dev, libdeviceinfo-dev, libgbinder-dev, libglib2.0-dev, libhybris-dev, pkgconf and systemd-dev. The `hello` alternatives in the packaging are not substitutes for a real binder-enabled Halium build. Tests need the DBus test environment; keep tests enabled.

Commands below describe the source/build steps executed inside that GitHub Actions runner only. Local, self-hosted and paid runner builds are outside the requested scope. They do not install onto the phone. Supply the absolute local patch path before running:

```sh
S10_HIDL_PATCH=/absolute/path/0001-upstream-system-suspend-hidl.patch
git clone https://gitlab.com/ubports/development/core/repowerd.git repowerd-s10-hidl
cd repowerd-s10-hidl
git checkout --detach 36575160752bdd0a983bee1b53e041ccc4ceaa60
git apply --check "$S10_HIDL_PATCH"
git apply "$S10_HIDL_PATCH"
git diff --check
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DREPOWERD_ENABLE_HYBRIS=ON \
  -DREPOWERD_ENABLE_BINDER=ON \
  -DREPOWERD_BUILD_TESTS=ON \
  -DENABLE_WERROR=ON \
  -DREPOWERD_DISABLE_TIME_SENSITIVE_TESTS=ON
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```

These options follow the pinned upstream `debian/rules` for an Ubuntu build. Build/test commands have **not** been executed in this Windows session. Successful patch application is not a build result.

For later package work inside the same free GitHub Actions runner, retain the pinned base's Debian packaging. Give all outputs one explicit local source version and use `dpkg-buildpackage -us -uc -b` in the arm64 build environment. `repowerd` and `repowerd-tools` have an exact dependency on `repowerd-data (= ${source:Version})` in this baseline. They must come from the same source/version; do not weaken that relation or replace only `/usr/sbin/repowerd`. This candidate provides no installation command.

## Limits to resolve before a handset trial

- The factory probes HIDL once at daemon construction. The service and binder access must be ready then. The preferred installed-source branch already has `WantedBy=graphical.target`; original tag 2025.09 has `multi-user.target`. No service-ordering patch is bundled. A later fallback log means this path was not selected for that process.
- The unchanged upstream adapter logs wake-lock acquisition failure rather than throwing for a later factory fallback. It has no service-death/reconnect handling or transaction timeout. A successful constructor alone does not prove inhibition works.
- Its resume/allow/disallow callback registrations, explicit `suspend()` and default-handler methods are no-ops. Confirm that automatic-suspend coordination through Android, rather than direct suspend or resume callbacks, matches the tested session.
- Establish that Android's autosuspend controller is active. Holding/releasing a HIDL wake lock cannot by itself enable a disabled Android autosuspend loop or clear unrelated kernel wake locks.
- Before deployment, require a genuine arm64 build and upstream tests, package dependency review, image/binary identities and a reversible recovery procedure. Keep BOOT 6, audio/TRRS, Wi-Fi and existing USB settings intact.
- A trial must show `HidlSystemPowerControl` selected and a wake lock actually acquired/released under screen state changes; compare read-only BOOTTIME/MONOTONIC snapshots, kernel suspend counters and physical wake behavior. Clock accounting alone is not a deep-sleep or endurance result.

The intended next step is a reproducible host build and adapter test coverage. Nothing here authorizes a binary replacement or claims runtime success.

## Reusable Linux build entry point

`build-linux-arm64.sh` runs the preferred pinned-source build only inside the free GitHub Actions workflow in a public repository. It refuses an ordinary local invocation. It verifies patch/source identities, checks real binder/property/deviceinfo development modules and source build dependencies, rejects skipped-test build options, and retains package versions, build logs, exit status and package checksums in a unique output directory. It uses the baseline native Debian packaging with version `2025.09+s10hidl.20261105`, preserving the exact daemon/tools/data dependency relation. It neither installs dependencies nor installs its outputs.

The workflow sets a clearly identified local-candidate builder identity in `DEBFULLNAME` and `DEBEMAIL` and executes:

```sh
bash /absolute/path/tools/repowerd-suspend/build-linux-arm64.sh /absolute/output/repowerd-hidl
```

The script has passed Bash syntax verification in Windows only. A completed build is a package-build result; it is not phone installation, HIDL transaction acceptance or suspend validation. A separate build record must report actual outcomes.

## Official repository and dependency identity

The workflow uses only `https://repo.ubports.com/`, suite `24.04-2.x`, component `main`, with APT `signed-by` and the SHA-256-pinned official 2026 key. The suite name is not `noble`; Ubuntu base packages still come from normal Ubuntu 24.04 repositories. This follows the signed-keyring method in [official UBports build documentation](https://docs.ubports.com/en/latest/systemdev/testing-locally.html).

`build-dependencies.json` records the observed key fingerprint, signed index hashes and exact development-package versions matching the handset: hybris/properties `61f88b`, deviceinfo `84bff0` and gbinder `d4855b1`. The workflow pins these versions to avoid inadvertently raising the candidate's runtime library requirement to the newer October 2026 libhybris series. APT still verifies signatures and resolves dependencies normally; no unsigned-repository or forced-dependency option is used. Package dependencies and ELF symbol requirements must be reviewed after the build.
