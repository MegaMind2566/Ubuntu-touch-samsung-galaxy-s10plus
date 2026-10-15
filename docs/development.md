# Development and validation

This project builds an experimental Ubuntu Touch adaptation for `beyond2lte`. Local scripts and CI build artifacts; they do not automatically flash a handset.

The test user now confirms a graphical Ubuntu Touch boot with working touch and Wi-Fi after graphics permission correction 1 on BOOT 6. A screenshot and fresh correction/runtime report remain pending. Development has moved from first boot to stability, remaining-hardware validation and a repeatable installation path; the older diagnostic procedures below remain state-specific references.

## Source and binary inputs

- [Source pins](../config/upstream.lock.json): Samsung Halium 12 adaptation, matching kernel and generic adaptation build tools.
- [Kernel configuration](../config/ubuntu-touch.config) and [kernel patches](../patches/kernel): AppArmor support, two SAR ramdisk fixes and the Samsung USB configuration string guard.
- [SYSTEM assembly inputs](evidence/assembly-inputs-2026-10-12.json): Ubuntu Touch 24.04 arm64 rootfs build 125 and Halium 12 GSI build 1310, with recorded digests.
- [Installation image pins](../config/install-images.lock.json): the original BOOT/SYSTEM candidate, used by the preparation and verification code. The current test configuration is BOOT 6 plus graphics permission correction 1; its earlier measured image identities are recorded in the dated evidence.

The source commits and major image hashes are pinned. Some upstream build-tool and prebuilt dependencies still need a complete lock before the entire build can be called reproducible. Successful builds do not establish a supported Ubuntu Touch update channel.

## Build the adaptation

Use a Linux build environment with the dependencies listed in [build-adaptation.yml](../.github/workflows/build-adaptation.yml).

```sh
python3 scripts/fetch_sources.py --include-kernel
bash scripts/build-adaptation.sh
```

`prepare_build.py` refuses nonempty or modified upstream checkouts and requires the five reviewed kernel patches. Build products live under `out/`; downloaded sources and build directories are not committed.

The [SYSTEM assembly workflow](../.github/workflows/assemble-system.yml) combines the pinned rootfs, Halium GSI and adaptation into the measured filesystem layout. Use its input records when reproducing the candidate instead of replacing binary URLs with the latest available download.

## Historical boot diagnostics

The completed diagnostic 1/2 packages and BOOT 4 userspace inspector are preserved in [archive](../archive/README.md), outside executable workflow paths. Their original sources and blob identities are listed in [archive/manifest.json](../archive/manifest.json). Reproduce an old package by checking out its recorded source commit with its original layout.

The current BOOT builder still imports the CPIO/image/input helpers in `prepare_boot_diagnostic.py` and `early_boot_diagnostic.py`. These modules, their immutable init input, the configuration fragment and the forced built-in-initramfs patch remain maintained. The shared force-guard regression is in `tests/boot_force_guard.py`. Standalone diagnostic builders, installers and their old native-entrypoint tests are not part of the current installation path.

## Kernel binary analysis

[kernel-symbol-audit.yml](../.github/workflows/kernel-symbol-audit.yml) checks out immutable `vmlinux-to-elf` and DTC commits. It recovers ELF symbols from the exact BOOT 1/2 kernels, verifies the mapped raw bytes with an independent ELF parser, and disassembles selected ARM64 boot functions. DTC is built unmodified and its upstream test suites are run.

```sh
python3 scripts/audit_kernel_symbols.py fetch
out/kernel-analysis-venv/bin/python scripts/audit_kernel_symbols.py analyze
```

The fetch step needs a scoped `UT_ARTIFACT_TOKEN` for reading this repository's Actions artifacts. The CI workflow configures that token only for the download step. Artifact clients use `GITHUB_REPOSITORY`; outside Actions, set this variable to the current `owner/name` before fetching artifacts after a repository rename. The converter needs its complete pinned source checkout and SQLite metadata database, not just its Python files. Source acquisition and isolated installation are shown in the workflow.

The generated ELF's load base and entry point are static-analysis metadata. Its BSS extent is synthetic, and it is not a flashable BOOT image. Runtime KASLR and the bootloader's actual transfer remain separate questions.

To repeat the device-tree inspection with the verified HWC1 DTB partition, prepared recovery and CI-built DTC tools:

```sh
python3 scripts/audit_device_trees.py \
  --dtb-partition /path/to/dt.img \
  --recovery /path/to/recovery-test.img \
  --tools /path/to/dtc-tools \
  --out out/device-tree-audit
```

