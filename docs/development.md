# Development and validation

This project builds an experimental Ubuntu Touch adaptation for `beyond2lte`. Local scripts and CI build artifacts; they do not automatically flash a handset.

## Source and binary inputs

- [Source pins](../config/upstream.lock.json): Samsung Halium 12 adaptation, matching kernel and generic adaptation build tools.
- [Kernel configuration](../config/ubuntu-touch.config) and [kernel patches](../patches/kernel): AppArmor support and the two SAR ramdisk fixes.
- [SYSTEM assembly inputs](evidence/assembly-inputs-2026-10-12.json): Ubuntu Touch 24.04 arm64 rootfs build 125 and Halium 12 GSI build 1310, with recorded digests.
- [Installation image pins](../config/install-images.lock.json): the original BOOT/SYSTEM candidate, used by the preparation and verification code. They are not the identity of the currently installed diagnostic BOOT.

The source commits and major image hashes are pinned. Some upstream build-tool and prebuilt dependencies still need a complete lock before the entire build can be called reproducible. Successful builds do not establish a supported Ubuntu Touch update channel.

## Build the adaptation

Use a Linux build environment with the dependencies listed in [build-adaptation.yml](../.github/workflows/build-adaptation.yml).

```sh
python3 scripts/fetch_sources.py --include-kernel
bash scripts/build-adaptation.sh
```

`prepare_build.py` refuses nonempty or modified upstream checkouts and requires the four reviewed kernel patches. Build products live under `out/`; downloaded sources and build directories are not committed.

The [SYSTEM assembly workflow](../.github/workflows/assemble-system.yml) combines the pinned rootfs, Halium GSI and adaptation into the measured filesystem layout. Use its input records when reproducing the candidate instead of replacing binary URLs with the latest available download.

## Current diagnostic

[early-boot-diagnostic.yml](../.github/workflows/early-boot-diagnostic.yml) builds diagnostic 2 after the first test produced no saved PID 1 evidence. It embeds a minimal raw CPIO derived from the pinned diagnostic 1 BusyBox/display payloads. A separate [configuration fragment](../config/early-boot-diagnostic.config) enables the built-in initramfs, and a [diagnostic-only patch](../patches/diagnostic/0001-honor-force-for-builtin-initramfs.patch) makes `CONFIG_INITRAMFS_FORCE` take precedence over `skip_initramfs`.

The builder compares the new kernel's embedded configuration with BOOT 2's embedded configuration and rejects changes outside initramfs options. It verifies the exact CPIO bytes in the compiled ARM64 Image, preserves diagnostic 1's external ramdisk and header fields, and packages that exact image as rollback. Generated Windows guard fixtures remain under `out/`. Builds and native host tests do not establish handset execution.

[boot-diagnostic.yml](../.github/workflows/boot-diagnostic.yml) obtains the previously verified BOOT 2 artifact, builds the static ARM64 display helper, and substitutes only the controlled diagnostic ramdisk. It validates kernel/header preservation and tests the collector and generated Windows guards.

The diagnostic does not start Ubuntu. It attempts to record its progress, enumerate a USB ACM function and show a framebuffer status. It saves bounded logs in a dedicated data directory and mounts SYSTEM/VENDOR read-only for layout checks. Its rollback restores BOOT 2; BOOT 2 itself is not a known working Ubuntu boot.

To regenerate a package from verified local diagnostic images:

```sh
python3 scripts/package-boot-diagnostic.py --images out/boot-diagnostic-images
```

Windows `.cmd` files in [tools/windows](../tools/windows/README.md) are packaging inputs. They run from an extracted, prepared package with its pinned dependencies and images, not directly from a repository checkout.

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

The [publication criterion](status.md#publication-criterion) is a confirmed Ubuntu Touch graphical boot on the test handset. Record that runtime result before changing repository visibility.

## Ubuntu BOOT 3 through the observed built-in path

`build-ubuntu-boot-handoff.sh` obtains the exact diagnostic 2 rollback from run 38735252560 and the original Ubuntu ramdisk from the pinned BOOT 2 input. It builds the same kernel source and normal four patches with the tested force guard, now using gzip compression for the complete Ubuntu initramfs. Its configuration comparison permits only the initramfs source/compression changes from diagnostic 2. Both embedded and external CPIO must match the instrumented payload exactly and fit the measured BOOT partition.

`ubuntu_boot_handoff.py` preserves all 347 original entries except three observed scripts and adds one bounded stage helper. The original rootfs/container mount logic remains; the automatic userdata repair/resize call block is skipped during this measured first-boot attempt. Logs are limited to five owned runs and 2 MiB of kernel text per run. No framebuffer test helper is added.

The dedicated `ubuntu-boot-handoff.yml` workflow checks the real compressed kernel payload, the actual ARM64 BusyBox parser and log-directory guards, source force behavior, corrupted inputs and the read-only collector. The Windows job uses the established 24 apply/restore cases and real CMD startup with the actual images. Phone operations in CI are simulated. Hardware Ubuntu boot remains a separate milestone. The original diagnostic builders and shared templates remain dependencies and are not archived.

### Revalidate and package a successful image without compiling it again

The observer helper is a binary firmware input, so `.gitattributes` forces LF on Windows. The first Windows BOOT 3 packaging attempt stopped safely because checkout had converted this file to CRLF. The compiled image and Linux checks had already passed.

`repackage_ubuntu_boot_handoff.py` pins that successful image job, artifact ID and ZIP digest. `repackage-ubuntu-boot-handoff.yml` rechecks the exact payload, peripheral configuration and actual ARM64 helpers, and compares the patched source used by the force-guard harness with the compiled-source manifest. It then tests the prepared ZIP on Windows. The resulting package uses the same kernel/image; this route is for host packaging changes that preserve the runtime payload byte for byte.
