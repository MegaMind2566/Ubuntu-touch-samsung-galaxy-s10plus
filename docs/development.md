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