The script validates all input identities, applies stock DTBO entry 9 and retains DTC warnings. The recorded TWRP index is a selection basis for this experiment; it is not a normal-boot device-tree capture.

## Validation boundaries

| Check | What it establishes |
| --- | --- |
| Source/configuration checks | Intended inputs and patches are present. |
| Image/hash/layout checks | Payload structure, identity and partition fit. |
| Host and ARM64 userspace fixtures | Behavior of selected programs and guarded paths with controlled inputs. |
| Native Windows tests | Actual PowerShell 5.1/CMD execution; USB responses and raw writes are simulated. |
| Handset readback | The intended bytes reached the measured partition prefix. |
| Normal-boot logs and observed screen | Actual execution stages on the handset. |

Keep those levels distinct in reports and pull requests. Every new hardware result should record image identity, operation performed, observed state and remaining uncertainty in `docs/evidence/`.

## Repository maintenance

Current code uses [scripts](../scripts/README.md), shared templates use `scripts/templates/`, and original experiment sources use [archive](../archive/README.md). Archive moves retain original Git blob identities in [archive/manifest.json](../archive/manifest.json); archived workflows are outside GitHub's executable workflow directory.

Do not copy firmware images, portable runtimes, build output or extracted kernel ELF files into Git. Preserve compact provenance reports and Actions artifact references. A future repository rename should retain historical run/artifact references; the current artifact helper derives the repository from `GITHUB_REPOSITORY` in CI.

For each hardware experiment, add its compact dated evidence and update [Project status](status.md) with the result and next action. Keep the README focused on the project goal and verified progress. Archive superseded standalone tools only after checking their active imports, packaging paths and workflows; update the archive manifest and replacement links together. Shared components stay in the maintained paths while active packages depend on them.

The [publication criterion](status.md#publication-criterion) is a confirmed Ubuntu Touch graphical boot on the test handset. The user's boot, touch and Wi-Fi reports meet that first-boot milestone. Record the report separately from earlier runtime/image measurements and add the screenshot and fresh correction logs when available. Repository visibility must be verified independently; documentation of the milestone does not establish that publication has occurred.

## Ubuntu BOOT 6 through the observed built-in path

The [BOOT 5 handset record](evidence/ubuntu-boot-5-handset-2026-10-15.json) confirms systemd PID 1, the Android container and vendor HWC execution. Both attempts panic when `usb_moded` links a USB configuration whose language directory exists but whose string is still NULL. Exact kernel symbols map the fault to `strcmp(cn->configuration, "Conf 1")` in Samsung's configfs driver. Patch 0005 adds the missing NULL guard; host and static ARM64 fixtures cover NULL, unset text and multiple language entries. A fixed comparison does not itself establish a graphical boot.

`build-ubuntu-boot-handoff.sh` obtains the exact BOOT 4 from successful run 38756613455, artifact 11985068265, as immutable image/header reference and rollback. The original Ubuntu ramdisk still comes from pinned BOOT 2. The installer separately requires the exact physically read-back BOOT 5 as its current-image baseline. Applying requires BOOT 5 and writes BOOT 6; restoring requires BOOT 6 and writes BOOT 4. The BOOT 5 bootloop is never the rollback target.

The kernel uses the pinned source, five normal patches and the built-in-initramfs force guard. Peripheral settings are preserved; permitted configuration differences from BOOT 4 remain the initramfs source and command line. BOOT 6 retains BOOT 5's `systemd.unified_cgroup_hierarchy=0` and systemd kmsg debugging in both kernel configuration and BOOT header. The [userspace audit](evidence/userspace-compatibility-2026-10-15.json) records the exact SYSTEM/Android identities, dependencies and controller compatibility.

`ubuntu_boot_handoff.py` preserves all 347 original CPIO entries except four instrumented scripts and adds five helper inputs. It retains the original Ubuntu wrapper and root/container mounts, disables automatic userdata repair/resize, and gives final `run-init` null input and kmsg output. Both decoded CPIO copies must match exactly and the compiled BOOT must fit its measured partition.

Before handing over PID 1, BOOT 6 copies the complete contents of three small existing profile directories into private executable RAM, adds the port's missing device/HWC profiles, and binds those directories over their original locations. The device profile accepts Android's observed `beyond2` alias. Hashes, read-only backing filesystems, canonical paths, bounded contents and preserved file metadata are checked before any bind. Preparation failure stops the handoff.

A hash-guarded RAM override adds an `ExecStartPost` to the existing Halium overlay unit. After its read-only Android/vendor mounts are ready, the hook masks Samsung's recovery-restoration script and supplies the missing Android init profiles in RAM, including their LXC aliases. LXC's existing `Requires`/`After` dependency prevents it starting when this hook fails. The recovery mask is installed before the Android init directories. These changes disappear at reboot and do not rewrite SYSTEM, VENDOR or RECOVERY.

The separate HWC helper still requires a genuinely running compositor service. Its RAM override survives LightDM restarts. A private static BusyBox observer inside the new root records PID 1, cgroups, mounts, kernel, journal and Android/HWC state for up to 120 seconds without holding old-initramfs descriptors. The collector additionally retrieves bounded `android-profile.log` output. The observer's `/proc/1` links are read individually for compatibility with the shipped BusyBox.

The source gate exercises the exact ARM64 BusyBox under QEMU, including trace transport, post-root observation, HWC readiness and RAM-profile preparation/rollback fault cases. USB tests also compile and execute static ARM64 cases. These fixtures simulate mounts and device responses; they do not mount or write a handset. Image tests check the embedded archive, configuration, source guards, exact command line and corrupt-input rejection.

The generated Windows suite has 25 apply/restore cases, including rejecting BOOT 4 as an apply baseline, requiring BOOT 5, preserving earlier checkpoints and restoring BOOT 4 only from BOOT 6. Native PowerShell 5.1/CMD and portable PowerShell 7/Linux checks must be recorded separately; the portable run cannot establish CMD/PE startup or Windows file-sharing denial. Shared installer/verifier templates remain unchanged. The BOOT 5 [build record](evidence/ubuntu-boot-5-build-2026-10-15.json) documents the previous local build and the hosted run that received no runner; its cause is unconfirmed.

Firmware validation preserves tested gzip bytes without host recompression. Superseded BOOT 3/4/5 standalone tools are archived with original Git blob identities; shared inputs remain active. The [BOOT 6 build/package record](evidence/ubuntu-boot-6-build-2026-10-15.json) records the completed local build, actual compiled NULL branch, 33 RAM-profile cases, 26 HWC cases and 25 portable PowerShell control-flow cases. The optional five-slot logging limit does not prevent RAM preparation or a later boot. Exact image/member/manifest checks pass; native Windows CI received no runner and executed no steps. Working graphics are now user-confirmed after the separate permission correction; this build record predates that report.


## Retained graphics logs after BOOT 6

The physical BOOT 6 record confirms its exact readback and two-minute normal run, followed by repeated Lomiri mapper aborts. `collect-ubuntu-graphics.py` uses the existing pinned portable tools and prepared TWRP; it validates recovery/BOOT identity and raw userdata before fixed, bounded log reads. It does not execute SYSTEM programs, mount filesystems or change phone files. It uses recovery BusyBox for metadata, canonical-path checks and log tails. The first handset result exposed a configuration mismatch: TWRP BusyBox 1.22.1 does not support `stat -c`, unlike the normal BOOT BusyBox used in the initial QEMU tests. Collector version 2 uses the advertised terse stat mode and treats failed collection separately from optional missing files. Version 2 recovered four retained log files on the handset, but its transport limit discarded USC after LF-to-CRLF expansion. Version 3 separates the remote read limit from a bounded 2x transfer allowance, preserves received newlines and adds the first 64 KiB of that same USC file. It retains the known working shell transport rather than requiring raw mode from older adbd. The revised suite executes the exact BusyBox, linker and libraries extracted from the hash-pinned original TWRP recovery under QEMU, reproduces the unsupported stat option, and exercises remote ranges and expanded transport limits. Mount/device boundaries remain fixtures; the phone kernel is not emulated.

```sh
python3 tests/test_ubuntu_graphics.py --qemu /path/to/qemu-aarch64-static --recovery-image /path/to/twrp-3.7.0_9-2-beyond2lte.img
python3 scripts/package-ubuntu-graphics.py
```

The package merges into the existing Windows installation folder. Its native launcher must be reviewed separately from the Python and ARM64 shell fixtures; this run does not claim native Windows execution. Preserve the existing BOOT 6 collector and shared helpers while these packages depend on them.

## Controlled runtime graphics probe on BOOT 6

The successful version 3 collection identified a working root EGL/Mali display path; the following runtime probe recovered the missing nested mapper failure. The separate `tools/graphics-probe/` payload uses the existing writable `/etc/systemd/system` mapping to install one removable diagnostic service from TWRP. It compares mapper initialization under controlled root/phablet/lightdm credentials, redirects the Bionic liblog instance within those probe children to stderr, and traces only their filesystem calls. It does not change existing display services or device permissions. A successful probe is not a graphical boot.

`manage-graphics-probe.py` checks pinned tools, root recovery, model/bootloader, prepared RECOVERY, exact BOOT 6 and already mounted raw userdata for preparation, collection and removal. The fixed files and enabled-unit link reside only on userdata. Payload hashes, canonical root-owned paths, conflicting files and nested mounts are checked; the enable link is the final write. Removal disables the owned service after validating all present known files and preserves logs/unknown files. Read the logs before removal.

```sh
python3 tests/test_graphics_runtime_probe.py --report out/graphics-runtime-tests.json
python3 tests/test_graphics_probe_installer.py --qemu /path/to/qemu-aarch64-static --recovery-image /path/to/twrp-3.7.0_9-2-beyond2lte.img --report out/graphics-installer-tests.json
python3 scripts/package-graphics-probe.py
```

The unit is `Type=simple`, so collecting the evidence does not hold the graphical target behind a long oneshot job. Its own process tree has a 150-second maximum, per-child timeouts, core dumps disabled and bounded private logs. The handset procedure allows four minutes after selecting System, since Android boot precedes the service's runtime limit. The [probe evidence record](evidence/ubuntu-graphics-runtime-probe-2026-10-15.json) separates host ABI fixtures, TWRP shell fixtures, parser validation and the completed handset comparison: root loads Mapper 2.0, while phablet/lightdm fail hwbinder access with EACCES. Both hwbinder and ion remain 0600; root opens ion in the working path. Retain BOOT 6 and its firmware evidence unchanged.


## Targeted graphics permission correction on BOOT 6

`tools/graphics-permissions/` provides the correction after which the user reports graphical boot, working touch and Wi-Fi, distinct from the immutable diagnostic probe. The earlier handset evidence establishes a device access failure rather than a missing vendor mapper ABI. The intended adaptation udev rules were skipped because their overlay destination did not exist. A dedicated rule persists through the existing `/etc/udev/rules.d` writable mapping without changing SYSTEM or flashing another image.

`manage-graphics-permissions.py` verifies pinned tools, root TWRP, model/SoC/bootloader, prepared RECOVERY, exact BOOT 6 and already mounted raw ext4 userdata before any operation. It stores four hash-pinned payloads and fixed udev/systemd configuration on userdata. The LightDM dependency is published last; repeat application is idempotent. Conflicts stop the operation, and failed creation rolls back only its own new files. Undo validates all present known files before removing the dependency first and preserves logs/unknown files. Undo takes effect after reboot; it does not chmod recovery devices.

On normal Ubuntu boot, the 45-second service runs after LXC configuration and udev triggering, before LightDM. It pins both root-owned character-device inodes with O_PATH, compares their major/minor identities with `/sys/class/misc`, accepts only the observed 0600 or intended 0666 modes, and completes both preflights before changing either. It changes mode only, retaining root ownership. The service verifies read/write access as phablet/lightdm, reverses its own changes on errors or SIGTERM/SIGINT and blocks LightDM on failure. No vndbinder/binder/Mali or SYSTEM permissions change. The udev rule retains those two modes across matching events.

An optional controlled comparison reuses only the hash-pinned historical mapper probe if it is still installed. Absence or diagnostic failure does not block the correction. There is no LXC attach or Android boot-completed polling in this path. Four private bounded logs and bounded existing compositor/greeter/LightDM excerpts can now document the reported successful session.

```sh
python3 tests/test_graphics_permissions_runtime.py --report out/graphics-permissions-runtime-tests.json
python3 tests/test_graphics_permissions_installer.py --qemu /path/to/qemu-aarch64-static --recovery-image /path/to/twrp-3.7.0_9-2-beyond2lte.img --report out/graphics-permissions-installer-tests.json
python3 scripts/package-graphics-permissions.py
```

Runtime device/sysfs/UID boundaries are simulated in host tests, including real signals delivered to dedicated fixture children. Installer shell cases execute the exact pinned TWRP BusyBox/linker/libraries under QEMU with controlled mounts/device metadata. Native Windows CMD/Python PE is not exercised by these fixtures. The GUI, touch and Wi-Fi now have the user's confirmation; a screenshot and fresh correction/runtime report have not yet been supplied. The [correction record](evidence/ubuntu-graphics-permission-fix-2026-10-15.json) records final payload identities, tests, delivery and the reported outcome. Keep the correction installed on the working handset; collect logs before any undo.
